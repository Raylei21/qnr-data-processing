"""
交互式用户输入模块
所有与用户的命令行交互集中在此。
"""

import re
from .config import Config


def ask_file_paths():
    """询问问卷和数据文件路径"""
    import os
    default_dir = os.getcwd()

    qnr_path = input(f'问卷文件路径（默认: 问卷.xlsx）: ').strip()
    if not qnr_path:
        qnr_path = os.path.join(default_dir, '问卷.xlsx')

    data_path = input(f'数据文件路径（默认: 数据.xlsx）: ').strip()
    if not data_path:
        data_path = os.path.join(default_dir, '数据.xlsx')

    output_path = input(f'输出文件路径（默认: 分析输出表.xlsx）: ').strip()
    if not output_path:
        output_path = os.path.join(default_dir, '分析输出表.xlsx')

    return qnr_path, data_path, output_path


def ask_sheet_names():
    """询问 sheet 名称"""
    num_sheet = input(f'数字版 sheet 名（默认: 数字版）: ').strip() or '数字版'
    text_sheet = input(f'文字版 sheet 名（默认: 文字版）: ').strip() or '文字版'
    return num_sheet, text_sheet


def ask_derived_cols():
    """询问末尾派生列数"""
    derived_n = input(f'末尾派生标签列数（默认去掉最后37列，0为不去掉）: ').strip()
    if derived_n == '':
        return 37
    return int(derived_n) if derived_n.isdigit() else 0


def ask_cleaning_rules():
    """交互式询问清洗规则"""
    print('\n' + '=' * 70)
    print('数据清洗')
    print('请输入清洗规则，每行一条。格式示例：')
    print('  Q1=2 and Q3=1       # 剔除 Q1=2 且 Q3=1 的样本')
    print('  Q5≠3                # 剔除 Q5≠3 的样本')
    print('  Q2>3                # 剔除 Q2>3 的样本')
    print('  Q4=4 or Q5=5        # 剔除 Q4=4 或 Q5=5 的样本')
    print('直接回车表示无需清洗')
    print('=' * 70)

    rules = []
    while True:
        line = input(f'  规则 {len(rules) + 1}（留空结束）: ').strip()
        if not line:
            break
        rules.append(line)
    return rules


def ask_label_rules():
    """交互式询问分组标签规则"""
    print('\n' + '=' * 70)
    print('分组标签定义')
    print('请定义各组标签的筛选规则。')
    print('格式示例（支持中英文标点）：')
    print('  核心篮球迷：Q18=1，且Q19=1～2；或Q18=2，Q19=1')
    print('  普通篮球迷：Q18=1，Q19=3；或Q18=2，Q19=2；或Q18=3，Q19=1')
    print()
    print('说明：')
    print('  · 同一条件内用 and/且/逗号连接（AND关系）')
    print('  · 用 分号/or 分隔不同的 OR 分支')
    print('  · 范围用 ～ 或 - 表示（如 1～3 = 1,2,3）')
    print('  · 系统会自动添加"总体"标签')
    print('=' * 70)

    label_rules = []
    while True:
        line = input(f'  规则描述 {len(label_rules) + 1}（留空结束）: ').strip()
        if not line:
            if not label_rules:
                print('  ⚠ 至少需要定义一个标签（除"总体"外）')
                continue
            break
        label_rules.append(line)
    return label_rules


