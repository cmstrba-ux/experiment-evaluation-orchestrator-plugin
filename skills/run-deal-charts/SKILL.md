---
name: run-deal-charts
description: Compute AI-summary-style deal-level charts (top winners/losers, by category, by booking platform) from review_experiments_deal. Invoked by orchestrator-workflow as a subagent.
---

# run-deal-charts

## Inputs
- `alternate_name`, `start_date`, `end_date`: required
- `out_path`: where to write deal_<alt_name>.json

## Steps

1. Run `bq_queries.deal_top_winners_losers` with parameters → split into `top_10_winners` (m1_delta DESC) and `top_10_losers` (m1_delta ASC).
2. Run `bq_queries.deal_by_category` → compute per-category deltas (CVR_treat - CVR_ctrl, m1_treat - m1_ctrl).
3. Run `bq_queries.deal_by_booking_platform` → per-platform breakdown.
4. Write JSON:

```json
{
  "alternate_name": "...",
  "top_winners": [{"deal_uuid":..., "deal_url":..., "category":..., "m1_delta":...}, ...],
  "top_losers":  [...],
  "by_category": [{"category":..., "cvr_delta":..., "m1_delta":..., "udv_ctrl":..., "udv_treat":...}, ...],
  "by_booking_platform": [{"booking_platform":..., "deal_count":..., "m1_delta":...}, ...]
}
```

## Tool contract
- `bq` CLI only. `assert_select_only` on every SQL string.
