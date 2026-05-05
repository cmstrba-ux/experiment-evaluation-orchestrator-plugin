# experiment-evaluation-orchestrator

Reads experiments from `test_definitions`, fans out parallel AB / SEO / deal-charts evaluation, produces a single combined Chart.js HTML report.

The combined report includes:
- Per-experiment scoreboard (Label, SRM, M1/UV + CVR daily Δ, verdict)
- Overview tab: side-by-side M1/UV and CVR daily line charts (Treatment vs Control)
- Per-Category tab: 4-column heatmap (M1/UV + CVR × Filtered + Overall) and per-category sub-tabs with daily Filtered + Overall trend charts
- SEO tab: pre/post window KPIs, overall DiD (variant vs control, day-normalized) and per-L2 DiD heatmap, per-L2 top-15 winners + losers from per_url, raw variant-only pre/post bars
- Deals tab: top winners + top losers tables with hyperlinked deal titles → groupon.com

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
