-- name: list_experiments
-- description: Read test_definitions, optionally filter to evaluate_automatically=TRUE.
--   `evaluate_seo_since` is the SEO release_date for the SEO subagent (typically equals
--   start_date, but can be later when only a partial cohort is in scope for SEO). Falls
--   back to start_date when blank/null so legacy rows keep working.
-- params: @auto_only (BOOL, default FALSE), @explicit_name (STRING, default NULL)
SELECT
  alternate_name,
  experiment_name,
  DATE(start_date) AS start_date,
  DATE(COALESCE(NULLIF(end_date, ''), CAST(DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY) AS STRING))) AS end_date,
  DATE(COALESCE(NULLIF(evaluate_seo_since, ''), start_date)) AS evaluate_seo_since,
  UPPER(use_deal_category_split) = 'TRUE' AS use_deal_category_split,
  UPPER(use_misc_split) = 'TRUE' AS use_misc_split,
  UPPER(evaluate_automatically) = 'TRUE' AS evaluate_automatically,
  end_date IS NULL OR end_date = '' AS is_in_flight
FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_definitions`
WHERE (NULLIF(@explicit_name, '') IS NULL OR alternate_name = @explicit_name)
  AND (NOT @auto_only OR UPPER(evaluate_automatically) = 'TRUE')
ORDER BY start_date DESC;

-- name: ab_filtered_raw
-- description: AB-Filtered view from review_experiments_hist (precise OR per spec §4).
--   Variant normalization (FAQ family): the FAQ experiments
--   (`xp-mbnxt-32228-web-faq-reviews-section` and older `xp-mbnxt-29568-web-faq-section`) were
--   renamed mid-experiment from true/false (original) to control/treatment (post-2026-05-14).
--   The nested CASE handles BOTH halves:
--     (1) maps old true/false rows to control/treatment (true→control, false→treatment) —
--         unchanged from the original mapping, which was semantically correct.
--     (2) swaps the post-rename control/treatment rows because the flag-layer assignment is
--         INVERTED for FAQ experiments — what's labeled 'control' in the source data is
--         actually the treatment side, and vice versa.
--   The IN list matches both GrowthBook experiment ids (used in `experiments_jupiter_hist`) and
--   `alternate_name` values used in `review_experiments_hist` / `review_experiments_deal`
--   ('FAQ reviews', 'FAQ reviews - 8k', 'FAQ reviews - 8k - before change'). ELSE branch is a
--   no-op for all other experiments. See CHANGELOG 0.6.5 + 0.8.4.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date, experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country, region, clientPlatform, groupon_version,
  log_status, active_visitor_flag,
  SUM(uv) AS uv,
  SUM(udv) AS udv,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(ue_orders) AS ue_orders,
  SUM(gross_bookings) AS gross_bookings
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_hist`
WHERE event_date BETWEEN @start_date AND @end_date
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9;

