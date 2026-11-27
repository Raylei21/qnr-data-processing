"""Write processing results and audit evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from .multiselect import open_verbatims, question_delimiter
from .processor import ProcessingResult


def write_result(
    result: ProcessingResult, output: dict[str, Any], config_dir: str | Path = "."
) -> dict[str, str]:
    config_dir = Path(config_dir)
    table_path = _resolve_path(
        output.get("table_path", "output/questionnaire_tables.xlsx"), config_dir
    )
    audit_path = _resolve_path(
        output.get("audit_path", "output/audit.json"), config_dir
    )
    cleaned_path_value = output.get("cleaned_path")

    table_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    publication_table = _publication_table(result)

    with pd.ExcelWriter(table_path, engine="openpyxl") as writer:
        _excel_safe_frame(publication_table).to_excel(
            writer, sheet_name="tables_long", index=False
        )
        _excel_safe_frame(_wide_table(publication_table, weighted=False)).to_excel(
            writer, sheet_name="tables_wide", index=False
        )
        if _has_non_unit_weights(publication_table):
            _excel_safe_frame(_wide_table(publication_table, weighted=True)).to_excel(
                writer, sheet_name="tables_weighted", index=False
            )
        _excel_safe_frame(_open_responses(result)).to_excel(
            writer, sheet_name="open_responses", index=False
        )
        _excel_safe_frame(_audit_frames(result.audit)[0]).to_excel(
            writer, sheet_name="cleaning_audit", index=False
        )
        _excel_safe_frame(_audit_frames(result.audit)[1]).to_excel(
            writer, sheet_name="group_bases", index=False
        )
        _excel_safe_frame(_quality_frame(result.audit["quality_checks"])).to_excel(
            writer, sheet_name="quality_checks", index=False
        )
        _excel_safe_frame(
            _quality_frame(result.audit["quality_checks_before_cleaning"])
        ).to_excel(
            writer, sheet_name="quality_before_cleaning", index=False
        )
        _excel_safe_frame(pd.DataFrame(result.audit["table_checks"])).to_excel(
            writer, sheet_name="table_checks", index=False
        )
        _excel_safe_frame(
            _group_membership_frame(result.audit["group_membership"])
        ).to_excel(
            writer, sheet_name="group_membership", index=False
        )
        _excel_safe_frame(_weight_frame(result.audit["weights"])).to_excel(
            writer, sheet_name="weight_diagnostics", index=False
        )
        targets = result.audit["weights"].get("targets", [])
        if targets:
            _excel_safe_frame(pd.DataFrame(targets)).to_excel(
                writer, sheet_name="weight_targets", index=False
            )
        _format_workbook(writer.book)

    with audit_path.open("w", encoding="utf-8") as handle:
        json.dump(result.audit, handle, ensure_ascii=False, indent=2)

    written = {"table": str(table_path), "audit": str(audit_path)}
    if cleaned_path_value:
        cleaned_path = _resolve_path(cleaned_path_value, config_dir)
        cleaned_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(cleaned_path, engine="openpyxl") as writer:
            numeric = result.dataset.numeric.copy()
            text = result.dataset.text.copy()
            weight_column = result.audit["weights"].get("output_column")
            if weight_column:
                numeric[weight_column] = result.weights
                text[weight_column] = result.weights
            _excel_safe_frame(numeric).to_excel(
                writer, sheet_name="numeric", index=False
            )
            _excel_safe_frame(text).to_excel(writer, sheet_name="text", index=False)
        written["cleaned"] = str(cleaned_path)
    return written


def _audit_frames(audit: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    cleaning_rows = [
        {
            "rule": item["name"],
            "type": item.get("type", "rule"),
            "before": item["before"],
            "removed": item["removed"],
            "changed": item.get("changed", 0),
            "after": item["after"],
            "removed_ids": ", ".join(item["removed_ids"]),
        }
        for item in audit["cleaning"]
    ]
    if not cleaning_rows:
        cleaning_rows.append(
            {
                "rule": "未配置清洗规则",
                "type": "rule",
                "before": audit["input_rows"],
                "removed": 0,
                "changed": 0,
                "after": audit["output_rows"],
                "removed_ids": "",
            }
        )
    cleaning = pd.DataFrame(cleaning_rows)
    groups = pd.DataFrame(
        [
            {
                "group": name,
                "base": base,
                "weighted_base": audit.get("group_weighted_bases", {}).get(name),
            }
            for name, base in audit["groups"].items()
        ]
    )
    return cleaning, groups


def _wide_table(table: pd.DataFrame, weighted: bool) -> pd.DataFrame:
    if table.empty:
        return pd.DataFrame()
    count_field = "weighted_count" if weighted else "count"
    base_field = "weighted_base" if weighted else "base"
    percent_field = "weighted_percent" if weighted else "percent"
    suffix = "_weighted" if weighted else ""
    groups = table["group"].drop_duplicates().tolist()
    keys = ["question_id", "question", "subitem", "option"]
    records = []
    for key_values, block in table.groupby(keys, sort=False, dropna=False):
        record = dict(zip(keys, key_values))
        by_group = block.set_index("group")
        for group in groups:
            if group not in by_group.index:
                continue
            row = by_group.loc[group]
            record[f"{group}{suffix}_count"] = row[count_field]
            record[f"{group}{suffix}_base"] = row[base_field]
            record[f"{group}{suffix}_percent"] = row[percent_field]
        records.append(record)
    return pd.DataFrame(records)


def _open_responses(result: ProcessingResult) -> pd.DataFrame:
    columns = [
        "question_id",
        "question",
        "subitem",
        "respondent_id",
        "response",
    ]
    if not result.privacy.get("include_open_responses", False):
        return pd.DataFrame(columns=columns)
    rows = []
    for question in result.questions:
        if question["type"] == "open":
            for column in question["columns"]:
                source = "text" if column.get("text") else "numeric"
                name = column.get(source)
                series = result.dataset.frame(source)[name]
                for respondent_id, value in series.dropna().items():
                    if not str(value).strip():
                        continue
                    rows.append(
                        {
                            "question_id": str(question["id"]),
                            "question": question.get("text", question["id"]),
                            "subitem": column.get("label", ""),
                            "respondent_id": (
                                str(respondent_id)
                                if result.privacy.get("include_respondent_ids", False)
                                else ""
                            ),
                            "response": str(value).strip(),
                        }
                    )
        elif question["type"] == "multi":
            delimiter = question_delimiter(question)
            if not delimiter:
                continue
            for column in question["columns"]:
                source = "text" if column.get("text") else "numeric"
                series = result.dataset.frame(source)[column[source]]
                for record in open_verbatims(series, delimiter).to_dict("records"):
                    rows.append(
                        {
                            "question_id": str(question["id"]),
                            "question": question.get("text", question["id"]),
                            "subitem": record["option"],
                            "respondent_id": (
                                str(record["respondent_id"])
                                if result.privacy.get("include_respondent_ids", False)
                                else ""
                            ),
                            "response": record["response"],
                        }
                    )
    return pd.DataFrame(rows, columns=columns)


def _has_non_unit_weights(table: pd.DataFrame) -> bool:
    if table.empty:
        return False
    return not (
        table["weighted_count"].round(10).eq(table["count"]).all()
        and table["weighted_base"].round(10).eq(table["base"]).all()
    )


def _publication_table(result: ProcessingResult) -> pd.DataFrame:
    table = result.table.copy()
    threshold = int(result.privacy.get("min_cell_size", 0) or 0)
    if threshold <= 0:
        return table
    suppressed = table["count"].gt(0) & table["count"].lt(threshold)
    table.loc[suppressed, ["count", "percent"]] = pd.NA
    table.loc[suppressed, ["weighted_count", "weighted_percent"]] = pd.NA
    return table


def _quality_frame(findings: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for finding in findings:
        row = dict(finding)
        if isinstance(row.get("respondent_ids"), list):
            row["respondent_ids"] = ", ".join(row["respondent_ids"])
        if isinstance(row.get("invalid_values"), dict):
            row["invalid_values"] = json.dumps(
                row["invalid_values"], ensure_ascii=False
            )
        rows.append(row)
    if not rows:
        rows.append(
            {
                "name": "未发现质量问题",
                "severity": "info",
                "count": 0,
                "description": "",
            }
        )
    return pd.DataFrame(rows)


def _group_membership_frame(audit: dict[str, Any]) -> pd.DataFrame:
    rows = list(audit["overlaps"])
    rows.append(
        {
            "left": "未归属任何自定义分组",
            "right": "",
            "overlap": audit["unassigned"],
        }
    )
    return pd.DataFrame(rows)


def _weight_frame(audit: dict[str, Any]) -> pd.DataFrame:
    scalar_audit = {key: value for key, value in audit.items() if key != "targets"}
    return pd.DataFrame(
        [
            {
                key: (
                    "; ".join(value) if isinstance(value, list) else value
                )
                for key, value in scalar_audit.items()
            }
        ]
    )


def _format_workbook(workbook) -> None:
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for worksheet in workbook.worksheets:
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        for column_cells in worksheet.columns:
            values = [str(cell.value or "") for cell in column_cells[:200]]
            width = min(max(max(map(len, values), default=8) + 2, 10), 50)
            worksheet.column_dimensions[column_cells[0].column_letter].width = width
        if worksheet.title in {"tables_long", "tables_wide", "tables_weighted"}:
            worksheet.column_dimensions["B"].width = 55
        if worksheet.title == "open_responses":
            worksheet.column_dimensions["B"].width = 70
            worksheet.column_dimensions["E"].width = 50
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                if cell.column in {2, 3, 4, 5}:
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
        for row in worksheet.iter_rows(min_row=2):
            for cell in row:
                header = worksheet.cell(row=1, column=cell.column).value
                if header and str(header).endswith(("percent", "_percent")):
                    cell.number_format = "0.00%"


def _resolve_path(value: str, config_dir: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else config_dir / path


def _excel_safe_frame(frame: pd.DataFrame) -> pd.DataFrame:
    safe = frame.copy()
    for column in safe.columns:
        safe[column] = safe[column].map(_excel_safe_value)
    return safe


def _excel_safe_value(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
