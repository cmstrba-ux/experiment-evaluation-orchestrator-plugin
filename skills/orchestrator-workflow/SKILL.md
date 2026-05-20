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
5. **list-experiments.** Build queue and **write it to `<run_dir>/queue.json`** (top level, NOT inside `raw/`). The renderer reads this exact path to merge `evaluate_seo_since` onto each experiment for the SEO TOO EARLY countdown — placing it under `raw/` silently breaks that feature (the merge no-ops and SEO tiles render `n/a` instead of `TOO EARLY — X/14 days`). If empty → exit with message.
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
11. **Publish to Groupon IQ via the `mcp__groupon-iq__upload_report` MCP tool** (single canonical link per run-date; reruns on the same day version that one report instead of spawning siblings). Title format: `Experiment Evaluation Combined Report — YYYY-MM-DD` (em-dash `—`, not hyphen) where the date is the **YYYY-MM-DD prefix of run_id** (the day the orchestrator ran). NOT data_through (data freshness drifts on reruns even when the analyst's intent is the same publication), NOT the experiment names — the canonical link is "today's combined evaluation run", and versioning is the dedup mechanism. Steps:

    1. Compute the date string from `run_id` (first 10 chars, YYYY-MM-DD).
    2. Base64-encode `<run_dir>/combined_report.html` (a ~350 KB HTML produces a ~470 KB base64 string, well under the MCP tool's 5 MB cap):

       ```bash
       python -c "import base64,sys; sys.stdout.write(base64.b64encode(open(r'<run_dir>\\combined_report.html','rb').read()).decode())"
       ```

       Pipe the output into a temporary file the next step can read, OR capture it as a shell variable. Do NOT inline the base64 inside the SKILL.md — it's per-run data.
    3. Call `mcp__groupon-iq__upload_report` with:
       - `title = "Experiment Evaluation Combined Report — <YYYY-MM-DD>"`
       - `html_file_base64 = <base64 from step 2>`
       - `folder_id = "dbdf853d-55c8-4780-ad03-35441e5ffc10"` (the "AI summaries" folder, established convention)
       - `visibility = "public"` (visible to all Groupon IQ users; the `upload_report` tool's enum is `shared_with_link | public | private` — there is NO `shared_in_groupon` value here, even though `create_report` has it; "public" is the closest equivalent to the old shared_in_groupon for org-wide discoverability)
       - `overwrite_option = "overwrite"` (versions any existing same-title report instead of creating a sibling — replaces the previous `list_reports → branch → POST /versions` two-step)
       - `description` = one-line summary of the queue (alternate_names + composed verdicts from `summary.md`)
    4. The tool returns the report URL. If the call fails (network, auth, or upstream error) — log it and continue; **do not fail the run on publish errors**.

    Why MCP not curl: this skill must run unattended in claude.ai routines, whose sandbox blocks `api.enc.groupon.com` for curl but allows the configured MCP server to reach it. `html_file_path` is NOT supported because the groupon-iq MCP runs as an HTTP server on Groupon infrastructure (`type: "http"`, `url: api.enc.groupon.com/groupon-iq-mcp/mcp`) — it has no view of the orchestrator's local filesystem regardless of slash direction. `html_file_base64` is the only file-aware mode that works for a remote MCP transport. The token cost (~120K tokens per upload at 350 KB HTML) is the explicit tradeoff for cross-environment portability.
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
