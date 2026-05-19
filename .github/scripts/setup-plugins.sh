#!/usr/bin/env bash
# Install dependent plugins into the local Claude Code config so headless
# `claude --print` can resolve slash commands like /evaluate-reviews-experiments.
#
# Strategy: place source code at ~/.claude/plugins/local-marketplaces/ci-marketplace/
# (matches the directory pattern that Claude Code auto-discovers), then use
# `claude --print "/plugin marketplace add ..."` and `/plugin install ...` to
# do the canonical registration — the same operations the interactive UI runs.
# This is more reliable than hand-writing installed_plugins.json because the
# install command also handles per-version cache materialization, enabling,
# and any internal registry side effects we don't know about.
#
# Required env (set by the workflow):
#   ANTHROPIC_API_KEY — Claude API key (needed because /plugin install boots a Claude session)
#   GH_TOKEN          — github.com PAT (only if seo-impact-plugin is private)
set -euo pipefail

PLUGINS_ROOT="$HOME/.claude/plugins"
LMP_NAME="ci-marketplace"
LMP="$PLUGINS_ROOT/local-marketplaces/$LMP_NAME"
WS="$GITHUB_WORKSPACE/experiment-evaluation-orchestrator-plugin"

mkdir -p "$LMP/plugins" "$LMP/.claude-plugin"

# ---------- Step 1: stage plugin source code under local-marketplaces ----------

# 1a) ab-experiments — copy from vendored snapshot (no GHE access needed in CI).
echo "==> Staging vendored ab-experiments"
cp -r "$WS/vendor/ab-experiments" "$LMP/plugins/ab-experiments"

# 1b) seo-impact-plugin — clone from github.com.
echo "==> Cloning seo-impact-plugin from github.com"
SEO_URL="https://github.com/c-pacharya-groupon/seo-impact-plugin.git"
if [[ -n "${GH_TOKEN:-}" ]]; then
  SEO_URL="https://x-access-token:${GH_TOKEN}@github.com/c-pacharya-groupon/seo-impact-plugin.git"
fi
git clone --depth 1 "$SEO_URL" "$LMP/plugins/seo-impact-plugin"

# 1c) experiment-evaluation-orchestrator — copy this repo (NOT symlink; symlinks
# are unreliable across Claude Code's plugin scan on some Linux setups).
echo "==> Staging experiment-evaluation-orchestrator from $WS"
cp -r "$WS" "$LMP/plugins/experiment-evaluation-orchestrator"
# Drop .git so the staged copy doesn't carry the orchestrator repo's history.
rm -rf "$LMP/plugins/experiment-evaluation-orchestrator/.git"

# Step 2: write the marketplace manifest so Claude Code's marketplace discovery
# finds the trio when it scans ~/.claude/plugins/local-marketplaces/*/.
cat > "$LMP/.claude-plugin/marketplace.json" <<JSON
{
  "\$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "$LMP_NAME",
  "description": "Ephemeral marketplace assembled by GitHub Actions for headless orchestrator runs",
  "owner": { "name": "ci", "email": "ci@noreply" },
  "plugins": [
    { "name": "ab-experiments",                       "source": "./plugins/ab-experiments" },
    { "name": "seo-impact-plugin",                    "source": "./plugins/seo-impact-plugin" },
    { "name": "experiment-evaluation-orchestrator",   "source": "./plugins/experiment-evaluation-orchestrator" }
  ]
}
JSON

echo "==> Marketplace staged at $LMP"
ls -la "$LMP/plugins/"
echo ""
echo "==> marketplace.json:"
cat "$LMP/.claude-plugin/marketplace.json"

# ---------- Step 3: use `claude` to register marketplace + install plugins ----

# These calls hit the Claude API briefly (each spawns a small session). Cost
# per call is tiny (~$0.005 each), but adds up across 4 calls — keep them at
# the end so we fail fast on staging errors before burning tokens.
#
# `--print` mode: claude runs the prompt non-interactively, prints output,
# exits. Slash commands are recognized; /plugin install writes to
# ~/.claude/plugins/installed_plugins.json which persists for the next
# claude invocation (i.e., the orchestrator run step below).

echo ""
echo "==> claude --version"
claude --version

echo ""
echo "==> Registering ci-marketplace"
claude --print "/plugin marketplace add $LMP"

echo ""
echo "==> Installing ab-experiments@$LMP_NAME"
claude --print "/plugin install ab-experiments@$LMP_NAME"

echo ""
echo "==> Installing seo-impact-plugin@$LMP_NAME"
claude --print "/plugin install seo-impact-plugin@$LMP_NAME"

echo ""
echo "==> Installing experiment-evaluation-orchestrator@$LMP_NAME"
claude --print "/plugin install experiment-evaluation-orchestrator@$LMP_NAME"

echo ""
echo "==> Verifying — /plugin list (should show all 3)"
claude --print "/plugin list"

echo ""
echo "==> Verifying — installed_plugins.json contents:"
cat "$PLUGINS_ROOT/installed_plugins.json"
