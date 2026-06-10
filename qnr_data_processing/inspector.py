"""Create a deterministic inventory before an agent writes the task spec."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .errors import DataValidationError


def inspect_file(path: str | Path, output_path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        raise DataValidationError(f"文件不存在: {source}")

    suffix = source.suffix.lower()
    inventory: dict[str, Any] = {"path": str(source.resolve()), "sheets": []}
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        excel = pd.ExcelFile(source)
        for sheet in excel.sheet_names:
            frame = pd.read_excel(source, sheet_name=sheet, dtype=object)
            inventory["sheets"].append(_frame_inventory(sheet, frame))
    elif suffix == ".csv":
        frame = pd.read_csv(source, dtype=object)
        inventory["sheets"].append(_frame_inventory("csv", frame))
    else:
        raise DataValidationError(f"不支持的文件格式: {suffix}")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(inventory, handle, ensure_ascii=False, indent=2)
    return inventory


def _frame_inventory(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    columns = []
    for column in frame.columns:
        series = frame[column]
        examples = [
            _json_value(value)
            for value in series.dropna().drop_duplicates().head(5).tolist()
        ]
        columns.append(
            {
                "name": str(column),
                "non_null": int(series.notna().sum()),
                "unique": int(series.nunique(dropna=True)),
                "examples": examples,
            }
        )
    return {"name": name, "rows": len(frame), "columns": columns}


def _json_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
