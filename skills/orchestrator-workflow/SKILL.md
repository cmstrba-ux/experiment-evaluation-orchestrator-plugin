---
name: orchestrator-workflow
description: Top-level workflow for evaluating a queue of experiments. Reads test_definitions, dispatches AB / SEO / deal-charts subagents in parallel (Opus, capped ~6 in flight), assembles the combined HTML report. Invoked by the /evaluate-reviews-experiments slash command.
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
7. *(Removed.)* Synthetic-control fallback inside `seo-impact-plugin:seo-impact-analyzer` (hierarchical L3→L2→L1→page_type→domain) replaces the orchestrator's previous control URL sampling.
8. **Dispatch parallel subagents** (Task tool, **model=opus** for every subagent, single message containing multiple tool calls):
   - For each experiment, fan out:
     - `run-ab-evaluation` → `<run_dir>/raw/ab_<alt_name>.json` (also computes per_category Filtered + Overall)
     - `run-seo-evaluation` (only if variant URLs exist AND `evaluate_seo_since <= today-14`) → `<run_dir>/raw/seo_<alt_name>.json`. The subagent shells out to `scripts/run_seo_pipeline.py` — a deterministic Python entrypoint that imports upstream `seo-impact-plugin` modules directly (no per-stage prompt dispatch). Pass `variant_urls_path` and `release_date = queue.evaluate_seo_since` (NOT `start_date`) — the AB window can begin earlier than the SEO release when the variant rolls out partway through. `list-experiments` already falls back to `start_date` when `evaluate_seo_since` is blank, so this field is always populated.
     - `run-deal-charts` (only if URLs exist) → `<run_dir>/raw/deal_<alt_name>.json` (winners/losers enriched with company_name + deal_title)
   - Cap concurrency: dispatch in batches of 6 if queue × 3 > 6.
   - **Model rule**: never downgrade to Sonnet inside this orchestrator. All three subagents need consistent reasoning depth (verdict synthesis, SRM remediation, narrative interpretation); cost is the explicit tradeoff for run-to-run consistency.
9. **Verify outputs.** Each expected JSON exists; if a subagent failed, the JSON contains `{"status":"failed","reason":...}` rather than missing. Log failures, continue.
10. **render-combined-report** on `<run_dir>` with `--run-id` and `--data-through`.
11. **Publish to Groupon IQ** (single canonical link per run-date; reruns on the same day version that one report instead of spawning siblings). Title format: `Experiment Evaluation YYYY-MM-DD` where the date is the **YYYY-MM-DD prefix of run_id** (the day the orchestrator ran). NOT data_through (data freshness drifts on reruns even when the analyst's intent is the same publication), NOT the experiment names — the canonical link is "today's evaluation run", and versioning is the dedup mechanism. Steps:
    1. Compute the date string from `run_id` (first 10 chars, YYYY-MM-DD).
    2. Search existing IQ reports for the exact title via `mcp__groupon-iq__list_reports` with `search="Experiment Evaluation <YYYY-MM-DD>"`. If a matching report exists, POST the new HTML as a new version via curl: `curl -X POST "https://api.enc.groupon.com/reports/reports/<id>/versions" -H "g-api-key: $IQ_API_KEY" -F "file=@<combined_report.html>;type=text/html"`.
    3. If no match exists, call `mcp__groupon-iq__create_report` with that exact title, `folder_id="dbdf853d-55c8-4780-ad03-35441e5ffc10"` ("AI summaries" folder, established convention), `visibility="shared_in_groupon"`, and a one-line description summarizing the queue (alternate_names + verdicts). Then POST the HTML to the returned `/versions` URL.
    4. Skip publish silently when `$IQ_API_KEY` is unset OR `--no-publish` is on the invocation. Don't fail the run on publish errors; log them and continue.
12. **Print final paths** to user: combined_report.html, summary.md, passthrough/, and the Groupon IQ URL (if publish succeeded).

## Tool contract
- All BQ via `bq` CLI. No DDL/DML. No MCP. No Okta.
- Subagents run on Opus — orchestrator-wide consistency requirement, not negotiable per-call.
- **Date window is LOCKED to test_definitions.** The `start_date` / `end_date` from the queue (sourced verbatim from `test_definitions`) are the single source of truth. Subagents MUST pass them unchanged to every BQ query and MUST NOT apply ramp-up trimming, warm-up cutoffs, early/late-day exclusion, or any other windowing heuristic. For closed experiments this guarantees byte-identical SUMs (and therefore identical headline %Δ) on rerun.

## Notes on SEO inputs

The orchestrator no longer supplies a control URL set. Upstream `seo-impact-plugin:seo-impact-analyzer` builds a synthetic peer cohort with hierarchical L3→L2→L1→page_type→domain fallback. The orchestrator's only SEO-input responsibility is `variant_urls` (already produced by `resolve-deal-urls`).

## Failure modes
- Required plugin missing → fail step 4 with install instructions.
- All subagents fail → render report anyway with failure tiles, return non-zero exit.
- Schema drift in test_definitions → fail step 5 hard.
