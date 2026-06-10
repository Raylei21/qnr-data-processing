import pandas as pd

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.processor import process


def test_clean_group_and_tabulate():
    numeric = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "age": [17, 20, 30, 40],
            "Q1": [1, 1, 2, 2],
            "Q2_A": [1, 1, 0, 1],
            "Q2_B": [0, 1, 1, 1],
        }
    ).set_index("id", drop=False)
    text = pd.DataFrame(
        {
            "id": [1, 2, 3, 4],
            "Q1": ["男", "男", "女", "女"],
            "Q2_A": ["是", "是", None, "是"],
            "Q2_B": [None, "是", "是", "是"],
        }
    ).set_index("id", drop=False)
    dataset = SurveyDataset(numeric, text, text.index)
    spec = {
        "questions": [
            {
                "id": "Q1",
                "type": "single",
                "text": "性别",
                "columns": [{"numeric": "Q1", "text": "Q1"}],
                "options": ["男", "女"],
            },
            {
                "id": "Q2",
                "type": "multi",
                "text": "品牌",
                "base": "any_selected",
                "columns": [
                    {
                        "numeric": "Q2_A",
                        "text": "Q2_A",
                        "label": "A",
                        "selected_values": ["是"],
                    },
                    {
                        "numeric": "Q2_B",
                        "text": "Q2_B",
                        "label": "B",
                        "selected_values": ["是"],
                    },
                ],
            },
        ],
        "cleaning": [
            {
                "name": "未成年",
                "rule": {"column": "age", "op": "lt", "value": 18},
            }
        ],
        "groups": [
            {
                "name": "A用户",
                "rule": {"question": "Q2", "option": "A", "op": "selected"},
            }
        ],
    }
    result = process(spec, dataset)

    assert result.audit["output_rows"] == 3
    assert result.audit["groups"] == {"总体": 3, "A用户": 2}
    women_total = result.table[
        (result.table["question_id"] == "Q1")
        & (result.table["option"] == "女")
        & (result.table["group"] == "总体")
    ].iloc[0]
    assert women_total["count"] == 2
    assert women_total["base"] == 3
