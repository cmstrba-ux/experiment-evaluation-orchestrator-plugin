---
name: render-combined-report
description: Compose the final combined HTML + exec summary from raw JSON intermediates produced by the AB / SEO / deal-charts subagents. Invoked by orchestrator-workflow as the last step.
---

# render-combined-report

## Inputs
- `run_dir`: directory containing `raw/{ab,seo,deal}_*.json` files
- `data_through`: max event_date across all raw JSONs (string)
- `run_id`: human-readable run id (YYYY-MM-DD-HH-MM)

## Steps

1. Verify `run_dir/raw/` exists and has at least one `ab_*.json` file.
2. Run:

   ```
   python -m scripts.lib.render \
     --run-dir <run_dir> \
     --out <run_dir>/combined_report.html \
     --summary <run_dir>/summary.md \
     --run-id <run_id> \
     --data-through <data_through>
   ```

3. Copy any passthrough artifacts (per-experiment .docx, .xlsx, plugin SEO HTML) into `<run_dir>/passthrough/` if they exist (run-ab-evaluation and run-seo-evaluation already write there).
4. Print final paths to stdout: combined_report.html, summary.md, passthrough/ (if any).

## Tool contract
- No BQ access in this skill — purely consumes JSON + writes HTML/MD.
- `render.py` does no I/O beyond the input JSONs and the two output files.

## Composed Final verdict (DEPLOY / HOLD / KILL)

Every exec card and the `summary.md` scoreboard surface a composed AB+SEO verdict at the top, computed deterministically by `scripts/lib/render.py:_compose_final_verdict`. The same function feeds the JS-side `D.composed_*` payload fields so HTML and Markdown always agree.

### The composed metric

`Net Margin / Visitor %Δ = (1 + m1uv_%Δ_AB) · (1 + clicks_DiD_%Δ_SEO) − 1`

This is the standard Traffic × Margin/visitor funnel decomposition — clean because the AB M1/UV already contains the CVR effect, so multiplying SEO clicks (= traffic uplift) doesn't double-count. AB measures effect on margin per existing visitor; SEO measures effect on number of visitors. The product is total margin per unit of pre-experiment traffic.

A 90% confidence interval is built via the delta method on the product, treating the two effects as independent:

```
Var(composed) ≈ (1+c)² · Var(m) + (1+m)² · Var(c)
```

SEs are recovered in this priority order:
- **AB M1+VFM/UV**: explicit `stats.m1uv.se` → `|effect| / |t_stat|` → `recover_se_from_p(effect, p, p_floor=0.001)`.
- **SEO clicks DiD**: explicit SE if upstream surfaces one (none today) → `recover_se_from_p(effect, power_analysis.p_value, p_floor=0.001)`. The 0.001 floor handles the upstream `p=0` case (below-resolution significance) conservatively without collapsing the CI to a point.

### Decision hierarchy (strictly ordered)

The verdict is resolved in this order — the first rule that fires wins:

1. **Hard guardrails** — vetos. KILL regardless of what the composed CI says.
   - **AB CVR significantly negative**: `cvr_pct ≤ −1.0%` AND `p < 0.05`. UX regression that the margin-per-visitor composition can mask.
   - **SEO impressions DiD at full signal**: `did_impressions_pct ≤ −10%` AND `signal_strength == 'full'`. Leading indicator for long-term ranking decay; the SearchPilot/Optibase kill-switch convention. Impressions (not clicks) because ranking shows up there first.
