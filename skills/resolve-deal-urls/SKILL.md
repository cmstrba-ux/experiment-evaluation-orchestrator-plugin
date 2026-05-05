---
name: resolve-deal-urls
description: Resolve test_deals deal_uuids → enriched URL list (deal_url, landing_page, category, merchant_uuid, booking_platform). Replaces MDS/Okta enrichment. Invoked by orchestrator-workflow before SEO/deal-charts subagents.
---

# resolve-deal-urls

## Inputs
- `alternate_name`: required.

## Steps

1. Run query `resolve_deal_urls` from `scripts/lib/bq_queries.sql` with parameter `@alternate_name`.
   Note: the underlying SQL filters `WHERE alternate_name = @alternate_name` against the `test_deals` table.
2. For every URL returned, assert `assert_no_mds(url)` from `scripts.lib.tool_contract` — refuse to forward MDS URLs.
3. Emit JSON: `[{"deal_uuid":..., "deal_url":..., "landing_page":..., "web_category_level_1":..., "web_category_level_2":..., "merchant_uuid":..., "booking_platform":...}, ...]`.

## Reporting

- If 0 rows returned → emit `{"status":"no_deals", "alternate_name": ...}` and let caller decide.
- If <50% of `test_deals` rows resolve → log warning with the count delta.

## Tool contract

- `bq` CLI only. URLs validated through `assert_no_mds` (no `mds.groupondev.com` allowed in output).
