---
name: ab-experiment-evaluation-c3
description: "Use this skill whenever you are asked to evaluate an A/B or A/B/C experiment using BigQuery data. Triggers include: 'evaluate this experiment', 'analyze experiment results', 'should we ship this test', 'run experiment analysis', or any reference to experiment variants (control/treatment), metrics like margin_1_vfm, ue_orders, UV, or experiment names matching patterns like 'xp-*'. This skill covers the full pipeline: data quality filtering, overall and platform-level results, statistical significance testing (paired t-test on daily data), power analysis, behavioral interpretation, business impact estimation, and a final SHIP/HOLD/KILL recommendation. Always produce a formatted Word document (.docx) as the final deliverable."
---

# A/B Experiment Evaluation Skill

## Purpose

Evaluate A/B or A/B/C experiments using BigQuery aggregated data and return a decision based on M1+VFM impact (stored as `margin_1_vfm`). The evaluation must be statistically rigorous, platform-aware, and clearly communicate uncertainty in all business impact projections.

---

## Metric Definitions (Use Full Names Always)

Never use shorthand abbreviations in outputs. Always spell out the full metric name.

The four metrics below are the **default evaluation set**. For a different primary metric, select from the **Full Metrics Catalog** below.

| Full Name | Formula | Description |
|---|---|---|
| **Conversion Rate** | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | Percentage of visitors who completed an order |
| **Margin per Visitor** ★ Primary KPI | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))` | Average M1+VFM generated per visitor. This is the primary decision-making KPI. |
| **Revenue per Visitor** | `SAFE_DIVIDE(SUM(gross_revenue), SUM(UV))` | Average gross revenue generated per visitor |
| **Margin per Order** | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(ue_orders))` | Average M1+VFM per successful order — reflects the profitability of individual transactions |

Use `SAFE_DIVIDE` for all divisions to avoid division-by-zero errors.

---

## Full Metrics Catalog

All available metrics from `experiments_jupiter_hist`. For full interpretation guidance see the evaluation skill catalog. Use `SAFE_DIVIDE` for all ratio metrics.

**Traffic & Visitor**

| Metric | Formula | What it tells you |
|---|---|---|
| Unique Visitors | `SUM(UV)` | Primary traffic denominator for all per-visitor rates |
| Unique Deal Viewers | `SUM(UDV)` | Visitors who reached a deal detail page — if ↓, discovery is the problem |
| **Deal View Rate** | `SAFE_DIVIDE(SUM(UDV), SUM(UV))` | Upper-funnel engagement. ↓ = suppression at search/listing/homepage level |
| Logged-in Visitors | `SUM(uv_logged_in)` | |
| Logged-out Visitors | `SUM(uv_logged_out)` | |
| Distinct bCookies | `SUM(distinct_bcookie_count)` | Secondary SRM check — use alongside UV split |

**Funnel Progression**

| Metric | Formula | What it tells you |
|---|---|---|
| **Checkout Entry Rate** | `SAFE_DIVIDE(SUM(CV_views), SUM(UV))` | ★ All-visitor checkout rate. ↓ = intent suppression before checkout. Guardrail for all experiments. |
| **Checkout per Deal Viewer** *(new)* | `SAFE_DIVIDE(SUM(CV_views), SUM(UDV))` | ★ PDP-to-checkout rate. If Deal View Rate is flat but this ↓, problem is on the deal detail page. |
| **Checkout-to-Order Rate** *(new)* | `SAFE_DIVIDE(SUM(ue_orders), SUM(CV_views))` | ★ Purchase completion inside checkout. ↓ = checkout friction. Primary for checkout/UX experiments. |
| Checkout Entry Rate (unique) | `SAFE_DIVIDE(SUM(CV_viewers), SUM(UV))` | ⚠️ Verify `SUM(CV_viewers) > 0` before use |
| Logged-in Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_in), SUM(uv_logged_in))` | |
| Logged-out Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_out), SUM(uv_logged_out))` | |
| Checkout Views (raw) | `SUM(CV_views)` | Volume context only |

