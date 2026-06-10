# qnr-data-processing

通用、配置驱动的问卷数据清洗与出数 Skill。

它把用户用自然语言提出的清洗、分组、出表和加权要求，转换成一份可复用的 JSON
任务配置，再通过确定性的 Python 引擎执行。引擎不写死题号、列位置、选项名称或业务
标签，适用于不同问卷项目。

## 能做什么

- 检查 Excel/CSV 的 Sheet、列名、样本量和示例值
- 自动生成问卷任务配置草稿
- 按受访者 ID 对齐数字版和文字版数据
- 执行 AND、OR、NOT 及任意嵌套的清洗和分组规则
- 处理单选、多选、矩阵单选、数值题和开放题
- 输出频数、比例、Base、分组交叉表、NET、T2B/B2B
- 支持每道题独立的统计 Base 和跳题资格条件
- 使用已有权重列出表
- 根据单指标或组合人群目标自动生成 RIM/Raking 权重
- 检查非法选项、互斥冲突、分组重叠和表格一致性
- 输出有效样本量、设计效应、极端权重和收敛诊断
- 默认隐藏受访者 ID、开放题原话和小样本单元格
- 生成完整 Excel 结果和 JSON 审计记录

## 适用范围

适合：

- 在线问卷和用户调研数据清洗
- 描述性频数、比例和分组交叉分析
- 用户画像、品牌、产品和满意度调研
- 配额偏差修正及 RIM/Raking 加权
- 可复核、可重复执行的研究数据交付

不用于替代：

- 显著性检验和复杂抽样方差估计
- MaxDiff、联合分析、因子分析、聚类分析
- 自动定性编码或开放题语义分析
- 人口目标分布的自动推测

## 安装

需要 Python 3.10 或更高版本。

```bash
git clone https://github.com/Raylei21/qnr-data-processing.git
cd qnr-data-processing
python -m pip install -e .
```

成功标志：

```bash
qnr-process --help
```

能够看到 `inspect`、`discover` 和 `run` 三个命令。

## 准备文件

推荐准备：

1. **回答数据**：`.xlsx`、`.xls` 或 `.csv`
2. **问卷文件**：推荐为 Excel，题号、题目和选项分行排列
3. **清洗要求**：例如“年龄小于 18 岁剔除”
4. **分组要求**：例如“最近半年使用过产品 A 的用户”
5. **出数要求**：需要哪些题、NET、Base 和分组
6. **加权目标**：如需要，提供目标人群及其目标占比和来源

如果回答文件同时包含数字版和文字版，建议：

- 两个 Sheet 的样本一一对应
- 使用相同且唯一的受访者 ID
- 列名包含稳定题号，例如 `Q1`、`Q2[选项A]`
- 列名标明题型，例如 `(单选)`、`(多选)`、`(矩阵单选)`

## 五步完成处理

### 第一步：检查数据文件

```bash
python -m qnr_data_processing inspect responses.xlsx \
  --output inventory.json
```

这个命令只读取数据结构，不会修改原文件。

成功标志：返回 `"status": "ok"`，并生成 `inventory.json`。

### 第二步：生成任务配置草稿

```bash
python -m qnr_data_processing discover responses.xlsx \
  --questionnaire questionnaire.xlsx \
  --output task.json
```

程序会识别题号、题型、列映射和问卷选项。

成功标志：返回识别到的题目数量。

请检查所有 `warnings`，特别是：

- 问卷和回答数据的选项文字不同
- 数据中出现问卷未列出的选项
- 存在 `CODE`、`VALUE` 等辅助列

这些警告不会被静默忽略，也会保留到最终审计。

### 第三步：填写清洗、分组和出数规则

最小任务配置示例：

