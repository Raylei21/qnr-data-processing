"""Strict structured rule engine shared by cleaning, groups, bases and nets."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from .dataset import SurveyDataset
from .errors import RuleError
from .multiselect import (
    answered as multi_answered,
    membership as multi_membership,
    question_delimiter,
    resolve_skip_values,
    tokenize,
)


LOGICAL_KEYS = {"all", "any", "not"}
OPERATORS = {
    "eq",
    "neq",
    "in",
    "not_in",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "contains",
    "not_contains",
    "regex",
    "missing",
    "not_missing",
    "selected",
    "not_selected",
}


class RuleEvaluator:
    def __init__(self, dataset: SurveyDataset, questions: list[dict[str, Any]]):
        self.dataset = dataset
        self.questions = {str(q["id"]): q for q in questions}

    def evaluate(self, rule: dict[str, Any]) -> pd.Series:
        if not isinstance(rule, dict) or not rule:
            raise RuleError("规则必须是非空对象")

        logical = LOGICAL_KEYS.intersection(rule)
        if logical:
            if len(logical) != 1 or len(rule) != 1:
                raise RuleError(f"逻辑规则只能包含一个键: {rule}")
            key = next(iter(logical))
            if key == "not":
                return ~self.evaluate(rule[key])
            children = rule[key]
            if not isinstance(children, list) or not children:
                raise RuleError(f"{key} 必须是非空数组")
            masks = [self.evaluate(child) for child in children]
            frame = pd.concat(masks, axis=1)
            return frame.all(axis=1) if key == "all" else frame.any(axis=1)

        return self._evaluate_condition(rule)

    def _evaluate_condition(self, condition: dict[str, Any]) -> pd.Series:
        op = condition.get("op")
        if op in {"selected", "not_selected"} and "question" in condition and "option" in condition:
            question = self.questions.get(str(condition["question"]))
            if question is not None and question_delimiter(question):
                mask = self._delimiter_option_membership(question, condition)
                if op == "not_selected":
                    mask = ~mask
                    if condition.get("missing_policy", "exclude") == "exclude":
                        mask = mask & self._delimiter_question_answered(question)
                return mask.fillna(False)
        if op not in OPERATORS:
            raise RuleError(f"不支持的操作符: {op}")
        series_list = self._resolve_series(condition)
        column_logic = condition.get("column_logic", "any")
        if column_logic not in {"any", "all"}:
            raise RuleError("column_logic 只能是 any 或 all")
        masks = [self._apply_operator(series, op, condition) for series in series_list]
        combined = pd.concat(masks, axis=1)
        return combined.any(axis=1) if column_logic == "any" else combined.all(axis=1)

    def _resolve_series(self, condition: dict[str, Any]) -> list[pd.Series]:
        source = condition.get("source", "numeric")
        frame = self.dataset.frame(source)

        if "column" in condition:
            columns = [condition["column"]]
        elif "columns" in condition:
            columns = condition["columns"]
            if not isinstance(columns, list) or not columns:
                raise RuleError("columns 必须是非空数组")
        elif "column_regex" in condition:
            try:
                pattern = re.compile(condition["column_regex"])
            except re.error as exc:
                raise RuleError(f"无效 column_regex: {exc}") from exc
            columns = [str(col) for col in frame.columns if pattern.search(str(col))]
        elif "question" in condition:
            columns = self._question_columns(
                str(condition["question"]), source, condition.get("option")
            )
        else:
            raise RuleError("条件必须包含 column、columns、column_regex 或 question")

        missing = [column for column in columns if column not in frame.columns]
        if missing:
            raise RuleError(f"{source} 数据找不到列: {missing}")
        if not columns:
            raise RuleError(f"条件没有匹配到任何列: {condition}")
        return [frame[column] for column in columns]

    def _question_columns(
        self, question_id: str, source: str, option: Any = None
    ) -> list[str]:
        question = self.questions.get(question_id)
        if question is None:
            raise RuleError(f"找不到题目配置: {question_id}")

        columns = question["columns"]
        if option is not None:
            option_text = str(option)
            columns = [
                item
                for item in columns
                if option_text
                in {
                    str(item.get("option", "")),
                    str(item.get("code", "")),
                    str(item.get("label", "")),
                }
            ]
            if not columns:
                raise RuleError(f"题目 {question_id} 找不到选项: {option}")

        key = "text" if source == "text" else "numeric"
        resolved = [item[key] for item in columns if item.get(key)]
        if not resolved:
            raise RuleError(f"题目 {question_id} 没有配置 {source} 列")
        return resolved

    def _delimiter_option_membership(
        self, question: dict[str, Any], condition: dict[str, Any]
    ) -> pd.Series:
        source = condition.get("source", "text")
        frame = self.dataset.frame(source)
        delimiter = question_delimiter(question)
        texts = self._delimiter_option_texts(question, condition["option"])
        masks: list[pd.Series] = []
        for column in question["columns"]:
            name = column.get(source)
            if not name:
                continue
            tokens = tokenize(frame[name], delimiter)
            mask = pd.Series(False, index=frame.index)
            for text in texts:
                mask = mask | multi_membership(tokens, text)
            masks.append(mask)
        if not masks:
            raise RuleError(f"题目 {question['id']} 没有配置 {source} 列")
        return pd.concat(masks, axis=1).any(axis=1)

    def _delimiter_question_answered(
        self, question: dict[str, Any]
    ) -> pd.Series:
        delimiter = question_delimiter(question)
        masks: list[pd.Series] = []
        for column in question["columns"]:
            source = "text" if column.get("text") else "numeric"
            name = column.get(source)
            if not name:
                continue
            tokens = tokenize(self.dataset.frame(source)[name], delimiter)
            masks.append(
                multi_answered(tokens, resolve_skip_values(column, question))
            )
        if not masks:
            return pd.Series(False, index=self.dataset.text.index)
        return pd.concat(masks, axis=1).any(axis=1)

    @staticmethod
    def _delimiter_option_texts(
        question: dict[str, Any], option_text: Any
    ) -> set[str]:
        target = str(option_text).strip()
        texts = {target}
        options = question.get("options")
        for column in question.get("columns", []):
            if column.get("options"):
                options = column["options"]
                break
        for item in options or []:
            if isinstance(item, dict):
                keys = {
                    str(item.get("value", "")).strip(),
                    str(item.get("label", "")).strip(),
                    str(item.get("code", "")).strip(),
                }
                if target in keys:
                    texts.add(str(item.get("value", "")).strip())
        return {text for text in texts if text}

    def _apply_operator(
        self, series: pd.Series, op: str, condition: dict[str, Any]
    ) -> pd.Series:
        answered = ~(series.isna() | series.astype("string").str.strip().eq(""))
        if op == "missing":
            return ~answered
        if op == "not_missing":
            return answered

        value = condition.get("value")
        if op in {"eq", "neq", "in", "not_in"}:
            result = self._compare_values(series, op, value)
        elif op in {"gt", "gte", "lt", "lte", "between"}:
            result = self._compare_numeric(series, op, value)
        elif op in {"contains", "not_contains", "regex"}:
            result = self._compare_text(series, op, value)
        elif op in {"selected", "not_selected"}:
            selected_values = condition.get(
                "selected_values", [1, "1", True, "是", "Yes", "YES"]
            )
            result = self._membership(series, selected_values)
            if op == "not_selected":
                result = ~result
        else:
            raise RuleError(f"未实现的操作符: {op}")
        result = result.fillna(False)
        if op in {"neq", "not_in", "not_contains", "not_selected"}:
            missing_policy = condition.get("missing_policy", "exclude")
            if missing_policy not in {"exclude", "include"}:
                raise RuleError("missing_policy 只能是 exclude 或 include")
            if missing_policy == "exclude":
                result = result & answered
        return result

    @staticmethod
    def _compare_values(series: pd.Series, op: str, value: Any) -> pd.Series:
        if op in {"in", "not_in"}:
            if not isinstance(value, list):
                raise RuleError(f"{op} 的 value 必须是数组")
            result = RuleEvaluator._membership(series, value)
            return ~result if op == "not_in" else result

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result = pd.to_numeric(series, errors="coerce").eq(value)
        else:
            result = series.astype("string").str.strip().eq(str(value).strip())
        return ~result if op == "neq" else result

    @staticmethod
    def _membership(series: pd.Series, values: list[Any]) -> pd.Series:
        numeric_values = [
            value
            for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        text_values = {str(value).strip() for value in values}
        numeric_match = pd.to_numeric(series, errors="coerce").isin(numeric_values)
        text_match = series.astype("string").str.strip().isin(text_values)
        return numeric_match | text_match

    @staticmethod
    def _compare_numeric(series: pd.Series, op: str, value: Any) -> pd.Series:
        numeric = pd.to_numeric(series, errors="coerce")
        if op == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise RuleError("between 的 value 必须是 [最小值, 最大值]")
            return numeric.between(value[0], value[1], inclusive="both")
        if not isinstance(value, (int, float)):
            raise RuleError(f"{op} 的 value 必须是数字")
        return {
            "gt": numeric.gt,
            "gte": numeric.ge,
            "lt": numeric.lt,
            "lte": numeric.le,
        }[op](value)

    @staticmethod
    def _compare_text(series: pd.Series, op: str, value: Any) -> pd.Series:
        if not isinstance(value, str):
            raise RuleError(f"{op} 的 value 必须是字符串")
        text = series.astype("string")
        if op == "regex":
            try:
                return text.str.contains(value, regex=True, na=False)
            except re.error as exc:
                raise RuleError(f"无效正则表达式: {exc}") from exc
        result = text.str.contains(value, regex=False, na=False)
        return ~result if op == "not_contains" else result
