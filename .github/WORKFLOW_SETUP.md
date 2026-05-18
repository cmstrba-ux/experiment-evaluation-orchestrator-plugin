# GitHub Actions setup — `Evaluate Review Experiments`

The workflow at `.github/workflows/evaluate.yml` runs the orchestrator on a Mon/Wed/Fri 11:00 UTC cron and publishes the combined HTML report to Groupon IQ. Once these one-time setup steps are done, daily runs are zero-touch.

## TL;DR

1. Configure Workload Identity Federation in GCP (one-time, ~15 min).
2. Add 5 secrets to this repo's GitHub Actions settings.
3. Trigger the workflow manually once to verify (Actions → Evaluate Review Experiments → Run workflow).

---

## 1. Workload Identity Federation (GCP side)

WIF lets GitHub Actions impersonate a GCP service account without storing static JSON keys. ~15-20 min one-time.

### a. Create the WIF pool + GitHub provider

```bash
# Run these locally with gcloud authenticated as a project owner.
export PROJECT_ID="your-gcp-project-id"
export POOL_ID="github-actions"
export PROVIDER_ID="github"

gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --display-name="GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc "$PROVIDER_ID" \
  --project="$PROJECT_ID" \
  --location="global" \
  --workload-identity-pool="$POOL_ID" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository == 'cmstrba-ux/experiment-evaluation-orchestrator-plugin'" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

### b. Pick or create a service account

```bash
export SA_NAME="orchestrator-ci"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create "$SA_NAME" \
  --project="$PROJECT_ID" \
  --display-name="Experiment evaluation orchestrator CI"
```

### c. Grant BQ permissions

```bash
# Workspace project — for running queries (BQ Job User).
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/bigquery.jobUser"

# Source datasets — Data Viewer on each one the orchestrator reads.
for dataset_project in kbc-grpn-40-0cd2 kbc-grpn-35 prj-grp-dataview-prod-1ff9; do
  gcloud projects add-iam-policy-binding "$dataset_project" \
    --member="serviceAccount:$SA_EMAIL" \
    --role="roles/bigquery.dataViewer"
done
```

### d. Bind the GitHub provider to the service account

```bash
export REPO="cmstrba-ux/experiment-evaluation-orchestrator-plugin"
export POOL_FULL="projects/$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')/locations/global/workloadIdentityPools/$POOL_ID"

gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" \
  --project="$PROJECT_ID" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/$POOL_FULL/attribute.repository/$REPO"
```

### e. Capture two values you need

```bash
echo "GCP_WORKLOAD_IDENTITY_PROVIDER = $POOL_FULL/providers/$PROVIDER_ID"
echo "GCP_SERVICE_ACCOUNT            = $SA_EMAIL"
```

---

## 2. Add GitHub repo secrets

Settings → Secrets and variables → Actions → **New repository secret**. Add all 5:

| Secret | Value | How to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-…` | https://console.anthropic.com/settings/keys |
| `IQ_API_KEY` | Groupon IQ personal token | https://iq.groupon.com/api-tokens |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | from step 1.e | — |
| `GCP_SERVICE_ACCOUNT` | from step 1.e | — |
| `GHE_TOKEN` | github.groupondev.com PAT with `repo` scope on `pcernik/claude-skills` | https://github.groupondev.com/settings/tokens |
| `GH_TOKEN` *(optional)* | github.com PAT with `repo` scope, only if `c-pacharya-groupon/seo-impact-plugin` is private | https://github.com/settings/tokens |

> The auto-provided `GITHUB_TOKEN` only has access to *this* repo — for cloning other public/private repos you must use a separate PAT. If `seo-impact-plugin` is fully public, you can omit `GH_TOKEN`.

---

## 3. Test it

1. Push the workflow to `main` (already committed in `0.8.0`).
2. Actions tab → **Evaluate Review Experiments** → **Run workflow** → Run.
3. Watch the job run. Expected ~30-60 min.
4. On success:
   - HTML artifact downloadable from the run page (kept 30 days).
   - Groupon IQ report at the canonical title `Experiment Evaluation Combined Report — YYYY-MM-DD` (versioned if a same-day run already exists).
5. If it fails:
   - **bq auth fails** → check the WIF pool's attribute-condition matches your repo path.
   - **plugin install fails** → check `GHE_TOKEN` has `repo` scope and isn't expired.
   - **Claude run fails** → check `ANTHROPIC_API_KEY` is set and has model access.
   - **IQ publish fails** → check `IQ_API_KEY` is valid (`curl -H "g-api-key: $IQ_API_KEY" https://api.enc.groupon.com/reports/list -X POST -d '{}' -H 'Content-Type: application/json'`).

---

## 4. Schedule changes

Edit `.github/workflows/evaluate.yml` cron and push:

```yaml
on:
  schedule:
    - cron: '0 11 * * 1,3,5'  # Mon/Wed/Fri at 11:00 UTC
```

Common patterns:
- `0 6 * * 1-5` — weekday mornings, 06:00 UTC
- `0 11 * * 1,3,5` — Mon/Wed/Fri at 11:00 UTC (default)
- `0 11 * * *` — every day at 11:00 UTC

---

## What's different from a local run

| | Local | CI |
|---|---|---|
| MCP servers | Full set (groupon-iq, datacatalog, etc.) | None — pure curl for IQ |
| Plugin install | Persistent in `~/.claude/plugins/` | Re-cloned every run from upstream repos |
| BQ auth | Your `gcloud` OAuth | Workload Identity Federation impersonates the SA |
| Output location | `temp/experiment-evaluation/` or `<project>/deliverables/` | Workflow runner workspace (artifacted after) |
| IQ publish | Skill Step 11 via MCP | Skill Step 11 skipped (IQ_API_KEY unset for Claude); workflow does curl publish |
| Cost | Your Claude session | Anthropic API key billing for Claude Code CLI |

---

## Cost expectations

Each run dispatches ~6 Opus subagents (3 experiments × {AB, deal_charts}; +SEO when ≥14 days). Rough estimate from local runs:
- 2-3M tokens per full run
- ~$15-30 per run at current Claude Opus pricing
- Mon/Wed/Fri = ~12 runs/month = ~$180-360/month

If this is too high, options:
- Reduce frequency to weekly
- Use Sonnet for non-narrative subagents (verdict logic only needs Sonnet; only the .docx passthrough genuinely benefits from Opus)
- Skip the .docx passthrough step entirely
