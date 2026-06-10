"""Non-interactive command line interface for agents and automation."""

from __future__ import annotations

import argparse
import json
import sys

from .dataset import load_dataset
from .discovery import discover_task
from .errors import QnrError
from .inspector import inspect_file
from .processor import process
from .reporting import write_result
from .spec import load_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qnr-process")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="读取工作簿结构并生成 JSON 清单"
    )
    inspect_parser.add_argument("input")
    inspect_parser.add_argument("--output", required=True)

    discover_parser = subparsers.add_parser(
        "discover", help="从标准问卷导出列名生成任务配置草稿"
    )
    discover_parser.add_argument("input")
    discover_parser.add_argument("--output", required=True)
    discover_parser.add_argument("--numeric-sheet", default="数字版")
    discover_parser.add_argument("--text-sheet", default="文字版")
    discover_parser.add_argument("--id-column", default="id")
    discover_parser.add_argument("--questionnaire")

    run_parser = subparsers.add_parser("run", help="按 JSON 配置清洗并出表")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument(
        "--validate-only", action="store_true", help="只校验配置和输入，不写输出"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            inventory = inspect_file(args.input, args.output)
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "output": args.output,
                        "sheets": len(inventory["sheets"]),
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        if args.command == "discover":
            task = discover_task(
                args.input,
                args.output,
                numeric_sheet=args.numeric_sheet,
                text_sheet=args.text_sheet,
                id_column=args.id_column,
                questionnaire_path=args.questionnaire,
            )
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "output": args.output,
                        "questions": len(task["questions"]),
                        "warnings": task["discovery_warnings"],
                    },
                    ensure_ascii=False,
                )
            )
            return 0

        spec = load_spec(args.config)
        dataset = load_dataset(spec["inputs"], spec["_config_dir"])
        result = process(spec, dataset)
        if args.validate_only:
            print(
                json.dumps(
                    {"status": "ok", "audit": result.audit}, ensure_ascii=False
                )
            )
            return 0

        written = write_result(
            result, spec.get("output", {}), config_dir=spec["_config_dir"]
        )
        print(
            json.dumps(
                {"status": "ok", "files": written, "audit": result.audit},
                ensure_ascii=False,
            )
        )
        return 0
    except QnrError as exc:
        print(
            json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
