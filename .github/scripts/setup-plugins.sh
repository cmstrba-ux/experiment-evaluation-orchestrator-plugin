#!/usr/bin/env bash
# Stage the three plugins to disk for headless `claude --print` use.
#
# Final design (after two rounds of dead ends in CI runs 26088077607 + 26088326173):
# headless `claude --print` blocks `/plugin install` AND blocks `/help` AND
# doesn't auto-load installed_plugins.json with any layout we tried. The
# canonical headless plugin-loading mechanism is `claude --plugin-dir <path>`,
# which loads a plugin per-session. So this script just stages the files;
# the workflow passes them via `--plugin-dir` flags on the `claude --print`
# invocation.
#
# Output paths (stable, used by the workflow):
#   /tmp/plugins/ab-experiments                       (from vendor/)
#   /tmp/plugins/seo-impact-plugin                    (cloned from gh.com)
#   /tmp/plugins/experiment-evaluation-orchestrator   (copied from $GITHUB_WORKSPACE)
#
# Required env (set by the workflow):
#   GH_TOKEN — github.com PAT (only if seo-impact-plugin is private)
set -euo pipefail

STAGE=/tmp/plugins
WS="$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin"

rm -rf "$STAGE"
mkdir -p "$STAGE"

# 1. ab-experiments — vendored in this repo (no GHE access in CI).
echo "==> ab-experiments (from vendor/)"
cp -r "$WS/vendor/ab-experiments" "$STAGE/ab-experiments"

# 2. seo-impact-plugin — github.com clone.
echo "==> seo-impact-plugin (cloning github.com/c-pacharya-groupon/seo-impact-plugin)"
SEO_URL="https://github.com/c-pacharya-groupon/seo-impact-plugin.git"
if [[ -n "${GH_TOKEN:-}" ]]; then
  SEO_URL="https://x-access-token:${GH_TOKEN}@github.com/c-pacharya-groupon/seo-impact-plugin.git"
fi
git clone --depth 1 "$SEO_URL" "$STAGE/seo-impact-plugin"
rm -rf "$STAGE/seo-impact-plugin/.git"

# 3. experiment-evaluation-orchestrator — copy from checked-out workspace.
echo "==> experiment-evaluation-orchestrator (from $WS)"
cp -r "$WS" "$STAGE/experiment-evaluation-orchestrator"
rm -rf "$STAGE/experiment-evaluation-orchestrator/.git"

# Diagnostics — confirms each plugin has a valid .claude-plugin/plugin.json
# AND a commands/ or skills/ directory that the orchestrator's main command
# references via ${CLAUDE_PLUGIN_ROOT}.
echo ""
echo "==> Staged plugins at $STAGE:"
for name in ab-experiments seo-impact-plugin experiment-evaluation-orchestrator; do
  dir="$STAGE/$name"
  if [[ -f "$dir/.claude-plugin/plugin.json" ]]; then
    ver=$(jq -r '.version // "no-version"' "$dir/.claude-plugin/plugin.json" 2>/dev/null || echo no-jq)
    echo "  $name → plugin.json v$ver"
  else
    echo "  $name → no plugin.json (marketplace-defined; commands/skills should still load)"
  fi
  ls "$dir" | head -10 | sed 's/^/    /'
done
echo ""
echo "==> Plugin loading will happen via `claude --plugin-dir` on the next step, NOT via installed_plugins.json."