```json
{
  "inputs": {
    "numeric": {
      "path": "responses.xlsx",
      "sheet": "数字版",
      "id_column": "样本ID"
    },
    "text": {
      "path": "responses.xlsx",
      "sheet": "文字版",
      "id_column": "样本ID"
    }
  },
  "questions": [
    {
      "id": "Q1",
      "type": "single",
      "text": "性别",
      "base": "answered",
      "columns": [{"numeric": "Q1", "text": "Q1"}],
      "options": ["男", "女"]
    },
    {
      "id": "Q2",
      "type": "multi",
      "text": "使用过的平台",
      "base": "any_selected",
      "columns": [
        {
          "numeric": "Q2_A",
          "text": "Q2_A",
          "label": "平台A",
          "selected_values": [1, "1", "是"]
        },
        {
          "numeric": "Q2_NONE",
          "text": "Q2_NONE",
          "label": "以上都没有",
          "selected_values": [1, "1", "是"],
          "exclusive": true
        }
      ]
    }
  ],
  "cleaning": [
    {
      "name": "剔除未成年人",
      "rule": {
        "column": "年龄",
        "source": "numeric",
        "op": "lt",
        "value": 18
      }
    }
  ],
  "groups": [
    {
      "name": "平台A用户",
      "rule": {
        "question": "Q2",
        "option": "平台A",
        "op": "selected"
      }
    }
  ],
  "privacy": {
    "include_respondent_ids": false,
    "include_open_responses": false,
    "min_cell_size": 5
  },
  "output": {
    "table_path": "output/questionnaire_tables.xlsx",
    "audit_path": "output/audit.json",
    "cleaned_path": "output/cleaned.xlsx"
  }
}
```

详细字段见：

- [任务配置说明](references/task-spec.md)
- [规则语法说明](references/rules.md)

### 第四步：只校验，不写结果

```bash
python -m qnr_data_processing run \
  --config task.json \
  --validate-only
```

重点检查：

- 输入和清洗后样本量
- 每条清洗规则删除的人数
- 各分组 Base
- 非法选项和互斥冲突
- 分组重叠和未归属样本
- 表格一致性
- 加权是否收敛
- 有效样本量和极端权重

成功标志：返回 `"status": "ok"`，且没有未处理的错误或重要警告。

### 第五步：正式出表

```bash
python -m qnr_data_processing run --config task.json
```

成功标志：返回 `"status": "ok"`，并列出生成的 Excel 和审计 JSON 路径。

## 清洗与分组规则

规则可以直接引用列：

```json
{
  "column": "年龄",
  "source": "numeric",
  "op": "gte",
  "value": 18
}
```

也可以引用题目和选项：

```json
{
  "question": "Q2",
  "option": "平台A",
  "op": "selected"
}
```

组合规则：

```json
{
  "all": [
    {"column": "城市等级", "source": "text", "op": "eq", "value": "一线"},
    {"column": "性别", "source": "text", "op": "eq", "value": "男"}
  ]
}
```

支持的逻辑和比较操作请查看 [规则语法说明](references/rules.md)。

## 自动加权

### 单指标和组合指标

每个目标由“人群规则 + 目标占比”组成。目标可以是：

- 男性占 55%
- 25–34 岁占 35%
- 一线城市男性占 30%
- 使用产品 A 且高频使用的用户占 20%

组合目标使用与清洗、分组相同的嵌套规则。

```json
{
  "weight": {
    "method": "raking",
    "targets": [
      {
        "name": "男性",
        "percent": 55,
        "source": "2026年度目标用户结构",
        "base": {
          "column": "性别",
          "source": "text",
          "op": "not_missing"
        },
        "rule": {
          "column": "性别",
          "source": "text",
          "op": "eq",
          "value": "男"
        }
      },
      {
        "name": "一线男性",
        "percent": 30,
        "source": "项目配额要求",
        "rule": {
          "all": [
            {
              "column": "城市等级",
              "source": "text",
              "op": "eq",
              "value": "一线"
            },
            {
              "column": "性别",
              "source": "text",
              "op": "eq",
              "value": "男"
            }
          ]
        }
      }
    ],
    "tolerance": 0.0001,
    "max_iterations": 200,
    "trim": {"min": 0.3, "max": 3.0},
    "output_column": "final_weight"
  }
}
```

