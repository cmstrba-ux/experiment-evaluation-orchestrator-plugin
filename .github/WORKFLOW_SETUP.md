# GitHub Actions setup — `Evaluate Review Experiments` (self-hosted runner)

The active workflow at `.github/workflows/evaluate.yml` runs on a **self-hosted GitHub Actions runner installed on your local Windows machine** so it uses your existing OAuth/Max Claude Code login. No pay-per-token API key, no plugin re-clone, no `bq` shim — your local Claude Code, local `bq`, and locally-installed plugins do the work.

> Cloud-runner rollback: if you ever want to switch back to a GitHub-hosted runner with `ANTHROPIC_API_KEY`, see `.github/disabled/workflows/evaluate-cloud-fallback.yml` and `.github/disabled/WORKFLOW_SETUP_CLOUD.md`. Move the workflow file back into `.github/workflows/`, swap the docs, and add the cloud secrets.

## TL;DR

1. Install the GitHub Actions runner on your Windows box as a service (~10 min).
2. Add `IQ_API_KEY` as a GitHub secret.
3. Trigger the workflow manually once to verify.

---

## 1. Install the self-hosted runner

### a. Get the runner package

1. GitHub repo → **Settings** → **Actions** → **Runners** → **New self-hosted runner**.
2. Pick **Windows x64**.
3. GitHub shows you a one-time registration token + Invoke-WebRequest / config commands. Keep the page open.

### b. Configure under your user account

Open **PowerShell as yourself** (NOT as admin — the runner needs your user's Claude/gcloud auth):

```powershell
mkdir C:\actions-runner; cd C:\actions-runner

# Download (replace 2.319.1 with the version GitHub shows).
Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.319.1/actions-runner-win-x64-2.319.1.zip -OutFile actions-runner.zip
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::ExtractToDirectory("$PWD\actions-runner.zip", "$PWD")

# Register with the repo (use the token from the GitHub page).
./config.cmd --url https://github.com/cmstrba-ux/experiment-evaluation-orchestrator-plugin --token <REPO_TOKEN>
# When prompted for labels, ACCEPT defaults — the workflow targets [self-hosted, windows].
```

### c. Install as a Windows service (so it survives logout)

```powershell
# Run the service as YOUR account so it inherits your claude OAuth + gcloud login.
./svc.cmd install YOURDOMAIN\miro    # or .\miro for local accounts
./svc.cmd start
```

To check / control later:
```powershell
./svc.cmd status
./svc.cmd stop
```

### d. Verify

1. GitHub repo → **Settings** → **Actions** → **Runners**. Your machine should show as `Idle` (green dot).
2. Open a fresh PowerShell as your user and confirm `claude --version`, `bq version`, and `curl --version` all work. The runner inherits that environment, so anything that works for you works for the workflow.

---

## 2. Add the IQ_API_KEY secret

Settings → Secrets and variables → Actions → **New repository secret**:

| Secret | Value | Source |
|---|---|---|
| `IQ_API_KEY` | Your Groupon IQ personal token | Copy from `~/.claude/settings.json` `env.IQ_API_KEY` |

That's the only secret. Claude auth via your local OAuth; `bq` auth via your local gcloud OAuth; plugins via your local install.

---

## 3. Test it

1. Push this workflow to `main` (already committed in `0.8.3`).
2. Actions tab → **Evaluate Review Experiments** → **Run workflow** → pick `main` → set `mode` (e.g., `explicit FAQ reviews - 8k - before change` for a single experiment) → Run.
3. Expected runtime ~30-60 min, same as a manual local invocation.
4. On success:
   - Combined report as a workflow artifact (kept 30 days).
   - Groupon IQ updated at `Experiment Evaluation Combined Report — YYYY-MM-DD`.
5. On failure: most issues are environment, not code:
   - **`claude` not found** → service running as wrong user. Reinstall with `./svc.cmd install <YOUR_USER>`.
   - **`bq` auth fails** → local gcloud session expired. Run `gcloud auth login` in PowerShell as your user.
   - **Slash command not found** → plugin not installed locally. Run `/plugin install experiment-evaluation-orchestrator@miro-personal` from your interactive Claude Code session.
   - **IQ publish fails** → `IQ_API_KEY` secret missing or expired.

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

## 5. If your machine is off at cron time

GitHub queues the scheduled run until a matching runner comes online, then dispatches. The job times out at 120 minutes (configurable). So:

- **Sleep / brief reboots**: fine — the queued run kicks off when your runner reconnects.
- **Off for hours**: the run waits in the queue; if you exceed the timeout it's cancelled. Trigger manually when you're back online.
- **Off for days**: install on an always-on box (a NAS, a Linux mini-PC, or eventually a cheap VPS — Linux runner is the same workflow, just change `runs-on:` to `[self-hosted, linux]` and update the `WORKSPACE_DIR` / `PLUGIN_DIR` env vars to Linux paths).

---

## 6. What's different from a local manual run

| | Manual local run | Self-hosted CI run |
|---|---|---|
| Trigger | You type `/evaluate-reviews-experiments` | Cron or workflow_dispatch from GitHub UI |
| Claude auth | Your OAuth | Your OAuth (same install, same login) |
| `bq` auth | Your gcloud | Your gcloud (same) |
| Plugin install | `~/.claude/plugins/` | `~/.claude/plugins/` (same) |
| IQ publish | Skill Step 11 via MCP | Pure curl via `.github/scripts/publish-to-iq.sh` (skill Step 11 skipped — IQ_API_KEY intentionally unset for the Claude run) |
| Cost | Your Claude subscription | Your Claude subscription (same — no separate API tokens) |

The CI run is essentially a scheduled `claude --print "/experiment-evaluation-orchestrator:evaluate-reviews-experiments"` followed by a curl IQ upload, both on your machine. Same auth, same code, just automated.

---

## 7. Updating the plugin code

The workflow's "Update plugin from origin/main (if clean working tree)" step runs `git pull` in the live install location before each run. So:

- **Most of the time**: latest committed code on `main` is used automatically.
- **If you have uncommitted local edits** in `~/.claude/plugins/local-marketplaces/miro-personal/plugins/experiment-evaluation-orchestrator/`: the step skips the reset with a warning and uses your local state. Commit or stash before scheduled runs if you want pure latest behavior.

---

## 8. Security notes

- **Runner runs as you**: the GH Actions service inherits your user permissions. Don't give push access to the repo to anyone you wouldn't lend your laptop to.
- **`IQ_API_KEY` is yours**: anyone who can trigger workflow runs OR has write access to repo secrets can publish to IQ as you.
- **No remote secret material on your box**: the runner only stores its own GitHub registration token. Your Claude OAuth and gcloud creds stay in your user profile, untouched.
