import pandas as pd
import pytest

from qnr_data_processing.dataset import load_dataset
from qnr_data_processing.errors import DataValidationError


def test_aligns_numeric_and_text_by_id(tmp_path):
    path = tmp_path / "responses.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"id": [2, 1], "Q1": [20, 10]}).to_excel(
            writer, sheet_name="numeric", index=False
        )
        pd.DataFrame({"id": [1, 2], "Q1": ["A", "B"]}).to_excel(
            writer, sheet_name="text", index=False
        )

    dataset = load_dataset(
        {
            "numeric": {"path": str(path), "sheet": "numeric", "id_column": "id"},
            "text": {"path": str(path), "sheet": "text", "id_column": "id"},
        }
    )
    assert dataset.numeric["Q1"].tolist() == [10, 20]


def test_rejects_mismatched_ids(tmp_path):
    path = tmp_path / "responses.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"id": [1, 3]}).to_excel(
            writer, sheet_name="numeric", index=False
        )
        pd.DataFrame({"id": [1, 2]}).to_excel(
            writer, sheet_name="text", index=False
        )

    with pytest.raises(DataValidationError):
        load_dataset(
            {
                "numeric": {
                    "path": str(path),
                    "sheet": "numeric",
                    "id_column": "id",
                },
                "text": {"path": str(path), "sheet": "text", "id_column": "id"},
            }
        )
