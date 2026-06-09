"""
选项模糊匹配模块
当问卷选项文本与数据标签不一致时，使用 difflib 进行模糊匹配。
"""

import difflib


def fuzzy_match_options(qnaire_opts, data_opt_values, cutoff=0.6):
    """
    将问卷选项列表与数据中实际出现的选项值进行模糊匹配。

    参数:
      qnaire_opts: 问卷中的选项列表 [str, ...]
      data_opt_values: 数据中实际出现的唯一值列表 [str, ...]
      cutoff: 匹配阈值（0-1），默认 0.6

    返回:
      mapping: {qnaire_opt: matched_data_opt or None}
        当匹配不上时值为 None（该选项在数据中不存在）
    """
    mapping = {}
    # 先尝试精确匹配
    remaining_qnaire = []
    for qo in qnaire_opts:
        qo_stripped = qo.strip()
        exact_match = None
        for do in data_opt_values:
            do_stripped = do.strip()
            if do_stripped == qo_stripped:
                exact_match = do_stripped
                break
        if exact_match:
            mapping[qo] = exact_match
        else:
            remaining_qnaire.append(qo)

    # 对剩余的问卷选项做模糊匹配
    unmatched_data = [d.strip() for d in data_opt_values
                      if d.strip() not in mapping.values()]

    for qo in remaining_qnaire:
        if not unmatched_data:
            mapping[qo] = None
            continue

        # 计算所有相似度
        similarities = [(do, difflib.SequenceMatcher(None, qo.strip(), do).ratio())
                        for do in unmatched_data]
        similarities.sort(key=lambda x: x[1], reverse=True)

        best_match, best_ratio = similarities[0] if similarities else (None, 0)

        if best_ratio >= cutoff:
            mapping[qo] = best_match
            unmatched_data = [d for d in unmatched_data if d != best_match]
        else:
            mapping[qo] = None

    return mapping


def get_display_options(qnaire_data, qn, text_series, score_config=None):
    """
    获取要显示在输出表中的选项列表。
    优先使用问卷选项，通过模糊匹配判断标签是否一致。

    返回:
      (display_opts, opt_mapping)
      display_opts: 要显示的选项文本列表
      opt_mapping: {显示文本: 数据中的精确标签}
    """
    qnaire_q = qnaire_data.get(qn, {})
    # 如果是矩阵题，用问卷选项的原始文本（可能包含方括号）
    qnaire_opts = qnaire_q.get('options', [])

    # 从数据中获取实际出现的唯一值
    data_vals = set()
    for v in text_series.dropna().unique():
        v_str = str(v).strip()
        if v_str and v_str != '是':  # 跳过多选的 "是"
            data_vals.add(v_str)

    data_opt_values = list(data_vals)

    # 判断问卷选项是否与数据标签兼容
    if qnaire_opts:
        mapping = fuzzy_match_options(qnaire_opts, data_opt_values, cutoff=0.6)

        # 如果至少匹配上一个，说明问卷选项可用
        has_any_match = any(v is not None for v in mapping.values())
        if has_any_match:
            display_opts = list(qnaire_opts)
            return display_opts, mapping

    # 问卷选项不可用，使用数据中的实际值
    if data_opt_values:
        # 尝试数值排序
        try:
            display_opts = sorted(data_opt_values, key=lambda x: int(x))
        except (ValueError, TypeError):
            display_opts = sorted(data_opt_values)
        return display_opts, {o: o for o in display_opts}

    return [], {}
