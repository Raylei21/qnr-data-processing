"""
列映射模块
将数据列名与问卷问题建立映射。
完全通用，无硬编码题号。
"""

import re


def get_q_number_from_col(col_name):
    """从列名提取主问题编号，如 Q3[1]... → 3, HQ33... → 33"""
    m = re.search(r'Q(\d+)', str(col_name))
    return int(m.group(1)) if m else None


def get_question_text(col_name):
    """从列名提取问题题干（去除类型标记和方括号子项）"""
    original = str(col_name)
    for keyword in ['(多选)', '(矩阵单选)', '(单选)', '(填空)', 'open']:
        if keyword in original:
            parts = original.split(keyword, 1)
            q_text = parts[0].strip()
            remaining = parts[1] if len(parts) > 1 else ''
            # 对于矩阵题，保留 [子项] 信息
            bracket_match = re.search(r'\[([^\]]+)\]', remaining)
            if bracket_match and ('(矩阵单选)' in keyword or keyword == '(矩阵单选)'):
                q_text = f"{q_text} [{bracket_match.group(1)}]"
            return q_text
    return original


def detect_col_type(header, q_num, qnaire_data):
    """
    根据列名和问卷信息判断列类型。
    返回: 'single' | 'multi' | 'open' | 'skip'
    """
    header_str = str(header)

    # 跳过列
    if re.search(r'\[CODE\]|\[VALUE\]', header_str):
        return 'skip'
    if 'Q0.' in header_str:
        return 'skip'

    # 多选
    if '(多选)' in header_str:
        return 'multi'

    # 填空/开放题
    if '(填空)' in header_str or '填空' in header_str:
        return 'open'

    # 矩阵单选 / 单选
    if '(矩阵单选)' in header_str or '(单选)' in header_str:
        return 'single'

    # 若问卷信息显示该题是多选，则也标记为 multi
    if q_num and q_num in qnaire_data:
        qtype = qnaire_data[q_num].get('type', '')
        if qtype == 'multi':
            return 'multi'
        if qtype in ('single', 'matrix_single'):
            return 'single'
        if qtype == 'open':
            return 'open'

    return 'single'


def build_column_map(df_text, df_num, qnaire_data, label_cols=None):
    """
    构建数据列与问卷问题的映射。

    参数:
      df_text, df_num: 文字版和数字版 DataFrame
      qnaire_data: 问卷解析结果
      label_cols: 需要跳过的列名（如 ['id', '分组标签']）

    返回:
      column_info: {col_name: {col_name, col_idx, header, type, q_num, text_series, num_series}}
      open_ended_cols: {q_num_str: {col, text, qnum}}
    """
    if label_cols is None:
        label_cols = []

    column_info = {}
    open_ended_cols = {}

    for i, col_name in enumerate(df_text.columns):
        if col_name in label_cols:
            continue

        header = str(col_name)
        q_num = get_q_number_from_col(col_name)
        q_type = detect_col_type(header, q_num, qnaire_data)

        # 处理特殊列名模式：Q34A, Q34B, HQ33 等
        # Q34A → 视为 Q34 的单选题
        # Q34B → 视为独立题（编号 = 题号+100 以区分）
        m_a = re.match(r'Q(\d+)A', str(col_name))
        m_b = re.match(r'Q(\d+)B', str(col_name))
        hq_m = re.match(r'HQ(\d+)', str(col_name))

        if m_a:
            q_num = int(m_a.group(1))
            q_type = 'single'
        elif m_b:
            q_num = int(m_b.group(1)) + 100  # 特殊编号
            q_type = 'single'
        elif hq_m and q_num is None:
            q_num = int(hq_m.group(1))
            q_type = 'single'

        column_info[col_name] = {
            'col_name': col_name,
            'col_idx': i,
            'header': header,
            'type': q_type,
            'q_num': q_num,
            'text_series': df_text.iloc[:, i],
            'num_series': df_num.iloc[:, i],
        }

        # 收集开放题列
        if q_type == 'open' and q_num:
            base_text = get_question_text(header)
            open_ended_cols[str(q_num)] = {
                'col': col_name,
                'text': base_text,
                'qnum': q_num,
            }

    return column_info, open_ended_cols
