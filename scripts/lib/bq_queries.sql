-- name: list_experiments
-- description: Read test_definitions, optionally filter to evaluate_automatically=TRUE.
-- params: @auto_only (BOOL, default FALSE), @explicit_name (STRING, default NULL)
SELECT
  alternate_name,
  experiment_name,
  DATE(start_date) AS start_date,
  DATE(COALESCE(NULLIF(end_date, ''), CAST(DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY) AS STRING))) AS end_date,
  UPPER(use_deal_category_split) = 'TRUE' AS use_deal_category_split,
  UPPER(use_misc_split) = 'TRUE' AS use_misc_split,
  UPPER(evaluate_automatically) = 'TRUE' AS evaluate_automatically,
  end_date IS NULL OR end_date = '' AS is_in_flight
FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_definitions`
WHERE (NULLIF(@explicit_name, '') IS NULL OR alternate_name = @explicit_name)
  AND (NOT @auto_only OR UPPER(evaluate_automatically) = 'TRUE')
ORDER BY start_date DESC;

-- name: ab_filtered_raw
-- description: AB-Filtered view from review_experiments (precise OR per spec §4).
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date, experimentname, variantname, country, region, clientPlatform, groupon_version,
  log_status, active_visitor_flag,
  SUM(uv) AS uv,
  SUM(udv) AS udv,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(ue_orders) AS ue_orders,
  SUM(gross_bookings) AS gross_bookings
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments`
WHERE event_date BETWEEN @start_date AND @end_date
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9;

-- name: ab_filtered_remediated
-- description: Same as ab_filtered_raw but filtered to active_visitor_flag = 'Y' (SRM remediation).
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  event_date, experimentname, variantname, country, region, clientPlatform, groupon_version,
  log_status,
  SUM(uv) AS uv,
  SUM(udv) AS udv,
  SUM(distinct_bcookie_count) AS distinct_bcookie_count,
  SUM(margin_1_vfm) AS margin_1_vfm,
  SUM(ue_orders) AS ue_orders,
  SUM(gross_bookings) AS gross_bookings
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments`
WHERE event_date BETWEEN @start_date AND @end_date
  AND active_visitor_flag = 'Y'
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2, 3, 4, 5, 6, 7, 8;

-- name: ab_overall_raw
-- description: AB-Overall (population-wide) view from experiment × combined_data. Uses test_definitions dates (NOT GrowthBook dates) for consistency with AB-Filtered.
-- params: @experiment_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  e.event_date,
  e.experimentname,
  e.variantname,
  COALESCE(cd.country, e.country) AS country,
  e.clientPlatform,
  e.distinct_bcookie_count,
  cd.uv, cd.udv, cd.ue_orders, cd.margin_1_vfm, cd.gross_bookings, cd.log_status
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiment` AS e
LEFT JOIN `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.combined_data` AS cd
  ON cd.event_date = e.event_date AND cd.bcookie = e.bcookie
WHERE e.experimentname = @experiment_name
  AND e.event_date BETWEEN @start_date AND @end_date;

