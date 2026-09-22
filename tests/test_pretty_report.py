import json

import pandas as pd

from qnr_data_processing.pretty_report import build_report


def _write_tables(tmp_path):
    wide = pd.DataFrame(
        [
            {
                "question_id": "Q1",
                "question": "性别",
                "option": "男",
                "总体_count": 10,
                "总体_base": 20,
                "总体_percent": 0.5,
                "分组A_count": 6,
                "分组A_base": 10,
                "分组A_percent": 0.6,
            },
            {
                "question_id": "Q1",
                "question": "性别",
                "option": "女",
                "总体_count": 10,
                "总体_base": 20,
                "总体_percent": 0.5,
                "分组A_count": 4,
                "分组A_base": 10,
                "分组A_percent": 0.4,
            },
            {
                "question_id": "Q2",
                "question": "满意度",
                "option": "T2B",
                "总体_count": 12,
                "总体_base": 20,
                "总体_percent": 0.6,
                "分组A_count": 7,
                "分组A_base": 10,
                "分组A_percent": 0.7,
            },
        ]
    )
    tables = tmp_path / "tables.xlsx"
    with pd.ExcelWriter(tables, engine="openpyxl") as writer:
        wide.to_excel(writer, sheet_name="tables_wide", index=False)
    return tables


def test_build_report_writes_one_block_per_question(tmp_path):
    tables = _write_tables(tmp_path)
    out = build_report(tables, tmp_path / "report.xlsx")

    assert out.exists()
    result = pd.read_excel(out, header=None)
    # 标题 + 两行表头 + Q1(题干+Base+2选项) + Q2(题干+Base+1选项)
    assert result.shape[0] == 1 + 2 + 4 + 3
    assert "频数" in result.iloc[2].tolist()
    assert "频率%" in result.iloc[2].tolist()
    # Base 行放在题干之后：Q1 的 Base=20
    assert int(result.iloc[4, 2]) == 20


def test_report_tags_multi_and_reads_groups_dynamically(tmp_path):
    tables = _write_tables(tmp_path)
    config = tmp_path / "task.json"
    config.write_text(
        json.dumps({"questions": [{"id": "Q2", "type": "multi"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = build_report(tables, tmp_path / "report.xlsx", config_path=config)

    result = pd.read_excel(out, header=None)
    banners = result.iloc[:, 0].dropna().astype(str)
    assert any("Q1" in b and "（多选）" not in b for b in banners)
    assert any("Q2" in b and "（多选）" in b for b in banners)
