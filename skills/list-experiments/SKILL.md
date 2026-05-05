---
name: list-experiments
description: Read test_definitions and produce the experiment evaluation queue. Use when the orchestrator needs the canonical list of experiments-to-evaluate. Invoked by orchestrator-workflow.
---

# list-experiments

## Inputs
- `mode`: `"auto"` (filter `evaluate_automatically=TRUE`) | `"explicit"` (single `alternate_name`) | `"since"` (`start_date >= YYYY-MM-DD`)
- `alternate_name`: required when `mode=explicit`
- `since_date`: required when `mode=since`

## Steps

1. Validate inputs. Refuse if mode is unknown.
2. Validate schema:
   - Run `python -c "from scripts.lib.schema_drift import validate_required_columns; validate_required_columns('fixtures/test_definitions.schema.json', ['alternate_name','experiment_name','start_date','end_date','use_deal_category_split','use_misc_split','evaluate_automatically'])"`
   - On failure → fail loudly.
3. Build the bq command:
   - Read query `list_experiments` from `scripts/lib/bq_queries.sql`.
   - Set `--parameter='auto_only:BOOL:true'` if `mode=auto`, else `false`.
   - Set `--parameter='explicit_name:STRING:<alternate_name>'` if `mode=explicit`, else empty.
   - For `mode=since`, run `auto_only=false, explicit_name=` and post-filter rows in Python.
4. Run via `bq query --use_legacy_sql=false --format=json --max_rows=500`.
5. Parse JSON, validate each row has all 8 columns, classify:
   - `is_in_flight = (end_date IS NULL OR end_date == '')`
   - `seo_eligible = (start_date <= today - 7)` — even before checking test_deals; will be re-checked by seo-guardrails
6. Emit queue as JSON to stdout: `[{"alternate_name":..., "experiment_name":..., "start_date":..., "end_date":..., "use_deal_category_split":..., "use_misc_split":..., "evaluate_automatically":..., "is_in_flight":..., "seo_eligible":...}, ...]`

## Tool contract

- Read-only BQ via `bq` CLI. Never DDL/DML, never MCP.
- All SQL passes through `scripts.lib.tool_contract.assert_select_only` before execution.

## Failure modes
- Schema drift → hard fail with column-list diff.
- bq query non-zero exit → propagate stderr to caller.
