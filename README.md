# qnr-data-processing

通用、配置驱动的问卷数据清洗与出数 Skill。

它把用户用自然语言提出的清洗、分组、出表和加权要求，转换成一份可复用的 JSON
任务配置，再通过确定性的 Python 引擎执行。引擎不写死题号、列位置、选项名称或业务
标签，适用于不同问卷项目。

> 第一次做问卷出数？先看 [新同学操作指南](docs/quickstart-guide.md)，
> 一步步告诉你该准备什么、原始数据给哪个版本、以及怎么跟着走完整个出数流程。

## 能做什么

- 检查 Excel/CSV 的 Sheet、列名、样本量和示例值
- 自动生成问卷任务配置草稿
- 按受访者 ID 对齐数字版和文字版数据
- 执行 AND、OR、NOT 及任意嵌套的清洗和分组规则
- 处理单选、多选、矩阵单选、数值题和开放题
- 按分隔符（如 `┋`）自动拆分单列多选，识别「(跳过)」和「others〖原话〗」
- 支持去重（按 key 保留最大/最小值）和归一化（去空格/去尾部符号/替换）清洗
- 输出频数、比例、Base、分组交叉表、NET、T2B/B2B
- 支持每道题独立的统计 Base 和跳题资格条件
- 声明式互斥分群（segments），自动生成派生列和分组列
- 内置跳题一致性检查（应跳过却作答 / 应作答却跳过）
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

### 去重与归一化清洗

除按规则删除外，清洗步骤还支持两种声明式操作：

```json
{
  "cleaning": [
    {
      "name": "同一客户保留作答时长最长的一条",
      "type": "dedup",
      "key": "customer_id",
      "keep": "max",
      "on": "duration_seconds",
      "source": "numeric"
    },
    {
      "name": "去掉 Q9 末尾句号",
      "type": "normalize",
      "column": "Q9",
      "source": "text",
      "op": "rstrip",
      "value": "."
    }
  ]
}
```

- `dedup`：按 `key` 分组，保留 `on` 列取 `max` 或 `min` 的那一条，删除其余重复样本。`on` 必须是数字列。
- `normalize`：原地改写一列（不删除样本），`op` 支持 `strip`、`lstrip`、`rstrip`、
  `lower`、`replace`（`replace` 需要 `value` 作为被替换文本、`replacement` 作为替换文本）。
  默认作用于 `source: "text"`。

## 单列分隔符多选

当多选答案被导出为单列、用分隔符（如 `┋`）连接时，无需手工拆分，直接在题目列上声明
`delimiter` 即可：

```json
{
  "id": "Q2",
  "type": "multi",
  "text": "吸引你下载的原因",
  "base": "any_selected",
  "columns": [
    {
      "text": "q02",
      "delimiter": "┋",
      "options": ["价格实惠", "款式多样", "others, please specify"]
    }
  ]
}
```

引擎会自动：

- 按 `delimiter` 拆分每个单元格，逐选项判断是否选中；
- 把 `(跳过)` 视为跳题，既不计入任何选项，也不计入 `any_selected` Base；
- 把 `others, please specify〖原话〗` 识别为「others」选项已选，同时在授权
  `include_open_responses` 时把 `〖原话〗` 逐条导出到 `open_responses`；
- 选项中的 `exclusive` 项与其他选项同时选择时，会进入质量检查。

`options` 可为字符串或 `{"value", "label", "exclusive"}` 对象；省略时按数据中出现的
选项文本自动生成。

## 互斥分群（segments）

当需要把样本按互斥规则切成 L1/L2/L3 这类分层时，用声明式 `segments`，而不是手工写派生列：

```json
{
  "segments": [
    {
      "name": "购买力分层",
      "column": "purchase_power",
      "mutually_exclusive": true,
      "residual": "L3",
      "branches": [
        {"value": "L1", "label": "高购买力", "rule": {"all": [{"column": "income", "op": "gte", "value": 6}, {"column": "comfort", "op": "lte", "value": 2}]}},
        {"value": "L2", "label": "中等购买力", "rule": {"column": "income", "op": "between", "value": [2, 5]}}
      ]
    }
  ]
}
```

