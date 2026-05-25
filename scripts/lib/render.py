"""Render combined HTML report + exec summary from per-experiment JSON intermediates.

Inputs (under <run_dir>/raw/):
  ab_<alt>.json:   AB evaluation output. Optionally includes:
                    - per_category (filtered)
                    - per_category_overall (population-wide per cat)
                    - overall_daily (daily M1/UV + CVR)
                    - srm_filtered_remediated, srm_overall_remediated (when SRM triggered remediation)
  seo_<alt>.json:  SEO eval output from `run-seo-evaluation` (thin shim over upstream
                    `seo-impact-plugin`). Required when status=ok:
                    - verdict (SHIP/PAUSE/EXTEND/REDESIGN/EARLY/INCONCLUSIVE)
                    - did (synthetic-control DiD: did_impressions_pct, did_clicks_pct, ...)
                    - power_analysis (p_value, current_power, mde_pp, ...)
                    - summary_tables (overall + by_category.{L1,L2,L3} paired Variant/All-Groupon rows)
                    - by_category_l1/l2/l3 (flat aggregations)
                    - upstream_html_b64 (base64 of upstream's self-contained HTML; iframed in SEO tab)
                    - passthrough_html / passthrough_xlsx (filenames inside passthrough/)
                    Note: url_details should NOT be embedded — full URL detail lives in the upstream XLSX.
  deal_<alt>.json: Deal-level output. Top winners/losers should ideally have
                    company_name + deal_title fields (enriched against deal_option).

Outputs:
  <run_dir>/combined_report.html — self-contained HTML with Chart.js, scoreboard
                                    (AB + SEO chips side-by-side), overview, merged 7-col
                                    per-cat heatmap (AB Filtered/Overall × M1/UV/CVR + SEO
                                    DiD impr/clicks/CTR), per-cat sub-tabs with daily charts,
                                    SEO tab embedding the upstream report via srcdoc iframe,
                                    deals tab with hyperlinked tables.
  <run_dir>/summary.md          — exec scoreboard markdown with per-experiment AB + SEO lines.

This module DOES NOT touch BigQuery. All enrichment must be done by upstream skills.
"""
from __future__ import annotations

import argparse
import base64 as _b64
import gzip as _gzip
import json
import math
from html import escape as h
from pathlib import Path
from statistics import mean, stdev

try:
    import docx as _docx  # python-docx — used to extract evaluator narrative from passthrough .docx
    _DOCX_AVAILABLE = True
except ImportError:
    _DOCX_AVAILABLE = False


# ---------- helpers ----------


def clean(obj):
    """Replace NaN/Inf with None recursively (so JSON.parse can consume the payload)."""
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _flatten_stats(stats):
    """Subagents historically nested stats under stats.treatment.{mean_delta,...} (legacy)
    or under stats.m1uv.{mean_delta,...} (current shape, keyed by primary metric). Flatten
    so callers can read mean_delta/p_value at top level without knowing the subagent shape.
    The original sub-dicts are preserved as siblings so `cvr` stays accessible.
    """
    if not isinstance(stats, dict):
        return stats
    if "mean_delta" in stats:
        return stats
    if isinstance(stats.get("treatment"), dict) and "mean_delta" in stats["treatment"]:
        return {**stats["treatment"]}
    primary = stats.get("m1uv")
    if isinstance(primary, dict) and "mean_delta" in primary:
        return {**stats, **primary}
    return stats


# ---------- SEO upstream-summary helpers ----------
#
# Upstream `seo-impact-plugin:seo-impact-analyzer` emits a `summary_tables`
# block with paired `Variant` / `All Groupon (...)` rows per L-value. Each
# Variant row also has `did_impr_pp` / `did_clicks_pp` stamped (variant Δ%
# minus paired-peer Δ%, in percentage points). The orchestrator does not
# stamp DiD CTR there — we derive it from the same paired rows below.
#
# AB-side L2 abbreviations → upstream's full L2 names. AB heatmap rows are
# labelled with abbreviations like "TTD" / "HBW" while upstream emits the
# full names "Things to Do" / "Beauty & Spas". Without this map, `_merge_
# categories` would surface duplicate rows and `_seo_l2_row_lookup` would
# miss the match. Mirrors render_app.js::_L2_ALIASES — keep both in sync.
_L2_ALIASES = {
    "TTD": "Things to Do",
    "HBW": "Beauty & Spas",
}


def _l2_candidates(name):
    """Return the lowercase set of L2 names to try matching for `name`
    (the original plus any alias from `_L2_ALIASES`)."""
    out = set()
    if not isinstance(name, str):
        return out
    original = name.strip()
    if not original:
        return out
    out.add(original.lower())
    alias = _L2_ALIASES.get(original.upper())
    if isinstance(alias, str):
        out.add(alias.strip().lower())
    elif isinstance(alias, (list, tuple)):
        for a in alias:
            if isinstance(a, str):
                out.add(a.strip().lower())
    return out


def _ctr_change_pp(row):
    """Return CTR change in percentage points (post_ctr - pre_ctr) * 100, or None if unsafe."""
    if not isinstance(row, dict):
        return None
    pre_imp = row.get("pre_impressions") or 0
    post_imp = row.get("post_impressions") or 0
    pre_clk = row.get("pre_clicks") or 0
    post_clk = row.get("post_clicks") or 0
    if pre_imp <= 0 or post_imp <= 0:
        return None
    pre_ctr = pre_clk / pre_imp
    post_ctr = post_clk / post_imp
    return (post_ctr - pre_ctr) * 100.0


def _seo_overall_ctr_did_pp(summary_tables):
    """Derive overall CTR DiD pp from upstream `summary_tables.overall`.

    Pairs the `Variant` row with the `Whole Groupon (...)` row. Returns None when
    either row is missing or any denominator is zero.
    """
    if not isinstance(summary_tables, dict):
        return None
    rows = summary_tables.get("overall") or []
    variant = next((r for r in rows if str(r.get("label", "")).startswith("Variant")), None)
    whole = next(
        (r for r in rows if str(r.get("label", "")).startswith("Whole Groupon")),
        None,
    )
    if variant is None or whole is None:
        return None
    v_pp = _ctr_change_pp(variant)
    w_pp = _ctr_change_pp(whole)
    if v_pp is None or w_pp is None:
        return None
    return v_pp - w_pp


def _l2_label_suffix(label):
    """Extract the L2 portion of an upstream summary_tables label.

    Upstream labels look like:
      "Variant — L2: Beauty & Spas / Massages"
      "All Groupon — L2: Beauty & Spas / Massages"
    The L2 name is the last `/`-separated component of the suffix after `:`.
    Returns the suffix L2 string, or None if the label doesn't match.
    """
    if not isinstance(label, str):
        return None
    if ": " not in label:
        return None
    after_colon = label.split(": ", 1)[1].strip()
    if "/" in after_colon:
        return after_colon.rsplit("/", 1)[-1].strip()
    return after_colon


def _seo_l2_row_lookup(summary_tables, l2_name):
    """Find the upstream `Variant — L2: <…>/<l2_name>` row in summary_tables.by_category.L2.rows.

    Honors `_L2_ALIASES` so AB-side abbreviations (e.g. "TTD") match the
    upstream full name (e.g. "Things to Do"). Returns the variant-row dict
    (with did_impr_pp / did_clicks_pp / pre/post totals), or None.
    """
    if not isinstance(summary_tables, dict) or not isinstance(l2_name, str):
        return None
    by_cat = summary_tables.get("by_category") or {}
    l2_block = by_cat.get("L2") or {}
    if not l2_block.get("available"):
        return None
    targets = _l2_candidates(l2_name)
    if not targets:
        return None
    for row in l2_block.get("rows") or []:
        label = row.get("label") or ""
        if not label.startswith("Variant"):
            continue
        suffix = _l2_label_suffix(label)
        if suffix and suffix.strip().lower() in targets:
            return row
    return None


def _seo_l2_ctr_did_pp(summary_tables, l2_name):
    """Per-L2 CTR DiD pp: variant CTR change minus paired All-Groupon CTR change in same L2.

    Honors `_L2_ALIASES` for the variant/peer lookup. Returns None when no
    pair exists or denominators are zero.
    """
    if not isinstance(summary_tables, dict) or not isinstance(l2_name, str):
        return None
    by_cat = summary_tables.get("by_category") or {}
    l2_block = by_cat.get("L2") or {}
    if not l2_block.get("available"):
        return None
    targets = _l2_candidates(l2_name)
    if not targets:
        return None
    rows = l2_block.get("rows") or []
    variant = None
    peer = None
    for row in rows:
        label = row.get("label") or ""
        suffix = _l2_label_suffix(label)
        if not suffix or suffix.strip().lower() not in targets:
            continue
        if label.startswith("Variant"):
            variant = row
        elif label.startswith("All Groupon"):
            peer = row
    if variant is None or peer is None:
        return None
    v_pp = _ctr_change_pp(variant)
    p_pp = _ctr_change_pp(peer)
    if v_pp is None or p_pp is None:
        return None
    return v_pp - p_pp


# ---------- variant naming convention ----------
#
# Canonical control mapping (see run-ab-evaluation/SKILL.md):
#   {"control", "treatment"} → "control" is ctrl
#   {"true", "false"}        → "true" is ctrl, "false" is treat (per stakeholder convention)
#   anything else            → keep the subagent's assignment
#
# The renderer will swap *_ctrl ↔ *_treat in daily rows + stats (and per_category /
# deal sibling) when a JSON was emitted with the labels reversed.


def _resolve_canonical_ctrl(ctrl_name, treat_name):
    """Return the canonical control variant name for this pair, or None if convention
    doesn't apply (caller keeps current assignment)."""
    if ctrl_name is None or treat_name is None:
        return None
    pair_lower = {str(ctrl_name).strip().lower(), str(treat_name).strip().lower()}
    if pair_lower == {"control", "treatment"}:
        return ctrl_name if str(ctrl_name).strip().lower() == "control" else treat_name
    if pair_lower == {"true", "false"}:
        return ctrl_name if str(ctrl_name).strip().lower() == "true" else treat_name
    if "control" in pair_lower:
        return ctrl_name if str(ctrl_name).strip().lower() == "control" else treat_name
    return None


def _swap_ctrl_treat_inplace(view):
    """Swap every *_ctrl ↔ *_treat field in daily rows and stats. Mutates view."""
    if not isinstance(view, dict):
        return
    for r in view.get("daily") or []:
        if not isinstance(r, dict):
            continue
        for ck in [k for k in list(r.keys()) if k.endswith("_ctrl") and (k[:-5] + "_treat") in r]:
            tk = ck[:-5] + "_treat"
            r[ck], r[tk] = r[tk], r[ck]
    stats = view.get("stats")
    if isinstance(stats, dict):
        for ck in [k for k in list(stats.keys()) if k.endswith("_ctrl") and (k[:-5] + "_treat") in stats]:
            tk = ck[:-5] + "_treat"
            stats[ck], stats[tk] = stats[tk], stats[ck]
        if "ctrl_name" in stats and "treat_name" in stats:
            stats["ctrl_name"], stats["treat_name"] = stats["treat_name"], stats["ctrl_name"]
        # Sub-dicts (m1uv, cvr) hold mean(treat-ctrl); flip the sign of signed fields.
        # mean_delta_pct is intentionally NOT touched here — build_payload() recomputes
        # it from the (now-swapped) daily totals via stats_for_daily(), which is the
        # canonical aggregate ratio. Mutating it here would either preserve a stale
        # daily-mean pct or compete with the recompute pass.
        for sub_key in ("m1uv", "cvr"):
            sub = stats.get(sub_key)
            if isinstance(sub, dict):
                for nk in ("mean_delta", "t_stat", "cohens_d"):
                    if nk in sub and isinstance(sub[nk], (int, float)):
                        sub[nk] = -sub[nk]


def _apply_variant_convention(ab):
    """If raw / remediated / per_category views use a non-canonical ctrl/treat assignment,
    swap so downstream consumers (renderer, summary) see the canonical orientation.
    Returns the canonical control name (or None) for use by adapt_deal."""
    canonical_ctrl = None
    raw = ab.get("raw") or {}
    rem = ab.get("remediated") or {}
    sources = []
    for view_key in ("filtered", "overall"):
        sources.append(raw.get(view_key))
        sources.append(rem.get(view_key))
    for cat_block_key in ("per_category", "per_category_overall"):
        for view in (ab.get(cat_block_key) or {}).values():
            sources.append(view)
    for view in sources:
        if not isinstance(view, dict):
            continue
        stats = view.get("stats") or {}
        ctrl_name = stats.get("ctrl_name")
        treat_name = stats.get("treat_name")
        target_ctrl = _resolve_canonical_ctrl(ctrl_name, treat_name)
        if target_ctrl is None:
            continue
        if canonical_ctrl is None:
            canonical_ctrl = target_ctrl
        if str(ctrl_name) != str(target_ctrl):
            _swap_ctrl_treat_inplace(view)
    return canonical_ctrl


