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
| AB-Overall data + stats + verdict | OWN | `bq_queries.ab_overall_raw` against `experiments_jupiter_hist` (pre-aggregated; matches ab-experiments plugin canon) with test_definitions dates → `stats.paired_ttest` → verdict. Date consistency with Filtered. |
| AB-Overall .docx artifact | DELEGATE to `ab-experiments:ab-experiment-evaluation-c3` | Generates official second-opinion .docx. Uses GrowthBook dates (acceptable for this passthrough). |
| AB-Filtered (raw) | OWN | No upstream skill knows about `review_experiments_hist` / deal-scoped pre-aggregation. |
| SRM check | OWN | Use `stats.srm_chi_square`. |
| AB-Overall remediated (active_visitor_flag='Y') | OWN | c3 plugin doesn't surface a remediation path. Use `bq_queries.ab_overall_remediated`, which filters the hist table to `active_visitor_flag='Y'` — the same definition that backed the legacy `active_visitor.is_active_visitor=1` join. DO NOT use `search_visitor_flag`, which is a strict subset (search-acquired traffic only) and produces wildly different M1/UV. |
| AB-Filtered remediated | OWN | Use `bq_queries.ab_filtered_remediated`. |
| PerCategory split | OWN | Group review_experiments_hist rows by experimentname suffix. |

## Steps

1. **AB-Overall data + stats (own).** Run `bq_queries.ab_overall_raw` with `experiment_name`, `start_date`, `end_date`. Aggregate by date × variant. Compute `paired_ttest`, `cohens_d` per variant pair on margin_1_vfm/UV. Verdict per the rules below.
2. **AB-Filtered raw (own).** Run `bq_queries.ab_filtered_raw` with `alternate_name`, `start_date`, `end_date`. Same stats pipeline.

   **Mandatory daily-row shape (both raw.filtered.daily and raw.overall.daily):** every row MUST include the four pre-divided ratio keys `m1uv_ctrl, m1uv_treat, cvr_ctrl, cvr_treat` alongside the raw totals (`uv_ctrl/treat, m1_ctrl/treat, udv_ctrl/treat, orders_ctrl/treat`). Compute `m1uv_<side> = m1_<side> / uv_<side>` and `cvr_<side> = orders_<side> / udv_<side>` per day (guard zero-UV/UDV days with `None`). The exec-summary tiles read these ratios; renderer DOES fall back to deriving them from totals (since 2026-05-11), but **emit them explicitly** so the contract is satisfied at source and downstream consumers don't need to reach for fallbacks. Observed regression 2026-05-11 on `ab_FAQ_reviews.json`: subagent emitted totals only, no ratios; renderer's strict gate at the time returned None and the exec card showed "n/a" for both M1+VFM/UV and CVR despite the data being computable.
3. **SRM check on each view.** Use `stats.srm_chi_square` against expected split (default 50/50; for A/B/C derive from observed variant count). Verdict from `chi_sq.verdict`.
4. **If SRM fail on Filtered:** run `bq_queries.ab_filtered_remediated`, recompute stats. Add to JSON under `remediated.filtered`.
5. **If SRM fail on Overall:** run `bq_queries.ab_overall_remediated`, recompute stats. Add under `remediated.overall`.
6. **PerCategory — Filtered** (always emit, branch on `use_deal_category_split`):
   - **If `use_deal_category_split=TRUE`** — run `bq_queries.category_daily` (slug-keyed: experiment-name suffix `-hbw`/`-ttd`/etc → category). Stamp every emitted `per_category.<cat>` object with `"denominator": "uv"` because rows include session-level `uv` from `review_experiments_hist`.
   - **If `use_deal_category_split=FALSE`** — run `bq_queries.category_daily_by_l2` (keyed by `review_experiments_deal.web_category_level_2`). Sources are deal-scoped, so session-level `uv` is unavailable — the M1 ratio uses `udv` (unique deal-displayers) as denominator. Stamp every emitted `per_category.<cat>` object with `"denominator": "udv"` so the renderer labels columns "M1/UDV" instead of "M1/UV". Per-row daily output has `udv, ue_orders, margin_1_vfm` per `(category, variantname)` — pivot to `m1_ctrl/treat, udv_ctrl/treat, orders_ctrl/treat`, then synthesize `uv_ctrl=udv_ctrl, uv_treat=udv_treat` so renderer code that reads `uv_*` works without branching (the value is deal-scoped UDV; the `denominator` marker tells the truth in the column header).
   - In both branches: compute paired t-test on the chosen M1 ratio (`m1uv_ctrl − m1uv_treat`) and on CVR (`cvr_ctrl − cvr_treat`) per cat. Emit under `per_category.<cat>.{daily,m1uv,cvr,variants,srm,verdict,denominator}`.
   - **Daily rows in `per_category.<cat>.daily` MUST include the underlying totals** (`uv_ctrl, uv_treat, m1_ctrl, m1_treat, udv_ctrl, udv_treat, orders_ctrl, orders_treat`) alongside any pre-divided ratios (`m1uv_ctrl/treat, cvr_ctrl/treat`). The renderer **always** recomputes `m1uv.mean_delta_pct` and `cvr.mean_delta_pct` from these totals as the **aggregate-ratio %Δ** (`SUM(num)/SUM(den)`) — the canonical ab-experiments-plugin metric that matches Groupon dashboards. Any subagent-emitted `mean_delta_pct` is overridden. Emitting only ratios (no totals) produces no displayed %Δ at all — the renderer refuses the daily-mean fallback because it diverges from dashboards by ~0.1–0.2pp.
