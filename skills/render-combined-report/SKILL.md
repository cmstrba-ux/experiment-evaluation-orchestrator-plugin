---
name: render-combined-report
description: Compose the final combined HTML + exec summary from raw JSON intermediates produced by the AB / SEO / deal-charts subagents. Invoked by orchestrator-workflow as the last step.
---

# render-combined-report

## Inputs
- `run_dir`: directory containing `raw/{ab,seo,deal}_*.json` files
- `data_through`: max event_date across all raw JSONs (string)
- `run_id`: human-readable run id (YYYY-MM-DD-HH-MM)

## Steps

1. Verify `run_dir/raw/` exists and has at least one `ab_*.json` file.
2. Run:

   ```
   python -m scripts.lib.render \
     --run-dir <run_dir> \
     --out <run_dir>/combined_report.html \
     --summary <run_dir>/summary.md \
     --run-id <run_id> \
     --data-through <data_through>
   ```

3. Copy any passthrough artifacts (per-experiment .docx, .xlsx, plugin SEO HTML) into `<run_dir>/passthrough/` if they exist (run-ab-evaluation and run-seo-evaluation already write there).
4. Print final paths to stdout: combined_report.html, summary.md, passthrough/ (if any).

## Tool contract
- No BQ access in this skill — purely consumes JSON + writes HTML/MD.
- `render.py` does no I/O beyond the input JSONs and the two output files.

## What the renderer produces

`combined_report.html` is a single self-contained HTML file with:
- **Scoreboard cards** per experiment (label, SRM, M1/UV + CVR Δ, Overall MPV mean Δ, SEO DiD headlines if available, verdict)
- **Per-experiment tab** with sub-tabs:
  - **Overview**: side-by-side daily M1/UV and CVR line charts; KPI cards.
  - **Per Category**: 4-column heatmap (M1/UV + CVR × Filtered + Overall) with significance markers; per-category sub-tabs each with daily Filtered + Overall trend charts.
  - **SEO**: pre/post window KPIs; overall DiD table (variant vs control, day-normalized, populated when `did_overall` is provided); per-L2 DiD heatmap row; per-L2 top 15 winners + losers from `per_url`; raw variant-only pre/post bars.
  - **Deals**: top winners + top losers tables with linked deal titles → groupon.com; by_category and by_booking_platform tables.

## Schema expected in raw JSONs

Each subagent enriches its JSON with the fields the renderer needs:

- `ab_<alt>.json` may include `per_category` (filtered, deal-scoped per cat) and `per_category_overall` (population-wide per cat). The renderer's heatmap uses both; if `per_category_overall` is absent it shows "n/a" for those columns.
- `seo_<alt>.json` may include `did_overall`, `did_per_l2`, `l2_topk` (top 15 winners/losers per L2 by clicks_delta). When `did_overall` is missing the renderer surfaces an explicit "DiD not computed" notice.
- `deal_<alt>.json` top winners/losers should include `company_name` + `deal_title` for clean hyperlinks.

## Failure modes
- Empty run_dir → renderer writes a stub HTML and exits 0.
- Schema regression in a per-experiment JSON → renderer does best-effort with safe fallbacks (`?? 0`, `n/a` cells); never throws.
