"""
Excel 输出模块
生成美观格式的 Excel 输出文件。
"""

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
import math

# 全局样式常量
HEADER_FONT = Font(name='微软雅黑', bold=True, size=11)
DATA_FONT = Font(name='微软雅黑', size=10)
SMALL_FONT = Font(name='微软雅黑', size=9)
SECTION_FONT = Font(name='微软雅黑', bold=True, size=11)
NOTE_FONT = Font(name='微软雅黑', size=9, italic=True, color='666666')
TITLE_FONT = Font(name='微软雅黑', bold=True, size=13)
TABLE_HEADER_FONT = Font(name='微软雅黑', bold=True, size=10, color='FFFFFF')

T2B_FILL = PatternFill(start_color='E2EFDA', end_color='E2EFDA', fill_type='solid')
B2B_FILL = PatternFill(start_color='FCE4D6', end_color='FCE4D6', fill_type='solid')
HEADER_FILL = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')
GROUP_FILL = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
TABLE_HEADER_FILL = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
ALT_FILL = PatternFill(start_color='D9E2F3', end_color='D9E2F3', fill_type='solid')

THIN_BORDER = Border(
    left=Side(style='thin'), right=Side(style='thin'),
    top=Side(style='thin'), bottom=Side(style='thin')
)
CENTER_ALIGN = Alignment(horizontal='center', vertical='center', wrap_text=True)
LEFT_ALIGN = Alignment(horizontal='left', vertical='center', wrap_text=True)

# 默认行高：0.5cm ≈ 14.17 points
ROW_HEIGHT_PT = 0.5 * 28.35


def write_output_excel(output_rows, group_names, open_ended_cols, df_text,
                       open_ended_analysis=None, filepath=None):
    """
    将完整数表写入 Excel 文件。

    参数:
      output_rows: [{问题, 选项, {group}_cnt, {group}_pct}, ...]
      group_names: [str, ...]
      open_ended_cols: {key: {col, text}}
      df_text: 文字版 DataFrame
      open_ended_analysis: [{title, note, headers, data}, ...]
      filepath: 输出路径（可选，None 则返回 Workbook 对象）

    返回: Workbook 对象
    """
    wb = Workbook()

    _write_sheet1(wb, output_rows, group_names)
    _write_sheet2(wb, open_ended_cols, df_text)
    _write_sheet3(wb, open_ended_analysis)

    if filepath:
        wb.save(filepath)
    return wb


def _write_sheet1(wb, output_rows, group_names):
    """Sheet 1: 频数频率表"""
    ws = wb.active
    ws.title = '数据分析表'

    # Row 1: 分组名（合并单元格）
    ws.cell(row=1, column=1, value='').border = THIN_BORDER
    ws.cell(row=1, column=2, value='').border = THIN_BORDER
    col = 3
    for gn in group_names:
        ws.merge_cells(start_row=1, start_column=col, end_row=1, end_column=col + 1)
        cell = ws.cell(row=1, column=col, value=gn)
        cell.font = HEADER_FONT
        cell.fill = GROUP_FILL
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER
        ws.cell(row=1, column=col + 1).border = THIN_BORDER
        col += 2

    # Row 2: 计数 / 列数%
    ws.cell(row=2, column=1, value='').border = THIN_BORDER
    ws.cell(row=2, column=2, value='').border = THIN_BORDER
    col = 3
    for gn in group_names:
        for label in ['计数', '列数%']:
            cell = ws.cell(row=2, column=col, value=label)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
            col += 1

    # Data rows
    current_row = 3
    prev_question = None

    for row_data in output_rows:
        question = row_data.get('问题', '')
        option = row_data.get('选项', '')

        is_t2b = option == 'T2B'
        is_b2b = option == 'B2B'
        fill = None
        if is_t2b:
            fill = T2B_FILL
        elif is_b2b:
            fill = B2B_FILL

        # 问题列
        q_cell = ws.cell(row=current_row, column=1)
        if question and question != prev_question:
            q_cell.value = question
            q_cell.font = DATA_FONT
            q_cell.alignment = LEFT_ALIGN
            prev_question = question
        q_cell.border = THIN_BORDER
        if fill:
            q_cell.fill = fill

        # 选项列
        opt_cell = ws.cell(row=current_row, column=2, value=option)
        opt_cell.font = DATA_FONT if not (is_t2b or is_b2b) else Font(
            name='微软雅黑', bold=True, size=10)
        opt_cell.alignment = LEFT_ALIGN
        opt_cell.border = THIN_BORDER
        if fill:
            opt_cell.fill = fill

        # 分组数据
        col = 3
        for gn in group_names:
            cnt = row_data.get(f'{gn}_cnt', 0)
            pct = row_data.get(f'{gn}_pct', 0)

            c1 = ws.cell(row=current_row, column=col, value=cnt)
            c1.font = DATA_FONT
            c1.alignment = CENTER_ALIGN
            c1.border = THIN_BORDER
            if fill:
                c1.fill = fill

            c2 = ws.cell(row=current_row, column=col + 1)
            c2.value = round(pct / 100, 4) if pct > 0 else 0
            c2.font = DATA_FONT
            c2.alignment = CENTER_ALIGN
            c2.border = THIN_BORDER
            c2.number_format = '0.00%'
            if fill:
                c2.fill = fill

            col += 2

        current_row += 1

    # 列宽
    ws.column_dimensions['A'].width = 55
    ws.column_dimensions['B'].width = 42
    for i in range(3, 3 + len(group_names) * 2):
        ws.column_dimensions[get_column_letter(i)].width = 12
    ws.freeze_panes = 'C3'

    # 行高（0.5cm 统一）
    for r in range(1, current_row):
        ws.row_dimensions[r].height = ROW_HEIGHT_PT