- 分支按顺序求值，首个命中分支归属该样本。
- `mutually_exclusive: true`（默认）会校验分支规则互不重叠，重叠即报错。
- `residual`：未命中任何分支的样本归属值；写 `"Exclude"`（默认）则排除在分群之外。
- 每个分支自动生成一个同名分组列（`L1`/`L2`/`L3`），并写入一个可被规则引用的派生列
  `column`（默认等于 `name`）。

## 跳题一致性检查（piping）

声明跳题逻辑后，引擎自动标记两类违反：

```json
{
  "piping": [
    {
      "name": "Q6 仅对 Q5 选失望者显示",
      "gate": {"question": "Q5", "option": "失望", "op": "selected"},
      "target": "Q6",
      "skip_values": ["(跳过)"]
    }
  ]
}
```

- 应跳过却作答：`gate` 之外却仍在 `target` 作答的样本。
- 应作答却跳过：`gate` 之内但 `target` 为空或为 `skip_values` 的样本。

检查结果进入 `quality_checks`，只标记、不自动删除。

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
| `tables_wide` | 各分组横向对比表（列名为 `{分组}_count/_base/_percent`） |
| `tables_weighted` | 配置非单位权重时生成的加权横表（列名为 `{分组}_weighted_count/_base/_percent`） |
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
- 对小于 `min_cell_size` 的单元格同时隐藏未加权和加权结果（默认 `0`，即不隐藏）
- 防止以 `=`、`+`、`-`、`@` 开头的文本被 Excel 当成公式执行

`min_cell_size` 默认是 `0`，表示**不做小样本隐藏**。它只作用于 `tables_long`、
`tables_wide`、`tables_weighted` 这些出表单元格；`cleaning_audit`、`group_bases` 和
审计 JSON 始终保留完整计数，便于复核。需要隐藏时显式设置，例如 `{"min_cell_size": 5}`。

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

## 美化版报表

出表后可额外生成一份排版好的「一题一块」报表，方便直接汇报：

```bash
python -m qnr_data_processing report \
  --tables output/questionnaire_tables.xlsx \
  --config task.json \
  --output output/数据分析表_美化版.xlsx \
  --title "数据分析表"
```

加 `--weighted` 则读取 `tables_weighted`，生成加权版美化报表：

```bash
python -m qnr_data_processing report \
  --tables output/questionnaire_tables.xlsx \
  --config task.json \
  --weighted \
  --output output/数据分析表_加权_美化版.xlsx
```

排版规则：

- 每道题一块：题干做通栏标题（多选题标「（多选）」、开放题标「（开放题）」）
- 题干下方插入一行 `Base`，列出各分组在这道题的样本量（分母）
- 每个分组两列：`频数` 与 `频率%`
- `T2B` / `B2B` 等合并行自动高亮

分组列由 `tables_wide` 动态识别，无需写死。

## Agent Skill

根目录的 [SKILL.md](SKILL.md) 定义 Agent 的操作流程。源码安装后可以直接使用 Python
命令，也可以将仓库打包为 Agent Skill。

当前开发版本：`2.3.0`

## 验证

```bash
python -m pytest
```

当前包含 38 项自动测试，并已使用真实问卷样例完成回归，包括：

- 单选、多选、矩阵题和 NET
- 自定义 Base 和缺失值逻辑
- 单指标与组合人群加权
- 权重收敛、冲突检测和截尾
- 去重与归一化清洗、分隔符多选、互斥分群、跳题一致性检查
- 数据质量及表格一致性
- 小样本保护和开放题隐私

## 许可证

当前仓库尚未声明开源许可证。如需公开分发或允许第三方复用，建议补充明确的
`LICENSE` 文件。
