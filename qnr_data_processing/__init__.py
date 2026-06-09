#!/usr/bin/env python3
"""
qnr_data_processing — 通用问卷数据处理包
============================================
全流程：
  1. 解析问卷（理解题目类型、选项）
  2. 加载原始数据（数字版 + 文字版）
  3. 数据清洗（用户自定义规则）
  4. 用户定义分组标签（如"核心篮球迷：Q18=1，Q19=1～2"）
  5. 评分题 T2B/B2B 配置
  6. 生成完整数表（频数+频率）+ 填空题原话 + 归纳分析
  7. 输出美观格式 Excel

特性：
  - 零硬编码：不依赖任何特定问卷的题号、选项文字、关键词
  - 模糊匹配：问卷选项与数据标签不一致时自动模糊匹配
  - 交互式配置：所有规则由用户在命令行定义
  - 配置持久化：可保存/加载问卷配置，避免重复输入
"""

from .questionnaire_parser import parse_questionnaire, show_questionnaire_summary
from .data_loader import load_data
from .column_mapper import build_column_map
from .option_matcher import fuzzy_match_options
from .interaction import (
    ask_cleaning_rules,
    ask_label_rules,
    ask_score_questions,
    ask_derived_cols,
    ask_open_ended_config,
)
from .cleaner import apply_cleaning_rules
from .label_engine import parse_label_rule, generate_labels, show_label_distribution
from .score_config import ScoreConfig
from .tabulator import make_output_rows
from .open_ended import analyze_open_ended
from .excel_writer import write_output_excel
from .config import Config

__version__ = '1.0.0'


def main():
    """主流程入口"""
    from .orchestrator import run_pipeline
    run_pipeline()
