import pandas as pd

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.processor import process


def test_matrix_net_is_calculated_per_subitem():
    text = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "Q3_A": ["非常好", "比较好", "非常差"],
            "Q3_B": ["非常差", "非常差", "非常好"],
        }
    ).set_index("id", drop=False)
    numeric = text.copy()
    dataset = SurveyDataset(numeric, text, text.index)
    spec = {
        "questions": [
            {
                "id": "Q3",
                "type": "matrix_single",
                "text": "评价",
                "columns": [
                    {"text": "Q3_A", "label": "A"},
                    {"text": "Q3_B", "label": "B"},
                ],
                "options": ["非常好", "比较好", "非常差"],
                "nets": [{"name": "T2B", "values": ["非常好", "比较好"]}],
            }
        ],
        "cleaning": [],
        "groups": [],
    }
    result = process(spec, dataset)
    t2b = result.table[
        (result.table["option"] == "T2B") & (result.table["group"] == "总体")
    ]
    assert t2b.set_index("subitem")["count"].to_dict() == {"A": 2, "B": 1}
