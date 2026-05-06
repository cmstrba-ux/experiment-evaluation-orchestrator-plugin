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

1. **AB-Overall data + stats (own).** Run `bq_queries.ab_overall_raw` with `experiment_name`, `start_date`, `end_date`. Aggregate by date × variant. Compute `paired_ttest`, `cohens_d` per variant pair on margin_1_vfm/UV. Verdict per the rules below.
2. **AB-Filtered raw (own).** Run `bq_queries.ab_filtered_raw` with `alternate_name`, `start_date`, `end_date`. Same stats pipeline.
3. **SRM check on each view.** Use `stats.srm_chi_square` against expected split (default 50/50; for A/B/C derive from observed variant count). Verdict from `chi_sq.verdict`.
4. **If SRM fail on Filtered:** run `bq_queries.ab_filtered_remediated`, recompute stats. Add to JSON under `remediated.filtered`.
5. **If SRM fail on Overall:** run `bq_queries.ab_overall_remediated`, recompute stats. Add under `remediated.overall`.
6. **PerCategory — Filtered** (always emit, branch on `use_deal_category_split`):
   - **If `use_deal_category_split=TRUE`** — run `bq_queries.category_daily` (slug-keyed: experiment-name suffix `-hbw`/`-ttd`/etc → category). Stamp every emitted `per_category.<cat>` object with `"denominator": "uv"` because rows include session-level `uv` from `review_experiments`.
   - **If `use_deal_category_split=FALSE`** — run `bq_queries.category_daily_by_l2` (keyed by `review_experiments_deal.web_category_level_2`). Sources are deal-scoped, so session-level `uv` is unavailable — the M1 ratio uses `udv` (unique deal-displayers) as denominator. Stamp every emitted `per_category.<cat>` object with `"denominator": "udv"` so the renderer labels columns "M1/UDV" instead of "M1/UV". Per-row daily output has `udv, ue_orders, margin_1_vfm` per `(category, variantname)` — pivot to `m1_ctrl/treat, udv_ctrl/treat, orders_ctrl/treat`, then synthesize `uv_ctrl=udv_ctrl, uv_treat=udv_treat` so renderer code that reads `uv_*` works without branching (the value is deal-scoped UDV; the `denominator` marker tells the truth in the column header).
   - In both branches: compute paired t-test on the chosen M1 ratio (`m1uv_ctrl − m1uv_treat`) and on CVR (`cvr_ctrl − cvr_treat`) per cat. Emit under `per_category.<cat>.{daily,m1uv,cvr,variants,srm,verdict,denominator}`.
   - **Daily rows in `per_category.<cat>.daily` MUST include the underlying totals** (`uv_ctrl, uv_treat, m1_ctrl, m1_treat, udv_ctrl, udv_treat, orders_ctrl, orders_treat`) alongside any pre-divided ratios (`m1uv_ctrl/treat, cvr_ctrl/treat`). The renderer **always** recomputes `m1uv.mean_delta_pct` and `cvr.mean_delta_pct` from these totals as the **aggregate-ratio %Δ** (`SUM(num)/SUM(den)`) — the canonical ab-experiments-plugin metric that matches Groupon dashboards. Any subagent-emitted `mean_delta_pct` is overridden. Emitting only ratios (no totals) produces no displayed %Δ at all — the renderer refuses the daily-mean fallback because it diverges from dashboards by ~0.1–0.2pp.
