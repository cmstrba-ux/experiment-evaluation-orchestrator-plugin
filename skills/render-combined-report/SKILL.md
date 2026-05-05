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
2. Run `python -m scripts.lib.render --run-dir <run_dir> --out <run_dir>/combined_report.html`.
3. Render `templates/exec_summary.md.j2` with the same data → `<run_dir>/summary.md`.
4. Copy passthrough artifacts (per-exp .docx and .xlsx) into `<run_dir>/passthrough/` if they exist.
5. Print final paths to stdout: combined_report.html, summary.md, passthrough/ (if any).

## Tool contract
- No BQ access in this skill — purely consumes JSON + writes HTML/MD.
