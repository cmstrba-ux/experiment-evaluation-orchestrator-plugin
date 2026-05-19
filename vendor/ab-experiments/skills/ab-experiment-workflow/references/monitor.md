---
name: ab-experiment-monitor
description: "Use this skill whenever you are asked to check, monitor, or health-check a RUNNING A/B or A/B/C experiment. Triggers include: 'check this experiment', 'should I kill this test', 'how is the experiment doing', 'monitor experiment progress', 'is it safe to keep running', 'should I stop the experiment early', or any reference to an in-flight experiment with patterns like 'xp-*'. This skill does NOT produce a SHIP verdict — it focuses on four questions: Is the data clean (SRM)? Is there active harm (guardrail breach)? Is significance achievable within reasonable runway (futility check)? What is the directional signal so far? Output is a concise health check summary, not a full evaluation report."
---

# A/B Experiment Monitor Skill

## Purpose

Assess the health of a **currently running** A/B or A/B/C experiment and answer one question: **should we kill it, flag it for investigation, or let it continue running?**

This skill is a companion to `ab-experiment-evaluation-c3`. It shares the same data sources, metric definitions, filtering rules, and statistical foundations — but it is scoped to mid-experiment decisions only. It does **not** produce a SHIP/HOLD verdict. That is reserved for the final evaluation skill after the experiment ends.

---

## When to Run This Skill

- The experiment is still actively running (not yet stopped in GrowthBook)
- You want to catch harm, data quality issues, or structural futility before the planned end date
- **Recommended cadence:** No more than twice per week (e.g., Monday and Thursday). Running more frequently increases peeking risk without proportional information gain

---

## Metric Definitions

Never use shorthand abbreviations in outputs. Always spell out the full metric name.

The five metrics below are the **default monitoring set**. For a different primary metric, select from the **Full Metrics Catalog** below.

| Full Name | Formula | Description |
|---|---|---|
| **Checkout Entry Rate** ★ Funnel KPI | `SAFE_DIVIDE(SUM(CV_views), SUM(UV))` | Percentage of visitors who viewed the checkout page — primary for CTA and funnel experiments |
| **Conversion Rate** | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | Percentage of visitors who completed an order |
| **Margin per Visitor** ★ Revenue KPI | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))` | Average M1+VFM generated per visitor |
| **Revenue per Visitor** | `SAFE_DIVIDE(SUM(gross_revenue), SUM(UV))` | Average gross revenue generated per visitor |
| **Margin per Order** | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(ue_orders))` | Average M1+VFM per successful order |

Use `SAFE_DIVIDE` for all divisions.

**Important — CV_viewers availability:** `CV_viewers` (unique visitors who viewed checkout) is often unpopulated (all zeros) in the experiments table. Always verify by summing it across the experiment before using. If `SUM(CV_viewers) = 0`, note this explicitly in the output and use `CV_views / UV` only. Do not use a zero-populated column in analysis.

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
| **Checkout per Deal Viewer** *(new)* | `SAFE_DIVIDE(SUM(CV_views), SUM(UDV))` | ★ PDP-to-checkout rate. If Deal View Rate flat but this ↓, problem is on the deal detail page. |
| **Checkout-to-Order Rate** *(new)* | `SAFE_DIVIDE(SUM(ue_orders), SUM(CV_views))` | ★ Purchase completion inside checkout. ↓ = checkout friction. Primary for checkout/UX experiments. |
| Checkout Entry Rate (unique) | `SAFE_DIVIDE(SUM(CV_viewers), SUM(UV))` | ⚠️ Verify `SUM(CV_viewers) > 0` before use |
| Logged-in Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_in), SUM(uv_logged_in))` | |
| Logged-out Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_out), SUM(uv_logged_out))` | |
| Checkout Views (raw) | `SUM(CV_views)` | Volume context only |

**Orders**

| Metric | Formula | What it tells you |
|---|---|---|
| Orders | `SUM(ue_orders)` | Finance-approved volume — always prefer over `orders_placed` |
| **Conversion Rate** | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | Overall purchase rate. Blunt alone — combine with Checkout-to-Order Rate to isolate checkout step. |
| **Refund Rate** | `SAFE_DIVIDE(SUM(ue_orders_refunds), SUM(ue_orders))` | ★ Tier-1 quality guardrail. ↑ = lower-quality orders. |
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