-- name: ab_filtered_remediated
-- description: Same as ab_filtered_raw but filtered to active_visitor_flag = 'Y' (SRM remediation).
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date, experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country, region, clientPlatform, groupon_version,
  log_status,
  SUM(uv) AS uv,
  SUM(udv) AS udv,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(ue_orders) AS ue_orders,
  SUM(gross_bookings) AS gross_bookings
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_hist`
WHERE event_date BETWEEN @start_date AND @end_date
  AND active_visitor_flag = 'Y'
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8;

-- name: ab_overall_raw
-- description: AB-Overall (population-wide) view from experiments_jupiter_hist (pre-aggregated). Matches the canonical ab-experiments plugin table. Uses test_definitions dates (NOT GrowthBook dates) for consistency with AB-Filtered. Date window strictly clipped to test_definitions.end_date even though hist covers ~120d.
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @experiment_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date,
  experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country,
  clientPlatform,
  log_status,
  search_visitor_flag,
  SUM(UV) AS uv,
  SUM(UDV) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(gross_bookings) AS gross_bookings,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = @experiment_name
  AND event_date BETWEEN @start_date AND @end_date
GROUP BY 1, 2, 3, 4, 5, 6, 7;

-- name: ab_overall_remediated
-- description: AB-Overall SRM remediation via active_visitor_flag='Y' on experiments_jupiter_hist. The hist table's active_visitor_flag is the same filter as is_active_visitor=1 in the legacy active_visitor join table — validated 2026-05-11 against FAQ reviews (M1/UV magnitudes match within +-2c after accounting for 5-day window expansion). DO NOT confuse with search_visitor_flag, which is a stricter subset (search-acquired traffic only).
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @experiment_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date,
  experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country,
  clientPlatform,
  log_status,
  SUM(UV) AS uv,
  SUM(UDV) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(gross_bookings) AS gross_bookings,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname = @experiment_name
  AND event_date BETWEEN @start_date AND @end_date
  AND active_visitor_flag = 'Y'
GROUP BY 1, 2, 3, 4, 5, 6;

-- name: discover_sub_experiments
-- description: Probe experiments_jupiter_hist for sub-experiment names matching a LIKE pattern in
--   the test window. Used by run-ab-evaluation when `use_deal_category_split=TRUE` and the parent
--   `experiment_name` (from test_definitions) returns 0 rows — e.g. "AI Summaries" is split into
--   per-category sub-experiments like 'xp-mbnxt-31196-ai-review-summary-hbw', '...-ttd', etc.
--   The pattern is supplied by the caller; the run-ab-evaluation skill maintains the
--   parent → pattern map.
-- params: @pattern (STRING), @start_date (DATE), @end_date (DATE)
SELECT DISTINCT experimentname
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE event_date BETWEEN @start_date AND @end_date
  AND LOWER(experimentname) LIKE LOWER(@pattern)
ORDER BY experimentname;

-- name: ab_overall_raw_multi
-- description: AB-Overall view across MULTIPLE sub-experiments (population-wide). Same shape as
--   `ab_overall_raw` but filters via `experimentname IN UNNEST(@experiment_names)` so the
--   orchestrator can sum across category-split sub-experiments (e.g. AI Summaries → 8 ai-review-
--   summary-<cat> rows). Variant rename CASE preserved.
-- params: @experiment_names (ARRAY<STRING>), @start_date (DATE), @end_date (DATE)
SELECT
  event_date,
  experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country,
  clientPlatform,
  log_status,
  search_visitor_flag,
  SUM(UV) AS uv,
  SUM(UDV) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(gross_bookings) AS gross_bookings,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname IN UNNEST(@experiment_names)
  AND event_date BETWEEN @start_date AND @end_date
GROUP BY 1, 2, 3, 4, 5, 6, 7;

-- name: ab_overall_remediated_multi
-- description: AB-Overall SRM remediation across MULTIPLE sub-experiments. Same as
--   `ab_overall_remediated` but filters via `experimentname IN UNNEST(@experiment_names)`.
-- params: @experiment_names (ARRAY<STRING>), @start_date (DATE), @end_date (DATE)
SELECT
  event_date,
  experimentname,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  country,
  clientPlatform,
  log_status,
  SUM(UV) AS uv,
  SUM(UDV) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(gross_bookings) AS gross_bookings,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist`
WHERE experimentname IN UNNEST(@experiment_names)
  AND event_date BETWEEN @start_date AND @end_date
  AND active_visitor_flag = 'Y'
GROUP BY 1, 2, 3, 4, 5, 6;

