"""
配置持久化模块
保存/加载问卷处理的中间配置，避免重复输入。
"""

import json
import os

DEFAULT_CONFIG_DIR = os.path.expanduser('~/.qnr_data_processing')


class Config:
    """问卷处理配置，可序列化为 JSON。"""

    def __init__(self):
        self.survey_name = ''
        self.qnr_path = ''
        self.data_path = ''
        self.num_sheet = '数字版'
        self.text_sheet = '文字版'
        self.derived_cols = 0
        self.cleaning_rules = []
        self.label_rules = []
        self.score_qnums = []
        self.score_t2b_indices = {}    # {qnum: [top N indices]}
        self.score_b2b_indices = {}     # {qnum: [bottom N indices]}

        # 列名映射缓存：{问卷选项文本: 数据中的实际选项文本}
        # 当模糊匹配确认后缓存映射关系
        self.option_mappings = {}       # {qnum: {qnaire_opt: data_opt}}

        # 开放题配置
        self.open_ended_keywords = {}   # {qnum_str: [keyword_category_dicts]}

    def save(self, name=None):
        """保存配置到 JSON 文件"""
        if name:
            self.survey_name = name
        if not self.survey_name:
            self.survey_name = 'default'
        os.makedirs(DEFAULT_CONFIG_DIR, exist_ok=True)
        path = os.path.join(DEFAULT_CONFIG_DIR, f'{self.survey_name}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.__dict__, f, ensure_ascii=False, indent=2)
        print(f'  配置已保存至: {path}')
        return path

    @classmethod
    def load(cls, name):
        """从 JSON 文件加载配置"""
        path = os.path.join(DEFAULT_CONFIG_DIR, f'{name}.json')
        if not os.path.exists(path):
            print(f'  配置未找到: {path}')
            return None
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        cfg = cls()
        cfg.__dict__.update(data)
        print(f'  配置已加载: {path}')
        return cfg

    @classmethod
    def list_saved(cls):
        """列出所有已保存的配置"""
        if not os.path.exists(DEFAULT_CONFIG_DIR):
            return []
        files = [f for f in os.listdir(DEFAULT_CONFIG_DIR) if f.endswith('.json')]
        return [f.replace('.json', '') for f in files]
