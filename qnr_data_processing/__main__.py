#!/usr/bin/env python3
"""CLI 入口: python -m qnr_data_processing"""

from .orchestrator import run_pipeline

if __name__ == '__main__':
    run_pipeline()
