# experiment-evaluation-orchestrator

Reads experiments from a `test_definitions` table, fans out parallel AB / SEO / deal-charts evaluation, and produces a single combined Chart.js HTML report.

The combined report includes:
- Per-experiment scoreboard (Label, SRM, M1/UV + CVR daily Δ, verdict)
- Overview tab: side-by-side M1/UV and CVR daily line charts (Treatment vs Control)
- Per-Category tab: 4-column heatmap (M1/UV + CVR × Filtered + Overall) and per-category sub-tabs with daily Filtered + Overall trend charts
- SEO tab: pre/post window KPIs, overall DiD (variant vs control, day-normalized) and per-L2 DiD heatmap, per-L2 top-15 winners + losers from per_url, raw variant-only pre/post bars
- Deals tab: top winners + top losers tables with hyperlinked deal titles

## Slash command

- `/evaluate-reviews-experiments [<alternate_name> | --auto | --since YYYY-MM-DD | --rerender <run-id>]`

## Tool contract

- Read-only BigQuery via the `bq` CLI (never MCP, never DDL/DML).
- URL and metadata resolution via local deal-dimension tables (no external service calls required at runtime).
- All evaluation branches share the same date-window logic from `test_definitions`.

## Required dependencies (soft)

- AB evaluation plugin (skills: `ab-experiment-evaluation-c3`, `ab-experiment-monitor`)
- SEO impact plugin (skills: `seo-guardrails`, `seo-page-classifier`, `seo-gsc-fetcher`, `seo-impact-analyzer`, `seo-report-generator`)

## Install

Install from a plugin marketplace that hosts this plugin:

```
/plugin marketplace add <marketplace-url>
/plugin install experiment-evaluation-orchestrator
```
