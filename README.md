# experiment-evaluation-orchestrator

Reads experiments from `test_definitions`, fans out parallel AB / SEO / deal-charts evaluation, produces a single combined Chart.js HTML report.

## Slash command

- `/evaluate-reviews-experiments [<alternate_name> | --auto | --since YYYY-MM-DD | --rerender <run-id>]`

## Tool contract

- Read-only BigQuery via `bq` CLI (never MCP, never DDL/DML).
- URL/metadata resolution via `dim_deal` + `deal_option` (MDS/Okta bypassed).
- Both branches use the same date-window logic from `test_definitions`.

## Required dependencies (soft)

- `ab-experiments` plugin (skills: `ab-experiment-evaluation-c3`, `ab-experiment-monitor`)
- `seo-impact-plugin` (skills: `seo-guardrails`, `seo-page-classifier`, `seo-gsc-fetcher`, `seo-impact-analyzer`, `seo-report-generator`)

## Spec

See `docs/plans/2026-05-05-12-41-experiment-evaluation-orchestrator.md`.

## Install

Direct from this repo (once published):
```
/plugin marketplace add https://github.com/cmstrba-ux/experiment-evaluation-orchestrator-plugin
/plugin install experiment-evaluation-orchestrator
```

Or via local marketplace wrapper (current setup at miro-personal). See `docs/plans/2026-05-05-12-41-experiment-evaluation-orchestrator.md` for full spec.
