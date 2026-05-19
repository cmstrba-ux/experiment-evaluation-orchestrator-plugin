# Pre-Launch Setup Validation

This reference covers everything needed to validate an experiment brief before launch,
and to help PMs understand what to fill in Jira, GrowthBook, and Confluence.

---

## Required Fields — Jira Ticket

The evaluation and monitor skills automatically pull these fields from Jira.
Missing fields degrade analysis quality. Validate all 6 before launch.

| Field | Format / Example | Why It Matters |
|---|---|---|
| **Experiment Type** | CTA label / Page layout / Checkout flow / Browse-Search / Pricing / Auth / A/A | Locks in the primary metric before any data is viewed — prevents peeking bias |
| **GrowthBook Tracking Key** | `xp-MBNXT-27180-cta-label-buy-caption` | Used as BigQuery `experimentname` filter — nothing runs without it |
| **Planned End Date** | `2026-03-28` | Monitor skill uses this for runway + futility calculation |
| **Control Description** | `"Buy Now" button on deal page` | Feeds behavioral mechanism analysis in the evaluation report |
| **Treatment Description(s)** | `"Get Deal" button on deal page` | Same reason — describe what the user literally sees, not technical flags |
| **Hypothesis** | `If we change X, then Y will increase because Z` | Required for mechanism analysis (Step 7 of evaluation) |

---

## Full Brief Template

For each experiment, the PM should fill in the following. Present this as a checklist
when the user asks "what should I fill in before launch?" or similar.

### SETUP
| Field | Value | Example |
|---|---|---|
| Owner | | `Jane Kowalski` |
| Tag | | `MBNXT`, `checkout`, `cta` |
| Jira Ticket ID | | `MBNXT-27180` |
| GrowthBook Tracking Key | | `xp-MBNXT-27180-cta-label-buy-caption` |
| Platform | | `touch / web / app / all` |
| Target Population | | `All US logged-in users` |

### EXPERIMENT DESIGN
| Field | Value | Example |
|---|---|---|
| Experiment Type | | `CTA label` |
| Description | | `Testing whether changing the buy button label from "Buy Now" to "Get Deal" increases checkout entries` |
| Hypothesis | | `If we change the CTA label to "Get Deal", then Checkout Entry Rate will increase because the word "Get" implies lower commitment than "Buy"` |
| Control | | `"Buy Now" button on deal page` |
| Treatment A | | `"Get Deal" button on deal page` |
| Treatment B | | *(leave blank if A/B only)* |
| Primary Success Metric | | *(auto-suggested from experiment type — see table below)* |
| MDE Assumption (relative) | | `+2%` — smallest lift worth shipping |
| Success Metric Impact (est.) | | `+2% relative uplift` |
| Guardrail Metric | | `Conversion Rate` |
| Guardrail Metric Impact (est.) | | `neutral or positive` |
| Est. Annual M1VFM Impact | | `~$200k–$300k` |

### TIMELINE
| Field | Value | Example |
|---|---|---|
| Start Date | | `2026-03-01` |
| Planned End Date | | `2026-03-28` |
| Actual End Date | | *(filled after experiment stops)* |
| Duration (days) | | `28` — calculated from runtime estimation (see section below) |

### RESULTS *(filled after evaluation)*
| Field | Value | Example |
|---|---|---|
| Winner | | `Treatment A` |
| Significance | | `p = 0.03, statistically significant` |
| Decision | | `SHIP` |
| Learnings | | `"Get Deal" framing reduced hesitation at checkout entry; effect stronger on touch` |
| Summary in 1 sentence | | `Changing CTA to "Get Deal" increased Checkout Entry Rate by +1.8% on touch` |

---

## Metric Selection Framework

Every experiment brief must declare metrics across four tiers before launch. Metric selection must happen **before any data is viewed** to prevent peeking bias.

---

### Tier 1 — Primary Decision Metrics

The primary metric is the single metric used for the SHIP/HOLD/KILL verdict. The secondary supports interpretation. Both must be declared upfront.

