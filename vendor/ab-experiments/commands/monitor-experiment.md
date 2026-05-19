---
description: Health-check a running AB experiment (SRM, harm, futility, direction)
allowed-tools: Read, Bash
argument-hint: <experiment-id or MBNXT-ticket>
---

Run a health check on the currently running experiment: $ARGUMENTS

This is a MID-EXPERIMENT monitor. The experiment is still live in GrowthBook.

Follow these steps exactly:

1. Read the skill file at `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-monitor/SKILL.md`
2. Identify the phase as **Mid-experiment monitoring**
3. If the argument is a Jira ticket (e.g. MBNXT-27180), look up the GrowthBook Tracking Key first. Also extract the **Experiment Type** field from the Jira ticket at this point.
4. Verify the experiment status in GrowthBook is `running` — if it has already stopped, redirect to /evaluate-experiment instead
5. **Metric Selection** — Before running any queries, present the available metrics to the user and ask which one to use as the primary success metric for this health check:
   - Based on the Experiment Type from the Jira ticket, identify the auto-suggested metric using the Metric Decision Logic table in `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-setup/references/setup.md`
   - Present the following options to the user and ask them to choose. Highlight the auto-suggested one by marking it as "(Recommended for this experiment type)":
     - **Margin per Visitor** — Average M1+VFM earned per unique visitor (`margin_1_vfm / UV`). Best for Browse/Search and Pricing/Promo experiments.
     - **Conversion Rate** — Share of visitors who completed an order (`ue_orders / UV`). Best for Checkout flow, Auth, and Infrastructure experiments.
     - **Checkout Entry Rate** — Share of visitors who entered checkout (`CV_views / UV`). Best for CTA label and Deal page layout experiments.
     - **Revenue per Visitor** — Average gross revenue per unique visitor (`gross_revenue / UV`). Best for revenue-focused analysis.
     - **Margin per Order** — Average M1+VFM per completed order (`margin_1_vfm / ue_orders`). Best for profitability analysis of individual transactions.
   - Wait for the user's selection before proceeding.
   - Record the chosen metric as `PRIMARY_METRIC`. This overrides the metric selection logic in Step 0b of the monitor skill — use the user's chosen metric as the primary guardrail metric throughout all four checks.
6. Follow the instructions in `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-monitor/SKILL.md` exactly, using `PRIMARY_METRIC` as the primary metric for all checks (SRM, guardrail, futility, directional signal).
7. Produce a concise in-chat health check summary covering: SRM status, guardrail breach detection, futility projection, and directional signal. State which primary metric was used.

No Word document is required for a monitor check — in-chat summary only.
