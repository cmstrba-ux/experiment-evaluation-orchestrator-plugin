"""Render combined HTML report + exec summary from per-experiment JSON intermediates.

Inputs (under <run_dir>/raw/):
  ab_<alt>.json:   AB evaluation output. Optionally includes:
                    - per_category (filtered)
                    - per_category_overall (population-wide per cat)
                    - overall_daily (daily M1/UV + CVR)
                    - srm_filtered_remediated, srm_overall_remediated (when SRM triggered remediation)
  seo_<alt>.json:  SEO eval output. Optionally includes:
                    - did_overall, did_per_l2 (when control set was supplied)
                    - l2_topk (top 15 winners/losers per L2 by clicks_delta, from per_url)
                    Note: per_url should NOT be embedded here (too large; ~MB-sized lists).
  deal_<alt>.json: Deal-level output. Top winners/losers should ideally have
                    company_name + deal_title fields (enriched against deal_option).

Outputs:
  <run_dir>/combined_report.html — self-contained HTML with Chart.js, scoreboard,
                                    overview, per-cat heatmap (4-col: Filtered/Overall ×
                                    M1/UV/CVR), per-cat sub-tabs with daily charts,
                                    SEO tab with DiD + L2 winners/losers, deals tab
                                    with hyperlinked tables.
  <run_dir>/summary.md          — exec scoreboard markdown.

This module DOES NOT touch BigQuery. All enrichment must be done by upstream skills.
"""
from __future__ import annotations

import argparse
import json
import math
from html import escape as h
from pathlib import Path
from statistics import mean, stdev


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
    """Subagent stats nest under stats.treatment.{mean_delta,...}; flatten."""
    if not isinstance(stats, dict):
        return stats
    if "mean_delta" in stats:
        return stats
    if isinstance(stats.get("treatment"), dict) and "mean_delta" in stats["treatment"]:
        return {**stats["treatment"]}
    return stats


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
    """Aggregate-ratio %Δ (matches ab-experiments plugin canon: SUM(num)/SUM(den)) for the
    point estimate; paired t-test on daily ratios for the p-value (matches plugin: 'paired
    t-test on daily data > t-test on aggregated totals').

    metric is the daily ratio key ('m1uv', 'cvr'). num_field/den_field are the underlying
    total fields (e.g. 'm1','uv' or 'orders','udv'). Inferred from `metric` if omitted.

    Daily rows must include the underlying totals alongside the ratios for the aggregate
    computation. If only ratios are present, falls back to daily-mean-based pct (legacy).
    """
    if num_field is None or den_field is None:
        if metric == "m1uv":
            num_field, den_field = "m1", "uv"
        elif metric == "cvr":
            num_field, den_field = "orders", "udv"
        else:
            num_field, den_field = metric, "uv"

    diffs = []
    for r in daily:
        ct = r.get(f"{metric}_ctrl")
        tt = r.get(f"{metric}_treat")
        if ct is None or tt is None:
            continue
        diffs.append(tt - ct)
    if not diffs:
        return {"mean_delta": 0, "mean_delta_pct": 0, "agg_ctrl": 0, "agg_treat": 0, "agg_delta": 0, "daily_mean_pct": 0, "p_value": 1.0, "n": 0}
    md, p = paired_t_p(diffs)

    # Aggregate ratio (canon).
    has_totals = any(f"{num_field}_ctrl" in r for r in daily)
    if has_totals:
        sum_num_c = sum(float(r.get(f"{num_field}_ctrl") or 0) for r in daily)
        sum_den_c = sum(float(r.get(f"{den_field}_ctrl") or 0) for r in daily)
        sum_num_t = sum(float(r.get(f"{num_field}_treat") or 0) for r in daily)
        sum_den_t = sum(float(r.get(f"{den_field}_treat") or 0) for r in daily)
        agg_c = (sum_num_c / sum_den_c) if sum_den_c else 0
        agg_t = (sum_num_t / sum_den_t) if sum_den_t else 0
        agg_delta = agg_t - agg_c
        agg_pct = ((agg_t / agg_c) - 1) * 100 if agg_c else 0
    else:
        agg_c = agg_t = agg_delta = 0
        agg_pct = 0  # signal: aggregate not computable from input shape

    base_vals = [r[f"{metric}_ctrl"] for r in daily if r.get(f"{metric}_ctrl") is not None]
    daily_mean_base = mean(base_vals) if base_vals else 1e-12
    daily_mean_pct = (md / daily_mean_base) * 100

    return {
        "mean_delta": md,
        # Primary displayed pct: aggregate ratio when totals are present, else daily-mean.
        "mean_delta_pct": agg_pct if has_totals else daily_mean_pct,
        "agg_ctrl": agg_c,
        "agg_treat": agg_t,
        "agg_delta": agg_delta,
        "daily_mean_pct": daily_mean_pct,
        "p_value": p,
        "n": len(diffs),
    }


