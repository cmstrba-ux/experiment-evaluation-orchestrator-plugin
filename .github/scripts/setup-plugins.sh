#!/usr/bin/env bash
# Install dependent plugins for headless `claude --print` use.
#
# Hard-learned lesson from CI runs 26088077607 et al.: headless Claude Code
# (`claude --print`) refuses `/plugin marketplace add` / `/plugin install`
# with "/plugin isn't available in this environment." So the install MUST be
# done by hand-writing the registry. We mirror exactly the directory layout
# the interactive UI produces locally:
#
#   ~/.claude/plugins/local-marketplaces/<mp>/.claude-plugin/marketplace.json
#   ~/.claude/plugins/cache/<mp>/<plugin>/<version>/...
#   ~/.claude/plugins/installed_plugins.json   (registry, scope=user)
#
# That's the layout Claude Code auto-discovers on startup.
#
# Required env (set by the workflow):
#   GH_TOKEN — github.com PAT (only if seo-impact-plugin is private)
set -euo pipefail

PLUGINS_ROOT="$HOME/.claude/plugins"
MP_NAME="ci-marketplace"
LMP="$PLUGINS_ROOT/local-marketplaces/$MP_NAME"
CACHE="$PLUGINS_ROOT/cache/$MP_NAME"
WS="$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin"

mkdir -p "$LMP/plugins" "$LMP/.claude-plugin" "$CACHE"

# ---------- Stage source code under local-marketplaces/ ----------

# 1a) ab-experiments — vendored snapshot (no GHE access needed in CI).
echo "==> Staging vendored ab-experiments"
cp -r "$WS/vendor/ab-experiments" "$LMP/plugins/ab-experiments"
AB_VERSION="$(cat "$WS/vendor/ab-experiments/UPSTREAM_VERSION.txt" 2>/dev/null || echo unknown)"

# 1b) seo-impact-plugin — github.com clone.
echo "==> Cloning seo-impact-plugin from github.com"
SEO_URL="https://github.com/c-pacharya-groupon/seo-impact-plugin.git"
if [[ -n "${GH_TOKEN:-}" ]]; then
  SEO_URL="https://x-access-token:${GH_TOKEN}@github.com/c-pacharya-groupon/seo-impact-plugin.git"
fi
git clone --depth 1 "$SEO_URL" "$LMP/plugins/seo-impact-plugin"
SEO_SHA=$(cd "$LMP/plugins/seo-impact-plugin" && git rev-parse HEAD)
# Strip .git so the staged copy doesn't drag the upstream history.
rm -rf "$LMP/plugins/seo-impact-plugin/.git"

# 1c) experiment-evaluation-orchestrator — copy this repo.
echo "==> Staging experiment-evaluation-orchestrator from $WS"
cp -r "$WS" "$LMP/plugins/experiment-evaluation-orchestrator"
rm -rf "$LMP/plugins/experiment-evaluation-orchestrator/.git"
ORCH_VERSION=$(python -c "import json; print(json.load(open('$WS/.claude-plugin/plugin.json'))['version'])")
ORCH_SHA=$(cd "$WS" && git rev-parse HEAD)

# ---------- marketplace.json under local-marketplaces/ ----------

cat > "$LMP/.claude-plugin/marketplace.json" <<JSON
{
  "\$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "$MP_NAME",
  "description": "Ephemeral marketplace assembled by GitHub Actions for headless orchestrator runs",
  "owner": { "name": "ci", "email": "ci@noreply" },
  "plugins": [
    { "name": "ab-experiments",                       "source": "./plugins/ab-experiments" },
    { "name": "seo-impact-plugin",                    "source": "./plugins/seo-impact-plugin" },
    { "name": "experiment-evaluation-orchestrator",   "source": "./plugins/experiment-evaluation-orchestrator" }
  ]
}
JSON

# ---------- Materialize cache/ — same content as local-marketplaces/plugins/ ----------
# The interactive /plugin install copies (or hard-links) from local-marketplaces
# into the cache dir, then the registry's installPath points at the cache copy.
# We replicate that pattern.

for entry in \
  "ab-experiments|$AB_VERSION" \
  "seo-impact-plugin|$SEO_SHA" \
  "experiment-evaluation-orchestrator|$ORCH_VERSION"; do
  name="${entry%|*}"
  ver="${entry#*|}"
  dest="$CACHE/$name/$ver"
  mkdir -p "$dest"
  # cp -r ... /. copies CONTENTS (avoids creating a nested directory).
  cp -r "$LMP/plugins/$name"/. "$dest/"
  echo "==> Cached: $dest"
done

# ---------- installed_plugins.json registry ----------

NOW="$(date -Iseconds)"
cat > "$PLUGINS_ROOT/installed_plugins.json" <<JSON
{
  "version": 2,
  "plugins": {
    "ab-experiments@$MP_NAME": [
      {
        "scope": "user",
        "installPath": "$CACHE/ab-experiments/$AB_VERSION",
        "version": "$AB_VERSION",
        "installedAt": "$NOW",
        "lastUpdated": "$NOW",
        "gitCommitSha": "$AB_VERSION"
      }
    ],
    "seo-impact-plugin@$MP_NAME": [
      {
        "scope": "user",
        "installPath": "$CACHE/seo-impact-plugin/$SEO_SHA",
        "version": "$SEO_SHA",
        "installedAt": "$NOW",
        "lastUpdated": "$NOW",
        "gitCommitSha": "$SEO_SHA"
      }
    ],
    "experiment-evaluation-orchestrator@$MP_NAME": [
      {
        "scope": "user",
        "installPath": "$CACHE/experiment-evaluation-orchestrator/$ORCH_VERSION",
        "version": "$ORCH_VERSION",
        "installedAt": "$NOW",
        "lastUpdated": "$NOW",
        "gitCommitSha": "$ORCH_SHA"
      }
    ]
  }
}
JSON

# ---------- Diagnostics ----------

echo ""
echo "==> Marketplace layout:"
find "$LMP" -maxdepth 3 -type d
echo ""
echo "==> Cache layout:"
find "$CACHE" -maxdepth 2 -type d
echo ""
echo "==> Each cached plugin has its .claude-plugin/plugin.json?"
for name in ab-experiments seo-impact-plugin experiment-evaluation-orchestrator; do
  for ver_dir in "$CACHE/$name"/*; do
    if [[ -f "$ver_dir/.claude-plugin/plugin.json" ]]; then
      echo "  $name → plugin.json present ($(jq -r .version "$ver_dir/.claude-plugin/plugin.json" 2>/dev/null || echo no-jq))"
    elif [[ -d "$ver_dir/skills" || -d "$ver_dir/commands" ]]; then
      echo "  $name → no plugin.json but has skills/commands (marketplace-defined plugin)"
    else
      echo "  $name → MISSING — neither plugin.json nor skills/commands found in $ver_dir"
    fi
  done
done
echo ""
echo "==> installed_plugins.json:"
cat "$PLUGINS_ROOT/installed_plugins.json"
echo ""
echo "==> Sanity: does claude --print see our slash command?"
echo "(If our command is registered, /help output should include it.)"
claude --print "/help" 2>&1 | head -80 || true
