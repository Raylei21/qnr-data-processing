"""Configuration-driven cleaning and long-format tabulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .dataset import SurveyDataset
from .errors import ConfigError, DataValidationError
from .multiselect import (
    answered as multi_answered,
    base_token,
    membership as multi_membership,
    normalize_options,
    resolve_skip_values,
    tokenize,
)
from .quality import (
    group_overlap_audit,
    piping_checks,
    run_quality_checks,
    table_consistency_checks,
    weight_diagnostics,
)
from .rules import RuleEvaluator
from .weighting import resolve_weights


@dataclass
class ProcessingResult:
    dataset: SurveyDataset
    table: pd.DataFrame
    audit: dict[str, Any]
    questions: list[dict[str, Any]]
    privacy: dict[str, Any]
    weights: pd.Series


def process(spec: dict[str, Any], dataset: SurveyDataset) -> ProcessingResult:
    validate_question_columns(dataset, spec["questions"])
    privacy = spec.get("privacy", {})
    include_ids = bool(privacy.get("include_respondent_ids", False))
    input_quality = run_quality_checks(
        dataset,
        spec["questions"],
        spec.get("quality_checks", []),
        include_ids,
    ) + piping_checks(
        dataset, spec["questions"], spec.get("piping", []), include_ids
    )

    cleaning_audit: list[dict[str, Any]] = []
    working = dataset
    for item in spec.get("cleaning", []):
        ctype = item.get("type", "rule")
        before = len(working.text)
        if ctype == "dedup":
            keep_mask = _dedup_keep_mask(working, item)
            removed_ids = (
                working.respondent_ids[~keep_mask].astype(str).tolist()
                if include_ids
                else []
            )
            working = working.subset(keep_mask)
            cleaning_audit.append(
                {
                    "name": item["name"],
                    "type": ctype,
                    "before": before,
                    "removed": int((~keep_mask).sum()),
                    "after": len(working.text),
                    "removed_ids": removed_ids,
                }
            )
        elif ctype == "normalize":
            changed, working = _normalize_dataset(working, item)
            cleaning_audit.append(
                {
                    "name": item["name"],
                    "type": ctype,
                    "before": before,
                    "removed": 0,
                    "after": len(working.text),
                    "changed": changed,
                    "removed_ids": [],
                }
            )
        else:
            evaluator = RuleEvaluator(working, spec["questions"])
            remove_mask = evaluator.evaluate(item["rule"])
            removed_ids = (
                working.respondent_ids[remove_mask].astype(str).tolist()
                if include_ids
                else []
            )
            working = working.subset(~remove_mask)
            cleaning_audit.append(
                {
                    "name": item["name"],
                    "type": ctype,
                    "before": before,
                    "removed": int(remove_mask.sum()),
                    "after": len(working.text),
                    "removed_ids": removed_ids,
                }
            )

    evaluator = RuleEvaluator(working, spec["questions"])
    final_quality = run_quality_checks(
        working,
        spec["questions"],
        spec.get("quality_checks", []),
        include_ids,
    ) + piping_checks(working, spec["questions"], spec.get("piping", []), include_ids)

    derived, segment_audit, segment_groups = _evaluate_segments(
        working, evaluator, spec.get("segments", [])
    )
    if derived:
        working = working.with_columns(derived)
        evaluator = RuleEvaluator(working, spec["questions"])

    weights, weight_audit = resolve_weights(
        working, spec["questions"], spec.get("weight")
    )
    groups = {"总体": pd.Series(True, index=working.text.index)}
    for name, mask in segment_groups.items():
        if name in groups:
            raise ConfigError(f"分组名称重复: {name}")
        groups[name] = mask
    for item in spec.get("groups", []):
        if item["name"] in groups:
            raise ConfigError(f"分组名称重复: {item['name']}")
        groups[item["name"]] = evaluator.evaluate(item["rule"])

    rows: list[dict[str, Any]] = []
    for question in spec["questions"]:
        rows.extend(_tabulate_question(working, evaluator, question, groups, weights))

    table = pd.DataFrame(
        rows,
        columns=[
            "question_id",
            "question",
            "subitem",
            "option",
            "group",
            "count",
            "base",
            "percent",
            "weighted_count",
            "weighted_base",
            "weighted_percent",
        ],
    )
    table_checks = table_consistency_checks(table, spec["questions"])
    warnings = list(
        dict.fromkeys(
            [
                *working.warnings,
                *[str(item) for item in spec.get("discovery_warnings", [])],
            ]
        )
    )
    audit = {
        "input_rows": len(dataset.text),
        "output_rows": len(working.text),
        "warnings": warnings,
        "cleaning": cleaning_audit,
        "groups": {name: int(mask.sum()) for name, mask in groups.items()},
        "group_weighted_bases": {
            name: float(weights[mask].sum()) for name, mask in groups.items()
        },
        "group_membership": group_overlap_audit(groups),
        "segments": segment_audit,
        "quality_checks_before_cleaning": input_quality,
        "quality_checks": final_quality,
        "table_checks": table_checks,
        "weights": {**weight_diagnostics(weights), **weight_audit},
        "questions": len(spec["questions"]),
    }
    return ProcessingResult(
        dataset=working,
        table=table,
        audit=audit,
        questions=spec["questions"],
        privacy=privacy,
        weights=weights,
    )


def validate_question_columns(
    dataset: SurveyDataset, questions: list[dict[str, Any]]
) -> None:
    missing: list[str] = []
    for question in questions:
        for column in question["columns"]:
            for source, frame in (("text", dataset.text), ("numeric", dataset.numeric)):
                name = column.get(source)
                if name and name not in frame.columns:
                    missing.append(f"{question['id']}:{source}:{name}")
    if missing:
        raise DataValidationError("题目配置引用了不存在的列: " + ", ".join(missing))


def _tabulate_question(
    dataset: SurveyDataset,
    evaluator: RuleEvaluator,
    question: dict[str, Any],
    groups: dict[str, pd.Series],
    weights: pd.Series,
) -> list[dict[str, Any]]:
    qtype = question["type"]
    if qtype == "multi":
        return _tabulate_multi(dataset, evaluator, question, groups, weights)
    if qtype == "open":
        return _tabulate_open(dataset, evaluator, question, groups, weights)
    return _tabulate_single(dataset, evaluator, question, groups, weights)


def _tabulate_single(
    dataset: SurveyDataset,
    evaluator: RuleEvaluator,
    question: dict[str, Any],
    groups: dict[str, pd.Series],
    weights: pd.Series,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in question["columns"]:
        source, name = _preferred_column(column)
        series = dataset.frame(source)[name]
        answered = _answered(series)
        base_mask = _resolve_question_base(
            evaluator, question.get("base", "answered"), answered, dataset.text.index
        )
        options = _single_options(series, question.get("options"))
        subitem = column.get("label") or column.get("option") or ""

        for option in options:
            value = option["value"]
            selected = _value_mask(series, value)
            rows.extend(
                _group_rows(
                    question,
                    subitem,
                    option["label"],
                    selected,
                    base_mask,
                    groups,
                    weights,
                )
            )

        for net in question.get("nets", []):
            if "values" in net:
                net_mask = _membership(series, net["values"])
            elif "rule" in net:
                net_mask = evaluator.evaluate(net["rule"])
            else:
                raise ConfigError(
                    f"题目 {question['id']} 的 net {net.get('name')} "
                    "必须包含 values 或 rule"
                )
            rows.extend(
                _group_rows(
                    question, subitem, net["name"], net_mask, base_mask, groups, weights
                )
            )
    return rows


def _tabulate_multi(
    dataset: SurveyDataset,
    evaluator: RuleEvaluator,
    question: dict[str, Any],
    groups: dict[str, pd.Series],
    weights: pd.Series,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    selections: list[tuple[str, pd.Series]] = []
    answers: list[pd.Series] = []

    for column in question["columns"]:
        delimiter = column.get("delimiter") or question.get("delimiter")
        if delimiter:
            source, name = _preferred_column(column)
            series = dataset.frame(source)[name]
            skip = resolve_skip_values(column, question)
            tokens = tokenize(series, delimiter)
            answers.append(multi_answered(tokens, skip))
            for option in _multi_options(column, question, tokens):
                selections.append(
                    (option["label"], multi_membership(tokens, option["value"]))
                )
        else:
            source, name = _preferred_column(column)
            series = dataset.frame(source)[name]
            selected_values = column.get(
                "selected_values", question.get("selected_values", [1, "1", True, "是"])
            )
            label = (
                column.get("label")
                or column.get("option")
                or column.get("text")
                or column.get("numeric")
            )
            selections.append((str(label), _membership(series, selected_values)))
            answers.append(_answered(series))

    base_mode = question.get("base", "any_answered")
    if base_mode == "all":
        base_mask = pd.Series(True, index=dataset.text.index)
    elif base_mode == "any_selected":
        base_mask = pd.concat([mask for _, mask in selections], axis=1).any(axis=1)
    elif base_mode == "any_answered":
        base_mask = pd.concat(answers, axis=1).any(axis=1)
    elif isinstance(base_mode, dict):
        base_mask = evaluator.evaluate(base_mode)
    else:
        raise ConfigError(f"题目 {question['id']} 的 base 配置无效: {base_mode}")

    for label, selected in selections:
        rows.extend(
            _group_rows(question, "", label, selected, base_mask, groups, weights)
        )

    for net in question.get("nets", []):
        net_mask = evaluator.evaluate(net["rule"])
        rows.extend(
            _group_rows(
                question, "", net["name"], net_mask, base_mask, groups, weights
            )
        )
    return rows


def _multi_options(
    column: dict[str, Any],
    question: dict[str, Any],
    tokens: pd.Series,
) -> list[dict[str, Any]]:
    configured = column.get("options") or question.get("options")
    if configured:
        return _normalize_options(configured)

    seen: list[str] = []
    for values in tokens:
        for token in values:
            base = base_token(token)
            if base and base not in seen:
                seen.append(base)
    if not seen:
        raise ConfigError(
            f"题目 {question['id']} 的多选列使用 delimiter 但未配置 options，"
            "且数据中没有可识别的选项"
        )
    return [{"value": value, "label": value} for value in seen]


def _tabulate_open(
    dataset: SurveyDataset,
    evaluator: RuleEvaluator,
    question: dict[str, Any],
    groups: dict[str, pd.Series],
    weights: pd.Series,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for column in question["columns"]:
        source, name = _preferred_column(column)
        answered = _answered(dataset.frame(source)[name])
        base_mask = _resolve_question_base(
            evaluator, question.get("base", "all"), answered, dataset.text.index
        )
        subitem = column.get("label") or ""
        rows.extend(
            _group_rows(
                question, subitem, "有填写", answered, base_mask, groups, weights
            )
        )
    return rows


def _group_rows(
    question: dict[str, Any],
    subitem: str,
    option: str,
    selected: pd.Series,
    base_mask: pd.Series,
    groups: dict[str, pd.Series],
    weights: pd.Series,
) -> list[dict[str, Any]]:
    rows = []
    for group_name, group_mask in groups.items():
        group_base = group_mask & base_mask
        base = int(group_base.sum())
        count = int((group_base & selected).sum())
        weighted_base = float(weights[group_base].sum())
        weighted_count = float(weights[group_base & selected].sum())
        rows.append(
            {
                "question_id": str(question["id"]),
                "question": question.get("text", str(question["id"])),
                "subitem": subitem,
                "option": option,
                "group": group_name,
                "count": count,
                "base": base,
                "percent": count / base if base else None,
                "weighted_count": weighted_count,
                "weighted_base": weighted_base,
                "weighted_percent": (
                    weighted_count / weighted_base if weighted_base else None
                ),
            }
        )
    return rows


def _preferred_column(column: dict[str, Any]) -> tuple[str, str]:
    if column.get("text"):
        return "text", column["text"]
    return "numeric", column["numeric"]


def _answered(series: pd.Series) -> pd.Series:
    return ~(series.isna() | series.astype("string").str.strip().eq(""))


def _single_options(
    series: pd.Series, configured: list[Any] | None
) -> list[dict[str, Any]]:
    if configured:
        return _normalize_options(configured)

    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("")]
    return [{"value": value, "label": value} for value in sorted(values.unique())]


def _normalize_options(configured: list[Any]) -> list[dict[str, Any]]:
    try:
        return normalize_options(configured)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _value_mask(series: pd.Series, value: Any) -> pd.Series:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return pd.to_numeric(series, errors="coerce").eq(value)
    return series.astype("string").str.strip().eq(str(value).strip()).fillna(False)


def _membership(series: pd.Series, values: list[Any]) -> pd.Series:
    numeric_values = [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    text_values = {str(value).strip() for value in values}
    return (
        pd.to_numeric(series, errors="coerce").isin(numeric_values)
        | series.astype("string").str.strip().isin(text_values)
    ).fillna(False)


def _resolve_question_base(
    evaluator: RuleEvaluator,
    base: Any,
    answered: pd.Series,
    index: pd.Index,
) -> pd.Series:
    if base == "answered":
        return answered
    if base == "all":
        return pd.Series(True, index=index)
    if isinstance(base, dict):
        return evaluator.evaluate(base)
    raise ConfigError("单选、矩阵或开放题的 base 只能是 all、answered 或结构化规则")


def _dedup_keep_mask(dataset: SurveyDataset, item: dict[str, Any]) -> pd.Series:
    key = item["key"]
    on = item["on"]
    keep = item.get("keep", "max")
    source = item.get("source", "numeric")
    frame = dataset.frame(source)
    if key not in frame.columns:
        raise DataValidationError(f"dedup 找不到 key 列: {key}")
    if on not in frame.columns:
        raise DataValidationError(f"dedup 找不到 on 列: {on}")
    on_values = pd.to_numeric(frame[on], errors="coerce")
    if on_values.notna().sum() == 0:
        raise DataValidationError(f"dedup 的 on 列必须是数字列: {on}")
    key_series = frame[key].astype(str)
    if keep == "max":
        index_of_keep = on_values.groupby(key_series).idxmax()
    else:
        index_of_keep = on_values.groupby(key_series).idxmin()
    keep_mask = pd.Series(False, index=dataset.text.index)
    keep_mask.loc[index_of_keep.values] = True
    return keep_mask


def _normalize_dataset(
    dataset: SurveyDataset, item: dict[str, Any]
) -> tuple[int, SurveyDataset]:
    source = item.get("source", "text")
    column = item["column"]
    op = item["op"]
    frame = dataset.frame(source)
    if column not in frame.columns:
        raise DataValidationError(f"normalize 找不到列: {column}")

    strings = frame[column].astype("string")
    if op == "strip":
        transformed = strings.str.strip()
    elif op == "lstrip":
        transformed = strings.str.lstrip(item.get("value"))
    elif op == "rstrip":
        transformed = strings.str.rstrip(item.get("value"))
    elif op == "lower":
        transformed = strings.str.lower()
    elif op == "replace":
        old = item.get("value")
        if old is None:
            raise ConfigError("normalize replace 必须提供 value（被替换文本）")
        transformed = strings.str.replace(
            old, item.get("replacement", ""), regex=False
        )
    else:
        raise ConfigError(f"normalize 不支持 op: {op}")

    changed = int((strings.ne(transformed) & strings.notna()).sum())
    new_frame = frame.copy()
    new_frame[column] = transformed.where(strings.notna(), None)
    if source == "numeric":
        new_dataset = SurveyDataset(
            numeric=new_frame,
            text=dataset.text.copy(),
            respondent_ids=dataset.text.index,
            warnings=list(dataset.warnings),
        )
    else:
        new_dataset = SurveyDataset(
            numeric=dataset.numeric.copy(),
            text=new_frame,
            respondent_ids=dataset.text.index,
            warnings=list(dataset.warnings),
        )
    return changed, new_dataset


def _evaluate_segments(
    dataset: SurveyDataset,
    evaluator: RuleEvaluator,
    segment_specs: list[dict[str, Any]],
) -> tuple[dict[str, pd.Series], dict[str, Any], dict[str, pd.Series]]:
    derived: dict[str, pd.Series] = {}
    segment_audit: dict[str, Any] = {}
    generated_groups: dict[str, pd.Series] = {}

    for segment in segment_specs:
        name = segment["name"]
        branches = segment["branches"]

        assigned = pd.Series(index=dataset.text.index, dtype=object)
        matched_any = pd.Series(False, index=dataset.text.index)
        branch_masks: list[tuple[dict[str, Any], pd.Series]] = []
        for branch in branches:
            branch_masks.append((branch, evaluator.evaluate(branch["rule"])))

        if segment.get("mutually_exclusive", True):
            hits = pd.Series(0, index=dataset.text.index)
            for _, mask in branch_masks:
                hits = hits + mask.astype(int)
            overlap = hits.gt(1)
            if overlap.any():
                raise DataValidationError(
                    f"分群“{name}”的分支规则存在重叠：{int(overlap.sum())} 个样本同时命中多个分支"
                )

        for branch, mask in branch_masks:
            newly = mask & ~matched_any
            assigned.loc[newly] = branch["value"]
            matched_any = matched_any | mask

        residual = segment.get("residual", "Exclude")
        residual_is_value = isinstance(residual, str) and residual not in {
            "Exclude",
            "exclude",
        }
        if residual_is_value:
            assigned.loc[~matched_any] = residual

        column_name = segment.get("column", name)
        derived[column_name] = assigned
        segment_audit[name] = {
            ("未归属" if pd.isna(value) else str(value)): int(count)
            for value, count in assigned.value_counts(dropna=False).items()
        }

        group_values = [branch["value"] for branch in branches]
        if residual_is_value and residual not in group_values:
            group_values.append(residual)
        for value in group_values:
            group_name = str(value)
            if group_name in generated_groups:
                raise ConfigError(f"分群分组名称重复: {group_name}")
            generated_groups[group_name] = (assigned == value).fillna(False)

    return derived, segment_audit, generated_groups
