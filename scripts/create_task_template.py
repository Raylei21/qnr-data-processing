#!/usr/bin/env python3
"""Create a conservative task skeleton from an inspector inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    with Path(args.inventory).open("r", encoding="utf-8") as handle:
        inventory = json.load(handle)

    sheets = inventory.get("sheets", [])
    sheet_name = sheets[0]["name"] if sheets else 0
    source_path = inventory.get("path", "responses.xlsx")
    template = {
        "inputs": {
            "text": {
                "path": source_path,
                "sheet": sheet_name,
                "id_column": "TODO",
            }
        },
        "questions": [
            {
                "id": "TODO",
                "type": "single",
                "text": "TODO",
                "columns": [{"text": "TODO"}],
            }
        ],
        "cleaning": [],
        "groups": [],
        "output": {
            "table_path": "output/questionnaire_tables.xlsx",
            "audit_path": "output/audit.json",
            "cleaned_path": "output/cleaned.xlsx",
        },
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(template, handle, ensure_ascii=False, indent=2)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
