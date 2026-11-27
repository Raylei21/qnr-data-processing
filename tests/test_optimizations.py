import pandas as pd
import pytest

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.errors import DataValidationError
from qnr_data_processing.pretty_report import build_report
from qnr_data_processing.processor import process
from qnr_data_processing.reporting import _publication_table, write_result


def dataset_from(data):
    frame = pd.DataFrame(data).set_index("id", drop=False)
    return SurveyDataset(frame.copy(), frame.copy(), frame.index)


def test_cleaning_dedup_keeps_max_on_column():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "customer_id": ["a", "a", "b", "c"],
            "duration": [10, 40, 20, 30],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "single",
                    "text": "测试",
                    "columns": [{"text": "Q1"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [
                {
                    "name": "去重",
                    "type": "dedup",
                    "key": "customer_id",
                    "keep": "max",
                    "on": "duration",
                    "source": "text",
                }
            ],
            "groups": [],
        },
        dataset,
    )
    assert result.audit["output_rows"] == 3
    audit = result.audit["cleaning"][0]
    assert audit["removed"] == 1
    assert audit["type"] == "dedup"
    kept = set(result.dataset.text["customer_id"])
    assert kept == {"a", "b", "c"}
    kept_duration = result.dataset.text.set_index("customer_id")["duration"].to_dict()
    assert kept_duration["a"] == 40


def test_cleaning_normalize_rstrip_period():
    dataset = dataset_from(
        {"id": [1, 2, 3], "Q9": ["A.", "B.", None]}
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q9",
                    "type": "single",
                    "text": "积分",
                    "columns": [{"text": "Q9"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [
                {
                    "name": "去句号",
                    "type": "normalize",
                    "column": "Q9",
                    "op": "rstrip",
                    "value": ".",
                }
            ],
            "groups": [],
        },
        dataset,
    )
    audit = result.audit["cleaning"][0]
    assert audit["removed"] == 0
    assert audit["changed"] == 2
    values = result.dataset.text["Q9"].tolist()
    assert values[0] == "A" and values[1] == "B"
    assert pd.isna(values[2])
    row = result.table[
        (result.table["option"] == "A") & (result.table["group"] == "总体")
    ].iloc[0]
    assert row["count"] == 1


def test_multi_delimiter_auto_split_with_skip_and_others():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "Q2": [
                "价格实惠┋款式多样",
                "(跳过)",
                "others, please specify〖太贵了〗",
                "款式多样",
            ],
        }
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q2",
                    "type": "multi",
                    "text": "吸引点",
                    "base": "any_selected",
                    "columns": [
                        {
                            "text": "Q2",
                            "delimiter": "┋",
                            "options": [
                                {"value": "价格实惠", "label": "价格实惠"},
                                {"value": "款式多样", "label": "款式多样"},
                                {
                                    "value": "others, please specify",
                                    "label": "其他",
                                },
                            ],
                        }
                    ],
                }
            ],
            "cleaning": [],
            "groups": [],
        },
        dataset,
    )
    counts = {
        (row["option"], row["group"]): row["count"]
        for _, row in result.table.iterrows()
        if row["group"] == "总体"
    }
    assert counts[("价格实惠", "总体")] == 1
    assert counts[("款式多样", "总体")] == 2
    assert counts[("其他", "总体")] == 1
    # skip respondent excluded from any_selected base
    base = result.table[
        (result.table["option"] == "价格实惠") & (result.table["group"] == "总体")
    ].iloc[0]["base"]
    assert base == 3


def test_multi_delimiter_exports_others_verbatim(tmp_path):
    dataset = dataset_from(
        {"id": [1, 2], "Q2": ["others, please specify〖太贵了〗", "款式多样"]}
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q2",
                    "type": "multi",
                    "text": "吸引点",
                    "base": "any_selected",
                    "columns": [
                        {
                            "text": "Q2",
                            "delimiter": "┋",
                            "options": ["款式多样", "others, please specify"],
                        }
                    ],
                }
            ],
            "cleaning": [],
            "groups": [],
            "privacy": {"include_open_responses": True},
        },
        dataset,
    )
    files = write_result(
        result,
        {"table_path": "tables.xlsx", "audit_path": "audit.json"},
        tmp_path,
    )
    responses = pd.read_excel(files["table"], sheet_name="open_responses")
    assert responses.iloc[0]["response"] == "太贵了"
    assert responses.iloc[0]["subitem"] == "others, please specify"