6a. **PerCategory — Overall** (only if `use_deal_category_split=TRUE`): each split is its own GrowthBook experiment (e.g. `xp-mbnxt-31196-ai-review-summary-hbw`). Discover the sub-experiment names by scanning the bcookie experiment table for matching prefixes, OR pass an explicit `sub_experiments` list. Run `bq_queries.overall_per_cat_daily` once with the STRUCT array of `{name, cat}`. Compute paired t-test on M1/UV and CVR per cat. Emit under `per_category_overall.<cat>.{daily,m1uv,cvr}` with the same daily-row-shape requirement as 6.
7. **Verdict** — emit per the canonical c3 rule (primary KPI = Margin per Visitor):

   | Verdict | When |
   |---|---|
   | **SHIP** | p<0.05 on primary, positive direction, consistent across platforms, no CVR guardrail breach |
   | **HOLD** | Positive direction with p∈[0.05, 0.15] AND days-to-significance ≤ 56d (≤ 8 weeks) |
   | **KILL** | Negative direction, OR p>0.15 with infeasible runway, OR observed effect too small to matter (Cohen's |d|<0.05 with no CVR signal) |

   This matches `ab-experiments:ab-experiment-evaluation-c3`'s table — the c3 .docx and the orchestrator JSON should agree on verdict. If they diverge, the c3 narrative is authoritative.

8. **Label is computed by the renderer**, not by this skill. Emit `label` as a hint for traceability, but the rendered scoreboard uses the renderer's `_compute_label(end_date, data_through, n_days, verdict, runway, primary_p)` rule:

   | Label | When |
   |---|---|
   | **PRELIMINARY** | `end_date >= data_through` (still in-flight) OR `n_days < 7` |
   | **FINAL** | Ended AND verdict=HOLD AND runway is feasible (`additional_days ≤ 56`) — could be extended |
   | **FINAL — can be closed** | All other ended cases — significant primary, SHIP, KILL, or HOLD with infeasible runway |

   The renderer is authoritative so the label stays internally consistent with the runway column shown in the scoreboard. A subagent-emitted `label` will be ignored if it contradicts the rule above (preserved in `ab_label_subagent` for debugging).

9. **Persistent SRM:** if SRM still fails after remediation → mark verdict `INCONCLUSIVE — persistent SRM`.
10. **Passthrough .docx (delegate).** Spawn a subagent to invoke `ab-experiments:evaluate-experiment` with `experiment_name` as $ARGUMENTS. Save the .docx output to `<passthrough_dir>/<alternate_name>.docx`. If it fails, record `passthrough_docx_error` but don't block the main eval.
11. **Write JSON** to `out_path`:

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
  "per_category": {  // FILTERED, deal-scoped — always emitted. Slug-keyed (HBW/TTD/...) when
    // use_deal_category_split=TRUE; L2-keyed (web_category_level_2) otherwise. The
    // `denominator` field tells the renderer whether to label the M1 ratio as M1/UV ("uv")
    // or M1/UDV ("udv").
    "Food & Drink": {"daily":[...], "m1uv":{mean_delta,mean_delta_pct,p_value,n}, "cvr":{...}, "variants":{...}, "srm":{...}, "verdict":"...", "denominator":"uv|udv"},
    "Automotive":   {...}
  },
  "per_category_overall": {  // OVERALL, population-wide — present only when use_deal_category_split=TRUE
    "Food & Drink": {"daily":[...], "m1uv":{...}, "cvr":{...}},
    "Automotive":   {...}
  },
  "passthrough_docx": "<path>"  // optional
}
```

## Variant naming convention

When you assign which variant is control vs. treatment from `variantname` values, follow this convention. The renderer assumes JSONs follow it; mismatches are auto-swapped, but get this right at source so SRM-fail remediation logic and downstream consumers (scoreboard, headline KPIs, .docx passthrough) stay aligned.

| Variants observed | Control | Treatment |
|---|---|---|
| `{"control", "treatment"}` | `control` | `treatment` |
| `{"true", "false"}` | **`true`** | **`false`** |
| `{"A", "B"}` (or any other pair) | alphabetic first | other |

The `true`/`false` rule reflects how Groupon GrowthBook flags are wired: `true` = original/no-flag-active = control; `false` = override/feature-active = treatment. A naive alphabetic assignment would invert this and flip the sign of every reported delta. Always emit `stats.ctrl_name` and `stats.treat_name` so the renderer can verify the assignment.

When SRM fails on the raw view AND remediated SRM passes, the renderer will automatically promote the remediated view (active_visitor_flag='Y') to be the primary `raw` block in the rendered scoreboard and HTML — keep emitting both views so this swap is possible. The original raw view is preserved under `raw_pre_remediation` for traceability, and the renderer surfaces both verdicts as `raw fail → active_visitor pass` so the SRM contamination remains visible.

## Runway / time-to-significance

The renderer projects "additional days needed to reach p<0.05" for any view where `p_value > 0.05`, using paired-t scaling (`n_required ≈ n_current × (1.96/|t|)²`). This is back-of-envelope, not a formal power analysis — it surfaces the "is it worth running longer?" decision. You don't need to compute this yourself; just emit `t_stat` and `p_value` (and `cohens_d`) inside `stats.m1uv` and the renderer handles the projection.

## Tool contract

- All SQL through `assert_select_only`. No MCP. No Okta.
- Use test_definitions dates for our analysis (NOT GrowthBook dates) to keep Filtered/Overall consistent.

## Failure modes
- `active_visitor_flag` column missing in review_experiments → skip Filtered remediation, set `srm.filtered.remediation_unavailable=true`.
- bq query failure → retry once with 2× timeout, mark view as failed.
- c3 passthrough .docx failure → record error, continue (non-blocking).
