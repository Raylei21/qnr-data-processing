"""
分组标签引擎
解析用户定义的标签规则并生成分组标签。
完全通用，无硬编码。
"""

import pandas as pd
import re
from .column_mapper import get_q_number_from_col
from .cleaner import parse_single_condition


def parse_label_rule(rule_text):
    """
    解析标签规则文本。
    输入: "核心篮球迷：Q18=1，且Q19=1～2；或Q18=2，Q19=1"
    返回: (label_name, [(logic, [(q_num, op, values), ...]), ...])
    """
    rule_text = rule_text.strip()
    m = re.split(r'[：:]\s*', rule_text, maxsplit=1)
    if len(m) < 2:
        print(f'  ⚠  无法解析标签名（缺少：分隔符）: "{rule_text}"')
        return None
    label_name = m[0].strip()
    body = m[1].strip()

    if not label_name or not body:
        print(f'  ⚠  标签名或规则体为空: "{rule_text}"')
        return None

    or_parts = re.split(r'\s*[；;]\s*|\s+或\s+', body)

    or_conditions = []
    for or_part in or_parts:
        or_part = or_part.strip()
        if not or_part:
            continue

        and_parts = re.split(r'\s+且\s+|\s+并且\s+|[，,]\s*', or_part)

        conditions = []
        for and_part in and_parts:
            and_part = and_part.strip()
            if not and_part:
                continue
            parsed = parse_single_condition(and_part)
            if parsed:
                conditions.append(parsed)
            else:
                print(f'    ⚠  无法解析条件: "{and_part}"（规则: {rule_text}）')

        if conditions:
            or_conditions.append(('and', conditions))

    if not or_conditions:
        print(f'  ⚠  规则解析后无有效条件: "{rule_text}"')
        return None

    return (label_name, or_conditions)


def _apply_conditions(df, conditions, logic):
    """应用一组条件，返回布尔掩码"""
    condition_masks = []
    for qn, op, values in conditions:
        col_name = None
        for c in df.columns:
            qnum = get_q_number_from_col(c)
            if qnum == qn:
                col_name = c
                break
        if col_name is None:
            print(f'    ⚠  找不到 Q{qn} 对应列，跳过')
            continue

        col = df[col_name]
        if op == 'eq':
            condition_masks.append(col == values[0])
        elif op == 'neq':
            condition_masks.append(col != values[0])
        elif op == 'in':
            condition_masks.append(col.isin(values))
        elif op == 'gt':
            condition_masks.append(col > values[0])
        elif op == 'lt':
            condition_masks.append(col < values[0])
        elif op == 'gte':
            condition_masks.append(col >= values[0])
        elif op == 'lte':
            condition_masks.append(col <= values[0])

    if not condition_masks:
        return pd.Series(False, index=df.index)

    if logic == 'or':
        return pd.concat(condition_masks, axis=1).any(axis=1)
    else:
        return pd.concat(condition_masks, axis=1).all(axis=1)


def generate_labels(df_num, label_rules):
    """
    根据用户定义的规则生成标签。
    始终保留"总体"标签（全量）。
    返回: pd.Series '分组标签'
    """
    df = df_num.copy()
    df['分组标签'] = '其他'

    label_names = []
    for rule_text in label_rules:
        parsed = parse_label_rule(rule_text)
        if parsed is None:
            continue
        label_name, or_conditions = parsed
        label_names.append(label_name)

        final_mask = pd.Series(False, index=df.index)
        for logic, conditions in or_conditions:
            branch_mask = _apply_conditions(df, conditions, logic)
            final_mask = final_mask | branch_mask

        df.loc[final_mask, '分组标签'] = label_name
        print(f'  {label_name}: {final_mask.sum()} 个样本')

    return df['分组标签'], label_names


def show_label_distribution(labels, label_names):
    """打印标签分布"""
    print('\n' + '=' * 40)
    print('标签分布')
    print('-' * 40)
    total = len(labels)
    print(f'  总体: {total} ({100.0:.1f}%)')
    for name in label_names:
        cnt = (labels == name).sum()
        print(f'  {name}: {cnt} ({cnt / total * 100:.1f}%)')
    others = (labels == '其他').sum()
    if others > 0:
        print(f'  其他: {others} ({others / total * 100:.1f}%)')
    print('=' * 40)