def ask_score_questions(qnaire_data):
    """
    交互式配置评分题的 T2B/B2B。
    使用选项位置索引（从1开始）而不是选项文字，确保通用性。

    返回: {q_num: {type, options, t2b_opts, b2b_opts, t2b_indices, b2b_indices}}
      - t2b_opts 是选项文本列表（用于显示）
      - t2b_indices 是选项索引列表（从1开始，用于通用匹配）
    """
    print('\n' + '=' * 70)
    print('评分题 T2B/B2B 配置')
    print('如需为评分题添加 T2B（Top2Box）和 B2B（Bottom2Box）汇总行，请在此配置。')
    print('系统将自动根据问卷选项数量，推荐可能是评分题的题目供您确认。')
    print('=' * 70)

    # 自动推荐：4/5/7/10/11 个选项的题目
    candidates = {}
    for qn, q in qnaire_data.items():
        n_opts = len(q.get('options', []))
        if n_opts in [4, 5, 7, 10, 11]:
            candidates[qn] = q

    if candidates:
        print('\n以下题目可能是评分题（选项数匹配）：')
        for qn in sorted(candidates.keys()):
            q = candidates[qn]
            opts = ' / '.join(q['options'][:5])
            if len(q['options']) > 5:
                opts += '...'
            print(f'  Q{qn:>2} [{len(q["options"])}个选项] {q["text"][:60]}')
            print(f'      选项: {opts}')

    score_config = {}
    while True:
        resp = input('\n请输入需要T2B/B2B的题号（逗号分隔，如 3,7,10,13；直接回车跳过）: ').strip()
        if not resp:
            break
        q_nums = []
        for part in resp.split(','):
            part = part.strip()
            if part.isdigit():
                q_nums.append(int(part))
        if not q_nums:
            continue

        for qn in q_nums:
            q = qnaire_data.get(qn, {})
            opts = q.get('options', [])
            if not opts:
                print(f'  Q{qn} 在问卷中无选项信息，请手动输入选项')
                opts_input = input(f'  Q{qn} 的选项（用 / 分隔）: ').strip()
                opts = [o.strip() for o in opts_input.split('/') if o.strip()]

            n_opts = len(opts)
            print(f'\n  Q{qn} 的选项列表:')
            for j, o in enumerate(opts, 1):
                print(f'    {j}. {o}')
            print(f'  T2B = 最后 {min(2, n_opts)} 个选项（评分最高）')
            print(f'  B2B = 前 {min(2, n_opts)} 个选项（评分最低）')

            # 使用索引位置（从1开始），默认最后2个为 T2B，前2个为 B2B
            t2b_indices = list(range(n_opts - min(2, n_opts) + 1, n_opts + 1))
            b2b_indices = list(range(1, min(3, n_opts + 1)))

            print(f'  默认 T2B = 选项 {t2b_indices} ({"、".join(opts[i-1] for i in t2b_indices)})')
            print(f'  默认 B2B = 选项 {b2b_indices} ({"、".join(opts[i-1] for i in b2b_indices)})')

            custom = input(f'  自定义 T2B 索引（用逗号分隔，留空用默认）: ').strip()
            if custom:
                try:
                    t2b_indices = [int(x.strip()) for x in custom.split(',') if x.strip().isdigit()]
                except ValueError:
                    pass

            custom = input(f'  自定义 B2B 索引（用逗号分隔，留空用默认）: ').strip()
            if custom:
                try:
                    b2b_indices = [int(x.strip()) for x in custom.split(',') if x.strip().isdigit()]
                except ValueError:
                    pass

            score_config[qn] = {
                'type': q.get('type', 'single'),
                'options': opts,
                't2b_opts': [opts[i - 1] for i in t2b_indices if 1 <= i <= len(opts)],
                'b2b_opts': [opts[i - 1] for i in b2b_indices if 1 <= i <= len(opts)],
                't2b_indices': t2b_indices,
                'b2b_indices': b2b_indices,
            }
            print(f'  Q{qn}: T2B={score_config[qn]["t2b_opts"]}, B2B={score_config[qn]["b2b_opts"]}')

        break  # 只接受一次输入

    return score_config


def ask_open_ended_config(qnaire_data, open_ended_cols):
    """
    配置开放题分析。
    用户可选择要分析的开放题，并配置关键词分类规则。

    返回: {qnum: {title, keywords: {theme: [keywords, ...]}}}
      None 表示跳过分析
    """
    if not open_ended_cols:
        return None

    print('\n' + '=' * 70)
    print('开放题分析配置')
    print('系统检测到以下开放题：')
    for qnum_str in sorted(open_ended_cols.keys(), key=lambda x: int(x)):
        info = open_ended_cols[qnum_str]
        qn = info['qnum']
        q = qnaire_data.get(qn, {})
        text_preview = q.get('text', info.get('text', ''))[:60]
        print(f'  Q{qn}: {text_preview}')

    do_analysis = input('\n是否对这些开放题进行关键词归纳分析？（y/n，默认 y）: ').strip().lower()
    if do_analysis == 'n':
        return None

    config = {}
    print('\n可配置关键词分类规则（留空则使用自动关键词频率统计）')
    for qnum_str in sorted(open_ended_cols.keys(), key=lambda x: int(x)):
        info = open_ended_cols[qnum_str]
        qn = info['qnum']
        print(f'\n  Q{qn}:')
        title = input(f'   分析标题（默认: Q{qn} 关键词分析）: ').strip()
        if not title:
            title = f'Q{qn} 关键词分析'

        custom_kw = input(f'   是否自定义关键词分类规则？（y/n，默认 n）: ').strip().lower()
        keywords = {}
        if custom_kw == 'y':
            print('   请输入关键词分类，每行一个。格式：类别名：关键词1、关键词2、关键词3')
            print('   留空行结束。')
            while True:
                line = input('     分类规则: ').strip()
                if not line:
                    break
                parts = re.split(r'[：:]\s*', line, maxsplit=1)
                if len(parts) == 2:
                    theme = parts[0].strip()
                    kw_list = [k.strip() for k in re.split(r'[、,，]', parts[1]) if k.strip()]
                    if theme and kw_list:
                        keywords[theme] = kw_list
                        print(f'      → 已添加: {theme} ({len(kw_list)} 个关键词)')

        config[str(qn)] = {
            'title': title,
            'keywords': keywords if keywords else {},
        }

    return config if config else {'auto': True}