## Core Fields & Filtering (Identical to Evaluation Skill)

### Primary data source (mandatory)

```
`kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
```

### Daily aggregation level

```
DATE(event_date) × LOWER(TRIM(clientPlatform)) × LOWER(TRIM(variantname))
```

### Data quality filter (mandatory)

```sql
HAVING SUM(UV) >= 1000
```

Also exclude rows where `SUM(UV) = 0`.

### Experiment scope

```sql
WHERE experimentname = '<experiment_id>'
```

---

## Pre-Analysis: Context Gathering

Before running any queries, gather context and lock in the primary metric. **This section must be completed before any BigQuery queries are run.** Changing the primary metric after seeing results is a form of peeking and invalidates the guardrail logic.

### Step 0 — Column Availability Check (Run First)

Before selecting the primary metric, verify which funnel columns are actually populated for this experiment:

```sql
SELECT
  SUM(CV_views)   AS total_cv_views,
  SUM(CV_viewers) AS total_cv_viewers,
  SUM(UV)         AS total_uv
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = '<experiment_id>'
```

- If `total_cv_views > 0`: Checkout Entry Rate (`CV_views / UV`) is available and must be used as the funnel metric for eligible experiment types
- If `total_cv_viewers > 0`: CV_viewers-based unique-visitor rate is also available
- If `total_cv_viewers = 0`: Note explicitly — `CV_viewers` is not populated for this experiment; use `CV_views` only. **This is common — always verify before use.**
- If `total_cv_views = 0`: Checkout funnel metrics are unavailable; fall back to MPV and CVR only

### Step 0b — Experiment-Type Metric Selection (Lock In Before Any Analysis)

Based on the experiment hypothesis (from Jira) and what is being tested, select and **lock in** the **primary guardrail metric** for Checks 1–4. This decision is made once and does not change after data is viewed.

| Experiment Type | Primary Guardrail Metric | Rationale |
|---|---|---|
| CTA label / button text / buy button | **Checkout Entry Rate** (`CV_views / UV`) | The button directly drives checkout entry — most proximate and statistically sensitive measure (lower day-to-day variance relative to effect size means faster power accumulation vs. CVR or MPV) |
| Deal page layout / images / price display | **Checkout Entry Rate** + CVR | Page changes affect both funnel entry and conversion |
| Checkout flow changes | **Conversion Rate** (`ue_orders / UV`) | Already inside checkout; entry rate is not relevant |
| Browse / search / category page changes | **Margin per Visitor** | Broad funnel — revenue impact is the best summary metric |
| Pricing / discount / promo changes | **Margin per Visitor** + Conversion Rate | Revenue and conversion both affected |
| A/A test or infrastructure test | **Conversion Rate** | Baseline sanity check only |

Always run all metrics in the aggregation query, but apply the selected primary metric for the paired t-test, futility projection, and guardrail verdict. Secondary metrics are reported for context only.

**Anti-pattern to avoid:** Do not run the analysis with MPV or CVR first and then switch to Checkout Entry Rate after observing the results. This inflates false positive risk and defeats the purpose of a pre-specified primary metric. If an analyst requests a different metric after results are shown, explain that the primary metric must be locked before data is viewed and offer to re-run the full check with the new metric explicitly declared as a secondary exploratory analysis.

### Step 0c — A/A Baseline Variance Lookup (Run Before Any Experiment Queries)

**Purpose:** Retrieve natural metric variance from the dedicated A/A experiments rather than estimating it from the experiment's own (potentially treatment-contaminated) daily data. These A/A-derived σ values are used in Check 3 (futility projection) as the baseline standard deviation, making power projections credible from day 1 rather than stabilising only after 2+ weeks of data.

**A/A experiment identifiers (hardcoded — do not change unless new A/A tests replace these):**

| Platform | A/A Experiment Name |
|---|---|
| desktop | `xp-MBNXT-30862-AA-test-desktop` |
| touch | `xp-MBNXT-30862-AA-test-touch` |

**Query — run once per skill invocation, before any experiment-specific queries:**

```sql
SELECT
  experimentname,
  STDDEV_SAMP(daily_cvr)  AS sigma_cvr,
  STDDEV_SAMP(daily_cer)  AS sigma_cer,
  STDDEV_SAMP(daily_mpv)  AS sigma_mpv,
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
| *(no A/A test)* | `app` | `iphone`, `android`, `ipad` — use within-experiment σ fallback; note: *"⚠️ No A/A baseline for app platform."* |

