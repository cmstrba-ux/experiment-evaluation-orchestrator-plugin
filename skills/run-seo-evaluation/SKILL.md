---
name: run-seo-evaluation
description: Deterministic shim that shells out to scripts/run_seo_pipeline.py to drive the upstream seo-impact-plugin end-to-end for one experiment. Produces the same JSON intermediate the combined renderer consumes — but identical inputs now yield byte-identical outputs across runs because no subagent interpretation of upstream SKILL.md is involved.
---

# run-seo-evaluation

## Inputs
- `alternate_name`
- `release_date` — sourced from `test_definitions.evaluate_seo_since` (the queue field of the same name). The orchestrator falls back to `start_date` when `evaluate_seo_since` is blank/null in the source row (handled in `bq_queries.list_experiments`), so this skill ALWAYS receives a concrete date. Do not re-substitute `start_date` here.
- `variant_urls_path`: absolute path to `raw/urls_<alt>.json` produced by `resolve-deal-urls`
- `out_path`: where to write `raw/seo_<alt>.json`
- `passthrough_dir`: where to write the upstream HTML/XLSX

## Why this skill is now a single shell-out

Earlier versions of this skill instructed the subagent to *dispatch* each upstream
stage (`seo-impact-plugin:seo-guardrails`, `seo-page-classifier`, `seo-gsc-fetcher`,
`seo-impact-analyzer`, `seo-report-generator`) one by one. Every dispatch was a
re-read of an upstream SKILL.md and a re-derivation of glue code, which is the
main source of run-to-run drift in the orchestrator. The pipeline is now driven
by a single parametric Python script at `${CLAUDE_PLUGIN_ROOT}/scripts/run_seo_pipeline.py`
that imports the upstream modules directly. Same inputs → identical outputs.

## Steps

1. **Pre-flight: cache freshness.** Verify the cached seo-impact-plugin has `compute_verdict`:
   ```powershell
   Select-String -Path "$env:USERPROFILE\.claude\plugins\cache\*\seo-impact-plugin\*\plugins\seo-impact-plugin\scripts\impact_analyzer.py","$env:USERPROFILE\.claude\plugins\cache\*\seo-impact-plugin\*\scripts\impact_analyzer.py" -Pattern "compute_verdict" -List
   ```
   No hit → write
   `{"status":"failed","reason":"stale plugin cache — run /plugin marketplace update <marketplace>","failed_at":"cache-precheck"}`
   to `out_path` and return without running.

2. **Validate variant URLs file is non-empty.** `Get-Content $variant_urls_path | ConvertFrom-Json | Measure-Object -Property Count` — if zero or the JSON contains `{"status":"no_deals"}`, write `{"status":"no_urls","alternate_name":<alt>}` and return.

3. **Run the deterministic pipeline — SYNCHRONOUSLY, in foreground.**

   ⚠️ **Run the Bash/PowerShell call synchronously. Do NOT use `run_in_background=true`, the Monitor tool, `&`, `Start-Job`, or any other backgrounding mechanism.** The pipeline takes 2-5 minutes and writes its JSON only at the end; backgrounding will return control before the file is written and tempt you to declare success on a stale or empty `out_path`. (Observed regression 2026-05-11 on FAQ_reviews: subagent backgrounded via Monitor, exited early, left `{"status":"no_urls"}` despite 3,153 URLs being resolved — the pipeline did finish successfully into scratch but the orchestrator JSON was wrong.) If you need a longer timeout, raise the Bash `timeout` parameter (up to 600000 ms) instead.

   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/run_seo_pipeline.py" \
       --alternate-name "<alternate_name>" \
       --variant-urls "<variant_urls_path>" \
       --release-date <release_date>  # YYYY-MM-DD, from queue.evaluate_seo_since \
       --out "<out_path>" \
       --passthrough-dir "<passthrough_dir>"
   ```
   The script writes `raw/seo_<alt>.json` itself — on failure it writes a
   `{"status":"failed", ...}` JSON and exits non-zero. Do not post-process or
   re-derive any field from the script's output.

4. **Read the resulting JSON and verify `status == "ok"` before returning.**
   - Open `out_path` with the Read tool after the script exits.
   - If `status != "ok"`, do NOT report success to the orchestrator — surface the reason verbatim (e.g. `no_urls`, `failed/cache-precheck`, `failed/run_seo_pipeline`).
   - If the script exit code was non-zero but `out_path` doesn't exist or is empty (script crashed before writing), report `status="failed"` with the captured stderr tail.
   - Never return `{"status":"ok"}` to the orchestrator without having read the file post-exit.

## Tool contract

- Never invoke `seo-impact-plugin:okta-proxy`, `seo-impact-plugin:seo-url-resolver`, or `seo-impact-plugin:seo-mds-insights-review` — `resolve-deal-urls` already pre-enriches the URL set, and the deterministic script skips upstream `resolve()` entirely.
- `bq` CLI is invoked transitively by the upstream `seo-gsc-fetcher` module; this skill itself only shells out to Python.

## Output schema (written by the script)

Same as before — the renderer is unchanged:
- `status`: `ok | no_urls | failed`
- `alternate_name`, `verdict`, `did_coherence`, `signal_level`
- `did`, `power_analysis`, `overall`
- `summary_tables`, `by_category_l1`, `by_category_l2`, `by_category_l3`, `by_page_type`
- `caveats`
- `upstream_html_b64` (plain base64 — `render.py` gzip-wraps it before embedding)
- `passthrough_html`, `passthrough_xlsx`

## Failure modes

- Cache pre-check fails → `{"status":"failed","failed_at":"cache-precheck"}`.
- Empty variant URL list → `{"status":"no_urls"}`.
- Any upstream stage raises → script writes `{"status":"failed","failed_at":"run_seo_pipeline","reason":<exc>}` and exits non-zero. Do NOT retry — the failure is deterministic and re-running will produce the same error.
