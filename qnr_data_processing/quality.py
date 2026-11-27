"""Survey-research quality diagnostics that never delete respondents silently."""

from __future__ import annotations

from itertools import combinations
from typing import Any

import pandas as pd

from .dataset import SurveyDataset
from .multiselect import (
    answered as multi_answered,
    membership as multi_membership,
    normalize_options,
    question_delimiter,
    resolve_skip_values,
    tokenize,
)
from .rules import RuleEvaluator


def run_quality_checks(
    dataset: SurveyDataset,
    questions: list[dict[str, Any]],
    configured_checks: list[dict[str, Any]],
    include_ids: bool,
) -> list[dict[str, Any]]:
    evaluator = RuleEvaluator(dataset, questions)
    findings: list[dict[str, Any]] = []

    for check in configured_checks:
        mask = evaluator.evaluate(check["rule"])
        findings.append(
            _finding(
                check["name"],
                check.get("severity", "warning"),
                int(mask.sum()),
                dataset.respondent_ids[mask],
                include_ids,
                check.get("description", "自定义质量检查规则"),
            )
        )

    for question in questions:
        findings.extend(_invalid_value_findings(dataset, question, include_ids))
        if question["type"] == "multi":
            finding = _exclusive_finding(dataset, question, include_ids)
            if finding:
                findings.append(finding)
    return findings


def piping_checks(
    dataset: SurveyDataset,
    questions: list[dict[str, Any]],
    piping: list[dict[str, Any]],
    include_ids: bool,
) -> list[dict[str, Any]]:
    """Flag skip-logic violations between a gate question and a target question.

    Two directions are checked per rule:

    - 应跳过却作答: a respondent outside the gate still answered the target.
    - 应作答却跳过: a respondent inside the gate left the target empty/skipped.
    """
    evaluator = RuleEvaluator(dataset, questions)
    question_map = {str(question["id"]): question for question in questions}
    findings: list[dict[str, Any]] = []

    for check in piping:
        name = check.get("name", "跳题逻辑检查")
        gate = check["gate"]
        target_id = str(check["target"])
        question = question_map.get(target_id)
        if question is None:
            findings.append(
                _finding(
                    f"{name}: 找不到目标题目",
                    "error",
                    0,
                    dataset.respondent_ids[:0],
                    include_ids,
                    f"piping target 不存在: {target_id}",
                )
            )
            continue
        skip_values = check.get("skip_values", ["(跳过)"])
        should_see = evaluator.evaluate(gate)
        answered = _question_answered(dataset, question, skip_values)

        leak = answered & ~should_see
        if leak.any():
            findings.append(
                _finding(
                    f"{name}: 应跳过却作答",
                    "error",
                    int(leak.sum()),
                    dataset.respondent_ids[leak],
                    include_ids,
                    f"{target_id} 在 gate 之外仍有作答",
                )
            )
        gap = should_see & ~answered
        if gap.any():
            findings.append(
                _finding(
                    f"{name}: 应作答却跳过",
                    "error",
                    int(gap.sum()),
                    dataset.respondent_ids[gap],
                    include_ids,
                    f"{target_id} 在 gate 之内缺失或跳过",
                )
            )
    return findings