**Orders**

| Metric | Formula | What it tells you |
|---|---|---|
| Orders | `SUM(ue_orders)` | Finance-approved volume — always prefer over `orders_placed` |
| **Conversion Rate** | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | Overall purchase rate. Blunt alone — use Checkout-to-Order Rate to isolate checkout step. |
| **Refund Rate** | `SAFE_DIVIDE(SUM(ue_orders_refunds), SUM(ue_orders))` | ★ Tier-1 quality guardrail. ↑ = lower-quality orders (buy + regret). |
| **Cancellation Rate** | `SAFE_DIVIDE(SUM(orders_cancelled), SUM(ue_orders))` | Post-purchase regret. More relevant for bookable deals. |
| **Promo Order Rate** | `SAFE_DIVIDE(SUM(ue_orders_with_promo), SUM(ue_orders))` | ↑ alongside ↑ CVR = check whether lift is real or promo-driven. |
| Logged-in CVR | `SAFE_DIVIDE(SUM(ue_orders_logged_in), SUM(uv_logged_in))` | |
| Logged-out CVR | `SAFE_DIVIDE(SUM(ue_orders_logged_out), SUM(uv_logged_out))` | |
| Authenticated Orders | `SUM(ue_orders_auth)` | |
| Canadian Orders | `SUM(ue_orders_can)` | |
| Promo Orders (raw) | `SUM(ue_orders_with_promo)` | |
| Refunds (raw) | `SUM(ue_orders_refunds)` | |
| Cancellations (raw) | `SUM(orders_cancelled)` | |

**Revenue & Margin**

| Metric | Formula | What it tells you |
|---|---|---|
| **Margin per Visitor (M1+VFM)** | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))` | ★ Primary decision KPI. Captures both conversion volume and transaction quality. |
| **Revenue per Visitor** | `SAFE_DIVIDE(SUM(gross_revenue), SUM(UV))` | Guardrail companion to MPV. Divergence reveals margin economics shift. |
| **Margin per Order** | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(ue_orders))` | Transaction profitability. MPV ↑ + this flat → volume drove the gain, not quality. |
| **VFM per Order** *(new)* | `SAFE_DIVIDE(SUM(vfm), SUM(ue_orders))` | Merchant-side economics per transaction. Decomposes Margin per Order into M1 vs. VFM. |
| **Promo Spend per Order** | `SAFE_DIVIDE(SUM(promo_spend), SUM(ue_orders))` | Cost of promotional lift. ↑ = margin-dilutive orders. |
| Revenue per Order (AOV) | `SAFE_DIVIDE(SUM(gross_revenue), SUM(ue_orders))` | Average transaction size. Recompute — do not use precomputed `AOV` column. |
| Bookings per Visitor | `SAFE_DIVIDE(SUM(gross_bookings), SUM(UV))` | |
| Total M1+VFM | `SUM(margin_1_vfm)` | Business impact estimates only — not for winner selection |
| Total Gross Revenue | `SUM(gross_revenue)` | |
| Total Gross Bookings | `SUM(gross_bookings)` | |
| VFM Component (total) | `SUM(vfm)` | |
| Promo Spend (total) | `SUM(promo_spend)` | |
| OD (Overhead & Discounts) | `SUM(od)` | |

---

## Synonyms (Core → Normalized)

Always interpret metrics using the original source fields. If downstream queries rename them, treat them as aliases only.

### Core fields (source of truth)

| Concept | Source Field |
|---|---|
| Visitors | `UV` |
| Orders (finance truth) | `ue_orders` |
| Margin / Primary KPI (M1+VFM) | `margin_1_vfm` |
| Revenue | `gross_revenue` |
| Platform | `clientPlatform` — values: `touch` (mobile web), `web` (desktop web), `iphone` (iOS app), `android` (Android app), `ipad` (iPad app), `email` (email click-throughs) |
| Variant | `variantname` |
| Date | `event_date` |
| Experiment filter | `experimentname` |