> **`email` rows** (`clientPlatform = 'email'`): Exclude from all analysis — email sessions are click-throughs with atypically high purchase intent and skew MPV/CVR upward artificially.

**Fallback:** If the A/A experiments return no rows (e.g., data pipeline issue), fall back to computing σ from the experiment's own daily control-arm data and add a note: *"⚠️ A/A baseline unavailable — σ estimated from experiment control arm data. Futility projections may be less stable in early days."*

**Maturity flag:** If `aa_days < 14`, add a note in the output: *"A/A baseline is based on N days of data — estimates will tighten as the A/A test accumulates more observations."*

### Jira ticket lookup

Use `Atlassian:getJiraIssue` with the issue key derived from the experiment name (e.g., `MBNXT-27180`). Extract:
- Planned experiment duration (if stated)
- Target population or traffic percentage
- Hypothesis and any planned interim check dates
- Current Jira status (is the team still expecting results?)

### GrowthBook experiment lookup

Use `GrowthBook:get_experiments` with the experiment ID, `mode: metadata`. Extract:

| Field | Why It Matters |
|---|---|
| `status` | Confirm the experiment is still `running`. If already stopped, redirect to the evaluation skill instead. |
| `phases[0].dateStarted` | Use this as the experiment start date for day-count calculations |
| `phases[0].targetingCondition` | Defines the eligible population — all figures are scoped to this |
| `phases[0].trafficSplit` | Cross-check against BigQuery split for SRM validation |
| `phases[0].coverage` | Traffic coverage percentage — affects expected daily UV |
| `settings.goals` | If empty, GrowthBook has no metrics configured — flag this as a process gap |

If the experiment is already stopped in GrowthBook, state: **"This experiment has ended. Use the ab-experiment-evaluation-c3 skill for a full evaluation."** Do not proceed with this skill.

---

## Health Check Steps

### Check 1 — Sample Ratio Mismatch (SRM)

**This is the highest priority check. Run it first. A failing SRM invalidates all other results.**

Compute visitor share by variant across the full experiment period so far:

```sql
SELECT
  LOWER(TRIM(variantname)) AS variant,
  SUM(UV) AS total_visitors,
  ROUND(SAFE_DIVIDE(SUM(UV), SUM(SUM(UV)) OVER ()) * 100, 2) AS traffic_share_pct
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = '<experiment_id>'
GROUP BY variant
HAVING SUM(UV) >= 1000
ORDER BY variant
```

**SRM verdict:**
- A/B test: flag if any variant deviates more than **2 percentage points** from 50%
- A/B/C test: flag if any variant deviates more than **2 percentage points** from 33.3%
- Also cross-check observed split against `phases[0].trafficSplit` from GrowthBook

| SRM Result | Action |
|---|---|
| **Clean** | State: "No SRM detected — traffic split is within expected range." Proceed to Check 2. |
| **Drift detected** | State: "⚠️ SRM WARNING — traffic split is off by X pp. Investigate instrumentation before drawing any conclusions. Do not use metric results until resolved." Still run remaining checks but clearly caveat all outputs. |

**Common SRM causes to note:** bot filtering changes, caching layer inconsistencies, partial rollout errors, platform-specific variant exposure issues.

---

### Check 2 — Guardrail Breach Detection (Harm Check)

**Purpose:** Detect whether any treatment variant is actively harming users relative to control. This check uses a **stricter significance threshold (p < 0.01)** because we want strong evidence before raising a harm alarm mid-experiment — but we also check absolute magnitude to catch large practical drops even without statistical significance yet.

#### 2a — Compute Current Metric Totals

