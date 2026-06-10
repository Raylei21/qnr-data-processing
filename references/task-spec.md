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
`weight_targets`.

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
  retaining full internal audit calculations.

The workbook includes quality findings, table-consistency checks, group-overlap diagnostics, and
weight diagnostics. Weight diagnostics report coefficient of variation, effective sample size,
efficiency, design effect, extreme-weight warnings, convergence, and target deviations. The engine
does not invent population targets; benchmarks must come from the user or an auditable source.
