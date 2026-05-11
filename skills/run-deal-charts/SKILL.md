---
name: run-deal-charts
description: Compute AI-summary-style deal-level charts (top winners/losers, by category, by booking platform) from review_experiments_deal. Enriches top winners/losers with company_name + deal_title from deal_option so the renderer can show clickable, human-readable rows. Invoked by orchestrator-workflow as a subagent.
---

# run-deal-charts

## Inputs
- `alternate_name`, `start_date`, `end_date`: required
- `ctrl_name`: optional override for the control variant name. If omitted, query the experiment data once and apply the canonical convention (see below) to pick it.
- `out_path`: where to write deal_<alt_name>.json

## Variant naming convention

Match `run-ab-evaluation/SKILL.md`:

| Variants observed | Control |
|---|---|
| `{"control", "treatment"}` | `control` |
| `{"true", "false"}` | `true` |
| anything else | alphabetic first |

`bq_queries.deal_top_winners_losers` requires `@ctrl_name` as a parameter — pass the canonical control value. When pivoting `deal_by_category` and `deal_by_booking_platform` results in this skill, use the same `ctrl_name` as the IF-pivot key. **Always emit `ctrl_name` at the top level of the output JSON** so the renderer can detect the convention used and align with sibling AB output.

## Steps

1. **Resolve ctrl_name.** If not provided, run `SELECT DISTINCT variantname FROM out_c_10_review_ab_experiments.review_experiments_hist WHERE event_date BETWEEN @start_date AND @end_date AND (experimentname = @alternate_name OR ...)` and apply the convention table above.
2. Run `bq_queries.deal_top_winners_losers` with `@ctrl_name=<resolved>` → split into `top_winners` (m1_delta DESC, top 10) and `top_losers` (m1_delta ASC, top 10).
3. Run `bq_queries.deal_by_category` → pivot rows where `variantname = ctrl_name` into `*_ctrl` and the other variant into `*_treat`. Compute per-category deltas (cvr_treat - cvr_ctrl, m1_treat - m1_ctrl).
4. **Enrich titles.** Collect the union of UUIDs across `top_winners` + `top_losers`. Run a single lookup against `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option` selecting `MAX(company_name)` and `MAX(deal_creative_content_title)` per `deal_uuid`. Merge results back into the rows so each contains `company_name` and `deal_title`.
4. Write JSON:

```json
{
  "alternate_name": "...",
  "ctrl_name": "control|true|...",
  "top_winners": [{"deal_uuid":..., "deal_url":..., "category":..., "m1_delta":..., "company_name":..., "deal_title":...}, ...],
  "top_losers":  [...],
  "by_category": [{"category":..., "cvr_delta":..., "m1_delta":..., "udv_ctrl":..., "udv_treat":...}, ...]
}
```

## Tool contract
- `bq` CLI only. `assert_select_only` on every SQL string.
- `company_name` may be merchant placeholder ("Groupon Merchant Services, LLC.") — keep it; `deal_title` is the user-facing value.
- Title enrichment is best-effort: if `deal_option` has no row for a UUID, leave `deal_title=null` / `company_name=null` and the renderer falls back to the URL slug.
- **Date window is LOCKED to test_definitions.** Pass `@start_date` and `@end_date` verbatim — no ramp-up trim, no early/late exclusion. For closed experiments this guarantees identical winners/losers/by-category across reruns.

## Failure modes
- title-enrichment query fails → continue without titles, set `enrichment_error` in the JSON.
- Empty top winners/losers (e.g. very small experiment) → emit empty arrays; do not error.