def adapt_ab(ab):
    """Normalize AB JSON shape: flatten stats, adapt daily field names."""
    if not ab:
        return ab
    raw = ab.get("raw") or {}
    for view_key in ("filtered", "overall"):
        v = raw.get(view_key)
        if not v:
            continue
        v["stats"] = _flatten_stats(v.get("stats"))
        # daily may already be in flat shape ({d, ctrl, treat}) or in subagent shape ({event_date, m1_*, uv_*})
        new_daily = []
        for d in v.get("daily") or []:
            if "d" in d and ("ctrl" in d or "treat" in d):
                new_daily.append(d)
                continue
            uvc = float(d.get("uv_control") or 0)
            uvt = float(d.get("uv_treatment") or 0)
            m1c = float(d.get("m1_control") or 0)
            m1t = float(d.get("m1_treatment") or 0)
            new_daily.append({
                "d": d.get("event_date") or d.get("d"),
                "ctrl": (m1c / uvc) if uvc else 0,
                "treat": (m1t / uvt) if uvt else 0,
            })
        if new_daily:
            v["daily"] = new_daily
    rem = ab.get("remediated") or {}
    if rem:
        for view_key in ("filtered", "overall"):
            v = rem.get(view_key)
            if v:
                v["stats"] = _flatten_stats(v.get("stats"))
    return ab


# ---------- data loading + payload assembly ----------


def load_run(run_dir: Path):
    raw = run_dir / "raw"
    experiments = {}
    for p in sorted(raw.glob("ab_*.json")):
        name = p.stem[len("ab_"):]
        experiments[name] = {"ab": adapt_ab(json.loads(p.read_text(encoding="utf-8")))}
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
        experiments.setdefault(name, {})["deal"] = d
    return experiments


