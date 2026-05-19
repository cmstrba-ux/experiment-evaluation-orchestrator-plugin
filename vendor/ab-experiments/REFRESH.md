# Refreshing the vendored ab-experiments plugin

This directory contains a snapshot of the `ab-experiments` plugin from `pcernik/claude-skills` on Groupon GHE. We vendor it here because the GHE host (`github.groupondev.com`) is VPN-only and GitHub Actions cloud runners can't reach it — vendoring keeps CI runs unblocked.

The plugin doesn't change often (a few times a year). When it does, refresh as follows:

## Refresh procedure

Run on a machine with VPN access to GHE (your laptop will do):

```powershell
# Path to your locally-installed ab-experiments cache. The exact dir name
# changes every refresh; pick the most recent one.
$AB_CACHE = Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache\miro-personal\ab-experiments" `
  | Sort-Object LastWriteTime -Descending | Select-Object -First 1
echo "Refreshing from: $($AB_CACHE.FullName)"

# Path to this vendored copy.
$VENDOR_DIR = "$env:USERPROFILE\.claude\plugins\local-marketplaces\miro-personal\plugins\experiment-evaluation-orchestrator\vendor\ab-experiments"

# Wipe + recopy. The .in_use/ subdir holds process locks that shouldn't be vendored.
Remove-Item -Recurse -Force $VENDOR_DIR\*
Copy-Item -Recurse "$($AB_CACHE.FullName)\*" $VENDOR_DIR
Remove-Item -Recurse -Force "$VENDOR_DIR\.in_use" -ErrorAction SilentlyContinue

# Pin the upstream SHA so we have an audit trail of what version is vendored.
$AB_CACHE.Name | Out-File "$VENDOR_DIR\UPSTREAM_VERSION.txt" -NoNewline
echo "Vendored version: $($AB_CACHE.Name)"

# Commit + push.
cd $env:USERPROFILE\.claude\plugins\local-marketplaces\miro-personal\plugins\experiment-evaluation-orchestrator
git add vendor/ab-experiments
git commit -m "vendor: refresh ab-experiments to $($AB_CACHE.Name)"
git push
```

The next CI run picks up the refreshed vendor automatically.

## When to refresh

- Upstream `ab-experiments` changes the c3 evaluation .docx format (rare).
- Upstream changes the `evaluate-experiment` slash command interface (rarer).
- A bug fix lands upstream that affects the orchestrator's `ab-experiments:evaluate-experiment` passthrough call.

If you're not sure whether you need to refresh, the orchestrator runs against the vendored copy locally too (via the marketplace) — local runs reproducing CI behavior means the vendor is fresh enough.

## Why not a git submodule?

A submodule would point to the GHE URL, which GitHub Actions still can't reach. The whole point of vendoring is to remove the runtime dependency on GHE. Submodules just defer the problem.

If a public-github mirror of `pcernik/claude-skills` ever appears, a submodule pointing there is the better long-term answer.