_DOCX_SECTION_PATTERNS = [
    # (section_id, regex matching the top-level paragraph that opens the section).
    # Order matters — first match wins. Patterns are case-insensitive and anchored.
    ("step_1_srm",                  r"^step\s*1\b"),
    ("step_2_overall_results",      r"^step\s*2\b"),
    ("step_3_platform_results",     r"^step\s*3\b"),
    ("step_4_stability",            r"^step\s*4\b"),
    ("step_5_significance",         r"^step\s*5\b"),
    ("step_6_power",                r"^step\s*6\b"),
    ("step_7_practical",            r"^step\s*7"),
    ("step_8_mechanism",            r"^step\s*8\b"),
    ("step_9_business_impact",      r"^step\s*9\b"),
    ("executive_summary",           r"^executive\s+summary\b"),
    ("final_recommendation",        r"^final\s+recommendation\b"),
    ("what_the_data_shows",         r"^what\s+the\s+data\s+shows"),
    ("what_remains_uncertain",      r"^what\s+remains\s+uncertain"),
    ("action_items",                r"^action\s+items"),
    # Sentinel sections we want to detect but NOT keep — they end the previous section.
    ("__discard_notes",             r"^notes\s*(?:&|and)\s*data\s+quality"),
    ("__discard_metric_defs",       r"^metric\s+definitions"),
    ("__discard_context",           r"^experiment\s+context"),
]


def _extract_docx_narrative(docx_path):
    """Extract the evaluator-written narrative from an AB passthrough .docx.

    The AB-evaluation skill emits a Word document under <run>/passthrough/<alt>.docx whose
    structure is uniform: top-level "Step N — ..." headings + named summary headings
    ("Executive Summary", "Final Recommendation", "What the data shows", "What remains
    uncertain", "Action items") with body paragraphs and `List Paragraph`-styled bullets
    underneath each.

    Returns a dict mapping section_id → list of {text, is_bullet} items (or empty dict on
    failure). The renderer picks high-value sections (step_7, step_8, final_recommendation,
    what_the_data_shows, etc.) for the Overview rationale.

    Why per-Step capture: some experiments (AI_Summaries here) have rich verdict prose
    inside Step 7 / Step 8 paragraphs but no separate "What the data shows" subsection.
    Falling back to per-Step capture means we always have *something* to surface, instead
    of dropping back to my synthesized rationale.
    """
    if not _DOCX_AVAILABLE:
        return {}
    try:
        p = Path(docx_path)
        if not p.exists():
            return {}
        d = _docx.Document(str(p))
    except Exception:
        return {}

    import re as _re
    compiled = [(sid, _re.compile(pat, _re.I)) for sid, pat in _DOCX_SECTION_PATTERNS]
    sections = {}
    current = None
    for para in d.paragraphs:
        text = (para.text or "").strip()
        if not text:
            continue
        # Skip outright the document title / experiment id / test-period header.
        low = text.lower()
        if low.startswith("a/b") or low.startswith("test period:"):
            continue
        # Detect section starts.
        matched = None
        for sid, rx in compiled:
            if rx.match(text):
                matched = sid
                break
        if matched:
            current = None if matched.startswith("__discard") else matched
            continue
        if current is None:
            continue
        is_bullet = bool(para.style and "list" in (para.style.name or "").lower())
        sections.setdefault(current, []).append({"text": text, "is_bullet": is_bullet})

    return {k: v for k, v in sections.items() if v}


def _gzip_b64_html(b64_html):
    """Take a base64-encoded HTML blob, decode it, gzip-compress, and re-base64-encode.

    Used to embed upstream SEO reports in the combined HTML at ~3-4% of the original
    base64 size (gzip is highly effective on HTML/CSS/JS). The browser-side renderer
    decompresses via DecompressionStream('gzip') before iframe srcdoc-ing the result.

    Returns the gzipped+base64 string, or None when the input is falsy / undecodable.
    Compresslevel 9 is used (decompression speed in JS is the same regardless of level).
    """
    if not b64_html:
        return None
    try:
        raw = _b64.b64decode(b64_html)
    except (ValueError, TypeError):
        return None
    gz = _gzip.compress(raw, compresslevel=9)
    return _b64.b64encode(gz).decode("ascii")


def _backfill_remediated_srm(rv):
    """Compute SRM on a remediated view when the subagent didn't emit one. Subagents
    historically emit `remediated.<view>.srm` only when they ran an explicit SRM check on
    the active-visitor cohort; many runs skip that step but DO emit `variants.{ctrl,treat}.total_uv`
    (the per-arm visitor counts that survived the active_visitor_flag='Y' filter). When
    that's the case we can compute the SRM ourselves under the same 50/50 assumption used
    upstream (chi-square one-df, α=0.001 — `srm-chi-square` skill canon).

    Mutates `rv` in place by setting `rv['srm']`. No-op when the SRM is already present or
    when variant counts aren't available.
    """
    if not isinstance(rv, dict):
        return
    if isinstance(rv.get("srm"), dict) and rv["srm"].get("verdict"):
        return  # subagent already emitted it
    variants = rv.get("variants")
    # Subagent contract per run-ab-evaluation/SKILL.md emits variants as a list of
    # {name, role, uv, udv, m1, orders, bcookies} dicts. Older shapes used a dict
    # {ctrl:{...}, treat:{...}} keyed by role. Normalize either shape into ctrl/treat
    # arm dicts before reading the visitor count.
    ctrl = treat = None
    if isinstance(variants, dict):
        ctrl = variants.get("ctrl") or {}
        treat = variants.get("treat") or {}
    elif isinstance(variants, list):
        for v in variants:
            if not isinstance(v, dict):
                continue
            role = str(v.get("role") or v.get("name") or "").lower()
            if role in ("ctrl", "control"):
                ctrl = v
            elif role in ("treat", "treatment"):
                treat = v
        ctrl = ctrl or {}
        treat = treat or {}
    else:
        return
    # Accept the documented `total_uv` key first; fall back to the SKILL-schema list
    # keys (`bcookies` is the canonical SRM denominator — distinct visitors per arm —
    # and `uv` is the session-level count used by some legacy emitters).
    def _arm_count(arm):
        for key in ("total_uv", "bcookies", "uv", "n"):
            val = arm.get(key)
            if val is not None:
                return val
        return None
    n_ctrl = _arm_count(ctrl)
    n_treat = _arm_count(treat)
    if n_ctrl is None or n_treat is None:
        return
    try:
        n_ctrl_f = float(n_ctrl)
        n_treat_f = float(n_treat)
    except (TypeError, ValueError):
        return
    n_total = n_ctrl_f + n_treat_f
    if n_total <= 0:
        return
    expected = n_total / 2.0
    chi_sq = ((n_ctrl_f - expected) ** 2) / expected + ((n_treat_f - expected) ** 2) / expected
    # χ² survival for one degree of freedom: P(χ² > x) = erfc(sqrt(x/2)). Avoids a scipy
    # dependency in the renderer (matches how `scripts.lib.stats.srm_chi_square` does it).
    p_value = math.erfc(math.sqrt(chi_sq / 2.0))
    alpha = 0.001
    verdict = "pass" if p_value >= alpha else "fail"
    rv["srm"] = {
        "chi_sq": chi_sq,
        "df": 1,
        "p_value": p_value,
        "alpha": alpha,
        "verdict": verdict,
        "observed": {
            ctrl.get("name") or "control": n_ctrl_f,
            treat.get("name") or "treatment": n_treat_f,
        },
        "expected_n": {
            ctrl.get("name") or "control": expected,
            treat.get("name") or "treatment": expected,
        },
        "computed_by": "renderer_backfill",
    }


def _promote_remediated_when_srm_fails(ab):
    """When raw SRM fails AND remediated SRM passes, promote the remediated view to be the
    primary `raw` view so the scoreboard, headline KPIs, and per-experiment HTML tab all
    use the active-visitor numbers (which are the analytically defensible ones once SRM
    contamination is removed). The original raw view is preserved under raw_pre_remediation,
    and the full original SRM dict is preserved under srm[view].original so the renderer
    can show 'raw failed → active_visitor passes' rather than just 'pass'."""
    srm_top = ab.get("srm") or {}
    raw = ab.get("raw") or {}
    rem = ab.get("remediated") or {}
    for view_key in ("filtered", "overall"):
        srm_view = srm_top.get(view_key) or {}
        if str(srm_view.get("verdict") or "").lower() != "fail":
            continue
        rv = rem.get(view_key) or {}
        # Subagents that skipped the explicit SRM step on the remediated cohort still
        # emit variant UV totals — backfill the SRM here so the promotion logic below
        # can pick it up. Without this, raw-fail experiments with a clean remediated
        # cohort surface as "INCONCLUSIVE — persistent SRM" with no remediation
        # context, which is misleading.
        _backfill_remediated_srm(rv)
        rv_srm = rv.get("srm") or {}
        if str(rv_srm.get("verdict") or "").lower() != "pass":
            continue
        ab.setdefault("raw_pre_remediation", {})[view_key] = raw.get(view_key)
        replaced = dict(rv)
        replaced["remediation_applied"] = True
        replaced["remediation_filter"] = "active_visitor_flag='Y'"
        raw[view_key] = replaced
        promoted_srm = dict(rv_srm)
        promoted_srm["original"] = {
            "verdict": srm_view.get("verdict"),
            "chi_sq": srm_view.get("chi_sq"),
            "p_value": srm_view.get("p_value"),
            "observed": srm_view.get("observed"),
            "expected_n": srm_view.get("expected_n"),
        }
        promoted_srm["promoted_from"] = "remediated"
        srm_top[view_key] = promoted_srm
    ab["raw"] = raw
    ab["srm"] = srm_top


def _compute_runway(stats, n_current):
    """Estimate additional days needed to lift the observed effect to p<0.05.

    Uses the t-statistic scaling rule for paired-t: keeping the effect size constant,
    t scales as sqrt(n), so n_required ≈ n_current * (1.96 / |t|)² for the standard
    α=0.05 two-sided threshold. This is a back-of-envelope projection — it assumes
    the observed effect is the true effect, which is shaky at small n. Used as a
    'how much longer would you have to run' heuristic, not an authoritative power
    analysis.

    Returns None when there's nothing useful to say (already significant, no t_stat,
    or projected runway is impractical at the observed effect size).
    """
    if not isinstance(stats, dict) or not n_current:
        return None
    p = stats.get("p_value")
    t = stats.get("t_stat")
    if p is None or t is None:
        return None
    try:
        p_f, t_f, n_f = float(p), float(t), float(n_current)
    except (TypeError, ValueError):
        return None
    if p_f < 0.05:
        return {"already_significant": True, "n_current": int(n_f), "current_p": p_f}
    if abs(t_f) < 0.3:
        return {
            "infeasible": True,
            "n_current": int(n_f),
            "current_p": p_f,
            "current_t": t_f,
            "reason": "observed effect too flat to project a meaningful runway",
        }
    scale = (1.96 / abs(t_f)) ** 2
    n_required = max(int(round(n_f * scale)), int(n_f) + 1)
    additional = n_required - int(n_f)
    if additional > 365:
        return {
            "infeasible": True,
            "n_current": int(n_f),
            "current_p": p_f,
            "current_t": t_f,
            "n_projected": n_required,
            "additional_days": additional,
            "reason": "projected runway > 1 year — effectively infeasible",
        }
    return {
        "n_current": int(n_f),
        "n_required": n_required,
        "additional_days": additional,
        "current_p": p_f,
        "current_t": t_f,
        "current_d": stats.get("cohens_d"),
    }


def paired_t_p(diffs):
    """Two-sided p-value from a paired-t test on a daily delta series."""
    n = len(diffs)
    if n < 2:
        return (0.0, 1.0)
    m = mean(diffs)
    sd = stdev(diffs)
    if sd == 0:
        return (m, 1.0)
    t = m / (sd / math.sqrt(n))
    z = abs(t)
    try:  # Prefer scipy when available for the proper Student-t survival.
        from scipy.stats import t as t_dist
        p = 2 * (1 - t_dist.cdf(z, df=n - 1))
    except Exception:  # noqa: BLE001 — fall back to normal approx.
        p = math.erfc(z / math.sqrt(2))
    return (m, p)


