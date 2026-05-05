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