| Role | Metric | Formula | Default for |
|---|---|---|---|
| **Primary KPI** | Margin per Visitor (M1+VFM) | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))` | All experiment types — the best single measure of business value per visitor |
| **Supporting volume** | Conversion Rate | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | Explains whether MPV moved due to volume or transaction quality |

> **Exception — bottom-funnel experiments**: For checkout flow / UX experiments where the user is already inside checkout, use **Checkout-to-Order Rate** (`ue_orders / CV_views`) as primary. It measures only the checkout step without upper-funnel noise, making it far more sensitive for detecting friction.

---

### Tier 2 — Guardrail Metrics

Guardrails **block rollout** if they worsen materially, even when the primary metric is positive. Declare all applicable guardrails before launch.

| Guardrail | Formula | Why it matters | Applies to |
|---|---|---|---|
| **Refund Rate** | `SAFE_DIVIDE(SUM(ue_orders_refunds), SUM(ue_orders))` | Detects low-quality orders — buy + regret signal | All experiments |
| **Cancellation Rate** | `SAFE_DIVIDE(SUM(orders_cancelled), SUM(ue_orders))` | Post-purchase intent quality | Bookable deals, subscription |
| **Checkout Entry Rate** | `SAFE_DIVIDE(SUM(CV_views), SUM(UV))` | If ↓, purchase intent is being suppressed before checkout | All experiments — even if not primary |
| **Revenue per Visitor** | `SAFE_DIVIDE(SUM(gross_revenue), SUM(UV))` | Ensures M1+VFM gain isn't hiding revenue shape deterioration | All experiments |
| **Promo Order Rate** | `SAFE_DIVIDE(SUM(ue_orders_with_promo), SUM(ue_orders))` | Detects whether lift is bought via promos, not earned | Merchandising, checkout, pricing, search |
| **Logged-in share** | `SAFE_DIVIDE(SUM(uv_logged_in), SUM(UV))` | Catches accidental auth behaviour changes | Auth, login flow, account-gated experiments |

---

### Tier 3 — Diagnostic Funnel Metrics

Diagnostics explain **what happened** and **where in the funnel**. They do not drive the rollout verdict but are essential for root cause analysis and behavioral interpretation.

Use the funnel chain below to locate where a variant creates or destroys value:

```
UV → UDV → CV_views → ue_orders
```

| Diagnostic | Formula | What it isolates |
|---|---|---|
| **Deal View Rate** | `SAFE_DIVIDE(SUM(UDV), SUM(UV))` | Discovery layer (search, listing, homepage). ↓ = problem before deal detail. |
| **Checkout per Deal Viewer** | `SAFE_DIVIDE(SUM(CV_views), SUM(UDV))` | Deal detail page (PDP). ↓ with flat Deal View Rate = problem is on PDP specifically. |
| **Checkout-to-Order Rate** | `SAFE_DIVIDE(SUM(ue_orders), SUM(CV_views))` | Inside checkout. ↓ with flat CER = checkout friction is the root cause. |
| **Margin per Order** | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(ue_orders))` | Transaction quality. Explains if MPV moved due to volume vs. better orders. |
| **Revenue per Order (AOV)** | `SAFE_DIVIDE(SUM(gross_revenue), SUM(ue_orders))` | Average deal size. ↑ = users buying pricier deals; ↓ = cheaper deal mix. |
| **Promo Spend per Order** | `SAFE_DIVIDE(SUM(promo_spend), SUM(ue_orders))` | Promotional cost per transaction. ↑ = margin-dilutive orders. |
| **VFM per Order** | `SAFE_DIVIDE(SUM(vfm), SUM(ue_orders))` | Merchant-side economics. Decomposes Margin per Order into M1 vs. VFM components. |

> **Funnel diagnosis logic**: If CVR drops, check (1) Was Deal View Rate flat? If yes → problem is at PDP or below. Then check (2) Was Checkout per Deal Viewer flat? If yes → problem is inside checkout. Use all three funnel metrics before attributing a drop to any single cause.

---

### Tier 4 — Validity & Quality Checks

These are **mandatory** for every experiment. Run them before interpreting any metric result.

