---
name: run-deal-charts
description: Compute AI-summary-style deal-level charts (top winners/losers, by category, by booking platform) from review_experiments_deal. Enriches top winners/losers with company_name + deal_title from deal_option so the renderer can show clickable, human-readable rows. Invoked by orchestrator-workflow as a subagent.
---

# run-deal-charts

## Inputs
- `alternate_name`, `start_date`, `end_date`: required
- `out_path`: where to write deal_<alt_name>.json

## Steps

1. Run `bq_queries.deal_top_winners_losers` with parameters → split into `top_winners` (m1_delta DESC, top 10) and `top_losers` (m1_delta ASC, top 10).
2. Run `bq_queries.deal_by_category` → compute per-category deltas (CVR_treat - CVR_ctrl, m1_treat - m1_ctrl).
3. Run `bq_queries.deal_by_booking_platform` → per-platform breakdown.
4. **Enrich titles.** Collect the union of UUIDs across `top_winners` + `top_losers`. Run a single lookup against `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option` selecting `MAX(company_name)` and `MAX(deal_creative_content_title)` per `deal_uuid`. Merge results back into the rows so each contains `company_name` and `deal_title`.
5. Write JSON:

```json
{
  "alternate_name": "...",
  "top_winners": [{"deal_uuid":..., "deal_url":..., "category":..., "m1_delta":..., "company_name":..., "deal_title":...}, ...],
  "top_losers":  [...],
  "by_category": [{"category":..., "cvr_delta":..., "m1_delta":..., "udv_ctrl":..., "udv_treat":...}, ...],
  "by_booking_platform": [{"booking_platform":..., "deal_count":..., "m1_delta":...}, ...]
}
```

## Tool contract
- `bq` CLI only. `assert_select_only` on every SQL string.
- `company_name` may be merchant placeholder ("Groupon Merchant Services, LLC.") — keep it; `deal_title` is the user-facing value.
- Title enrichment is best-effort: if `deal_option` has no row for a UUID, leave `deal_title=null` / `company_name=null` and the renderer falls back to the URL slug.

## Failure modes
- title-enrichment query fails → continue without titles, set `enrichment_error` in the JSON.
- Empty top winners/losers (e.g. very small experiment) → emit empty arrays; do not error.