-- name: ab_overall_remediated
-- description: AB-Overall filtered to active_visitor (SRM remediation).
-- params: @experiment_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  e.event_date,
  e.experimentname,
  e.variantname,
  COALESCE(cd.country, e.country) AS country,
  e.clientPlatform,
  e.distinct_bcookie_count,
  cd.uv, cd.udv, cd.ue_orders, cd.margin_1_vfm, cd.gross_bookings, cd.log_status
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiment` AS e
INNER JOIN `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.active_visitor` AS av
  ON av.bcookie = e.bcookie AND av.event_date = e.event_date AND av.is_active_visitor = 1
LEFT JOIN `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.combined_data` AS cd
  ON cd.event_date = e.event_date AND cd.bcookie = e.bcookie
WHERE e.experimentname = @experiment_name
  AND e.event_date BETWEEN @start_date AND @end_date;

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

-- name: resolve_control_urls
-- description: Sample matched control URL set for SEO DiD. URLs that are NOT in test_deals,
--   page_type='deals', root_domain='groupon.com', coupon_core_flag='core', in the same L2
--   categories as the variant set, ranked by pre-period impressions and capped per L2.
-- params: @alternate_name (STRING), @pre_start (DATE), @pre_end (DATE), @per_l2_cap (INT64, default 5000)
WITH variant_l2 AS (
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
variant_urls AS (
  SELECT DISTINCT 'https://www.groupon.com/deals/' || deal_permalink AS full_url
  FROM `kbc-grpn-40-0cd2.in_c_shr_dimension_datamart.deal_option`
  WHERE LOWER(TRIM(deal_uuid)) IN (
    SELECT LOWER(TRIM(deal_uuid))
    FROM `kbc-grpn-40-0cd2.in_c_keboola_ex_google_drive_01kjaefgnqyrk1y6trtznth660.test_deals`
    WHERE alternate_name = @alternate_name
  )
  AND deal_permalink IS NOT NULL
),
candidates AS (
  SELECT
    full_url,
    category_level_2 AS l2,
    SUM(impressions) AS pre_imp,
    ROW_NUMBER() OVER (PARTITION BY category_level_2 ORDER BY SUM(impressions) DESC) AS rn
  FROM `prj-grp-dataview-prod-1ff9.marketing.seo_datamart`
  WHERE date BETWEEN @pre_start AND @pre_end
    AND root_domain = 'groupon.com'
    AND coupon_core_flag = 'core'
    AND page_type = 'deals'
    AND category_level_2 IN (SELECT l2 FROM target_l2)
  GROUP BY full_url, category_level_2
)
SELECT c.full_url AS deal_url, c.l2 AS web_category_level_2, c.pre_imp
FROM candidates c
LEFT JOIN variant_urls v ON v.full_url = c.full_url
WHERE v.full_url IS NULL
  AND c.rn <= IFNULL(@per_l2_cap, 5000);

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
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
WITH base AS (
  SELECT
    event_date, experimentname, variantname,
    SUM(uv) AS uv, SUM(udv) AS udv, SUM(ue_orders) AS ue_orders, SUM(margin_1_vfm) AS margin_1_vfm
  FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments`
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

-- name: overall_per_cat_daily
-- description: AB-Overall (population-wide) per-category daily stats. Each category split is
--   its own GrowthBook experiment ('xp-mbnxt-XXXXX-ai-review-summary-<slug>'), so we query
--   the bcookie experiment+combined_data path once per sub-experiment in a single UNION-style
--   select via a STRUCT array of (name, cat). Caller passes the array as @sub_experiments.
-- params: @sub_experiments (ARRAY<STRUCT<name STRING, cat STRING>>), @start_date (DATE), @end_date (DATE)
SELECT
  exps.cat AS category,
  e.event_date,
  e.variantname,
  SUM(e.distinct_bcookie_count) AS bcookies,
  SUM(cd.uv) AS uv,
  SUM(cd.udv) AS udv,
  SUM(cd.ue_orders) AS orders,
  SUM(cd.margin_1_vfm) AS m1
FROM `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.experiment` AS e
JOIN UNNEST(@sub_experiments) AS exps ON exps.name = e.experimentname
LEFT JOIN `kbc-grpn-40-0cd2.out_c_10_bcookie_with_experiment_from_jupiter.combined_data` AS cd
  ON cd.event_date = e.event_date AND cd.bcookie = e.bcookie
WHERE e.event_date BETWEEN @start_date AND @end_date
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- name: deal_top_winners_losers
-- description: Top 10 winners + losers by margin_1_vfm uplift (treatment vs control) per deal.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
WITH per_deal AS (
  SELECT
    deal_uuid, deal_url, deal_category, variantname,
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
    SUM(IF(variantname = 'control', m1, 0)) AS m1_ctrl,
    SUM(IF(variantname != 'control', m1, 0)) AS m1_treat
  FROM per_deal
  GROUP BY 1, 2, 3
)
SELECT *, (m1_treat - m1_ctrl) AS m1_delta
FROM pivoted
ORDER BY ABS(m1_treat - m1_ctrl) DESC
LIMIT 20;

-- name: deal_by_category
-- description: Aggregated CVR / M1 deltas by web_category_level_2.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  web_category_level_2 AS category,
  variantname,
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

-- name: deal_by_booking_platform
-- description: Aggregations by booking_platform.
-- params: @alternate_name (STRING), @start_date (DATE), @end_date (DATE)
SELECT
  booking_platform,
  variantname,
  COUNT(DISTINCT deal_uuid) AS deal_count,
  SUM(udv) AS udv,
  SUM(margin_1_vfm) AS m1
FROM `kbc-grpn-40-0cd2.out_c_10_review_ab_experiments.review_experiments_deal`
WHERE event_date BETWEEN @start_date AND @end_date
  AND (
    experimentname = @alternate_name
    OR experimentname LIKE CONCAT('% - ', @alternate_name)
    OR experimentname LIKE CONCAT('% - ', @alternate_name, ' - %')
  )
GROUP BY 1, 2;