| Check | What to verify | How |
|---|---|---|
| **Traffic split (SRM)** | Variant split roughly matches expected allocation (±2pp) | Compare `SUM(UV)` by variant against expected share |
| **bCookie split** | Secondary SRM check — confirms bucketing consistency | Compare `SUM(distinct_bcookie_count)` by variant |
| **Platform balance** | Each variant has comparable `clientPlatform` mix | Check share of touch / web / app across variants |
| **Country balance** | No variant is overrepresented in a high-performing country | Check `country` distribution across variants |
| **Log-status balance** | Logged-in share is comparable across variants | Compare `uv_logged_in / UV` by variant |
| **Search visitor balance** | `search_visitor_flag` share is comparable | Useful for search/ranking experiments |
| **CV_viewers fill rate** | `SUM(CV_viewers) > 0` before using as a metric | Run a column availability check before analysis |

---

### Experiment Type → Metric Assignment

Use this lookup to complete the metric fields in the brief template:

| Experiment Type | Primary Metric | Secondary | Key Guardrails | Key Diagnostics |
|---|---|---|---|---|
| **Search / ranking / category** | Margin per Visitor | Conversion Rate | Refund Rate, Checkout Entry Rate | Deal View Rate, `CV_views/UDV`, Margin per Order |
| **Deal page (PDP) / images / layout** | Margin per Visitor | Conversion Rate | Checkout Entry Rate, Refund Rate | `CV_views/UDV`, `ue_orders/CV_views`, Margin per Order |
| **CTA / button text** | Checkout Entry Rate | Conversion Rate | Conversion Rate, Refund Rate | `CV_views/UDV`, `ue_orders/CV_views` |
| **Checkout flow / UX** | Checkout-to-Order Rate | Margin per Visitor | Refund Rate, Cancellation Rate, Promo Order Rate | `CV_views/UV`, Margin per Order, Revenue per Order |
| **Pricing / discount / promo** | Margin per Visitor | Conversion Rate | Revenue per Visitor, Promo Order Rate, Refund Rate | Promo Spend per Order, `margin_1_vfm/ue_orders`, `vfm/ue_orders` |
| **Authentication / login** | Conversion Rate | Margin per Visitor | Margin per Visitor, Refund Rate | Logged-in CVR, Logged-out CVR, Logged-in share |
| **Infrastructure / A/A** | Conversion Rate | Margin per Visitor | Margin per Visitor | All funnel metrics (sanity check only) |

---

## Runtime Estimation

Before setting the Planned End Date, estimate the minimum number of days the experiment needs to run to have sufficient statistical power to detect the declared MDE.

This uses the same **paired t-test on daily data** method as the evaluation skill — so the power calculation is consistent end-to-end.

---

### Formula

```
days_needed = CEIL( 7.85 × σ_D² / δ² )
```

Where:
- `7.85` = `(Z_α/2 + Z_β)²` = `(1.96 + 0.842)²` — standard two-tailed α=0.05, 80% power
- `σ_D` = std dev of daily (Treatment − Control) MPV differences from the **A/A baseline**
- `δ` = MDE in absolute terms = `baseline_MPV × MDE_relative`

For **A/B/C tests** (3 variants, 2 pairwise comparisons), apply Bonferroni correction:
replace `7.85` with `9.49` = `(Z_α/4 + Z_β)²` = `(2.24 + 0.842)²`

---

### Step 1 — Get σ_D and baseline MPV from the A/A test

Run this query against the A/A baseline for the target platform. Available A/A tests:
- **Touch** → `xp-MBNXT-30862-AA-test-touch` with `clientPlatform = 'touch'`
- **Web** → `xp-MBNXT-30862-AA-test-desktop` with `clientPlatform = 'web'`
- **App** → no A/A baseline exists; use `web` σ_D as a conservative proxy

```sql
WITH daily_variants AS (
  SELECT
    DATE(event_date) AS d,
    experimentvariationname,
    SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV)) AS daily_mpv
  FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
  WHERE experimentname = '<AA_TEST_KEY>'                  -- e.g. xp-MBNXT-30862-AA-test-touch
    AND clientPlatform = '<PLATFORM>'                     -- touch | web
    AND clientPlatform != 'email'
    AND country = '<COUNTRY>'                             -- e.g. US — omit to use all countries
  GROUP BY 1, 2
),
pivoted AS (
  SELECT
    d,
    MAX(IF(experimentvariationname = 'control',   daily_mpv, NULL)) AS mpv_control,
    MAX(IF(experimentvariationname = 'treatment', daily_mpv, NULL)) AS mpv_treatment
  FROM daily_variants
  GROUP BY 1
  HAVING mpv_control IS NOT NULL AND mpv_treatment IS NOT NULL
)
SELECT
  COUNT(*)                                           AS days_in_aa,
  ROUND(AVG(mpv_control), 4)                        AS baseline_mpv,
  ROUND(STDDEV(mpv_treatment - mpv_control), 4)     AS sigma_d
FROM pivoted
```

