"""
数据清洗模块
应用用户定义的清洗规则。完全通用，无硬编码。
"""

import pandas as pd
import re
from .column_mapper import get_q_number_from_col


def parse_single_condition(cond_str):
    """
    解析单一条件如 'Q1=2'、'Q19=1～2'、'Q5≠3'、'Q2>3'
    返回 (q_num, operator, values)
    """
    cond_str = cond_str.strip()
    patterns = [
        (r'Q(\d+)\s*[=]\s*(\d+)\s*[～~-]\s*(\d+)', lambda m: (
            int(m.group(1)), 'in', list(range(int(m.group(2)), int(m.group(3)) + 1)))),
        (r'Q(\d+)\s*[=]\s*(\d+)', lambda m: (int(m.group(1)), 'eq', [int(m.group(2))])),
        (r'Q(\d+)\s*(≠|!=)\s*(\d+)', lambda m: (int(m.group(1)), 'neq', [int(m.group(3))])),
        (r'Q(\d+)\s*[>]\s*(\d+)', lambda m: (int(m.group(1)), 'gt', [int(m.group(2))])),
        (r'Q(\d+)\s*[<]\s*(\d+)', lambda m: (int(m.group(1)), 'lt', [int(m.group(2))])),
        (r'Q(\d+)\s*[≥>=]\s*(\d+)', lambda m: (int(m.group(1)), 'gte', [int(m.group(2))])),
        (r'Q(\d+)\s*[≤<=]\s*(\d+)', lambda m: (int(m.group(1)), 'lte', [int(m.group(2))])),
    ]
    for pattern, handler in patterns:
        m = re.search(pattern, cond_str)
        if m:
            return handler(m)
    return None


def parse_cleaning_rule(rule_text):
    """
    解析清洗规则文本。支持 and/or 连接。
    返回: (逻辑类型, [(q_num, op, values), ...])
    """
    rule_text = rule_text.strip()
    if ' or ' in rule_text.lower() or ' 或 ' in rule_text:
        separator = 'or'
    else:
        separator = 'and'

    if separator == 'or':
        parts = re.split(r'\s+(?:or|Or|OR|或)\s+', rule_text)
    else:
        parts = re.split(r'\s+(?:and|And|AND|且|并且)\s+|\s*[,，]\s*(?=Q)', rule_text)

    conditions = []
    for part in parts:
        part = part.strip()
        if part:
            parsed = parse_single_condition(part)
            if parsed:
                conditions.append(parsed)
            else:
                print(f'   ⚠  无法解析条件: "{part}"，已跳过')
    return separator, conditions


def apply_cleaning_rules(df_num, df_text, rules):
    """
    应用清洗规则，返回清洗后的数据框。
    每一条 rule 独立应用（规则之间是 AND 关系）。
    """
    if not rules:
        return df_num, df_text, []

    total_before = len(df_num)
    removed_details = []

    for rule_text in rules:
        logic, conditions = parse_cleaning_rule(rule_text)
        if not conditions:
            continue

        condition_masks = []
        for qn, op, values in conditions:
            col_name = None
            for c in df_num.columns:
                qnum = get_q_number_from_col(c)
                if qnum == qn:
                    col_name = c
                    break
            if col_name is None:
                print(f'   ⚠  找不到 Q{qn} 对应的列，跳过此条件')
                continue

            if op == 'eq':
                condition_masks.append(df_num[col_name] == values[0])
            elif op == 'neq':
                condition_masks.append(df_num[col_name] != values[0])
            elif op == 'in':
                condition_masks.append(df_num[col_name].isin(values))
            elif op == 'gt':
                condition_masks.append(df_num[col_name] > values[0])
            elif op == 'lt':
                condition_masks.append(df_num[col_name] < values[0])
            elif op == 'gte':
                condition_masks.append(df_num[col_name] >= values[0])
            elif op == 'lte':
                condition_masks.append(df_num[col_name] <= values[0])

        if not condition_masks:
            continue

        if logic == 'or':
            remove_mask = pd.concat(condition_masks, axis=1).any(axis=1)
        else:
            remove_mask = pd.concat(condition_masks, axis=1).all(axis=1)

        n_removed = remove_mask.sum()
        removed_details.append((rule_text, n_removed))
        keep_mask = ~remove_mask
        df_num = df_num[keep_mask].reset_index(drop=True)
        df_text = df_text[keep_mask].reset_index(drop=True)

    total_after = len(df_num)
    print(f'\n  清洗前样本量: {total_before}')
    for rule, n in removed_details:
        print(f'  规则 "{rule}" → 剔除 {n} 个样本')
    print(f'  清洗后样本量: {total_after}')
    return df_num, df_text, removed_details
