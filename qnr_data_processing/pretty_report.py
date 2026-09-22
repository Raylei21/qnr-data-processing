"""Generate a presentation-ready report workbook from the engine's tables output.

Layout (one block per question):

    1. a full-width question banner (题干), tagged （多选）/（开放题） where relevant
    2. a "Base" row showing each group's denominator for that question
    3. one row per option, with each group reported as 频数 (count) and 频率% (column %)

T2B/B2B summary rows (nets) are highlighted. Groups are detected dynamically from
the ``tables_wide`` sheet, so this works for any task configuration without hardcoding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# --- style constants ---
F_TITLE = Font(name="微软雅黑", bold=True, size=14)
F_HEAD = Font(name="微软雅黑", bold=True, size=10, color="FFFFFF")
F_GROUP = Font(name="微软雅黑", bold=True, size=10)
F_Q = Font(name="微软雅黑", bold=True, size=10, color="1F4E79")
F_OPT = Font(name="微软雅黑", size=10)
F_OPT_BOLD = Font(name="微软雅黑", bold=True, size=10)
F_BASE = Font(name="微软雅黑", size=9, italic=True, color="595959")
FILL_HEAD = PatternFill("solid", fgColor="4472C4")
FILL_GROUP = PatternFill("solid", fgColor="BDD7EE")
FILL_Q = PatternFill("solid", fgColor="D9E2F3")
FILL_BASE = PatternFill("solid", fgColor="F2F2F2")
FILL_NET = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)

SUMMARY_OPTIONS = {"T2B", "B2B"}  # net rows to highlight
TYPE_TAGS = {"multi": "（多选）", "open": "（开放题）"}


def _groups_from_columns(columns: list[Any]) -> list[str]:
    return [str(c)[: -len("_count")] for c in columns if str(c).endswith("_count")]


def _text(value: Any) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _cell(
    ws,
    row: int,
    column: int,
    value: Any,
    font: Font | None = None,
    fill: PatternFill | None = None,
    align: Alignment | None = None,
):
    cell = ws.cell(row=row, column=column, value=value)
    if font is not None:
        cell.font = font
    if fill is not None:
        cell.fill = fill
    if align is not None:
        cell.alignment = align
    return cell


def build_report(
    tables_path: str | Path,
    output_path: str | Path,
    config_path: str | Path | None = None,
    title: str = "数据分析表",
) -> Path:
    """Build the beautified report from an engine output workbook.

    Args:
        tables_path: engine output Excel containing a ``tables_wide`` sheet.
        output_path: destination ``.xlsx`` path.
        config_path: optional ``task.json``; used to tag multi/open questions.
        title: report title shown in the first row.
    """
    wide = pd.read_excel(Path(tables_path), sheet_name="tables_wide")
    groups = _groups_from_columns(list(wide.columns))
    if not groups:
        raise ValueError("tables_wide 里没有找到 *_count 分组列")

    qtype: dict[str, str] = {}
    if config_path:
        spec = json.loads(Path(config_path).read_text(encoding="utf-8"))
        qtype = {str(q["id"]): q["type"] for q in spec.get("questions", [])}

    n_cols = 2 + len(groups) * 2
    wb = Workbook()
    ws = wb.active
    ws.title = (title or "数据分析表")[:31]

    # title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n_cols)
    _cell(ws, 1, 1, title, F_TITLE, None, CENTER)
    ws.row_dimensions[1].height = 26

    # two-row header
    ws.merge_cells(start_row=2, start_column=1, end_row=3, end_column=1)
    _cell(ws, 2, 1, "题目", F_HEAD, FILL_HEAD, CENTER)
    ws.merge_cells(start_row=2, start_column=2, end_row=3, end_column=2)
    _cell(ws, 2, 2, "选项", F_HEAD, FILL_HEAD, CENTER)
    col = 3
    for group in groups:
        ws.merge_cells(start_row=2, start_column=col, end_row=2, end_column=col + 1)
        _cell(ws, 2, col, group, F_HEAD, FILL_HEAD, CENTER)
        _cell(ws, 3, col, "频数", F_GROUP, FILL_GROUP, CENTER)
        _cell(ws, 3, col + 1, "频率%", F_GROUP, FILL_GROUP, CENTER)
        col += 2
    ws.row_dimensions[2].height = 20
    ws.row_dimensions[3].height = 18

    # data blocks
    r = 4
    current_qid: str | None = None
    for _, row in wide.iterrows():
        qid = str(row["question_id"])
        if qid != current_qid:
            current_qid = qid
            tag = TYPE_TAGS.get(qtype.get(qid, ""), "")
            banner = f"{qid}. {_text(row['question'])}{tag}"
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=n_cols)
            _cell(ws, r, 1, banner, F_Q, FILL_Q, LEFT)
            for cidx in range(1, n_cols + 1):
                ws.cell(row=r, column=cidx).border = BORDER
                ws.cell(row=r, column=cidx).fill = FILL_Q
            ws.row_dimensions[r].height = 22
            r += 1

            # Base row
            _cell(ws, r, 2, "Base", F_BASE, FILL_BASE, LEFT)
            ws.cell(row=r, column=2).border = BORDER
            col = 3
            for group in groups:
                base_val = row.get(f"{group}_base")
                ws.merge_cells(start_row=r, start_column=col, end_row=r, end_column=col + 1)
                _cell(
                    ws, r, col,
                    None if pd.isna(base_val) else int(base_val),
                    F_BASE, FILL_BASE, CENTER,
                )
                ws.cell(row=r, column=col).border = BORDER
                ws.cell(row=r, column=col + 1).border = BORDER
                col += 2
            r += 1

        opt = _text(row["option"])
        is_net = opt.upper() in SUMMARY_OPTIONS
        _cell(ws, r, 2, opt, F_OPT_BOLD if is_net else F_OPT, None, LEFT)
        col = 3
        for group in groups:
            cnt = row.get(f"{group}_count")
            pct = row.get(f"{group}_percent")
            _cell(
                ws, r, col,
                None if pd.isna(cnt) else int(cnt),
                F_OPT_BOLD if is_net else None, None, CENTER,
            )
            pcell = _cell(
                ws, r, col + 1,
                None if pd.isna(pct) else float(pct),
                F_OPT_BOLD if is_net else None, None, CENTER,
            )
            pcell.number_format = "0.0%"
            col += 2

        for cidx in range(1, n_cols + 1):
            ws.cell(row=r, column=cidx).border = BORDER
        if is_net:
            for cidx in range(1, n_cols + 1):
                ws.cell(row=r, column=cidx).fill = FILL_NET
                if cidx >= 2:
                    ws.cell(row=r, column=cidx).font = F_OPT_BOLD
        r += 1

    # column widths and freeze panes
    ws.column_dimensions["A"].width = 3
    ws.column_dimensions["B"].width = 46
    for i in range(3, n_cols + 1):
        ws.column_dimensions[get_column_letter(i)].width = 11
    ws.freeze_panes = "C4"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return output_path