### Acceptable normalized aliases

| Alias | Derived from |
|---|---|
| visitors | `SUM(UV)` |
| orders | `SUM(ue_orders)` |
| margin | `SUM(margin_1_vfm)` |
| revenue | `SUM(gross_revenue)` |

### Excluded / Avoided Fields

- `orders_placed` — use `ue_orders` (finance truth) instead
- Any precomputed or derived margin fields if `margin_1_vfm` exists
- Any derived date fields if `event_date` is available
- Precomputed `CVR` column — always recompute from `ue_orders / UV`

---

## Filtering & Grouping Rules

### Default aggregation level

Aggregate to daily facts:

```
DATE(event_date) × LOWER(TRIM(clientPlatform)) × LOWER(TRIM(variantname))
```

### Data quality filtering (mandatory)

Exclude low-volume glitch rows in the `HAVING` clause:

```sql
HAVING SUM(UV) >= 1000
```

Also exclude rows where `SUM(UV) = 0`.

### Primary data source (mandatory)

Always use this fully qualified table as the first and main source for all queries:

```
`kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
```

Never substitute a different table unless the user explicitly requests it. All steps in this skill default to querying this table.

### Experiment scope

```sql
WHERE experimentname = '<experiment_id>'
```

---

## Pre-Analysis: Context Gathering

Before running any queries, gather context from two sources. This enriches the behavioral mechanism analysis and surfaces critical configuration details that affect interpretation.

### Jira ticket lookup

Search Atlassian for the experiment ID (e.g., `MBNXT-27180`). Extract:
- Exact variant labels (what text each button/element actually shows)
- Experiment scope (which deal types, pages, or user segments are included)
- Hypothesis stated by the product team
- Assignee and Jira status
- Any implementation constraints (e.g., "not cached in Redis", "applies to non-bookable deals only")

Use `Atlassian:getJiraIssue` with the issue key derived from the experiment name.

### A/A Baseline Variance Lookup (Run Before Any Experiment Queries)

**Purpose:** Pull natural metric variance from the dedicated A/A experiments so that power analysis (Step 6) uses a treatment-free σ baseline rather than within-experiment variance. This produces more accurate MDE estimates and richer noise-floor context in the statistical results.

**A/A experiment identifiers (hardcoded — do not change unless new A/A tests replace these):**

| Platform | A/A Experiment Name |
|---|---|
| desktop | `xp-MBNXT-30862-AA-test-desktop` |
| touch | `xp-MBNXT-30862-AA-test-touch` |

**Query — run once before any experiment-specific queries:**

```sql
SELECT
  experimentname,
  STDDEV_SAMP(daily_cvr)  AS sigma_cvr,
  STDDEV_SAMP(daily_cer)  AS sigma_cer,
  STDDEV_SAMP(daily_mpv)  AS sigma_mpv,
  AVG(daily_cvr)          AS mean_cvr,
  AVG(daily_cer)          AS mean_cer,
  AVG(daily_mpv)          AS mean_mpv,
  COUNT(*)                AS aa_days
