---
description: Evaluate a completed AB experiment — produces SHIP/HOLD/KILL report
allowed-tools: Read, Write, Bash
argument-hint: Provide the experiment ID or Jira ticket (e.g., `MBNXT-27180`)
---

Evaluate the completed A/B experiment: $ARGUMENTS

This is a POST-EXPERIMENT evaluation. The experiment has ended and a final decision is needed.

Follow these steps exactly:

1. Read the skill file at `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-evaluation-c3/SKILL.md`
2. Identify the phase as **Post-experiment evaluation**
3. If the argument is a Jira ticket (e.g. MBNXT-27180), look up the GrowthBook Tracking Key from the ticket first — that key is the BigQuery `experimentname` filter. Also extract the **Experiment Type** field from the Jira ticket at this point.
4. **Metric Selection** — Determine the primary success metric and establish guardrails using the following 3-tier logic:

   **Tier 1 — Universal default**
   - **Margin per Visitor** (`margin_1_vfm / UV`) is the default PRIMARY_METRIC for all experiments.
   - It captures both conversion volume and per-order profitability in a single number, making it the broadest-coverage KPI.
   - Use it automatically when the experiment type is unknown or not specified.

   **Tier 2 — Always-computed guardrails (mandatory, never skipped)**
   Regardless of which primary metric is chosen, always compute and report these two guardrail metrics alongside the primary results:
   - **Refund Rate** — `ue_orders_refunds / ue_orders` — detects order quality degradation that primary metrics can miss. Flag any increase >0.5pp vs. control as a guardrail breach.
   - **Cart Abandonment Rate** — `1 - (ue_orders / CV_viewers)` — detects checkout friction introduced by the experiment. Flag any increase >1pp vs. control as a guardrail breach.
   A guardrail breach does not automatically override the SHIP decision but must be explicitly called out in the report and recommendation.

   **Tier 3 — Alternative primary metrics (override when experiment type is known)**
   - If the Experiment Type is available from the Jira ticket, use the Metric Decision Logic table in `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-setup/references/setup.md` to identify the recommended alternative.
   - If the recommended alternative differs from Margin per Visitor, present it to the user and ask whether to use it as PRIMARY_METRIC instead. Mark it as "(Recommended for this experiment type)".
   - Available alternatives:
     - **Conversion Rate** — `ue_orders / UV`. Best for Checkout flow, Auth, and Infrastructure experiments.
     - **Checkout Entry Rate** — `CV_views / UV`. Best for CTA label and Deal page layout experiments.
     - **Revenue per Visitor** — `gross_revenue / UV`. Best for revenue-focused analysis.
     - **Margin per Order** — `margin_1_vfm / ue_orders`. Best for profitability of individual transactions.
     - **Gross Bookings per Visitor** — `gross_bookings / UV`. Best for experiments scoped to bookable deals.
     - **Deal View Rate** — `UDV / UV`. Best for Browse/Search/Discovery experiments measuring deal engagement.
   - If the experiment type is unknown or the user skips, default to Margin per Visitor — do not block progress waiting for a selection.
   - Record the final choice as `PRIMARY_METRIC`.
5. Follow the instructions in `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-evaluation-c3/SKILL.md` exactly, substituting `PRIMARY_METRIC` wherever "Margin per Visitor" is referenced as the primary KPI.
6. To generate the final Word document, read `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-report-document-structure/SKILL.md` and follow its instructions. This skill owns all document layout and formatting — do not apply docx formatting independently.
   - Note: ignore any path references to `/mnt/skills/user/ab-experiment-report-document-structure/SKILL.md` inside the evaluation skill — use the bundled version at `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-report-document-structure/SKILL.md` instead.
7. The final Word document (.docx) must clearly state which primary metric was used for the evaluation.
