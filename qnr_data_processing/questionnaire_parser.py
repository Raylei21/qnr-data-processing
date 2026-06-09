"""
问卷解析模块
从问卷.xlsx 中自动识别题目类型和选项。
完全通用，不依赖任何特定问卷的题号或选项文字。
"""

import openpyxl
import re


# 题目类型标记关键词（可扩展）
TYPE_MARKERS = {
    '【单选题】': 'single',
    '【多选题】': 'multi',
    '【开放题】': 'open',
    '【填空题】': 'open',
    '【评分题】': 'single',
}

# Section header 关键词（出现在选项列中需要跳过的行）
SECTION_KEYWORDS = [
    '有提示认知度', '品牌美誉度', '品牌NPS',
    '篮球属性', '足球属性', '游戏属性',
    '社区属性', '基础人口属性',
    '以下哪方面', '主要用于',
]


def parse_questionnaire(path):
    """
    解析问卷.xlsx，返回：
      questions: {q_num: {num, text, type, options, full_text}}
      - type: 'single' | 'multi' | 'open' | 'unknown'
      - options: [option_text, ...]  (open 题为 [])
    """
    wb = openpyxl.load_workbook(path)
    ws = wb['Sheet1']
    questions = {}
    current_q = None

    def is_new_q(text):
        if not text:
            return False
        return any(k in str(text) for k in TYPE_MARKERS)

    all_rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))

    # 第一遍：数总题数
    q_idx = 0
    for row in all_rows:
        col_b = row[1] if len(row) > 1 else None
        if col_b and is_new_q(col_b):
            q_idx += 1

    q_idx = 0

    # 第二遍：解析题目和选项
    for row in all_rows:
        col_b = row[1] if len(row) > 1 else None
        col_c = row[2] if len(row) > 2 else None

        if col_b and is_new_q(col_b):
            q_idx += 1
            q_num = q_idx
            text = str(col_b).strip()

            # 判断题型
            qtype = 'single'
            for marker, t in TYPE_MARKERS.items():
                if marker in text:
                    qtype = t
                    break

            # 矩阵题检测：题干旁有"矩阵"标记
            if col_c and '矩阵' in str(col_c):
                qtype = 'matrix_single'

            current_q = {
                'num': q_num,
                'text': text,
                'type': qtype,
                'options': [],
                'full_text': text,
            }
            if col_c:
                current_q['full_text'] = f'{text} {col_c}'
            questions[q_num] = current_q
            continue

        if current_q and col_b:
            opt = str(col_b).strip()
            if not opt or opt.startswith('=MAX'):
                continue
            # 跳过 section header
            if any(sh in opt for sh in SECTION_KEYWORDS):
                continue
            current_q['options'].append(opt)

    wb.close()

    # 后处理：检测矩阵题的子选项
    _detect_matrix_subitems(questions)

    return questions


def _detect_matrix_subitems(questions):
    """
    检测矩阵题：如果某单选题的选项包含 ']'（如 "[抖音]"），
    则标记为矩阵题并提取子项列表。
    """
    for qn, q in questions.items():
        if q['type'] != 'single':
            continue
        has_brackets = False
        sub_items = []
        for opt in q['options']:
            m = re.search(r'\[([^\]]+)\]', opt)
            if m:
                has_brackets = True
                sub_items.append(m.group(1))
        if has_brackets and sub_items:
            q['type'] = 'matrix_single'
            q['sub_items'] = sub_items


def show_questionnaire_summary(questions):
    """打印问卷概要"""
    print('\n' + '=' * 70)
    print(f'问卷共 {len(questions)} 道题')
    print('=' * 70)
    for qn in sorted(questions.keys()):
        q = questions[qn]
        type_label = {
            'single': '单选', 'multi': '多选', 'matrix_single': '矩阵单选',
            'open': '开放/填空', 'unknown': '未知',
        }.get(q['type'], q['type'])
        n_opts = len(q.get('options', []))
        preview = q['text'][:80]
        print(f'  Q{qn:>2} [{type_label:>6}][{n_opts:>2}个选项] {preview}')
    print('=' * 70)
