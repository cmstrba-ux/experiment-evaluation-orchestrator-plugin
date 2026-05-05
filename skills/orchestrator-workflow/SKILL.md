---
name: orchestrator-workflow
description: Top-level workflow for evaluating a queue of experiments. Reads test_definitions, dispatches AB / SEO / deal-charts subagents in parallel (Sonnet, capped ~6 in flight), assembles the combined HTML report. Invoked by the /evaluate-reviews-experiments slash command.
---

# orchestrator-workflow

## Inputs
- `mode`: `auto` | `explicit <alternate_name>` | `since <YYYY-MM-DD>` | `rerender <run-id>`
- `out_root`: optional override for output directory (default: `<calling-project>/deliverables/` or `temp/experiment-evaluation/`)

## Steps

1. **Resolve out_root.** Walk up from cwd for `CLAUDE.md`; if found inside `projects/groupon/...` then out_root = `<project>/deliverables/`. Otherwise `temp/experiment-evaluation/`.
2. **Generate run_id** = current local time as `YYYY-MM-DD-HH-MM`. `run_dir` = `<out_root>/<run_id>`. Create `raw/` and `passthrough/` subdirs.
3. **Mode = rerender:** call render-combined-report directly on the existing `<run-id>` dir. Skip steps 4-9.
4. **Verify dependencies installed.** Check that both `ab-experiments` and `seo-impact-plugin` are loaded by querying the plugin manifest. If missing, fail with install instructions.
5. **list-experiments.** Build queue. If empty → exit with message.
6. **resolve-deal-urls** for every queue entry where `test_deals` has matching rows. Cache results in `<run_dir>/raw/urls_<alt_name>.json`.
7. **resolve-control-urls** for every entry that's SEO-eligible (start_date <= today-7). Cache in `<run_dir>/raw/control_urls_<alt_name>.json`. Required so seo-impact-analyzer can compute DiD.
8. **Dispatch parallel subagents** (Agent tool, model=sonnet, single message containing multiple tool calls):
   - For each experiment, fan out:
     - `run-ab-evaluation` → `<run_dir>/raw/ab_<alt_name>.json` (also computes per_category Filtered + Overall)
     - `run-seo-evaluation` (only if variant URLs exist AND start_date <= today-7) → `<run_dir>/raw/seo_<alt_name>.json`. Pass `variant_urls` and `control_urls` so DiD always computed.
     - `run-deal-charts` (only if URLs exist) → `<run_dir>/raw/deal_<alt_name>.json` (winners/losers enriched with company_name + deal_title)
   - Cap concurrency: dispatch in batches of 6 if queue × 3 > 6.
9. **Verify outputs.** Each expected JSON exists; if a subagent failed, the JSON contains `{"status":"failed","reason":...}` rather than missing. Log failures, continue.
10. **render-combined-report** on `<run_dir>` with `--run-id` and `--data-through`.
11. **Print final paths** to user: combined_report.html, summary.md, passthrough/.

## Tool contract
- All BQ via `bq` CLI. No DDL/DML. No MCP. No Okta.
- Subagents run on Sonnet (cost/speed); orchestrator is the only Opus context.

## Failure modes
- Required plugin missing → fail step 4 with install instructions.
- All subagents fail → render report anyway with failure tiles, return non-zero exit.
- Schema drift in test_definitions → fail step 5 hard.
