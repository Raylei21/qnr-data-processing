"""
数据加载模块
加载数字版和文字版 Excel 数据。
"""

import pandas as pd


def load_data(data_path, num_sheet='数字版', text_sheet='文字版',
              num_path=None, text_path=None):
    """
    加载数字版和文字版数据。

    参数:
      data_path: 同时包含 num 和 text sheet 的文件路径
      num_sheet, text_sheet: sheet 名称
      num_path, text_path: 如果 num 和 text 在不同文件，分别指定

    返回:
      (df_num, df_text)
    """
    if num_path is None:
        num_path = data_path
    if text_path is None:
        text_path = data_path

    df_num = pd.read_excel(num_path, sheet_name=num_sheet)
    df_text = pd.read_excel(text_path, sheet_name=text_sheet)

    return df_num, df_text
