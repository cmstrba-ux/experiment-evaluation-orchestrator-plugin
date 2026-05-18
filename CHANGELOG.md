0.7.2 — Exec-card readability + SEO TOO EARLY treatment + IQ auto-publish:
  - render_app.js:buildExecCard / new buildFinalRow — Final verdict row promoted ABOVE
    the metrics tiles. Bottom-line recommendation is now the first thing readers see
    after the experiment name; Confidence / Why / Action stay below tiles. Was burying
    the verdict at the bottom of the takeaway block, two scrolls from the metric tiles
    that justify it.
  - render.py:build_payload / render_summary — SEO TOO EARLY flag (`seo_too_early`,
    `seo_days_elapsed`, `seo_days_needed_total=14`) derived from queue.json's
    `evaluate_seo_since`. When the SEO release date is < 14 days old AND SEO didn't run:
      * SEO tiles render "TOO EARLY — X/14 days needed" instead of "n/a"
      * SEO header badge becomes "TOO EARLY  X/14 days" instead of "unknown"
      * Final verdict pill gains a PRELIMINARY chip ("SEO not yet eligible — verdict is
        AB-only") so the AB-only composition can't be mistaken for the full picture
      * summary.md SEO line becomes "TOO EARLY — X/14 days needed for preliminary results"
    Matches the existing orchestrator-side dispatch gate (skills/list-experiments and
    orchestrator-workflow already skip SEO when evaluate_seo_since > today-14); the
    renderer now surfaces that intentional skip instead of falling back to a generic
    n/a state.
  - render.py:load_run — reads `<run_dir>/queue.json` (already written by the
    /evaluate-reviews-experiments command) and joins `evaluate_seo_since` onto each
    experiment dict by alternate_name. Single source of truth — subagent JSONs don't
    need a contract change to carry the field.
  - render.py:HTML_SHELL — header gains an inline "↻ Rerun" pill linking to
    https://github.com/cmstrba-ux/experiment-evaluation-orchestrator-plugin so any
    viewer can clone the plugin and rerun the analysis locally. Styled as a translucent
    pill next to the title; doesn't compete with `hdr-meta` on the right.
  - skills/orchestrator-workflow/SKILL.md — Step 11 added: publish combined_report.html
    to Groupon IQ with the canonical title `Experiment Evaluation <YYYY-MM-DD>` where
    the date is the run_id prefix (the day the orchestrator ran, not data_through —
    data freshness drifts on reruns even when the analyst's intent is the same
    publication). No experiment names — versioning is the dedup mechanism. Existing reports with
    that title are versioned via the /versions endpoint; otherwise create_report +
    versions. Folder ID dbdf853d-55c8-4780-ad03-35441e5ffc10 ("AI summaries" — the
    established convention). Skips silently when IQ_API_KEY is missing or --no-publish
    is set; never fails the run on publish errors.

0.7.1 — Plugin resolution via canonical registry (no more cache-path globbing):
  - scripts/run_seo_pipeline.py:_find_seo_plugin_root — rewritten to read
    `~/.claude/plugins/installed_plugins.json` (the canonical Claude Code plugin
    registry). Every installed plugin records its `installPath` there regardless of
    how it was sourced — local marketplace `./...` path, remote `url:`, or
    `github:`. Previous implementation globbed `~/.claude/plugins/cache/*/seo-impact-
    plugin/*/...` directly, which (a) hard-coded the cache as the storage location
    and broke if upstream's SHA changed mid-session, (b) silently picked the most
    recently-modified candidate from a glob (potentially the wrong version), and
    (c) wouldn't have worked if seo-impact-plugin were ever moved to a local-source
    layout. New implementation reads the registry, finds any `seo-impact-plugin@*`
    entry, and verifies the installPath contains the expected scripts. Cache glob
    is retained as a defensive fallback only — used when the registry is missing
    or doesn't list the plugin. Smoke-tested: registry resolves to the same path
    the glob would have found, plus a `compute_verdict` cache-freshness assertion.
  - commands/evaluate-reviews-experiments.md Step 3 — dependency check rewritten
    to read `installed_plugins.json` directly via a one-line python snippet that
    checks for `ab-experiments@*` and `seo-impact-plugin@*` entries. No more
    hard-coded paths to `cache/...` or `local-marketplaces/...` — the registry is
    the one stable lookup that works for any plugin source type. Exit code 0 =
    both present; non-zero with a "Missing: ..." message otherwise.

0.7.0 — Statistical Final verdict: joint AB+SEO CI + hard guardrails (OEC + guardrails pattern):
  - scripts/lib/stats.py — three new helpers:
    * `_normal_ppf` (Acklam's algorithm, accurate to ~1e-9, no scipy dependency)
    * `recover_se_from_p(effect, p_value, p_floor=0.001)` — back out SE from a two-sided
      p-value via normal-approx with a p-floor clamp so upstream-reported `p=0` produces
      a conservative finite SE rather than collapsing the CI to a point.
    * `compose_funnel_ci(m1uv_pct, m1uv_se, clicks_pct, clicks_se, alpha=0.10)` —
      delta-method 90% CI on the product (1+m1uv)(1+clicks)−1 = Net Margin/Visitor %Δ.
      Independence-of-effects assumed; documented as a small approximation.
  - scripts/lib/render.py:_compose_final_verdict — rewritten as a strict 4-stage decision
    hierarchy: (1) hard guardrails (AB CVR ≤ −1% at p<0.05 → KILL; SEO impressions DiD
    ≤ −10% at full signal → KILL) — these are vetos independent of the composed metric;
    (2) SRM persistent-fail short-circuit to label-matrix (composed CI not trusted when
    the bcookie split is biased); (3) composed funnel 90% CI rule — lower > +0.5%
    (Minimum Worth-Shipping Effect) → DEPLOY, upper < −0.5% → KILL, straddles → HOLD;
    (4) label-matrix fallback when SEs aren't recoverable. The 5 tunables — MWSE, CI
    alpha, guardrail thresholds — are module constants for easy retuning.
  - scripts/lib/render.py:build_payload + render_summary — emit and read a unified
    `signals` dict (ab_verdict, m1uv_pct/se/t/n, cvr_pct/p, seo_status/verdict/
    signal_strength, did_imp_pct, did_clicks_pct/p, srm_verdict). Payload now carries
    `composed_basis` ('ci' | 'guardrail' | 'matrix'), `composed_net_pct`,
    `composed_se_pct`, `composed_lower_pct`, `composed_upper_pct`, `composed_alpha`,
    `composed_mwse_pct` so HTML and Markdown share one source of truth.
  - scripts/lib/render_app.js — new `ciTile(D)` replaces the legacy "Total estimated
    margin impact" tile. Headline tile now reads `Net margin / visitor: X.XX% · 90% CI
    [lower, upper]` with a `CI / guardrail / matrix` basis chip in the label so the
    reader knows the verdict's rigor at a glance. The Final row in the takeaway block
    gains the same basis chip next to the verdict pill.
  - scripts/lib/render.py CSS — `.exec-tile-basis` (basis chip on the headline tile)
    and `.exec-final-basis` (basis chip on the Final row).
  - skills/render-combined-report/SKILL.md — full rewrite of the "Composed Final
    verdict" section: the composed metric definition, SE-recovery priority order,
    4-stage decision hierarchy, tunable defaults table, worked example reproducing
    the FAQ reviews case (90% CI [−5.69%, +1.13%] → CI rule says HOLD; guardrail trip
    forces KILL), and the three honest caveats (independence assumption, p-clamp
    conservatism, organic-traffic scope).
  - render_summary methodology section — replaced the label-matrix one-liner with the
    new CI+guardrails rule statement.
  - tests/test_stats.py — 16 new tests covering `_normal_ppf` against known quantiles,
    `recover_se_from_p` (simple case, p-clamp, missing-input handling), `compose_funnel_ci`
    (none-returns, point-only no-SE, FAQ reviews worked example, clear-DEPLOY and
    clear-KILL cases), and `_compose_final_verdict` decision hierarchy (each guardrail,
    each CI branch, matrix fallback, FAQ reviews end-to-end). Pytest: 49 passed.

0.6.6 — Composed AB+SEO Final verdict (DEPLOY / HOLD / KILL) + renderer SRM-backfill list-shape fix:
  - scripts/lib/render.py — new `_compose_final_verdict()` helper composes a single
    DEPLOY / HOLD / KILL recommendation from the AB verdict (`raw.filtered.verdict`) and
    the upstream SEO verdict, plus a 1-2 sentence rationale. Categorizes SEO into
    WIN (POSITIVE/SHIP) / HARM (PAUSE/NEGATIVE/REDESIGN) / UNCLEAR (INCONCLUSIVE/EXTEND/
    EARLY/MIXED) / MISSING (no SEO data). Two invariants — AB KILL is dominant; SEO HARM
    is dominant. Everything else is HOLD. Full rule table lives in
    `skills/render-combined-report/SKILL.md`.
  - scripts/lib/render.py — `build_payload` now emits `composed_verdict`,
    `composed_rationale`, `composed_cls` so the JS-rendered exec card and the
    `summary.md` scoreboard read from the same source of truth.
  - scripts/lib/render.py:render_summary — scoreboard line now leads with the Final
    verdict (`- Final: **KILL** — AB ruled KILL ...`) above AB/SEO lines, and the
    Methodology section documents the composition rule.
  - scripts/lib/render_app.js — exec card takeaway block now renders a Final row at
    the top (pill + rationale, color-coded green/amber/red); exec card left-border now
    reflects the Final verdict (not AB-only); the top-of-summary tally counts
    `N deploy · N hold · N kill` instead of the AB-only `ship/kill/other`.
  - scripts/lib/render.py CSS — added `.exec-takeaway-row.exec-final.final-{deploy,hold,kill}`
    styles for the new pill + rationale row.
  - skills/render-combined-report/SKILL.md — documented the composition rule (inputs,
    SEO categorization, 4×4 verdict matrix, the two invariants, and the rationale-text
    extension point for new combos).
  - scripts/lib/render.py:_backfill_remediated_srm — accepts both list-shaped variants
    (the documented SKILL.md schema: `[{name, role, uv, bcookies, ...}]`) AND legacy
    dict-shaped variants (`{ctrl: {...}, treat: {...}}`). Falls through `total_uv →
    bcookies → uv → n` for the SRM denominator. Previously crashed with
    `AttributeError: 'list' object has no attribute 'get'` on the documented shape,
    blocking render for runs where the AB subagent followed the schema literally.

0.6.5 — SEO release_date sourced from test_definitions.evaluate_seo_since + FAQ reviews mid-experiment variant rename:
  - scripts/lib/bq_queries.sql, fixtures/test_definitions.schema.json, skills/list-experiments/SKILL.md
    — `list_experiments` now projects `evaluate_seo_since` (from the new test_definitions column of
    the same name) alongside `start_date`/`end_date`. The SQL falls back to `start_date` when the
    column is blank/null so legacy rows keep working. `seo_eligible` in list-experiments is now
    gated on `evaluate_seo_since <= today-14` (widened from the previous 7-day cushion on
    `start_date`), so the upstream SEO pipeline has enough post-period days for a meaningful DiD
    before the orchestrator opens a run.
  - skills/orchestrator-workflow/SKILL.md, skills/run-seo-evaluation/SKILL.md — the SEO subagent
    now receives `release_date = queue.evaluate_seo_since` (instead of `queue.start_date`) and
    forwards it to `scripts/run_seo_pipeline.py --release-date`. The AB window can begin earlier
    than the SEO release (e.g. FAQ reviews ran AB from 2026-04-06 but the SEO test variant only
    went live 2026-05-01).
  - scripts/lib/bq_queries.sql — added a per-experiment variant-rename CASE to every query that
    reads `variantname` (9 queries: ab_filtered_raw/remediated, ab_overall_raw/remediated,
    category_daily base CTE, category_daily_by_l2, overall_per_cat_daily, deal_top_winners_losers
    per_deal CTE, deal_by_category). For
    `experimentname IN ('xp-mbnxt-32228-web-faq-reviews-section', 'FAQ reviews', 'FAQ reviews - 8k')`,
    the pre-rename `true`/`false` variant names are mapped onto the post-rename
    `control`/`treatment` names so both halves aggregate as one experiment. The IN list covers
    both the GrowthBook experiment id (used in `experiments_jupiter_hist`) and the alternate_name
    values (used in `review_experiments_hist`/`review_experiments_deal`). The CASE is a no-op for
    every other experiment. Verified on 2026-05-13→2026-05-17 jupiter_hist window and the full
    FAQ reviews deal-table cohort: SQL now emits exactly 2 variants (`control`, `treatment`) with
    summed UV/UDV/M1 across the old+new naming halves.
  - skills/run-ab-evaluation/SKILL.md — added a "Per-experiment overrides" subsection under
    "Variant naming convention". Documents the FAQ reviews rename, tells subagents to pass
    `@ctrl_name='control'` (the post-rename name) to `deal_top_winners_losers`, and reminds future
    maintainers that any new override must be applied in the SQL CASE statements as well as the
    skill table.

0.6.4 — Exec-summary UI polish + GrowthBook variant-naming guard:
  - scripts/lib/render_app.js, scripts/lib/render.py — exec-card overhaul: dual AB+SEO verdict groups
    in the per-experiment header with PRELIMINARY/FINAL labels for both; SEO post-days and power
    meta inline (e.g. "8/28 post-days · power 100%"); scope subtitle collapsed from two lines to
    one row; DATA: ORIGINAL / REMEDIATED / SRM FAIL badge on both exec card AB group and AB tab
    header; .badge-tip CSS (dotted underline + ⓘ glyph) so users see the tooltip affordance.
  - scripts/lib/render_app.js — fixed firstSentence regex truncating at decimals (was
    `/^[^.!?]+[.!?]/`, now `/[.!?](?=\s+\S|\s*$)/g` with min-length + lowercase-next-word guards).
  - scripts/lib/render.py — auto-detects `passthrough/<alternate_name>.docx` files so c3
    narratives surface even when the AB subagent did not write `passthrough_docx` into JSON.
  - skills/run-ab-evaluation/SKILL.md — added a hard contract block on GrowthBook true/false
    variants: ctrl MUST be `"true"`, with a mandatory one-line sanity check in subagent output
    (recurring inversion bug, last observed on FAQ reviews 2026-05-12 — sign-flipped −1.78% vs the
    canonical +1.78%).
  - README.md — generalized for publication (removed internal-only references).

0.6.3 — Robustness fixes from /evaluate-reviews-experiments run (2026-05-11 night):
  - skills/resolve-deal-urls/SKILL.md — mandates `--max_rows=500000` (was unset → bq CLI default
    silently truncated). Added truncation-detection rule: after writing the JSON, count entries vs
    `SELECT COUNT(DISTINCT deal_uuid)` over the same `test_deals` filter; fail loudly if the resolved
    count equals (or is suspiciously close to) the `--max_rows` value. Observed regression:
    "AI Summaries v4 - Single format 30k" (30,520 deals in test_deals) was clipped to 10,000 deals
    by an orchestrator-side `--max_rows=10000`, propagating downstream as 5,933-of-30,520 SEO
    ingestion (62% missing). SEO verdict at the truncated subset read SHIP (DiD Impressions +25.87%,
    Clicks +6.63%) but flipped to INCONCLUSIVE with the full set (DiD Impressions −12.62%, Clicks
    +0.82%) — the 10k subset was biased toward higher-impression deals.
  - scripts/lib/render.py:stats_for_daily() — now derives per-day ratios from raw totals
    (`m1uv = m1/uv`, `cvr = orders/udv`) when explicit `<metric>_ctrl`/`<metric>_treat` keys are
    absent. Removed three strict pre-check gates (`"m1uv_ctrl" in daily[0]`) at lines 921, 945
    (build_payload) and 1344 (write_summary_md). Subagent JSONs that emit only raw totals (the
    FAQ reviews AB shape) now produce populated exec tiles instead of "n/a". Smoke-tested 3 cases:
    totals-only → derives correctly; totals+explicit-ratios → identical result, prefers explicit;
    ratios-only-no-totals → returns None (no aggregate base — correct).
  - scripts/lib/render.py:write_summary_md() — now sources `raw.overall.daily` (AB-Overall,
    population-wide via experiments_jupiter_hist) explicitly, with fallback to filtered only when
    Overall is absent. Stamps `scope: AB-Overall` on every summary line. Was silently falling back
    to `raw.filtered.daily` (deal-scoped via review_experiments_hist) because the legacy
    `ab.overall_daily` key was unset — the summary headline therefore showed deal-filtered numbers
    while the HTML exec card showed population-wide, an inconsistency that confused cross-run
    comparisons. The flip is dramatic on FAQ reviews: −9.15% (deal-filtered) → +1.78% (population
    overall) — sign-flipped because deal-scoped is a small high-variance subset.
  - skills/run-ab-evaluation/SKILL.md step 2 — added "Mandatory daily-row shape" clause requiring
    `m1uv_ctrl/treat` and `cvr_ctrl/treat` per daily row (formula: `m1uv_<side> = m1_<side> /
    uv_<side>`; `cvr_<side> = orders_<side> / udv_<side>`; guard zero-denominator days with None).
    Belt-and-suspenders since the renderer now derives anyway, but enforces the contract at source
    so future subagent regressions are caught upstream. Cites the FAQ-reviews regression.
  - Validated cached JSON against fresh `experiments_jupiter_hist` query for FAQ reviews (closed
    2026-04-25, 35 days past start): byte-identical SUMs → no retention drift on jupiter_hist
    (~120-day retention). `review_experiments_hist` has shorter (~30-day) retention so the
    Filtered view may bite for older closed experiments — yet another reason summary.md should
    source Overall.

0.6.2 — Filtered table swap to _hist + locked date-window contract:
  - bq_queries.sql — swapped `review_experiments` → `review_experiments_hist` in 3 FROM clauses
    (`ab_filtered_raw`, `ab_filtered_remediated`, `category_daily`) + the `ab_filtered_raw` description
    comment. `_hist` retains longer history (919K rows on 2026-05-11); identical schema (UV, UDV,
    margin_1_vfm, ue_orders, gross_bookings, distinct_bcookie_count, active_visitor_flag, region,
    groupon_version, log_status all present). The non-hist table has ~30-day rolling retention which
    silently truncated FAQ reviews' first 4-5 days. `_deal` references kept on `review_experiments_deal`
    (separate table). `fixtures/review_experiments.schema.json` + `tests/test_schema_drift.py` not
    renamed in this version — flagged as open follow-up.
  - skills/run-ab-evaluation/SKILL.md — updated 4 prose mentions of `review_experiments` →
    `review_experiments_hist` in the ownership table, step 6, step 6a, and failure modes.
  - skills/run-deal-charts/SKILL.md — updated the ctrl_name lookup SQL example to reference
    `review_experiments_hist`.
  - skills/run-ab-evaluation/SKILL.md — added "Date window is LOCKED — no trimming, no ramp-up
    dropping" subsection under Tool contract. Hard rules: subagents MUST pass `@start_date`/`@end_date`
    verbatim to every BQ query; MUST emit daily arrays covering every calendar date in the window
    (zero-row days emitted as-is so SRM and paired t-test run on the full window); MUST NOT apply
    ramp-up offsets, warm-up trims, or early/late exclusion. Applies to raw, remediated,
    per_category, per_category_overall.
  - skills/run-deal-charts/SKILL.md — same locked-window clause added under Tool contract.
  - skills/orchestrator-workflow/SKILL.md — same locked-window contract added under Tool contract so
    it is visible at the orchestrator level.
  - Reason: user observed FAQ reviews headline %Δ shifting across reruns despite the experiment being
    closed. Cross-run SUM diff (overall m1_ctrl=17,397.93 byte-identical May 6 ↔ May 11; filtered
    differed because the non-hist table had purged Apr 6-9) proved the source was frozen for the dates
    that existed in both runs. The `_hist` swap fixes the retention truncation; the locked-window
    contract prevents future Opus-subagent-side trimming heuristics.
  - Local-only; not pushed to GitHub.

0.6.1 — Fix remediation column on experiments_jupiter_hist:
  - bq_queries.sql `ab_overall_remediated` — changed remediation filter from `search_visitor_flag = 'Y'`
    (introduced incorrectly in 0.6.0) to `active_visitor_flag = 'Y'`. The hist table has both columns;
    `search_visitor_flag` is a strict subset (search-acquired traffic only), `active_visitor_flag` is
    the actual equivalent of the legacy `active_visitor.is_active_visitor = 1` join.
  - Validated 2026-05-11 against FAQ reviews: with `active_visitor_flag='Y'` ctrl/treat M1+VFM/UV =
    $2.60 / $2.64 (+1.78%), matching the legacy join's $2.59 / $2.52 magnitude within +-2c. With
    `search_visitor_flag='Y'` the same query produced $4.06 / $4.63 (+14%), which is search-acquired
    traffic only and not equivalent to active-visitor remediation.
  - skills/run-ab-evaluation/SKILL.md — column reference + warning added.
  - Local-only; not pushed to GitHub.

0.6.0 — AB Overall canonical-table swap:
  - bq_queries.sql `ab_overall_raw` — swapped `bcookie_with_experiment_from_jupiter.experiment`
    + LEFT JOIN `combined_data` for `bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
    (pre-aggregated; matches ab-experiments plugin canon). Direct SUM of UV / UDV / margin_1_vfm /
    ue_orders / gross_bookings / distinct_bcookie_count from the hist table. No more bcookie-level
    join. Adds `search_visitor_flag` to the projection so the renderer can show "active vs all" if
    needed. Reason: the legacy `experiment` table has a rolling ~30-day window (Apr 10/11 → May 9/10
    observed 2026-05-11), silently truncating any test that closed >30d ago; hist has ~120 days of
    coverage and is the source of truth used by the ab-experiments plugin's own queries.
  - bq_queries.sql `ab_overall_remediated` — swapped from `experiment ∩ active_visitor (is_active_visitor=1)
    + combined_data` chain to `experiments_jupiter_hist WHERE search_visitor_flag = 'Y'`. Data owner
    confirmed `search_visitor_flag` on the hist table is the same column that backed the legacy
    `active_visitor.is_active_visitor=1` join. SRM remediation now runs on the same pre-aggregated
    source. (In practice the hist table's raw SRM usually already passes because non-search/non-active
    rows are absent from the rollup; remediation is a fallback, not a routine path.)
  - bq_queries.sql `overall_per_cat_daily` — same swap. PerCategory Overall (for `use_deal_category_split=TRUE`
    experiments) now reads from hist with a single STRUCT-array UNNEST projection of (sub_experiment_name → category).
  - skills/run-ab-evaluation/SKILL.md — updated "What this skill does itself" table + step 6a to
    name `experiments_jupiter_hist` as the AB-Overall source. Remediation row now says
    `search_visitor_flag='Y'` instead of `active_visitor` join.
  - Behavioral consequence: AB-Overall verdicts and headlines may shift on existing tests when re-run
    (FAQ reviews: M1+VFM/UV went from -2.87% remediated on Apr 11-25 window to +1.78% raw on Apr 6-25
    window; sign + magnitude changed because the hist grain doesn't have bcookie-level imbalance and
    captures the full registered window). Re-evaluate any test whose verdict was load-bearing under v0.5.x.
  - Local-only; not pushed to GitHub.

0.5.2 — Determinism + model consistency:
  - scripts/run_seo_pipeline.py — new parametric Python entrypoint that drives the upstream
    seo-impact-plugin (classify → fetch → enrich → analyze → generate) by importing the
    modules directly. Skips upstream resolve() / mds-insights since urls_<alt>.json is
    pre-enriched by resolve-deal-urls. Same inputs now produce byte-identical seo_<alt>.json
    across runs.
  - skills/run-seo-evaluation/SKILL.md — rewritten as a thin shim that shells out to
    run_seo_pipeline.py. No more per-stage prompt dispatch (seo-guardrails / page-classifier
    / gsc-fetcher / impact-analyzer / report-generator dispatch chain removed).
  - commands/evaluate-reviews-experiments.md + skills/orchestrator-workflow/SKILL.md —
    subagent model flipped sonnet → opus for all three subagents (run-ab-evaluation,
    run-seo-evaluation, run-deal-charts). Consistency over cost: verdict synthesis, SRM
    remediation, and narrative interpretation now run on the same model as the orchestrator.
  - Output schema unchanged — renderer compatibility preserved (still emits
    upstream_html_b64 plain; render.py gzip-wraps it before embedding).

0.5.1 — local-only polish (see project memory for full notes):
  - render.py + render_app.js — gzip-compress + DecompressionStream-decode embedded SEO HTML
    (54.7 MB → 2.2 MB combined report). lineChart dailyLabel fallback for AI_Summaries.
    Exec card restructure: Total estimated margin impact tile first; Confidence/Why/Action
    rows replace single-sentence Takeaway. M1 → M1+VFM rename in 18 user-visible spots.
    Two-line scope/scale subtitle. "FINAL — can be closed" → "FINAL"; FINAL (could extend)
    → "FINAL — could extend". SHOW_OVERVIEW_TAB feature flag.

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