2. **Data-quality short-circuit**: if SRM is still failing on the AB-Overall view after the active_visitor remediation attempt, fall through to the label matrix (composed CI isn't trusted when the bcookie split is biased).
3. **Composed funnel 90% CI rule** (when both component SEs are recoverable):
   - `lower > +MWSE` (default +0.5%) → **DEPLOY** — significantly positive AND material.
   - `upper < −MWSE` → **KILL** — significantly negative.
   - straddles ± MWSE → **HOLD**.
4. **Label-matrix fallback** — only reached when SEs aren't recoverable (very rare with the new SE plumbing). Preserves the original 4×4 AB-verdict × SEO-bucket matrix so degenerate runs still produce a sensible verdict.

The `composed_basis` payload field tells the reader which rule fired: `ci` / `guardrail` / `matrix`. The exec card surfaces this as a small chip next to the Final verdict so the rigor level is visible.

### Tunable defaults

Set at the top of `scripts/lib/render.py`:

| Constant | Default | Meaning |
|---|---|---|
| `_DEFAULT_MWSE_PCT` | 0.5 | Minimum Worth-Shipping Effect in % — below this the lift isn't worth the rollout/maintenance cost. |
| `_DEFAULT_CI_ALPHA` | 0.10 | CI level (90%) — industry convention for product-decision CIs (Microsoft, Booking.com); 95% is for academic significance. |
| `_GUARDRAIL_SEO_IMP_PCT_FULL_SIGNAL` | −10.0 | Hard floor on impressions DiD at full signal. |
| `_GUARDRAIL_CVR_NEG_PCT` | −1.0 | CVR negative threshold for the UX guardrail. |
| `_GUARDRAIL_CVR_P_THRESH` | 0.05 | p-value threshold for the CVR guardrail. |

### Worked example — FAQ reviews (2026-04-06 → 2026-04-25)

- AB M1+VFM/UV: +1.79% (t=1.04, n=20) → SE ≈ 1.72pp via `|effect|/|t_stat|`.
- SEO clicks DiD: −4.03% (p=0.0, clamped to 0.001 for SE recovery) → SE ≈ 1.22pp.
- Composed: (1.0179)(0.9597) − 1 = **−2.28%**.
- 90% CI: [−5.69%, +1.13%]. CI straddles zero ± 0.5% → CI rule says **HOLD**.
- SEO impressions DiD = −16.05% at full signal → trips guardrail → **KILL via guardrail**.
- Rationale: *"Guardrail tripped: SEO impressions DiD −16.05% at full signal trips the organic-ranking-risk floor of −10%. (Composed net margin/visitor would be −2.28% — guardrails veto regardless.)"*

This is a meaningful improvement over the old label-matrix KILL: the user now sees that the AB+SEO trade-off is genuinely uncertain (CI straddles zero) and the KILL comes specifically from the long-term ranking risk, not from a confident negative composite.

### Caveats

- **Independence assumption** in the CI math: AB and SEO are measured on overlapping populations / time windows, so some correlation exists. The independence-based CI is within a few percent of the true CI for typical experiments; flag if a use case needs joint covariance.
- **p-clamp at 0.001** for SE recovery is conservative — for an upstream `p=0` it underestimates how significant the test really was, producing a wider-than-true CI. That's the safer direction (less likely to over-confidently DEPLOY).
- **The composed metric measures organic margin per unit of organic traffic**. Paid traffic isn't in this composition. For experiments dominated by SEM/affiliate traffic the AB lift may matter more than the SEO term suggests.

## What the renderer produces

`combined_report.html` is a single self-contained HTML file with:
- **Executive summary**: top tally (`N experiments evaluated · X deploy · Y hold · Z kill`) + per-experiment exec cards. Each card shows the composed Final verdict at the top of the takeaway block (pill + rationale), followed by Confidence / Why / Action rows. The card's left-border color (green / amber / red) reflects the Final verdict, not the AB-only verdict.
- **Scoreboard cards** per experiment (label, SRM, M1/UV + CVR Δ, Overall MPV mean Δ, SEO DiD headlines if available, verdict)
- **Per-experiment tab** with sub-tabs:
  - **Overview**: side-by-side daily M1/UV and CVR line charts; KPI cards.
  - **Per Category**: 4-column heatmap (M1/UV + CVR × Filtered + Overall) with significance markers; per-category sub-tabs each with daily Filtered + Overall trend charts.
  - **SEO**: pre/post window KPIs; overall DiD table (variant vs control, day-normalized, populated when `did_overall` is provided); per-L2 DiD heatmap row; per-L2 top 15 winners + losers from `per_url`; raw variant-only pre/post bars.
  - **Deals**: top winners + top losers tables with linked deal titles → groupon.com; by_category and by_booking_platform tables.

## Schema expected in raw JSONs

Each subagent enriches its JSON with the fields the renderer needs:

- `ab_<alt>.json` may include `per_category` (filtered, deal-scoped per cat) and `per_category_overall` (population-wide per cat). The renderer's heatmap uses both; if `per_category_overall` is absent it shows "n/a" for those columns.
- `seo_<alt>.json` may include `did_overall`, `did_per_l2`, `l2_topk` (top 15 winners/losers per L2 by clicks_delta). When `did_overall` is missing the renderer surfaces an explicit "DiD not computed" notice.
- `deal_<alt>.json` top winners/losers should include `company_name` + `deal_title` for clean hyperlinks.

## Failure modes
- Empty run_dir → renderer writes a stub HTML and exits 0.
- Schema regression in a per-experiment JSON → renderer does best-effort with safe fallbacks (`?? 0`, `n/a` cells); never throws.