注意：

- `percent: 30` 表示该人群的目标占比是 30%，不是给样本乘以 0.3
- 指标存在缺失值时，应使用 `base` 排除缺失或不符合资格的样本
- 目标比例必须来自用户或可审计来源，程序不会自动猜测
- 子集目标不能高于母集目标
- 互斥目标的比例合计不能超过 100%
- 目标无样本、互相冲突或无法收敛时，程序会停止

### 使用已有权重

如果数据中已经有权重列：

```json
{
  "weight": {
    "source": "numeric",
    "column": "weight"
  }
}
```

## 输出文件说明

结果 Excel 可能包含：

| Sheet | 内容 |
|---|---|
| `tables_long` | 标准长表，包含未加权和加权结果 |
| `tables_wide` | 各分组横向对比表 |
| `tables_weighted` | 配置非单位权重时生成的加权横表 |
| `open_responses` | 明确授权后输出的开放题逐条原话 |
| `cleaning_audit` | 每条清洗规则的删除人数 |
| `group_bases` | 各分组未加权及加权 Base |
| `quality_checks` | 清洗后仍存在的数据质量问题 |
| `quality_before_cleaning` | 清洗前发现的数据质量问题 |
| `table_checks` | 频数和 Base 的一致性检查 |
| `group_membership` | 分组重叠及未归属样本 |
| `weight_diagnostics` | 权重效率、设计效应和极端权重 |
| `weight_targets` | 目标占比、调整前后比例及偏差 |

审计 JSON 包含同样的关键诊断，方便自动化检查和项目复核。

如果配置了 `cleaned_path`，清洗后的数字版和文字版会写入新文件；自动生成权重时，
文件中会增加 `final_weight` 列。

## 隐私与安全

默认配置：

- 不输出受访者 ID
- 不输出开放题逐条原话
- 不覆盖原始数据
- 将结果写入新路径
- 对小于 `min_cell_size` 的单元格同时隐藏未加权和加权结果
- 防止以 `=`、`+`、`-`、`@` 开头的文本被 Excel 当成公式执行

仅在确认有权限且确实需要时启用：

```json
{
  "privacy": {
    "include_respondent_ids": true,
    "include_open_responses": true
  }
}
```

## 常见问题

### 找不到列

检查 `task.json` 中的列名是否与回答文件完全一致。不要依赖列的位置。

### 数字版和文字版无法对齐

确认两个 Sheet 配置了正确的 `id_column`，并且 ID 唯一、无空值、集合一致。

### 单选选项合计不等于 Base

通常表示：

- 问卷和回答数据使用了不同版本的选项文字
- 数据中存在问卷未配置的值
- 题目的统计 Base 配置错误

先检查 `quality_checks` 和 `table_checks`，不要直接忽略。

### 权重无法收敛

检查：

- 目标人群是否有实际样本
- 相同人群是否配置了不同目标
- 子集目标是否高于母集目标
- 互斥目标的比例是否超过 100%
- 权重截尾范围是否过窄
- 指标缺失值是否配置了正确 Base

### 为什么开放题工作表是空的

开放题原话可能包含姓名、手机号或公司等个人信息，因此默认不导出。确认授权后设置：

```json
{
  "privacy": {
    "include_open_responses": true
  }
}
```

## Agent Skill

根目录的 [SKILL.md](SKILL.md) 定义 Agent 的操作流程。源码安装后可以直接使用 Python
命令，也可以将仓库打包为 Agent Skill。

当前开发版本：`2.2.0`

## 验证

```bash
python -m pytest
```

当前包含 25 项自动测试，并已使用真实问卷样例完成回归，包括：

- 单选、多选、矩阵题和 NET
- 自定义 Base 和缺失值逻辑
- 单指标与组合人群加权
- 权重收敛、冲突检测和截尾
- 数据质量及表格一致性
- 小样本保护和开放题隐私

## 许可证

当前仓库尚未声明开源许可证。如需公开分发或允许第三方复用，建议补充明确的
`LICENSE` 文件。
