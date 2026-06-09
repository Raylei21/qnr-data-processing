"""
数表生成模块
根据列映射、分组、评分配置生成频数+频率输出行。
完全通用，无硬编码。
"""

import re
import pandas as pd
from .column_mapper import get_question_text
from .option_matcher import get_display_options


def make_output_rows(column_info_list, groups, qnaire_data, score_configs,
                     multi_cols_by_q, multi_eligibility, group_names):
    """生成所有输出行"""
    output_rows = []
    processed_multi = set()

    for ci in column_info_list:
        if ci['type'] == 'skip':
            continue

        col_name = ci['col_name']
        qn = ci['q_num']
        q_type = ci['type']
        q_text = get_question_text(ci['header'])

        # === 多选 ===
        if q_type == 'multi':
            if qn in processed_multi:
                continue
            processed_multi.add(qn)

            group_cols = multi_cols_by_q.get(qn, [ci])

            for sub_ci in group_cols:
                sub_name = sub_ci['col_name']
                # 提取选项名（方括号中的内容）
                opt_name = sub_name
                m = re.search(r'\[([^\]]+)\]', str(sub_name))
                if m:
                    opt_name = m.group(1)

                row = {'问题': q_text, '选项': opt_name}

                for gname in group_names:
                    gmask = groups[gname]
                    eligible = multi_eligibility.get((qn, gname), gmask)
                    total_eligible = eligible.sum()
                    selected = eligible & (sub_ci['text_series'] == '是')
                    cnt = selected.sum()
                    pct = cnt / total_eligible * 100 if total_eligible > 0 else 0
                    row[f'{gname}_cnt'] = cnt
                    row[f'{gname}_pct'] = round(pct, 2)

                output_rows.append(row)

        # === 单选/矩阵 ===
        elif q_type == 'single':
            text_series = ci['text_series']

            # 跳过已经是多选的一部分的"是"列
            unique_vals = text_series.dropna().unique()
            is_sub_of_multi = (len(unique_vals) == 1 and str(unique_vals[0]) == '是')
            # 检查是否已被多选处理
            if is_sub_of_multi and qn in processed_multi:
                continue

            # 获取显示选项列表（自动模糊匹配）
            display_opts, opt_mapping = get_display_options(
                qnaire_data, qn, text_series, score_configs
            )

            if not display_opts:
                continue

            first_row = True
            for opt in display_opts:
                row = {'问题': q_text if first_row else '', '选项': opt}
                mapped_opt = opt_mapping.get(opt, opt)
                opt_exact = mapped_opt.strip() if mapped_opt else opt.strip()

                for gname in group_names:
                    gmask = groups[gname]
                    answered = gmask & text_series.notna()
                    total_ans = answered.sum()

                    if opt_exact is None:
                        cnt = 0
                    else:
                        matched = answered & (text_series.str.strip() == opt_exact)
                        cnt = matched.sum()

                    pct = cnt / total_ans * 100 if total_ans > 0 else 0
                    row[f'{gname}_cnt'] = cnt
                    row[f'{gname}_pct'] = round(pct, 2)

                output_rows.append(row)
                first_row = False

            # T2B/B2B 行
            if score_configs and qn in score_configs:
                sc = score_configs[qn]

                for label, is_t2b in [('T2B', True), ('B2B', False)]:
                    srow = {'问题': q_text if first_row else '', '选项': label}
                    first_row = False

                    for gname in group_names:
                        gmask = groups[gname]
                        answered = gmask & text_series.notna()
                        total_ans = answered.sum()

                        opts = sc['t2b_opts'] if is_t2b else sc['b2b_opts']
                        cnt = sum(
                            (answered & (text_series.str.strip() == opt)).sum()
                            for opt in opts
                        )
                        pct = cnt / total_ans * 100 if total_ans > 0 else 0
                        srow[f'{gname}_cnt'] = cnt
                        srow[f'{gname}_pct'] = round(pct, 2)

                    output_rows.append(srow)

        # === 填空/开放 ===
        elif q_type == 'open':
            row = {'问题': q_text, '选项': '有填写'}
            for gname in group_names:
                gmask = groups[gname]
                answered = gmask & ci['text_series'].notna()
                cnt = answered.sum()
                total = gmask.sum()
                pct = cnt / total * 100 if total > 0 else 0
                row[f'{gname}_cnt'] = cnt
                row[f'{gname}_pct'] = round(pct, 2)
            output_rows.append(row)

    return output_rows
