---
description: Evaluate a queue of experiments (AB + SEO + deal charts) from test_definitions and produce a combined Chart.js HTML report.
---

# /evaluate-experiments

Usage: `/evaluate-experiments [<alternate_name> | --auto | --since YYYY-MM-DD | --rerender <run-id>]`

## Args parsing
- No args or `--auto` → mode=auto (filter `evaluate_automatically=TRUE`).
- `--since YYYY-MM-DD` → mode=since.
- `--rerender <run-id>` → mode=rerender.
- Bare alternate_name → mode=explicit.

## Action
Invoke `experiment-evaluation-orchestrator:orchestrator-workflow` with the parsed mode. Report progress as subagents complete (one update per experiment finished). At end, print the final paths to combined_report.html and summary.md.

## Behavior on errors
Surface any orchestrator-workflow error messages verbatim. Don't swallow.
