---
name: run-seo-evaluation
description: Thin coordinator that runs the SEO impact pipeline by sequencing seo-impact-plugin's existing skills. Skips okta-proxy / seo-url-resolver / seo-mds-insights-review (orchestrator pre-enriched URLs from dim_deal). Reimplements nothing — passes through the plugin's outputs.
---

# run-seo-evaluation

## Inputs
- `alternate_name`, `start_date`, `end_date`, `urls` (pre-enriched list from resolve-deal-urls), `out_path`

## What this skill does itself vs. delegates

| Step | Owner | Why |
|---|---|---|
| Date / window guardrails (early/partial/full signal) | DELEGATE to `seo-impact-plugin:seo-guardrails` | Plugin already has tiered thresholds; don't hardcode. |
| URL resolution | SKIP (orchestrator did it) | `resolve-deal-urls` already produced enriched URLs from `dim_deal`/`deal_option` — no MDS/Okta needed. |
| Page classification | DELEGATE to `seo-impact-plugin:seo-page-classifier` | Existing skill. |
| GSC fetch | DELEGATE to `seo-impact-plugin:seo-gsc-fetcher` | Existing skill. |
| Pre/post + DiD analysis | DELEGATE to `seo-impact-plugin:seo-impact-analyzer` | Already computes DiD with statistical confidence. Do NOT reimplement. |
| HTML/XLSX passthrough output | DELEGATE to `seo-impact-plugin:seo-report-generator` | Plugin's standard output for the passthrough/ folder. |
| MDS insights review | SKIP | Okta-dependent, not on critical path. |

## Steps

1. **Guardrails.** Dispatch `seo-impact-plugin:seo-guardrails` with `release_date=start_date`. Capture `signal_level` (early/partial/full) or abort reason.
   - If aborted → write `{"status":"skipped","reason":<plugin reason>}` to out_path, return.
2. **Verify URLs.** Each entry has `deal_url`, `landing_page`. Run `assert_no_mds(deal_url)` for each.
3. **Page classification.** Dispatch `seo-impact-plugin:seo-page-classifier` with the URL list. Capture classified URL list.
4. **GSC fetch.** Dispatch `seo-impact-plugin:seo-gsc-fetcher` with `release_date=start_date`, classified URLs, control set (sample non-experiment deals from same categories).
5. **Analysis.** Dispatch `seo-impact-plugin:seo-impact-analyzer`. Capture pre/post deltas, DiD, per-URL trends, statistical confidence — all from the plugin, no recomputation.
6. **Passthrough rendering.** Dispatch `seo-impact-plugin:seo-report-generator` → write `passthrough/seo_<alt_name>.html` and `passthrough/seo_<alt_name>.xlsx`.
7. **Write JSON intermediate** to out_path:

```json
{
  "status": "ok",
  "alternate_name": "...",
  "signal_level": "early|partial|full",
  "pre_post": {...},
  "did": {...},
  "per_url": [...],
  "passthrough_html": "passthrough/seo_<alt_name>.html",
  "passthrough_xlsx": "passthrough/seo_<alt_name>.xlsx"
}
```

## Tool contract

- Never invoke `seo-impact-plugin:okta-proxy`, `seo-url-resolver`, or `seo-mds-insights-review`.
- Don't reimplement DiD or statistical tests — `seo-impact-analyzer` is authoritative.
- `bq` CLI only for any direct BQ access.

## Failure modes
- Guardrails abort → graceful skip with reason in JSON.
- Any delegated skill fails → retry once, then mark `status: failed` with which step failed.
- Empty URL list → `{"status":"no_urls"}`.
