---
name: run-seo-evaluation
description: Thin coordinator that runs the SEO impact pipeline by sequencing seo-impact-plugin's existing skills. Skips okta-proxy / seo-url-resolver / seo-mds-insights-review (orchestrator pre-enriched URLs from dim_deal). Merges variant URLs (from resolve-deal-urls) with control URLs (from resolve-control-urls) so seo-impact-analyzer always has both groups → DiD is always computed. Post-processes per_url into per-L2 top-15 winners/losers + DiD-by-L2 aggregates so the embedded report payload stays small.
---

# run-seo-evaluation

## Inputs
- `alternate_name`, `start_date`, `end_date`
- `variant_urls`: pre-enriched list from `resolve-deal-urls` (each row tagged `group="variant"`)
- `control_urls`: list from `resolve-control-urls` (each row tagged `group="control"`)
- `out_path`: where to write `seo_<alt>.json`
- `passthrough_dir`: where to write the SEO plugin's HTML/XLSX

## What this skill does itself vs. delegates

| Step | Owner | Why |
|---|---|---|
| Date / window guardrails (early/partial/full signal) | DELEGATE to `seo-impact-plugin:seo-guardrails` | Plugin already has tiered thresholds. |
| URL resolution | SKIP (orchestrator did it) | `resolve-deal-urls` + `resolve-control-urls` already produced enriched URLs. No MDS/Okta needed. |
| Page classification | DELEGATE to `seo-impact-plugin:seo-page-classifier` | Existing skill. |
| GSC fetch | DELEGATE to `seo-impact-plugin:seo-gsc-fetcher` | Existing skill. |
| Pre/post + DiD analysis | DELEGATE to `seo-impact-plugin:seo-impact-analyzer` | Authoritative. Computes DiD natively when both groups are present. |
| Per-L2 top-15 winners/losers + DiD-by-L2 aggregates | OWN | Post-process per_url; the SEO plugin doesn't expose this view. |
| HTML/XLSX passthrough output | DELEGATE to `seo-impact-plugin:seo-report-generator` | Plugin's standard passthrough. |
| MDS insights review | SKIP | Okta-dependent, not on critical path. |

## Steps

1. **Merge URL set.** Tag each variant URL with `group="variant"` and each control URL with `group="control"`. Verify no MDS URLs leak. If `control_urls` is empty/missing, log a clear warning and proceed in variant-only mode (DiD will be empty).
2. **Guardrails.** Dispatch `seo-impact-plugin:seo-guardrails` with `release_date=start_date`. Capture `signal_level` (early/partial/full) or abort reason.
   - If aborted → write `{"status":"skipped","reason":...}` to out_path, return.
3. **Page classification.** Dispatch `seo-impact-plugin:seo-page-classifier` with the merged URL list.
4. **GSC fetch.** Dispatch `seo-impact-plugin:seo-gsc-fetcher` with `release_date=start_date`, classified URLs.
5. **Analysis.** Dispatch `seo-impact-plugin:seo-impact-analyzer`. With both groups present it produces a non-empty `did` dict.
6. **Post-process per_url** into:
   - `l2_topk` — `{<L2>: {n_total, n_with_change, winners[15], losers[15]}}`. Winners/losers ranked by `clicks_delta` (descending / ascending). Variant-side only.
   - `did_per_l2` — day-normalized DiD per L2. Only populated when both groups are present in per_url. Schema: `{<L2>: {variant: {pre_imp_total, post_imp_total, pre_clk_total, post_clk_total, pre_url_count, post_url_count, imp_pct_change, clk_pct_change, ctr_pre, ctr_post, ctr_delta_pp}, control: {…}, did: {imp_pp, clk_pp, ctr_pp}}}`.
   - `did_overall` — same shape as a single did_per_l2 entry, summed across L2s.
   - `l2_order` — the L2 keys in display order (descending by total variant impressions).
7. **Passthrough rendering.** Dispatch `seo-impact-plugin:seo-report-generator` → write `<passthrough_dir>/seo_<alt_name>.html` and `<passthrough_dir>/seo_<alt_name>.xlsx`.
8. **Write JSON intermediate** to `out_path`:

```json
{
  "status": "ok",
  "alternate_name": "...",
  "signal_level": "early|partial|full",
  "pre_post": {...},
  "pre_days": 28,
  "post_days": 18,
  "did_overall": {...},
  "did_per_l2": {...},
  "l2_topk": {...},
  "l2_order": ["Beauty & Spas", "..."],
  "passthrough_html": "passthrough/seo_<alt_name>.html",
  "passthrough_xlsx": "passthrough/seo_<alt_name>.xlsx"
}
```

**Do NOT embed the full `per_url` list** in this JSON — it can be 18k+ rows × ~30 columns and will bloat the combined report HTML. The full list lives in the passthrough .xlsx.

## Tool contract

- Never invoke `seo-impact-plugin:okta-proxy`, `seo-url-resolver`, or `seo-mds-insights-review`.
- Don't reimplement DiD when the plugin can compute it — only post-process its outputs.
- `bq` CLI only for any direct BQ access.

## Failure modes
- Guardrails abort → graceful skip with reason in JSON.
- Empty variant URL list → `{"status":"no_urls"}`.
- Empty control URL list → proceed variant-only; `did_overall`/`did_per_l2` will be omitted; renderer surfaces "DiD not computed" notice.
- Any delegated skill fails → retry once, then mark `status: failed` with which step failed.
