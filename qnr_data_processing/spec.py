"""Load and validate the survey task specification."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ConfigError


QUESTION_TYPES = {"single", "multi", "open", "numeric", "matrix_single"}


def load_spec(path: str | Path) -> dict[str, Any]:
    spec_path = Path(path)
    try:
        with spec_path.open("r", encoding="utf-8") as handle:
            spec = json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"配置文件不存在: {spec_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"配置文件不是有效 JSON: 第 {exc.lineno} 行第 {exc.colno} 列"
        ) from exc

    validate_spec(spec)
    spec["_config_dir"] = str(spec_path.resolve().parent)
    return spec


def validate_spec(spec: dict[str, Any]) -> None:
    if not isinstance(spec, dict):
        raise ConfigError("配置根节点必须是 JSON 对象")

    inputs = spec.get("inputs")
    if not isinstance(inputs, dict):
        raise ConfigError("缺少 inputs 配置")
    if not inputs.get("text", {}).get("path"):
        raise ConfigError("inputs.text.path 不能为空")

    questions = spec.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ConfigError("questions 必须是非空数组")

    seen_ids: set[str] = set()
    for position, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise ConfigError(f"questions[{position}] 必须是对象")
        qid = str(question.get("id", "")).strip()
        if not qid:
            raise ConfigError(f"questions[{position}].id 不能为空")
        if qid in seen_ids:
            raise ConfigError(f"题目 id 重复: {qid}")
        seen_ids.add(qid)

        qtype = question.get("type")
        if qtype not in QUESTION_TYPES:
            raise ConfigError(f"题目 {qid} 的 type 不支持: {qtype}")

        columns = question.get("columns")
        if not isinstance(columns, list) or not columns:
            raise ConfigError(f"题目 {qid} 必须配置至少一个 columns 项")
        for column in columns:
            if not isinstance(column, dict):
                raise ConfigError(f"题目 {qid} 的 columns 项必须是对象")
            if not column.get("text") and not column.get("numeric"):
                raise ConfigError(
                    f"题目 {qid} 的每个 columns 项至少需要 text 或 numeric 列名"
                )

    _validate_named_rules(spec.get("cleaning", []), "cleaning")
    _validate_named_rules(spec.get("groups", []), "groups")
    _validate_named_rules(spec.get("quality_checks", []), "quality_checks")
    _validate_weight(spec.get("weight"))

    privacy = spec.get("privacy", {})
    if not isinstance(privacy, dict):
        raise ConfigError("privacy 必须是对象")
    min_cell_size = privacy.get("min_cell_size", 0)
    if not isinstance(min_cell_size, int) or min_cell_size < 0:
        raise ConfigError("privacy.min_cell_size 必须是非负整数")
    for field in ("include_respondent_ids", "include_open_responses"):
        if field in privacy and not isinstance(privacy[field], bool):
            raise ConfigError(f"privacy.{field} 必须是布尔值")


def _validate_named_rules(items: Any, field: str) -> None:
    if not isinstance(items, list):
        raise ConfigError(f"{field} 必须是数组")
    for position, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("name"):
            raise ConfigError(f"{field}[{position}] 必须包含 name")
        if not isinstance(item.get("rule"), dict):
            raise ConfigError(f"{field}[{position}].rule 必须是对象")


def _validate_weight(weight: Any) -> None:
    if weight is None:
        return
    if not isinstance(weight, dict):
        raise ConfigError("weight 必须是对象")
    targets = weight.get("targets")
    if targets is None:
        if not weight.get("column"):
            raise ConfigError("weight 必须包含 column 或 targets")
        return
    method = weight.get("method", "raking")
    if method != "raking":
        raise ConfigError("含 targets 的 weight.method 目前只能是 raking")
    if not isinstance(targets, list) or not targets:
        raise ConfigError("weight.targets 必须是非空数组")
    names: set[str] = set()
    for position, target in enumerate(targets, 1):
        if not isinstance(target, dict) or not target.get("name"):
            raise ConfigError(f"weight.targets[{position}] 必须包含 name")
        if not isinstance(target.get("rule"), dict):
            raise ConfigError(f"weight.targets[{position}].rule 必须是对象")
        name = str(target["name"]).strip()
        if name in names:
            raise ConfigError(f"weight.targets 名称重复: {name}")
        names.add(name)
        if "base" in target and not isinstance(target["base"], dict):
            raise ConfigError(f"weight.targets[{position}].base 必须是规则对象")
        has_target = "target" in target
        has_percent = "percent" in target
        if has_target == has_percent:
            raise ConfigError(
                f"weight.targets[{position}] 必须且只能包含 target 或 percent"
            )
        try:
            share = (
                float(target["target"])
                if has_target
                else float(target["percent"]) / 100.0
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                f"weight.targets[{position}] 的目标比例必须是数字"
            ) from exc
        if not 0 < share < 1:
            raise ConfigError(
                f"weight.targets[{position}] 的目标比例必须大于 0 且小于 100%"
            )
    tolerance = weight.get("tolerance", 0.0001)
    max_iterations = weight.get("max_iterations", 200)
    if not isinstance(tolerance, (int, float)) or tolerance <= 0:
        raise ConfigError("weight.tolerance 必须是正数")
    if not isinstance(max_iterations, int) or max_iterations <= 0:
        raise ConfigError("weight.max_iterations 必须是正整数")
    output_column = weight.get("output_column", "final_weight")
    if not isinstance(output_column, str) or not output_column.strip():
        raise ConfigError("weight.output_column 必须是非空字符串")
    trim = weight.get("trim", {})
    if not isinstance(trim, dict):
        raise ConfigError("weight.trim 必须是对象")
    trim_min = trim.get("min", 0)
    trim_max = trim.get("max", float("inf"))
    if not isinstance(trim_min, (int, float)) or not isinstance(
        trim_max, (int, float)
    ):
        raise ConfigError("weight.trim.min 和 max 必须是数字")
    if trim_min < 0 or trim_max <= 0 or trim_min > trim_max:
        raise ConfigError("weight.trim 必须满足 0 <= min <= max")
    if trim_min > 1 or trim_max < 1:
        raise ConfigError("weight.trim 范围必须包含 1")
