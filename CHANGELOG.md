0.1.0 — plugin scaffolding + marketplace.json registration
0.1.0 — tool_contract.py + tests
0.1.1 — stats.paired_ttest, stats.cohens_d
0.1.2 — stats.srm_chi_square, stats.did
0.1.3 — bq_queries.list_experiments
0.1.4 — bq_queries.ab_filtered_{raw,remediated}
0.1.5 — bq_queries.ab_overall_{raw,remediated}
0.1.6 — bq_queries.resolve_deal_urls
0.1.7 — bq_queries.deal_{top_winners_losers,by_category,by_booking_platform}
0.1.8 — schema fixtures + drift validator
0.1.9 — skills/list-experiments
0.1.10 — skills/resolve-deal-urls
0.1.11 — skills/run-ab-evaluation (revised Option B)
0.1.12 — skills/run-seo-evaluation (revised thin coordinator)
0.1.13 — skills/run-deal-charts
0.1.15 — exec_summary.md.j2
0.1.17 — skills/render-combined-report
0.1.18 — skills/orchestrator-workflow
0.1.19 — commands/evaluate-experiments
0.1.14 — render.py + idempotency test
0.1.16 — templates/report.html.j2 full Chart.js scaffold

0.2.0 — Major report overhaul:
  - render.py rewrite: builds HTML inline (no Jinja for body), strips per_url before embed,
    NaN → null cleanup, autoescape disabled for the embedded JSON payload, accepts --run-id
    and --data-through and writes summary.md too. Frontend lives in render_app.js.
  - report HTML adds: CVR alongside M1/UV everywhere, 4-column per-cat heatmap (M1/UV + CVR ×
    Filtered + Overall), per-cat sub-tabs with daily Filtered + Overall trend charts, SEO
    DiD + DiD-by-L2 sections, per-L2 top-15 winners/losers from per_url, hyperlinked deal
    titles in winners/losers tables.
  - skills/resolve-control-urls (new): samples non-experiment groupon.com 'deals' URLs in
    same L2s, ranked by pre-period impressions. Required so seo-impact-analyzer can compute
    DiD natively (was previously empty for variant-only inputs).
  - skills/run-seo-evaluation: now merges variant + control URL sets, post-processes per_url
    into l2_topk + did_per_l2 + did_overall aggregates, drops per_url before writing JSON
    so the combined report stays under ~200 KB.
  - skills/run-ab-evaluation: adds per-category Overall (population-wide) view via
    bq_queries.overall_per_cat_daily.
  - skills/run-deal-charts: enriches top winners/losers with company_name + deal_title from
    deal_option (single follow-up lookup) so the renderer can produce clickable rows.
  - skills/orchestrator-workflow: adds a resolve-control-urls step before SEO subagent fan-out.
  - skills/render-combined-report: passes --run-id + --data-through; writes summary.md too.
  - bq_queries.sql: + resolve_control_urls, + seo_did_l2 (fallback DiD aggregator),
    + category_daily, + overall_per_cat_daily.
  - exec_summary.md.j2: fix stats path (subagents nest under stats.treatment.*).
  - render.py + skills: switch displayed %Δ from daily-mean-based to aggregate-ratio
    (SUM(num)/SUM(den)). This matches the ab-experiments plugin canon ("Margin per Visitor =
    SAFE_DIVIDE(SUM(margin_1_vfm), SUM(UV))") and Groupon dashboards. p-value still comes
    from paired t-test on daily ratios (also plugin canon). Daily rows in per_category[*].daily
    + per_category_overall[*].daily are now expected to carry the underlying totals
    (uv_ctrl/treat, m1_ctrl/treat, udv_ctrl/treat, orders_ctrl/treat) alongside ratios.
  - scoreboard cards: SEO headline block (Impressions DiD, Clicks DiD, CTR DiD + signal level
    badge) when seo.did_overall is populated; falls back to variant-only raw Δ + a "no control"
    note when control set wasn't provided.

0.2.1 — Variant naming convention + active-visitor remediation auto-promotion:
  - bq_queries.deal_top_winners_losers: now takes @ctrl_name parameter (was hardcoded to
    'control'). Without this, true/false experiments produced m1_ctrl=0 for every row and
    "winners" became "highest absolute treatment spend" — meaningless rankings.
  - render.py:
    - _flatten_stats now lifts the m1uv sub-dict to top level so the scoreboard's mean_delta
      / p_value reads correctly. Previously summary.md showed "+0.0000 (p=1.000)" for every
      experiment because the subagent emits stats keyed under m1uv, not at top level.
    - Daily-shape normalization no longer clobbers rows that already carry m1_ctrl/uv_ctrl
      (current subagent shape) by overwriting them with all-zero {d, ctrl, treat} rows.
    - New _resolve_canonical_ctrl + _swap_ctrl_treat_inplace helpers apply the variant
      naming convention: control/treatment → control is ctrl; true/false → true is ctrl,
      false is treat (per stakeholder convention; reflects how Groupon GrowthBook flags
      map to "no override" vs "override active"). When a JSON's stats.ctrl_name disagrees
      with the canon, all *_ctrl ↔ *_treat fields are swapped in raw, remediated, per_category,
      per_category_overall, and the sibling deal JSON's by_category, by_booking_platform,
      top_winners, top_losers (with deltas recomputed).
    - New _promote_remediated_when_srm_fails: when raw SRM fails AND remediated SRM passes,
      the remediated view (active_visitor_flag='Y') replaces the raw view as the primary
      source for the scoreboard, headline KPIs, and per-experiment HTML tab. Original raw
      view preserved under raw_pre_remediation.
  - render_app.js: SRM card uses ctrl_name/treat_name to look up observed bcookies (not
    hardcoded obs.control/obs.treatment, which were undefined for true/false experiments).
    Surfaces "using active_visitor remediation" when the view was promoted.
  - skills/run-ab-evaluation/SKILL.md: documents the variant naming convention and the
    automatic remediation-promotion behaviour.
  - skills/run-deal-charts/SKILL.md: documents the convention, requires emitting
    ctrl_name in the output JSON, and instructs the subagent to pass @ctrl_name to
    deal_top_winners_losers.

0.2.2 — Drop SEO control + runway projection + clearer raw-SRM surfacing + remove
        by-booking-platform table:
  - bq_queries.sql: removed `deal_by_booking_platform` (no longer rendered).
  - render.py:
    - new _compute_runway helper: projects additional days needed to lift p below 0.05
      using paired-t scaling (n_req ≈ n × (1.96/|t|)²). Returns {already_significant},
      {infeasible, reason}, or {n_required, additional_days, current_p/t/d}. Capped at
      365 days; |t| < 0.3 marked infeasible.
    - build_payload now emits runway_filtered + runway_overall.
    - summary.md scoreboard adds a Runway column ("+14d to p<0.05" / "infeasible") and
      the SRM column shows the raw verdict explicitly: "raw fail → active_visitor pass"
      when remediation kicked in (was just "pass (active-visitor)" — easy to misread).
    - _promote_remediated_when_srm_fails now preserves the FULL original SRM dict
      (chi_sq, p_value, observed, expected_n) under srm[view].original so the JS card
      can show both rows side-by-side.
    - adapt_deal no longer touches by_booking_platform.
  - render_app.js:
    - removes the by_booking_platform table from the Deals tab.
    - removes the "DiD not computed" warning banner — variant-only is now the intended
      default rather than a missing-setup state. Per-L2 DiD table only renders when DiD
      data is actually present.
    - SRM Overview card now shows two rows when remediation kicked in: "SRM — raw bcookie"
      with the failed χ²/p_value and observed split, and "SRM — active_visitor (used)"
      with the passing values.
    - Scoreboard card surfaces "SRM raw fail → active_visitor pass" badge + a second SRM
      row with the raw χ². Adds a "Runway to p<0.05" row when result is not significant.
  - skills/orchestrator-workflow/SKILL.md: drops the resolve-control-urls step. SEO
    subagent now runs variant-only by default.
  - skills/run-seo-evaluation/SKILL.md: control_urls input removed; merged URL set step
    becomes "variant URLs only"; output schema drops did_overall / did_per_l2.
  - skills/run-deal-charts/SKILL.md: removes step 4 (deal_by_booking_platform) and the
    by_booking_platform output field.
  - skills/run-ab-evaluation/SKILL.md: documents the renderer-side runway projection +
    "raw fail → active_visitor pass" surfacing.
  - skills/resolve-control-urls/SKILL.md: kept in the plugin for explicit DiD callers,
    but no longer invoked by orchestrator-workflow.

0.2.3 — SEO DiD relabeled "variant vs All Groupon" + folded into Per Category tab:
  - skills/orchestrator-workflow/SKILL.md: re-introduces the resolve-control-urls step.
    The sampled "control" set is in fact non-experiment Groupon /deals/ pages in matching
    L2s — i.e. "All Groupon (deal)" — and was the natural comparison for DiD. Stopping
    its propagation in 0.2.2 turned out to be the wrong call; restored as default while
    keeping the SEO subagent's variant-only fallback when control_urls is missing.
  - skills/run-seo-evaluation/SKILL.md: control_urls re-listed as input (still optional).
    Added a naming note: JSON keys stay `control` (analyzer schema) but the renderer
    relabels to "All Groupon" in user-facing strings.
  - render.py:
    - new `_merge_categories(ab, seo)`: per-category list now includes SEO L2 keys when
      the AB experiment doesn't split by category. The Per Category tab no longer says
      "No per-category data available" just because use_deal_category_split=FALSE — it
      surfaces the SEO L2 view instead.
  - render_app.js:
    - heatmap grows from 4 data columns to 7: adds "SEO DiD (variant vs All Groupon)"
      group with Impressions Δpp + Clicks Δpp + CTR Δpp per L2, alongside the existing
      AB-Filtered / AB-Overall M1/UV + CVR cells. URL counts shown as the cell sub-label.
    - per-category sub-tabs append a new "SEO — variant vs All Groupon (L2)" section
      with KPI tiles (Imp DiD, Clk DiD, CTR DiD) and a side-by-side variant vs All
      Groupon table for URL counts and pre/post impressions+clicks totals.
    - sub-tabs now skip empty AB chart sections cleanly when the experiment has no AB
      per-category split, with a one-line note explaining why.
    - Overall DiD table on the SEO tab + DiD-by-L2 table + scoreboard SEO block all
      relabeled "Control" → "All Groupon".

0.4.0 — Aggregate-ratio enforcement + scorecard redesign:
  - render.py:
    - stats_for_daily(): removed the daily-mean fallback. When a subagent emits ratios
      without underlying totals, the function now returns None instead of computing a
      daily-mean pct. The previous fallback meant a subagent that drifted back to
      daily-mean could leak that pct through to displayed scorecards.
    - New _recompute_view_metrics(view, ratio_keys=("m1uv","cvr")): walks a view's
      `daily` rows, recomputes m1uv/cvr blocks via stats_for_daily(), and replaces both
      top-level (per_category[*]) and nested (raw.filtered.stats) shapes in place.
      Subagent-emitted mean_delta_pct is unconditionally overridden — daily-mean values
      can no longer reach the renderer surface.
    - build_payload(): runs _recompute_view_metrics on raw.filtered, raw.overall, every
      per_category[*], and every per_category_overall[*]. Single point of enforcement for
      the ab-experiments canonical %Δ = SUM(num)/SUM(den) (matches Groupon dashboards).
    - render_summary methodology line now leads with "%Δ: aggregate ratio SUM(num)/SUM(den).
      Daily means are not used."
    - HTML/CSS: new .sec-title, .metric-row, .metric-row.hero, .funnel-detail, .card-details,
      .pmeta, .sigstar styles for the redesigned scoreboard.
  - render_app.js:
    - Scoreboard rebuilt with importance-based ordering and section-aware coloring:
      1) AB Test (filtered): M1/UV %Δ (hero) + CVR %Δ — color-tinted by sign and
         saturation, deeper if p<0.05. AB verdict badge.
      2) SEO (DiD vs synthetic peer): DiD Clicks % (hero) + DiD Impressions % + DiD CTR pp
         — color-tinted with a wider ±15% saturation scale appropriate to SEO magnitudes.
         SEO verdict + signal badges.
      3) Expected funnel impact: composed total = (1+SEO clicks) × (1+M1/UV) − 1 with a
         three-stage breakdown (Traffic × Conversion × Margin/order). MPV (margin/order)
         is derived as (1+M1/UV)/(1+CVR)−1 so the stages compose without double-counting
         CVR (M1/UV already captures it within the AB population).
      4) Details (collapsed <details>): deals count, runway projection, SRM χ² rows —
         muted, no coloring. Previously these sat between important rows and dragged the
         eye away from the headline numbers.
    - New helpers: metricTint(pct, p, scale) for tinted backgrounds with significance
      depth; expectedFunnelTotal(clicksPct, m1uvPct) for the composed total;
      mpvFromM1UVAndCVR(m1uvPct, cvrPct) for the derived margin/order stage.
    - Removed broken `o.mean_delta` reference (left over from the prior MPV row that
      relied on the deleted daily-mean local — would have thrown ReferenceError on every
      card render).
  - tests/test_aggregate_ratio.py: 8 tests covering aggregate-vs-daily-mean discrimination
    in stats_for_daily, recompute override of subagent-emitted daily-mean pct, top-level
    and nested view shapes, end-to-end build_payload pass.
  - skills/run-ab-evaluation/SKILL.md: documents the renderer-side recompute pass and
    the no-daily-mean-fallback contract.

