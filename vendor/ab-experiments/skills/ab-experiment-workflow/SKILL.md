---
name: ab-experiment-workflow
description: >
  Full A/B experiment lifecycle management for Groupon MBNXT experiments.
  Use this skill for ANY request involving A/B experiments — whether running,
  completed, or being set up. Triggers include: 'evaluate experiment', 'check
  experiment', 'should we ship', 'how is the test doing', 'monitor experiment',
  'kill the experiment', 'run experiment analysis', 'is the experiment healthy',
  or any reference to experiment names matching patterns like 'xp-*' or
  'MBNXT-*'. This skill covers the complete lifecycle: pre-launch setup
  validation, mid-experiment health monitoring, and post-experiment evaluation
  with SHIP/HOLD/KILL decisions and Word document output. Always use this skill
  whenever the user mentions A/B tests, experiments, GrowthBook, or experiment
  evaluation — do not attempt to handle these requests without consulting this
  skill first.
version: 0.1.0
---

# A/B Experiment Workflow

This skill orchestrates the full lifecycle of A/B experiment management at Groupon.
It delegates to three specialised sub-skills depending on the phase of the experiment.

---

## Step 1 — Identify the Phase

Before doing anything else, determine which phase the user is in:

| User says | Phase | Sub-skill to read |
|---|---|---|
| "evaluate", "should we ship", "analysis", experiment has ended | **Post-experiment** | Read `references/evaluation.md` |
| "check", "monitor", "how is it doing", "should I kill", experiment still running | **Mid-experiment** | Read `references/monitor.md` |
| "set up", "brief", "what should I fill in", "before launch" | **Pre-launch** | Read `references/setup.md` |
| Unclear | Ask one question: "Is the experiment still running, or has it ended?" | — |

**Once you identify the phase, immediately read the corresponding reference file** and follow its instructions exactly. Do not proceed from memory — always read the file.

---

## Step 2 — Extract the Experiment ID

For monitor and evaluation phases, you need the experiment tracking key. It follows the pattern `xp-MBNXT-XXXXX-*` and is used as the BigQuery `experimentname` filter.

Extract it from:
1. The user's message (they may paste it directly)
2. The Jira ticket (field: `GrowthBook Tracking Key`)
3. GrowthBook (experiment name field)

If the user only gives a Jira ticket number (e.g., `MBNXT-27180`), look up the Jira ticket to find the GrowthBook Tracking Key before proceeding.

---

## Step 3 — Follow the Sub-skill

Each reference file is self-contained. It will tell you exactly what to do, in what order, including:
- Which Jira and GrowthBook fields to extract
- Which BigQuery queries to run (with exact table names and SQL)
- Which statistical methods to apply
- What the output format should be

---

## Data Source (All Phases)

Primary table — always use this unless explicitly told otherwise:
```
kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist
```

A/A baseline experiments (for power analysis):
```
xp-MBNXT-30862-AA-test-desktop   (web platform)
xp-MBNXT-30862-AA-test-touch     (touch platform)
```

---

## Primary Metric Selection (All Phases)

Lock in the primary metric from the Jira `Experiment Type` field **before viewing any data**.

| Experiment Type | Primary Metric | Formula |
|---|---|---|
| CTA label / button text | Checkout Entry Rate | `CV_views / UV` |
| Deal page layout / images | Checkout Entry Rate | `CV_views / UV` |
| Checkout flow / UX | Conversion Rate | `ue_orders / UV` |
| Browse / search / category | Margin per Visitor | `margin_1_vfm / UV` |
| Pricing / discount / promo | Margin per Visitor | `margin_1_vfm / UV` |
| Authentication / login | Conversion Rate | `ue_orders / UV` |
| Infrastructure / A/A | Conversion Rate | `ue_orders / UV` |

⚠️ **Margin per Visitor (`margin_1_vfm / UV`) is always reported as the business KPI** regardless of which primary metric is locked. A result cannot SHIP if Margin per Visitor is materially harmed.

Verify `CV_views` is populated before committing to Checkout Entry Rate:
```sql
SELECT SUM(CV_views) AS total_cv_views
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = '<experiment_id>'
```
If `total_cv_views = 0`, fall back to Conversion Rate and note the fallback.

---

## Key Fields from experiments_jupiter_hist

### Dimensions & Filters

| Field | Type | Use |
|---|---|---|
| `event_date` | DATE | Aggregate to daily level |
| `country` | STRING | Country code |
| `region` | STRING | Sub-country region |
| `clientPlatform` | STRING | `touch` (mobile web), `web` (desktop web), `iphone` (iOS app), `android` (Android app), `ipad` (iPad app), `email` (email click-throughs) — always split by platform bucket in Step 3 |
| `groupon_version` | STRING | App/site version |
| `log_status` | STRING | Logged-in vs logged-out |
| `cash_payment_type` | STRING | Payment method |
| `experimentname` | STRING | Experiment tracking key |
| `variantname` | STRING | Variant label — filter/group by this |
| `web_category_level_1–6` | STRING | Deal category hierarchy (L1–L6) |
| `pds_cat_name` | STRING | PDS category name |
| `search_visitor_flag` | STRING | Whether visitor came from search |