-- name: resolve_deal_urls
-- description: Resolve test_deals → deal_url + metadata. Replaces MDS/Okta enrichment.
-- params: @alternate_name (STRING)
WITH deals AS (
  SELECT LOWER(TRIM(deal_uuid)) AS deal_uuid
  FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_deals`
  WHERE alternate_name = @alternate_name
),
url_meta AS (
  SELECT
    deal_uuid,
    'https://www.groupon.com/deals/' || MAX(deal_permalink) AS deal_url,
    '/deals/' || MAX(deal_permalink) AS landing_page,
    MAX(web_category_level_1) AS web_category_level_1,
    MAX(web_category_level_2) AS web_category_level_2
  FROM `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option`
  GROUP BY 1
),
deal_meta AS (
  SELECT
    deal_uuid,
    MAX(merchant_uuid) AS merchant_uuid,
    MAX(booking_platform) AS booking_platform
  FROM `kbc-grpn-40-0cd2.in_c_shr_unagi.dim_deal`
  GROUP BY 1
)
SELECT
  d.deal_uuid,
  u.deal_url, u.landing_page, u.web_category_level_1, u.web_category_level_2,
  m.merchant_uuid, m.booking_platform
FROM deals AS d
LEFT JOIN url_meta AS u USING (deal_uuid)
LEFT JOIN deal_meta AS m USING (deal_uuid)
WHERE u.deal_url IS NOT NULL;

-- name: seo_did_l2
-- description: Aggregated impressions/clicks per group×L2×period for DiD calculation.
--   Only used when computing DiD outside the seo-impact-analyzer (e.g. when control set
--   was added late). Prefer letting seo-impact-analyzer compute DiD natively.
-- params: @alternate_name (STRING), @pre_start (DATE), @pre_end (DATE), @post_start (DATE), @post_end (DATE)
WITH variant_urls AS (
  SELECT DISTINCT 'https://www.groupon.com/deals/' || deal_permalink AS full_url
  FROM `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option`
  WHERE LOWER(TRIM(deal_uuid)) IN (
    SELECT LOWER(TRIM(deal_uuid))
    FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_deals`
    WHERE alternate_name = @alternate_name
  )
  AND deal_permalink IS NOT NULL
),
variant_l2 AS (
  SELECT DISTINCT MAX(web_category_level_2) AS l2
  FROM `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option`
  WHERE LOWER(TRIM(deal_uuid)) IN (
    SELECT LOWER(TRIM(deal_uuid))
    FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_deals`
    WHERE alternate_name = @alternate_name
  )
  GROUP BY deal_uuid
),
target_l2 AS (
  SELECT DISTINCT l2 FROM variant_l2 WHERE l2 IS NOT NULL
),
seo AS (
  SELECT
    full_url, category_level_2,
    CASE
      WHEN date BETWEEN @pre_start AND @pre_end THEN 'pre'
      WHEN date BETWEEN @post_start AND @post_end THEN 'post'
    END AS period,
    impressions, clicks, sum_position
  FROM `prj-grp-dataview-prod-1ff9.marketing.seo_datamart`
  WHERE date BETWEEN @pre_start AND @post_end
    AND root_domain = 'groupon.com'
    AND coupon_core_flag = 'core'
    AND page_type = 'deals'
    AND category_level_2 IN (SELECT l2 FROM target_l2)
),
labelled AS (
  SELECT
    s.full_url, s.category_level_2 AS l2, s.period,
    IF(v.full_url IS NULL, 'control', 'variant') AS grp,
    s.impressions, s.clicks, s.sum_position
  FROM seo s
  LEFT JOIN variant_urls v USING (full_url)
  WHERE s.period IS NOT NULL
)
SELECT
  grp, l2, period,
  COUNT(DISTINCT full_url) AS url_count,
  SUM(impressions) AS impressions,
  SUM(clicks) AS clicks,
  SAFE_DIVIDE(SUM(sum_position), NULLIF(SUM(impressions),0)) AS avg_position
FROM labelled
GROUP BY 1, 2, 3
ORDER BY 2, 1, 3;

-- name: category_daily
-- description: Daily aggregated stats per deal-category × variant for AB-Filtered per-cat trends.
--   Same xp-mbnxt-32228 variant rename applied in the base CTE — see ab_filtered_raw for context.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
WITH base AS (
  SELECT
    event_date, experimentname,
    CASE
      WHEN experimentname IN (
        'xp-mbnxt-32228-web-faq-reviews-section',
        'xp-mbnxt-29568-web-faq-section',
        'FAQ reviews',
        'FAQ reviews - 8k',
        'FAQ reviews - 8k - before change'
      ) THEN
        CASE variantname
          WHEN 'false'     THEN 'treatment'
          WHEN 'true'      THEN 'control'
          WHEN 'control'   THEN 'treatment'
          WHEN 'treatment' THEN 'control'
          ELSE variantname
        END
      ELSE variantname
    END AS variantname,
    SUM(uv) AS uv, SUM(udv) AS udv, SUM(ue_orders) AS ue_orders, SUM(margin_1_vfm) AS margin_1_vfm
  FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_hist`
  WHERE event_date BETWEEN @start_date AND @end_date
    AND (
      experimentname = @alternate_name
      OR experimentname LIKE CONCAT('% - ', @alternate_name)
      OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
    )
  GROUP BY 1, 2, 3
)
SELECT
  event_date,
  -- Convention: derive category from the experimentname prefix slug (xp-MBNXT-XXXXX-ai-review-summary-<cat-slug>).
  CASE
    WHEN LOWER(experimentname) LIKE '%-hbw -%'              THEN 'HBW'
    WHEN LOWER(experimentname) LIKE '%-ttd -%'              THEN 'TTD'
    WHEN LOWER(experimentname) LIKE '%-fd -%'               THEN 'Food & Drink'
    WHEN LOWER(experimentname) LIKE '%-personalservices -%' THEN 'Personal Services'
    WHEN LOWER(experimentname) LIKE '%-healthfitness -%'    THEN 'Health & Fitness'
    WHEN LOWER(experimentname) LIKE '%-automotive -%'       THEN 'Automotive'
    WHEN LOWER(experimentname) LIKE '%-retail -%'           THEN 'Retail'
    WHEN LOWER(experimentname) LIKE '%-homeservices -%'     THEN 'Home Services'
    ELSE 'Unknown'
  END AS category,
  variantname,
  SUM(uv) AS uv, SUM(udv) AS udv, SUM(ue_orders) AS ue_orders, SUM(margin_1_vfm) AS margin_1_vfm
FROM base
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- name: category_daily_by_l2
-- description: Daily AB-Filtered per-category trends keyed by deal-level web_category_level_2,
--   used for experiments WITHOUT explicit per-cat splits (use_deal_category_split=FALSE). Sources
--   `review_experiments_deal` (deal-scoped); session-level `uv` is not available here, so the
--   denominator for the M1 ratio is `udv` (unique deal-displayers). Caller MUST stamp
--   `per_category[cat].denominator='udv'` so the renderer labels columns "M1/UDV" instead of "M1/UV".
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date,
  web_category_level_2 AS category,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  SUM(udv) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS margin_1_vfm
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_deal`
WHERE event_date BETWEEN @start_date AND @end_date
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
  AND web_category_level_2 IS NOT NULL
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- name: overall_per_cat_daily
-- description: AB-Overall (population-wide) per-category daily stats from experiments_jupiter_hist.
--   Each category split is its own GrowthBook experiment ('xp-mbnxt-XXXXX-ai-review-summary-<slug>'),
--   so we filter the pre-aggregated hist table by sub-experiment name. Caller passes a STRUCT array
--   of (name, cat) as @sub_experiments to project category labels.
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @sub_experiments (ARRAY<STRUCT<name STRING, cat STRING>>), @start_date (DATE), @end_date (DATE)
SELECT
  exps.cat AS category,
  h.event_date,
  CASE
    WHEN h.experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE h.variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE h.variantname
      END
    ELSE h.variantname
  END AS variantname,
  SUM(h.distinct_bcookie_count) AS bcookies,
  SUM(h.UV) AS uv,
  SUM(h.UDV) AS udv,
  SUM(h.ue_orders) AS orders,
  SUM(h.margin_1_vfm) AS m1
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiments_jupiter_hist` AS h
JOIN UNNEST(@sub_experiments) AS exps ON exps.name = h.experimentname
WHERE h.event_date BETWEEN @start_date AND @end_date
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- name: deal_top_winners_losers
-- description: Top 10 winners + losers by margin_1_vfm uplift (treatment vs control) per deal.
--   Caller must pass @ctrl_name matching the actual control variant in this experiment. The
--   canonical convention is "control" (when present) or "true" (when variants are true/false);
--   see run-ab-evaluation/SKILL.md "Variant naming convention".
--   Same xp-mbnxt-32228 variant rename applied inside per_deal — see ab_filtered_raw for context.
--   For this experiment, callers MUST pass @ctrl_name='control' (the post-rename name), since
--   the CASE has already mapped 'true'→'control' before per_deal aggregates.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE), @ctrl_name (STRING)
WITH per_deal AS (
  SELECT
    deal_uuid, deal_url, deal_category,
    CASE
      WHEN experimentname IN (
        'xp-mbnxt-32228-web-faq-reviews-section',
        'xp-mbnxt-29568-web-faq-section',
        'FAQ reviews',
        'FAQ reviews - 8k',
        'FAQ reviews - 8k - before change'
      ) THEN
        CASE variantname
          WHEN 'false'     THEN 'treatment'
          WHEN 'true'      THEN 'control'
          WHEN 'control'   THEN 'treatment'
          WHEN 'treatment' THEN 'control'
          ELSE variantname
        END
      ELSE variantname
    END AS variantname,
    SUM(margin_1_vfm) AS m1
  FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_deal`
  WHERE event_date BETWEEN @start_date AND @end_date
    AND (
      experimentname = @alternate_name
      OR experimentname LIKE CONCAT('% - ', @alternate_name)
      OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
    )
  GROUP BY 1, 2, 3, 4
),
pivoted AS (
  SELECT
    deal_uuid, deal_url, deal_category,
    SUM(IF(variantname = @ctrl_name, m1, 0)) AS m1_ctrl,
    SUM(IF(variantname != @ctrl_name, m1, 0)) AS m1_treat
  FROM per_deal
  GROUP BY 1, 2, 3
)
SELECT *, (m1_treat - m1_ctrl) AS m1_delta
FROM pivoted
ORDER BY ABS(m1_treat - m1_ctrl) DESC
LIMIT 20;

-- name: deal_by_category
-- description: Aggregated CVR / M1 deltas by web_category_level_2.
--   Same xp-mbnxt-32228 variant rename applied — see ab_filtered_raw for context.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  web_category_level_2 AS category,
  CASE
    WHEN experimentname IN (
      'xp-mbnxt-32228-web-faq-reviews-section',
      'xp-mbnxt-29568-web-faq-section',
      'FAQ reviews',
      'FAQ reviews - 8k',
      'FAQ reviews - 8k - before change'
    ) THEN
      CASE variantname
        WHEN 'false'     THEN 'treatment'
        WHEN 'true'      THEN 'control'
        WHEN 'control'   THEN 'treatment'
        WHEN 'treatment' THEN 'control'
        ELSE variantname
      END
    ELSE variantname
  END AS variantname,
  SUM(udv) AS udv,
  SUM(ue_orders) AS ue_orders,
  SUM(margin_1_vfm) AS m1,
  SAFE_DIVIDE(SUM(ue_orders), SUM(udv)) AS cvr
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_deal`
WHERE event_date BETWEEN @start_date AND @end_date
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2;

