import pandas as pd

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.processor import process
from qnr_data_processing.reporting import _publication_table
from qnr_data_processing.rules import RuleEvaluator


def dataset_from(data):
    frame = pd.DataFrame(data).set_index("id", drop=False)
    return SurveyDataset(frame.copy(), frame.copy(), frame.index)


def test_negative_operator_excludes_missing_by_default():
    dataset = dataset_from({"id": [1, 2, 3], "Q1": [1, 2, None]})
    evaluator = RuleEvaluator(dataset, [])
    default = evaluator.evaluate({"column": "Q1", "op": "neq", "value": 1})
    include = evaluator.evaluate(
        {
            "column": "Q1",
            "op": "neq",
            "value": 1,
            "missing_policy": "include",
        }
    )
    assert default.tolist() == [False, True, False]
    assert include.tolist() == [False, True, True]


def test_single_question_supports_eligibility_base():
    dataset = dataset_from(
        {"id": [1, 2, 3, 4], "eligible": [1, 1, 0, 0], "Q1": ["A", None, None, "B"]}
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
                    "base": {"column": "eligible", "op": "eq", "value": 1},
                }
            ],
            "cleaning": [],
            "groups": [],
        },
        dataset,
    )
    row = result.table[
        (result.table["option"] == "A") & (result.table["group"] == "总体")
    ].iloc[0]
    assert row["count"] == 1
    assert row["base"] == 2


def test_quality_checks_find_invalid_and_exclusive_values():
    dataset = dataset_from(
        {
            "id": [1, 2, 3],
            "Q1": ["A", "X", "B"],
            "Q2_A": [1, 0, 1],
            "Q2_NONE": [1, 1, 0],
        }
    )
    spec = {
        "questions": [
            {
                "id": "Q1",
                "type": "single",
                "text": "单选",
                "columns": [{"text": "Q1"}],
                "options": ["A", "B"],
            },
            {
                "id": "Q2",
                "type": "multi",
                "text": "多选",
                "base": "any_selected",
                "columns": [
                    {"numeric": "Q2_A", "label": "A", "selected_values": [1]},
                    {
                        "numeric": "Q2_NONE",
                        "label": "以上都没有",
                        "selected_values": [1],
                        "exclusive": True,
                    },
                ],
            },
        ],
        "cleaning": [],
        "groups": [],
    }
    result = process(spec, dataset)
    findings = {item["name"]: item["count"] for item in result.audit["quality_checks"]}
    assert findings["发现未配置选项值"] == 1
    assert findings["互斥选项与其他选项同时选择"] == 1


def test_weight_and_group_overlap_diagnostics():
    dataset = dataset_from(
        {"id": [1, 2, 3], "Q1": ["A", "B", "A"], "weight": [0.5, 1.0, 2.0]}
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
            "groups": [
                {"name": "A组", "rule": {"column": "Q1", "source": "text", "op": "eq", "value": "A"}},
                {"name": "全部", "rule": {"column": "Q1", "source": "text", "op": "not_missing"}},
            ],
            "weight": {"column": "weight"},
        },
        dataset,
    )
    assert result.audit["weights"]["effective_n"] < 3
    assert result.audit["group_membership"]["overlaps"] == [
        {"left": "A组", "right": "全部", "overlap": 2}
    ]
    assert result.audit["group_membership"]["unassigned"] == 0


def test_respondent_ids_are_hidden_by_default():
    dataset = dataset_from({"id": [1, 2], "Q1": ["A", "B"]})
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
                    "name": "删A",
                    "rule": {
                        "column": "Q1",
                        "source": "text",
                        "op": "eq",
                        "value": "A",
                    },
                }
            ],
            "groups": [],
        },
        dataset,
    )
    assert result.audit["cleaning"][0]["removed_ids"] == []


def test_discovery_warnings_are_preserved_in_final_audit():
    dataset = dataset_from({"id": [1], "Q1": ["A"]})
    result = process(
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
            "discovery_warnings": ["问卷与数据标签不一致"],
        },
        dataset,
    )

    assert result.audit["warnings"] == ["问卷与数据标签不一致"]


def test_small_unweighted_cells_also_suppress_weighted_results():
    dataset = dataset_from(
        {"id": [1, 2, 3], "Q1": ["A", "B", "B"], "weight": [10, 1, 1]}
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
            "weight": {"column": "weight"},
            "privacy": {"min_cell_size": 2},
        },
        dataset,
    )
    row = _publication_table(result).query("option == 'A'").iloc[0]

    assert pd.isna(row["count"])
    assert pd.isna(row["weighted_count"])
