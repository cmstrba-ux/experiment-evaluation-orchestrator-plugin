# experiment-evaluation-orchestrator

Reads experiments from a `test_definitions` table, fans out parallel AB / SEO / deal-charts evaluation, and produces a single combined Chart.js HTML report.

The combined report includes:
- **Executive summary** with per-experiment cards: composed Final verdict (DEPLOY/HOLD/KILL), `Net margin / visitor` headline tile with 90% CI band, basis chip (`CI` / `guardrail` / `matrix`), and a one-sentence rationale.
- Per-experiment scoreboard (Label, SRM, M1/UV + CVR daily Δ, AB + SEO verdicts)
- Overview tab: side-by-side M1/UV and CVR daily line charts (Treatment vs Control)
- Per-Category tab: 4-column heatmap (M1/UV + CVR × Filtered + Overall) and per-category sub-tabs with daily Filtered + Overall trend charts
- SEO tab: pre/post window KPIs, overall DiD (variant vs control, day-normalized) and per-L2 DiD heatmap, per-L2 top-15 winners + losers from per_url, raw variant-only pre/post bars
- Deals tab: top winners + top losers tables with hyperlinked deal titles

## Final verdict (DEPLOY / HOLD / KILL)

Every exec card and the `summary.md` scoreboard carry one composed verdict — the bottom-line "should we deploy" recommendation given **both** the AB result and the SEO impact.

### The composed metric

`Net Margin / Visitor %Δ = (1 + m1uv_%Δ_AB) · (1 + clicks_DiD_%Δ_SEO) − 1`

The clean Traffic × Margin/visitor funnel — no double-counting because AB M1/UV already contains the CVR effect. A 90% confidence interval is built via the delta method on the product. Component standard errors are recovered in priority order:

1. Explicit `stats.m1uv.se` from the AB subagent.
2. `|effect| / |t_stat|` when `t_stat` is emitted.
3. Inverse-normal `|effect| / z(1 − p/2)` from the p-value, with `p` clamped to a 0.001 floor so an upstream `p=0` produces a conservative finite SE rather than collapsing the CI to a point.

### Decision hierarchy (strictly ordered)

The first rule that fires wins:

1. **Hard guardrails** (KILL on trip, vetoes — independent of the composed CI):
   - **AB CVR significantly negative**: `cvr ≤ −1%` AND `p < 0.05`. Catches UX regressions that the margin-per-visitor composition can mask.
   - **Full-signal SEO impressions DiD**: `≤ −10%` when signal is `full`. Leading indicator for long-term ranking decay; impressions (not clicks) because ranking shows up there first. Matches the SearchPilot/Optibase kill-switch convention.
2. **Data-quality short-circuit**: SRM persistent fail (raw fail + active-visitor remediation didn't pass) → fall back to label matrix; composed CI isn't trusted when the bcookie split is biased.
3. **Composed funnel 90% CI rule** (when both component SEs are recoverable):
   - `lower > +MWSE` (default +0.5%) → **DEPLOY** — significantly positive AND material.
   - `upper < −MWSE` → **KILL** — significantly negative.
   - straddles ± MWSE → **HOLD**.
4. **Label-matrix fallback** when SEs are unrecoverable. Preserves the original 4×4 AB-verdict × SEO-bucket matrix so degenerate runs still produce a sensible verdict.

The `composed_basis` field on every card tells you which rule fired — `CI`, `guardrail`, or `matrix` — so the level of statistical rigor behind the verdict is always visible.

### Tunable defaults

Set as module constants at the top of `scripts/lib/render.py`:

| Constant | Default | Meaning |
|---|---|---|
| `_DEFAULT_MWSE_PCT` | 0.5 | Minimum Worth-Shipping Effect in %. Below this the lift isn't worth rollout/maintenance cost. |
| `_DEFAULT_CI_ALPHA` | 0.10 | CI level (90%). Industry convention for product-decision CIs (Microsoft, Booking.com); 95% is for academic significance. |
| `_GUARDRAIL_SEO_IMP_PCT_FULL_SIGNAL` | −10.0 | Hard floor on impressions DiD at full signal. |
| `_GUARDRAIL_CVR_NEG_PCT` | −1.0 | CVR negative threshold for the UX guardrail. |
| `_GUARDRAIL_CVR_P_THRESH` | 0.05 | p-value threshold for the CVR guardrail. |

### Caveats

- **Independence assumption** in the CI math — AB and SEO are measured on overlapping populations / time windows, so some correlation exists. The independence-based CI is within a few percent of the true CI for typical experiments.
- **p-clamp at 0.001** for SE recovery is conservative — for an upstream `p=0` it underestimates how significant the test really was, producing a wider-than-true CI. That's the safer direction (less likely to over-confidently DEPLOY).
- **The composed metric measures organic margin per unit of organic traffic.** Paid traffic isn't in this composition; for experiments dominated by SEM/affiliate traffic the AB lift may matter more than the SEO term suggests.

Full rule and worked example: see `skills/render-combined-report/SKILL.md`.

## Slash command

- `/evaluate-reviews-experiments [<alternate_name> | --auto | --since YYYY-MM-DD | --rerender <run-id>]`

## Tool contract

- Read-only BigQuery via the `bq` CLI (never MCP, never DDL/DML).
- URL and metadata resolution via local deal-dimension tables (no external service calls required at runtime).
- All evaluation branches share the same date-window logic from `test_definitions`.

## Required dependencies (soft)

- AB evaluation plugin (skills: `ab-experiment-evaluation-c3`, `ab-experiment-monitor`)
- SEO impact plugin (skills: `seo-guardrails`, `seo-page-classifier`, `seo-gsc-fetcher`, `seo-impact-analyzer`, `seo-report-generator`)

## Install

Install from a plugin marketplace that hosts this plugin:

```
/plugin marketplace add <marketplace-url>
/plugin install experiment-evaluation-orchestrator
```
