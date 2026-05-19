---
description: Validate a pre-launch experiment brief and confirm the primary metric
allowed-tools: Read, AskUserQuestion, mcp__BigQuery_MCP__execute_sql, mcp__579a50aa-9191-470a-9b67-bfdfa57cd190__getJiraIssue, mcp__579a50aa-9191-470a-9b67-bfdfa57cd190__search
argument-hint: <MBNXT-ticket or experiment-name>
---

## FIRST ACTION — do this before anything else, before reading any files, before generating any text

Call the AskUserQuestion tool with exactly this structure:

```json
{
  "questions": [
    {
      "question": "How would you like to proceed?",
      "header": "Setup mode",
      "multiSelect": false,
      "options": [
        {
          "label": "Show me the template",
          "description": "Display the blank brief so I can fill it in and paste it to Jira myself"
        },
        {
          "label": "Guide me through the setup",
          "description": "Ask me one field at a time and produce a filled template at the end"
        }
      ]
    }
  ]
}
```

Do not read any files. Do not write any text. Call AskUserQuestion now with the structure above.

---

Once the user has answered, then read the skill and reference files:
1. Read `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-setup/SKILL.md`
2. Read `${CLAUDE_PLUGIN_ROOT}/skills/ab-experiment-setup/references/setup.md`

Then follow the mode the user selected (Mode A or Mode B below).

*(Argument provided, if any: $ARGUMENTS)*

---

## Mode A — Show me the template

Step A1 — Ask two quick questions using AskUserQuestion (both in a single call):

```json
{
  "questions": [
    {
      "question": "Which platform(s) will this experiment run on?",
      "header": "Platform",
      "multiSelect": false,
      "options": [
        { "label": "touch", "description": "Mobile web only" },
        { "label": "web", "description": "Desktop web only" },
        { "label": "app", "description": "iOS and Android apps" },
        { "label": "all", "description": "Touch + web + app" }
      ]
    },
    {
      "question": "What is your MDE — the smallest relative lift worth shipping?",
      "header": "MDE",
      "multiSelect": false,
      "options": [
        { "label": "5%", "description": "Aggressive — detects only large effects, shortest runtime" },
        { "label": "3%", "description": "Balanced — typical default for most experiments" },
        { "label": "2%", "description": "Conservative — catches smaller effects, longer runtime" },
        { "label": "1%", "description": "Very conservative — requires long runtime (60–90+ days)" }
      ]
    }
  ]
}
```

Step A2 — Run the A/A baseline BigQuery query from `references/setup.md` for the declared platform. Compute `days_needed` using:
```
δ = baseline_mpv × MDE_rel
days_raw = CEIL(7.85 × sigma_d² / δ²)
days_needed = max(days_raw, 14), rounded up to nearest 7
```

Step A3 — Display the runtime result clearly:
> **Estimated runtime: N days (X weeks)**
> Based on: platform=[platform], MDE=[MDE]%, A/A baseline σ_D=[sigma_d], baseline MPV=[baseline_mpv]
> Suggested end date if starting today: [today + days_needed]

Step A4 — Display the full blank brief template from `references/setup.md` (all four sections: SETUP, EXPERIMENT DESIGN, TIMELINE, RESULTS) as a clean copy-pasteable block, with `Duration (days)` pre-filled with the calculated value.

Add a note at the bottom:
> 💡 When you're done filling it in, come back and run `/setup-experiment <Jira ticket ID>` — I'll validate it and confirm your metrics.

Stop here. Do not ask any further questions.

---

## Mode B — Guide me through the setup

Walk the user through each field interactively using AskUserQuestion. Ask **one field at a time**.

### Round 1 — SETUP + RUNTIME (ask these first so the estimate is ready early)
1. **Owner** — Who is the experiment owner? (full name)
2. **Tag(s)** — What tags apply? (e.g. MBNXT, checkout, cta — comma separated)
3. **Jira Ticket ID** — What is the Jira ticket ID? (e.g. MBNXT-27180)
4. **GrowthBook Tracking Key** — What is the GrowthBook tracking key? (must start with `xp-`)
5. **Platform** — Which platform(s) does this experiment run on? Use AskUserQuestion with options: touch / web / app / all
6. **MDE Assumption** — What is the smallest relative lift worth shipping? Use AskUserQuestion with options: 5% / 3% / 2% / 1%

→ **After step 6**: immediately run the A/A baseline BigQuery query and show the runtime estimate:
> **Estimated runtime: N days (X weeks)**. If you start today ([date]), you should plan to end around [date].

7. **Target Population** — Who is being targeted? (e.g. All US logged-in users)
8. **Start Date** — When do you plan to launch? (suggest today's date as default)
→ Confirm: **Planned End Date** = Start Date + days_needed

### Round 2 — EXPERIMENT DESIGN
9. **Experiment Type** — What type is this experiment? Show the 7 options from the reference table and ask the user to pick one.
→ After receiving Experiment Type: auto-suggest Primary Metric and Guardrail Metrics from the lookup table. Ask the user to confirm or override.
10. **Description** — In one sentence, what are you testing and what outcome do you expect?
11. **Hypothesis** — Write your hypothesis as: "If we [change X], then [Y] will happen because [Z]"
12. **Control** — What does the user literally see in the control? (not a tech flag — describe the UI)
13. **Treatment A** — What does the user literally see in Treatment A?
14. **Treatment B** — Is there a Treatment B? (leave blank if A/B only)
15. **Estimated annual M1+VFM impact** — Rough annual business impact if it ships? (e.g. ~$200k–$300k)

### Round 3 — CONFIRMATION
Display the completed filled template with all answers substituted in. Then:
- Run the full 9-item validation checklist from `references/setup.md` against the filled brief
- Show each item as ✅ or ❌ with a short note on any failures
- If everything passes, say: "Your brief is ready. Copy the template above into your Jira ticket."
- If anything fails, list exactly what needs to be fixed before launch.
