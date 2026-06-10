"""Discover survey questions from exported response headers."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import DataValidationError


HEADER_PATTERN = re.compile(
    r"^(?P<id>HQ\d+|Q\d+[A-Za-z]?)(?:\[(?P<sub>[^\]]+)\])?\.(?P<body>.*)$"
)
OPTION_PATTERN = re.compile(r"\[([^\]]+)\]\s*$")


def discover_task(
    data_path: str | Path,
    output_path: str | Path,
    numeric_sheet: str = "数字版",
    text_sheet: str = "文字版",
    id_column: str = "id",
    questionnaire_path: str | Path | None = None,
) -> dict[str, Any]:
    data_path = Path(data_path).resolve()
    numeric = pd.read_excel(data_path, sheet_name=numeric_sheet, dtype=object)
    text = pd.read_excel(data_path, sheet_name=text_sheet, dtype=object)
    if list(numeric.columns) != list(text.columns):
        raise DataValidationError("数字版和文字版列名或列序不一致，无法自动生成配置")
    if id_column not in text.columns:
        raise DataValidationError(f"找不到 respondent ID 列: {id_column}")

    questionnaire = (
        parse_questionnaire(questionnaire_path) if questionnaire_path else {}
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    warnings: list[str] = []

    for column in text.columns:
        match = HEADER_PATTERN.match(str(column))
        if not match:
            continue
        question_id = match.group("id")
        body = match.group("body")
        qtype = _detect_type(body)
        option_match = OPTION_PATTERN.search(body)
        option = option_match.group(1).strip() if option_match else None
        clean_text = _clean_question_text(body)

        item: dict[str, Any] = {
            "numeric": str(column),
            "text": str(column),
        }
        if option and option not in {"CODE", "VALUE"}:
            item["label"] = option
            item["option"] = option
        elif match.group("sub"):
            item["label"] = str(match.group("sub"))

        grouped.setdefault(question_id, []).append(
            {
                "type": qtype,
                "text": clean_text,
                "column": item,
                "special": option if option in {"CODE", "VALUE"} else None,
            }
        )

    questions: list[dict[str, Any]] = []
    for question_id, items in grouped.items():
        types = {item["type"] for item in items}
        qtype = next(iter(types)) if len(types) == 1 else "single"
        if len(types) > 1:
            warnings.append(
                f"{question_id} 的列包含多种题型标记 {sorted(types)}，草稿按 single 处理"
            )
        question: dict[str, Any] = {
            "id": question_id,
            "type": qtype,
            "text": items[0]["text"],
            "columns": [item["column"] for item in items],
        }

        questionnaire_id = re.sub(r"^HQ", "", question_id)
        questionnaire_id = re.sub(r"^Q", "", questionnaire_id)
        questionnaire_id = re.sub(r"[A-Za-z]+$", "", questionnaire_id)
        options = questionnaire.get(questionnaire_id, {}).get("options", [])
        if qtype in {"single", "matrix_single"}:
            observed = _observed_values(
                text, [item["column"]["text"] for item in items]
            )
            if options:
                reconciled, option_warnings = _reconcile_options(options, observed)
                if reconciled:
                    question["options"] = reconciled
                warnings.extend(
                    f"{question_id}: {message}" for message in option_warnings
                )
            elif qtype == "matrix_single" or len(items) == 1:
                question["options"] = observed
        if qtype == "multi":
            question["base"] = "any_selected"
            question["selected_values"] = [1, "1", True, "是", "Yes", "YES"]
        if any(item["special"] for item in items):
            warnings.append(
                f"{question_id} 含 CODE/VALUE 辅助列，请在正式任务中确认保留哪些列"
            )
        questions.append(question)

    task = {
        "inputs": {
            "numeric": {
                "path": str(data_path),
                "sheet": numeric_sheet,
                "id_column": id_column,
            },
            "text": {
                "path": str(data_path),
                "sheet": text_sheet,
                "id_column": id_column,
            },
        },
        "questions": questions,
        "cleaning": [],
        "groups": [],
        "output": {
            "table_path": "output/questionnaire_tables.xlsx",
            "audit_path": "output/audit.json",
            "cleaned_path": "output/cleaned.xlsx",
        },
        "discovery_warnings": warnings,
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(task, handle, ensure_ascii=False, indent=2)
    return task


def parse_questionnaire(path: str | Path) -> dict[str, dict[str, Any]]:
    frame = pd.read_excel(path, sheet_name=0, header=None, dtype=object)
    questions: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    for _, row in frame.iterrows():
        raw_id = row.iloc[0] if len(row) else None
        text = row.iloc[1] if len(row) > 1 else None
        if pd.notna(raw_id) and pd.notna(text):
            question_id = _normalize_question_id(raw_id)
            current = {
                "text": str(text).strip(),
                "type": _detect_type(str(text)),
                "options": [],
            }
            questions[question_id] = current
            continue
        if current is None or pd.isna(text):
            continue
        option = str(text).strip()
        if not option or option.startswith("="):
            continue
        current["options"].append(option)
    return questions


def _detect_type(text: str) -> str:
    if "多选" in text:
        return "multi"
    if "矩阵单选" in text:
        return "matrix_single"
    if "填空" in text or "开放" in text:
        return "open"
    return "single"


def _clean_question_text(body: str) -> str:
    text = re.sub(r"\((?:多选|矩阵单选|单选|填空|开放)\)", "", body)
    text = OPTION_PATTERN.sub("", text)
    text = re.sub(r"\{[^{}]*\}", "", text)
    return text.strip()


def _normalize_question_id(value: Any) -> str:
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _observed_values(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for column in columns:
        for value in frame[column].dropna():
            label = str(value).strip()
            if not label or label in seen:
                continue
            seen.add(label)
            values.append(label)
    return values


def _reconcile_options(
    questionnaire_options: list[Any], observed_values: list[Any]
) -> tuple[list[str], list[str]]:
    questionnaire = [
        str(value).strip() for value in questionnaire_options if str(value).strip()
    ]
    observed = [str(value).strip() for value in observed_values if str(value).strip()]
    remaining = list(observed)
    reconciled: list[str] = []
    warnings: list[str] = []

    for option in questionnaire:
        match = _best_observed_match(option, remaining)
        if match is None:
            reconciled.append(option)
            continue
        reconciled.append(match)
        remaining.remove(match)
        if match != option:
            warnings.append(f"问卷选项“{option}”按数据标签“{match}”出数")

    if remaining:
        reconciled.extend(remaining)
        warnings.append(f"数据中存在问卷未列出的选项: {remaining}")
    return list(dict.fromkeys(reconciled)), warnings


def _best_observed_match(option: str, candidates: list[str]) -> str | None:
    normalized_option = _normalize_option_text(option)
    for candidate in candidates:
        if _normalize_option_text(candidate) == normalized_option:
            return candidate

    scores = [
        (
            SequenceMatcher(
                None, normalized_option, _normalize_option_text(candidate)
            ).ratio(),
            candidate,
        )
        for candidate in candidates
    ]
    if not scores:
        return None
    score, candidate = max(scores, key=lambda item: item[0])
    return candidate if score >= 0.82 else None


def _normalize_option_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).lower()
