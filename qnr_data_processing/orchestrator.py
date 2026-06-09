"""
主流程编排器
将各模块串联为完整的问卷数据处理流水线。
"""

import os
import sys
import pandas as pd

from .questionnaire_parser import parse_questionnaire, show_questionnaire_summary
from .data_loader import load_data
from .column_mapper import build_column_map
from .interaction import (
    ask_file_paths, ask_sheet_names, ask_cleaning_rules,
    ask_label_rules, ask_score_questions, ask_derived_cols,
    ask_open_ended_config,
)
from .cleaner import apply_cleaning_rules
from .label_engine import generate_labels, show_label_distribution
from .tabulator import make_output_rows
from .open_ended import analyze_open_ended
from .excel_writer import write_output_excel
from .config import Config


def run_pipeline():
    """执行完整的数据处理流水线"""
    print('\n' + '=' * 70)
    print('   QNR Data Processing — 通用问卷数据处理')
    print('=' * 70)

    # ====== 配置加载/新建 ======
    saved_configs = Config.list_saved()
    cfg = Config()

    if saved_configs:
        print(f'\n检测到已保存的配置: {", ".join(saved_configs)}')
        use_saved = input('是否加载已有配置？（输入配置名，或直接回车新建）: ').strip()
        if use_saved:
            loaded = Config.load(use_saved)
            if loaded:
                cfg = loaded

    # ====== 文件路径 ======
    qnr_path = cfg.qnr_path or ''
    data_path = cfg.data_path or ''

    if not qnr_path or not os.path.exists(qnr_path):
        qnr_path = input(f'\n问卷文件路径: ').strip()
    if not data_path or not os.path.exists(data_path):
        data_path = input(f'数据文件路径: ').strip()

    output_path = input(f'输出文件路径（默认: 分析输出表.xlsx）: ').strip()
    if not output_path:
        output_path = os.path.join(os.getcwd(), '分析输出表.xlsx')

    cfg.qnr_path = qnr_path
    cfg.data_path = data_path

    # ====== Step 1: 问卷解析 ======
    print('\n' + '=' * 70)
    print('Step 1: 解析问卷')
    print('=' * 70)
    try:
        qnaire = parse_questionnaire(qnr_path)
    except Exception as e:
        print(f'  ❌ 问卷解析失败: {e}')
        sys.exit(1)
    show_questionnaire_summary(qnaire)

    # ====== Step 2: 加载数据 ======
    print('\n' + '=' * 70)
    print('Step 2: 加载数据')
    print('=' * 70)
    num_sheet = cfg.num_sheet if hasattr(cfg, 'num_sheet') else '数字版'
    text_sheet = cfg.text_sheet if hasattr(cfg, 'text_sheet') else '文字版'

    num_sheet = input(f'数字版 sheet 名（默认: {num_sheet}）: ').strip() or num_sheet
    text_sheet = input(f'文字版 sheet 名（默认: {text_sheet}）: ').strip() or text_sheet
    cfg.num_sheet = num_sheet
    cfg.text_sheet = text_sheet

    try:
        df_num, df_text = load_data(data_path, num_sheet, text_sheet)
    except Exception as e:
        print(f'\n⚠ 数据加载失败: {e}')
        print('请分别输入数字版和文字版的文件路径。')
        num_path = input(f'数字版文件路径: ').strip()
        text_path = input(f'文字版文件路径: ').strip()
        df_num, df_text = load_data(data_path, num_sheet, text_sheet,
                                    num_path=num_path, text_path=text_path)

    # 派生列处理
    derived_n = ask_derived_cols()
    cfg.derived_cols = derived_n
    if derived_n > 0:
        df_num = df_num.iloc[:, :-derived_n]
        df_text = df_text.iloc[:, :-derived_n]

    print(f'\n  原始样本量: {len(df_num)}')
    print(f'  数据列数: {len(df_num.columns)}')

    # ====== Step 3: 清洗 ======
    cleaning_rules = cfg.cleaning_rules if cfg.cleaning_rules else ask_cleaning_rules()
    if cleaning_rules:
        df_num, df_text, _ = apply_cleaning_rules(df_num, df_text, cleaning_rules)
        cfg.cleaning_rules = cleaning_rules
    else:
        print('  无需清洗，继续下一步')

    # ====== Step 4: 标签定义 ======
    label_rules = cfg.label_rules if cfg.label_rules else ask_label_rules()
    cfg.label_rules = label_rules

    if label_rules:
        print('\n正在生成标签...')
        labels, label_names = generate_labels(df_num, label_rules)
        show_label_distribution(labels, label_names)
    else:
        print('  未定义自定义标签，仅使用"总体"分组')
        labels = pd.Series(['总体'] * len(df_num), name='分组标签')
        label_names = []

    # 构建分组
    group_names = ['总体'] + label_names
    groups = {'总体': pd.Series(True, index=df_text.index)}
    for name in label_names:
        groups[name] = labels == name

    # 添加标签到数据框
    df_num['分组标签'] = labels
    df_text['分组标签'] = labels

    # ====== 列映射构建 ======
    print('\n' + '=' * 70)
    print('构建列-题映射...')
    column_info, open_ended_cols = build_column_map(
        df_text, df_num, qnaire, label_cols=['id', '分组标签']
    )

    # 构建多选列分组
    multi_cols_by_q = {}
    for col_name, ci in column_info.items():
        if ci['type'] == 'multi':
            qn = ci['q_num']
            if qn not in multi_cols_by_q:
                multi_cols_by_q[qn] = []
            multi_cols_by_q[qn].append(ci)

    # 多选 eligibility 预计算
    multi_eligibility = {}
    for qn, cols in multi_cols_by_q.items():
        for gname, gmask in groups.items():
            any_selected = pd.Series(False, index=df_text.index)
            for ci in cols:
                any_selected = any_selected | (ci['text_series'] == '是')
            multi_eligibility[(qn, gname)] = gmask & any_selected

    # ====== Step 5: 评分题配置 ======
    score_configs = ask_score_questions(qnaire)
    cfg.score_qnums = list(score_configs.keys())

    # ====== Step 6: 开放题分析配置 ======
    open_ended_cfg = ask_open_ended_config(qnaire, open_ended_cols)

    # ====== Step 7: 生成输出 ======
    print('\n' + '=' * 70)
    print('生成输出数据...')
    print('=' * 70)

    # 列排序
    col_info_list = []
    for col_name in df_text.columns:
        if col_name in ['id', '分组标签']:
            continue
        if col_name in column_info:
            col_info_list.append(column_info[col_name])

    col_info_list.sort(key=lambda x: (
        0 if x['type'] != 'skip' else 1,
        x['q_num'] if x['q_num'] else 999,
        x['col_idx']
    ))

    output_rows = make_output_rows(
        col_info_list, groups, qnaire, score_configs,
        multi_cols_by_q, multi_eligibility, group_names
    )

    # 开放题分析
    print('生成开放题分析...')
    if open_ended_cfg:
        open_ended_analysis = analyze_open_ended(df_text, open_ended_cols, open_ended_cfg)
    else:
        open_ended_analysis = None

    # ====== Step 8: 写入 Excel ======
    print('写入 Excel...')
    wb = write_output_excel(
        output_rows, group_names, open_ended_cols,
        df_text, open_ended_analysis, filepath=output_path
    )

    # ====== 保存配置 ======
    save_cfg = input(f'\n是否保存当前配置以便下次复用？（y/n，默认 n）: ').strip().lower()
    if save_cfg == 'y':
        name = input(f'  配置名称（默认: {os.path.splitext(os.path.basename(qnr_path))[0]}）: ').strip()
        if not name:
            name = os.path.splitext(os.path.basename(qnr_path))[0]
        cfg.save(name)

    # ====== 输出摘要 ======
    print(f'\n{"=" * 70}')
    print(f'  ✅ 完成！文件已保存至: {output_path}')
    print(f'{"=" * 70}')
    print(f'  Sheet1 "数据分析表": {len(output_rows)} 行数据')
    print(f'  Sheet2 "填空题原话": 用户原始回答')
    print(f'  Sheet3 "开放题归纳": {"关键词分析" if open_ended_analysis else "无"}')
    print(f'  分组: {", ".join(group_names)}')
    print(f'  样本量: {len(df_num)}')
    print(f'{"=" * 70}')