```sql
SELECT
  LOWER(TRIM(variantname)) AS variant,
  SUM(UV)                                               AS visitors,
  SUM(ue_orders)                                        AS orders,
  SUM(CV_views)                                         AS cv_views,
  SUM(CV_viewers)                                       AS cv_viewers,
  SUM(margin_1_vfm)                                     AS total_margin,
  SUM(gross_revenue)                                    AS total_revenue,
  SAFE_DIVIDE(SUM(CV_views),    SUM(UV))                AS checkout_entry_rate,
  SAFE_DIVIDE(SUM(CV_viewers),  SUM(UV))                AS checkout_viewer_rate,
  SAFE_DIVIDE(SUM(ue_orders),   SUM(UV))                AS conversion_rate,
  SAFE_DIVIDE(SUM(margin_1_vfm),SUM(UV))                AS margin_per_visitor,
  SAFE_DIVIDE(SUM(gross_revenue),SUM(UV))               AS revenue_per_visitor,
  SAFE_DIVIDE(SUM(margin_1_vfm),SUM(ue_orders))         AS margin_per_order
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = '<experiment_id>'
GROUP BY variant
HAVING SUM(UV) >= 1000
ORDER BY variant
```

If `SUM(CV_viewers) = 0` across all variants, exclude `checkout_viewer_rate` from the output table and note it as unpopulated.

#### 2b — Compute Daily Deltas for Paired Statistical Test

```sql
SELECT
  DATE(event_date) AS day,
  LOWER(TRIM(variantname)) AS variant,
  SAFE_DIVIDE(SUM(CV_views),    SUM(UV)) AS daily_checkout_entry_rate,
  SAFE_DIVIDE(SUM(ue_orders),   SUM(UV)) AS daily_cvr,
  SAFE_DIVIDE(SUM(margin_1_vfm),SUM(UV)) AS daily_mpv
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = '<experiment_id>'
GROUP BY day, variant
HAVING SUM(UV) >= 1000
ORDER BY day, variant
```

Then compute daily deltas (treatment − control) and run a **paired t-test** (`scipy.stats.ttest_rel`) on the **primary metric** selected in Step 0b. Always run the test on all three metrics but report the primary one as the guardrail basis. Secondary metrics are for context only.

#### 2c — Guardrail Breach Decision

Run the paired t-test on **all three metrics** (Checkout Entry Rate, Conversion Rate, Margin per Visitor). Apply the guardrail verdict using the **primary metric** selected in Step 0b. Secondary metrics are reported for context and to detect divergence patterns.

| Condition | Severity | Recommended Action |
|---|---|---|
| **Primary metric** paired t-test p < 0.01 AND direction is negative | 🔴 **HARM DETECTED** | Recommend immediate KILL |
| **Primary metric** absolute drop > 5% relative AND negative, even if p > 0.01 | 🟡 **HARM WARNING** | Flag for urgent review; consider pausing |
| **Secondary metric** p < 0.01 AND strongly negative (> 3% relative drop), even if primary is clean | 🟡 **HARM WARNING** | Flag — divergence may indicate an instrumentation issue or nuanced harm |
| No breach on primary or secondary metrics | ✅ **No guardrail breach detected** | Proceed to Check 3 |

**Important:** A guardrail breach uses p < 0.01 (not 0.05) to minimize false alarms mid-experiment. However, large absolute negative directions even without significance should always be flagged — practical harm is not always detectable early with standard thresholds.

**Noise-floor framing (add to guardrail output when A/A baseline is available):** For each metric, report how many A/A standard deviations the observed delta represents: *"[Metric] delta of [value] = [ratio]× natural noise floor (A/A σ = [value])."* This contextualises whether a delta is within expected random variation or genuinely anomalous.

#### 2d — Metric Divergence Interpretation

When the **primary funnel metric** (Checkout Entry Rate) and **downstream metrics** (CVR, MPV) point in opposite directions, do not average them out. Investigate and report the pattern explicitly:

| Pattern | Likely Interpretation | Action |
|---|---|---|
| Checkout Entry Rate ↓ + CVR flat/↑ + MPV flat/↑ | **Funnel filtering effect** — the treatment deters lower-intent visitors from clicking, but those who do convert at similar or better rates. The CTA change may be self-selecting a higher-quality audience. | Flag pattern; report both effects neutrally; note that checkout suppression is still a structural regression unless intentional |
| Checkout Entry Rate ↓ + CVR ↓ + MPV ↓ | **Broad harm** — the treatment is suppressing both entry and downstream outcomes. Clear harm signal. | KILL |
| Checkout Entry Rate ↑ + CVR flat/↓ | **Entry inflation without conversion** — more visitors enter checkout but fewer complete. May indicate misleading CTA. | WATCH; flag for qualitative review |
| All metrics move together | **Consistent signal** — straightforward interpretation | Report normally |