def stats_for_daily(daily, metric, num_field=None, den_field=None):
    """Aggregate-ratio %Δ (ab-experiments canon: SUM(num)/SUM(den)) for the point estimate;
    paired t-test on daily ratios for the p-value (also canon: 'paired t-test on daily data
    > t-test on aggregated totals').

    metric is the daily ratio key ('m1uv', 'cvr'). num_field/den_field are the underlying
    total fields (e.g. 'm1','uv' or 'orders','udv'). Inferred from `metric` if omitted.

    Daily rows MUST include the underlying totals; without them the aggregate ratio cannot
    be computed and this function returns None. Daily-mean-based percentages are not
    produced — silently falling back to a daily-mean pct diverges from Groupon dashboards
    by ~0.1-0.2pp when daily UV/UDV varies, so the contract is enforced strictly.

    Per-day ratio keys (`<metric>_ctrl`/`<metric>_treat`) are preferred for the paired
    t-test diffs, but when a subagent emits only the raw totals the ratios are derived
    on the fly from `<num>_ctrl/<den>_ctrl` so the renderer doesn't go n/a for an AB
    JSON that includes the math inputs but not the pre-divided values.
    """
    if num_field is None or den_field is None:
        if metric == "m1uv":
            num_field, den_field = "m1", "uv"
        elif metric == "cvr":
            num_field, den_field = "orders", "udv"
        else:
            num_field, den_field = metric, "uv"

    def _ratio(r, side):
        explicit = r.get(f"{metric}_{side}")
        if explicit is not None:
            return explicit
        num = r.get(f"{num_field}_{side}")
        den = r.get(f"{den_field}_{side}")
        if num is None or den in (None, 0):
            return None
        return float(num) / float(den)

    diffs = []
    for r in daily or []:
        ct = _ratio(r, "ctrl")
        tt = _ratio(r, "treat")
        if ct is None or tt is None:
            continue
        diffs.append(tt - ct)
    if not diffs:
        return None
    has_totals = any(f"{num_field}_ctrl" in r for r in daily)
    if not has_totals:
        return None  # contract violation: subagent emitted ratios but no totals
    md, p = paired_t_p(diffs)
    sum_num_c = sum(float(r.get(f"{num_field}_ctrl") or 0) for r in daily)
    sum_den_c = sum(float(r.get(f"{den_field}_ctrl") or 0) for r in daily)
    sum_num_t = sum(float(r.get(f"{num_field}_treat") or 0) for r in daily)
    sum_den_t = sum(float(r.get(f"{den_field}_treat") or 0) for r in daily)
    agg_c = (sum_num_c / sum_den_c) if sum_den_c else 0
    agg_t = (sum_num_t / sum_den_t) if sum_den_t else 0
    agg_delta = agg_t - agg_c
    agg_pct = ((agg_t / agg_c) - 1) * 100 if agg_c else 0
    return {
        "mean_delta": md,
        "mean_delta_pct": agg_pct,
        "agg_ctrl": agg_c,
        "agg_treat": agg_t,
        "agg_delta": agg_delta,
        "p_value": p,
        "n": len(diffs),
    }


def _recompute_view_metrics(view, ratio_keys=("m1uv", "cvr")):
    """Recompute m1uv / cvr stats blocks on `view` from the view's `daily` totals using
    `stats_for_daily()` so every displayed %Δ is the canonical aggregate ratio
    SUM(num)/SUM(den). Mutates the view in place.

    Looks up the existing block at both top-level (`view[m1uv]`) and nested
    (`view['stats'][m1uv]`) and replaces it. Preserves any extra fields (e.g. `cohens_d`)
    from the original block; only the percentage-bearing fields are overwritten.

    Subagents historically emitted daily-mean-based mean_delta_pct alongside totals; this
    function unconditionally overrides that pct with the aggregate ratio. Subagent JSON
    that omits totals leaves the original block untouched (the renderer will treat the
    result as missing rather than show a daily-mean number).
    """
    if not isinstance(view, dict):
        return
    daily = view.get("daily") or []
    if not daily:
        return
    for metric in ratio_keys:
        recomputed = stats_for_daily(daily, metric)
        if recomputed is None:
            continue
        # Top-level (per_category[*] shape).
        if isinstance(view.get(metric), dict):
            view[metric] = {**view[metric], **recomputed}
        elif metric in view:
            view[metric] = recomputed
        # Nested under stats (raw.filtered / raw.overall shape).
        stats = view.get("stats")
        if isinstance(stats, dict) and isinstance(stats.get(metric), dict):
            stats[metric] = {**stats[metric], **recomputed}


def adapt_ab(ab):
    """Normalize AB JSON shape so the renderer can read it without knowing the subagent's
    output conventions. Pipeline:
      1. Apply canonical variant convention (swap *_ctrl/*_treat if reversed).
      2. When raw SRM failed and remediated passed, promote remediated → raw so the
         headline numbers reflect the active-visitor-cleaned data.
      3. Flatten nested stats (m1uv / treatment) to top level.
      4. Normalize legacy daily shape (uv_control/m1_control → ctrl/treat ratio).
    Returns the (mutated) ab plus stashes the canonical control name on the object so
    sibling deal JSON can be aligned without re-reading the source.
    """
    if not ab:
        return ab
    canonical_ctrl = _apply_variant_convention(ab)
    if canonical_ctrl is not None:
        ab["_canonical_ctrl_name"] = canonical_ctrl
    _promote_remediated_when_srm_fails(ab)

    raw = ab.get("raw") or {}
    for view_key in ("filtered", "overall"):
        v = raw.get(view_key)
        if not v:
            continue
        v["stats"] = _flatten_stats(v.get("stats"))
        # Daily rows may be in three shapes:
        #   (a) {d, ctrl, treat}                                     — already-flat ratio shape
        #   (b) {event_date, m1_ctrl, uv_ctrl, m1uv_ctrl, ...}        — current subagent shape
        #   (c) {event_date, uv_control, m1_control, ...}             — legacy subagent shape
        # Only case (c) needs reshaping; (a) and (b) pass through so stats_for_daily can
        # consume them downstream.
        new_daily = []
        for d in v.get("daily") or []:
            if not isinstance(d, dict):
                continue
            if "uv_control" in d or "m1_control" in d:
                uvc = float(d.get("uv_control") or 0)
                uvt = float(d.get("uv_treatment") or 0)
                m1c = float(d.get("m1_control") or 0)
                m1t = float(d.get("m1_treatment") or 0)
                new_daily.append({
                    "d": d.get("event_date") or d.get("d"),
                    "ctrl": (m1c / uvc) if uvc else 0,
                    "treat": (m1t / uvt) if uvt else 0,
                })
            else:
                new_daily.append(d)
        if new_daily:
            v["daily"] = new_daily

    rem = ab.get("remediated") or {}
    if rem:
        for view_key in ("filtered", "overall"):
            v = rem.get(view_key)
            if v:
                v["stats"] = _flatten_stats(v.get("stats"))
    return ab


def adapt_deal(deal, canonical_ctrl):
    """Align deal JSON with the canonical control name. The deal subagent pivots ctrl/treat
    using whatever variant order it sees in the data; if that disagrees with the canonical
    convention, swap *_ctrl ↔ *_treat across by_category, by_booking_platform, top_winners,
    and top_losers. Note: top_winners/top_losers ranking comes from BQ — for old runs where
    bq_queries.deal_top_winners_losers was hardcoded to variantname='control', the rankings
    are wrong (m1_ctrl=0 for all rows) and re-running the query is the only proper fix.
    """
    if not isinstance(deal, dict) or canonical_ctrl is None:
        return deal
    embedded_ctrl = deal.get("ctrl_name")
    if embedded_ctrl is not None and str(embedded_ctrl) == str(canonical_ctrl):
        return deal
    for arr_key in ("by_category", "top_winners", "top_losers"):
        for r in deal.get(arr_key) or []:
            if not isinstance(r, dict):
                continue
            for ck in [k for k in list(r.keys()) if k.endswith("_ctrl") and (k[:-5] + "_treat") in r]:
                tk = ck[:-5] + "_treat"
                r[ck], r[tk] = r[tk], r[ck]
            # Recompute deltas where present so the renderer's hyperlinked tables show the
            # correct sign without re-running BQ.
            if "m1_ctrl" in r and "m1_treat" in r and "m1_delta" in r:
                r["m1_delta"] = (r.get("m1_treat") or 0) - (r.get("m1_ctrl") or 0)
            if "cvr_ctrl" in r and "cvr_treat" in r and "cvr_delta" in r:
                r["cvr_delta"] = (r.get("cvr_treat") or 0) - (r.get("cvr_ctrl") or 0)
    deal["ctrl_name"] = canonical_ctrl
    return deal


# ---------- data loading + payload assembly ----------


def load_run(run_dir: Path):
    raw = run_dir / "raw"
    experiments = {}
    for p in sorted(raw.glob("ab_*.json")):
        name = p.stem[len("ab_"):]
        ab = adapt_ab(json.loads(p.read_text(encoding="utf-8")))
        # Pull the evaluator-written narrative from the passthrough .docx.
        # Preferred: AB JSON's explicit `passthrough_docx` path.
        # Fallback: scan <run_dir>/passthrough/ for a docx whose stem matches the
        # alternate_name. This covers the common case where the AB subagent's c3
        # passthrough succeeded (docx exists on disk) but the JSON wasn't updated
        # with the path — previously the narrative silently dropped to synthesized.
        docx_path = (ab or {}).get("passthrough_docx")
        if not docx_path:
            alt = (ab or {}).get("alternate_name") or name
            passthrough_dir = run_dir / "passthrough"
            if passthrough_dir.is_dir():
                candidates = [
                    passthrough_dir / f"{alt}.docx",
                    passthrough_dir / f"{name}.docx",
                ]
                for cand in candidates:
                    if cand.is_file():
                        docx_path = str(cand)
                        break
        if docx_path:
            narrative = _extract_docx_narrative(docx_path)
            if narrative:
                ab["evaluation_narrative"] = narrative
                ab["passthrough_docx"] = docx_path
        experiments[name] = {"ab": ab}
    # Only pick up filenames that match `seo_<safe_alt>.json` for known experiments.
    # Skip intermediate files like seo_did_l2.json that orchestrator may write alongside.
    known_names = set(experiments.keys())
    for p in sorted(raw.glob("seo_*.json")):
        name = p.stem[len("seo_"):]
        if known_names and name not in known_names:
            continue
        try:
            seo = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(seo, dict):
            continue
        # Strip any embedded per_url to keep payload small.
        seo.pop("per_url", None)
        experiments.setdefault(name, {})["seo"] = seo
    for p in sorted(raw.glob("deal_*.json")):
        name = p.stem[len("deal_"):]
        if known_names and name not in known_names:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(d, dict):
            continue
        canonical_ctrl = (experiments.get(name) or {}).get("ab", {}).get("_canonical_ctrl_name")
        adapt_deal(d, canonical_ctrl)
        d.pop("by_booking_platform", None)  # no longer rendered; drop to keep HTML payload lean
        experiments.setdefault(name, {})["deal"] = d
    # urls_<alt>.json — produced by resolve-deal-urls. List of enriched deal records;
    # count = number of deals in the experiment's test_deals input. May also be a
    # status dict (e.g. {"status":"no_deals"}) when the experiment has no test_deals rows.
    for p in sorted(raw.glob("urls_*.json")):
        name = p.stem[len("urls_"):]
        if known_names and name not in known_names:
            continue
        try:
            urls = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(urls, list):
            experiments.setdefault(name, {})["n_deals"] = 0
            experiments[name]["deals_per_l2"] = {}
            continue
        # Bucket deals by web_category_level_2 (full-name L2), unique by deal_uuid.
        # Used by the renderer to show a per-row deal count under each heatmap label.
        per_l2 = {}
        seen = set()
        for r in urls:
            if not isinstance(r, dict):
                continue
            uuid = r.get("deal_uuid")
            if uuid in seen:
                continue
            seen.add(uuid)
            l2 = r.get("web_category_level_2")
            if isinstance(l2, str) and l2.strip():
                per_l2[l2] = per_l2.get(l2, 0) + 1
        experiments.setdefault(name, {})["n_deals"] = len(urls)
        experiments[name]["deals_per_l2"] = per_l2
    # Merge queue metadata (evaluate_seo_since, is_in_flight, seo_eligible) from
    # the orchestrator's queue.json so the renderer can compute the SEO TOO EARLY
    # countdown ("X/14 days needed") and flag results as PRELIMINARY when the
    # SEO release is still inside the 14-day pre-eligibility window. The queue
    # field is the single source of truth; subagent JSONs don't carry it.
    #
    # Canonical location is `<run_dir>/queue.json`. We also probe `<run_dir>/raw/queue.json`
    # as a fallback because orchestrator-workflow Step 5 left the path unspecified and the
    # list-experiments skill emits to stdout — earlier runs piped it to raw/ alongside the
    # other artifacts, which silently broke SEO TOO EARLY detection on 2026-05-20. The
    # fallback keeps reruns of those run directories working; new runs should write to the
    # top-level path.
    queue_path = run_dir / "queue.json"
    if not queue_path.is_file():
        alt_queue_path = run_dir / "raw" / "queue.json"
        if alt_queue_path.is_file():
            queue_path = alt_queue_path
    if queue_path.is_file():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            queue = []
        if isinstance(queue, list):
            # Build a lookup keyed by both the safe-filename form and the raw
            # alternate_name so we hit regardless of how the orchestrator slugged
            # the file paths.
            by_alt = {}
            for q in queue:
                if not isinstance(q, dict):
                    continue
                alt = q.get("alternate_name")
                if alt:
                    by_alt[alt] = q
            for name, exp in experiments.items():
                ab = exp.get("ab") or {}
                alt = ab.get("alternate_name") or name
                q = by_alt.get(alt)
                if not q:
                    continue
                exp["evaluate_seo_since"] = q.get("evaluate_seo_since")
                exp["is_in_flight"] = q.get("is_in_flight")
                exp["seo_eligible"] = q.get("seo_eligible")
    return experiments


