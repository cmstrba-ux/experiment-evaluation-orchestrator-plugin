#!/usr/bin/env bash
# Clone dependent plugins (ab-experiments from GHE, seo-impact-plugin from gh.com)
# and wire them into Claude Code's plugin registry so the headless `claude` CLI
# can find them.
#
# Required env (set by the workflow):
#   GHE_TOKEN — github.groupondev.com PAT with read on pcernik/claude-skills
#   GH_TOKEN  — github.com PAT (only needed if seo-impact-plugin is private)
#
# Plugin registry layout (mirrors what `/plugin install` produces locally):
#   ~/.claude/plugins/installed_plugins.json     — registry, points to installPath per plugin
#   ~/.claude/plugins/ci-marketplace/plugins/<name>/   — cloned plugin sources
set -euo pipefail

PLUGINS_ROOT="$HOME/.claude/plugins"
CI_MP="$PLUGINS_ROOT/ci-marketplace"
mkdir -p "$CI_MP/plugins" "$CI_MP/.claude-plugin"

# 1) ab-experiments — git subdir of pcernik/claude-skills (Groupon GHE)
echo "==> Cloning pcernik/claude-skills from GHE (subdir: plugins/pcernik/ab-experiments)"
if [[ -z "${GHE_TOKEN:-}" ]]; then
  echo "::error::GHE_TOKEN is not set; cannot clone github.groupondev.com/pcernik/claude-skills"
  exit 1
fi
TMP_SKILLS=$(mktemp -d)
git clone --depth 1 \
  "https://x-access-token:${GHE_TOKEN}@github.groupondev.com/pcernik/claude-skills.git" \
  "$TMP_SKILLS"
cp -r "$TMP_SKILLS/plugins/pcernik/ab-experiments" "$CI_MP/plugins/ab-experiments"
AB_SHA=$(cd "$TMP_SKILLS" && git rev-parse HEAD)
rm -rf "$TMP_SKILLS"

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
