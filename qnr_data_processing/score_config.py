"""
评分题配置模块
使用选项位置索引（而非文字）定义 T2B/B2B，确保通用性。
"""

class ScoreConfig:
    """评分题 T2B/B2B 配置"""

    def __init__(self):
        # {qnum: {type, options, t2b_opts, b2b_opts, t2b_indices, b2b_indices}}
        self.configs = {}

    def add(self, qn, options, t2b_indices, b2b_indices, q_type='single'):
        """添加一个评分题的配置"""
        self.configs[qn] = {
            'type': q_type,
            'options': list(options),
            't2b_opts': [options[i - 1] for i in t2b_indices if 1 <= i <= len(options)],
            'b2b_opts': [options[i - 1] for i in b2b_indices if 1 <= i <= len(options)],
            't2b_indices': t2b_indices,
            'b2b_indices': b2b_indices,
        }

    def get(self, qn, default=None):
        return self.configs.get(qn, default)

    def __contains__(self, qn):
        return qn in self.configs

    def __iter__(self):
        return iter(self.configs)