def _merge_categories(ab, seo):
    """Order categories for the per-experiment heatmap.

    AB-defined categories come first (the experiment's own splits, from
    `per_category` or its overall counterpart). Any SEO L2 that the variant URL
    set touched but AB didn't split on is appended afterwards — extracted from
    upstream `summary_tables.by_category.L2.rows[]` Variant labels.

    Honors `_L2_ALIASES`: if the AB list contains an abbreviation (e.g. "TTD")
    whose alias matches an upstream L2 name (e.g. "Things to Do"), the upstream
    name is NOT appended as a separate row — the AB row will pull SEO data
    via the same alias mapping in `_seoL2VariantRow` / `_seo_l2_row_lookup`.
    """
    ab_cats = (
        list((ab.get("per_category") or {}).keys())
        or list((ab.get("per_category_overall") or {}).keys())
    )
    # Build a lowercase set of every L2 name the AB list already covers,
    # including aliases — so we don't append an upstream name that's the
    # full form of an AB abbreviation already in the list.
    ab_covered = set()
    for cat in ab_cats:
        ab_covered.update(_l2_candidates(cat))
    seo_cats = []
    summary_tables = (seo or {}).get("summary_tables") or {}
    l2_block = (summary_tables.get("by_category") or {}).get("L2") or {}
    if l2_block.get("available"):
        for row in l2_block.get("rows") or []:
            label = row.get("label") or ""
            if not label.startswith("Variant"):
                continue
            suffix = _l2_label_suffix(label)
            if not suffix:
                continue
            if suffix.strip().lower() in ab_covered:
                continue
            if suffix not in seo_cats:
                seo_cats.append(suffix)
    return list(dict.fromkeys(ab_cats + seo_cats))


# Defaults that shape the Final verdict. Tuned for Groupon-scale where:
#  * 0.5% margin/visitor is the minimum effect we'd commit deploy/maintenance cost to
#  * a 90% CI is the industry standard for product-decision CIs (vs 95% for academic
#    significance) — Microsoft / Booking experimentation literature
#  * SEO impressions at full signal is the leading indicator for long-term ranking
#    risk; the -10% threshold matches the SearchPilot/Optibase kill-switch convention
_DEFAULT_MWSE_PCT = 0.5
_DEFAULT_CI_ALPHA = 0.10
_GUARDRAIL_SEO_IMP_PCT_FULL_SIGNAL = -10.0
_GUARDRAIL_CVR_NEG_PCT = -1.0
_GUARDRAIL_CVR_P_THRESH = 0.05
# Directional KILL guardrail: when BOTH M1+VFM/UV and CVR are meaningfully negative
# at the same time, KILL regardless of p-values or composed CI. Rationale: with two
# correlated metrics both pointing materially negative, the probability the true
# effect is non-negative is small even when individual p-values look high (small-
# sample noise inflates p). Thresholds are 2x the noise floor on each metric so a
# true-zero experiment has a low chance of tripping both simultaneously. Catches
# the "high-variance, all-signals-negative" case that the CI rule misses because
# the CI is wide enough to straddle zero.
_GUARDRAIL_DIRECTIONAL_M1UV_PCT = -1.0
_GUARDRAIL_DIRECTIONAL_CVR_PCT = -2.0


def _label_matrix_fallback(ab_verdict, seo_status, seo_verdict):
    """Original 4×4 label matrix — used only when the composed funnel CI can't be
    constructed (e.g. AB SE unrecoverable, SEO MISSING). Preserves prior behavior
    so older runs and degenerate cases still produce a sensible verdict.
    """
    ab = (ab_verdict or "").upper()
    if ab not in ("SHIP", "HOLD", "KILL"):
        ab = "INCONCLUSIVE"
    seo_v = (seo_verdict or "").upper()
    if seo_status != "ok":
        seo_cat = "MISSING"
    elif seo_v in ("POSITIVE", "SHIP"):
        seo_cat = "WIN"
    elif seo_v in ("PAUSE", "NEGATIVE", "REDESIGN"):
        seo_cat = "HARM"
    else:
        seo_cat = "UNCLEAR"
    if ab == "KILL":
        return "KILL"
    if ab == "SHIP":
        if seo_cat == "HARM":
            return "KILL"
        if seo_cat in ("WIN", "MISSING"):
            return "DEPLOY"
        return "HOLD"
    return "KILL" if seo_cat == "HARM" else "HOLD"


def _fmt_pct(v, sign=True):
    if v is None:
        return "n/a"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "n/a"
    return f"{fv:+.2f}%" if sign else f"{fv:.2f}%"


def _fmt_p(v):
    if v is None:
        return "n/a"
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "n/a"
    return "<0.001" if fv < 0.001 else f"{fv:.3f}"


def _compose_final_verdict(signals, mwse_pct=_DEFAULT_MWSE_PCT, ci_alpha=_DEFAULT_CI_ALPHA):
    """Compose AB + SEO signals into a DEPLOY / HOLD / KILL verdict + rationale.

    `signals` keys (all optional, None when missing):
      ab_verdict          str — SHIP/HOLD/KILL/INCONCLUSIVE
      m1uv_pct, m1uv_se, m1uv_p, m1uv_t, m1uv_n
      cvr_pct,  cvr_se,  cvr_p,  cvr_t,  cvr_n
      seo_status          'ok'/'no_urls'/'failed'/None
      seo_verdict         upstream verdict label
      seo_signal_strength 'full'/'partial'/None
      did_imp_pct, did_clicks_pct, did_clicks_p
      srm_verdict         'pass'/'fail' (post-remediation; persistent fail → no CI)
      srm_promoted_from   'remediated' / None
      ab_label            renderer-computed AB label (used to detect INCONCLUSIVE)

    Decision order — strictly hierarchical:

      1. Hard guardrails (KILL on trip, independent of composed CI):
         a. AB CVR significantly negative (p<0.05 AND mean_delta_pct <= -1%)
         b. Full-signal SEO impressions DiD <= -10%
      2. Data-quality short-circuit:
         a. SRM persistent fail (`srm_verdict == 'fail'` after promotion) → label-matrix
      3. Composed funnel 90% CI rule (when both SEs available):
         a. lower > +MWSE → DEPLOY
         b. upper < -MWSE → KILL
         c. otherwise → HOLD
      4. Fallback to label matrix when CI can't be constructed.

    Returns a dict with: verdict, rationale, cls, basis ('guardrail'/'ci'/'matrix'),
    plus the composed CI fields so the renderer can show the [lower, upper] band.
    """
    from scripts.lib.stats import compose_funnel_ci, recover_se_from_p

    # Extract signals (defensive defaults)
    s = signals or {}
    ab_verdict = s.get("ab_verdict")
    m1uv_pct = s.get("m1uv_pct")
    m1uv_p = s.get("m1uv_p")
    m1uv_t = s.get("m1uv_t")
    cvr_pct = s.get("cvr_pct")
    cvr_p = s.get("cvr_p")
    seo_status = s.get("seo_status")
    seo_verdict = s.get("seo_verdict")
    seo_signal = s.get("seo_signal_strength")
    did_imp_pct = s.get("did_imp_pct")
    did_clicks_pct = s.get("did_clicks_pct")
    did_clicks_p = s.get("did_clicks_p")
    srm_verdict = (s.get("srm_verdict") or "").lower()

    # --- 1. Hard guardrails ----------------------------------------------------
    guardrail_trip = None
    if (cvr_pct is not None and cvr_p is not None
            and cvr_pct <= _GUARDRAIL_CVR_NEG_PCT
            and cvr_p < _GUARDRAIL_CVR_P_THRESH):
        guardrail_trip = (
            f"AB CVR significantly negative (CVR {_fmt_pct(cvr_pct)}, p={_fmt_p(cvr_p)}); "
            f"floor is {_GUARDRAIL_CVR_NEG_PCT:.1f}% at p<{_GUARDRAIL_CVR_P_THRESH}."
        )
    if (guardrail_trip is None and seo_status == "ok"
            and seo_signal == "full"
            and did_imp_pct is not None
            and did_imp_pct <= _GUARDRAIL_SEO_IMP_PCT_FULL_SIGNAL):
        guardrail_trip = (
            f"SEO impressions DiD {_fmt_pct(did_imp_pct)} at full signal trips the "
            f"organic-ranking-risk floor of {_GUARDRAIL_SEO_IMP_PCT_FULL_SIGNAL:.0f}%."
        )
    # Directional KILL: M1+VFM/UV AND CVR both meaningfully negative. Doesn't
    # require statistical significance because the joint occurrence is itself
    # the signal — small-sample noise rarely flips both metrics negative past
    # their respective noise floors at the same time. Catches the
    # "very negative point estimate + wide CI that straddles zero" case where
    # the CI rule says HOLD but every visible indicator says ship-this-and-lose-money.
    if (guardrail_trip is None
            and m1uv_pct is not None
            and cvr_pct is not None
            and m1uv_pct <= _GUARDRAIL_DIRECTIONAL_M1UV_PCT
            and cvr_pct <= _GUARDRAIL_DIRECTIONAL_CVR_PCT):
        guardrail_trip = (
            f"Directional KILL — M1+VFM/UV {_fmt_pct(m1uv_pct)} AND CVR {_fmt_pct(cvr_pct)}; "
            f"both metrics past their negative noise floors ({_GUARDRAIL_DIRECTIONAL_M1UV_PCT:.1f}% / "
            f"{_GUARDRAIL_DIRECTIONAL_CVR_PCT:.1f}%). Joint negative direction makes a true-zero "
            f"effect implausible, so the wide CI doesn't rescue this from KILL."
        )

    # --- 2. Recover SEs --------------------------------------------------------
    # AB M1+VFM/UV SE — prefer explicit se, then back out from t_stat, then from p.
    m1uv_se = s.get("m1uv_se")
    if m1uv_se is None and m1uv_t is not None and m1uv_pct is not None:
        try:
            t = float(m1uv_t)
            if t != 0:
                m1uv_se = abs(float(m1uv_pct)) / abs(t)
        except (TypeError, ValueError):
            m1uv_se = None
    if m1uv_se is None:
        m1uv_se = recover_se_from_p(m1uv_pct, m1uv_p)
    # SEO clicks DiD SE — recover from upstream p-value (clamped) since the upstream
    # plugin doesn't surface an explicit SE on did_clicks_pct.
    clicks_se = s.get("clicks_se")
    if clicks_se is None and seo_status == "ok":
        clicks_se = recover_se_from_p(did_clicks_pct, did_clicks_p)

    # --- 3. SRM persistent fail short-circuit ----------------------------------
    srm_persistent_fail = (srm_verdict == "fail")

    # --- 4. Build composed CI --------------------------------------------------
    ci = compose_funnel_ci(
        m1uv_pct=m1uv_pct,
        m1uv_se_pct=m1uv_se,
        clicks_pct=did_clicks_pct if seo_status == "ok" else None,
        clicks_se_pct=clicks_se if seo_status == "ok" else None,
        alpha=ci_alpha,
    )

    # --- 5. Resolve verdict ----------------------------------------------------
    have_ci = bool(ci and ci.get("se") is not None and ci.get("lower") is not None)
    basis = "matrix"
    if guardrail_trip is not None:
        final = "KILL"
        basis = "guardrail"
    elif srm_persistent_fail:
        final = _label_matrix_fallback(ab_verdict, seo_status, seo_verdict)
        basis = "matrix"
    elif have_ci:
        if ci["lower"] > mwse_pct:
            final = "DEPLOY"
        elif ci["upper"] < -mwse_pct:
            final = "KILL"
        else:
            final = "HOLD"
        basis = "ci"
    else:
        final = _label_matrix_fallback(ab_verdict, seo_status, seo_verdict)
        basis = "matrix"

    # --- 6. Build rationale ----------------------------------------------------
    seo_v_str = (seo_verdict or "").upper() if seo_status == "ok" else None
    sig_str = ""
    if seo_signal == "full":
        sig_str = "full signal"
    elif seo_signal == "partial":
        sig_str = "partial signal"

    if basis == "ci":
        ci_band = f"[{_fmt_pct(ci['lower'])} to {_fmt_pct(ci['upper'])}]"
        ci_pct = int(round((1 - ci_alpha) * 100))
        if final == "DEPLOY":
            rationale = (
                f"Composed net margin/visitor {_fmt_pct(ci['point'])} with {ci_pct}% CI {ci_band} — "
                f"entirely above the +{mwse_pct:.1f}% minimum-worth-shipping threshold."
            )
        elif final == "KILL":
            rationale = (
                f"Composed net margin/visitor {_fmt_pct(ci['point'])} with {ci_pct}% CI {ci_band} — "
                f"entirely below the -{mwse_pct:.1f}% threshold."
            )
        else:
            rationale = (
                f"Composed net margin/visitor {_fmt_pct(ci['point'])} with {ci_pct}% CI {ci_band} — "
                f"straddles zero ±{mwse_pct:.1f}%, not enough evidence to decide."
            )
    elif basis == "guardrail":
        rationale = f"Guardrail tripped: {guardrail_trip}"
        if have_ci:
            rationale += (
                f" (Composed net margin/visitor would be {_fmt_pct(ci['point'])} — "
                f"guardrails veto regardless.)"
            )
    else:
        # Matrix fallback — preserve the old explanatory style so the user knows
        # why we couldn't use the CI rule.
        ab = (ab_verdict or "INCONCLUSIVE").upper()
        ab_part = f"AB {ab} (M1+VFM/UV {_fmt_pct(m1uv_pct)}, p={_fmt_p(m1uv_p)})"
        if seo_status == "ok":
            seo_part = (f"SEO {seo_v_str} (impressions DiD {_fmt_pct(did_imp_pct)}"
                        + (f", {sig_str}" if sig_str else "") + ")")
        else:
            seo_part = "SEO data unavailable"
        reason = "SRM persistent fail — composed CI not trusted" if srm_persistent_fail \
                 else "uncertainty bounds not recoverable from this run's data"
        rationale = f"{ab_part}; {seo_part}. Verdict from rule-based matrix ({reason})."

    cls = {"DEPLOY": "final-deploy", "HOLD": "final-hold", "KILL": "final-kill"}[final]
    return {
        "verdict": final,
        "rationale": rationale,
        "cls": cls,
        "basis": basis,
        "composed_point": ci["point"] if ci else None,
        "composed_se": ci["se"] if ci else None,
        "composed_lower": ci["lower"] if ci else None,
        "composed_upper": ci["upper"] if ci else None,
        "composed_alpha": ci["alpha"] if ci else ci_alpha,
        "mwse_pct": mwse_pct,
    }


