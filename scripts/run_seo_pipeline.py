"""Deterministic SEO pipeline runner for the experiment-evaluation-orchestrator.

Replaces the prompt-driven `run-seo-evaluation` skill chain. Takes a pre-enriched
URL list from `resolve-deal-urls` (urls_<alt>.json) and runs the upstream
seo-impact-plugin pipeline end-to-end without any subagent interpretation.

Skips the upstream `resolve` / `mds-insights-review` stages — URLs are already
enriched from BQ (deal_url, landing_page, web_category_level_1/2). Calls the
upstream `classify -> fetch -> enrich -> analyze -> generate` stages directly.

Writes the same JSON intermediate shape the renderer expects in
`raw/seo_<alt>.json`, plus passthrough HTML/XLSX under `passthrough/`.

Usage:
    python scripts/run_seo_pipeline.py \\
        --alternate-name "AI Summaries v4 - Single format 30k" \\
        --variant-urls /path/to/raw/urls_<alt>.json \\
        --release-date 2026-04-26 \\
        --out /path/to/raw/seo_<alt>.json \\
        --passthrough-dir /path/to/passthrough
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import logging
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yaml

logger = logging.getLogger("run_seo_pipeline")


def _find_seo_plugin_root() -> Path:
    """Locate the installed seo-impact-plugin via the Claude Code plugin registry.

    The canonical mechanism is `~/.claude/plugins/installed_plugins.json` — every
    installed plugin records its `installPath` there regardless of how it was sourced
    (local marketplace `./...` path vs remote `url:` / `github:` source). Reading from
    the registry instead of globbing the cache directory means:
      - No hard-coded SHA-bearing paths that break when upstream updates;
      - Works identically for any plugin source type;
      - Picks up the same installation the host runtime uses.

    Falls back to a cache glob ONLY if the registry can't be read or doesn't list the
    plugin — that path is retained as a defensive backstop for very old installs that
    predate the v2 registry, but should not be the primary mechanism.

    The plugin's on-disk layout may be flat (`<root>/scripts/impact_analyzer.py`) or
    nested under `plugins/seo-impact-plugin/` (the upstream repo's actual structure).
    Both are supported.
    """
    home = Path.home()
    registry_path = home / ".claude" / "plugins" / "installed_plugins.json"

    def _verify_root(root: Path) -> Path | None:
        """Return the directory that actually contains the upstream scripts/, or None."""
        for candidate in (root / "plugins" / "seo-impact-plugin", root):
            if (candidate / "scripts" / "impact_analyzer.py").is_file():
                return candidate
        return None

    # --- Primary path: read installed_plugins.json ---
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            entries = (registry.get("plugins") or {})
            # Match any marketplace — keyed `seo-impact-plugin@<marketplace>`. Project
            # scope wins over user scope (the entry list is iterated in registry order
            # and project-scoped installs are usually first; both work either way).
            for key, install_list in entries.items():
                if not key.startswith("seo-impact-plugin@"):
                    continue
                for entry in install_list or []:
                    install_path = entry.get("installPath")
                    if not install_path:
                        continue
                    verified = _verify_root(Path(install_path))
                    if verified is not None:
                        return verified
        except (OSError, ValueError, KeyError):
            pass  # fall through to glob fallback

    # --- Fallback: glob the cache tree (retained for resilience) ---
    candidates = []
    for pattern in (
        "*/seo-impact-plugin/*/plugins/seo-impact-plugin/scripts/impact_analyzer.py",
        "*/seo-impact-plugin/*/scripts/impact_analyzer.py",
    ):
        for hit in (home / ".claude" / "plugins" / "cache").glob(pattern):
            candidates.append(hit.parent.parent)
    if not candidates:
        raise RuntimeError(
            "Could not find seo-impact-plugin via installed_plugins.json or the "
            "plugin cache. Install it via `/plugin marketplace add <marketplace>` + "
            "`/plugin install seo-impact-plugin@<marketplace>` first."
        )
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _build_variant_df(urls_json_path: Path) -> pd.DataFrame:
    """Materialize the variant DataFrame the SEO pipeline expects.

    Skips upstream `resolve()` by populating canonical_url + the same enrichment
    columns it would have produced from MDS.
    """
    rows = json.loads(urls_json_path.read_text(encoding="utf-8"))
    if isinstance(rows, dict):  # status:no_deals etc.
        raise ValueError(f"urls JSON has no rows: {rows}")
    if not rows:
        raise ValueError("urls JSON is empty — nothing to evaluate.")

    df = pd.DataFrame(rows)
    landing = df.get("landing_page")
    # Fall back to deal_url if landing_page is absent, all-NaN, or all relative paths
    # (resolve-deal-urls emits relative paths in landing_page but full URLs in deal_url).
    if (
        landing is None
        or landing.isna().all()
        or not landing.dropna().str.startswith(("http://", "https://")).any()
    ):
        landing = df.get("deal_url")
    if landing is None:
        raise ValueError("urls JSON missing both 'landing_page' and 'deal_url' columns.")

    out = pd.DataFrame({
        "url": landing.astype(str),
        "canonical_url": landing.astype(str),
        "group": "variant",
        "source_row": range(1, len(df) + 1),
        "mds_uuid": df.get("deal_uuid"),
        "mds_category": None,
        "category_level_1": df.get("web_category_level_1"),
        "category_level_2": df.get("web_category_level_2"),
    })
    # Drop rows where landing_page is NaN/empty after coercion.
    out = out[out["url"].str.startswith(("http://", "https://"), na=False)].reset_index(drop=True)
    out.attrs["ingestion_mode"] = "orchestrator_pre_enriched"
    out.attrs["source_descriptor"] = f"urls_<alt>.json ({len(out)} URLs)"
    return out


def _make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def run(
    alternate_name: str,
    variant_urls_path: Path,
    release_date: date,
    out_path: Path,
    passthrough_dir: Path,
) -> dict:
    plugin_root = _find_seo_plugin_root()
    logger.info("Using seo-impact-plugin at %s", plugin_root)

    sys.path.insert(0, str(plugin_root))
    # Lazy imports so import errors surface only when the plugin is actually invoked.
    from scripts.page_classifier import classify
    from scripts.gsc_fetcher import fetch
    from scripts.category_enricher import enrich
    from scripts.impact_analyzer import analyze
    from scripts.report_generator import generate

    config = yaml.safe_load((plugin_root / "config" / "plugin_config.yaml").read_text(encoding="utf-8"))
    # Pre-enriched URLs may exceed the upstream default cap; orchestrator runs
    # are explicit opt-ins to whatever size the test_deals row count produces.
    config.setdefault("plugin", {})["allow_oversize"] = True

    df = _build_variant_df(variant_urls_path)
    if df.empty:
        out = {"status": "no_urls", "alternate_name": alternate_name}
        out_path.write_text(json.dumps(out), encoding="utf-8")
        return out

    run_id = _make_run_id()
    # Use a dedicated scratch dir under the orchestrator passthrough tree so
    # repeated runs don't collide and intermediates are easy to inspect.
    scratch_dir = passthrough_dir / f"_seo_scratch_{alternate_name.replace(' ', '_').replace('/', '_')}"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[%s] Stage 03 — page classifier (%d URLs)", run_id, len(df))
    df = classify(df, config, scratch_dir)

    logger.info("[%s] Stage 05 — GSC + UE fetch (release=%s)", run_id, release_date)
    data = fetch(df, release_date=release_date, config=config, output_dir=scratch_dir, run_id=run_id)

    logger.info("[%s] Stage 04 — category enricher", run_id)
    df = enrich(df, config)

    config["_effective_post_days"] = data["meta"]["effective_post_days"]
    logger.info(
        "[%s] Stage 06 — impact analyzer (%d post days)",
        run_id, data["meta"]["effective_post_days"],
    )
    result = analyze(
        data["page_pre"], data["page_post"],
        data["kw_pre"], data["kw_post"],
        data["ue_cy"], data["ue_py"],
        df_meta=df, config=config, run_id=run_id, output_dir=scratch_dir,
        bench_pre=data.get("bench_pre"), bench_post=data.get("bench_post"),
        domain_pre=data.get("domain_pre"), domain_post=data.get("domain_post"),
    )
    result["meta"] = {
        "release_date": release_date.isoformat(),
        **data["meta"],
        "pipeline_notes": config.get("_pipeline_notes", []),
        "user_decisions": [],
        "extra_breakdowns": config.get("report", {}).get("extra_breakdowns", []),
        "input_summary": {
            "mode": df.attrs.get("ingestion_mode", "orchestrator_pre_enriched"),
            "url_count": len(df),
        },
    }

    logger.info("[%s] Stage 07 — report generator", run_id)
    html_path = generate(result, config, scratch_dir, run_id)

    # Verdict must be present — older upstream commits lack compute_verdict.
    if result.get("verdict") is None:
        raise RuntimeError(
            "Upstream impact_analysis missing 'verdict' — the cached seo-impact-plugin "
            "predates compute_verdict. Run `/plugin marketplace update <marketplace>` "
            "or purge ~/.claude/plugins/cache/<marketplace>/seo-impact-plugin/."
        )

    # Copy passthrough artifacts under stable filenames.
    safe_alt = alternate_name.replace("/", "_")
    passthrough_html = passthrough_dir / f"seo_{safe_alt}.html"
    passthrough_xlsx = passthrough_dir / f"seo_{safe_alt}.xlsx"
    passthrough_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(html_path, passthrough_html)
    xlsx_src = scratch_dir / f"seo_impact_report_{run_id}.xlsx"
    if xlsx_src.exists():
        shutil.copy2(xlsx_src, passthrough_xlsx)

    html_b64 = base64.b64encode(passthrough_html.read_bytes()).decode("ascii")

    out = {
        "status": "ok",
        "alternate_name": alternate_name,
        "verdict": result.get("verdict"),
        "did_coherence": result.get("did_coherence"),
        "signal_level": result.get("meta", {}).get("signal_level"),
        "did": result.get("did") or {},
        "power_analysis": result.get("power_analysis") or {},
        "overall": result.get("overall") or [],
        "summary_tables": result.get("summary_tables") or {},
        "by_category_l1": result.get("by_category_l1") or [],
        "by_category_l2": result.get("by_category_l2") or [],
        "by_category_l3": result.get("by_category_l3") or [],
        "by_page_type": result.get("by_page_type") or [],
        "caveats": result.get("caveats") or [],
        "upstream_html_b64": html_b64,
        "passthrough_html": f"passthrough/seo_{safe_alt}.html",
        "passthrough_xlsx": f"passthrough/seo_{safe_alt}.xlsx" if xlsx_src.exists() else None,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out), encoding="utf-8")
    logger.info("Wrote %s (status=%s, verdict=%s)", out_path, out["status"], out["verdict"])
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alternate-name", required=True)
    parser.add_argument("--variant-urls", required=True, type=Path)
    parser.add_argument("--release-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--passthrough-dir", required=True, type=Path)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    release_date = date.fromisoformat(args.release_date)
    try:
        run(
            alternate_name=args.alternate_name,
            variant_urls_path=args.variant_urls,
            release_date=release_date,
            out_path=args.out,
            passthrough_dir=args.passthrough_dir,
        )
    except Exception as exc:
        logger.exception("SEO pipeline failed")
        failed = {
            "status": "failed",
            "alternate_name": args.alternate_name,
            "reason": str(exc),
            "failed_at": "run_seo_pipeline",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(failed), encoding="utf-8")
        sys.exit(1)


if __name__ == "__main__":
    main()