6a. **PerCategory — Overall** (only if `use_deal_category_split=TRUE`): each split is its own GrowthBook experiment (e.g. `xp-mbnxt-31196-ai-review-summary-hbw`). Discover the sub-experiment names by scanning `experiments_jupiter_hist` for matching prefixes, OR pass an explicit `sub_experiments` list. Run `bq_queries.overall_per_cat_daily` once with the STRUCT array of `{name, cat}`. Compute paired t-test on M1/UV and CVR per cat. Emit under `per_category_overall.<cat>.{daily,m1uv,cvr}` with the same daily-row-shape requirement as 6.
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

### Per-experiment overrides (applied at the SQL layer)

Some experiments are renamed mid-flight and need a fixed mapping so old + new naming halves aggregate as one experiment. These are applied **inside `bq_queries.sql`** via a CASE on `experimentname`, so the SQL output already contains the normalized variantname before this skill sees it:

| Experiment | `experimentname` values matched | Pre-rename | Post-rename | What the SQL emits |
|---|---|---|---|---|
| FAQ reviews 32228 | `xp-mbnxt-32228-web-faq-reviews-section` (jupiter_hist) + `FAQ reviews` + `FAQ reviews - 8k` (review_experiments_hist / _deal) | `true` / `false` | `control` / `treatment` | `control` / `treatment` |

For FAQ reviews specifically, the observed variants will always be `{"control", "treatment"}` (never the original `{"true","false"}`) — apply the first row of the convention table, not the second. Pass `@ctrl_name='control'` to `deal_top_winners_losers` for this experiment. When adding a new override here, also update the CASE statements in `scripts/lib/bq_queries.sql` (every query that reads `variantname`) — and remember the `experimentname` column carries the alternate_name in `review_experiments_hist` / `review_experiments_deal` but the GrowthBook id in `experiments_jupiter_hist`, so include both forms in the IN list.

The `true`/`false` rule reflects how Groupon GrowthBook flags are wired: `true` = original/no-flag-active = control; `false` = override/feature-active = treatment. A naive alphabetic assignment would invert this and flip the sign of every reported delta. Always emit `stats.ctrl_name` and `stats.treat_name` so the renderer can verify the assignment.

⚠️ **DO NOT DEFAULT TO ALPHABETIC for true/false variants.** This has recurred multiple times — most recently 2026-05-12 on FAQ reviews, where the subagent reported %Δ M1+VFM/UV = −1.78% when the canonical convention gives +1.78%. The data was identical; only the sign was wrong. Self-check before emitting JSON:
1. If observed variants include both `"true"` and `"false"`: ctrl_name MUST be `"true"`.
2. Print a one-line sanity check in your summary: `"ctrl=true (M1/UV=X.XX), treat=false (M1/UV=Y.YY) → %Δ=+/-Z%"` so the orchestrator can spot inversions.
3. If `stats.ctrl_name` ends up `"false"` (because you sorted alphabetically), STOP and re-pivot before writing the JSON.

When SRM fails on the raw view AND remediated SRM passes, the renderer will automatically promote the remediated view (active_visitor_flag='Y') to be the primary `raw` block in the rendered scoreboard and HTML — keep emitting both views so this swap is possible. The original raw view is preserved under `raw_pre_remediation` for traceability, and the renderer surfaces both verdicts as `raw fail → active_visitor pass` so the SRM contamination remains visible.

## Runway / time-to-significance

The renderer projects "additional days needed to reach p<0.05" for any view where `p_value > 0.05`, using paired-t scaling (`n_required ≈ n_current × (1.96/|t|)²`). This is back-of-envelope, not a formal power analysis — it surfaces the "is it worth running longer?" decision. You don't need to compute this yourself; just emit `t_stat` and `p_value` (and `cohens_d`) inside `stats.m1uv` and the renderer handles the projection.

## Tool contract

- All SQL through `assert_select_only`. No MCP. No Okta.
- Use test_definitions dates for our analysis (NOT GrowthBook dates) to keep Filtered/Overall consistent.

### Date window is LOCKED — no trimming, no ramp-up dropping

The `start_date` and `end_date` passed in by the orchestrator come straight from `test_definitions` and are the single source of truth for every view in this skill.

**Hard rules:**
- Pass `@start_date` and `@end_date` to every BQ query verbatim. Do NOT add a ramp-up offset, "warm-up trim," or any first-/last-day exclusion.
- The emitted `raw.filtered.daily` and `raw.overall.daily` arrays MUST cover every calendar date in `[start_date, end_date]` for which the source table returns rows. Do not drop days because traffic was low, because the experiment "looked unstable early," or because daily SUM was zero — emit the zero-row day as-is so the renderer's paired t-test and SRM run on the full window.
- For closed experiments, this guarantees byte-identical SUMs across reruns. Any per-run drift indicates a contract violation in this skill and must be fixed here, not papered over in the renderer.
- If a per-category sub-view legitimately has no rows for a date in the window (e.g. the category had zero deal-views that day), emit the day with zero metrics rather than skipping it.

The same locked-window contract applies to `per_category[*].daily`, `per_category_overall[*].daily`, `remediated.filtered.daily`, and `remediated.overall.daily`.

## Failure modes
- `active_visitor_flag` column missing in review_experiments_hist → skip Filtered remediation, set `srm.filtered.remediation_unavailable=true`.
- bq query failure → retry once with 2× timeout, mark view as failed.
- c3 passthrough .docx failure → record error, continue (non-blocking).
