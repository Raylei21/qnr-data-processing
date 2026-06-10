import pandas as pd
import pytest

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.errors import DataValidationError
from qnr_data_processing.processor import process
from qnr_data_processing.reporting import write_result


def dataset_from(data):
    frame = pd.DataFrame(data).set_index("id", drop=False)
    return SurveyDataset(frame.copy(), frame.copy(), frame.index)


def weighting_spec(targets, **weight_options):
    return {
        "questions": [
            {
                "id": "Q1",
                "type": "single",
                "text": "结果题",
                "columns": [{"text": "Q1"}],
                "options": ["A", "B"],
            }
        ],
        "cleaning": [],
        "groups": [],
        "weight": {"targets": targets, **weight_options},
    }


def test_raking_supports_single_and_combined_targets():
    dataset = dataset_from(
        {
            "id": range(1, 9),
            "gender": ["男", "男", "男", "女", "女", "女", "女", "男"],
            "city": ["一线", "一线", "二线", "一线", "一线", "二线", "二线", "二线"],
            "Q1": ["A", "B", "A", "B", "A", "B", "A", "B"],
        }
    )
    result = process(
        weighting_spec(
            [
                {
                    "name": "男性",
                    "percent": 60,
                    "rule": {
                        "column": "gender",
                        "source": "text",
                        "op": "eq",
                        "value": "男",
                    },
                },
                {
                    "name": "一线城市",
                    "percent": 50,
                    "rule": {
                        "column": "city",
                        "source": "text",
                        "op": "eq",
                        "value": "一线",
                    },
                },
                {
                    "name": "一线男性",
                    "percent": 30,
                    "rule": {
                        "all": [
                            {
                                "column": "city",
                                "source": "text",
                                "op": "eq",
                                "value": "一线",
                            },
                            {
                                "column": "gender",
                                "source": "text",
                                "op": "eq",
                                "value": "男",
                            },
                        ]
                    },
                },
            ],
            tolerance=0.000001,
        ),
        dataset,
    )

    audit = result.audit["weights"]
    assert audit["mode"] == "raking"
    assert audit["converged"] is True
    assert result.weights.mean() == pytest.approx(1.0)
    for target in audit["targets"]:
        assert target["achieved_share"] == pytest.approx(
            target["target_share"], abs=0.000001
        )


def test_raking_fails_when_positive_target_has_no_sample():
    dataset = dataset_from(
        {"id": [1, 2], "gender": ["男", "女"], "Q1": ["A", "B"]}
    )
    with pytest.raises(DataValidationError, match="当前样本为 0"):
        process(
            weighting_spec(
                [
                    {
                        "name": "一线男性",
                        "percent": 30,
                        "rule": {
                            "column": "gender",
                            "source": "text",
                            "op": "eq",
                            "value": "不存在",
                        },
                    }
                ]
            ),
            dataset,
        )


def test_raking_can_start_from_existing_base_weight():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "gender": ["男", "男", "女", "女"],
            "base_w": [2.0, 2.0, 1.0, 1.0],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    result = process(
        weighting_spec(
            [
                {
                    "name": "女性",
                    "percent": 50,
                    "rule": {
                        "column": "gender",
                        "source": "text",
                        "op": "eq",
                        "value": "女",
                    },
                }
            ],
            base_weight={"source": "numeric", "column": "base_w"},
        ),
        dataset,
    )

    assert result.audit["weights"]["targets"][0]["initial_share"] == pytest.approx(
        1 / 3
    )
    assert result.audit["weights"]["targets"][0]["achieved_share"] == pytest.approx(
        0.5
    )


def test_generated_weights_are_exported_with_target_audit(tmp_path):
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "gender": ["男", "男", "男", "女"],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    result = process(
        weighting_spec(
            [
                {
                    "name": "女性",
                    "percent": 50,
                    "rule": {
                        "column": "gender",
                        "source": "text",
                        "op": "eq",
                        "value": "女",
                    },
                }
            ]
        ),
        dataset,
    )
    files = write_result(
        result,
        {
            "table_path": "tables.xlsx",
            "audit_path": "audit.json",
            "cleaned_path": "cleaned.xlsx",
        },
        tmp_path,
    )

    assert "weight_targets" in pd.ExcelFile(files["table"]).sheet_names
    cleaned = pd.read_excel(files["cleaned"], sheet_name="numeric")
    assert "final_weight" in cleaned.columns
    assert cleaned["final_weight"].mean() == pytest.approx(1.0)


def test_target_base_excludes_missing_from_the_complement():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "gender": ["男", "女", None, None],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    result = process(
        weighting_spec(
            [
                {
                    "name": "男性（已回答性别）",
                    "percent": 60,
                    "base": {
                        "column": "gender",
                        "source": "text",
                        "op": "not_missing",
                    },
                    "rule": {
                        "column": "gender",
                        "source": "text",
                        "op": "eq",
                        "value": "男",
                    },
                }
            ]
        ),
        dataset,
    )

    target = result.audit["weights"]["targets"][0]
    assert target["base_n"] == 2
    assert target["achieved_share"] == pytest.approx(0.6)
    assert result.weights.loc[3] == pytest.approx(result.weights.loc[4])


def test_conflicting_identical_targets_fail_before_iteration():
    dataset = dataset_from(
        {"id": [1, 2], "gender": ["男", "女"], "Q1": ["A", "B"]}
    )
    rule = {
        "column": "gender",
        "source": "text",
        "op": "eq",
        "value": "男",
    }
    with pytest.raises(DataValidationError, match="同一人群"):
        process(
            weighting_spec(
                [
                    {"name": "男性目标1", "percent": 60, "rule": rule},
                    {"name": "男性目标2", "percent": 50, "rule": rule},
                ]
            ),
            dataset,
        )


def test_subset_target_cannot_exceed_superset_target():
    dataset = dataset_from(
        {
            "id": [1, 2, 3, 4],
            "gender": ["男", "男", "女", "女"],
            "city": ["一线", "二线", "一线", "二线"],
            "Q1": ["A", "B", "A", "B"],
        }
    )
    with pytest.raises(DataValidationError, match="子集"):
        process(
            weighting_spec(
                [
                    {
                        "name": "一线男性",
                        "percent": 70,
                        "rule": {
                            "all": [
                                {
                                    "column": "gender",
                                    "source": "text",
                                    "op": "eq",
                                    "value": "男",
                                },
                                {
                                    "column": "city",
                                    "source": "text",
                                    "op": "eq",
                                    "value": "一线",
                                },
                            ]
                        },
                    },
                    {
                        "name": "男性",
                        "percent": 60,
                        "rule": {
                            "column": "gender",
                            "source": "text",
                            "op": "eq",
                            "value": "男",
                        },
                    },
                ]
            ),
            dataset,
        )


def test_trimming_bounds_are_preserved_after_normalization():
    dataset = dataset_from(
        {
            "id": range(1, 11),
            "rare": ["是"] + ["否"] * 9,
            "Q1": ["A", "B"] * 5,
        }
    )
    result = process(
        weighting_spec(
            [
                {
                    "name": "稀有人群",
                    "percent": 25,
                    "rule": {
                        "column": "rare",
                        "source": "text",
                        "op": "eq",
                        "value": "是",
                    },
                }
            ],
            trim={"min": 0.5, "max": 3.0},
            tolerance=0.000001,
        ),
        dataset,
    )

    assert result.weights.mean() == pytest.approx(1.0)
    assert result.weights.min() >= 0.5
    assert result.weights.max() <= 3.0