def _seo_days_since_release(run_id, eval_seo_since, fallback_through=None):
    """Calendar days from the SEO release date to the run date.

    The SEO maturation clock counts wall-clock days since `evaluate_seo_since`,
    NOT days inside the AB data window. `data_through` is pinned to the experiment
    `end_date` (the window is locked to test_definitions), so anchoring on it froze
    the countdown at `end_date - release` — e.g. an experiment ending one day after
    release showed 1/14 forever regardless of real elapsed time. We anchor on the
    run date (the `YYYY-MM-DD` prefix of `run_id`) instead: deterministic on rerender
    of the same run, and it advances with real time the way the orchestrator's
    eligibility gate (`evaluate_seo_since <= today-14`) already does.

    Falls back to `fallback_through` only when `run_id` has no parseable date prefix
    (e.g. the default "run" used by the idempotency fixture). Returns None if neither
    a run date nor the release date can be parsed.
    """
    from datetime import date as _D
    if not eval_seo_since:
        return None
    try:
        d_release = _D.fromisoformat(str(eval_seo_since))
    except (ValueError, TypeError):
        return None
    as_of = None
    if run_id and len(str(run_id)) >= 10:
        try:
            as_of = _D.fromisoformat(str(run_id)[:10])
        except (ValueError, TypeError):
            as_of = None
    if as_of is None and fallback_through:
        try:
            as_of = _D.fromisoformat(str(fallback_through))
        except (ValueError, TypeError):
            as_of = None
    if as_of is None:
        return None
    return max(0, (as_of - d_release).days)


def _run_date(run_id):
    """The calendar date the run happened, from the `YYYY-MM-DD` prefix of run_id.
    Returns an ISO date string or None (e.g. the idempotency fixture passes "run")."""
    from datetime import date as _D
    if not run_id or len(str(run_id)) < 10:
        return None
    try:
        return _D.fromisoformat(str(run_id)[:10]).isoformat()
    except (ValueError, TypeError):
        return None