Always state which pattern is present in the output. Do not leave metric divergence unexplained.

---

### Check 3 — Futility Projection (Days-to-Significance)

**Purpose:** Given the experiment's current effect size and variance, project how many total days would be needed to reach significance on the **primary metric**. If the projection far exceeds a reasonable runway, the experiment should be killed now to free up traffic and development resources.

This reuses the power analysis logic from Step 6 of the evaluation skill, applied to in-flight data.

#### 3a — Compute Current Effect Size and Variance

Using the daily **primary metric** deltas (treatment − control) already computed in Check 2b. The primary metric is the one selected in Step 0b (e.g., Checkout Entry Rate for CTA experiments, MPV for browse/pricing experiments):

```
mean_delta     = mean of daily (primary_metric_treatment − primary_metric_control)
n_days_so_far  = count of paired days available
SE_current     = std_delta / sqrt(n_days_so_far)
t_stat_current = mean_delta / SE_current
```

**σ selection — use A/A baseline when available (preferred):**

```
IF A/A baseline available (from Step 0c):
    std_delta = sigma value for (primary_metric × platform) from A/A query
    label as: "σ source: A/A baseline (xp-MBNXT-30862-AA-test-[platform])"
ELSE:
    std_delta = standard deviation of daily deltas from this experiment's control arm
    label as: "σ source: within-experiment estimate (A/A baseline unavailable)"
```

The A/A σ is preferred because it is treatment-free — it captures pure natural metric variance without any confounding from the experimental treatment. Within-experiment σ inflates slightly when a real treatment effect is present, making futility projections overly pessimistic. More importantly, in early days (< 10 observations) the within-experiment σ estimate is highly unstable, while the A/A σ is immediately reliable.

When the experiment covers **both platforms**, use the platform-specific A/A σ for each platform's separate futility projection, and use a weighted average (weighted by daily UV share) for the overall projection.

#### 3b — Project Days Needed for 80% Power

Iterate over candidate `n` values (n = 1, 2, 3, ... up to 365) until:

```
abs(mean_delta) >= (t_crit(df=n-1, α=0.05) + t_power(df=n-1, β=0.20)) × (std_delta / sqrt(n))
```

Where:
- `t_crit` = `scipy.stats.t.ppf(0.975, df=n-1)` (two-sided)
- `t_power` = `scipy.stats.t.ppf(0.80, df=n-1)`

Also compute days needed for 90% power using `t_power = scipy.stats.t.ppf(0.90, df=n-1)`.

#### 3c — Compute Minimum Detectable Effect at Current Sample Size

```
MDE_absolute = (t_crit(df=n-1) + t_power(df=n-1)) × (std_delta / sqrt(n_days_so_far))
MDE_relative = MDE_absolute / abs(MPV_control) × 100
```

#### 3d — Futility Verdict

Report for the **primary metric**:
- Current days in experiment
- Primary metric name (as selected in Step 0b)
- σ source (A/A baseline or within-experiment estimate)
- Observed mean daily delta (absolute and relative %)
- **Noise-floor context:** *"The natural daily σ for [metric] on [platform] is [value] — the observed delta represents [ratio]× the noise floor."* (Use A/A σ for this framing.)
- Current p-value from paired t-test
- Days needed for 80% power (from current effect size + σ)
- Days needed for 90% power
- Additional days needed beyond current runtime
- MDE at current sample size (absolute and relative %)
- Ratio of observed effect to MDE (e.g., "0.43× MDE — effect is less than half detectable threshold")

Also report secondary metrics (CVR, MPV, or Checkout Entry Rate depending on which is primary) for context, with their own p-values and direction, but without full futility projections.

