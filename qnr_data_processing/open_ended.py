"""
开放题分析模块
对填空题/开放题做关键词归纳分析。
不依赖任何特定题号或关键词——关键词分类可由用户自定义，
未自定义时自动做高频词统计。
"""

from collections import Counter
import re


def _tokenize(text):
    """简单中文分词：按标点和空格分割"""
    text = str(text).lower()
    # 按非中文字符和标点分割
    # 使用原始字符串避免 SyntaxWarning
    sep_chars = '，。！？、；：""''（）【】《》\\s,.!?;:()\\[\\]{}<>/\\\\|_\\-+'
    tokens = re.split(f'[{sep_chars}]', text)
    return [t.strip() for t in tokens if t.strip() and len(t.strip()) >= 2]


def _extract_ngrams(text, n=2):
    """提取字符级 n-gram 用于高频片段检测"""
    text = str(text).strip()
    if len(text) < n:
        return []
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def analyze_open_ended(df_text, open_ended_cols, config=None):
    """
    对填空题做关键词归纳分析。

    参数:
      df_text: 文字版 DataFrame
      open_ended_cols: {qnum_str: {col, text, qnum}}
      config: 用户配置（可选），格式:
        {qnum_str: {title, keywords: {theme: [keywords, ...]}}}
        为 None 时全部自动分析

    返回: [{title, note, headers, data}, ...]
    """
    from .column_mapper import get_question_text

    analysis = []

    for qnum_str in sorted(open_ended_cols.keys(), key=lambda x: int(x)):
        info = open_ended_cols[qnum_str]
        col_name = info['col']
        qn = info['qnum']

        if col_name not in df_text.columns:
            continue

        series = df_text[col_name].dropna()
        total = len(series)
        if total == 0:
            continue

        q_config = config.get(qnum_str, {}) if config else {}
        title = q_config.get('title', f'Q{qn} 关键词分析')
        keywords_config = q_config.get('keywords', {})

        if keywords_config:
            # 用户自定义关键词分类
            theme_cnt = Counter()
            for t in keywords_config:
                theme_cnt[t] = 0
            for v in series:
                lower = str(v).lower()
                for theme, kws in keywords_config.items():
                    for kw in kws:
                        if kw in lower:
                            theme_cnt[theme] += 1
                            break

            rows = []
            for theme, cnt in theme_cnt.most_common():
                rows.append([theme, cnt, f'{cnt / total * 100:.1f}%'])

            analysis.append({
                'title': title,
                'note': f'有效样本：{total}人',
                'headers': ['关键词类别', '提及人数', '提及率'],
                'data': rows,
            })

        else:
            # 自动高频词分析
            # 1. 按空格/标点分词统计高频词
            word_counter = Counter()
            for v in series:
                tokens = _tokenize(v)
                word_counter.update(tokens)

            # 过滤掉常见停用词
            stop_words = {'一个', '什么', '没有', '可以', '这个', '那个', '就是',
                         '不是', '但是', '还是', '因为', '所以', '如果', '虽然',
                         '而且', '或者', '比较', '非常', '很多', '一些', '有些'}
            meaningful_words = [(w, c) for w, c in word_counter.most_common(30)
                               if w not in stop_words and len(w) >= 2][:15]

            if meaningful_words:
                rows = []
                for i, (word, cnt) in enumerate(meaningful_words, 1):
                    rows.append([i, word, cnt, f'{cnt / total * 100:.1f}%'])

                analysis.append({
                    'title': title,
                    'note': f'有效样本：{total}人 | 高频词汇 Top 15',
                    'headers': ['排名', '关键词', '出现次数', '出现率'],
                    'data': rows,
                })

            # 2. 统计字符级 2-gram 高频片段
            ngram_counter = Counter()
            for v in series:
                grams = _extract_ngrams(v, 2)
                ngram_counter.update(grams)

            meaningful_ngrams = [(g, c) for g, c in ngram_counter.most_common(20)
                                if len(g.strip()) == 2 and not all(ch in '的了吗是不在有了和我与人就都对上' for ch in g)][:10]

            if meaningful_ngrams:
                rows = []
                total_ngrams = sum(c for _, c in meaningful_ngrams)
                for i, (gram, cnt) in enumerate(meaningful_ngrams, 1):
                    rows.append([i, gram, cnt, f'{cnt / total_ngrams * 100:.1f}%'])

                analysis.append({
                    'title': f'{title} - 高频片段',
                    'note': f'基于字符片段（2-gram）分析',
                    'headers': ['排名', '片段', '出现次数', '占比'],
                    'data': rows,
                })

    return analysis if analysis else None
