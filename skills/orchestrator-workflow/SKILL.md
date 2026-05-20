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
11. **Publish to Groupon IQ via a dedicated upload subagent** (single canonical link per run-date; reruns on the same day version that one report instead of spawning siblings). Title format: `Experiment Evaluation Combined Report — YYYY-MM-DD` (em-dash `—`, not hyphen) where the date is the **YYYY-MM-DD prefix of run_id** (the day the orchestrator ran). NOT data_through (data freshness drifts on reruns even when the analyst's intent is the same publication), NOT the experiment names — the canonical link is "today's combined evaluation run", and versioning is the dedup mechanism. Steps:

    1. Compute the date string from `run_id` (first 10 chars, YYYY-MM-DD). Title = `"Experiment Evaluation Combined Report — <YYYY-MM-DD>"`.
    2. Dispatch a single subagent (Task tool, `subagent_type=general-purpose`, `model=opus`) with a self-contained prompt instructing it to:
       1. Read `<run_dir>/combined_report.html` from disk and base64-encode it.
       2. Call `mcp__groupon-iq__upload_report` with:
          - `title = "Experiment Evaluation Combined Report — <YYYY-MM-DD>"`
          - `html_file_base64 = <the base64 string from step 1>`
          - `folder_id = "dbdf853d-55c8-4780-ad03-35441e5ffc10"` (the "AI summaries" folder, established convention)
          - `visibility = "public"` (the `upload_report` enum is `public | shared_with_link | private` — no `shared_in_groupon` value here; `public` is the closest equivalent for org-wide discoverability)
          - `overwrite_option = "overwrite"` (versions any existing same-title report instead of creating a sibling — the server handles the dedup, so we don't need a separate `list_reports` call)
          - `description` = the one-line scoreboard summary (alternate_names + composed verdicts) from `summary.md`
       3. Return just the final report URL to the orchestrator. Stay under 100 words.
    3. Receive the URL from the subagent and print it to the user. If the subagent reports failure — log the reason but don't fail the run; `combined_report.html` and `summary.md` already exist locally.

    Why a subagent and not the main session: emitting a base64 of `combined_report.html` (currently ~350 KB → ~470 KB base64, ~120 K tokens) directly from the main orchestrator session would consume most of its remaining output budget. The subagent has a fresh, dedicated context — the base64 cost stays isolated there, and the main session only sees the short URL coming back. This is the same pattern as the `run-ab-evaluation` / `run-seo-evaluation` subagents.

    Why MCP and not a Python helper that POSTs directly to the IQ REST API: the IQ REST API and the MCP transport share the same host (`api.enc.groupon.com`), but only the MCP route survives in the claude.ai routine sandbox — direct network calls from the sandbox to `api.enc.groupon.com` are blocked by network policy. The MCP tool call is routed through Anthropic's harness, which is what makes it work there. The MCP HTTP transport is also how Claude Code locally reaches the IQ MCP, so the same code path serves both environments.

    Practical ceiling — explicit tradeoff: this design fits HTML up to roughly 600–700 KB raw (where the subagent's own context budget caps out emitting base64), and ~3.75 MB if we accept losing the subagent isolation (the MCP tool's `html_file_base64` cap is 5 MB of base64 = ~3.75 MB raw). Current reports run ~350 KB. If they grow past ~3 MB we need a different mechanism — likely a `html_file_url` mode on the IQ MCP that fetches the file from a temporary URL, since no LLM-mediated path scales past the 5 MB MCP cap.
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