0.5.0 — CEO-ready report: Executive Summary + many scorecard refinements:
  - render.py:
    - New top-level "Executive Summary" section above the scoreboard. Per-experiment
      cards render the experiment name + verdict badges, four headline metric tiles
      (M1/UV %Δ, CVR %Δ, SEO Clicks DiD, composed Total margin %Δ), and a one-sentence
      takeaway pulled from the evaluator's hand-written narrative (or synthesized when
      the docx narrative isn't loaded). Top tally shows N experiments evaluated and
      ship/kill/other counts.
    - build_payload now exposes unfiltered_m1uv / unfiltered_cvr from raw.overall.daily
      so the scorecard hero metric and funnel composition use population-wide AB
      results instead of deal-scoped (filtered) ones. Legacy overall_m1uv / overall_cvr
      kept for backward compat.
    - Date-window fallback: when ab.start_date / end_date are null but daily rows have
      dates, derive the window from min/max of raw.overall.daily (or filtered).
    - _backfill_remediated_srm: when the AB subagent skips the SRM check on the
      remediated cohort but emits variant.total_uv counts, compute SRM ourselves
      (math.erfc + chi-square one-df, α=0.001) so the remediation-promotion logic can
      actually surface "raw fail → active_visitor pass" instead of a misleading
      "persistent SRM" headline.
    - _extract_docx_narrative: parses the AB evaluator's passthrough .docx and stores
      structured sections (Executive Summary, What the data shows, What remains
      uncertain, Action items, Final Recommendation, plus per-Step bodies) under
      ab.evaluation_narrative. Surfaced into payload as evaluation_narrative.
    - _compute_label rewritten: label now keys off significance + runway, not on the
      verdict string. p<0.05 OR runway>56d → "FINAL — can be closed"; not significant
      with runway≤56d → "FINAL" (could extend), regardless of verdict. Fixes the
      contradiction we hit on AI_Summaries (verdict=KILL, p=0.07, runway=+2d) showing
      "FINAL — can be closed" alongside a "+2d to p<0.05" runway.
    - badge-final restyled to neutral gray (was green) — completion is not a result;
      green should mean "good news", not "test ended".
    - New CSS for sec-title, metric-row, metric-row.hero, funnel-detail, card-details,
      rationale, narrative-section, exec-card, exec-tile, plus header-row (split
      title + right-aligned meta) and exp-deals (small subtitle).
    - HTML title changed to "Review Experiments evaluation".
  - render_app.js:
    - Scoreboard rebuilt with importance-based ordering: header → Expected funnel
      impact → AB Population-wide → SEO → collapsed Details. Color-tinted metric rows
      with significance depth. SRM pill hidden on clean pass; neutral when remediated;
      red on hard fail. Funnel formula text moved to Details.
    - SEO scorecard row drops DiD CTR pp (was rarely populated and added noise).
    - Funnel rebuilt with honest two-stage math: Traffic × Margin/visitor = Total,
      with CVR × Margin/order shown as decomposition (M1/UV already includes CVR ×
      MPV, so we don't multiply CVR a third time). Title renamed to "Estimated total
      margin impact". Formula + interpretation hint live in Details.
    - Per-experiment Overview tab renamed to "AB experiment". Tab order: AB
      experiment → SEO → Per Category → Deals.
    - Overview rationale block: prefers evaluator's docx narrative, falls back to
      synthesized "Why <verdict>?" rationale when narrative isn't loaded.
    - Removed redundant KPI cards from the Overview tab (they used a different cohort
      source than the scorecard and produced confusingly different numbers).
    - Per-category heatmap reordered: Totals → SEO DiD → AB Overall → AB Filtered
      (was: Filtered → Overall → SEO). "Control / Treatment" stacked under a single
      "Totals" parent header. Rows sorted by total M1 (control + treatment) desc —
      heaviest categories first.
    - Per-category trend chart fix: switched canvas IDs from row-index based to
      slug(cat) based so chart-init lookups still work after the row sort. Replaced
      setTimeout(0) with double-rAF so charts measure non-zero canvas dims after the
      display:none → display:block parent transition completes.
    - Deals tab trimmed to Top Winners + Top Losers (dropped By-Category table).
    - Card layout tuned: minimum width 320px → 380px, h3 1.02rem with overflow-wrap
      so long experiment names don't push to multiple lines.
    - Header restructured: title "Review Experiments evaluation" + right-aligned
      segmented meta (N experiments · run X · data through Y).
  - tests/test_aggregate_ratio.py: 8 tests still pass after the v0.5 refactor.
  - skills/run-ab-evaluation/SKILL.md: documents the rationale-and-narrative pull,
    the unfiltered-headline convention, and the relabeled funnel section.
