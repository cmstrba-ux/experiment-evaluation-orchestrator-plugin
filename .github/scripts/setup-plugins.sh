#!/usr/bin/env bash
# Install dependent plugins (ab-experiments vendored in this repo, seo-impact-plugin
# from gh.com) and wire them into Claude Code's plugin registry so the headless
# `claude` CLI can find them.
#
# Required env (set by the workflow):
#   GH_TOKEN  — github.com PAT (only needed if seo-impact-plugin is private)
#
# Plugin registry layout (mirrors what `/plugin install` produces locally):
#   ~/.claude/plugins/installed_plugins.json     — registry, points to installPath per plugin
#   ~/.claude/plugins/ci-marketplace/plugins/<name>/   — plugin sources
#
# ab-experiments is vendored under vendor/ab-experiments/ in this repo (synced manually
# from pcernik/claude-skills on Groupon GHE — see VENDOR_AB_EXPERIMENTS.md for the
# refresh procedure). Vendoring avoids any need for GHE access from CI runners, since
# the Groupon GHE instance is VPN-only and GitHub Actions cloud runners can't reach it.
set -euo pipefail

PLUGINS_ROOT="$HOME/.claude/plugins"
CI_MP="$PLUGINS_ROOT/ci-marketplace"
mkdir -p "$CI_MP/plugins" "$CI_MP/.claude-plugin"

# 1) ab-experiments — vendored copy in vendor/ab-experiments/ of this repo.
echo "==> Linking vendored ab-experiments from $GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin/vendor/ab-experiments"
VENDORED_AB="$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin/vendor/ab-experiments"
if [[ ! -d "$VENDORED_AB" ]]; then
  echo "::error::Vendored ab-experiments not found at $VENDORED_AB"
  exit 1
fi
cp -r "$VENDORED_AB" "$CI_MP/plugins/ab-experiments"
# Use the orchestrator repo's HEAD SHA as the version proxy for ab-experiments
# (since the vendored copy doesn't carry its own git history). Good-enough
# audit signal — "vendor was current as of orchestrator commit X".
AB_SHA=$(cd "$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin" && git rev-parse HEAD)

# 2) seo-impact-plugin — github.com/c-pacharya-groupon/seo-impact-plugin
echo "==> Cloning c-pacharya-groupon/seo-impact-plugin"
SEO_URL="https://github.com/c-pacharya-groupon/seo-impact-plugin.git"
if [[ -n "${GH_TOKEN:-}" ]]; then
  SEO_URL="https://x-access-token:${GH_TOKEN}@github.com/c-pacharya-groupon/seo-impact-plugin.git"
fi
git clone --depth 1 "$SEO_URL" "$CI_MP/plugins/seo-impact-plugin"
SEO_SHA=$(cd "$CI_MP/plugins/seo-impact-plugin" && git rev-parse HEAD)

# 3) experiment-evaluation-orchestrator — this repo, already checked out in GITHUB_WORKSPACE
echo "==> Linking experiment-evaluation-orchestrator from $GITHUB_WORKSPACE"
ln -sfn "$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin" \
  "$CI_MP/plugins/experiment-evaluation-orchestrator"
ORCH_VERSION=$(cat "$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin/.claude-plugin/plugin.json" \
  | python -c "import json,sys; print(json.load(sys.stdin)['version'])")
ORCH_SHA=$(cd "$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin" && git rev-parse HEAD)

# 4) Write ci-marketplace's marketplace.json so Claude Code understands the trio as a marketplace.
cat > "$CI_MP/.claude-plugin/marketplace.json" <<JSON
{
  "\$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "ci-marketplace",
  "description": "Ephemeral marketplace assembled by GitHub Actions for headless orchestrator runs",
  "owner": { "name": "ci", "email": "ci@noreply" },
  "plugins": [
    { "name": "ab-experiments", "source": "./plugins/ab-experiments" },
    { "name": "seo-impact-plugin", "source": "./plugins/seo-impact-plugin" },
    { "name": "experiment-evaluation-orchestrator", "source": "./plugins/experiment-evaluation-orchestrator" }
  ]
}
JSON

# 5) Write installed_plugins.json registry. Claude Code reads this to find each
#    plugin's installPath at runtime. Format matches what /plugin install writes locally.
cat > "$PLUGINS_ROOT/installed_plugins.json" <<JSON
{
  "version": 2,
  "plugins": {
    "ab-experiments@ci-marketplace": [
      {
        "scope": "user",
        "installPath": "$CI_MP/plugins/ab-experiments",
        "version": "$AB_SHA",
        "installedAt": "$(date -Iseconds)",
        "lastUpdated": "$(date -Iseconds)",
        "gitCommitSha": "$AB_SHA"
      }
    ],
    "seo-impact-plugin@ci-marketplace": [
      {
        "scope": "user",
        "installPath": "$CI_MP/plugins/seo-impact-plugin",
        "version": "$SEO_SHA",
        "installedAt": "$(date -Iseconds)",
        "lastUpdated": "$(date -Iseconds)",
        "gitCommitSha": "$SEO_SHA"
      }
    ],
    "experiment-evaluation-orchestrator@ci-marketplace": [
      {
        "scope": "user",
        "installPath": "$CI_MP/plugins/experiment-evaluation-orchestrator",
        "version": "$ORCH_VERSION",
        "installedAt": "$(date -Iseconds)",
        "lastUpdated": "$(date -Iseconds)",
        "gitCommitSha": "$ORCH_SHA"
      }
    ]
  }
}
JSON

echo ""
echo "==> Plugins installed:"
ls -la "$CI_MP/plugins/"
echo ""
echo "==> Registry:"
cat "$PLUGINS_ROOT/installed_plugins.json"