def table_consistency_checks(
    table: pd.DataFrame, questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    question_map = {str(question["id"]): question for question in questions}

    for question_id, question_table in table.groupby("question_id", sort=False):
        question = question_map[question_id]
        nets = {net["name"] for net in question.get("nets", [])}
        if question["type"] not in {"single", "matrix_single", "numeric"}:
            continue
        if question.get("base", "answered") != "answered":
            continue
        option_rows = question_table[~question_table["option"].isin(nets)]
        for (subitem, group), block in option_rows.groupby(
            ["subitem", "group"], dropna=False, sort=False
        ):
            if block.empty:
                continue
            base = int(block["base"].iloc[0])
            count_sum = int(block["count"].sum())
            if count_sum != base:
                findings.append(
                    {
                        "name": "单选选项合计不等于Base",
                        "severity": "error",
                        "question_id": question_id,
                        "subitem": subitem,
                        "group": group,
                        "base": base,
                        "option_count_sum": count_sum,
                        "difference": count_sum - base,
                    }
                )
            weighted_base = float(block["weighted_base"].iloc[0])
            weighted_sum = float(block["weighted_count"].sum())
            if abs(weighted_sum - weighted_base) > 1e-8:
                findings.append(
                    {
                        "name": "单选加权选项合计不等于加权Base",
                        "severity": "error",
                        "question_id": question_id,
                        "subitem": subitem,
                        "group": group,
                        "weighted_base": weighted_base,
                        "weighted_option_count_sum": weighted_sum,
                        "difference": weighted_sum - weighted_base,
                    }
                )

        for left, right in combinations(question.get("nets", []), 2):
            if "values" not in left or "values" not in right:
                continue
            overlap = sorted(set(map(str, left["values"])) & set(map(str, right["values"])))
            if overlap:
                findings.append(
                    {
                        "name": "NET定义重叠",
                        "severity": "warning",
                        "question_id": question_id,
                        "nets": [left["name"], right["name"]],
                        "overlap_values": overlap,
                    }
                )
    return findings


def group_overlap_audit(groups: dict[str, pd.Series]) -> dict[str, Any]:
    custom = {name: mask for name, mask in groups.items() if name != "总体"}
    overlaps = []
    for (left_name, left), (right_name, right) in combinations(custom.items(), 2):
        count = int((left & right).sum())
        if count:
            overlaps.append(
                {"left": left_name, "right": right_name, "overlap": count}
            )
    if custom:
        any_group = pd.concat(custom.values(), axis=1).any(axis=1)
        unassigned = int((~any_group).sum())
    else:
        unassigned = 0
    return {"overlaps": overlaps, "unassigned": unassigned}


def weight_diagnostics(weights: pd.Series) -> dict[str, Any]:
    total = float(weights.sum())
    squared = float((weights**2).sum())
    effective_n = total**2 / squared if squared else 0.0
    n = len(weights)
    mean = float(weights.mean()) if n else 0.0
    std = float(weights.std(ddof=0)) if n else 0.0
    positive = weights[weights > 0]
    minimum_positive = float(positive.min()) if len(positive) else 0.0
    maximum = float(weights.max()) if n else 0.0
    ratio = maximum / minimum_positive if minimum_positive else None
    return {
        "n": n,
        "sum": total,
        "min": float(weights.min()) if n else 0.0,
        "max": maximum,
        "mean": mean,
        "coefficient_of_variation": std / mean if mean else None,
        "effective_n": effective_n,
        "efficiency": effective_n / n if n else None,
        "design_effect": n / effective_n if effective_n else None,
        "max_to_min_positive_ratio": ratio,
        "warnings": [
            message
            for condition, message in [
                (ratio is not None and ratio > 10, "最大权重超过最小正权重的10倍"),
                (n > 0 and effective_n / n < 0.5, "加权有效样本量低于原样本量的50%"),
            ]
            if condition
        ],
    }


def _invalid_value_findings(
    dataset: SurveyDataset, question: dict[str, Any], include_ids: bool
) -> list[dict[str, Any]]:
    if question["type"] not in {"single", "matrix_single", "numeric"}:
        return []
    if not question.get("options"):
        return []
    valid = {
        str(item.get("value", item)).strip() if isinstance(item, dict) else str(item).strip()
        for item in question["options"]
    }
    findings = []
    for column in question["columns"]:
        source = "text" if column.get("text") else "numeric"
        name = column[source]
        series = dataset.frame(source)[name]
        answered = ~(series.isna() | series.astype("string").str.strip().eq(""))
        invalid = answered & ~series.astype("string").str.strip().isin(valid)
        if invalid.any():
            finding = _finding(
                "发现未配置选项值",
                "error",
                int(invalid.sum()),
                dataset.respondent_ids[invalid],
                include_ids,
                f"{question['id']} / {column.get('label', name)}",
            )
            finding["question_id"] = str(question["id"])
            finding["column"] = name
            finding["invalid_values"] = (
                series[invalid].astype(str).value_counts().head(20).to_dict()
            )
            findings.append(finding)
    return findings


def _exclusive_finding(
    dataset: SurveyDataset, question: dict[str, Any], include_ids: bool
) -> dict[str, Any] | None:
    if question_delimiter(question):
        return _delimiter_exclusive_finding(dataset, question, include_ids)
    columns = question["columns"]
    exclusive_positions = [
        index for index, column in enumerate(columns) if column.get("exclusive")
    ]
    if not exclusive_positions:
        return None
    masks = []
    for column in columns:
        source = "text" if column.get("text") else "numeric"
        values = column.get(
            "selected_values", question.get("selected_values", [1, "1", True, "是"])
        )
        masks.append(_membership(dataset.frame(source)[column[source]], values))
    selected_count = pd.concat(masks, axis=1).sum(axis=1)
    exclusive_selected = pd.concat(
        [masks[index] for index in exclusive_positions], axis=1
    ).any(axis=1)
    violation = exclusive_selected & selected_count.gt(1)
    if not violation.any():
        return None
    return _finding(
        "互斥选项与其他选项同时选择",
        "error",
        int(violation.sum()),
        dataset.respondent_ids[violation],
        include_ids,
        str(question["id"]),
    )


def _delimiter_exclusive_finding(
    dataset: SurveyDataset, question: dict[str, Any], include_ids: bool
) -> dict[str, Any] | None:
    options = question.get("options")
    for column in question.get("columns", []):
        if column.get("options"):
            options = column["options"]
            break
    if not options:
        return None
    normalized = normalize_options(options)
    exclusive_values = [
        str(item["value"]) for item in normalized if item.get("exclusive")
    ]
    if not exclusive_values:
        return None

    delimiter = question_delimiter(question)
    masks = []
    for column in question["columns"]:
        source = "text" if column.get("text") else "numeric"
        tokens = tokenize(dataset.frame(source)[column[source]], delimiter)
        for item in normalized:
            masks.append(multi_membership(tokens, str(item["value"])))
    if not masks:
        return None
    selected_count = pd.concat(masks, axis=1).sum(axis=1)
    exclusive_selected = pd.Series(False, index=selected_count.index)
    for column in question["columns"]:
        source = "text" if column.get("text") else "numeric"
        tokens = tokenize(dataset.frame(source)[column[source]], delimiter)
        for value in exclusive_values:
            exclusive_selected = exclusive_selected | multi_membership(tokens, value)
    violation = exclusive_selected & selected_count.gt(1)
    if not violation.any():
        return None
    return _finding(
        "互斥选项与其他选项同时选择",
        "error",
        int(violation.sum()),
        dataset.respondent_ids[violation],
        include_ids,
        str(question["id"]),
    )


def _question_answered(
    dataset: SurveyDataset, question: dict[str, Any], skip_values: list[str]
) -> pd.Series:
    skip = {str(value).strip() for value in skip_values}
    masks: list[pd.Series] = []
    for column in question["columns"]:
        source = "text" if column.get("text") else "numeric"
        name = column.get(source)
        if not name:
            continue
        series = dataset.frame(source)[name]
        nonempty = ~(series.isna() | series.astype("string").str.strip().eq(""))
        not_skip = ~series.astype("string").str.strip().isin(skip)
        masks.append(nonempty & not_skip)
    if not masks:
        return pd.Series(False, index=dataset.text.index)
    return pd.concat(masks, axis=1).any(axis=1)


def _membership(series: pd.Series, values: list[Any]) -> pd.Series:
    text_values = {str(value).strip() for value in values}
    return series.astype("string").str.strip().isin(text_values).fillna(False)


def _finding(
    name: str,
    severity: str,
    count: int,
    ids: pd.Index,
    include_ids: bool,
    description: str,
) -> dict[str, Any]:
    result = {
        "name": name,
        "severity": severity,
        "count": count,
        "description": description,
    }
    if include_ids:
        result["respondent_ids"] = ids.astype(str).tolist()
    return result