| Projection | Futility Verdict |
|---|---|
| Days needed ≤ planned end date OR ≤ current days × 2 | ✅ **On Track** — power achievable within reasonable extension |
| Days needed > planned end date AND ≤ current days + 56 (8 more weeks) | 🟡 **BORDERLINE** — extension may be justified if effect is directionally positive and business value is high |
| Days needed > current days + 56 AND effect is negative (p < 0.15) | 🔴 **FUTILE + DIRECTIONALLY BAD** — recommend KILL regardless of power projection |
| Days needed > current days + 56 AND effect is near-zero (< 0.5% relative on primary metric) AND no harm detected | 🟡 **FLAT — CONTINUE** — the experiment is structurally uninformative on the primary metric, but it is not harmful. Do not KILL on futility grounds alone; let it run to its planned end date or until another stopping criterion is met |
| Days needed > current days + 56 AND effect is clearly directionally positive but below MDE | 🟡 **BORDERLINE POSITIVE** — extend if runway permits; flag to team for a go/no-go decision |

**Distinguishing flat-effect futility from directionally-bad futility:**
- **Directionally bad + futile** (effect negative, p < 0.15): Recommend KILL. The experiment is both uninformative and pointing in the wrong direction — no upside to continuing.
- **Flat + futile** (effect near-zero, no harm): Recommend CONTINUE or WATCH. The experiment is not generating signal, but it is not causing harm. Killing it on futility grounds is optional — only justified if the traffic opportunity cost is significant or another arm in the same experiment is being stopped anyway.
- **Never apply a KILL verdict for futility alone when the primary metric is flat and no harm is detected.** The cost of running a flat experiment is opportunity cost (traffic tied up), not user harm. That cost must be weighed against the value of more data.

**Important framing:** If the observed effect is very small in absolute terms (e.g., < 0.1% relative on the primary metric), call out explicitly that even if significance were achieved, the practical business impact would be negligible. Power and significance are not the only basis for a KILL — a structurally tiny effect is also a valid KILL signal when combined with a negative direction.

---

### Check 4 — Directional Signal Summary

**Purpose:** Provide a neutral, factual summary of where the experiment currently stands directionally. This is informational only — it is **not** a SHIP signal. No winner should be declared mid-experiment.

Report for each treatment variant vs. control:

| Output | Description |
|---|---|
| Direction | Is the **primary metric** currently above or below control? |
| Days beating control | How many of the N observed days has the variant been above control on the primary metric? (count and %) |
| Consistency | Is the direction consistent day-to-day, or is it flipping? |
| Platform signal | Is the directional pattern consistent across `touch`, `web`, and `app` (iphone + android + ipad)? Flag if diverging. |
| Metric divergence | Are funnel metrics (Checkout Entry Rate) and downstream metrics (CVR, MPV) pointing in the same direction? If not, describe the pattern using the table in Check 2d. |
| Current p-value | Reported for informational context only — explicitly note it is not a significance threshold at this stage |

**Required framing:** Always include this statement when reporting directional results:

> *"These are directional observations from a running experiment. They do not constitute a significant result. Do not act on directional signals alone — wait for the full evaluation to reach a SHIP/KILL decision."*

If the direction is positive and the futility projection shows achievability within runway, this can be noted as **"early positive trajectory — continue running."**

If the direction is negative but not yet a guardrail breach, note it as **"directionally negative so far — monitor closely."**

If metrics are diverging (e.g., funnel suppression with neutral downstream), explicitly describe the pattern and its possible interpretation rather than averaging or ignoring the divergence.

---

## Peeking Risk Disclosure (Mandatory)

Every health check output must include the following disclosure in the Notes section:

> *"This health check uses standard paired t-test statistics on partial experiment data. Repeated statistical testing on accumulating data inflates the false positive rate (peeking problem). The p-values reported here should not be used as a basis for declaring a winner or making a SHIP decision. They are included for informational context only. Use the ab-experiment-evaluation-c3 skill after the experiment ends for a statistically valid final evaluation."*

---

## Decision Outputs

The health check produces one of six outcomes per variant:

