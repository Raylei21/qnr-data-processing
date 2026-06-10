"""Configuration-driven cleaning and long-format tabulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .dataset import SurveyDataset
from .errors import ConfigError, DataValidationError
from .quality import (
    group_overlap_audit,
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
    )

    cleaning_audit: list[dict[str, Any]] = []
    working = dataset
    for item in spec.get("cleaning", []):
        evaluator = RuleEvaluator(working, spec["questions"])
        remove_mask = evaluator.evaluate(item["rule"])
        before = len(working.text)
        removed_ids = (
            working.respondent_ids[remove_mask].astype(str).tolist()
            if include_ids
            else []
        )
        working = working.subset(~remove_mask)
        cleaning_audit.append(
            {
                "name": item["name"],
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
    )
    weights, weight_audit = resolve_weights(
        working, spec["questions"], spec.get("weight")
    )
    groups = {"总体": pd.Series(True, index=working.text.index)}
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
    selections: list[pd.Series] = []
    answers: list[pd.Series] = []

    for column in question["columns"]:
        source, name = _preferred_column(column)
        series = dataset.frame(source)[name]
        selected_values = column.get(
            "selected_values", question.get("selected_values", [1, "1", True, "是"])
        )
        selections.append(_membership(series, selected_values))
        answers.append(_answered(series))

    base_mode = question.get("base", "any_answered")
    if base_mode == "all":
        base_mask = pd.Series(True, index=dataset.text.index)
    elif base_mode == "any_selected":
        base_mask = pd.concat(selections, axis=1).any(axis=1)
    elif base_mode == "any_answered":
        base_mask = pd.concat(answers, axis=1).any(axis=1)
    elif isinstance(base_mode, dict):
        base_mask = evaluator.evaluate(base_mode)
    else:
        raise ConfigError(f"题目 {question['id']} 的 base 配置无效: {base_mode}")

    for column, selected in zip(question["columns"], selections):
        label = (
            column.get("label")
            or column.get("option")
            or column.get("text")
            or column.get("numeric")
        )
        rows.extend(
            _group_rows(question, "", str(label), selected, base_mask, groups, weights)
        )

    for net in question.get("nets", []):
        net_mask = evaluator.evaluate(net["rule"])
        rows.extend(
            _group_rows(
                question, "", net["name"], net_mask, base_mask, groups, weights
            )
        )
    return rows


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
        normalized = []
        for item in configured:
            if isinstance(item, dict):
                if "value" not in item:
                    raise ConfigError("选项对象必须包含 value")
                normalized.append(
                    {"value": item["value"], "label": str(item.get("label", item["value"]))}
                )
            else:
                normalized.append({"value": item, "label": str(item)})
        return normalized

    values = series.dropna().astype(str).str.strip()
    values = values[values.ne("")]
    return [{"value": value, "label": value} for value in sorted(values.unique())]


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
