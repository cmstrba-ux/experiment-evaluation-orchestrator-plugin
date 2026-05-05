---
name: run-ab-evaluation
description: Coordinator that produces both AB-Filtered (deal-scoped) and AB-Overall (population-wide) views for one experiment, with SRM auto-remediation. Owns the analysis with explicit test_definitions dates for consistency between views; invokes ab-experiments:ab-experiment-evaluation-c3 only as a passthrough .docx generator.
---

# run-ab-evaluation

## Inputs
- `alternate_name`, `experiment_name`, `start_date`, `end_date`, `use_deal_category_split`, `out_path`, `passthrough_dir`

## What this skill does itself vs. delegates

| View / step | Owner | Notes |
|---|---|---|
| AB-Overall data + stats + verdict | OWN | `bq_queries.ab_overall_raw` with test_definitions dates → `stats.paired_ttest` → verdict. Date consistency with Filtered. |
| AB-Overall .docx artifact | DELEGATE to `ab-experiments:ab-experiment-evaluation-c3` | Generates official second-opinion .docx. Uses GrowthBook dates (acceptable for this passthrough). |
| AB-Filtered (raw) | OWN | No upstream skill knows about `review_experiments` / deal-scoped pre-aggregation. |
| SRM check | OWN | Use `stats.srm_chi_square`. |
| AB-Overall remediated (active_visitor only) | OWN | c3 doesn't accept active_visitor filter. Use `bq_queries.ab_overall_remediated`. |
| AB-Filtered remediated | OWN | Use `bq_queries.ab_filtered_remediated`. |
| PerCategory split | OWN | Group review_experiments rows by experimentname suffix. |

## Steps

1. **AB-Overall data + stats (own).** Run `bq_queries.ab_overall_raw` with `experiment_name`, `start_date`, `end_date`. Aggregate by date × variant. Compute `paired_ttest`, `cohens_d` per variant pair on margin_1_vfm/UV. Verdict per spec §5.
2. **AB-Filtered raw (own).** Run `bq_queries.ab_filtered_raw` with `alternate_name`, `start_date`, `end_date`. Same stats pipeline.
3. **SRM check on each view.** Use `stats.srm_chi_square` against expected split (default 50/50; for A/B/C derive from observed variant count). Verdict from `chi_sq.verdict`.
4. **If SRM fail on Filtered:** run `bq_queries.ab_filtered_remediated`, recompute stats. Add to JSON under `remediated.filtered`.
5. **If SRM fail on Overall:** run `bq_queries.ab_overall_remediated`, recompute stats. Add under `remediated.overall`.
6. **PerCategory — Filtered** (only if `use_deal_category_split=TRUE`): run `bq_queries.category_daily` to get daily per-category × variant deal-scoped stats. Compute paired t-test on M1/UV and CVR per cat. Emit under `per_category.<cat>.{daily,m1uv,cvr,variants,srm,verdict}`.
   - **Daily rows in `per_category.<cat>.daily` MUST include the underlying totals** (`uv_ctrl, uv_treat, m1_ctrl, m1_treat, udv_ctrl, udv_treat, orders_ctrl, orders_treat`) alongside any pre-divided ratios (`m1uv_ctrl/treat, cvr_ctrl/treat`). The renderer uses these to compute the **aggregate-ratio %Δ** (`SUM(num)/SUM(den)`) which is the canonical ab-experiments-plugin metric and matches Groupon dashboards. Emitting only daily ratios produces a daily-mean pct that diverges from the dashboards by ~0.1–0.2pp when daily UV varies.
6a. **PerCategory — Overall** (only if `use_deal_category_split=TRUE`): each split is its own GrowthBook experiment (e.g. `xp-mbnxt-31196-ai-review-summary-hbw`). Discover the sub-experiment names by scanning the bcookie experiment table for matching prefixes, OR pass an explicit `sub_experiments` list. Run `bq_queries.overall_per_cat_daily` once with the STRUCT array of `{name, cat}`. Compute paired t-test on M1/UV and CVR per cat. Emit under `per_category_overall.<cat>.{daily,m1uv,cvr}` with the same daily-row-shape requirement as 6.
7. **Verdict + Label** per spec §5 (FINAL / FINAL — can be closed / PRELIMINARY).
8. **Persistent SRM:** if SRM still fails after remediation → mark verdict `INCONCLUSIVE — persistent SRM`.
9. **Passthrough .docx (delegate).** Spawn a subagent to invoke `ab-experiments:evaluate-experiment` with `experiment_name` as $ARGUMENTS. Save the .docx output to `<passthrough_dir>/<alternate_name>.docx`. If it fails, record `passthrough_docx_error` but don't block the main eval.
10. **Write JSON** to `out_path`:

```json
{
  "alternate_name": "...",
  "label": "PRELIMINARY|FINAL|FINAL — can be closed",
  "srm": {
    "filtered": {"verdict":"pass|fail", "chi_sq":..., "p_value":..., "observed":..., "expected_n":...},
    "overall":  {"verdict":"pass|fail", ...}
  },
  "raw": {
    "filtered": {"daily":[...], "variants":[...], "stats":{...}, "verdict":"SHIP|HOLD|KILL"},
    "overall":  {"daily":[...], "variants":[...], "stats":{...}, "verdict":"..."}
  },
  "remediated": {  // present only when SRM triggered remediation
    "filtered": {...},
    "overall":  {...}
  },
  "per_category": {  // FILTERED, deal-scoped — present only when use_deal_category_split=TRUE
    "Food & Drink": {"daily":[...], "m1uv":{mean_delta,mean_delta_pct,p_value,n}, "cvr":{...}, "variants":{...}, "srm":{...}, "verdict":"..."},
    "Automotive":   {...}
  },
  "per_category_overall": {  // OVERALL, population-wide — present only when use_deal_category_split=TRUE
    "Food & Drink": {"daily":[...], "m1uv":{...}, "cvr":{...}},
    "Automotive":   {...}
  },
  "passthrough_docx": "<path>"  // optional
}
```

## Tool contract

- All SQL through `assert_select_only`. No MCP. No Okta.
- Use test_definitions dates for our analysis (NOT GrowthBook dates) to keep Filtered/Overall consistent.

## Failure modes
- `active_visitor_flag` column missing in review_experiments → skip Filtered remediation, set `srm.filtered.remediation_unavailable=true`.
- bq query failure → retry once with 2× timeout, mark view as failed.
- c3 passthrough .docx failure → record error, continue (non-blocking).
