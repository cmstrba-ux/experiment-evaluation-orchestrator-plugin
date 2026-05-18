#!/usr/bin/env bash
# Publish combined_report.html from a finished orchestrator run to Groupon IQ
# using the IQ REST API. Pure curl — no MCP server needed, so this works in
# headless CI where the groupon-iq MCP isn't installed.
#
# Strategy mirrors orchestrator-workflow/SKILL.md Step 11:
#   1. Build the canonical title:  Experiment Evaluation Combined Report — YYYY-MM-DD
#      where YYYY-MM-DD is the run_id date prefix (the day the orchestrator ran).
#   2. POST /reports/list (search) to find an existing report with that exact title.
#   3. If found:  POST /reports/reports/<id>/versions  with the new HTML.
#   4. If not:    POST /reports/reports  (create) with title/folder/visibility,
#                 then POST /reports/reports/<id>/versions for v1.
#   5. Print the IQ URL.
#
# Required env (set by the workflow):
#   IQ_API_KEY  — Groupon IQ personal token (g-api-key header)
#   RUN_DIR     — path to the orchestrator run dir, e.g. temp/experiment-evaluation/2026-05-18-14-46
#
# IQ REST endpoints (discovered via the orchestrator's local MCP probing):
#   POST /reports/list                          {search, limit, offset} → paginated list
#   POST /reports/reports                       {title, visibility, folderId, description} → {id,...}
#   POST /reports/reports/<id>/versions         multipart file=@... → {versionId, versionNumber}
#
# Canonical "AI summaries" folder ID — same value the orchestrator skill uses for local runs:
IQ_FOLDER_ID="dbdf853d-55c8-4780-ad03-35441e5ffc10"
IQ_BASE="https://api.enc.groupon.com"

set -euo pipefail

: "${IQ_API_KEY:?IQ_API_KEY is required}"
: "${RUN_DIR:?RUN_DIR is required (path to orchestrator run dir)}"

HTML_PATH="$RUN_DIR/combined_report.html"
if [[ ! -f "$HTML_PATH" ]]; then
  echo "::error::combined_report.html not found at $HTML_PATH"
  exit 1
fi

# Derive run_id from the directory name; first 10 chars are YYYY-MM-DD.
RUN_ID=$(basename "$RUN_DIR")
RUN_DATE="${RUN_ID:0:10}"
if ! [[ "$RUN_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "::error::Could not derive YYYY-MM-DD from run_id=$RUN_ID"
  exit 1
fi

# Em-dash (U+2014) is intentional — matches the canonical title format used
# locally. Encoded as a UTF-8 literal in the JSON body.
TITLE="Experiment Evaluation Combined Report — $RUN_DATE"
echo "Target title: $TITLE"

# Step 2: search existing reports.
echo "==> Searching IQ for existing report with title: $TITLE"
SEARCH_JSON=$(jq -nc --arg s "$TITLE" '{search:$s, limit:50}')
SEARCH_RESULT=$(curl -sS -X POST \
  -H "g-api-key: $IQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$SEARCH_JSON" \
  "$IQ_BASE/reports/list")

# Find an exact-title match (search is a contains match, so we filter).
REPORT_ID=$(echo "$SEARCH_RESULT" | jq -r --arg t "$TITLE" '.data[] | select(.title == $t) | .id' | head -1)

if [[ -n "$REPORT_ID" ]]; then
  echo "==> Found existing report: $REPORT_ID — uploading new version"
else
  echo "==> No existing report found — creating new one"
  CREATE_JSON=$(jq -nc \
    --arg t "$TITLE" \
    --arg f "$IQ_FOLDER_ID" \
    --arg d "Automated orchestrator run (GitHub Actions). Plugin: github.com/cmstrba-ux/experiment-evaluation-orchestrator-plugin" \
    '{title:$t, visibility:"shared_in_groupon", folderId:$f, description:$d}')
  CREATE_RESULT=$(curl -sS -X POST \
    -H "g-api-key: $IQ_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$CREATE_JSON" \
    "$IQ_BASE/reports/reports")
  REPORT_ID=$(echo "$CREATE_RESULT" | jq -r '.id // empty')
  if [[ -z "$REPORT_ID" ]]; then
    echo "::error::Create failed: $CREATE_RESULT"
    exit 1
  fi
  echo "==> Created: $REPORT_ID"
fi

# Step 3: upload version.
echo "==> POST $IQ_BASE/reports/reports/$REPORT_ID/versions  (file=$HTML_PATH)"
UPLOAD_RESULT=$(curl -sS -X POST \
  -H "g-api-key: $IQ_API_KEY" \
  -F "file=@$HTML_PATH;type=text/html" \
  "$IQ_BASE/reports/reports/$REPORT_ID/versions")
VERSION_NO=$(echo "$UPLOAD_RESULT" | jq -r '.versionNumber // empty')
VERSION_ID=$(echo "$UPLOAD_RESULT" | jq -r '.versionId // empty')
if [[ -z "$VERSION_NO" ]]; then
  echo "::error::Upload failed: $UPLOAD_RESULT"
  exit 1
fi

REPORT_URL="https://iq.groupon.com/reports/detail?id=$REPORT_ID"
echo ""
echo "==> Published to Groupon IQ:"
echo "    title:    $TITLE"
echo "    report:   $REPORT_ID"
echo "    version:  v$VERSION_NO ($VERSION_ID)"
echo "    url:      $REPORT_URL"

# Surface URL to subsequent steps + the run summary.
echo "iq_url=$REPORT_URL" >> "${GITHUB_OUTPUT:-/dev/null}"
{
  echo "## Groupon IQ"
  echo ""
  echo "- **Title:** $TITLE"
  echo "- **URL:** $REPORT_URL"
  echo "- **Version:** v$VERSION_NO"
} >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
