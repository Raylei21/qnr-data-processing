"""Configuration-driven questionnaire data processing."""

from .dataset import SurveyDataset, load_dataset
from .processor import ProcessingResult, process
from .rules import RuleEvaluator
from .spec import load_spec, validate_spec

__version__ = "2.2.0"
__all__ = [
    "ProcessingResult",
    "RuleEvaluator",
    "SurveyDataset",
    "load_dataset",
    "load_spec",
    "process",
    "validate_spec",
]


def main():
    """Command line entry point."""
    from .cli import main as cli_main

    return cli_main()