def test_weighted_wide_table_uses_weighted_suffix(tmp_path):
    dataset = dataset_from(
        {"id": [1, 2, 3, 4], "Q1": ["A", "B", "A", "B"], "w": [2, 1, 2, 1]}
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "single",
                    "text": "测试",
                    "columns": [{"text": "Q1"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [],
            "groups": [],
            "weight": {"source": "numeric", "column": "w"},
        },
        dataset,
    )
    files = write_result(
        result,
        {"table_path": "tables.xlsx", "audit_path": "audit.json"},
        tmp_path,
    )
    weighted = pd.read_excel(files["table"], sheet_name="tables_weighted")
    assert "总体_weighted_count" in weighted.columns
    assert "总体_weighted_base" in weighted.columns
    assert "总体_weighted_percent" in weighted.columns
    wide = pd.read_excel(files["table"], sheet_name="tables_wide")
    assert "总体_count" in wide.columns
    assert "总体_weighted_count" not in wide.columns


def test_report_weighted_reads_weighted_sheet(tmp_path):
    dataset = dataset_from(
        {"id": [1, 2], "Q1": ["A", "B"], "w": [3, 1]}
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "single",
                    "text": "测试",
                    "columns": [{"text": "Q1"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [],
            "groups": [],
            "weight": {"source": "numeric", "column": "w"},
        },
        dataset,
    )
    tables = tmp_path / "tables.xlsx"
    write_result(result, {"table_path": "tables.xlsx", "audit_path": "audit.json"}, tmp_path)
    out = build_report(tables, tmp_path / "weighted_report.xlsx", weighted=True)
    frame = pd.read_excel(out, header=None)
    # 标题 + 表头(2) + Q1 题干 + Base + 2 选项 = 6 行
    assert frame.shape[0] == 1 + 2 + 1 + 1 + 2
    # weighted base = 4
    assert int(frame.iloc[4, 2]) == 4


def test_segments_generate_exclusive_groups_and_derived_column():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "income": [8, 3, 1, 4],
            "comfort": [1, 2, 3, 4],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "single",
                    "text": "测试",
                    "columns": [{"text": "Q1"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [],
            "groups": [],
            "segments": [
                {
                    "name": "购买力",
                    "column": "purchase_power",
                    "mutually_exclusive": True,
                    "residual": "L3",
                    "branches": [
                        {
                            "value": "L1",
                            "label": "高购买力",
                            "rule": {
                                "all": [
                                    {"column": "income", "op": "gte", "value": 6},
                                    {"column": "comfort", "op": "lte", "value": 2},
                                ]
                            },
                        },
                        {
                            "value": "L2",
                            "label": "中等",
                            "rule": {
                                "column": "income",
                                "op": "between",
                                "value": [2, 5],
                            },
                        },
                    ],
                }
            ],
        },
        dataset,
    )
    assert result.audit["segments"]["购买力"]["L1"] == 1
    assert result.audit["segments"]["购买力"]["L2"] == 2
    assert result.audit["segments"]["购买力"]["L3"] == 1
    assert set(result.audit["groups"]) == {"总体", "L1", "L2", "L3"}
    assert "purchase_power" in result.dataset.text.columns
    row = result.table[
        (result.table["option"] == "A") & (result.table["group"] == "L1")
    ].iloc[0]
    assert row["base"] == 1


def test_segments_reject_overlapping_branches():
    dataset = dataset_from(
        {"id": [1], "income": [10], "Q1": ["A"]}
    )
    with pytest.raises(DataValidationError, match="重叠"):
        process(
            {
                "questions": [
                    {
                        "id": "Q1",
                        "type": "single",
                        "text": "测试",
                        "columns": [{"text": "Q1"}],
                        "options": ["A"],
                    }
                ],
                "cleaning": [],
                "groups": [],
                "segments": [
                    {
                        "name": "分段",
                        "branches": [
                            {
                                "value": "A",
                                "rule": {"column": "income", "op": "gte", "value": 5},
                            },
                            {
                                "value": "B",
                                "rule": {"column": "income", "op": "gte", "value": 5},
                            },
                        ],
                    }
                ],
            },
            dataset,
        )


def test_piping_checks_flag_skip_logic_violations():
    dataset = dataset_from(
        {
            "id": [1, 2, 3],
            "Q4": ["是", "否", "是"],
            "Q5": ["答了", "答了", "(跳过)"],
        }
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q4",
                    "type": "single",
                    "text": "前置",
                    "columns": [{"text": "Q4"}],
                    "options": ["是", "否"],
                },
                {
                    "id": "Q5",
                    "type": "single",
                    "text": "目标",
                    "columns": [{"text": "Q5"}],
                    "options": ["答了"],
                },
            ],
            "cleaning": [],
            "groups": [],
            "piping": [
                {
                    "name": "Q5仅对Q4=是显示",
                    "gate": {
                        "column": "Q4",
                        "source": "text",
                        "op": "eq",
                        "value": "是",
                    },
                    "target": "Q5",
                    "skip_values": ["(跳过)"],
                }
            ],
        },
        dataset,
    )
    names = {f["name"]: f["count"] for f in result.audit["quality_checks"]}
    assert names["Q5仅对Q4=是显示: 应跳过却作答"] == 1  # id=2 answered but gate false
    assert names["Q5仅对Q4=是显示: 应作答却跳过"] == 1  # id=3 gate true but skipped


def test_min_cell_size_defaults_to_no_suppression():
    dataset = dataset_from({"id": [1, 2, 3], "Q1": ["A", "B", "B"]})
    result = process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "single",
                    "text": "测试",
                    "columns": [{"text": "Q1"}],
                    "options": ["A", "B"],
                }
            ],
            "cleaning": [],
            "groups": [],
        },
        dataset,
    )
    row = _publication_table(result).query("option == 'A'").iloc[0]
    assert row["count"] == 1
    assert not pd.isna(row["count"])


def test_rule_selector_on_delimiter_multi():
    dataset = dataset_from(
        {
            "id": [1, 2, 3],
            "Q2": ["价格实惠┋款式多样", "款式多样", "(跳过)"],
        }
    )
    result = process(
        {
            "questions": [
                {
                    "id": "Q2",
                    "type": "multi",
                    "text": "吸引点",
                    "base": "any_selected",
                    "columns": [
                        {
                            "text": "Q2",
                            "delimiter": "┋",
                            "options": ["价格实惠", "款式多样"],
                        }
                    ],
                }
            ],
            "cleaning": [],
            "groups": [
                {
                    "name": "选价格",
                    "rule": {
                        "question": "Q2",
                        "option": "价格实惠",
                        "source": "text",
                        "op": "selected",
                    },
                }
            ],
        },
        dataset,
    )
    assert result.audit["groups"]["选价格"] == 1

