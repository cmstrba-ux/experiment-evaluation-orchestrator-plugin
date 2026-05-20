---
name: list-experiments
description: Read test_definitions and produce the experiment evaluation queue. Use when the orchestrator needs the canonical list of experiments-to-evaluate. Invoked by orchestrator-workflow.
---

# list-experiments

## Inputs
- `mode`: `"auto"` (filter `evaluate_automatically=TRUE`) | `"explicit"` (single `alternate_name`) | `"since"` (`start_date >= YYYY-MM-DD`)
- `alternate_name`: required when `mode=explicit`
- `since_date`: required when `mode=since`
- `out_path`: optional. When the caller passes one, write the queue JSON to that path **in addition** to emitting it on stdout. The orchestrator-workflow always passes `<run_dir>/queue.json` (top level, NOT under `raw/`) because render.py reads exactly that path to compute the SEO TOO EARLY countdown.

## Steps

1. Validate inputs. Refuse if mode is unknown.
2. Validate schema:
   - Run `python -c "from scripts.lib.schema_drift import validate_required_columns; validate_required_columns('fixtures/test_definitions.schema.json', ['alternate_name','experiment_name','start_date','end_date','evaluate_seo_since','use_deal_category_split','use_misc_split','evaluate_automatically'])"`
   - On failure → fail loudly.
3. Build the bq command:
   - Read query `list_experiments` from `scripts/lib/bq_queries.sql`.
   - Set `--parameter='auto_only:BOOL:true'` if `mode=auto`, else `false`.
   - Set `--parameter='explicit_name:STRING:<alternate_name>'` if `mode=explicit`, else empty.
   - For `mode=since`, run `auto_only=false, explicit_name=` and post-filter rows in Python.
4. Run via `bq query --use_legacy_sql=false --format=json --max_rows=500`.
5. Parse JSON, validate each row has all 9 columns, classify:
   - `is_in_flight = (end_date IS NULL OR end_date == '')`
   - `seo_eligible = (evaluate_seo_since <= today - 14)` — even before checking test_deals; will be re-checked by seo-guardrails. Uses `evaluate_seo_since` (not `start_date`) because the AB window can begin earlier than the SEO release. The 14-day cushion (vs the previous 7) gives the upstream SEO pipeline enough post-period days for a meaningful DiD before the orchestrator gates a run.
6. Emit queue as JSON to stdout: `[{"alternate_name":..., "experiment_name":..., "start_date":..., "end_date":..., "evaluate_seo_since":..., "use_deal_category_split":..., "use_misc_split":..., "evaluate_automatically":..., "is_in_flight":..., "seo_eligible":...}, ...]`
7. If `out_path` was supplied, write the same JSON to that file path (UTF-8, no BOM). The orchestrator-workflow always passes `<run_dir>/queue.json` — placing it under `<run_dir>/raw/` instead silently breaks render.py's SEO TOO EARLY merge (the lookup is hardcoded to the top-level path; the merge no-ops without warning and SEO tiles render `n/a` instead of `TOO EARLY — X/14 days`).

`evaluate_seo_since` is the SEO release_date passed to `run-seo-evaluation` (via `--release-date`). It is sourced from `test_definitions.evaluate_seo_since`; when that column is blank/null in the source row, the SQL falls back to `start_date` so legacy rows keep working.

## Tool contract

- Read-only BQ via `bq` CLI. Never DDL/DML, never MCP.
- All SQL passes through `scripts.lib.tool_contract.assert_select_only` before execution.

## Failure modes
- Schema drift → hard fail with column-list diff.
- bq query non-zero exit → propagate stderr to caller.
