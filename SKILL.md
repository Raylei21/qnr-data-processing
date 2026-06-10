---
name: qnr-data-processing
description: Inspect, clean, validate, tabulate, and export questionnaire or survey response data from Excel/CSV using explicit structured rules and auditable denominators. Use when Codex needs to process questionnaire data, translate user-written cleaning/grouping/tabulation requirements into a task JSON, produce frequency or percentage tables, handle single-choice/multiple-choice/matrix/open-ended questions, or verify that survey outputs are reproducible and free of survey-specific hardcoding.
---

# Questionnaire Data Processing

Use the bundled Python engine. Treat user language as requirements to compile into an explicit
JSON task specification; never pass ambiguous natural language directly to data operations.

## Workflow

1. Identify the questionnaire file, response file, desired cleaning rules, groups, table rules,
   output path, whether numeric/text response versions exist, skip logic, mutually exclusive
   options, weighting requirements, and privacy restrictions.
2. Run the inspector before writing rules:

   ```bash
   python -m qnr_data_processing inspect INPUT.xlsx --output inventory.json
   ```

3. Read `inventory.json` and inspect relevant headers and example values. If question wording,
   option coding, respondent ID, multiple-choice encoding, or denominator remains ambiguous,
   stop and ask the user for a questionnaire/codebook or a small desensitized sample.
4. For exports whose columns include stable question IDs and type markers, create a draft:

   ```bash
   python -m qnr_data_processing discover RESPONSES.xlsx \
     --questionnaire QUESTIONNAIRE.xlsx --output task.json
   ```

5. Review every discovery warning, especially questionnaire/data option-label differences and
   CODE/VALUE helper columns. Discovery uses observed response labels for calculation so spelling
   differences do not lose counts, but every reconciliation warning still requires review. Create
   or complete the task JSON following [references/task-spec.md](references/task-spec.md).
   Explicitly map every included question to real columns. Never infer by column position.
6. Translate requirements into the structured rule tree described in
   [references/rules.md](references/rules.md). Preserve parentheses and AND/OR/NOT semantics.
7. Validate without writing output:

   ```bash
   python -m qnr_data_processing run --config task.json --validate-only
   ```

8. When the user supplies population benchmarks, compile each benchmark into `weight.targets`.
   Every target is an explicit rule plus a percentage, so it can represent one category such as
   “male 55%” or a combined cell such as “tier-1 AND male 30%”. Use raking for multiple overlapping
   targets. Treat the percentage as a target population share, never as a direct multiplier.
   Confirm that each target has observed respondents. When the weighting variable has missing or
   ineligible responses, add an explicit target `base` so missing cases are not treated as the
   complement category.
9. Review sample counts, cleaning counts, quality findings, invalid codes, exclusive-option
   conflicts, group overlap, group bases, table consistency, and weight diagnostics. Resolve every
   error and material warning before continuing.
10. Execute:

   ```bash
   python -m qnr_data_processing run --config task.json
   ```

11. Check the generated audit JSON and Excel sheets. Report input N, cleaned N, each cleaning
   rule's removed N, quality findings, group bases, weight efficiency, output paths, privacy
   suppression, and any limitations to the user.

## Safety Rules

- Never silently skip an invalid rule, missing column, duplicate respondent ID, or unmatched
  sample. Fix the configuration or ask the user.
- Never delete source files or overwrite them. Write cleaned data and reports to new paths.
- Fuzzy matching may only propose a discovery-time label reconciliation. It must preserve the
  observed data label, emit an audit warning, and never silently decide a cleaning, grouping,
  denominator, NET, or coding rule.
- Require an explicit denominator for multiple-choice questions when `any_answered` is not the
  intended base.
- Keep overlapping groups overlapping unless the user explicitly defines priority/exclusivity.
- Do not claim semantic analysis of open text from simple keyword counts. Label it keyword coding.
- Treat `neq`, `not_in`, `not_contains`, and `not_selected` as excluding missing/skip values unless
  the task explicitly sets `missing_policy: include`.
- Do not call the engine a MaxDiff, conjoint, factor-analysis, clustering, significance-testing,
  or qualitative-coding engine. Use specialist statistical workflows for those analyses.
- Default to hiding respondent IDs. Include IDs only when the user explicitly needs an auditable
  respondent-level file and is authorized to receive it.
- Default to not exporting respondent-level open-ended verbatims. Set
  `privacy.include_open_responses: true` only after confirming the user needs them and understands
  that verbatims may contain direct identifiers.
- Never invent population benchmarks. Weight targets must come from the user or an identified,
  auditable source.
- Record benchmark `source` and `notes` when available.
- Never report generated weights as valid when raking did not converge. Review target deviations,
  trimming, effective N, design effect, and extreme-weight warnings.

## Included Resources

- `references/task-spec.md`: complete task JSON fields and example.
- `references/rules.md`: supported logical and comparison operators.
- `scripts/create_task_template.py`: generate a starter JSON from an inventory.
