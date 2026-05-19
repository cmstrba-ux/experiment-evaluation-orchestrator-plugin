# AB Experiments Plugin

Full A/B experiment lifecycle management for Groupon MBNXT experiments.

## Quick Start

This plugin is available as an org-level plugin — no setup needed, just press **Install** in Cowork.

**The fastest way to use it is with slash commands.** Type the command directly in chat and hit Enter — Claude loads the right skill immediately and guides you from there.

| What you want to do | Command |
|---|---|
| Validate an experiment brief before launch | `/setup-experiment` |
| Monitor a running experiment | `/monitor-experiment` |
| Evaluate a completed experiment | `/evaluate-experiment` |

> **Skip the plugin menu.** Avoid: ➕ Plus → Plugins → ab-experiments → Select skill.
> It works, but slash commands are faster and load with full context from the start.
> This matters most for `/setup-experiment` — it runs a structured pre-launch checklist that needs clean context to work correctly.

**Example:** About to launch a new experiment? Type `/setup-experiment` and hit Enter. Claude will ask for your experiment brief and walk you through the validation step by step, or provide a full list of required fields to fill in.

---

## Overview

This plugin covers every stage of the experiment lifecycle — from validating a brief before launch, to monitoring a live experiment for early harm, to producing a final SHIP/HOLD/KILL evaluation report once it ends.

It connects to your existing Jira (Atlassian), GrowthBook, and BigQuery integrations to pull the data it needs automatically.

When you run any command, the plugin will present the available metrics and ask which one you want to use as the **primary success metric** for your analysis.

---

## Components

### Commands

| Command | Description |
|---------|-------------|
| `/evaluate-experiment <id>` | Post-experiment evaluation — runs full statistical analysis and produces a Word document report with a SHIP/HOLD/KILL recommendation |
| `/monitor-experiment <id>` | Mid-experiment health check — checks SRM, guardrail breaches, futility, and directional signal for a running experiment |
| `/setup-experiment <ticket>` | Pre-launch validation — checks a Jira brief for missing or incorrectly filled fields before launch |

The `<id>` argument accepts either a GrowthBook Tracking Key (e.g. `xp-MBNXT-27180-cta-label`) or a Jira ticket number (e.g. `MBNXT-27180`). When given a Jira ticket, the plugin looks up the tracking key automatically.

### Skills (Bundled)

| Skill | Used by | Purpose |
|-------|---------|---------|
| `ab-experiment-evaluation-c3` | `/evaluate-experiment` | Full statistical evaluation pipeline — SRM, significance testing, power analysis, business impact |
| `ab-experiment-monitor` | `/monitor-experiment` | Mid-experiment health checks — harm detection, futility projection, directional signal |
| `ab-experiment-report-document-structure` | `/evaluate-experiment` | Word document generation — layout, formatting, and report structure |
| `ab-experiment-setup` | `/setup-experiment` | Pre-launch validation checklist and metric decision logic |

---

## Metric Selection

At the start of each command, the plugin presents the following metrics and asks you to choose your primary success metric:

| Metric | What it measures | Best for |
|--------|-----------------|---------|
| **Margin per Visitor** | M1+VFM earned per unique visitor | Browse/Search, Pricing/Promo experiments |
| **Conversion Rate** | Orders completed per unique visitor | Checkout flow, Auth, Infrastructure experiments |
| **Checkout Entry Rate** | Checkout page views per unique visitor | CTA label, Deal page layout experiments |
| **Revenue per Visitor** | Gross revenue earned per unique visitor | Revenue-focused analysis |
| **Margin per Order** | M1+VFM per completed order | Profitability of individual transactions |

The plugin auto-suggests the most appropriate metric based on the experiment type found in your Jira ticket — you can accept the suggestion or choose a different one.

---

## Usage

### Evaluate a completed experiment

```
/evaluate-experiment xp-MBNXT-27180-cta-label-buy-caption
```
or
```
/evaluate-experiment MBNXT-27180
```

### Check a running experiment

```
/monitor-experiment xp-MBNXT-31045-checkout-flow
```

Recommended cadence: no more than twice per week.

### Validate a brief before launch

```
/setup-experiment MBNXT-31045
```

---

## Requirements

| Connection | Used for |
|------------|----------|
| **Atlassian / Jira** | Fetching experiment briefs, variant descriptions, hypothesis, planned end dates |
| **GrowthBook** | Fetching experiment status, targeting conditions, traffic splits, metrics configuration |
| **BigQuery** | Running all statistical queries against the experiments data table |

---

## Data Source

All queries run against:
```
kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist
```

A/A baseline experiments used for power analysis:
```
xp-MBNXT-30862-AA-test-desktop
xp-MBNXT-30862-AA-test-touch
```
