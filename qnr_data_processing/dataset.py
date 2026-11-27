"""Load numeric/text response data and align respondents safely."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import DataValidationError


@dataclass
class SurveyDataset:
    numeric: pd.DataFrame
    text: pd.DataFrame
    respondent_ids: pd.Index
    warnings: list[str] = field(default_factory=list)

    def subset(self, mask: pd.Series) -> "SurveyDataset":
        aligned = mask.reindex(self.text.index, fill_value=False).astype(bool)
        return SurveyDataset(
            numeric=self.numeric.loc[aligned].copy(),
            text=self.text.loc[aligned].copy(),
            respondent_ids=self.text.index[aligned],
            warnings=list(self.warnings),
        )

    def frame(self, source: str) -> pd.DataFrame:
        if source == "text":
            return self.text
        if source == "numeric":
            return self.numeric
        raise DataValidationError(f"未知数据源: {source}")

    def with_columns(self, mapping: dict[str, pd.Series]) -> "SurveyDataset":
        numeric = self.numeric.copy()
        text = self.text.copy()
        for name, series in mapping.items():
            aligned = series.reindex(self.text.index)
            numeric[name] = aligned
            text[name] = aligned
        return SurveyDataset(
            numeric=numeric,
            text=text,
            respondent_ids=self.text.index,
            warnings=list(self.warnings),
        )


def load_dataset(inputs: dict[str, Any], config_dir: str | Path = ".") -> SurveyDataset:
    config_dir = Path(config_dir)
    text_cfg = inputs["text"]
    numeric_cfg = inputs.get("numeric")

    text = _read_table(text_cfg, config_dir)
    numeric = _read_table(numeric_cfg, config_dir) if numeric_cfg else text.copy()

    text_id = text_cfg.get("id_column")
    numeric_id = numeric_cfg.get("id_column") if numeric_cfg else text_id
    warnings: list[str] = []

    if text_id or numeric_id:
        if not text_id or not numeric_id:
            raise DataValidationError("数字版和文字版必须同时配置 id_column")
        _validate_id_column(text, text_id, "文字版")
        _validate_id_column(numeric, numeric_id, "数字版")

        text = text.set_index(text_id, drop=False)
        numeric = numeric.set_index(numeric_id, drop=False)
        missing_numeric = text.index.difference(numeric.index)
        missing_text = numeric.index.difference(text.index)
        if len(missing_numeric) or len(missing_text):
            raise DataValidationError(
                "数字版和文字版样本 ID 不一致: "
                f"文字版独有 {len(missing_numeric)} 个，数字版独有 {len(missing_text)} 个"
            )
        numeric = numeric.reindex(text.index)
    else:
        if len(text) != len(numeric):
            raise DataValidationError(
                f"未配置 id_column，且行数不一致: 文字版 {len(text)}，数字版 {len(numeric)}"
            )
        warnings.append("未配置 id_column，仅按原始行序对齐数字版和文字版")
        text.index = pd.RangeIndex(len(text), name="_row_id")
        numeric.index = text.index

    return SurveyDataset(
        numeric=numeric,
        text=text,
        respondent_ids=text.index,
        warnings=warnings,
    )


def _read_table(config: dict[str, Any] | None, config_dir: Path) -> pd.DataFrame:
    if not config:
        raise DataValidationError("缺少输入文件配置")
    path = Path(config["path"])
    if not path.is_absolute():
        path = config_dir / path
    if not path.exists():
        raise DataValidationError(f"输入文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        sheet = config.get("sheet", 0)
        return pd.read_excel(path, sheet_name=sheet, dtype=object)
    if suffix == ".csv":
        return pd.read_csv(
            path,
            encoding=config.get("encoding", "utf-8-sig"),
            dtype=object,
        )
    raise DataValidationError(f"不支持的输入格式: {suffix}")


def _validate_id_column(frame: pd.DataFrame, column: str, label: str) -> None:
    if column not in frame.columns:
        raise DataValidationError(f"{label}找不到 ID 列: {column}")
    if frame[column].isna().any():
        raise DataValidationError(f"{label} ID 列存在空值: {column}")
    duplicated = frame[column].duplicated(keep=False)
    if duplicated.any():
        examples = frame.loc[duplicated, column].astype(str).head(5).tolist()
        raise DataValidationError(f"{label} ID 列存在重复值，例如: {examples}")