| Status | Criteria | Recommended Action |
|---|---|---|
| 🔴 **KILL — Harm Detected** | Primary metric paired t-test p < 0.01 AND direction is negative, OR large absolute drop > 5% relative even without significance | Stop the experiment immediately in GrowthBook |
| 🔴 **KILL — Futile + Bad Direction** | Days-to-significance > 8 weeks AND primary metric direction is negative AND p < 0.15 | Stop the experiment; do not extend |
| 🟡 **FLAG — SRM Detected** | Traffic split deviation > 2pp from expected | Pause experiment; investigate instrumentation before resuming |
| 🟡 **WATCH — Negative Trend** | Directionally negative on primary metric but not yet a confirmed breach; futility borderline | Increase monitoring frequency; reassess in 5–7 days |
| 🟡 **WATCH — Flat + Futile** | Days-to-significance > 8 weeks AND effect near-zero (< 0.5% relative) AND no harm detected | No action required; continue to planned end date but note low signal probability |
| ✅ **CONTINUE** | SRM clean, no guardrail breach, futility projection within reasonable runway | Let the experiment run to its planned end date |

**Mixed verdicts within a multi-variant experiment (A/B/C):**
Different arms of the same experiment may and often will receive different verdicts. Report a verdict per variant independently. When one arm is KILLed, explicitly note the implications for the remaining arms:
- If the KILLed arm's traffic can be reallocated to remaining arms, flag this as an option
- If remaining arms are flat/CONTINUE, their statistical power is unaffected until the traffic split changes
- If all remaining arms are flat or WATCH, consider whether the overall experiment has value and recommend a team review

**No SHIP verdict is produced by this skill.** If you see a strong positive signal, the correct action is CONTINUE — let it run to completion, then use the evaluation skill.

---

## Output Format

The health check output is intentionally concise. It is not a full report — it is a status dashboard. No Word document is required. Output as a structured in-chat summary with the following sections:

### 1. Experiment Header
- Experiment name and ID
- GrowthBook status and start date
- Days running so far
- Population scope (from GrowthBook targeting condition)
- Date of this health check

### 2. Overall Health Status
A single-line verdict at the top:

```
OVERALL STATUS: [KILL — Harm / KILL — Futile / FLAG — SRM / WATCH — Negative Trend / CONTINUE]
```

### 3. Check 1: SRM Result
- Traffic split table (variant, visitors, share %, expected %, deviation)
- SRM verdict (Clean / Warning)

### 4. Check 2: Guardrail Status
- Metric totals table (all available metrics per variant: Checkout Entry Rate, CVR, MPV, Revenue per Visitor)
- Primary metric identified (per Step 0b selection)
- Delta vs. control for **primary metric** (with p-value and guardrail verdict)
- Delta vs. control for secondary metrics (for context, with p-values)
- Metric divergence pattern noted if primary and secondary metrics disagree (per Check 2d table)
- Guardrail verdict per variant (No Breach / Warning / Harm Detected)

### 5. Check 3: Futility Projection
- Primary metric name
- **σ source** (A/A baseline with experiment name and day count, OR within-experiment fallback)
- **A/A baseline σ values used** (per platform, per metric — report the values pulled from Step 0c)
- Current days in test
- Observed mean daily delta on primary metric (absolute and relative %)
- **Noise-floor context** (observed delta as a multiple of A/A σ)
- Current p-value (informational)
- Days needed for 80% power
- Days needed for 90% power
- Additional days required
- MDE at current sample size (absolute and relative %)
- Effect / MDE ratio
- Futility verdict (On Track / Borderline / Futile)

### 6. Check 4: Directional Signal
- Primary metric direction per variant (positive / negative)
- Days beating control on primary metric (count and %)
- Secondary metric directions (one line each)
- Metric divergence pattern description if applicable
- Platform consistency note
- Required framing statement (see Check 4 above)

### 7. Recommended Action
One clear sentence **per variant** — each variant gets its own independent verdict:
- **KILL — Harm Detected** (primary metric breach)
- **KILL — Futile + Bad Direction** (futile and pointing negative)
- **FLAG** (SRM — investigate instrumentation)
- **WATCH — Negative Trend** (directionally bad but below breach threshold)
- **WATCH — Flat + Futile** (near-zero effect, no signal expected, no harm)
- **CONTINUE** (let it run to planned end date)

When multiple variants are present (A/B/C), explicitly note if verdicts differ and whether killing one arm has implications for the remaining arms' traffic split or statistical power.

