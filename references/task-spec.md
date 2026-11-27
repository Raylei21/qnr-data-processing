# Task Specification

The engine accepts UTF-8 JSON. Paths are resolved relative to the task file.

## Example

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
      "options": [
        {"value": "男", "label": "男"},
        {"value": "女", "label": "女"}
      ]
    },
    {
      "id": "Q2",
      "type": "multi",
      "text": "使用过的平台",
      "base": "any_answered",
      "selected_values": [1, "1", "是"],
      "columns": [
        {"numeric": "Q2_1", "text": "Q2_1", "label": "微信"},
        {
          "numeric": "Q2_2",
          "text": "Q2_2",
          "label": "以上都没有",
          "exclusive": true
        }
      ]
    }
  ],
  "discovery_warnings": [
    "Q1: 问卷选项“男性”按数据标签“男”出数"
  ],
  "cleaning": [
    {
      "name": "剔除未成年人",
      "rule": {"column": "年龄", "op": "lt", "value": 18}
    }
  ],
  "groups": [
    {
      "name": "微信用户",
      "rule": {"question": "Q2", "option": "微信", "op": "selected"}
    }
  ],
  "weight": {
    "method": "raking",
    "targets": [
      {
        "name": "25-34岁",
        "percent": 35,
        "source": "2026年度目标用户结构",
        "base": {
          "column": "年龄段",
          "source": "text",
          "op": "not_missing"
        },
        "rule": {
          "column": "年龄段",
          "source": "text",
          "op": "eq",
          "value": "25-34岁"
        }
      },
      {
        "name": "一线男性",
        "percent": 30,
        "rule": {
          "all": [
            {"column": "城市等级", "source": "text", "op": "eq", "value": "一线"},
            {"column": "性别", "source": "text", "op": "eq", "value": "男"}
          ]
        }
      }
    ],
    "trim": {"min": 0.3, "max": 3.0},
    "output_column": "final_weight"
  },
  "quality_checks": [
    {
      "name": "答题时长过短",
      "severity": "warning",
      "rule": {"column": "duration_seconds", "op": "lt", "value": 180}
    }
  ],
  "privacy": {
    "include_respondent_ids": false,
    "include_open_responses": false,
    "min_cell_size": 5
  },
  "output": {
    "table_path": "output/tables.xlsx",
    "audit_path": "output/audit.json",
    "cleaned_path": "output/cleaned.xlsx"
  }
}
```

## Question Fields

- `id`: unique stable identifier; it need not start with Q.
- `type`: `single`, `multi`, `matrix_single`, `numeric`, or `open`.
- `text`: display title.
- `columns`: explicit source columns. Each item may contain `numeric`, `text`, `label`,
  `option`, `code`, and `selected_values`.
- `options`: optional ordered values for single-choice questions. If omitted, observed text values
  are used.
- `base`: multiple-choice denominator:
  - `all`
  - `any_answered`
  - `any_selected`
  - a structured rule object
- For `single`, `matrix_single`, `numeric`, and `open`, `base` may be:
  - `answered`
  - `all`
  - a structured eligibility rule
- `nets`: optional summary rows. Each item contains `name` plus either:
  - `values`: values combined within each current single/matrix column.
  - `rule`: a structured rule for cross-column or custom summaries.

### Delimiter-joined multiple choice

When a multiple-choice question is exported as one column whose selected options are joined by a
delimiter, declare `delimiter` on the column instead of a one-hot column per option:

```json
{
  "id": "Q2",
  "type": "multi",
  "text": "吸引原因",
  "base": "any_selected",
  "columns": [
    {
      "text": "q02",
      "delimiter": "┋",
      "options": [
        {"value": "价格实惠", "label": "价格实惠"},
        {"value": "others, please specify", "label": "其他"}
      ],
      "skip_values": ["(跳过)"]
    }
  ]
}
```

`options` entries may be strings or `{"value", "label", "exclusive"}` objects; when omitted, the
engine derives them from observed tokens. `skip_values` defaults to `["(跳过)"]`; a cell containing
only skip values is treated as skipped (not answered, not selected). Inline verbatims written as
`option〖原文〗` are counted as that option and, when `privacy.include_open_responses` is true, are
exported to `open_responses`.

## Cleaning

Cleaning entries support three forms. The default is a named delete rule:

```json
{"name": "剔除未成年人", "rule": {"column": "年龄", "op": "lt", "value": 18}}
```

`dedup` keeps one row per key by an extreme value of a numeric `on` column:

```json
{"name": "去重", "type": "dedup", "key": "customer_id", "keep": "max", "on": "duration_seconds"}
```

`normalize` rewrites a column in place without deleting rows:

```json
{"name": "去句号", "type": "normalize", "column": "Q9", "source": "text", "op": "rstrip", "value": "."}
```

Normalize `op` values: `strip`, `lstrip`, `rstrip`, `lower`, `replace` (`replace` also needs
`replacement`).

## Segments

Segments assign respondents to mutually exclusive categories and generate both a derived column
and one group column per branch:

```json
{
  "segments": [
    {
      "name": "购买力分层",
      "column": "purchase_power",
      "mutually_exclusive": true,
      "residual": "L3",
      "branches": [
        {"value": "L1", "label": "高购买力", "rule": {"column": "income", "op": "gte", "value": 6}},
        {"value": "L2", "label": "中等购买力", "rule": {"column": "income", "op": "between", "value": [2, 5]}}
      ]
    }
  ]
}
```

Branches are evaluated in order and the first match wins. `mutually_exclusive` (default `true`)
raises an error if any respondent matches more than one branch. `residual` assigns unmatched
respondents to a value (`"L3"`) or excludes them (`"Exclude"`, the default). The derived column is
named `column` (default `name`) and can be referenced by regular `column` rules.

## Piping

Declare skip logic to have the engine flag both directions of a violation:

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

The check flags "应跳过却作答" (answered outside the gate) and "应作答却跳过" (empty or skipped
inside the gate). Findings appear in `quality_checks` and never auto-delete.

## Output

`tables_long` contains:

- question ID and wording
- matrix subitem
- option or net
- group
- count
- base
- percent

The workbook also contains cleaning and group-base audit sheets. Respondent IDs are hidden by
default; set `privacy.include_respondent_ids` only when respondent-level traceability is authorized.

`weight` is optional. It supports two modes:

- Existing column: `{"source": "numeric", "column": "weight"}`.
- Generated raking weight: provide `targets`, each with `name`, `rule`, and either `percent`
  (`30`) or `target` (`0.30`).

Each target is an independent benchmark. Its rule may use any supported nested logic, including
combined cells such as city tier AND gender. Multiple overlapping targets are adjusted iteratively.
`percent` and `target` mean the desired population share within the target's Base; they are not
sample-level multipliers.

Generated-weight options:

- Target `base`: optional eligibility rule. Use it whenever missing, skipped, or ineligible cases
  must be excluded from the benchmark denominator.
- Target `source` / `notes`: optional provenance fields copied into the audit.
- `base_weight`: optional existing weight column used as the starting weight.
- `tolerance`: maximum accepted absolute share deviation; default `0.0001`.
- `max_iterations`: default `200`.
- `trim.min` / `trim.max`: optional bounds after normalizing weights to mean 1.
- `allow_non_convergence`: default `false`; keep `false` for production research.
- `output_column`: generated column name in the cleaned workbook; default `final_weight`.

The workbook adds `tables_weighted`, `weight_diagnostics`, and, for generated weights,
`weight_targets`. `tables_wide` columns are named `{group}_count` / `{group}_base` /
`{group}_percent`; `tables_weighted` columns are named `{group}_weighted_count` /
`{group}_weighted_base` / `{group}_weighted_percent`. The `report --weighted` flag builds the
beautified report from the weighted sheet.

## Research Audit Fields

- `quality_checks`: named rules that identify suspect respondents. Findings are reported but are
  not automatically deleted.
- `discovery_warnings`: warnings produced while reconciling questionnaire metadata, helper
  columns, and observed option labels. They are preserved in the final audit.
- Mark a multiple-choice column with `"exclusive": true` to detect “none of these” conflicts.
- `privacy.include_respondent_ids`: default `false`; controls respondent IDs in audits and open
  responses.
- `privacy.include_open_responses`: default `false`; respondent-level verbatims require explicit
  opt-in because the text itself may contain personal information.
- `privacy.min_cell_size`: suppresses published counts and percentages below the threshold while
  retaining full internal audit calculations. Default `0` (no suppression). It affects only the
  published table sheets, never the audit JSON or audit sheets.

The workbook includes quality findings, table-consistency checks, group-overlap diagnostics, and
weight diagnostics. Weight diagnostics report coefficient of variation, effective sample size,
efficiency, design effect, extreme-weight warnings, convergence, and target deviations. The engine
does not invent population targets; benchmarks must come from the user or an auditable source.
