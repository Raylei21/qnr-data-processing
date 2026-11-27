"""Split delimiter-joined multiple-choice cells into per-option membership.

Some questionnaire exports store a multiple-choice question in a single cell,
joining the selected options with a delimiter such as ``┋``. This module turns
such cells into per-option boolean masks, and understands two conventions that
often accompany that encoding:

- ``(跳过)`` marks a respondent who was skipped out of the question.
- ``others, please specify〖原话〗`` marks an "other" selection whose verbatim
  follows the ``〖`` marker.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

DEFAULT_SKIP_VALUES = ["(跳过)"]
OPEN_MARK = "〖"
OPEN_CLOSE = "〗"


def question_delimiter(question: dict[str, Any]) -> str | None:
    """Return the delimiter of a multi question, or ``None`` for one-hot."""
    if question.get("delimiter"):
        return str(question["delimiter"])
    for column in question.get("columns", []):
        if column.get("delimiter"):
            return str(column["delimiter"])
    return None


def resolve_skip_values(column: dict[str, Any], question: dict[str, Any]) -> list[str]:
    values = (
        column.get("skip_values")
        or question.get("skip_values")
        or DEFAULT_SKIP_VALUES
    )
    return [str(value) for value in values]


def normalize_options(options: list[Any]) -> list[dict[str, Any]]:
    """Normalize an option list of strings or dicts into value/label records."""
    normalized: list[dict[str, Any]] = []
    for item in options:
        if isinstance(item, dict):
            if "value" not in item:
                raise ValueError("选项对象必须包含 value")
            normalized.append(
                {
                    "value": item["value"],
                    "label": str(item.get("label", item["value"])),
                    "exclusive": bool(item.get("exclusive", False)),
                }
            )
        else:
            normalized.append({"value": item, "label": str(item), "exclusive": False})
    return normalized


def tokenize(series: pd.Series, delimiter: str) -> pd.Series:
    def _split(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, float) and pd.isna(value):
            return []
        return [
            token.strip() for token in str(value).split(delimiter) if token.strip()
        ]

    return series.map(_split)


def base_token(token: str) -> str:
    """Strip an inline open-ended verbatim (``option〖原文〗``) to the option text."""
    return token.split(OPEN_MARK, 1)[0].strip()


def membership(tokens: pd.Series, option_text: str) -> pd.Series:
    target = str(option_text).strip()
    return tokens.map(lambda values: any(base_token(token) == target for token in values))


def answered(tokens: pd.Series, skip_values: list[str]) -> pd.Series:
    skip = {str(value).strip() for value in skip_values}
    return tokens.map(lambda values: any(token not in skip for token in values))


def open_verbatims(series: pd.Series, delimiter: str) -> pd.DataFrame:
    """Return one row per inline verbatim (respondent_id, option, response)."""
    rows: list[dict[str, Any]] = []
    for respondent_id, value in series.items():
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        for token in str(value).split(delimiter):
            token = token.strip()
            if OPEN_MARK not in token:
                continue
            option, _, verbatim = token.partition(OPEN_MARK)
            verbatim = verbatim.rstrip(OPEN_CLOSE).strip()
            if verbatim:
                rows.append(
                    {
                        "respondent_id": respondent_id,
                        "option": option.strip(),
                        "response": verbatim,
                    }
                )
    return pd.DataFrame(rows, columns=["respondent_id", "option", "response"])