This returns three values:
- `baseline_mpv` — the daily average MPV to anchor the MDE calculation
- `sigma_d` — the natural daily noise in (T−C) differences under no-treatment condition

---

### Step 2 — Apply the formula

With the values from Step 1 and the declared MDE:

```
δ = baseline_mpv × MDE_relative            (e.g. 0.52 × 0.02 = 0.0104 for 2% MDE)
days_raw = CEIL( 7.85 × sigma_d² / δ² )
days_needed = max(days_raw, 14)            (floor: 2 full weeks for weekly seasonality)
days_final = CEIL(days_needed / 7) × 7    (round up to nearest full week)
```

If `days_final > 90`: the experiment is **underpowered** at this MDE with this population. Options:
- Widen the target population (more UV per day → shorter runtime)
- Relax the MDE (accept detecting only larger effects)
- Treat it as an exploratory experiment (no power guarantee — acknowledge this in the brief)

---

### Step 3 — Apply practical adjustments

| Adjustment | Rule | Reason |
|---|---|---|
| **Weekly seasonality floor** | Always round up to a multiple of 7 days | Weekend/weekday cycles inflate variance if cut mid-week |
| **Minimum duration** | At least 14 days (2 full weeks) | Even if formula says fewer, shorter experiments miss seasonal variance |
| **Novelty warm-up** | Note first 3–5 days may show novelty effects | Analysts may exclude them post-hoc; plan for them in duration |
| **Ramp-up time** | Add 2–3 days if GrowthBook ramp is gradual (e.g. 10% → 50% → 100%) | Power calculation assumes full allocation from day 1 |
| **Multi-metric correction** | If multiple primary metrics declared, use the most conservative days estimate | Prevents underpowered secondary metrics from contaminating verdicts |

---

### Quick Reference — Typical Runtimes

These are **illustrative ranges** based on historical touch A/A σ_D ≈ 0.008–0.012 and typical baseline MPV of $0.40–$0.65 for US traffic:

| MDE (relative) | Approx. days needed (touch, US) |
|---|---|
| 5% | ~14–21 days |
| 3% | ~21–35 days |
| 2% | ~35–56 days |
| 1% | ~56–90+ days |

> **Always run the Step 1 query for the specific country and platform** — these ranges are rough guides, not substitutes for the actual σ_D calculation.

---

## Validation Checklist

When a PM asks to validate their brief before launch, check all of the following:

1. ✅ GrowthBook Tracking Key is in `xp-*` format (not a URL or display name)
2. ✅ Experiment Type matches one of the 7 categories in the decision logic table
3. ✅ MDE assumption is declared (as a relative % — e.g. `+2%`)
4. ✅ Planned End Date is set, is in the future, and is consistent with the runtime estimate
5. ✅ Duration covers at least 14 days and is a multiple of 7 (full weeks)
6. ✅ Control and Treatment descriptions say what the user literally sees (not tech flags)
7. ✅ Hypothesis follows "If we [X] then [Y] because [Z]" — has a mechanism, not just a direction
8. ✅ GrowthBook experiment has metrics configured (if not, flag: evaluation will be BigQuery-only)
9. ✅ GrowthBook targeting condition is documented in the Jira ticket (so population scope is known)

If any item fails, explain what's missing and what specifically to add.

---

## Quick-Pick Rule for PMs

If unsure which Experiment Type applies, ask: **"Where in the user journey does the change appear?"**

- Before the deal page → `Browse/Search`
- On the deal page, before the button → `Deal page layout`
- On the buy button itself → `CTA label`
- After clicking the button, inside checkout → `Checkout flow`
- After purchase (pricing, discount, promo value) → `Pricing/promo`
- Login wall or account gate → `Authentication`
