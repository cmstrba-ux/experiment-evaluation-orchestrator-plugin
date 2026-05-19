# GitHub Actions setup — `Evaluate Review Experiments`

The workflow at `.github/workflows/evaluate.yml` runs the orchestrator on a Mon/Wed/Fri 11:00 UTC cron and publishes the combined HTML report to Groupon IQ. Once these one-time setup steps are done, daily runs are zero-touch.

**Auth approach**: this workflow uses your gcloud user OAuth credentials (Application Default Credentials) instead of Workload Identity Federation. Reason: WIF requires creating a workload identity pool in your GCP project, which most users don't have IAM admin rights for. ADC works today with zero admin involvement, at the cost of being tied to a single user (you). For production-grade automation managed by an SRE team, switch to WIF once admin perms are available.

## TL;DR

1. Export your gcloud Application Default Credentials JSON (one command).
2. Add 4 secrets to this repo's GitHub Actions settings.
3. Trigger the workflow manually once to verify.

---

## 1. Export your gcloud ADC credentials

On the machine where `bq` works today (your usual dev box):

```powershell
# If you've never run `gcloud auth application-default login`, do it now:
gcloud auth application-default login
# A browser opens; sign in with your Groupon account.

# The credentials are now at this path. Open in Notepad:
notepad $env:APPDATA\gcloud\application_default_credentials.json
# Select all → Copy. Don't paste into chat; paste directly into the GitHub secret UI.
```

The file contains a `refresh_token` that grants long-lived access. Treat it like a password.

**Rotation**: when the token gets invalidated (you run `gcloud auth application-default revoke`, your Google session expires from org policy, or you change your password), the CI will start failing 401s. To rotate: revoke locally, re-login, re-paste the new JSON into the `GCP_ADC_JSON` GitHub secret.

---

## 2. Add GitHub repo secrets

Settings → Secrets and variables → Actions → **New repository secret**. Add all 4 (+1 optional):

| Secret | Value | How to get |
|---|---|---|
| `ANTHROPIC_API_KEY` | `sk-ant-…` | https://console.anthropic.com/settings/keys |
| `IQ_API_KEY` | Groupon IQ personal token | Copy from your local `~/.claude/settings.json` `env.IQ_API_KEY`, or mint a new one at https://iq.groupon.com/api-tokens |
| `GCP_ADC_JSON` | Contents of the JSON file from step 1 | Paste the whole file content (including `{` and `}`) |
| `GH_TOKEN` *(optional)* | github.com PAT with `repo` scope, only if `c-pacharya-groupon/seo-impact-plugin` is private | https://github.com/settings/tokens |

> The auto-provided `GITHUB_TOKEN` only has access to *this* repo — for cloning other public/private repos you must use a separate PAT. If `seo-impact-plugin` is fully public, you can omit `GH_TOKEN`.

> The `ab-experiments` plugin is **vendored** in `vendor/ab-experiments/` of this repo (it lives on Groupon's GHE which is VPN-only, unreachable from GitHub Actions cloud runners). To refresh the vendored copy when upstream changes, see `vendor/ab-experiments/REFRESH.md`.

---

## 3. Test it

1. Push the workflow to `main` (already committed in `0.8.0`).
2. Actions tab → **Evaluate Review Experiments** → **Run workflow** → pick `main` → Run.
3. Watch the job run. Expected ~30-60 min.
4. On success:
   - HTML artifact downloadable from the run page (kept 30 days).
   - Groupon IQ report at the canonical title `Experiment Evaluation Combined Report — YYYY-MM-DD` (versioned if a same-day run already exists).
5. If it fails:
   - **`bq query` returns 401 / 403** → `GCP_ADC_JSON` expired or your account lost permissions. Re-export from your local box and update the secret.
   - **`bq query` returns "project not found"** → the billing project in the workflow (`prj-grp-foundryai-dev-7c37`) might not exist or you lost access. Edit the workflow's `GCP_BILLING_PROJECT` constant.
   - **plugin install fails** → `GHE_TOKEN` lacks `repo` scope or is expired.
   - **Claude run fails** → `ANTHROPIC_API_KEY` is missing or hit rate limit / out of credits.
   - **IQ publish fails** → `IQ_API_KEY` expired. Test locally with: `curl -X POST -H "g-api-key: $IQ_API_KEY" -d '{}' -H 'Content-Type: application/json' https://api.enc.groupon.com/reports/list`.

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
| BQ auth | Your `gcloud` OAuth (auto-renewed in your shell) | Same OAuth via ADC, restored from a GitHub secret |
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

---

## Security notes

- **The `GCP_ADC_JSON` secret IS you** in CI. Anyone with write access to this repo's secrets (or anyone who can trigger workflow runs that print the secret accidentally) can act as your gcloud identity. Treat the secret with the same care as your laptop's gcloud login.
- **The workflow never logs the secret content** — no `echo "$GCP_ADC_JSON"`, no `cat` of the JSON file. If you add debug steps later, keep that contract.
- **GitHub masks secrets in logs** by default, but only known secret values — if you write the value through string interpolation that changes the format, masking can miss. Stick to env-var passing.
- **When you leave Groupon** or rotate your account, run `gcloud auth application-default revoke` locally — that invalidates the refresh token AND the CI secret in one step.