### All Available Metrics

**Never use precomputed `CVR` or `AOV` columns** — always recompute from source fields.
Always use `SAFE_DIVIDE` to avoid division-by-zero.
Data quality filter: `HAVING SUM(UV) >= 1000`

**Traffic & Visitor**

| Metric | Formula | Notes |
|---|---|---|
| Unique Visitors | `SUM(UV)` | ★ Primary traffic unit |
| Unique Deal Viewers | `SUM(UDV)` | Visitors who viewed a deal |
| Deal View Rate | `SAFE_DIVIDE(SUM(UDV), SUM(UV))` | |
| Logged-in Visitors | `SUM(uv_logged_in)` | |
| Logged-out Visitors | `SUM(uv_logged_out)` | |
| Distinct bCookies | `SUM(distinct_bcookie_count)` | |

**Funnel**

| Metric | Formula | Notes |
|---|---|---|
| Checkout Entry Rate | `SAFE_DIVIDE(SUM(CV_views), SUM(UV))` | ★ Primary for CTA / funnel experiments |
| Checkout Views (raw) | `SUM(CV_views)` | |
| Checkout Entry Rate (unique) | `SAFE_DIVIDE(SUM(CV_viewers), SUM(UV))` | ⚠️ Verify `SUM(CV_viewers) > 0` before use |
| Logged-in Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_in), SUM(uv_logged_in))` | |
| Logged-out Checkout Entry Rate | `SAFE_DIVIDE(SUM(cv_logged_out), SUM(uv_logged_out))` | |

**Orders**

| Metric | Formula | Notes |
|---|---|---|
| Orders | `SUM(ue_orders)` | ★ Finance-approved — use this, not `orders_placed` |
| Conversion Rate | `SAFE_DIVIDE(SUM(ue_orders), SUM(UV))` | |
| Logged-in CVR | `SAFE_DIVIDE(SUM(ue_orders_logged_in), SUM(uv_logged_in))` | |
| Logged-out CVR | `SAFE_DIVIDE(SUM(ue_orders_logged_out), SUM(uv_logged_out))` | |
| Authenticated Orders | `SUM(ue_orders_auth)` | |
| Canadian Orders | `SUM(ue_orders_can)` | |
| Promo Order Rate | `SAFE_DIVIDE(SUM(ue_orders_with_promo), SUM(ue_orders))` | Pricing experiments |
| Promo Orders (raw) | `SUM(ue_orders_with_promo)` | |
| Refund Rate | `SAFE_DIVIDE(SUM(ue_orders_refunds), SUM(ue_orders))` | ★ Tier-1 guardrail |
| Refunds (raw) | `SUM(ue_orders_refunds)` | |
| Cancellation Rate | `SAFE_DIVIDE(SUM(orders_cancelled), SUM(ue_orders))` | |
| Cancellations (raw) | `SUM(orders_cancelled)` | |

**Revenue & Margin**

| Metric | Formula | Notes |
|---|---|---|
| Margin per Visitor (M1+VFM) | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))` | ★ Primary revenue KPI |
| Revenue per Visitor | `SAFE_DIVIDE(SUM(gross_revenue), SUM(UV))` | |
| Margin per Order | `SAFE_DIVIDE(SUM(margin_1_vfm), SUM(ue_orders))` | |
| Revenue per Order (AOV) | `SAFE_DIVIDE(SUM(gross_revenue), SUM(ue_orders))` | Recompute — do not use precomputed `AOV` column |
| Bookings per Visitor | `SAFE_DIVIDE(SUM(gross_bookings), SUM(UV))` | |
| Total M1+VFM | `SUM(margin_1_vfm)` | Use for impact estimates only, not winner selection |
| Total Gross Revenue | `SUM(gross_revenue)` | |
| Total Gross Bookings | `SUM(gross_bookings)` | |
| VFM Component | `SUM(vfm)` | VFM portion only (excludes M1) |
| Promo Spend | `SUM(promo_spend)` | |
| Promo Spend per Order | `SAFE_DIVIDE(SUM(promo_spend), SUM(ue_orders))` | |
| OD (Overhead & Discounts) | `SUM(od)` | |

---

## Reference Files

- `references/monitor.md` — Full mid-experiment health check instructions (4 checks, verdicts, output format)
- `references/evaluation.md` — Full post-experiment evaluation instructions (9 steps, Word doc output)
- `references/setup.md` — Pre-launch PM brief validation and requirements
