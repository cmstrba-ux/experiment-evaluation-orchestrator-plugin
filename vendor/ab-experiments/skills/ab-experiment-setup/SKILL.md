---
name: ab-experiment-setup
description: "Validate a pre-launch A/B experiment brief. Use when asked to set up, validate, or check an experiment brief before launch. Covers required field checks, metric selection, and the full brief template."
---

# Pre-Launch Experiment Setup Skill

## Purpose

Validate an experiment brief before launch by checking all required fields in the Jira ticket, confirming the correct primary success metric, and **estimating the minimum runtime** needed to detect the declared MDE with 80% power.

This skill runs one optional BigQuery query (A/A baseline σ_D) for runtime estimation. All other steps are documentation and validation only.

---

## How to Use This Skill

When invoked via the `/setup-experiment` command, always start by asking the user which mode they want:

- **Mode A — Show me the template**: Display the blank brief template as a clean copy-pasteable block. No further questions.
- **Mode B — Guide me through the setup**: Ask each field one at a time across four rounds (SETUP → EXPERIMENT DESIGN → RUNTIME → CONFIRMATION). At the end, display the fully filled template and run the validation checklist.

For Mode B:
1. Read the reference file at `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-setup/references/setup.md`
2. Walk through fields one by one using AskUserQuestion — one field per message
3. After Experiment Type is declared, auto-suggest the Primary Metric and Guardrails from the lookup table
4. **Estimate the required runtime** — run the A/A baseline BigQuery query for the relevant platform, compute days_needed, and suggest Start Date + Planned End Date
5. Present the completed filled template, then run the 9-item validation checklist

---

## Metric Selection (Summary)

Metric selection uses a **4-tier framework** defined in full in `references/setup.md`. Every brief must declare all four tiers before launch. Quick reference by experiment type:

| Experiment Type | Primary Metric | Key Guardrails |
|---|---|---|
| Search / ranking / category | Margin per Visitor | Refund Rate, Checkout Entry Rate |
| Deal page (PDP) / layout | Margin per Visitor | Checkout Entry Rate, Refund Rate |
| CTA / button text | Checkout Entry Rate | Conversion Rate, Refund Rate |
| Checkout flow / UX | Checkout-to-Order Rate (`ue_orders / CV_views`) | Refund Rate, Cancellation Rate, Promo Rate |
| Pricing / discount / promo | Margin per Visitor | Revenue per Visitor, Promo Order Rate, Refund Rate |
| Authentication / login | Conversion Rate | Margin per Visitor, Refund Rate |
| Infrastructure / A/A | Conversion Rate | Margin per Visitor |

See `references/setup.md` for full tier definitions (decision metrics / guardrails / diagnostics / validity checks) and the funnel diagnosis logic.

---

## Runtime Estimation (Summary)

To estimate the minimum number of days before launch:

1. **Ask the PM for their MDE** — what is the smallest relative lift worth shipping? (typical range: 1%–5%)
2. **Run the A/A baseline query** from `references/setup.md` against the correct platform (touch / web) to get `sigma_d` and `baseline_mpv`
3. **Apply the formula**: `days = CEIL(7.85 × sigma_d² / (baseline_mpv × MDE_rel)²)` — use `9.49` instead of `7.85` for A/B/C tests
4. **Apply floors**: minimum 14 days; round up to the next multiple of 7

Quick MDE guide:
- 5% MDE → ~14–21 days (touch, US typical)
- 3% MDE → ~21–35 days
- 2% MDE → ~35–56 days
- 1% MDE → 56–90+ days (consider widening population)

If the estimate exceeds 90 days, flag this to the PM: the experiment is underpowered at the declared MDE.

See `references/setup.md` for the full formula, worked example, and practical adjustment rules (novelty warm-up, ramp-up buffer, multi-metric correction).

---

## Output

Produce a clear validation report covering:
- All 9 checklist items: present ✅ or missing ❌
- Exact wording for anything that needs to be corrected
- The confirmed Primary Metric, Secondary Metric, Guardrail Metrics, and key Diagnostics for this experiment type
- The estimated minimum runtime in days (with MDE assumption stated)
- Any items that would block launch