def build_payload(name, exp, run_id, data_through):
    ab = exp.get("ab") or {}
    seo = exp.get("seo") or {}
    deal = exp.get("deal") or {}

    raw_filt = (ab.get("raw") or {}).get("filtered") or {}
    raw_ovr = (ab.get("raw") or {}).get("overall") or {}

    # Overall daily (deal-scoped): prefer ab.overall_daily if pre-computed by upstream;
    # else fall back to filtered.daily (M1/UV only) — CVR will be missing.
    overall_daily = ab.get("overall_daily") or raw_filt.get("daily") or []
    overall_m1uv = stats_for_daily(overall_daily, "m1uv") if overall_daily and "m1uv_ctrl" in (overall_daily[0] if overall_daily else {}) else None
    overall_cvr = stats_for_daily(overall_daily, "cvr") if overall_daily and "cvr_ctrl" in (overall_daily[0] if overall_daily else {}) else None

    return clean({
        "name": name,
        "run_id": run_id,
        "data_through": data_through,
        "alternate_name": ab.get("alternate_name") or name,
        "experiment_name": ab.get("experiment_name"),
        "start_date": ab.get("start_date"),
        "end_date": ab.get("end_date"),
        "ab_label": ab.get("label"),
        "srm_filtered": (ab.get("srm") or {}).get("filtered") or {},
        "srm_overall": (ab.get("srm") or {}).get("overall") or {},
        "ab_filtered_stats": _flatten_stats(raw_filt.get("stats") or {}),
        "ab_filtered_verdict": raw_filt.get("verdict"),
        "ab_overall_stats": _flatten_stats(raw_ovr.get("stats") or {}),
        "ab_overall_verdict": raw_ovr.get("verdict"),
        "raw_filtered_daily": raw_filt.get("daily") or [],
        "raw_overall_daily": raw_ovr.get("daily") or [],
        "overall_daily": overall_daily,  # alias; some templates expect this
        "overall_m1uv": overall_m1uv,
        "overall_cvr": overall_cvr,
        "categories": list((ab.get("per_category") or {}).keys()) or list((ab.get("per_category_overall") or {}).keys()),
        "per_category": ab.get("per_category") or {},
        "per_category_overall": ab.get("per_category_overall") or {},
        "seo": {
            "status": seo.get("status"),
            "signal_level": seo.get("signal_level"),
            "pre_post": seo.get("pre_post"),
            "did_overall": seo.get("did_overall"),  # populated when control set was supplied
            "did_per_l2": seo.get("did_per_l2") or {},
            "l2_topk": seo.get("l2_topk") or {},
            "l2_order": seo.get("l2_order") or list((seo.get("did_per_l2") or {}).keys()) or list((seo.get("l2_topk") or {}).keys()),
            "pre_days": seo.get("pre_days"),
            "post_days": seo.get("post_days"),
            "passthrough_html": seo.get("passthrough_html"),
            "passthrough_xlsx": seo.get("passthrough_xlsx"),
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
header { background:linear-gradient(135deg,#1a365d 0%,#2b6cb0 100%); color:#fff; padding:36px 0 28px; }
header h1 { font-size:1.9rem; font-weight:700; margin-bottom:6px; }
header p { opacity:0.85; font-size:0.95rem; }
.section { margin:28px 0; }
.section h2 { margin-bottom:14px; font-size:1.25rem; color:#2d3748; }
.scoreboard { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }
.card { background:var(--card); border-radius:10px; padding:18px; box-shadow:0 1px 3px rgba(0,0,0,0.08); border-left:5px solid var(--border); }
.card.win { border-left-color:var(--green); } .card.lose { border-left-color:var(--red); } .card.flat { border-left-color:var(--yellow); }
.card .row { display:flex; justify-content:space-between; padding:4px 0; font-size:0.92rem; }
.card .row .lbl { color:var(--muted); }
.card .verdict { font-weight:700; font-size:1.05rem; padding-top:8px; border-top:1px solid var(--border); margin-top:8px; }
.badge { display:inline-block; padding:3px 10px; border-radius:14px; font-size:0.72rem; font-weight:700; text-transform:uppercase; margin-right:6px; vertical-align:middle; }
.badge-final { background:#c6f6d5; color:#22543d; }
.badge-prelim { background:#fefcbf; color:#744210; }
.badge-pass { background:#e6f4ea; color:#1e4d2b; }
.badge-fail { background:#fed7d7; color:#742a2a; }
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
.cat-subtabs { display:flex; gap:4px; flex-wrap:wrap; margin:14px 0 8px; }
.cat-subtab-btn { padding:6px 14px; background:#edf2f7; border:1px solid var(--border); border-radius:14px; cursor:pointer; font-weight:600; font-size:0.85rem; }
.cat-subtab-btn.active { background:#2b6cb0; color:#fff; border-color:#2b6cb0; }
.cat-subtab-content { display:none; }
.cat-subtab-content.active { display:block; }
footer { background:#1a202c; color:#a0aec0; text-align:center; padding:20px; font-size:0.82rem; margin-top:40px; }
</style>
</head><body>

<header>
  <div class="container">
    <h1>Experiment Evaluation</h1>
    <p id="hdr-meta"></p>
  </div>
</header>

<div class="container">

<div class="section">
  <h2>Scoreboard</h2>
  <div class="scoreboard" id="scoreboard"></div>
</div>

<div class="section">
  <div class="tabs" id="exp-tabs"></div>
  <div id="exp-tab-contents"></div>
</div>

</div>

<footer><div class="container">paired t-test α=0.05 · SRM chi-square α=0.001 · dates from test_definitions, NOT GrowthBook · M1/UV = margin_1_vfm / uv · CVR = ue_orders / udv</div></footer>

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
    payloads = {name: build_payload(name, exp, run_id, data_through) for name, exp in experiments_raw.items()}
    payload_json = json.dumps({"run_id": run_id, "data_through": data_through, "experiments": payloads}, separators=(",", ":"), allow_nan=False)
    js = JS_PATH.read_text(encoding="utf-8") if JS_PATH.exists() else ""
    title = ", ".join(payloads.keys())[:80]
    html = HTML_SHELL.replace("__TITLE__", h(title)).replace("__PAYLOAD__", payload_json).replace("__JS__", js)
    out_path.write_text(html, encoding="utf-8", newline="\n")


def render_summary(run_dir: Path, out_path: Path, run_id: str, data_through: str) -> None:
    experiments_raw = load_run(run_dir)
    lines = [f"# Experiment Evaluation — {run_id}", "", f"Data through **{data_through}**.", "", "## Scoreboard", "",
             "| Experiment | Label | AB-Filtered | AB-Overall | SEO DiD (clicks pp) | Verdict | SRM |",
             "|---|---|---|---|---|---|---|"]
    for name, exp in experiments_raw.items():
        ab = exp.get("ab") or {}
        seo = exp.get("seo") or {}
        raw = ab.get("raw") or {}
        f_stats = _flatten_stats((raw.get("filtered") or {}).get("stats") or {})
        o_stats = _flatten_stats((raw.get("overall") or {}).get("stats") or {})
        f_md = f_stats.get("mean_delta") or 0
        f_p = f_stats.get("p_value") or 1
        o_md = o_stats.get("mean_delta") or 0
        o_p = o_stats.get("p_value") or 1
        seo_did = "n/a"
        if isinstance(seo.get("did_overall"), dict):
            d = seo["did_overall"].get("did") or {}
            if d.get("clk_pp") is not None:
                seo_did = f"{d['clk_pp']:+.2f}pp"
        verdict = (raw.get("filtered") or {}).get("verdict") or "?"
        srm = ((ab.get("srm") or {}).get("filtered") or {}).get("verdict") or "?"
        lines.append(f"| {name} | {ab.get('label','?')} | {f_md:+.4f} (p={f_p:.3f}) | {o_md:+.4f} (p={o_p:.3f}) | {seo_did} | {verdict} | {srm} |")
    lines.append("")
    lines.append("## Methodology")
    lines.append("- AB significance: paired t-test on daily M1/UV, α=0.05.")
    lines.append("- SRM check: chi-square, α=0.001.")
    lines.append("- SRM remediation: re-run with `active_visitor_flag='Y'` when raw SRM fails.")
    lines.append("- SEO DiD: variant pre/post % change minus control pre/post % change, day-normalized.")
    lines.append("")
    lines.append("Full HTML report: `combined_report.html`.")
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