def _iter_daily_dates(obj):
    """Yield the date string of every row in every `daily` array found anywhere in obj.
    Rows carry the date under `event_date`, `date`, or `d` depending on subagent shape."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "daily" and isinstance(v, list):
                for row in v:
                    if isinstance(row, dict):
                        dt = row.get("event_date") or row.get("date") or row.get("d")
                        if dt:
                            yield str(dt)
            else:
                yield from _iter_daily_dates(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_daily_dates(item)


def _max_event_date(experiments_raw):
    """Deterministically derive data_through = max event_date across all raw daily arrays.

    Replaces the agent-passed `--data-through`, which the orchestrating model resolved
    inconsistently from a loose "max event_date" instruction (one run passed ~yesterday,
    another the locked window end — see CHANGELOG v0.8.9/v0.9.0). Computing it from the
    raw JSONs makes the report's "data through" stamp a pure function of the data.
    Returns an ISO date string, or None when no daily rows exist (degenerate run).
    """
    from datetime import date as _D
    best = None
    for exp in experiments_raw.values():
        for ds in _iter_daily_dates(exp):
            s = str(ds)[:10]
            try:
                _D.fromisoformat(s)
            except (ValueError, TypeError):
                continue
            if best is None or s > best:
                best = s
    return best


def build_payload(name, exp, run_id, data_through):
    ab = exp.get("ab") or {}
    seo = exp.get("seo") or {}
    deal = exp.get("deal") or {}

    raw_filt = (ab.get("raw") or {}).get("filtered") or {}
    raw_ovr = (ab.get("raw") or {}).get("overall") or {}

    # Canonical %Δ recompute: walk every view that the renderer reads `mean_delta_pct`
    # from and replace m1uv/cvr blocks with `stats_for_daily()` output (aggregate ratio
    # SUM(num)/SUM(den), paired t-test on daily ratios). This is the single point where
    # the renderer enforces the ab-experiments canon — subagent-emitted percentages are
    # overridden, so a subagent that drifts back to daily-mean cannot leak through.
    _recompute_view_metrics(raw_filt)
    _recompute_view_metrics(raw_ovr)
    for cat_block_key in ("per_category", "per_category_overall"):
        for cat_view in (ab.get(cat_block_key) or {}).values():
            _recompute_view_metrics(cat_view)

    # Overall daily (deal-scoped): prefer ab.overall_daily if pre-computed by upstream;
    # else fall back to filtered.daily (M1/UV only) — CVR will be missing.
    # `stats_for_daily` derives per-day ratios from raw totals (m1/uv, orders/udv) when
    # the explicit ratio keys are absent, so any daily-row shape that carries the totals
    # produces a result; only shapes that omit BOTH ratios and totals return None.
    overall_daily = ab.get("overall_daily") or raw_filt.get("daily") or []
    overall_m1uv = stats_for_daily(overall_daily, "m1uv") if overall_daily else None
    overall_cvr  = stats_for_daily(overall_daily, "cvr")  if overall_daily else None

    # Unfiltered (population-wide) headline stats from raw.overall.daily — these are the
    # canonical "AB Test" headline numbers (whole-population; not deal-scoped). Scorecard
    # heroes and funnel composition source these. Falls back to None when raw.overall is
    # absent or its daily rows lack the underlying totals.
    raw_ovr_daily = raw_ovr.get("daily") or []

    # Derive start/end dates from the daily rows when the AB JSON omits them — some
    # subagents emit ab.start_date/end_date as null even though the daily window is clear.
    # Prefer raw.overall.daily (population-wide) and fall back to raw.filtered.daily.
    def _row_date(r):
        return r.get("event_date") or r.get("date") or r.get("d") if isinstance(r, dict) else None
    start_date = ab.get("start_date")
    end_date = ab.get("end_date")
    if not start_date or not end_date:
        for daily_src in (raw_ovr_daily, raw_filt.get("daily") or []):
            ds = [_row_date(r) for r in daily_src]
            ds = [d for d in ds if d]
            if ds:
                start_date = start_date or min(ds)
                end_date = end_date or max(ds)
                break
    # No explicit gate on m1uv_ctrl/cvr_ctrl — `stats_for_daily` derives ratios from raw
    # totals (m1/uv, orders/udv) when the pre-divided keys are absent. Subagents that
    # emit only totals (e.g. earlier FAQ-reviews AB shape) now produce populated tiles
    # instead of n/a.
    unfiltered_m1uv = stats_for_daily(raw_ovr_daily, "m1uv") if raw_ovr_daily else None
    unfiltered_cvr  = stats_for_daily(raw_ovr_daily, "cvr")  if raw_ovr_daily else None

    f_stats = _flatten_stats(raw_filt.get("stats") or {})
    o_stats = _flatten_stats(raw_ovr.get("stats") or {})
    f_n = (f_stats.get("n") if isinstance(f_stats, dict) else 0) or len(raw_filt.get("daily") or [])
    o_n = (o_stats.get("n") if isinstance(o_stats, dict) else 0) or len(raw_ovr.get("daily") or [])
    runway_filtered = _compute_runway(f_stats, f_n)
    runway_overall = _compute_runway(o_stats, o_n)
    computed_label = _compute_label(
        end_date=ab.get("end_date"),
        as_of=_run_date(run_id) or data_through,  # run date = wall-clock anchor for in-flight; data_through is fallback
        n_days=f_n or o_n,
        verdict=(raw_filt.get("verdict") or raw_ovr.get("verdict")),
        runway=runway_filtered,
        primary_p=f_stats.get("p_value") if isinstance(f_stats, dict) else None,
    )
    # Composed AB+SEO Final verdict — surfaced at the top of each exec card and in
    # summary.md. Built on the joint Net Margin/Visitor CI (delta-method composition
    # of AB M1+VFM/UV %Δ and SEO clicks DiD %Δ) plus hard guardrails for ranking risk
    # and CVR regressions. See _compose_final_verdict for the full decision hierarchy.
    _seo_did = (seo or {}).get("did") or {}
    _seo_overall = (seo or {}).get("overall") or {}
    _seo_power = (seo or {}).get("power_analysis") or {}
    # Source AB stats from the same view the exec card displays (population-wide
    # unfiltered when available; falls back to filtered). Pulls t_stat + n directly
    # so SE recovery is exact, not just approximated from p.
    _ab_overall_stats = _flatten_stats((raw_ovr.get("stats") or {}))
    _ab_filtered_stats = _flatten_stats((raw_filt.get("stats") or {}))
    _ab_primary_stats = _ab_overall_stats if _ab_overall_stats else _ab_filtered_stats
    _srm_overall = (ab.get("srm") or {}).get("overall") or {}
    _signals = {
        "ab_verdict": raw_filt.get("verdict") or raw_ovr.get("verdict"),
        "ab_label": computed_label,
        "m1uv_pct": (unfiltered_m1uv or {}).get("mean_delta_pct") if unfiltered_m1uv else None,
        "m1uv_p":   (unfiltered_m1uv or {}).get("p_value") if unfiltered_m1uv else None,
        "m1uv_t":   _ab_primary_stats.get("t_stat") if isinstance(_ab_primary_stats, dict) else None,
        "m1uv_n":   _ab_primary_stats.get("n") if isinstance(_ab_primary_stats, dict) else None,
        "m1uv_se":  _ab_primary_stats.get("se_pct") if isinstance(_ab_primary_stats, dict) else None,
        "cvr_pct":  (unfiltered_cvr or {}).get("mean_delta_pct") if unfiltered_cvr else None,
        "cvr_p":    (unfiltered_cvr or {}).get("p_value") if unfiltered_cvr else None,
        "seo_status": (seo or {}).get("status"),
        "seo_verdict": (seo or {}).get("verdict"),
        "seo_signal_strength": _seo_overall.get("signal_strength"),
        "did_imp_pct": _seo_did.get("did_impressions_pct"),
        "did_clicks_pct": _seo_did.get("did_clicks_pct"),
        "did_clicks_p":   _seo_power.get("p_value"),
        "srm_verdict": (_srm_overall.get("verdict") or "").lower(),
        "srm_promoted_from": _srm_overall.get("promoted_from"),
    }
    composed = _compose_final_verdict(_signals)

    # SEO TOO EARLY computation. `evaluate_seo_since` is the SEO release date from
    # test_definitions; the orchestrator only dispatches SEO when at least 14 days
    # have elapsed since release. Before that, we show a "TOO EARLY — X/14 days"
    # countdown in the exec card and mark the Final verdict as PRELIMINARY because
    # the SEO component of the composed CI is unavailable. The 14-day threshold is
    # the same one used in skills/list-experiments/SKILL.md (`seo_eligible`).
    eval_seo_since = exp.get("evaluate_seo_since")
    seo_status = (seo or {}).get("status")
    seo_days_needed_total = 14
    # Days are measured from release to the RUN date (run_id prefix), not data_through.
    # See _seo_days_since_release — data_through is the AB window end and froze this at
    # end_date - release for closed experiments (the 1/14-forever bug).
    seo_days_elapsed = _seo_days_since_release(run_id, eval_seo_since, data_through)
    # Too early = SEO has not been dispatched AND the window hasn't matured.
    # When seo_status is 'ok' we already have results; don't flag too-early.
    seo_too_early = (
        seo_status != "ok"
        and seo_days_elapsed is not None
        and seo_days_elapsed < seo_days_needed_total
    )

    if seo_too_early:
        # Overlay PRELIMINARY framing on the composed verdict — the verdict pill
        # stays as-is (HOLD/KILL/DEPLOY from AB-only signal) but the rationale and
        # label communicate that SEO is still pending.
        composed["rationale"] = (
            f"PRELIMINARY — awaiting SEO data ({seo_days_elapsed}/{seo_days_needed_total} days "
            f"since release {eval_seo_since}). Current AB-only composition: {composed['rationale']}"
        )

    return clean({
        "name": name,
        "run_id": run_id,
        "data_through": data_through,
        "alternate_name": ab.get("alternate_name") or name,
        "experiment_name": ab.get("experiment_name"),
        "start_date": start_date,
        "end_date": end_date,
        "evaluate_seo_since": eval_seo_since,
        "seo_too_early": seo_too_early,
        "seo_days_elapsed": seo_days_elapsed,
        "seo_days_needed_total": seo_days_needed_total,
        "n_deals": exp.get("n_deals"),  # from urls_<alt>.json (resolve-deal-urls output)
        "evaluation_narrative": ab.get("evaluation_narrative") or {},
        "deals_per_l2": exp.get("deals_per_l2") or {},  # {L2_name: count} for heatmap row labels
        "ab_label": computed_label,
        # Composed AB+SEO final verdict (DEPLOY | HOLD | KILL) + one-sentence rationale +
        # CSS class. JS reads `D.composed_verdict / composed_rationale / composed_cls`
        # to render the Final row at the top of the exec card takeaway block.
        "composed_verdict": composed["verdict"],
        "composed_rationale": composed["rationale"],
        "composed_cls": composed["cls"],
        # CI-based composition fields. `composed_basis` distinguishes a verdict that
        # came from the principled CI rule vs. the label-matrix fallback vs. a
        # guardrail trip — visible in the exec card so the reader knows the level
        # of statistical rigor behind the recommendation.
        "composed_basis": composed["basis"],
        "composed_net_pct": composed["composed_point"],
        "composed_se_pct": composed["composed_se"],
        "composed_lower_pct": composed["composed_lower"],
        "composed_upper_pct": composed["composed_upper"],
        "composed_alpha": composed["composed_alpha"],
        "composed_mwse_pct": composed["mwse_pct"],
        "ab_label_subagent": ab.get("label"),  # subagent's original label, kept for traceability
        "srm_filtered": (ab.get("srm") or {}).get("filtered") or {},
        "srm_overall": (ab.get("srm") or {}).get("overall") or {},
        "ab_filtered_stats": f_stats,
        "ab_filtered_verdict": raw_filt.get("verdict"),
        "ab_overall_stats": o_stats,
        "ab_overall_verdict": raw_ovr.get("verdict"),
        "runway_filtered": runway_filtered,
        "runway_overall": runway_overall,
        "raw_filtered_daily": raw_filt.get("daily") or [],
        "raw_overall_daily": raw_ovr.get("daily") or [],
        "overall_daily": overall_daily,  # alias; some templates expect this
        "overall_m1uv": overall_m1uv,
        "overall_cvr": overall_cvr,
        "unfiltered_m1uv": unfiltered_m1uv,
        "unfiltered_cvr": unfiltered_cvr,
        "categories": _merge_categories(ab, seo),
        "per_category": ab.get("per_category") or {},
        "per_category_overall": ab.get("per_category_overall") or {},
        "seo": {
            "status": seo.get("status"),
            "signal_level": seo.get("signal_level"),
            # Upstream-verbatim core values
            "verdict": seo.get("verdict"),
            "did_coherence": seo.get("did_coherence"),
            "did": seo.get("did") or {},
            # `overall` carries signal_strength + effective_post_days that the
            # exec-summary card uses to label SEO as PRELIMINARY/FINAL and surface
            # the N/28 post-days meta. Top-level `signal_level` is typically null,
            # so the exec card falls back to `overall.signal_strength`.
            "overall": seo.get("overall") or {},
            "power_analysis": seo.get("power_analysis") or {},
            "summary_tables": seo.get("summary_tables") or {},
            "by_category_l1": seo.get("by_category_l1") or [],
            "by_category_l2": seo.get("by_category_l2") or [],
            "by_category_l3": seo.get("by_category_l3") or [],
            "by_page_type": seo.get("by_page_type") or [],
            "caveats": seo.get("caveats") or [],
            # Derived helpers (computed once here so JS doesn't need pp arithmetic)
            "did_ctr_pp_overall": _seo_overall_ctr_did_pp(seo.get("summary_tables") or {}),
            # Embedded upstream HTML report — gzipped + base64 to keep the combined
            # report small enough to share as a single file. Decompressed in the
            # browser via DecompressionStream('gzip') before iframe srcdoc.
            # Compression saves ~95-97% on typical SEO HTML (it's mostly repeated
            # CSS/JS/Chart.js configs that gzip extremely well).
            "upstream_html_b64_gz": _gzip_b64_html(seo.get("upstream_html_b64")),
            "passthrough_html": seo.get("passthrough_html"),
            "passthrough_xlsx": seo.get("passthrough_xlsx"),
            # Skipped/failed reasons preserved
            "reason": seo.get("reason"),
            "failed_at": seo.get("failed_at"),
        },
        "deal": deal,
    })


# ---------- HTML template (string-substituted, not Jinja) ----------


HTML_SHELL = r"""<!doctype html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Experiment Evaluation — __TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root { --bg:#f8f9fa; --card:#fff; --green:#38a169; --red:#e53e3e; --yellow:#d69e2e; --accent:#3182ce; --ctrl:#4A90D9; --treat:#E8734A; --text:#1a202c; --muted:#718096; --border:#e2e8f0; }
*,*::before,*::after { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; padding-bottom:48px; }
.container { max-width:1440px; margin:0 auto; padding:0 24px; }
header { background:linear-gradient(135deg,#1a365d 0%,#2b6cb0 100%); color:#fff; padding:32px 0 28px; }
header .header-row { display:flex; align-items:flex-end; justify-content:space-between; gap:24px; flex-wrap:wrap; }
header h1 { font-size:1.9rem; font-weight:700; line-height:1.15; }
header h1 .hdr-rerun-link { font-size:0.78rem; font-weight:600; padding:4px 10px; background:rgba(255,255,255,0.18); border:1px solid rgba(255,255,255,0.35); border-radius:14px; margin-left:14px; vertical-align:middle; color:#fff; text-decoration:none; letter-spacing:0.3px; white-space:nowrap; }
header h1 .hdr-rerun-link:hover { background:rgba(255,255,255,0.28); border-color:rgba(255,255,255,0.6); }
header .hdr-meta { opacity:0.88; font-size:0.9rem; text-align:right; line-height:1.4; }
header .hdr-meta .stat { display:inline-block; padding:0 8px; border-left:1px solid rgba(255,255,255,0.35); }
header .hdr-meta .stat:first-child { border-left:0; padding-left:0; }
.section { margin:28px 0; }
.section h2 { margin-bottom:14px; font-size:1.25rem; color:#2d3748; }
.scoreboard { display:grid; grid-template-columns:repeat(auto-fill,minmax(380px,1fr)); gap:16px; }
.card { background:var(--card); border-radius:10px; padding:18px; box-shadow:0 1px 3px rgba(0,0,0,0.08); border-left:5px solid var(--border); }
.card h3 { font-size:1.02rem; font-weight:700; line-height:1.25; word-break:break-word; overflow-wrap:anywhere; }
.card.win { border-left-color:var(--green); } .card.lose { border-left-color:var(--red); } .card.flat { border-left-color:var(--yellow); }
.card .row { display:flex; justify-content:space-between; padding:4px 0; font-size:0.92rem; }
.card .row .lbl { color:var(--muted); }
.card .verdict { font-weight:700; font-size:1.05rem; padding-top:8px; border-top:1px solid var(--border); margin-top:8px; }
.badge { display:inline-block; padding:3px 10px; border-radius:14px; font-size:0.72rem; font-weight:700; text-transform:uppercase; margin-right:6px; vertical-align:middle; }
.badge-final { background:#edf2f7; color:#4a5568; }
.badge-prelim { background:#fefcbf; color:#744210; }
.badge-neutral { background:#edf2f7; color:#4a5568; }
.badge-pass { background:#e6f4ea; color:#1e4d2b; }
.badge-fail { background:#fed7d7; color:#742a2a; }
/* Tooltip hint — applied to badges that have a `title=` attribute so the reader
   sees there's more info on hover. Dotted bottom border + help cursor + a small
   ⓘ glyph after the text. Without this the title=tooltip was invisible. */
.badge-tip { cursor:help; position:relative; padding-right:18px; box-shadow:inset 0 -1px 0 0 currentColor; }
.badge-tip::after { content:"\01F6C8"; position:absolute; right:5px; top:50%; transform:translateY(-50%); font-size:0.78rem; opacity:0.75; line-height:1; }
.tabs { display:flex; gap:0; flex-wrap:wrap; border-bottom:2px solid var(--border); }
.tab-btn { padding:10px 22px; background:#edf2f7; border:1px solid var(--border); border-bottom:none; cursor:pointer; font-weight:600; font-size:0.95rem; }
.tab-btn.active { background:var(--card); border-bottom:2px solid var(--card); margin-bottom:-2px; color:#2b6cb0; }
.tab-content { display:none; background:var(--card); border:1px solid var(--border); border-top:none; padding:24px; border-radius:0 0 10px 10px; }
.tab-content.active { display:block; }
.chart-wrap { position:relative; height:280px; margin-bottom:8px; }
.chart-grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
@media (max-width:900px) { .chart-grid-2 { grid-template-columns:1fr; } }
.muted { color:var(--muted); font-size:0.85rem; }
table { width:100%; border-collapse:collapse; font-size:0.9rem; margin-top:8px; }
th,td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--border); }
th { background:#edf2f7; font-weight:600; }
td:first-child,th:first-child { text-align:left; }
td.label,th.label { text-align:left; }
.deal-row td:first-child { max-width:520px; }
.deal-row a { color:var(--accent); text-decoration:none; font-weight:600; }
.deal-row a:hover { text-decoration:underline; }
.deal-row .meta { color:var(--muted); font-size:0.8rem; }
.heatmap { display:grid; grid-template-columns:170px repeat(4, 1fr); gap:1px; background:var(--border); border:1px solid var(--border); border-radius:8px; overflow:hidden; }
.hm-cell { background:var(--card); padding:14px 12px; text-align:center; font-weight:600; }
.hm-head { background:#edf2f7; font-size:0.8rem; text-transform:uppercase; letter-spacing:0.5px; color:#4a5568; }
.hm-row-label { background:var(--card); text-align:left; font-weight:600; }
.hm-cell .pct { font-size:1.1rem; }
.hm-cell .pval { display:block; font-size:0.7rem; color:var(--muted); margin-top:2px; }
.hm-sig { box-shadow:inset 0 0 0 2px #1a202c; }
.skipped { background:#fefcbf; padding:14px; border-radius:8px; }
.bar-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }
.kpi { background:var(--card); padding:14px 16px; border-radius:8px; border-left:4px solid var(--accent); }
.kpi .label { font-size:0.78rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.5px; }
.kpi .value { font-size:1.4rem; font-weight:700; margin-top:4px; }
.kpi .delta { font-size:0.85rem; margin-top:2px; color:var(--muted); }
.kpi.win { border-left-color:var(--green); } .kpi.lose { border-left-color:var(--red); }
.sec-title { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.6px; color:var(--muted); margin-top:12px; padding-bottom:3px; border-bottom:1px dashed var(--border); font-weight:700; }
.exp-deals { font-size:0.75rem; color:var(--muted); font-weight:400; margin:-2px 0 4px; }
.metric-row { display:flex; justify-content:space-between; align-items:center; padding:7px 10px; border-radius:4px; margin:3px 0; font-size:0.92rem; gap:8px; }
.metric-row .lbl { color:#2d3748; font-weight:500; }
.metric-row.hero { padding:11px 12px; font-size:1.02rem; box-shadow:inset 0 0 0 1px rgba(0,0,0,0.04); }
.metric-row.hero .lbl { font-weight:700; }
.metric-row strong { font-size:1rem; }
.metric-row.hero strong { font-size:1.18rem; }
.metric-row .pmeta { color:#4a5568; font-size:0.78rem; margin-left:6px; }
.metric-row .sigstar { color:#22543d; font-size:0.78rem; margin-left:4px; }
.funnel-detail { color:var(--muted); font-size:0.76rem; line-height:1.45; padding:4px 10px 8px; }
.funnel-detail .stage { white-space:nowrap; }
.card-details { margin-top:10px; padding-top:8px; border-top:1px dashed var(--border); }
.card-details summary { cursor:pointer; font-size:0.78rem; color:var(--muted); padding:2px 0; user-select:none; }
.card-details summary:hover { color:var(--text); }
.card-details .row { padding:3px 0; font-size:0.84rem; }
.card-details .row .lbl, .card-details .row .muted { color:var(--muted); }
.rationale { padding:12px 16px; border-radius:6px; border-left:4px solid var(--border); margin-bottom:18px; font-size:0.92rem; line-height:1.55; }
.rationale-title { font-size:0.78rem; text-transform:uppercase; letter-spacing:0.6px; color:var(--muted); font-weight:700; margin-bottom:6px; }
.rationale-title strong { color:var(--text); letter-spacing:0; }
.rationale-list { margin:0; padding-left:20px; }
.rationale-list li { margin:3px 0; }
.rationale-list .sigstar { color:#22543d; font-weight:700; }
.narrative-section { margin-top:10px; }
.narrative-section:first-child { margin-top:0; }
.narrative-h { font-size:0.78rem; text-transform:uppercase; letter-spacing:0.6px; color:#2d3748; font-weight:700; margin-bottom:4px; }
.narrative-section p { margin:4px 0; }
.narrative-section ul { margin:4px 0; padding-left:22px; }
.narrative-section li { margin:3px 0; }
.exec-summary { margin-bottom:8px; }
.exec-overview { color:var(--muted); font-size:0.9rem; margin-bottom:14px; }
.exec-overview .tally { padding:0 10px; border-left:1px solid var(--border); }
.exec-overview .tally:first-child { padding-left:0; border-left:0; }
.exec-overview .tally strong { color:var(--text); }
.exec-cards { display:grid; grid-template-columns:1fr; gap:14px; }
.exec-card { background:var(--card); border-radius:10px; padding:18px 22px; box-shadow:0 1px 3px rgba(0,0,0,0.08); border-left:6px solid var(--border); display:grid; grid-template-columns:1fr; gap:12px; }
.exec-card.exec-ship { border-left-color:var(--green); }
.exec-card.exec-kill { border-left-color:var(--red); }
.exec-card.exec-other { border-left-color:var(--yellow); }
.exec-card-header { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }
.exec-card-name { font-size:1.15rem; font-weight:700; color:var(--text); }
.exec-card-name .exec-deals-inline { font-weight:400; font-size:0.78rem; color:var(--muted); margin-left:8px; }
.exec-card-badges { display:flex; gap:6px; flex-wrap:wrap; }
.badge-verdict-ship { background:#c6f6d5; color:#22543d; }
.badge-verdict-kill { background:#fed7d7; color:#742a2a; }
.badge-verdict-neutral { background:#fefcbf; color:#744210; }
.exec-card-tiles { display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; }
@media (max-width:1100px) { .exec-card-tiles { grid-template-columns:repeat(3, 1fr); } }
@media (max-width:760px) { .exec-card-tiles { grid-template-columns:repeat(2, 1fr); } }
.exec-verdict-group { display:inline-flex; align-items:center; gap:5px; padding:4px 8px; background:#fafbfc; border:1px solid var(--border); border-radius:10px; flex-wrap:wrap; }
.exec-verdict-label { font-size:0.68rem; text-transform:uppercase; letter-spacing:0.7px; color:var(--muted); font-weight:700; padding-right:2px; }
.exec-verdict-meta { font-size:0.74rem; color:var(--muted); padding-left:6px; margin-left:2px; border-left:1px dashed var(--border); white-space:nowrap; }
.exec-tile { background:var(--bg); border-radius:6px; padding:11px 13px; border-left:3px solid var(--border); }
.exec-tile.pos { border-left-color:var(--green); background:#f0fff4; }
.exec-tile.neg { border-left-color:var(--red); background:#fff5f5; }
.exec-tile.neu { border-left-color:var(--muted); background:#fafbfc; }
.exec-tile.na  { border-left-color:var(--border); background:var(--bg); opacity:0.7; }
.exec-tile.sig { box-shadow:inset 0 0 0 1px rgba(0,0,0,0.08); }
.exec-tile .exec-tlabel { font-size:0.7rem; text-transform:uppercase; letter-spacing:0.5px; color:var(--muted); font-weight:600; }
.exec-tile .exec-tval { font-size:1.35rem; font-weight:700; margin-top:2px; line-height:1.15; }
.exec-tile.pos .exec-tval { color:#22543d; }
.exec-tile.neg .exec-tval { color:#742a2a; }
.exec-tile.na .exec-tval { color:var(--muted); }
.exec-tile .exec-tp { font-size:0.7rem; color:var(--muted); margin-top:1px; }
.exec-tile .exec-tstar { color:#22543d; font-size:0.7rem; margin-left:3px; }
.exec-takeaway { color:var(--text); font-size:0.92rem; line-height:1.5; padding-top:8px; border-top:1px dashed var(--border); display:grid; gap:6px; }
.exec-takeaway-row { display:grid; grid-template-columns:90px 1fr; gap:10px; align-items:start; }
.exec-takeaway-row .exec-tk-label { font-size:0.68rem; text-transform:uppercase; letter-spacing:0.6px; color:var(--muted); font-weight:700; padding-top:2px; }
.exec-takeaway-row > span:nth-child(2) { color:var(--text); }
.exec-conf.exec-conf-high { color:#22543d; }
.exec-conf.exec-conf-high .exec-tk-label { color:#22543d; }
.exec-conf.exec-conf-mid { color:#744210; }
.exec-conf.exec-conf-mid .exec-tk-label { color:#744210; }
.exec-conf.exec-conf-low { color:#742a2a; }
.exec-conf.exec-conf-low .exec-tk-label { color:#742a2a; }
/* Final composed AB+SEO verdict — first row of the takeaway block. Larger and bolder
   than the Confidence/Why/Action rows since this is the bottom-line recommendation. */
.exec-takeaway-row.exec-final { padding-bottom:6px; border-bottom:1px dashed var(--border); margin-bottom:2px; align-items:center; }
.exec-takeaway-row.exec-final .exec-tk-label { font-size:0.74rem; font-weight:800; color:var(--text); }
.exec-takeaway-row.exec-final .exec-final-pill { display:inline-block; font-weight:800; font-size:0.84rem; letter-spacing:0.5px; padding:3px 12px; border-radius:14px; margin-right:10px; vertical-align:middle; }
.exec-takeaway-row.exec-final.final-deploy .exec-final-pill { background:#c6f6d5; color:#22543d; }
.exec-takeaway-row.exec-final.final-hold   .exec-final-pill { background:#fefcbf; color:#744210; }
.exec-takeaway-row.exec-final.final-kill   .exec-final-pill { background:#fed7d7; color:#742a2a; }
.exec-takeaway-row.exec-final .exec-final-rationale { color:var(--text); font-size:0.94rem; }
/* Final-row strip rendered ABOVE the tiles (moved out of the takeaway block so the
   bottom-line recommendation is the first thing readers see after the experiment name).
   Mirrors the takeaway Final-row look but stands as a standalone element. */
.exec-final-strip { display:grid; grid-template-columns:170px 1fr; gap:10px; align-items:center; padding:10px 14px; border-radius:8px; background:#fafbfc; border:1px solid var(--border); border-left-width:4px; }
.exec-final-strip .exec-tk-label { font-size:0.74rem; font-weight:800; color:var(--text); letter-spacing:0.6px; text-transform:uppercase; }
.exec-final-strip .exec-final-pill { display:inline-block; font-weight:800; font-size:0.86rem; letter-spacing:0.5px; padding:4px 14px; border-radius:14px; margin-right:10px; vertical-align:middle; }
.exec-final-strip.final-deploy { border-left-color:var(--green); background:#f0fff4; }
.exec-final-strip.final-deploy .exec-final-pill { background:#c6f6d5; color:#22543d; }
.exec-final-strip.final-hold { border-left-color:var(--yellow); background:#fffbeb; }
.exec-final-strip.final-hold   .exec-final-pill { background:#fefcbf; color:#744210; }
.exec-final-strip.final-kill { border-left-color:var(--red); background:#fff5f5; }
.exec-final-strip.final-kill   .exec-final-pill { background:#fed7d7; color:#742a2a; }
.exec-final-strip .exec-final-rationale { color:var(--text); font-size:0.95rem; line-height:1.45; }
.exec-final-strip .exec-final-basis { display:inline-block; font-size:0.66rem; font-weight:700; letter-spacing:0.5px; text-transform:uppercase; padding:2px 8px; border-radius:10px; background:#edf2f7; color:#4a5568; margin-right:10px; vertical-align:middle; }
/* Basis chip on the Final row — tells reader whether the verdict came from the
   CI rule, a guardrail trip, or the label-matrix fallback. Same idea on the
   Net-margin/visitor tile so the rigor level is visible in two places. */
.exec-takeaway-row.exec-final .exec-final-basis {
  display:inline-block; font-size:0.68rem; font-weight:700; letter-spacing:0.5px;
  text-transform:uppercase; padding:2px 8px; border-radius:10px;
  background:#edf2f7; color:#4a5568; margin-right:10px; vertical-align:middle;
}
.exec-tile .exec-tile-basis {
  display:inline-block; font-size:0.6rem; font-weight:700; letter-spacing:0.4px;
  text-transform:uppercase; padding:1px 6px; border-radius:8px;
  background:#edf2f7; color:#4a5568; margin-left:6px; vertical-align:middle;
}
.exec-card-subtitle { font-size:0.8rem; color:var(--muted); font-weight:400; margin:-4px 0 2px; line-height:1.5; }
.exec-card-subtitle.exec-card-subtitle-scale { font-size:0.76rem; color:#a0aec0; margin-top:0; }
.exp-deals-scale { font-size:0.72rem; color:#a0aec0; margin-top:-2px; }
.cat-subtabs { display:flex; gap:4px; flex-wrap:wrap; margin:14px 0 8px; }
.cat-subtab-btn { padding:6px 14px; background:#edf2f7; border:1px solid var(--border); border-radius:14px; cursor:pointer; font-weight:600; font-size:0.85rem; }
.cat-subtab-btn.active { background:#2b6cb0; color:#fff; border-color:#2b6cb0; }
.cat-subtab-content { display:none; }
.cat-subtab-content.active { display:block; }
footer { background:#1a202c; color:#a0aec0; text-align:center; padding:20px; font-size:0.82rem; margin-top:40px; }
</style>
</head><body>

<header>
  <div class="container header-row">
    <h1>Review Experiments evaluation <a class="hdr-rerun-link" href="https://github.com/cmstrba-ux/experiment-evaluation-orchestrator-plugin" target="_blank" rel="noopener" title="Clone the plugin and run /evaluate-reviews-experiments locally to reproduce this analysis on your own machine">↓ Download plugin for local execution</a></h1>
    <div id="hdr-meta" class="hdr-meta"></div>
  </div>
</header>

<div class="container">

<div class="section exec-summary">
  <h2>Executive Summary</h2>
  <div id="exec-summary"></div>
</div>

<div class="section">
  <div class="tabs" id="exp-tabs"></div>
  <div id="exp-tab-contents"></div>
</div>

</div>

<footer><div class="container">paired t-test α=0.05 · SRM chi-square α=0.001 · dates from test_definitions, NOT GrowthBook · M1+VFM/UV = margin_1_vfm / uv · CVR = ue_orders / udv</div></footer>

<script id="data" type="application/json">__PAYLOAD__</script>
<script>
__JS__
</script>
</body></html>
"""


# JS lives in a sibling file so we don't have to embed a 400-line string template.
JS_PATH = Path(__file__).parent / "render_app.js"


# ---------- main ----------


def render(run_dir: Path, out_path: Path, run_id: str = "run", data_through: str = "(unknown)") -> None:
    experiments_raw = load_run(run_dir)
    if not experiments_raw:
        out_path.write_text("<html><body><h1>No experiments to render.</h1></body></html>", encoding="utf-8")
        return
    # data_through is computed deterministically from the raw daily arrays so the
    # header "data through" stamp is a pure function of the data, not of whatever the
    # orchestrating agent hand-passed. The CLI --data-through is a fallback only.
    data_through = _max_event_date(experiments_raw) or data_through
    payloads = {name: build_payload(name, exp, run_id, data_through) for name, exp in experiments_raw.items()}
    payload_json = json.dumps({"run_id": run_id, "data_through": data_through, "experiments": payloads}, separators=(",", ":"), allow_nan=False)
    js = JS_PATH.read_text(encoding="utf-8") if JS_PATH.exists() else ""
    title = ", ".join(payloads.keys())[:80]
    html = HTML_SHELL.replace("__TITLE__", h(title)).replace("__PAYLOAD__", payload_json).replace("__JS__", js)
    out_path.write_text(html, encoding="utf-8", newline="\n")


def _runway_label(runway):
    if not runway or runway.get("already_significant"):
        return ""
    if runway.get("infeasible"):
        return "infeasible"
    add = runway.get("additional_days")
    if add is None:
        return ""
    return f"+{add}d to p<0.05"


# Cap for "would a brief extension flip this to significant?". c3 spec uses
# "≤ 8 weeks more" → 56 days. HOLD with runway under this cap stays FINAL
# (could extend); anything else is FINAL — can be closed.
EXTEND_RUNWAY_CAP_DAYS = 56


def _compute_label(end_date, as_of, n_days, verdict, runway, primary_p=None):
    """Authoritative label rule for the renderer.

    The subagent-emitted label is ignored — the renderer derives the label
    deterministically from significance + runway + duration. Label vocabulary:

    - PRELIMINARY: experiment still in-flight (end_date >= as_of, where `as_of` is
                   the run date) or n_days < 7. The result is not stable yet.
                   NOTE: `as_of` is the run/calendar date, NOT data_through — the
                   latter is the locked data-window end and would mis-flag the
                   latest closed experiment as in-flight (same clock confusion the
                   v0.8.9 SEO countdown fix addressed).
    - FINAL: experiment ended. This is the default — once an experiment has run
             past its end_date with enough days, it IS final. No "can be closed"
             qualifier (it's already final; nothing to "close").
    - FINAL — could extend: ended, primary metric not yet significant, AND a brief
                            extension (≤ 56d) could plausibly flip it to p<0.05.
                            Surfaces the extension option without implying the
                            test is still running or that closing is wrong.

    The earlier rule emitted "FINAL — can be closed" for decisive-read tests, but
    the user pointed out that "can be closed" is misleading/redundant — finished
    experiments are simply final, not waiting to be closed. Only the extendable
    case needs an explicit qualifier.
    """
    try:
        if end_date and as_of and str(end_date) >= str(as_of):
            return "PRELIMINARY"
    except Exception:
        pass
    if n_days is not None and n_days < 7:
        return "PRELIMINARY"

    runway = runway or {}
    # Decisive significance is final — no extension consideration needed.
    if runway.get("already_significant") or (primary_p is not None and primary_p < 0.05):
        return "FINAL"

    # Not significant — would a brief extension change that? If yes, surface that.
    add_days = runway.get("additional_days")
    can_extend_briefly = (
        add_days is not None
        and not runway.get("infeasible")
        and add_days <= EXTEND_RUNWAY_CAP_DAYS
    )
    if can_extend_briefly:
        return "FINAL — could extend"
    # Not significant and no viable extension path — also final.
    return "FINAL"


def _srm_label(srm_view):
    verdict = (srm_view or {}).get("verdict") or "?"
    if (srm_view or {}).get("promoted_from") == "remediated":
        orig = (srm_view.get("original") or {}).get("verdict") or "fail"
        return f"raw {orig} → active_visitor pass"
    return verdict


def render_summary(run_dir: Path, out_path: Path, run_id: str, data_through: str) -> None:
    """Write summary.md — exec scoreboard with both AB and SEO verdicts per experiment.

    Stats are recomputed via ``stats_for_daily()`` (canonical aggregate ratio
    SUM(num)/SUM(den) for %Δ; paired t-test on daily ratios for p-value) so the
    summary headline matches the HTML scoreboard exactly. Subagent-emitted
    ``mean_delta_pct`` values are intentionally ignored — only the aggregate
    ratio matches the ab-experiments dashboard convention.
    """
    experiments_raw = load_run(run_dir)
    # Same deterministic data_through as render() — derived from the data, CLI is fallback.
    data_through = _max_event_date(experiments_raw) or data_through
    lines = [f"# Experiment Evaluation — {run_id}", "", f"Data through **{data_through}**.", "", "## Scoreboard", ""]
    for name, exp in experiments_raw.items():
        ab = exp.get("ab") or {}
        seo = exp.get("seo") or {}
        raw = ab.get("raw") or {}
        raw_filt = raw.get("filtered") or {}
        f_stats = _flatten_stats(raw_filt.get("stats") or {})
        f_md = f_stats.get("mean_delta") or 0
        f_p = f_stats.get("p_value") or 1
        ab_verdict = raw_filt.get("verdict") or (raw.get("overall") or {}).get("verdict") or "?"

        # Canonical recompute: mirror build_payload(). Source the AB-Overall view first
        # (population-wide, `raw.overall.daily` from experiments_jupiter_hist) since that
        # matches what the exec-card top tiles show. Fall back to AB-Filtered only when
        # Overall is absent. `stats_for_daily` derives per-day ratios from raw totals
        # when explicit ratio keys are missing, so no strict gate.
        raw_ovr = raw.get("overall") or {}
        ovr_daily = raw_ovr.get("daily") or []
        scope_label = "AB-Overall"
        if not ovr_daily:
            ovr_daily = raw_filt.get("daily") or []
            scope_label = "AB-Filtered (no Overall view)" if ovr_daily else "n/a"
        om = stats_for_daily(ovr_daily, "m1uv") if ovr_daily else None
        oc = stats_for_daily(ovr_daily, "cvr")  if ovr_daily else None

        m_md = om.get("mean_delta_pct") if om else None
        m_p = om.get("p_value") if om else None
        c_md = oc.get("mean_delta_pct") if oc else None
        ab_summary = (
            f"M1+VFM/UV {m_md:+.2f}% (p={m_p:.3f})"
            if m_md is not None and m_p is not None
            else f"MPV mean Δ ${f_md:+.4f} (p={f_p:.3f})"
        )
        if c_md is not None:
            ab_summary += f", CVR {c_md:+.2f}%"
        ab_summary += f" · scope: {scope_label}"

        n_deals = exp.get("n_deals")
        header_suffix = f" — {n_deals:,} deals" if isinstance(n_deals, int) and n_deals > 0 else ""
        # Composed AB+SEO Final verdict (DEPLOY|HOLD|KILL). Recompute here using the
        # same signals dict the exec card uses so summary.md and combined_report.html
        # agree byte-for-byte.
        seo_did = (seo or {}).get("did") or {}
        seo_overall = (seo or {}).get("overall") or {}
        seo_power = (seo or {}).get("power_analysis") or {}
        ovr_stats = _flatten_stats((raw_ovr.get("stats") or {}))
        filt_stats = _flatten_stats((raw_filt.get("stats") or {}))
        primary_stats = ovr_stats if ovr_stats else filt_stats
        srm_overall = (ab.get("srm") or {}).get("overall") or {}
        # CVR signal for the guardrail check — derive from raw.overall.daily the
        # same way the exec card does so the guardrail and the displayed tile share
        # one source of truth.
        ovr_cvr = stats_for_daily(ovr_daily, "cvr") if ovr_daily else None
        composed = _compose_final_verdict({
            "ab_verdict": ab_verdict,
            "m1uv_pct": m_md,
            "m1uv_p": m_p,
            "m1uv_t": primary_stats.get("t_stat") if isinstance(primary_stats, dict) else None,
            "m1uv_n": primary_stats.get("n") if isinstance(primary_stats, dict) else None,
            "cvr_pct": (ovr_cvr or {}).get("mean_delta_pct") if ovr_cvr else None,
            "cvr_p":   (ovr_cvr or {}).get("p_value")        if ovr_cvr else None,
            "seo_status": (seo or {}).get("status"),
            "seo_verdict": (seo or {}).get("verdict"),
            "seo_signal_strength": seo_overall.get("signal_strength"),
            "did_imp_pct": seo_did.get("did_impressions_pct"),
            "did_clicks_pct": seo_did.get("did_clicks_pct"),
            "did_clicks_p": seo_power.get("p_value"),
            "srm_verdict": (srm_overall.get("verdict") or "").lower(),
            "srm_promoted_from": srm_overall.get("promoted_from"),
        })
        # SEO TOO EARLY overlay — mirrors build_payload(). When evaluate_seo_since
        # is set and < 14 days have elapsed, mark the Final as PRELIMINARY and
        # surface the day-counter; SEO line shows "TOO EARLY — X/14 days needed".
        eval_seo_since = exp.get("evaluate_seo_since")
        seo_status_str = seo.get("status")
        # Wall-clock days since release (run-date anchored, same as build_payload).
        # Computed unconditionally so the <28d maturity chip below works when SEO ran.
        seo_days_elapsed = _seo_days_since_release(run_id, eval_seo_since, data_through)
        seo_too_early = (
            seo_status_str != "ok"
            and seo_days_elapsed is not None
            and seo_days_elapsed < 14
        )
        final_rationale_text = composed["rationale"]
        if seo_too_early:
            final_rationale_text = (
                f"PRELIMINARY — awaiting SEO data ({seo_days_elapsed}/14 days since release "
                f"{eval_seo_since}). Current AB-only composition: {composed['rationale']}"
            )

        lines.append(f"- **{name}**{header_suffix}")
        lines.append(f"  - Final Recommendation: **{composed['verdict']}** — {final_rationale_text}")
        lines.append(f"  - AB: **{ab_verdict}** — {ab_summary}")

        if seo_too_early:
            lines.append(
                f"  - SEO: **TOO EARLY** — {seo_days_elapsed}/14 to preliminary results "
                f"(release {eval_seo_since}; data through {data_through})"
            )
        elif seo.get("status") != "ok":
            seo_msg = seo.get("status") or "n/a"
            if seo.get("reason"):
                seo_msg += f" ({seo['reason']})"
            lines.append(f"  - SEO: n/a — {seo_msg}")
        else:
            seo_verdict = seo.get("verdict") or "?"
            did = seo.get("did") or {}
            power = seo.get("power_analysis") or {}
            imp_pct = did.get("did_impressions_pct")
            clk_pct = did.get("did_clicks_pct")
            seo_p = power.get("p_value")
            # SEO maturity in summary.md: 14-28 days post-release is PRELIMINARY at
            # all costs (mirrors render_app.js). ≥28 days inherits whatever upstream's
            # signal_strength says (typically FINAL when full signal is reached).
            # When PRELIMINARY, append the day countdown ("X/28 to final results") so
            # the markdown matches the HTML scoreboard's badge meta.
            mat_chip = ""
            if seo_days_elapsed is not None:
                if seo_days_elapsed < 28:
                    mat_chip = f" [PRELIMINARY — {seo_days_elapsed}/28 to final results]"
                else:
                    upstream_label = (seo_overall.get("signal_strength") or "").lower()
                    if upstream_label == "full":
                        mat_chip = " [FINAL]"
                    else:
                        mat_chip = f" [PRELIMINARY — {seo_days_elapsed}/28 to final results]"
            parts = []
            if imp_pct is not None:
                parts.append(f"DiD Impressions {imp_pct:+.2f}%")
            if clk_pct is not None:
                parts.append(f"DiD Clicks {clk_pct:+.2f}%")
            if seo_p is not None:
                parts.append(f"p={seo_p:.3f}")
            seo_summary = ", ".join(parts) if parts else "no DiD computed"
            lines.append(f"  - SEO: **{seo_verdict}**{mat_chip} — {seo_summary}")

    lines.extend([
        "",
        "## Methodology",
        "- **Final** verdict (DEPLOY|HOLD|KILL) is built from a joint Net Margin/Visitor CI (delta-method composition of AB M1+VFM/UV %Δ and SEO clicks DiD %Δ, 90% CI) plus hard guardrails: SEO impressions DiD ≤ −10% at full signal → KILL; AB CVR ≤ −1% at p<0.05 → KILL. CI rule: lower > +0.5% → DEPLOY; upper < −0.5% → KILL; straddling → HOLD. The `basis` chip on each card shows whether the verdict came from the CI rule, a guardrail trip, or the label-matrix fallback. Full rule in `skills/render-combined-report/SKILL.md`.",
        "- AB %Δ: aggregate ratio SUM(num)/SUM(den) (ab-experiments canon, matches Groupon dashboards). Daily means are not used.",
        "- AB significance: paired t-test on daily M1+VFM/UV, α=0.05.",
        "- SRM check: chi-square, α=0.001. Active-visitor remediation surfaces when raw fails AND AV passes.",
        "- SEO: synthetic-control DiD on impressions / clicks (hierarchical L3→L2→L1→page_type→domain peer cohort), variant-vs-whole-domain CTR DiD, and verdict from `seo-impact-plugin:seo-impact-analyzer`. Per-category SEO is variant Δ% minus same-category All-Groupon Δ% (benchmark spread).",
        "",
        "Full HTML report: `combined_report.html`.",
    ])
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--summary", required=False, help="If provided, also write the summary.md to this path")
    ap.add_argument("--run-id", default="run")
    ap.add_argument("--data-through", default="(unknown)")
    args = ap.parse_args()
    run_dir = Path(args.run_dir)
    render(run_dir, Path(args.out), run_id=args.run_id, data_through=args.data_through)
    if args.summary:
        render_summary(run_dir, Path(args.summary), run_id=args.run_id, data_through=args.data_through)


if __name__ == "__main__":
    main()