FROM (
  SELECT
    experimentname,
    DATE(event_date) AS day,
    SAFE_DIVIDE(SUM(ue_orders),    SUM(UV)) AS daily_cvr,
    SAFE_DIVIDE(SUM(CV_views),     SUM(UV)) AS daily_cer,
    SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV)) AS daily_mpv
  FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
  WHERE experimentname IN (
    'xp-MBNXT-30862-AA-test-desktop',
    'xp-MBNXT-30862-AA-test-touch'
  )
    AND LOWER(TRIM(variantname)) = 'control'
  GROUP BY experimentname, DATE(event_date)
  HAVING SUM(UV) >= 1000
)
GROUP BY experimentname
```

**Map results to platforms:**

| experimentname | → Platform bucket | `clientPlatform` values covered |
|---|---|---|
| `xp-MBNXT-30862-AA-test-desktop` | `web` | `web` |
| `xp-MBNXT-30862-AA-test-touch` | `touch` | `touch` |
| *(no A/A test)* | `app` | `iphone`, `android`, `ipad` — use within-experiment σ fallback; add note: *"⚠️ No A/A baseline for app platform."* |

**Fallback:** If A/A experiments return no rows, fall back to within-experiment control-arm σ and note: *"⚠️ A/A baseline unavailable — σ estimated from experiment control arm. Power analysis may be less accurate."*

**Maturity flag:** If `aa_days < 14`, add a note: *"A/A baseline based on N days — estimates will tighten as the A/A test accumulates more observations."*

### GrowthBook experiment lookup

Use `GrowthBook:get_experiments` with the GrowthBook experiment ID (found in the Jira ticket or known from naming conventions). Use `mode: full` to get complete configuration. Extract and report:

| Field | Why It Matters |
|---|---|
| `status` | Is the experiment still running? If `running` with no `dateEnded`, the team must manually stop it after a decision — GrowthBook will not stop it automatically. |
| `phases[0].targetingCondition` | Defines the eligible population (e.g., US-only). All visitor and margin figures are scoped to this population — call this out explicitly in the report. |
| `settings.goals` / `settings.guardrails` | If empty, GrowthBook has **no metrics configured** and will show "No data" in its UI despite the experiment running. All analysis must be BigQuery-driven. Flag this as a process gap. |
| `settings.statsEngine` | Bayesian vs. Frequentist — note which engine GrowthBook is configured to use, even if no metrics are attached. |
| `settings.attributionModel` | First Exposure vs. other — relevant for understanding how margin is attributed. |
| `settings.regressionAdjustmentEnabled` | Note if CUPED/regression adjustment is on. |
| `hashAttribute` | Confirms the bucketing key (bCookie, userId, etc.). |
| `phases[0].trafficSplit` | Cross-check against the observed BigQuery split for SRM validation. |
| `variations[].screenshots` | Screenshots exist in GrowthBook — reference them in the report as available in the GrowthBook UI (do not attempt to embed them; presigned URLs expire quickly). |
| `dateCreated` vs. `phases[0].dateStarted` | The gap between ticket creation and experiment launch is worth noting in the Notes section. |

**If GrowthBook has no metrics configured:** Add a prominent warning to the report's GrowthBook Configuration section. The experiment will show "No data" in GrowthBook's UI, and GrowthBook will not surface a recommendation. The team must rely entirely on BigQuery analysis and must manually stop the experiment.

---

## Evaluation Steps

### Step 1 — Traffic Split Sanity Check (Sample Ratio Mismatch)

Compute visitor share by variant:
- A/B: expected ~50/50
- A/B/C: expected ~33/33/33

If split is materially off (>2pp deviation), flag instrumentation risk and do not proceed to conclusions without noting the caveat.

If split is clean, state: **"No SRM detected — traffic split is clean."**

---

### Step 2 — Overall Results

Aggregate across the full test period for each variant. Compute all four core metrics plus percentage uplift vs. control:

| Metric | Formula |
|---|---|
| Conversion Rate | `SUM(ue_orders) / SUM(UV)` |
| Margin per Visitor | `SUM(margin_1_vfm) / SUM(UV)` |
| Revenue per Visitor | `SUM(gross_revenue) / SUM(UV)` |
| Margin per Order | `SUM(margin_1_vfm) / SUM(ue_orders)` |

**Important:** When comparing total margin across variants, always note whether differences are driven by traffic size vs. per-visitor efficiency. Total margin advantage from more visitors is not a valid basis for declaring a winner — Margin per Visitor (the efficiency metric) is the deciding KPI.

---

### Step 3 — Platform Results (Mandatory)

Repeat Step 2 separately for each of the three platform buckets:

| Bucket | `clientPlatform` values | SQL filter |
|--------|------------------------|------------|
| `touch` | `touch` | `LOWER(TRIM(clientPlatform)) = 'touch'` |
| `web` | `web` | `LOWER(TRIM(clientPlatform)) = 'web'` |
| `app` | `iphone`, `android`, `ipad` | `LOWER(TRIM(clientPlatform)) IN ('iphone', 'android', 'ipad')` |

> **`email` traffic**: Exclude — email sessions are click-throughs with atypically high purchase intent that distort CVR and MPV. Filter with `LOWER(TRIM(clientPlatform)) != 'email'` or exclude explicitly.

> **App A/A baseline**: No A/A test exists for the app platform. Use within-experiment control-arm σ as fallback for Step 6 power analysis on the app bucket, and note: *"⚠️ No A/A baseline for app platform — σ estimated from experiment control arm."*

**Winner selection — primary KPI: Margin per Visitor**

Winner = variant with highest Margin per Visitor, subject to:
- Conversion Rate should not drop meaningfully
- Results should be directionally consistent across platforms

If the overall winner differs by platform, call out Simpson's paradox risk and recommend deeper validation or segmented rollout.

---

### Step 4 — Stability Analysis

For each day compute:

```
delta_mpv_variant = Margin per Visitor (variant) − Margin per Visitor (control)
```

Report:
- Number and share of days the variant beats control
- Average delta over all days

A variant beating control on fewer than 50% of days is considered directionally inconsistent.

---

### Step 5 — Statistical Significance Testing

**Method:** Paired t-test on daily Margin per Visitor (one observation per day per variant pair).

Pairing on date is required because it controls for shared day-level seasonality and noise between variants.

Use Python (`scipy.stats.ttest_rel` or `ttest_1samp` on deltas) to compute. Do not rely on pre-aggregated totals alone.

For each treatment vs. control report:

| Output | Description |
|---|---|
| Mean daily delta | Average of (treatment MPV − control MPV) across all days |
| Standard deviation of deltas | Day-to-day variability in the delta |
| Standard error | `std / sqrt(n_days)` |
| t-statistic | `mean_delta / standard_error` |
| p-value | Two-sided paired t-test |
| 95% Confidence Interval | `mean_delta ± t_crit × SE` |
| Significant? | p < 0.05 = yes; p < 0.10 = marginal; p ≥ 0.10 = no |

---

### Step 6 — Power Analysis & Minimum Detectable Effect (MDE)

Run this step whenever a result is not statistically significant.

**σ selection — use A/A baseline when available (preferred):**

```
IF A/A baseline available (from A/A lookup step):
    std_delta = sigma value for (primary_metric × platform) from A/A query
    label as: "σ source: A/A baseline (xp-MBNXT-30862-AA-test-[platform], N days)"
