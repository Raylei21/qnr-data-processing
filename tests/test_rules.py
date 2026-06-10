import pandas as pd

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.rules import RuleEvaluator


def make_dataset():
    numeric = pd.DataFrame(
        {
            "id": [1, 2, 3],
            "age": [17, 25, 40],
            "brand_a": [1, 0, 1],
            "brand_b": [0, 1, 1],
        }
    ).set_index("id", drop=False)
    text = pd.DataFrame(
        {"id": [1, 2, 3], "comment": ["太贵", "很好", None]}
    ).set_index("id", drop=False)
    questions = [
        {
            "id": "brands",
            "type": "multi",
            "columns": [
                {"numeric": "brand_a", "label": "A"},
                {"numeric": "brand_b", "label": "B"},
            ],
        }
    ]
    return SurveyDataset(numeric, text, text.index), questions


def test_nested_logic_preserves_parentheses():
    dataset, questions = make_dataset()
    evaluator = RuleEvaluator(dataset, questions)
    mask = evaluator.evaluate(
        {
            "any": [
                {
                    "all": [
                        {"column": "age", "op": "gte", "value": 18},
                        {"question": "brands", "option": "B", "op": "selected"},
                    ]
                },
                {
                    "column": "comment",
                    "source": "text",
                    "op": "contains",
                    "value": "贵",
                },
            ]
        }
    )
    assert mask.tolist() == [True, True, True]


def test_multi_question_selector():
    dataset, questions = make_dataset()
    evaluator = RuleEvaluator(dataset, questions)
    mask = evaluator.evaluate(
        {"question": "brands", "option": "A", "op": "selected"}
    )
    assert mask.tolist() == [True, False, True]
