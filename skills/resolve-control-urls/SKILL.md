---
name: resolve-control-urls
description: Resolve a matched control URL set for SEO DiD. Samples non-experiment groupon.com 'deals' URLs in the same L2 categories as the variant set, ranked by pre-period impressions. Without this, seo-impact-analyzer cannot compute Difference-in-Differences.
---

# resolve-control-urls

## Inputs
- `alternate_name`: required.
- `pre_start`, `pre_end`: pre-period date range (used to rank candidates by impressions).
- `per_l2_cap`: optional, default 5000 — max control URLs per L2 to keep size bounded.

## Steps

1. Run query `resolve_control_urls` from `scripts/lib/bq_queries.sql` with parameters.
2. For every URL returned, assert `assert_no_mds(url)` from `scripts.lib.tool_contract`.
3. Emit JSON: `[{"deal_url":..., "web_category_level_2":..., "pre_imp":..., "group":"control"}, ...]`.

## Why this exists

`resolve-deal-urls` only emits URLs from `test_deals` — all tagged as the experiment's variant group. Without a parallel control set, `seo-impact-analyzer.compute_did(...)` returns an empty `did` dict and the combined report has no Difference-in-Differences row. That's the primary corrected estimator for SEO impact (raw pre/post is confounded by window asymmetry, indexing churn, seasonality).

The control set we sample here:
- Same `category_level_2` as the variant set (so L1/L2 distribution matches).
- Same `page_type='deals'`, `root_domain='groupon.com'`, `coupon_core_flag='core'` (apples-to-apples).
- Excluded from `test_deals` (no contamination).
- Top-K by pre-period impressions per L2 (so we capture meaningful control volume without scanning the long tail).

## Reporting

- If 0 control URLs returned → emit `{"status":"no_control","alternate_name":...}` and let caller decide whether to skip DiD.
- If <100 control URLs per L2 → log a warning; DiD will be noisy but still computable.

## Tool contract

- `bq` CLI only. URLs validated through `assert_no_mds`.
- Read-only — no DDL/DML.