### 8. Notes
- Data source and quality filters
- Statistical method and peeking risk disclosure (mandatory)
- GrowthBook experiment ID and status
- Jira ticket and assignee
- Population scope (targeting condition)
- Recommended next check date (based on cadence: twice per week)
- If experiment is approaching its planned end date: recommend switching to the full evaluation skill instead

---

## Key Differences from the Evaluation Skill

| Dimension | ab-experiment-evaluation-c3 | ab-experiment-monitor |
|---|---|---|
| When to use | After experiment ends | While experiment is running |
| Statistical method | Paired t-test on complete data | Paired t-test on partial data (with peeking disclaimer) |
| Significance threshold | α = 0.05 for SHIP | α = 0.01 for guardrail breach only; no SHIP threshold |
| Possible verdicts | SHIP / HOLD / KILL | KILL / FLAG / WATCH / CONTINUE |
| Business impact section | Yes | No — incomplete data makes projections unreliable |
| Word document output | Yes (full report) | No — concise in-chat summary only |
| Behavioral mechanism section | Yes | No — defer to final evaluation |
| Power analysis | Post-hoc (how long would it have taken?) | Forward-looking (how many more days are needed?) |

---

## Key Pitfalls

- **Do not declare a winner mid-experiment.** A positive directional signal at day 10 can reverse by day 30. Only the final evaluation skill should produce a SHIP verdict.
- **Do not use p < 0.05 as a mid-experiment kill threshold for negative results.** Use p < 0.01 for harm detection, plus the absolute magnitude check. Standard α = 0.05 generates too many false alarms in a monitoring context.
- **Futility kill is not a failure — but flat-futility is not a kill.** Stopping a futile experiment early is the correct decision only when the effect is directionally negative. A near-zero, non-harmful result is a different situation: the experiment is uninformative, not harmful. Do not kill a flat experiment unless the traffic cost is significant. Frame both cases clearly — resource optimization (kill the bad-direction futile arms) is different from giving up on a clean flat arm.
- **Distinguish directionally bad futility from flat futility.** "FUTILE" covers two very different cases: (a) the effect is negative and won't improve — kill it, (b) the effect is essentially zero and the experiment can't detect it — a judgment call based on opportunity cost. These should never be collapsed into the same verdict.
- **In a multi-variant experiment, evaluate each arm independently.** Killing Treatment B does not mean killing Treatment A. Report a verdict per variant. When one arm is stopped, flag the traffic reallocation opportunity for the team.
- **A large absolute negative direction matters even without statistical significance.** If the primary metric is down 4% relative after 14 days, that is a meaningful signal even if p = 0.15. Do not ignore large practical effects just because they haven't crossed a threshold yet.
- **SRM invalidates all other checks.** If SRM is detected, the metric results are unreliable. Report the SRM clearly and stop drawing conclusions from the other steps until instrumentation is verified.
- **Consistent direction matters more than point-in-time p-value.** A variant beating control on 80% of days with a stable trend is more meaningful than a single-day spike. Always report the day-beating-control share alongside the p-value.
- **Don't mistake variance for signal.** Early in an experiment, day-to-day variance is high and the confidence interval on the mean delta is wide. Always report the MDE alongside the observed effect so the reader understands how small the detectable signal is at current sample sizes.
- **Always check if the experiment is actually still running.** Before doing any analysis, confirm GrowthBook status is `running`. If it's already stopped, redirect to the evaluation skill.
- **Always select the primary metric based on experiment type before running any tests.** Running MPV or CVR as the primary metric for a CTA button test will miss funnel-entry suppression that is only visible in Checkout Entry Rate. The wrong primary metric can produce a clean bill of health on a harmful experiment.
- **Never leave metric divergence unexplained.** If Checkout Entry Rate is down but CVR and MPV are neutral or positive, that is a specific and interpretable pattern — not noise. Describe it (e.g., funnel filtering effect) and note whether the checkout suppression is intentional or a regression.
- **CV_viewers may be unpopulated — always verify.** Run the column availability check (Step 0) before including CV_viewers in any analysis. Using a zero-populated column produces misleading results.
- **The primary metric failing does not excuse secondary metric harm.** If the primary metric is clean but a secondary metric (e.g., MPV) shows p < 0.01 and a large negative direction, still flag it as a HARM WARNING. Guardrail thresholds apply to all metrics, not just the primary.
