# Structured Rules

Rules are JSON objects. A rule is either a logical node or a condition.

## Logical Nodes

```json
{"all": [RULE, RULE]}
{"any": [RULE, RULE]}
{"not": RULE}
```

Nesting preserves parentheses. For `(A AND B) OR C`, use:

```json
{"any": [{"all": [A, B]}, C]}
```

## Column Selection

Use exactly one selector:

```json
{"column": "Q1", "source": "numeric", "op": "eq", "value": 1}
{"columns": ["Q2_1", "Q2_2"], "source": "numeric", "op": "selected"}
{"column_regex": "^Q2_", "source": "numeric", "op": "selected"}
{"question": "Q2", "option": "微信", "source": "numeric", "op": "selected"}
```

`source` is `numeric` or `text`; default is `numeric`.

When a selector resolves to several columns, `column_logic` controls combination:

- `any`: at least one column matches.
- `all`: every column matches.

## Operators

- Equality: `eq`, `neq`, `in`, `not_in`
- Numeric: `gt`, `gte`, `lt`, `lte`, `between`
- Text: `contains`, `not_contains`, `regex`
- Empty values: `missing`, `not_missing`
- Multiple choice: `selected`, `not_selected`

Negative operators exclude missing values by default. This prevents skipped respondents from being
classified as “not selected” or “not equal.” Include missing values only when explicitly intended:

```json
{"column": "Q8", "op": "neq", "value": 1, "missing_policy": "include"}
```

Examples:

```json
{"column": "age", "op": "between", "value": [18, 35]}
{"column": "comment", "source": "text", "op": "contains", "value": "价格"}
{"question": "Q5", "option": "其他", "op": "selected", "selected_values": [1]}
```

For a multiple-choice question encoded as a single delimiter-joined column (see `delimiter` in the
task specification), `question` + `option` + `selected` matches the split tokens instead of one-hot
columns. `option` may name the option's `value` or `label`.

Do not translate a rule if its field, coding, or precedence is uncertain. Ask for clarification.

## Quality Check Patterns

Quality checks are named violation rules. A respondent matching the rule is flagged, not silently
deleted.

```json
{
  "quality_checks": [
    {
      "name": "答题时长过短",
      "severity": "warning",
      "rule": {"column": "duration_seconds", "op": "lt", "value": 180}
    },
    {
      "name": "跳题逻辑违反",
      "severity": "error",
      "rule": {
        "all": [
          {"question": "Q2", "option": "虎扑", "op": "not_selected"},
          {"question": "Q3", "option": "虎扑", "op": "not_missing"}
        ]
      }
    },
    {
      "name": "注意力检测失败",
      "severity": "error",
      "rule": {"column": "attention_check", "op": "neq", "value": 3}
    }
  ]
}
```
