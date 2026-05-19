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
| Platform | | `touch / web / app / both / all` — app covers iphone + android + ipad |
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
| Duration (days) | | `28` |

### RESULTS *(filled after evaluation)*
| Field | Value | Example |
|---|---|---|
| Winner | | `Treatment A` |
| Significance | | `p = 0.03, statistically significant` |
| Decision | | `SHIP` |
| Learnings | | `"Get Deal" framing reduced hesitation at checkout entry; effect stronger on touch` |
| Summary in 1 sentence | | `Changing CTA to "Get Deal" increased Checkout Entry Rate by +1.8% on touch` |

---

## Metric Decision Logic

Use this table to suggest the correct Primary Success Metric based on Experiment Type:

| Experiment Type | Primary Success Metric | Guardrail Metric | Why |
|---|---|---|---|
| CTA label / button text | Checkout Entry Rate (`CV_views / UV`) | Conversion Rate | Button drives checkout entry — most direct and sensitive signal |
| Deal page layout / images | Checkout Entry Rate (`CV_views / UV`) | Conversion Rate | Page content affects willingness to enter checkout |
| Checkout flow / UX | Conversion Rate (`ue_orders / UV`) | Margin per Visitor | User is already past entry — conversion is what matters |
| Browse / search / category | Margin per Visitor (`margin_1_vfm / UV`) | Conversion Rate | Broad funnel — revenue efficiency is the best single summary |
| Pricing / discount / promo | Margin per Visitor (`margin_1_vfm / UV`) | Conversion Rate + Promo Rate | Pricing directly affects margin — watch `ue_orders_with_promo` |
| Authentication / login | Conversion Rate (`ue_orders / UV`) | Margin per Visitor | Auth friction blocks purchase completion |
| Infrastructure / A/A | Conversion Rate (`ue_orders / UV`) | Margin per Visitor | Baseline sanity check only |

---

## Validation Checklist

When a PM asks to validate their brief before launch, check all of the following:

1. ✅ GrowthBook Tracking Key is in `xp-*` format (not a URL or display name)
2. ✅ Experiment Type matches one of the 7 categories in the decision logic table
3. ✅ Planned End Date is set and is in the future
4. ✅ Control and Treatment descriptions say what the user literally sees (not tech flags)
5. ✅ Hypothesis follows "If we [X] then [Y] because [Z]" — has a mechanism, not just a direction
6. ✅ GrowthBook experiment has metrics configured (if not, flag: evaluation will be BigQuery-only)
7. ✅ GrowthBook targeting condition is documented in the Jira ticket (so population scope is known)

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
