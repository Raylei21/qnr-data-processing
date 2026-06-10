import pandas as pd
from openpyxl import load_workbook

from qnr_data_processing.dataset import SurveyDataset
from qnr_data_processing.processor import process
from qnr_data_processing.reporting import write_result


def open_result(include_open_responses):
    frame = pd.DataFrame(
        {"id": [1], "Q1": ["=HYPERLINK(\"https://example.com\")"]}
    ).set_index("id", drop=False)
    dataset = SurveyDataset(frame.copy(), frame.copy(), frame.index)
    return process(
        {
            "questions": [
                {
                    "id": "Q1",
                    "type": "open",
                    "text": "意见",
                    "columns": [{"text": "Q1"}],
                }
            ],
            "cleaning": [],
            "groups": [],
            "privacy": {
                "include_open_responses": include_open_responses,
                "include_respondent_ids": False,
            },
        },
        dataset,
    )


def test_open_responses_are_not_exported_without_explicit_permission(tmp_path):
    files = write_result(
        open_result(False),
        {"table_path": "tables.xlsx", "audit_path": "audit.json"},
        tmp_path,
    )

    responses = pd.read_excel(files["table"], sheet_name="open_responses")
    assert responses.empty


def test_excel_like_open_response_is_exported_as_text(tmp_path):
    files = write_result(
        open_result(True),
        {"table_path": "tables.xlsx", "audit_path": "audit.json"},
        tmp_path,
    )

    workbook = load_workbook(files["table"], data_only=False)
    cell = workbook["open_responses"]["E2"]
    assert cell.data_type == "s"
    assert cell.value.startswith("'=")