def _write_sheet2(wb, open_ended_cols, df_text):
    """Sheet 2: 填空题原话"""
    ws2 = wb.create_sheet('填空题原话')
    for i, h in enumerate(['题目', '序号', '原始回答', '归纳分类'], 1):
        cell = ws2.cell(row=1, column=i, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER_ALIGN
        cell.border = THIN_BORDER

    ws2.column_dimensions['A'].width = 50
    ws2.column_dimensions['B'].width = 8
    ws2.column_dimensions['C'].width = 50
    ws2.column_dimensions['D'].width = 30

    r = 2
    for key, info in open_ended_cols.items():
        col_name = info['col']
        if col_name not in df_text.columns:
            continue
        col_idx = df_text.columns.get_loc(col_name)
        series = df_text.iloc[:, col_idx]
        label = info.get('text', info.get('col', key))

        responses = series.dropna()
        if len(responses) == 0:
            cell = ws2.cell(row=r, column=1, value=label)
            cell.font = DATA_FONT
            ws2.cell(row=r, column=3, value='(无回答)').font = DATA_FONT
            for c in range(1, 5):
                ws2.cell(row=r, column=c).border = THIN_BORDER
            r += 1
            continue

        sample = responses.head(200)
        for idx, (orig_idx, val) in enumerate(sample.items()):
            ws2.cell(row=r, column=1, value=label if idx == 0 else '').font = DATA_FONT
            ws2.cell(row=r, column=2, value=idx + 1).font = DATA_FONT
            ws2.cell(row=r, column=3, value=str(val).strip()[:200]).font = SMALL_FONT
            ws2.cell(row=r, column=3).alignment = Alignment(wrap_text=True)
            for c in range(1, 5):
                ws2.cell(row=r, column=c).border = THIN_BORDER
            r += 1

        r += 1  # 分隔行


def _write_sheet3(wb, open_ended_analysis):
    """Sheet 3: 开放题归纳"""
    ws3 = wb.create_sheet('开放题归纳')
    ws3.column_dimensions['A'].width = 55
    ws3.column_dimensions['B'].width = 18
    ws3.column_dimensions['C'].width = 18
    ws3.column_dimensions['D'].width = 55

    row3 = 1

    def ws3_title(text):
        nonlocal row3
        ws3.cell(row=row3, column=1, value=text).font = TITLE_FONT
        row3 += 2

    def ws3_table_hdr(headers):
        nonlocal row3
        for i, h in enumerate(headers, 1):
            cell = ws3.cell(row=row3, column=i, value=h)
            cell.font = TABLE_HEADER_FONT
            cell.fill = TABLE_HEADER_FILL
            cell.alignment = CENTER_ALIGN
            cell.border = THIN_BORDER
        row3 += 1

    def ws3_row(values, hl=False):
        nonlocal row3
        for i, v in enumerate(values, 1):
            cell = ws3.cell(row=row3, column=i, value=v)
            cell.font = DATA_FONT
            cell.alignment = CENTER_ALIGN if i > 1 else LEFT_ALIGN
            cell.border = THIN_BORDER
            if hl:
                cell.fill = ALT_FILL
        row3 += 1

    if open_ended_analysis:
        for item in open_ended_analysis:
            ws3_title(item['title'])
            if 'note' in item:
                ws3.cell(row=row3, column=1, value=item['note']).font = NOTE_FONT
                row3 += 2

            ws3_table_hdr(item['headers'])
            for i, row_data in enumerate(item['data']):
                ws3_row(row_data, hl=(i % 2 == 0))

            row3 += 1