ELSE:
    std_delta = standard deviation of daily deltas from this experiment's own data
    label as: "σ source: within-experiment estimate (A/A baseline unavailable)"
```

The A/A σ is preferred because it is treatment-free and stable. Within-experiment σ computed from the completed experiment is acceptable as a fallback but will slightly overestimate variance when a real treatment effect is present.

**Noise-floor context (add to Step 5 statistical results when A/A baseline is available):**

For each metric, include: *"The natural daily σ for [metric] on [platform] is [A/A σ value] — the observed delta of [value] represents [ratio]× the noise floor."* This communicates practical significance beyond the p-value: a delta of 0.3× σ is well within noise, while a delta of 2× σ is structurally meaningful regardless of significance.

**Minimum Detectable Effect at 80% power (α = 0.05):**

```
MDE = (t_crit + t_power) × (std_delta / sqrt(n_days))
```

**Days needed to detect the observed effect** — iterate over candidate `n` values until:

```
abs(mean_delta) >= (t_crit(df=n-1) + t_power(df=n-1)) × (std_delta / sqrt(n))
```

Report:
- **σ source** (A/A baseline with experiment name and day count, or within-experiment fallback)
- **A/A baseline σ values** (report the per-platform, per-metric values used)
- MDE as both absolute and relative (%) to control Margin per Visitor
- Days needed for 80% power
- Days needed for 90% power
- Current days in test
- Gap remaining (how many more days would be needed)
- Ratio of MDE to observed effect
- **Noise-floor ratio** for observed delta on each metric (delta / A/A σ)

**Decision heuristic:** If days needed exceed ~8–12 weeks of additional runtime, recommend KILL rather than extension.

---

### Step 7 — Behavioral Mechanism & Context (Qualitative Layer)

When experiment context is provided (e.g., what the variants actually show or change), add a qualitative interpretation:

- State what the hypothesis predicts mechanistically
- Compare the prediction to what was actually observed
- Explain whether the mechanism is inherently weak or strong given the product context

This step distinguishes between "the test was underpowered" and "the hypothesis is fundamentally weak." Both produce a non-significant result, but they lead to different follow-up actions.

---

### Step 8 — Business Impact Estimate

Only present this if there is a directional winner. Clearly label all projections as estimates with uncertainty.

**Observed-period equivalent (exact, historical):**

```
observed_incremental_m1vfm = delta_mpv × total_visitors_across_all_variants
```

Present as: *"If the winning variant had been deployed to 100% of traffic during the experiment period, the estimated incremental impact would have been approximately +$X in M1+VFM."*

**Monthly projection (range, not a single number):**

```
monthly_low  = observed × 0.8
monthly_high = observed × 1.2
```

Present as: *"Assuming similar traffic levels, the expected uplift is approximately in the range of +$X to +$Y M1+VFM per month."*

**Annual projection (range):**

```
annual_low  = monthly_low × 12
annual_high = monthly_high × 12
```

**Required wording — always use:**
- "estimated range"
- "expected uplift"
- "approximate impact"
- "directional only" (when result is not statistically significant)

**Never use:**
- "will generate" / "will deliver" / "expected to produce exactly"
- Precise figures like "$516,214/year"

If result is not statistically significant, add: *"These projections should be treated as directional only — the result has not been statistically confirmed."*

---

## Winner Selection & Decision Rule

**Primary KPI: Margin per Visitor**

| Decision | Criteria |
|---|---|
| **SHIP** | Winner on Margin per Visitor, p < 0.05, consistent across platforms, no Conversion Rate guardrail breach |
| **HOLD / EXTEND** | Positive direction, p between 0.05–0.15, days needed for significance within reasonable runway (≤ 8 weeks more) |
| **KILL** | Negative direction, OR p > 0.15 with days needed exceeding reasonable runway, OR observed effect is structurally too small to matter |

---

## Output Format

### Analysis payload (computed in this skill)

After completing all analytical steps, assemble the following structured results:

1. **Experiment metadata** — experiment name, date range, total days, total visitors
2. **Variant verdicts** — SHIP / KILL / DIRECTIONAL SIGNAL / HOLD / BASELINE per variant (use verdict logic from report skill)
3. **GrowthBook Configuration** — experiment status, targeting condition (population scope), metrics configured (yes/no), stats engine, attribution model, hash attribute, screenshots note, any process gaps (e.g., no metrics = "No data" warning)
4. **Step 1: SRM Check** — traffic split per variant (visitors, share, expected) + pass/fail verdict
5. **Step 2: Overall Results** — all four metrics per variant + uplift vs. control
6. **Step 3: Platform Results** — same metrics split by `touch` / `web` / `app` (iphone + android + ipad)
7. **Step 4: Stability** — days beating control + average daily delta per variant
8. **Step 5: Statistical Testing** — mean delta, std, SE, t-stat, p-value, 95% CI, significance label per variant
9. **Step 6: Power Analysis** — σ source (A/A baseline or within-experiment fallback), A/A baseline σ values used (per platform/metric), MDE (absolute + %), days needed at 80% and 90% power, current days, gap, noise-floor ratio per metric
10. **Step 7: Practical Significance** — Cohen's d, relative uplift %, cost-of-change assessment, and practical verdict narrative per variant
11. **Step 8: Behavioral Mechanism** — qualitative narrative on hypothesis, predicted vs. observed, and mechanism context (informed by Jira + GrowthBook context)
12. **Step 9: Business Impact** — observed-period equivalent, monthly range, annual range (directional label if not significant)
13. **Final Recommendation** — SHIP / HOLD / KILL per variant with bullet-point reasoning
14. **Notes** — source table, data quality filters applied, fields used, statistical method, population scope (targeting condition), GrowthBook experiment ID + status, Jira ticket + assignee, any caveats

### Document generation (delegated to report skill)

**After completing the analysis, read `/mnt/skills/user/ab-experiment-report-document-structure/SKILL.md` and use that skill exclusively to produce the final Word document (.docx) deliverable.**

The report skill owns all document rendering decisions: layout, colors, typography, table structure, section order, and formatting. Pass all computed results, verdicts, and narrative text to it. Do not independently apply docx formatting — defer entirely to the report skill's specifications.

---

## Key Lessons & Common Pitfalls

- **Total margin ≠ efficiency.** A variant with more visitors can show higher total M1+VFM but lower Margin per Visitor. Always use Margin per Visitor as the deciding metric, not total margin.
- **`ue_orders` not `orders_placed`.** The `ue_orders` field is the finance-approved order count. Always prefer it.
- **Paired t-test on daily data > t-test on aggregated totals.** Daily pairing controls for seasonality and shared noise. It is the correct method for this data structure.
- **Power analysis is mandatory when p > 0.05.** Never just report "not significant" — always quantify how many days would be needed and whether extending is practical.
- **Context determines whether to extend or kill.** A CTA label test producing 0.8% Margin per Visitor lift with 254 days needed is a KILL. A checkout flow change producing 0.8% from 30 days with 60 days needed might be a HOLD.
- **The behavioral mechanism matters.** When experiment context is known, explain *why* the result is the size it is. This prevents re-testing the same weak hypothesis.
- **`log_status` filtering:** The `log_status` field distinguishes logged-in from logged-out users. Logged-out sessions may have null or incomplete revenue/margin fields. Be explicit about which population is being analyzed.
- **`log_status` is a BOOL in BigQuery** — filter with `log_status = true`, not `log_status = 'true'` (string comparison will throw a type error).
- **Always check if GrowthBook has metrics configured.** If `settings.goals` is empty, GrowthBook will show "No data" in its UI despite the experiment running with millions of visitors. This is a common process gap — flag it prominently in the report and note that all analysis is BigQuery-driven.
- **GrowthBook experiments don't stop themselves.** If the experiment status is `running` with no `dateEnded`, the team must manually stop it in GrowthBook after a decision is made. Include this as an explicit action item in the recommendation.
- **Targeting conditions define the analysis population.** A GrowthBook targeting condition like `{ "country": "US" }` means all BigQuery figures are US-only. Always surface this in the report — do not present results as global without verifying targeting scope.
- **GrowthBook experiment ID ≠ tracking key.** The tracking key (e.g., `xp-MBNXT-27180-cta-label-buy-caption`) is what appears in BigQuery. The GrowthBook experiment ID (e.g., `exp_19g61mmi4e2hj6`) is the internal identifier used for API calls. Both should be recorded in the report's Notes section.
- **CTA label experiments on mature platforms produce trivially small effects.** By the time a user reaches the CTA button, purchase intent is already determined by the deal content and price. Label wording is a confirmation mechanism, not a persuasion mechanism. Expect Cohen's d < 0.1 and require very long runtimes to detect — this hypothesis class is a low-ROI testing priority on Groupon's non-bookable deal pages.
- **Non-bookable deal scope significantly constrains behavioral interpretation.** Experiments scoped only to non-bookable deals exclude bookable deals, which have a fundamentally different user journey (calendar selection, time commitment). Always identify deal type scope from the Jira ticket and incorporate it into the mechanism analysis.
