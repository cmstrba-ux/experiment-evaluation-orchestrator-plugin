---
name: resolve-deal-urls
description: Resolve test_deals deal_uuids → enriched URL list (deal_url, landing_page, category, merchant_uuid, booking_platform). Replaces MDS/Okta enrichment. Invoked by orchestrator-workflow before SEO/deal-charts subagents.
---

# resolve-deal-urls

## Inputs
- `alternate_name`: required.

## Steps

1. Run query `resolve_deal_urls` from `<plugin-root>/scripts/lib/bq_queries.sql` (the file lives at the orchestrator plugin root, NOT inside this skill's directory — typically `…/local-marketplaces/<marketplace>/plugins/experiment-evaluation-orchestrator/scripts/lib/bq_queries.sql`) with parameter `@alternate_name`.
   Note: the underlying SQL filters `WHERE alternate_name = @alternate_name` against the `test_deals` table.
   **Critical**: invoke `bq` with `--format=prettyjson` and **suppress stderr** (`2>/dev/null` on POSIX, `2>$null` on PowerShell). `bq query` writes `Waiting on bqjob_… RUNNING/DONE` progress lines to stdout if not formatted, which silently corrupts the downstream JSON file (observed in run `2026-05-06-10-26`: 947-byte progress prefix made `urls_FAQ_reviews.json` unparseable, causing the SEO subagent to fall into a manual recovery pipeline with the wrong DiD method).
   **Critical**: pass `--max_rows=500000`. The `bq query` CLI default truncates responses to 100 rows for prettyjson; an unset or low max_rows silently caps the URL list at whatever the CLI default is. Observed regression 2026-05-11 on "AI Summaries v4 - Single format 30k": orchestrator-side `--max_rows=10000` clipped the resolved URL set to 10,000 of 30,520 deals, which propagated downstream — SEO ingested ~5,933 of the 30,520-deal population (62% missing), giving a SHIP verdict that flipped to INCONCLUSIVE after a rerun with the full set. Setting 500k covers any plausible experiment size; the underlying SQL has no LIMIT, only the CLI does.
2. For every URL returned, assert `assert_no_mds(url)` from `scripts.lib.tool_contract` — refuse to forward MDS URLs.
3. Before writing the JSON output file, validate that the captured stdout starts with `[` (after stripping leading whitespace). If it doesn't, search for the first `[{` substring and slice from there — but log a warning, since this means the formatting guard above failed.
4. Emit JSON: `[{"deal_uuid":..., "deal_url":..., "landing_page":..., "web_category_level_1":..., "web_category_level_2":..., "merchant_uuid":..., "booking_platform":...}, ...]`.

## Reporting

- If 0 rows returned → emit `{"status":"no_deals", "alternate_name": ...}` and let caller decide.
- If <50% of `test_deals` rows resolve → log warning with the count delta.
- **Truncation detection**: after writing the JSON, count entries and compare against `SELECT COUNT(DISTINCT LOWER(TRIM(deal_uuid)))` over the same `test_deals` filter. If the resolved count equals (or is suspiciously close to) the `--max_rows` value passed to bq, fail loudly — that's a CLI-side truncation, not a legitimate "no permalink" drop. Re-run with a higher cap rather than passing the truncated set downstream.

## Tool contract

- `bq` CLI only. URLs validated through `assert_no_mds` (no `mds.groupondev.com` allowed in output).
