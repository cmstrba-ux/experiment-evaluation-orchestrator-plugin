---
description: Evaluate experiments (AB + SEO + deal charts) from test_definitions and produce a combined Chart.js HTML report.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
argument-hint: <alternate_name> | --auto | --since YYYY-MM-DD | --rerender <run-id>
---

You are running the experiment-evaluation-orchestrator. The user typed: `/evaluate-reviews-experiments $ARGUMENTS`

## Step 1: Parse arguments

Parse `$ARGUMENTS` into a `mode`:
- Empty or `--auto` → `mode=auto` (the queue will filter `evaluate_automatically=TRUE`).
- `--since YYYY-MM-DD` → `mode=since` with `since_date` set.
- `--rerender <run-id>` → `mode=rerender` with `run_id` set.
- Anything else → `mode=explicit` with `alternate_name = $ARGUMENTS` (the entire argument string, including spaces — alternate_names like "AI Summaries v4 - Single format 30k" contain spaces and dashes; do NOT split on whitespace).

## Step 2: Read the orchestrator-workflow skill and follow it

Read `${CLAUDE_PLUGIN_ROOT}/skills/orchestrator-workflow/SKILL.md` and follow its instructions exactly with the parsed mode. The skill describes the full pipeline: list-experiments → resolve-deal-urls → fan-out subagents (run-ab-evaluation / run-seo-evaluation / run-deal-charts) → render-combined-report.

Inputs the skill needs from this command:
- `mode` (from Step 1)
- `alternate_name` / `since_date` / `run_id` if applicable
- `out_root`: not specified by the user — let the workflow auto-resolve (walk up from cwd for CLAUDE.md → if inside `projects/groupon/...` use `<project>/deliverables/`, otherwise `temp/experiment-evaluation/`).

## Step 3: Verify dependencies before doing real work

Before any BQ query or subagent dispatch, confirm both dependency plugins are loaded:
- `ab-experiments` (look for `~/.claude/plugins/cache/miro-personal/ab-experiments/` — must contain a versioned subfolder with `skills/ab-experiment-evaluation-c3/SKILL.md`).
- `seo-impact-plugin` (look at `~/.claude/plugins/local-marketplaces/miro-personal/plugins/seo-impact-plugin/skills/`).
If either is missing, stop and tell the user to install it first.

## Step 4: Execute the workflow

Run the steps from `orchestrator-workflow/SKILL.md`. Use Task tool with `subagent_type=general-purpose` and `model=opus` to fan out the per-experiment evaluators in parallel. Cap concurrency at ~6 simultaneous subagents. (Opus is the canonical model for orchestrator subagents — keeps verdict reasoning, narrative synthesis, and SRM-remediation branching consistent with the main orchestrator context.)

## Step 5: Surface the result

When the run completes, print to the user:
- `combined_report.html` absolute path
- `summary.md` absolute path
- `passthrough/` directory (if present)
- A one-line scoreboard summary per experiment (label + verdict from each `raw/ab_<alt>.json`).

If any subagent failed, surface the failure tile message and which experiment it belonged to. Do NOT swallow errors.

## Tool contract (must hold throughout)

- Read-only BigQuery via `bq` CLI only — never MCP, never DDL/DML.
- URL resolution from `dim_deal` / `deal_option` only — never invoke `seo-impact-plugin:okta-proxy` / `seo-url-resolver` / `seo-mds-insights-review`.
- Date window is taken from `test_definitions.start_date` / `end_date` for both AB-Filtered and AB-Overall — never from GrowthBook brief dates.
