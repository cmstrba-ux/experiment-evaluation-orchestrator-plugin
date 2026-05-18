// Frontend for the combined experiment-evaluation report.
// Inputs (from <script id="data">): { run_id, data_through, experiments: { <name>: payload } }
// payload schema is documented in render.py (build_payload).

const ROOT = JSON.parse(document.getElementById('data').textContent);
const charts = {};

// Feature flag: when false the per-experiment "Overview" sub-tab (which holds the
// detailed scorecard) is suppressed in the rendered HTML. The Executive Summary at
// the top of the page is the primary scan surface; the analyst-grade scorecard is
// kept in code (renderOverview + buildScorecardHtml are still defined and tested)
// so we can re-enable by flipping this single flag without re-implementing anything.
// Flip to `true` to bring back the Overview tab + scorecard.
const SHOW_OVERVIEW_TAB = false;

const fmtPct = x => (x>=0?'+':'') + (x*100).toFixed(2) + '%';
const fmtPctOf = x => (x>=0?'+':'') + (x||0).toFixed(2) + '%';
const fmtP = p => p < 0.001 ? '<0.001' : p.toFixed(3);
const fmtMoney = x => (x>=0?'+':'') + '$' + Math.abs(x||0).toLocaleString(undefined,{maximumFractionDigits:0});
const fmtMoney2 = x => (x>=0?'+':'') + '$' + Math.abs(x||0).toFixed(4);
const fmtPp = x => (x>=0?'+':'') + (x||0).toFixed(2) + 'pp';

// Compact number / money formatters for scope-of-experiment subtitles. Used by both
// the Executive Summary cards and the Scorecard header to show UVs / M1 / Impressions /
// Clicks at a glance without the visual noise of full toLocaleString counts.
function compactNum(v) {
  if (v == null || isNaN(v)) return 'n/a';
  const a = Math.abs(v);
  if (a >= 1e9) return (v/1e9).toFixed(2) + 'B';
  if (a >= 1e6) return (v/1e6).toFixed(2) + 'M';
  if (a >= 1e3) return (v/1e3).toFixed(1) + 'k';
  return Math.round(v).toLocaleString();
}
function compactMoney(v) {
  return (v == null || isNaN(v)) ? 'n/a' : '$' + compactNum(v);
}

// Sum AB scope (Total UVs + Total M1 VFM) across daily rows. Sources from raw.overall
// (population-wide) so the totals match the headline AB metric cohort. Returns null
// fields when the underlying daily rows lack the required keys.
function abScopeTotals(D) {
  const daily = D.raw_overall_daily || [];
  if (!daily.length) return {uv: null, m1: null};
  let uv = 0, m1 = 0, hasUv = false, hasM1 = false;
  for (const r of daily) {
    if (r.uv_ctrl != null || r.uv_treat != null) {
      uv += (+(r.uv_ctrl) || 0) + (+(r.uv_treat) || 0); hasUv = true;
    }
    if (r.m1_ctrl != null || r.m1_treat != null) {
      m1 += (+(r.m1_ctrl) || 0) + (+(r.m1_treat) || 0); hasM1 = true;
    }
  }
  return {uv: hasUv ? uv : null, m1: hasM1 ? m1 : null};
}

// SEO scope: total post-period impressions + clicks for the Variant row in
// summary_tables.overall (the experiment's own URLs after release). Falls back to
// did.impressions / did.clicks when the summary_tables row isn't structured the way
// the renderer expects. Returns null fields when the SEO subagent didn't run.
function seoScopeTotals(D) {
  const seo = D.seo || {};
  if (seo.status !== 'ok') return {imp: null, clk: null};
  const rows = ((seo.summary_tables || {}).overall) || [];
  const variant = Array.isArray(rows) ? rows.find(r => String(r.label || '').startsWith('Variant')) : null;
  if (variant) {
    return {
      imp: (variant.post_impressions != null) ? variant.post_impressions : null,
      clk: (variant.post_clicks != null) ? variant.post_clicks : null,
    };
  }
  const did = seo.did || {};
  return {
    imp: (did.post_impressions != null) ? did.post_impressions : null,
    clk: (did.post_clicks != null) ? did.post_clicks : null,
  };
}

// Compose the full scope subtitle (deals · window · days · UVs · M1 · impressions ·
// clicks). Returns an HTML string with single-line layout so all context (scope +
// scale) sits in one row beneath the experiment name. Previously rendered as two
// lines (scope, then a smaller-grey "scale" line); user requested consolidation.
// Used in both the Exec Summary card and the Scorecard so a viewer gets the same
// context regardless of which surface they're looking at.
function buildScopeSubtitle(D, opts) {
  const wrapClass = (opts && opts.wrapClass) || 'exp-deals';
  const parts = [];
  if (D.n_deals != null) parts.push(`${Number(D.n_deals).toLocaleString()} deals`);
  if (D.start_date && D.end_date) parts.push(`${D.start_date} → ${D.end_date}`);
  // Days running: prefer the unfiltered (raw.overall) n — that's the count of daily
  // rows the AB stats are actually computed on. Fall back to a date-arithmetic
  // estimate when daily rows aren't loaded.
  const om = D.unfiltered_m1uv || D.overall_m1uv || null;
  let nDays = om ? om.n : null;
  if (nDays == null && D.start_date && D.end_date) {
    const ms = (Date.parse(D.end_date) - Date.parse(D.start_date));
    if (!isNaN(ms)) nDays = Math.round(ms / 86400000) + 1;
  }
  if (nDays != null) parts.push(`${nDays} day${nDays === 1 ? '' : 's'}`);

  const ab = abScopeTotals(D);
  const seo = seoScopeTotals(D);
  if (ab.uv != null) parts.push(`${compactNum(ab.uv)} UVs`);
  if (ab.m1 != null) parts.push(`${compactMoney(ab.m1)} M1+VFM`);
  if (seo.imp != null) parts.push(`${compactNum(seo.imp)} impressions`);
  if (seo.clk != null) parts.push(`${compactNum(seo.clk)} clicks`);

  return parts.length
    ? `<div class="${wrapClass}">${parts.join(' · ')}</div>`
    : '';
}

function colorFor(pct) {
  const x = Math.max(-3, Math.min(3, pct||0)) / 3;
  if (x >= 0) return `rgba(56,161,105,${0.15 + 0.55*x})`;
  return `rgba(229,62,62,${0.15 + 0.55*(-x)})`;
}
function seoColor(pp) {
  const x = Math.max(-30, Math.min(30, pp||0)) / 30;
  if (x >= 0) return `rgba(56,161,105,${0.15 + 0.55*x})`;
  return `rgba(229,62,62,${0.15 + 0.55*(-x)})`;
}

// Generic metric-row tint: scales `pct` to ±`scale` for full saturation, deepens
// when `p < 0.05`. Returns null for missing values so callers can render a
// transparent row. Scales differ by metric: AB %Δ uses ±3, SEO %Δ uses ±15,
// SEO CTR pp uses ±1, expected-funnel uses ±5.
function metricTint(pct, p, scale) {
  if (pct == null || isNaN(pct)) return null;
  const max = scale || 3;
  const x = Math.max(-max, Math.min(max, pct||0)) / max;
  const sig = p != null && p < 0.05;
  const opacity = sig ? (0.30 + 0.45*Math.abs(x)) : (0.10 + 0.25*Math.abs(x));
  if (x >= 0) return `rgba(56,161,105,${opacity.toFixed(3)})`;
  return `rgba(229,62,62,${opacity.toFixed(3)})`;
}

// Compose AB margin uplift with SEO traffic uplift into a directional total. M1/UV
// already captures CVR effects within the experiment population, so we only multiply
// it with SEO clicks %Δ — multiplying a third CVR factor would double-count. Returns
// null when both inputs are missing; falls back to whichever is present otherwise.
function expectedFunnelTotal(clicksPct, m1uvPct) {
  if (clicksPct == null && m1uvPct == null) return null;
  const c = (clicksPct == null ? 0 : clicksPct) / 100;
  const m = (m1uvPct == null ? 0 : m1uvPct) / 100;
  return ((1 + c) * (1 + m) - 1) * 100;
}

// MPV = margin per order. Derived from M1/UV and CVR so the funnel decomposition
// (Traffic × Conversion × Margin/order) sums back to M1/UV without double-counting:
//   (1+M1UV%) = (1+CVR%) × (1+MPV%)  →  MPV% = (1+M1UV%)/(1+CVR%) - 1
function mpvFromM1UVAndCVR(m1uvPct, cvrPct) {
  if (m1uvPct == null || cvrPct == null) return null;
  const denom = 1 + cvrPct/100;
  if (Math.abs(denom) < 1e-9) return null;
  return ((1 + m1uvPct/100) / denom - 1) * 100;
}

// Read the date label from a daily row. Subagents emit different keys depending on
// the source: most use `event_date`, some (AI_Summaries pattern) use `date`, the
// legacy ratio-only shape uses `d`. Falling through them all keeps lineChart agnostic
// so a key mismatch doesn't silently produce a chart with all-undefined x-axis
// labels (which Chart.js renders blank, looking like a broken chart).
function dailyLabel(row) {
  if (!row) return null;
  return row.event_date || row.date || row.d || null;
}

function lineChart(id, daily, ctrlKey, treatKey, ylabel) {
  const ctx = document.getElementById(id);
  if (!ctx || !daily || !daily.length) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {
    type:'line',
    data:{ labels: daily.map(dailyLabel),
      datasets:[
        {label:'Control',   data:daily.map(d=>d[ctrlKey] ?? d.ctrl),   borderColor:'#4A90D9', backgroundColor:'rgba(74,144,217,0.1)', tension:0.25, pointRadius:3},
        {label:'Treatment', data:daily.map(d=>d[treatKey] ?? d.treat), borderColor:'#E8734A', backgroundColor:'rgba(232,115,74,0.1)', tension:0.25, pointRadius:3},
      ]},
    options:{ responsive:true, maintainAspectRatio:false,
              plugins:{ legend:{position:'bottom'}, tooltip:{mode:'index',intersect:false} },
              scales:{ y:{ title:{display:true,text:ylabel} } } }
  });
}

function header() {
  const meta = document.getElementById('hdr-meta');
  const names = Object.keys(ROOT.experiments);
  const expLabel = `${names.length} experiment${names.length!==1?'s':''}`;
  meta.innerHTML = `
    <span class="stat"><strong>${expLabel}</strong></span>
    <span class="stat">run <strong>${ROOT.run_id}</strong></span>
    <span class="stat">data through <strong>${ROOT.data_through}</strong></span>`;
}

// Upstream summary_tables helpers — mirrors render.py::_seo_l2_row_lookup +
// _seo_l2_ctr_did_pp. Per-L2 CTR DiD must be derived in JS too because the
// Python build_payload only computes the *overall* CTR DiD; per-L2 stays
// inline so no payload is duplicated.

// AB-side L2 abbreviations → upstream's full L2 names. The heatmap is keyed on
// the AB category name; upstream emits human-readable category labels in the
// summary_tables `Variant — L2: <L1> / <L2>` format. When AB uses "TTD" and
// upstream uses "Things to Do", the suffix match would otherwise miss.
// Lookups are case-insensitive; values can be a string or a list of synonyms.
const _L2_ALIASES = {
  'TTD': 'Things to Do',
  'HBW': 'Beauty & Spas',
};

function _l2Candidates(l2Name) {
  // Returns the lowercase set of suffixes to try matching against upstream rows
  // for the given AB category name (the original, plus any alias).
  const out = new Set();
  if (l2Name == null) return out;
  const original = String(l2Name).trim();
  if (original) out.add(original.toLowerCase());
  const upper = original.toUpperCase();
  const alias = _L2_ALIASES[upper];
  if (alias) {
    if (Array.isArray(alias)) alias.forEach(a => out.add(String(a).trim().toLowerCase()));
    else out.add(String(alias).trim().toLowerCase());
  }
  return out;
}

function _l2LabelSuffix(label) {
  if (typeof label !== 'string') return null;
  const i = label.indexOf(': ');
  if (i < 0) return null;
  const after = label.slice(i + 2).trim();
  if (after.indexOf('/') >= 0) {
    return after.slice(after.lastIndexOf('/') + 1).trim();
  }
  return after;
}

function _seoL2VariantRow(seo, l2Name) {
  const block = ((((seo || {}).summary_tables || {}).by_category) || {}).L2;
  if (!block || !block.available) return null;
  const targets = _l2Candidates(l2Name);
  if (!targets.size) return null;
  for (const row of (block.rows || [])) {
    const label = row.label || '';
    if (!label.startsWith('Variant')) continue;
    const suffix = _l2LabelSuffix(label);
    if (suffix && targets.has(suffix.trim().toLowerCase())) return row;
  }
  return null;
}

function _seoL2PeerRow(seo, l2Name) {
  const block = ((((seo || {}).summary_tables || {}).by_category) || {}).L2;
  if (!block || !block.available) return null;
  const targets = _l2Candidates(l2Name);
  if (!targets.size) return null;
  for (const row of (block.rows || [])) {
    const label = row.label || '';
    if (!label.startsWith('All Groupon')) continue;
    const suffix = _l2LabelSuffix(label);
    if (suffix && targets.has(suffix.trim().toLowerCase())) return row;
  }
  return null;
}

function _ctrChangePp(row) {
  if (!row) return null;
  const preI = row.pre_impressions || 0;
  const postI = row.post_impressions || 0;
  if (preI <= 0 || postI <= 0) return null;
  const preC = row.pre_clicks || 0;
  const postC = row.post_clicks || 0;
  return ((postC / postI) - (preC / preI)) * 100.0;
}

function _seoL2CtrDidPp(seo, l2Name) {
  const v = _seoL2VariantRow(seo, l2Name);
  const p = _seoL2PeerRow(seo, l2Name);
  if (!v || !p) return null;
  const vPp = _ctrChangePp(v);
  const pPp = _ctrChangePp(p);
  if (vPp == null || pPp == null) return null;
  return vPp - pPp;
}

// Shared verdict-to-badge color mapping for both AB and SEO scoreboard chips.
// Case-insensitive (some upstream paths emit lowercase). Unknown values fall to
// `badge-prelim` (amber) rather than `badge-fail` (red) — a missing/unrecognised
// verdict is ambiguous, not bad.
function verdictBadgeCls(verdict) {
  const v = String(verdict == null ? '' : verdict).trim().toUpperCase();
  if (v === 'SHIP' || v === 'POSITIVE') return 'badge-pass';
  if (v === 'KILL' || v === 'NEGATIVE' || v === 'PAUSE') return 'badge-fail';
  if (v === 'REDESIGN') return 'badge-fail';
  if (v === 'HOLD' || v === 'EXTEND' || v === 'EARLY' || v === 'INCONCLUSIVE' || v === 'MIXED') return 'badge-prelim';
  return 'badge-prelim';
}

// CEO Executive Summary — top-level view above the analyst scoreboard. Each card
// renders the experiment name + verdict badges, four headline metric tiles
// (M1/UV %Δ, CVR %Δ, SEO Clicks DiD, composed Total margin %Δ), and a one-sentence
// takeaway (preferred from the evaluator's hand-written narrative; synthesized when
// the .docx narrative isn't available). Designed for a 30-second scan: sign of each
// metric is encoded by tile color, magnitude is the visible number, takeaway answers
// "so what".
function renderExecSummary() {
  const root = document.getElementById('exec-summary');
  if (!root) return;
  const exps = Object.entries(ROOT.experiments);
  if (!exps.length) { root.innerHTML = '<p class="muted">No experiments to summarize.</p>'; return; }

  // Top-level tally. Counts the COMPOSED Final verdict (DEPLOY / HOLD / KILL) so the
  // top-of-report headline answers the same question every exec card answers — what
  // to do given BOTH the AB and SEO results. Falls back to the AB-only verdict for
  // older runs that lack `composed_verdict`.
  const decisions = exps.map(([n, D]) => {
    const c = String(D.composed_verdict || '').toUpperCase();
    if (c) return c;
    const ab = String(D.ab_filtered_verdict || '').toUpperCase();
    return ab === 'SHIP' ? 'DEPLOY' : ab === 'KILL' ? 'KILL' : 'HOLD';
  });
  const deploys = decisions.filter(v => v === 'DEPLOY').length;
  const kills = decisions.filter(v => v === 'KILL').length;
  const holds = exps.length - deploys - kills;
  const tally = `
    <span class="tally"><strong>${exps.length}</strong> experiment${exps.length!==1?'s':''} evaluated</span>
    <span class="tally"><strong>${deploys}</strong> deploy</span>
    <span class="tally"><strong>${holds}</strong> hold</span>
    <span class="tally"><strong>${kills}</strong> kill</span>`;

  const cards = exps.map(([n, D]) => buildExecCard(n, D)).join('');
  root.innerHTML = `<div class="exec-overview">${tally}</div><div class="exec-cards">${cards}</div>`;
}

// AB data-source / SRM badge. Three states:
//   - "DATA: ORIGINAL"    — raw bcookie SRM passed; headline numbers come from raw cohort.
//   - "DATA: REMEDIATED"  — raw SRM failed BUT active_visitor remediation passed; headline
//                           numbers were swapped to the remediated view, so the reader
//                           should know the displayed AB metrics aren't from the full pop.
//   - "SRM FAIL"          — neither passed; headline numbers should be read with caution.
// Prefers AB-Overall SRM since the exec card's AB metrics come from raw.overall.
function dataSourceBadge(D) {
  const srmObj = (D.srm_overall && Object.keys(D.srm_overall).length)
    ? D.srm_overall
    : (D.srm_filtered || {});
  if (!srmObj || !Object.keys(srmObj).length) return '';
  const promoted = srmObj.promoted_from === 'remediated';
  const verdict = srmObj.verdict || 'pass';
  const p = srmObj.p_value;
  const pStr = (p != null && !isNaN(p)) ? ` (chi² p=${fmtP(p)})` : '';
  if (promoted) {
    return `<span class="badge badge-prelim badge-tip" title="raw bcookie SRM failed; metrics shown use the active_visitor-remediated cohort${pStr}">DATA: REMEDIATED</span>`;
  }
  if (verdict !== 'pass') {
    return `<span class="badge badge-fail badge-tip" title="SRM ${verdict}${pStr} — no remediation rescued the split; numbers may be biased">SRM FAIL</span>`;
  }
  return `<span class="badge badge-final badge-tip" title="raw bcookie SRM passed${pStr} — metrics shown use the unmodified cohort">DATA: ORIGINAL</span>`;
}

// Net Margin/Visitor tile — replaces the old "Total estimated margin impact" tile.
// Shows the composed point estimate and the [lower, upper] CI band when the CI
// rule is in effect. Falls back to the legacy product-of-pcts display when the
// payload doesn't carry CI fields (degraded run, missing SEs).
//
// CI band coloring follows the verdict rule that uses it:
//   - lower > +MWSE → pos (green) — significantly positive and material
//   - upper < -MWSE → neg (red)   — significantly negative
//   - straddles    → neu (gray)   — HOLD
// The MWSE comes from the payload so the tile and the verdict can never disagree.
function ciTile(D) {
  const basis = D.composed_basis;
  const point = D.composed_net_pct;
  const lo = D.composed_lower_pct;
  const hi = D.composed_upper_pct;
  const mwse = (D.composed_mwse_pct != null) ? D.composed_mwse_pct : 0.5;
  const alpha = D.composed_alpha;
  const ciPct = (alpha != null && !isNaN(alpha)) ? Math.round((1 - alpha) * 100) : 90;

  // Legacy fallback: no point estimate at all — show n/a.
  if (point == null || isNaN(point)) {
    return `<div class="exec-tile na"><div class="exec-tlabel">Net margin / visitor</div><div class="exec-tval">n/a</div></div>`;
  }

  // No CI bounds (basis = 'matrix') — show the point alone with a basis hint so the
  // reader knows the rigor level dropped.
  if (lo == null || hi == null || isNaN(lo) || isNaN(hi)) {
    const cls = point > 0.5 ? 'pos' : point < -0.5 ? 'neg' : 'neu';
    return `<div class="exec-tile ${cls}">
      <div class="exec-tlabel">Net margin / visitor <span class="exec-tile-basis" title="No CI — verdict from rule-based matrix">matrix</span></div>
      <div class="exec-tval">${fmtPctOf(point)}</div>
      <div class="exec-tp">CI unavailable</div>
    </div>`;
  }

  const cls = lo > mwse ? 'pos' : hi < -mwse ? 'neg' : 'neu';
  const basisHint = basis === 'ci' ? `${ciPct}% CI`
                   : basis === 'guardrail' ? 'guardrail'
                   : basis;
  return `<div class="exec-tile ${cls} sig">
    <div class="exec-tlabel">Net margin / visitor <span class="exec-tile-basis">${escapeText(basisHint || '')}</span></div>
    <div class="exec-tval">${fmtPctOf(point)}</div>
    <div class="exec-tp">${ciPct}% CI [${fmtPctOf(lo)}, ${fmtPctOf(hi)}]</div>
  </div>`;
}

// Per-experiment exec card. Pulls the same headline values the scorecard uses
// (unfiltered / population-wide AB metrics + SEO DiD vs synthetic peer + composed funnel).
function buildExecCard(name, D) {
  const verdict = (D.ab_filtered_verdict || '').toUpperCase();
  const om = D.unfiltered_m1uv || D.overall_m1uv || null;
  const oc = D.unfiltered_cvr  || D.overall_cvr  || null;
  const did = (D.seo && D.seo.did) || {};
  const power = (D.seo && D.seo.power_analysis) || {};
  const m1uvPct = om ? om.mean_delta_pct : null;
  const m1uvP   = om ? om.p_value : null;
  const cvrPct  = oc ? oc.mean_delta_pct : null;
  const cvrP    = oc ? oc.p_value : null;
  const clkPct  = (did.did_clicks_pct == null) ? null : did.did_clicks_pct;
  const impPct  = (did.did_impressions_pct == null) ? null : did.did_impressions_pct;
  const seoP    = power.p_value;
  const totalPct = expectedFunnelTotal(clkPct, m1uvPct);

  // SEO status: 'ok' = pipeline ran; 'no_urls'/'failed' surface as a single
  // status pill. Signal strength label (PRELIMINARY/FINAL) is shown as a badge
  // AND in a descriptive caption below the header. Sources:
  // `seo.overall.signal_strength` ('full' ≥28 post-days → FINAL, 'partial' <28 →
  // PRELIMINARY), `seo.overall.effective_post_days`, and
  // `seo.power_analysis.current_power`.
  const seoStatusRaw = D.seo && D.seo.status;
  const seoOk = seoStatusRaw === 'ok';
  const seoVerdict = seoOk ? (((D.seo && D.seo.verdict) || '?') + '').toUpperCase() : null;
  const seoOverall = (D.seo && D.seo.overall) || {};
  const seoSig = seoOverall.signal_strength;
  const seoPostDays = seoOverall.effective_post_days;
  const seoPower = (D.seo && D.seo.power_analysis && D.seo.power_analysis.current_power);
  const seoLabel = seoSig === 'full' ? 'FINAL' : seoSig === 'partial' ? 'PRELIMINARY' : null;
  const seoLabelBadgeCls = seoLabel === 'FINAL' ? 'badge-final' : 'badge-prelim';
  const seoVerdictBadgeCls = verdictBadgeCls(seoVerdict);

  // Card left-border color now mirrors the COMPOSED Final verdict (DEPLOY/HOLD/KILL),
  // not the AB-only verdict. This keeps the visual hierarchy consistent with the
  // Final row at the top of the takeaway block. Falls back to AB-derived class for
  // backward compat if `composed_verdict` is absent (older runs).
  const finalVerdict = String(D.composed_verdict || '').toUpperCase();
  const verdictCardCls = finalVerdict === 'DEPLOY' ? 'exec-ship'
    : finalVerdict === 'KILL' ? 'exec-kill'
    : finalVerdict === 'HOLD' ? 'exec-other'
    : (verdict === 'SHIP' ? 'exec-ship' : verdict === 'KILL' ? 'exec-kill' : 'exec-other');
  const verdictBadgeCls2 = verdict === 'SHIP' ? 'badge-verdict-ship' : verdict === 'KILL' ? 'badge-verdict-kill' : 'badge-verdict-neutral';
  const labelBadgeCls = (D.ab_label || '').startsWith('FINAL') ? 'badge-final' : 'badge-prelim';

  // Tile sign-classification thresholds: AB %Δ uses ±0.5% (anything inside is noise),
  // SEO clicks pp uses ±1pp (the typical noise floor on partial-signal SEO runs).
  const tile = (label, val, p, sigThresh) => {
    if (val == null || isNaN(val)) {
      return `<div class="exec-tile na"><div class="exec-tlabel">${label}</div><div class="exec-tval">n/a</div></div>`;
    }
    const cls = val > sigThresh ? 'pos' : val < -sigThresh ? 'neg' : 'neu';
    const sigClass = (p != null && p < 0.05) ? ' sig' : '';
    const star = (p != null && p < 0.05) ? '<span class="exec-tstar">★</span>' : '';
    const pStr = (p != null) ? `<div class="exec-tp">p=${fmtP(p)}</div>` : '';
    return `<div class="exec-tile ${cls}${sigClass}">
      <div class="exec-tlabel">${label}</div>
      <div class="exec-tval">${fmtPctOf(val)}${star}</div>
      ${pStr}
    </div>`;
  };

  // SEO TOO EARLY tile — used in place of the n/a tile when the experiment's
  // SEO release date is set but fewer than 14 days have elapsed. Shows the
  // day-counter so the reader knows when the next run will include SEO data.
  // The orchestrator skips SEO dispatch entirely in this window, so the AB-only
  // composition stands until 14 days mature.
  const tooEarlyTile = (label) => {
    const elapsed = (D.seo_days_elapsed != null) ? D.seo_days_elapsed : 0;
    const total = (D.seo_days_needed_total != null) ? D.seo_days_needed_total : 14;
    return `<div class="exec-tile neu"><div class="exec-tlabel">${label}</div><div class="exec-tval" style="font-size:0.95rem;">TOO EARLY</div><div class="exec-tp">${elapsed}/${total} days needed</div></div>`;
  };

  // Two-line subtitle for the exec card: scope (deals · window · days) + scale (UVs ·
  // M1 · impressions · clicks). Same content the scorecard shows so a viewer gets the
  // same context wherever they look. wrapClass is exec-card-subtitle so styling matches
  // the card's typography.
  const subtitleHtml = buildScopeSubtitle(D, {wrapClass: 'exec-card-subtitle'});
  const expName = D.alternate_name || name;
  const takeawayHtml = renderExecTakeaway(D);

  // Header badges: two side-by-side verdict groups (AB + SEO) so the reader sees
  // BOTH verdicts AND BOTH preliminary/final states at a glance. Previously only
  // the AB pair was shown, so SEO PRELIMINARY/INCONCLUSIVE state was invisible
  // in the exec view (only buried in the analyst scorecard below).
  //
  // AB data-source badge: shows whether the displayed metrics use the raw bcookie
  // cohort or the active_visitor-remediated one. Always visible so the reader
  // knows which dataset the headline numbers came from. Prefers AB-Overall SRM
  // since the headline M1/UV / CVR are sourced from overall too.
  const abDataSource = dataSourceBadge(D);
  const abGroupHtml = `
    <div class="exec-verdict-group">
      <span class="exec-verdict-label">AB</span>
      <span class="badge ${labelBadgeCls}">${escapeText(D.ab_label || '?')}</span>
      <span class="badge ${verdictBadgeCls2}">${verdict || '?'}</span>
      ${abDataSource}
    </div>`;
  // SEO group: single-row layout. PRELIMINARY/FINAL badge + verdict badge +
  // inline meta (post-days, power). The verbose caption beneath the header
  // ("PARTIAL SIGNAL — N post-period days...") is folded into this row so the
  // entire AB+SEO summary lives on one line under the experiment name.
  const seoPowerPct = (seoPower != null && !isNaN(seoPower))
    ? `${Math.round(seoPower * 100)}%` : null;
  let seoGroupHtml = '';
  if (seoOk) {
    const seoLabelBadge = seoLabel
      ? `<span class="badge ${seoLabelBadgeCls}">${seoLabel}</span>`
      : '';
    const postDaysMeta = seoPostDays != null
      ? `<span class="exec-verdict-meta">${seoPostDays}/28 post-days</span>` : '';
    const powerMeta = seoPowerPct
      ? `<span class="exec-verdict-meta">power ${seoPowerPct}</span>` : '';
    seoGroupHtml = `
      <div class="exec-verdict-group">
        <span class="exec-verdict-label">SEO</span>
        ${seoLabelBadge}
        <span class="badge ${seoVerdictBadgeCls}">${seoVerdict}</span>
        ${postDaysMeta}
        ${powerMeta}
      </div>`;
  } else if (D.seo_too_early) {
    // SEO release < 14 days old: orchestrator intentionally skipped dispatch.
    // Surface the day-counter in the badge so the reader sees PRELIMINARY state
    // without needing to read the tile contents.
    const elapsed = (D.seo_days_elapsed != null) ? D.seo_days_elapsed : 0;
    const total = (D.seo_days_needed_total != null) ? D.seo_days_needed_total : 14;
    seoGroupHtml = `
      <div class="exec-verdict-group" title="SEO requires ${total} days post-release before a preliminary signal is meaningful">
        <span class="exec-verdict-label">SEO</span>
        <span class="badge badge-prelim">TOO EARLY</span>
        <span class="exec-verdict-meta">${elapsed}/${total} days</span>
      </div>`;
  } else if (D.seo) {
    seoGroupHtml = `
      <div class="exec-verdict-group">
        <span class="exec-verdict-label">SEO</span>
        <span class="badge badge-prelim">${escapeText(seoStatusRaw || 'unknown')}</span>
      </div>`;
  }

  // Final verdict row — moved ABOVE the tiles so the bottom-line recommendation
  // is the first thing the reader sees after the experiment name. The same
  // markup used to live inside .exec-takeaway below; relocating it answers the
  // "what to do" question before "what are the numbers" rather than after.
  const finalRowHtml = buildFinalRow(D);

  // SEO tile rendering: when the orchestrator skipped SEO because the 14-day
  // window hasn't matured, show TOO EARLY tiles instead of n/a. Otherwise the
  // standard tile() handles both the data-present and the no-SEO-data fallback.
  const seoClicksTile = D.seo_too_early ? tooEarlyTile('SEO Clicks') : tile('SEO Clicks', clkPct, seoP, 1.0);
  const seoImpTile    = D.seo_too_early ? tooEarlyTile('SEO Impressions') : tile('SEO Impressions', impPct, seoP, 1.0);

  return `<div class="exec-card ${verdictCardCls}">
    <div class="exec-card-header">
      <div class="exec-card-name">${escapeText(expName)}</div>
      <div class="exec-card-badges">
        ${abGroupHtml}
        ${seoGroupHtml}
      </div>
    </div>
    ${subtitleHtml}
    ${finalRowHtml}
    <div class="exec-card-tiles">
      ${ciTile(D)}
      ${tile('M1+VFM/UV %Δ',                  m1uvPct, m1uvP, 0.5)}
      ${tile('CVR %Δ',                        cvrPct,  cvrP,  0.5)}
      ${seoClicksTile}
      ${seoImpTile}
    </div>
    ${takeawayHtml}
  </div>`;
}

// Build the Final verdict row HTML. Extracted from renderExecTakeaway so the
// row can be placed ABOVE the tiles (where it belongs as the bottom-line
// recommendation) while the rest of the takeaway block (Confidence/Why/Action)
// stays below. Same payload fields, same look — just relocated.
function buildFinalRow(D) {
  const finalVerdict = String(D.composed_verdict || '').toUpperCase();
  if (!finalVerdict) return '';
  const finalRationale = D.composed_rationale || '';
  const finalCls = D.composed_cls || '';
  const finalBasis = D.composed_basis;
  const basisLabel = finalBasis === 'ci' ? 'CI'
    : finalBasis === 'guardrail' ? 'guardrail'
    : finalBasis === 'matrix' ? 'matrix'
    : '';
  const basisChip = basisLabel
    ? `<span class="exec-final-basis" title="Verdict basis: ${escapeText(basisLabel)}">${basisLabel}</span>`
    : '';
  // When SEO is too early we overlay a PRELIMINARY tag on the verdict pill so
  // the reader can't mistake an AB-only composed verdict for the full picture.
  const prelimChip = D.seo_too_early
    ? `<span class="exec-final-basis" style="background:#fefcbf;color:#744210;" title="SEO not yet eligible — verdict is AB-only">PRELIMINARY</span>`
    : '';
  return `<div class="exec-final-strip ${finalCls}">
    <span class="exec-tk-label">Final</span>
    <span><span class="exec-final-pill">${finalVerdict}</span>${prelimChip}${basisChip}<span class="exec-final-rationale">${escapeText(finalRationale)}</span></span>
  </div>`;
}

// Render the multi-line "Takeaway" block in the Exec Summary card. Three rows:
//   1. Confidence — explicit statement of statistical significance (which metrics
//      reached p<0.05, which didn't). Avoids the failure mode of a CEO reading a
//      bold number and assuming it's a confirmed effect when it's actually n.s.
//      When overall is not significant, surfaces subset-level significance from
//      the evaluator narrative (e.g., "Web subset shows Cohen's d=0.345").
//   2. Why — one sentence from the evaluator's narrative (or synthesized)
//      explaining what drove the result.
//   3. Action — first action item from the evaluator narrative or a synthesized
//      recommendation aligned with the verdict.
function renderExecTakeaway(D) {
  const verdict = (D.ab_filtered_verdict || '').toUpperCase();
  const om = D.unfiltered_m1uv || D.overall_m1uv || null;
  const oc = D.unfiltered_cvr  || D.overall_cvr  || null;
  const did = (D.seo && D.seo.did) || {};
  const seoP = ((D.seo && D.seo.power_analysis) || {}).p_value;
  const m1uvSig = !!(om && om.p_value != null && om.p_value < 0.05);
  const cvrSig  = !!(oc && oc.p_value != null && oc.p_value < 0.05);
  const seoSig  = !!(seoP != null && seoP < 0.05);

  // Confidence row. Three states: full significance, partial, none. When none of the
  // three primary metrics reached p<0.05, lean on the evaluator's "What remains
  // uncertain" narrative — that's where subset-level (per-platform / per-category)
  // significance often hides for tests with weak overall signal.
  const sigParts = [];
  if (m1uvSig) sigParts.push('M1+VFM/UV');
  if (cvrSig) sigParts.push('CVR');
  if (seoSig) sigParts.push('SEO');
  let confidenceCls = 'exec-conf-low';
  let confidenceText;
  if (sigParts.length === 0) {
    confidenceCls = 'exec-conf-low';
    confidenceText = `<strong>Not statistically significant</strong> — no headline metric reached p&lt;0.05; numbers are <em>directional only</em>.`;
    // Hint at subset evidence when present in the narrative.
    const narr = D.evaluation_narrative || {};
    const platformHint = (narr.step_3_platform_results && narr.step_3_platform_results.length)
      ? narr.step_3_platform_results.find(it => /web|touch|desktop|mobile/i.test(it.text))
      : null;
    if (platformHint) {
      confidenceText += ` See platform breakdown — significance may concentrate in a subset.`;
    }
  } else if (sigParts.length === 3) {
    confidenceCls = 'exec-conf-high';
    confidenceText = `<strong>Statistically significant on all three headline metrics</strong> (M1+VFM/UV, CVR, SEO at p&lt;0.05).`;
  } else {
    confidenceCls = 'exec-conf-mid';
    confidenceText = `<strong>Statistically significant on ${sigParts.join(' &amp; ')}</strong> (p&lt;0.05); other headline metrics directional only.`;
  }

  // "Why" row — pull a substantive sentence from the evaluator narrative when present.
  // First bullet of "What the data shows" is hand-curated; preferred. Falls back to
  // step bodies, then synthesis.
  const whyText = execTakeaway(D);

  // "Action" row — first action item if available; else a recommendation aligned with
  // verdict + significance. We avoid prescribing SHIP/KILL when significance is low
  // since the evaluator may have done it on practical grounds — defer to their action
  // list when the doc has one.
  const narr = D.evaluation_narrative || {};
  let actionText;
  if (narr.action_items && narr.action_items.length) {
    actionText = narr.action_items[0].text;
  } else if (verdict === 'KILL' && sigParts.length > 0) {
    actionText = `Recommend KILL — significant negative signal.`;
  } else if (verdict === 'KILL') {
    actionText = `Recommend KILL on practical grounds — direction is negative even though overall p≥0.05.`;
  } else if (verdict === 'SHIP' && sigParts.length > 0) {
    actionText = `Recommend SHIP — significant positive signal.`;
  } else if (verdict === 'SHIP') {
    actionText = `Recommend SHIP on practical grounds — direction is positive even though overall p≥0.05.`;
  } else if (sigParts.length === 0) {
    actionText = `Hold or extend. Overall result is inconclusive; check subsets before deciding.`;
  } else {
    actionText = `Verdict ${verdict} — see full evaluation report for context.`;
  }

  // Final verdict moved above the tiles (see buildFinalRow); the takeaway block
  // now contains only Confidence / Why / Action rows.

  return `
    <div class="exec-takeaway">
      <div class="exec-takeaway-row exec-conf ${confidenceCls}"><span class="exec-tk-label">Confidence</span><span>${confidenceText}</span></div>
      <div class="exec-takeaway-row"><span class="exec-tk-label">Why</span><span>${escapeText(whyText)}</span></div>
      <div class="exec-takeaway-row"><span class="exec-tk-label">Action</span><span>${escapeText(actionText)}</span></div>
    </div>`;
}

// Pick a single CEO-grade sentence for the exec card. Priority order:
//   1. First bullet of evaluator's "What the data shows" (hand-curated, most reliable)
//   2. First action item ("Stop the experiment immediately…")
//   3. First sentence of "Final recommendation" prose
//   4. First sentence of "Executive summary" (rarely present in current docx layouts)
//   5. First sentence of Step 7 (practical-significance) prose — fallback for docs
//      where the curated subsections are empty (AI_Summaries pattern)
//   6. Synthesized sentence from headline metrics (last resort, when no docx loaded)
function execTakeaway(D) {
  const n = D.evaluation_narrative || {};
  // Extract the first complete sentence from narrative prose. Original regex
  // (`/^[^.!?]+[.!?]/`) stopped at ANY period, which truncated decimals
  // ("Cohen's d = 0.042" → "Cohen's d = 0") and money ("$2.45 difference" → "$2")
  // mid-token, producing unfinished sentences in the Exec Summary "Why" row.
  // Current rule:
  //   - Period/!/? must be followed by whitespace or end-of-string (skips decimals,
  //     "$2.45", "p=0.001", "v4.0" — those have digits after the dot, no space).
  //   - Require ≥25 chars before the break to avoid stopping on short abbreviations
  //     at sentence start ("vs.", "U.S.", "Mr.").
  //   - If the next non-whitespace character is lowercase, treat the period as
  //     mid-sentence abbreviation ("vs. control" → keep going) and continue scanning.
  const firstSentence = (s) => {
    const str = String(s || '').trim();
    if (!str) return '';
    const MIN_LEN = 25;
    const re = /[.!?](?=\s+\S|\s*$)/g;
    let m;
    while ((m = re.exec(str)) !== null) {
      const end = m.index + 1;
      if (end < MIN_LEN) continue;
      const after = str.slice(end).match(/^\s+(\S)/);
      if (after && /[a-z]/.test(after[1])) continue;
      return str.slice(0, end).trim();
    }
    return str.length > 240 ? str.slice(0, 237).trim() + '…' : str;
  };
  if (n.what_the_data_shows && n.what_the_data_shows.length) {
    return firstSentence(n.what_the_data_shows[0].text);
  }
  if (n.action_items && n.action_items.length) {
    return firstSentence(n.action_items[0].text);
  }
  if (n.final_recommendation && n.final_recommendation.length) {
    return firstSentence(n.final_recommendation[0].text);
  }
  if (n.executive_summary) {
    return firstSentence(n.executive_summary);
  }
  if (n.step_7_practical && n.step_7_practical.length) {
    return firstSentence(n.step_7_practical[0].text);
  }
  // Fallback synthesis. Keep it short — CEO-grade sentence, not analyst prose.
  const verdict = (D.ab_filtered_verdict || '').toUpperCase();
  const om = D.unfiltered_m1uv || D.overall_m1uv || null;
  const oc = D.unfiltered_cvr  || D.overall_cvr  || null;
  const did = (D.seo && D.seo.did) || {};
  const m1 = om ? om.mean_delta_pct : null;
  const cv = oc ? oc.mean_delta_pct : null;
  const ck = (did.did_clicks_pct == null) ? null : did.did_clicks_pct;
  const fmt = (v) => v == null ? 'n/a' : fmtPctOf(v);
  if (verdict === 'KILL') return `Recommend KILL — M1+VFM/UV ${fmt(m1)}, CVR ${fmt(cv)}, SEO clicks ${fmt(ck)} — net negative funnel.`;
  if (verdict === 'SHIP') return `Recommend SHIP — M1+VFM/UV ${fmt(m1)}, CVR ${fmt(cv)}, SEO clicks ${fmt(ck)} — net positive funnel.`;
  return `Inconclusive — M1+VFM/UV ${fmt(m1)}, CVR ${fmt(cv)}, SEO clicks ${fmt(ck)} — needs more data or clearer signal.`;
}

// Builds the per-experiment scorecard HTML used inside the new Overview sub-tab.
// Replaces the global scoreboard() function — the Executive Summary now owns the
// page-level scan, while the scorecard delivers the analyst-grade detail per
// experiment. Returns a single .card HTML string; caller wraps with .scoreboard.
function buildScorecardHtml(name, D) {
    const v = D.ab_filtered_verdict || '?';
    const cls = v === 'SHIP' ? 'win' : v === 'KILL' ? 'lose' : 'flat';
    // FINAL: neutral gray (no green) — completion is not a result. PRELIM keeps amber
    // because in-progress runs do warrant a visual reminder.
    const labelBadge = (D.ab_label||'').startsWith('FINAL') ? 'badge-final' : 'badge-prelim';

    // SRM source: prefer the unfiltered (raw.overall) SRM since the AB hero metrics also
    // come from raw.overall. Falls back to filtered SRM if overall is missing.
    const srmObj = (D.srm_overall && Object.keys(D.srm_overall).length) ? D.srm_overall : (D.srm_filtered || {});
    const srm = srmObj.verdict || 'pass';
    const srmPromoted = srmObj.promoted_from === 'remediated';
    // Pill visibility: hide when SRM passes cleanly (the common case — pill adds noise).
    // Show neutral when active-visitor remediation kicked in (post-remediation pass is the
    // current value, so "warning, not error"). Show red on hard fail (important to flag).
    let srmPillHtml = '';
    if (srmPromoted) {
      srmPillHtml = `<span class="badge badge-neutral" title="raw bcookie SRM failed; active_visitor remediation passed (chi² p=${fmtP(srmObj.p_value||1)})">SRM remediated (active_visitor)</span>`;
    } else if (srm !== 'pass') {
      srmPillHtml = `<span class="badge badge-fail">SRM ${srm}</span>`;
    }

    // AB hero metric source: unfiltered (population-wide) M1/UV + CVR from raw.overall.daily.
    // Falls back to legacy overall_m1uv / overall_cvr when the unfiltered shape isn't present.
    const om = D.unfiltered_m1uv || D.overall_m1uv || null;
    const oc = D.unfiltered_cvr  || D.overall_cvr  || null;
    const m1uvPct = om ? om.mean_delta_pct : null;
    const m1uvP   = om ? om.p_value : null;
    const cvrPct  = oc ? oc.mean_delta_pct : null;
    const cvrP    = oc ? oc.p_value : null;

    // SEO headline values (clicks / impressions only — DiD CTR pp dropped from card).
    const seoStatus = D.seo && D.seo.status === 'ok';
    const did = (D.seo && D.seo.did) || {};
    const power = (D.seo && D.seo.power_analysis) || {};
    const seoVerdict = seoStatus ? ((D.seo && D.seo.verdict) || '?') : null;
    const impPct = (did.did_impressions_pct == null) ? null : did.did_impressions_pct;
    const clkPct = (did.did_clicks_pct == null) ? null : did.did_clicks_pct;
    const seoP   = power.p_value;
    const seoSig = D.seo && D.seo.signal_level;
    const seoSigBadgeCls = seoSig === 'full' ? 'badge-pass' : seoSig === 'partial' ? 'badge-prelim' : 'badge-fail';

    // Funnel composition. Traffic × Conversion × Margin/order. MPV is derived from
    // M1/UV and CVR so the three stages compose cleanly back to (1+SEO)(1+M1UV)-1.
    const mpvPct = mpvFromM1UVAndCVR(m1uvPct, cvrPct);
    const totalPct = expectedFunnelTotal(clkPct, m1uvPct);

    // Renders one colored metric row. `kind` is 'pct' for percentages or 'pp' for
    // percentage points; `scale` controls saturation breakpoint for tint intensity.
    const metricRow = (label, val, p, scale, kind, hero) => {
      const fmt = kind === 'pp' ? fmtPp : fmtPctOf;
      const cls2 = 'metric-row' + (hero ? ' hero' : '');
      if (val == null || isNaN(val)) {
        return `<div class="${cls2}"><span class="lbl">${label}</span><span class="muted">n/a</span></div>`;
      }
      const bg = metricTint(val, p, scale);
      const sigStar = (p != null && p < 0.05) ? ' <span class="sigstar">★</span>' : '';
      const pStr = (p != null) ? `<span class="pmeta">p=${fmtP(p)}</span>` : '';
      return `<div class="${cls2}" style="background:${bg||'transparent'}">
                <span class="lbl">${label}</span>
                <span><strong>${fmt(val)}</strong>${sigStar}${pStr}</span>
              </div>`;
    };

    // Header: experiment name, then deals subtitle (small font), then label + (optional)
    // SRM pill. SRM pill suppressed entirely on clean pass.
    // Scorecard subtitle: scope + scale. Reuses the same buildScopeSubtitle helper as
    // the exec summary cards so analyst and CEO views show identical context.
    const dealsSubtitle = buildScopeSubtitle(D, {wrapClass: 'exp-deals'});
    const headerHtml = `
      <h3>${name}</h3>
      ${dealsSubtitle}
      <div style="margin:6px 0 10px">
        <span class="badge ${labelBadge}">${D.ab_label||'?'}</span>
        ${srmPillHtml}
      </div>`;

    // Expected funnel impact — top section. Two-tier explanation:
    //   1. The honest math (what we actually compute): Traffic × Margin-per-visitor.
    //      M1/UV is the AB margin-per-visitor metric and ALREADY captures CVR + MPV;
    //      we never multiply three independent factors.
    //   2. The decomposition (what's inside Margin-per-visitor): CVR × Margin-per-order.
    //      Margin-per-order is derived as (1+M1/UV)/(1+CVR)−1 so the decomposition
    //      sums back to M1/UV exactly.
    // The full formula + double-counting note moved to the Details block.
    let expectedSection = '';
    if (totalPct != null) {
      const fmtSign = (v) => v == null ? 'n/a' : fmtPctOf(v);
      const totalLine = (clkPct != null && m1uvPct != null)
        ? `<strong>Traffic ${fmtSign(clkPct)}</strong> × <strong>Margin/visitor ${fmtSign(m1uvPct)}</strong> = <strong>${fmtSign(totalPct)}</strong>`
        : (m1uvPct != null
            ? `<strong>Margin/visitor ${fmtSign(m1uvPct)}</strong> (no SEO traffic signal — total is the AB margin uplift only)`
            : `<strong>Traffic ${fmtSign(clkPct)}</strong> (no AB margin signal)`);
      const decompLine = (cvrPct != null && mpvPct != null)
        ? `<span style="color:#a0aec0">Margin/visitor decomposes as: CVR ${fmtSign(cvrPct)} × Margin/order ${fmtSign(mpvPct)}</span>`
        : '';
      expectedSection = `
        <div class="sec-title">Estimated total margin impact</div>
        ${metricRow('Total margin %Δ', totalPct, null, 5, 'pct', true)}
        <div class="funnel-detail">
          ${totalLine}
          ${decompLine ? `<br>${decompLine}` : ''}
        </div>`;
    }

    // AB Test section — colored, important metrics first. Sourced from raw.overall
    // (population-wide / unfiltered) so the headline matches the canonical AB test result.
    const abSection = `
      <div class="sec-title">AB Population-wide</div>
      ${metricRow('M1+VFM/UV %Δ', m1uvPct, m1uvP, 3, 'pct', true)}
      ${metricRow('CVR %Δ',   cvrPct,  cvrP,  3, 'pct', false)}
      <div class="row" style="padding-top:6px"><span class="lbl">AB verdict</span><span><span class="badge ${verdictBadgeCls(v)}">${v}</span></span></div>`;

    // SEO section — colored DiD clicks / impressions only (CTR pp removed; was rarely
    // populated and added noise).
    let seoSection = '';
    if (seoStatus) {
      seoSection = `
        <div class="sec-title">SEO (DiD vs synthetic peer)</div>
        ${metricRow('DiD Clicks %',      clkPct, seoP, 15, 'pct', true)}
        ${metricRow('DiD Impressions %', impPct, seoP, 15, 'pct', false)}
        <div class="row" style="padding-top:6px"><span class="lbl">SEO verdict</span><span><span class="badge ${verdictBadgeCls(seoVerdict)}">${seoVerdict}</span> <span class="badge ${seoSigBadgeCls}">${seoSig||'?'}</span></span></div>`;
    } else if (D.seo) {
      seoSection = `
        <div class="sec-title">SEO</div>
        <div class="row"><span class="lbl">Status</span><span class="muted">${D.seo.status||'unknown'}${D.seo.reason ? ' — ' + D.seo.reason : ''}</span></div>`;
    }

    // De-emphasized details — collapsed; no coloring; muted text. Funnel formula text,
    // SRM χ² rows (always — both clean and remediated cases), runway projection, and the
    // SEO peer-cohort caveat all live here.
    const runway = D.runway_filtered;
    let runwayLine = '';
    if (runway && !runway.already_significant) {
      if (runway.infeasible) {
        runwayLine = `<div class="row"><span class="lbl">Runway to p&lt;0.05</span><span class="muted">infeasible (${runway.reason || 'effect too flat'})</span></div>`;
      } else if (runway.additional_days != null) {
        runwayLine = `<div class="row"><span class="lbl">Runway to p&lt;0.05</span><span class="muted">+${runway.additional_days}d (need ~${runway.n_required}d total)</span></div>`;
      }
    }
    let funnelFormulaLine = '';
    if (totalPct != null) {
      const note = (clkPct == null)
        ? 'Formula: total = AB M1+VFM/UV %Δ (no SEO traffic signal to compose with).'
        : 'Formula: total = (1 + SEO clicks %Δ) × (1 + AB M1+VFM/UV %Δ) − 1. M1+VFM/UV already includes CVR × margin-per-order, so we don\'t multiply CVR a third time. The CVR / Margin-per-order decomposition is shown for attribution only — Margin/order is back-solved as (1+M1+VFM/UV)/(1+CVR)−1.';
      const interp = 'Interpretation: positive means shipping is expected to grow margin; negative means it would shrink it. Magnitudes under ±0.5% are typically within noise on short windows.';
      funnelFormulaLine = `<div class="row" style="font-size:0.78rem;flex-direction:column;align-items:flex-start;gap:4px"><span class="lbl">Funnel formula</span><span class="muted">${note}</span><span class="muted">${interp}</span></div>`;
    }
    const srmChiLine = (srmObj && srmObj.chi_sq !== undefined)
      ? `<div class="row"><span class="lbl">SRM χ² (in use)</span><span class="muted">${(srmObj.chi_sq||0).toFixed(3)} (p=${fmtP(srmObj.p_value||1)})</span></div>` : '';
    const srmRawLine = (srmPromoted && srmObj.original)
      ? `<div class="row"><span class="lbl">SRM χ² (raw)</span><span class="muted">${(srmObj.original.chi_sq||0).toFixed(3)} (p=${fmtP(srmObj.original.p_value||0)})</span></div>` : '';
    const seoNoteLine = seoStatus
      ? `<div class="row" style="font-size:0.74rem"><span class="lbl"></span><span class="muted">DiD Impr/Clicks vs L3-matched synthetic peer.</span></div>`
      : '';
    const detailsBody = funnelFormulaLine + runwayLine + srmChiLine + srmRawLine + seoNoteLine;
    const detailsSection = detailsBody ? `
      <details class="card-details"><summary>Details</summary>${detailsBody}</details>` : '';

    return `<div class="card ${cls}">${headerHtml}${expectedSection}${abSection}${seoSection}${detailsSection}</div>`;
}

function buildExpTabs() {
  const tabsRoot = document.getElementById('exp-tabs');
  const contentRoot = document.getElementById('exp-tab-contents');
  Object.entries(ROOT.experiments).forEach(([name, D], idx) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (idx === 0 ? ' active' : '');
    btn.textContent = name;
    btn.onclick = () => showExpTab(name);
    tabsRoot.appendChild(btn);
    const wrap = document.createElement('div');
    wrap.className = 'tab-content' + (idx === 0 ? ' active' : '');
    wrap.id = 'exp-' + slug(name);
    wrap.innerHTML = expBody(name);
    contentRoot.appendChild(wrap);
  });
  if (Object.keys(ROOT.experiments).length) initExp(Object.keys(ROOT.experiments)[0]);
}

function slug(s) { return s.replace(/[^a-z0-9]+/gi, '_'); }

function showExpTab(name) {
  document.querySelectorAll('#exp-tabs .tab-btn').forEach(b => b.classList.toggle('active', b.textContent === name));
  document.querySelectorAll('#exp-tab-contents .tab-content').forEach(c => c.classList.toggle('active', c.id === 'exp-' + slug(name)));
  initExp(name);
}

function expBody(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  return `
    <div class="tabs" style="border-bottom-color:#cbd5e0">
      ${SHOW_OVERVIEW_TAB ? `<button class="tab-btn active" data-sub="overview">Overview</button>` : ''}
      <button class="tab-btn${SHOW_OVERVIEW_TAB ? '' : ' active'}" data-sub="ab">AB experiment</button>
      <button class="tab-btn" data-sub="seo">SEO</button>
      <button class="tab-btn" data-sub="categories">Per Category</button>
      <button class="tab-btn" data-sub="deals">Deals</button>
    </div>
    ${SHOW_OVERVIEW_TAB ? `<div class="sub-content" data-sub="overview" style="padding-top:18px">
      <div id="overview-${sl}"></div>
    </div>` : ''}
    <div class="sub-content" data-sub="ab" style="${SHOW_OVERVIEW_TAB ? 'display:none;' : ''}padding-top:18px">
      <h3 style="margin-bottom:8px">${D.alternate_name||name} — AB experiment</h3>
      <div style="margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">
        <span class="badge ${(D.ab_label||'').startsWith('FINAL') ? 'badge-final' : 'badge-prelim'}">${escapeText(D.ab_label||'?')}</span>
        <span class="badge ${verdictBadgeCls(D.ab_filtered_verdict)}">${(D.ab_filtered_verdict||'?').toUpperCase()}</span>
        ${dataSourceBadge(D)}
      </div>
      <p class="muted" style="margin-bottom:12px">Window: ${D.start_date} → ${D.end_date}. AB-Filtered metrics shown over time.</p>
      <div id="rationale-${sl}"></div>
      <div class="chart-grid-2">
        <div><h4 style="font-size:0.95rem;margin-bottom:6px">M1+VFM/UV (margin per unique visitor)</h4><div class="chart-wrap"><canvas id="ch-${sl}-m1uv"></canvas></div></div>
        <div><h4 style="font-size:0.95rem;margin-bottom:6px">CVR (orders / UDV)</h4><div class="chart-wrap"><canvas id="ch-${sl}-cvr"></canvas></div></div>
      </div>
    </div>
    <div class="sub-content" data-sub="categories" style="display:none;padding-top:18px">
      <h3 style="margin-bottom:8px">Per-category heatmap</h3>
      <p class="muted" style="margin-bottom:12px">Color intensity = magnitude. Bold border = p &lt; 0.05.</p>
      <div class="heatmap" id="heatmap-${sl}"></div>
      <h3 style="margin-top:24px;margin-bottom:8px">Daily trends per category</h3>
      <div class="cat-subtabs" id="cat-subtabs-${sl}"></div>
      <div id="cat-subcontent-${sl}"></div>
    </div>
    <div class="sub-content" data-sub="seo" style="display:none;padding-top:18px"><div id="seo-${sl}"></div></div>
    <div class="sub-content" data-sub="deals" style="display:none;padding-top:18px"><div id="deals-${sl}"></div></div>
  `;
}

function initExp(name) {
  const root = document.getElementById('exp-' + slug(name));
  if (!root) return;
  // wire sub-tab clicks
  root.querySelectorAll(':scope > .tabs .tab-btn').forEach(b => {
    b.onclick = () => {
      const sub = b.dataset.sub;
      root.querySelectorAll(':scope > .tabs .tab-btn').forEach(x => x.classList.toggle('active', x === b));
      root.querySelectorAll('.sub-content').forEach(c => c.style.display = (c.dataset.sub === sub ? 'block' : 'none'));
      if (sub === 'overview') renderOverview(name);
      if (sub === 'ab') renderAB(name);
      if (sub === 'categories') renderCategories(name);
      if (sub === 'seo') renderSeo(name);
      if (sub === 'deals') renderDeals(name);
    };
  });
  // Build all sub-tabs eagerly so the first click is fast. Overview is the new default
  // (formerly the global scoreboard); AB experiment is no longer the landing tab.
  renderOverview(name);
  renderAB(name);
  renderCategories(name);
  renderSeo(name);
  renderDeals(name);
}

// Render the evaluator-written narrative pulled from the passthrough .docx. Renders the
// most actionable sections first (executive summary, what the data shows, action items,
// final recommendation) and falls back to per-Step body paragraphs (Step 7 practical
// significance, Step 8 behavioral mechanism, Step 2 overall results) when the curated
// subsections are absent. Returns '' when no narrative was loaded; caller then falls
// back to the synthesized rationale.
function renderEvaluatorNarrative(D) {
  const n = D.evaluation_narrative || {};
  if (!n || !Object.keys(n).length) return '';
  const verdict = (D.ab_filtered_verdict || '').toUpperCase();
  const tint = (verdict === 'KILL') ? 'background:#fff5f5;border-left-color:var(--red)'
            : (verdict === 'SHIP') ? 'background:#f0fff4;border-left-color:var(--green)'
            : 'background:#fffaf0;border-left-color:var(--yellow)';

  const renderItems = (items, opts) => {
    if (!items || !items.length) return '';
    const limit = (opts && opts.limit) || items.length;
    const sliced = items.slice(0, limit);
    let html = '';
    let openUl = false;
    sliced.forEach(it => {
      if (it.is_bullet) {
        if (!openUl) { html += '<ul class="rationale-list">'; openUl = true; }
        html += `<li>${escapeText(it.text)}</li>`;
      } else {
        if (openUl) { html += '</ul>'; openUl = false; }
        html += `<p style="margin:6px 0">${escapeText(it.text)}</p>`;
      }
    });
    if (openUl) html += '</ul>';
    return html;
  };

  // Curated sections we surface, in display order. Pick the first available "what
  // happened" source (named-summary section preferred; fall back to Step body if
  // the named one is absent).
  const blocks = [];
  const push = (title, items, opts) => {
    if (items && items.length) blocks.push({title, html: renderItems(items, opts)});
  };

  if (n.executive_summary) push('Executive summary', n.executive_summary, {limit: 4});
  // "What the data shows" + "What remains uncertain" are evaluator-curated when present.
  push('What the data shows', n.what_the_data_shows);
  push('What remains uncertain', n.what_remains_uncertain);
  // Final recommendation may be empty when the eval splits content into action items.
  if (n.final_recommendation && n.final_recommendation.length) {
    push('Final recommendation', n.final_recommendation);
  }
  push('Action items', n.action_items);

  // Per-Step fallbacks — only surface when no curated subsection above provided content,
  // or when the AB doc puts the verdict reasoning inline in Step paragraphs (AI_Summaries
  // pattern) rather than under named subsections.
  const havePrimary = blocks.length > 0;
  if (!havePrimary || !n.what_the_data_shows) {
    if (n.step_7_practical) push('Practical significance', n.step_7_practical, {limit: 5});
    if (n.step_8_mechanism) push('Behavioral mechanism', n.step_8_mechanism, {limit: 4});
    if (n.step_2_overall_results) push('Overall results', n.step_2_overall_results, {limit: 3});
  }

  if (!blocks.length) return '';

  const body = blocks.map(b =>
    `<div class="narrative-section"><div class="narrative-h">${escapeText(b.title)}</div>${b.html}</div>`
  ).join('');
  return `<div class="rationale" style="${tint}">
    <div class="rationale-title">Why <strong>${verdict || '?'}</strong>? — from AB evaluation report</div>
    ${body}
  </div>`;
}

function escapeText(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Build a "Why <verdict>?" narrative from the actual metric values + SRM/runway/SEO state.
// Returns an HTML string (or '' when there's nothing meaningful to say). Used by
// renderOverview to give human context for the verdict, beyond the raw numbers in the
// scoreboard. Used as a FALLBACK only — when the evaluator's docx narrative is loaded
// it takes precedence (see renderEvaluatorNarrative).
function buildVerdictRationale(D) {
  const verdict = (D.ab_filtered_verdict || '').toUpperCase();
  if (!verdict) return '';
  const om = D.unfiltered_m1uv || D.overall_m1uv || null;
  const oc = D.unfiltered_cvr  || D.overall_cvr  || null;
  const m1uvPct = om ? om.mean_delta_pct : null;
  const m1uvP   = om ? om.p_value : null;
  const cvrPct  = oc ? oc.mean_delta_pct : null;
  const cvrP    = oc ? oc.p_value : null;
  const did = (D.seo && D.seo.did) || {};
  const seoP = ((D.seo && D.seo.power_analysis) || {}).p_value;
  const clkPct = (did.did_clicks_pct == null) ? null : did.did_clicks_pct;
  const impPct = (did.did_impressions_pct == null) ? null : did.did_impressions_pct;
  const seoVerdict = D.seo && D.seo.status === 'ok' ? D.seo.verdict : null;
  const srm = D.srm_filtered || {};
  const srmRemediated = srm.promoted_from === 'remediated';
  const srmHardFail = srm.verdict && srm.verdict !== 'pass';
  const runway = D.runway_filtered || {};

  const sigSuffix = (p) => {
    if (p == null) return '';
    return p < 0.05 ? ` <span class="sigstar">★</span>` : ` <span class="muted" style="font-weight:400">(n.s., p=${fmtP(p)})</span>`;
  };

  // Rank candidate metrics by magnitude (signed) so we can call out the dominant signal.
  const candidates = [];
  if (m1uvPct != null) candidates.push({label: 'M1+VFM/UV', pct: m1uvPct, p: m1uvP});
  if (cvrPct  != null) candidates.push({label: 'CVR',   pct: cvrPct,  p: cvrP});
  if (clkPct  != null) candidates.push({label: 'SEO Clicks (DiD)', pct: clkPct, p: seoP});
  if (impPct  != null) candidates.push({label: 'SEO Impressions (DiD)', pct: impPct, p: seoP});

  const bullets = [];

  // 1) Headline: the metric most responsible for the verdict direction.
  if (verdict === 'KILL') {
    const losers = candidates.filter(c => c.pct < 0).slice().sort((a,b) => a.pct - b.pct); // most negative first
    if (losers.length) {
      const w = losers[0];
      bullets.push(`<strong>${w.label} ${fmtPctOf(w.pct)}${sigSuffix(w.p)}</strong> — primary driver of the negative composed funnel.`);
      losers.slice(1, 3).forEach(c => {
        bullets.push(`Also negative: ${c.label} ${fmtPctOf(c.pct)}${sigSuffix(c.p)}.`);
      });
    } else {
      bullets.push(`KILL despite no individual metric being clearly negative — check SRM / sample size below.`);
    }
  } else if (verdict === 'SHIP') {
    const winners = candidates.filter(c => c.pct > 0).slice().sort((a,b) => b.pct - a.pct);
    if (winners.length) {
      const w = winners[0];
      bullets.push(`<strong>${w.label} ${fmtPctOf(w.pct)}${sigSuffix(w.p)}</strong> — primary driver of the positive composed funnel.`);
      winners.slice(1, 3).forEach(c => {
        bullets.push(`Also positive: ${c.label} ${fmtPctOf(c.pct)}${sigSuffix(c.p)}.`);
      });
    }
  } else {
    // INCONCLUSIVE / HOLD / EXTEND / PRELIMINARY — explain why we can't call it.
    const bigSig = candidates.filter(c => c.p != null && c.p < 0.05);
    if (bigSig.length === 0) {
      bullets.push(`No metric reached statistical significance (all p ≥ 0.05). The observed deltas are within noise on this sample size.`);
    } else {
      bullets.push(`Mixed signal — significant on ${bigSig.map(c => `${c.label} ${fmtPctOf(c.pct)}`).join(', ')}, but the funnel composition isn't decisive.`);
    }
  }

  // 2) SEO impact, when independently informative (overall verdict, not already pulled in above).
  if (seoVerdict && verdict !== 'KILL') {
    const seoLine = (clkPct != null && impPct != null)
      ? `SEO verdict <strong>${seoVerdict}</strong>: DiD clicks ${fmtPctOf(clkPct)}, impressions ${fmtPctOf(impPct)}${sigSuffix(seoP)}.`
      : `SEO verdict <strong>${seoVerdict}</strong>.`;
    bullets.push(seoLine);
  }

  // 3) SRM context (hard fail or remediation).
  if (srmRemediated) {
    const oP = (srm.original || {}).p_value;
    bullets.push(`SRM raw bcookie split failed (χ² p=${oP != null ? fmtP(oP) : '<0.001'}); active-visitor remediation passed (χ² p=${fmtP(srm.p_value || 1)}). Headline numbers above use the remediated cohort.`);
  } else if (srmHardFail) {
    bullets.push(`<strong>SRM ${srm.verdict}</strong> — assignment imbalance not resolvable by remediation. Decision should be treated as advisory, not authoritative.`);
  }

  // 4) Runway (only when the verdict isn't already SHIP/KILL).
  if (runway && !runway.already_significant && verdict !== 'SHIP' && verdict !== 'KILL') {
    if (runway.infeasible) {
      bullets.push(`Runway: <strong>infeasible</strong> — ${runway.reason || 'observed effect too small to converge in any reasonable window'}.`);
    } else if (runway.additional_days != null) {
      bullets.push(`Runway: needs ~<strong>${runway.additional_days} more days</strong> for p<0.05 (n=${runway.n_current}d → projected ~${runway.n_required}d total).`);
    }
  }

  // 5) Sample-size caveat for very short windows.
  const n = (om && om.n) || (oc && oc.n) || null;
  if (n != null && n < 7) {
    bullets.push(`Short sample window (n=${n}d) — confidence in the call is limited until the test has run longer.`);
  }

  if (!bullets.length) return '';

  // Soft-tinted callout matching the verdict colour family.
  const tint = (verdict === 'KILL') ? 'background:#fff5f5;border-left-color:var(--red)'
            : (verdict === 'SHIP') ? 'background:#f0fff4;border-left-color:var(--green)'
            : 'background:#fffaf0;border-left-color:var(--yellow)';
  return `<div class="rationale" style="${tint}">
    <div class="rationale-title">Why <strong>${verdict}</strong>?</div>
    <ul class="rationale-list">${bullets.map(b => `<li>${b}</li>`).join('')}</ul>
  </div>`;
}

// renderOverview now renders the single-experiment scorecard into the new Overview
// sub-tab (was a global "Scoreboard" section above the experiment tabs; the Executive
// Summary section above replaces that scan-level role). The per-experiment AB charts +
// rationale moved to the new "AB experiment" sub-tab and are owned by renderAB().
function renderOverview(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`overview-${sl}`);
  if (!root) return;
  root.innerHTML = `<div class="scoreboard">${buildScorecardHtml(name, D)}</div>`;
}

function renderAB(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const daily = D.overall_daily || [];
  // Double-rAF for the same reason as initCatCharts — when the user switches to a
  // not-yet-rendered experiment outer tab, the canvas is briefly 0×0 until layout runs.
  const drawCharts = () => {
    if (daily.length && daily[0].m1uv_ctrl !== undefined) {
      lineChart(`ch-${sl}-m1uv`, daily, 'm1uv_ctrl', 'm1uv_treat', 'M1+VFM/UV ($)');
      lineChart(`ch-${sl}-cvr`,  daily, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
    } else {
      lineChart(`ch-${sl}-m1uv`, D.raw_filtered_daily, 'ctrl', 'treat', 'M1+VFM/UV ($)');
    }
  };
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(() => requestAnimationFrame(drawCharts));
  } else {
    setTimeout(drawCharts, 32);
  }
  const rationale = document.getElementById(`rationale-${sl}`);
  if (rationale) {
    // Prefer the evaluator's hand-written narrative (parsed from passthrough .docx) when
    // available; fall back to the renderer's synthesized rationale otherwise.
    const evalText = renderEvaluatorNarrative(D);
    rationale.innerHTML = evalText || buildVerdictRationale(D);
  }
  // Headline KPI cards (M1/UV, CVR, SRM, runway) are intentionally NOT rendered here —
  // they were duplicating the scorecard / scoreboard sections AND used a different cohort
  // source (legacy overall_m1uv reads from raw.filtered.daily as fallback, while the
  // scorecard uses unfiltered raw.overall.daily). The mismatch was confusing; the
  // scorecard is the single canonical home for those numbers now.
}

function renderCategories(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`heatmap-${sl}`);
  if (!root) return;
  let cats = D.categories || [];
  if (!cats.length) {
    root.innerHTML = '<p class="muted" style="padding:14px">No per-category data available.</p>';
    return;
  }
  // Sort categories by total M1 (control + treatment, summed across daily rows) descending —
  // heaviest categories first. Categories with no daily data fall to the bottom in original order.
  // Sort key uses per_category[cat].daily; per_category_overall is the fallback when filtered is empty.
  const _catWeight = (cat) => {
    const daily = ((D.per_category||{})[cat] || {}).daily
              || ((D.per_category_overall||{})[cat] || {}).daily
              || [];
    let total = 0;
    for (const r of daily) {
      total += (+(r.m1_ctrl) || 0) + (+(r.m1_treat) || 0);
    }
    return total;
  };
  cats = cats.slice().sort((a, b) => _catWeight(b) - _catWeight(a));
  const cell = (s) => {
    if (!s || s.p_value === undefined) return `<div class="hm-cell muted">n/a</div>`;
    const sig = s.p_value < 0.05 ? ' hm-sig' : '';
    return `<div class="hm-cell${sig}" style="background:${colorFor(s.mean_delta_pct)}"><div class="pct">${fmtPctOf(s.mean_delta_pct)}</div><span class="pval">p=${fmtP(s.p_value)}</span></div>`;
  };
  const seoPpCell = (val, n_pre, n_post) => {
    if (val == null || isNaN(val)) return `<div class="hm-cell muted">n/a</div>`;
    return `<div class="hm-cell" style="background:${seoColor(val)}"><div class="pct">${fmtPp(val)}</div><span class="pval">${n_post||0} URLs</span></div>`;
  };
  // Determine M1 ratio denominator from the first per-cat object that carries the
  // marker (set by run-ab-evaluation: 'uv' for split experiments, 'udv' for L2-derived).
  // Default to 'uv' for backward compatibility with older AB JSONs.
  let m1Denom = 'uv';
  for (const c of cats) {
    const pc = (D.per_category || {})[c];
    if (pc && pc.denominator) { m1Denom = String(pc.denominator).toLowerCase(); break; }
  }
  const m1RatioLabel = m1Denom === 'udv' ? 'M1+VFM/UDV' : 'M1+VFM/UV';
  const denomLabel   = m1Denom.toUpperCase();
  // Per-row deal count: lookup `D.deals_per_l2` honoring AB-side aliases.
  const dealsPerL2 = D.deals_per_l2 || {};
  const dealsPerL2Lower = {};
  Object.keys(dealsPerL2).forEach(k => { dealsPerL2Lower[k.trim().toLowerCase()] = dealsPerL2[k]; });
  const dealCountFor = (cat) => {
    for (const c of _l2Candidates(cat)) {
      if (dealsPerL2Lower[c] != null) return dealsPerL2Lower[c];
    }
    return null;
  };
  // Aggregate-totals helper for the Control / Treatment scale cells (per cat).
  // Sums daily totals across the experiment window — this is the canonical aggregate-ratio
  // (SUM(num)/SUM(den)), not a daily mean. For L2-derived rows, uv_* daily fields are
  // synthesized from udv_* by run-ab-evaluation, so the same code path produces M1/UDV.
  const aggTotals = (daily) => {
    let m1c=0, m1t=0, dc=0, dt=0, uc=0, ut=0, oc_=0, ot_=0;
    for (const r of (daily || [])) {
      m1c += +(r.m1_ctrl)||0;   m1t += +(r.m1_treat)||0;
      dc  += +(r.uv_ctrl)||0;   dt  += +(r.uv_treat)||0;
      uc  += +(r.udv_ctrl)||0;  ut  += +(r.udv_treat)||0;
      oc_ += +(r.orders_ctrl)||0; ot_ += +(r.orders_treat)||0;
    }
    return { m1c, m1t, dc, dt, uc, ut, oc_, ot_ };
  };
  const compactNum = (v) => {
    if (v == null || isNaN(v)) return 'n/a';
    const a = Math.abs(v);
    if (a >= 1e9) return (v/1e9).toFixed(2)+'B';
    if (a >= 1e6) return (v/1e6).toFixed(2)+'M';
    if (a >= 1e3) return (v/1e3).toFixed(1)+'k';
    return Math.round(v).toLocaleString();
  };
  const compactMoney = (v) => v == null || isNaN(v) ? 'n/a' : '$' + compactNum(v);
  const scaleCell = (m1, denom, udv, orders) => {
    // denom = uv (split) or udv (L2-view); udv is always the CVR denominator.
    if ((m1==null && denom==null && udv==null && orders==null) || (m1===0 && denom===0 && udv===0 && orders===0)) {
      return `<div class="hm-cell muted" style="text-align:left;font-size:0.72rem;line-height:1.4;padding:8px">no daily data</div>`;
    }
    const m1Per = (denom && denom > 0) ? (m1/denom) : null;
    const cvr   = (udv && udv > 0) ? (orders/udv) : null;
    return `<div class="hm-cell" style="text-align:left;font-size:0.72rem;line-height:1.45;padding:8px;background:#fafbfc">
      <div>M1+VFM: <strong>${compactMoney(m1)}</strong></div>
      <div>${denomLabel}: <strong>${compactNum(denom)}</strong></div>
      <div>${m1RatioLabel}: <strong>${m1Per==null?'n/a':'$'+m1Per.toFixed(3)}</strong></div>
      <div>CVR: <strong>${cvr==null?'n/a':(cvr*100).toFixed(2)+'%'}</strong></div>
    </div>`;
  };
  // Heatmap grid: row label + 2 scale cells (Totals: Control, Treatment) + 3 SEO DiD cells +
  // 2 AB Overall cells + 2 AB Filtered cells = 10 cols. Order: Totals → SEO → AB Overall → AB Filtered.
  root.style.gridTemplateColumns = '200px 1.4fr 1.4fr repeat(7, 1fr)';
  let html = `
    <div class="hm-cell hm-head"></div>
    <div class="hm-cell hm-head" style="grid-column:span 2">Totals</div>
    <div class="hm-cell hm-head" style="grid-column:span 3">SEO DiD (variant vs same-category All Groupon)</div>
    <div class="hm-cell hm-head" style="grid-column:span 2">AB-Overall (population-wide)</div>
    <div class="hm-cell hm-head" style="grid-column:span 2">AB-Filtered (deal-scoped)</div>
    <div class="hm-cell hm-head"></div>
    <div class="hm-cell hm-head">Control</div>
    <div class="hm-cell hm-head">Treatment</div>
    <div class="hm-cell hm-head">DiD Impr pp</div>
    <div class="hm-cell hm-head">DiD Clicks pp</div>
    <div class="hm-cell hm-head">DiD CTR pp</div>
    <div class="hm-cell hm-head">${m1RatioLabel} %Δ</div>
    <div class="hm-cell hm-head">CVR %Δ</div>
    <div class="hm-cell hm-head">${m1RatioLabel} %Δ</div>
    <div class="hm-cell hm-head">CVR %Δ</div>`;
  cats.forEach(cat => {
    const pf = D.per_category[cat] || {m1uv:{},cvr:{},daily:[]};
    const po = (D.per_category_overall||{})[cat] || {m1uv:{},cvr:{}};
    const variantRow = _seoL2VariantRow(D.seo, cat);
    const didImpPp   = variantRow ? variantRow.did_impr_pp   : null;
    const didClkPp   = variantRow ? variantRow.did_clicks_pp : null;
    const didCtrPp   = _seoL2CtrDidPp(D.seo, cat);
    const urlCount   = variantRow ? (variantRow.url_count || 0) : 0;
    const t = aggTotals(pf.daily);
    const dealCount = dealCountFor(cat);
    const dealsLine = dealCount == null ? '' : `<div class="muted" style="font-size:0.72rem;font-weight:400;margin-top:2px">${Number(dealCount).toLocaleString()} deal${dealCount===1?'':'s'}</div>`;
    html += `<div class="hm-cell hm-row-label">${cat}${dealsLine}</div>`;
    // Order: Totals (Control, Treatment) → SEO DiD (Impr, Clicks, CTR) → AB Overall (M1/UV, CVR) → AB Filtered (M1/UV, CVR).
    html += scaleCell(t.m1c, t.dc, t.uc, t.oc_);
    html += scaleCell(t.m1t, t.dt, t.ut, t.ot_);
    html += seoPpCell(didImpPp, urlCount, urlCount);
    html += seoPpCell(didClkPp, urlCount, urlCount);
    html += seoPpCell(didCtrPp, urlCount, urlCount);
    html += cell(po.m1uv);
    html += cell(po.cvr);
    html += cell(pf.m1uv);
    html += cell(pf.cvr);
  });
  root.innerHTML = html;
  // Benchmark-spread caveat for per-L2 SEO DiD.
  const note = document.createElement('p');
  note.className = 'muted';
  note.style.cssText = 'margin-top:8px;font-size:0.78rem';
  note.textContent = 'Per-category SEO DiD here is variant Δ% minus All-Groupon-in-same-category Δ% (benchmark spread). The headline DiD on the scoreboard uses an L3-matched synthetic-control peer; the two answer different questions.';
  root.parentElement && root.parentElement.appendChild(note);

  // sub-tabs
  const subRoot = document.getElementById(`cat-subtabs-${sl}`);
  const subContent = document.getElementById(`cat-subcontent-${sl}`);
  subRoot.innerHTML = '';
  subContent.innerHTML = '';
  cats.forEach((cat, i) => {
    const cs = slug(cat);
    const btn = document.createElement('button');
    btn.className = 'cat-subtab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = cat;
    btn.dataset.cat = cat;
    btn.onclick = () => {
      subRoot.querySelectorAll('.cat-subtab-btn').forEach(b => b.classList.toggle('active', b.dataset.cat === cat));
      subContent.querySelectorAll('.cat-subtab-content').forEach(c => c.classList.toggle('active', c.dataset.cat === cat));
      initCatCharts(name, cat);
    };
    subRoot.appendChild(btn);
    const div = document.createElement('div');
    div.className = 'cat-subtab-content' + (i === 0 ? ' active' : '');
    div.dataset.cat = cat;
    const hasAbF = ((D.per_category||{})[cat] || {}).daily && (D.per_category[cat].daily.length > 0);
    const hasAbO = ((D.per_category_overall||{})[cat] || {}).daily && (D.per_category_overall[cat].daily.length > 0);
    // Canvas IDs use slug(cat) — not the row index — so chart-init lookups still work
    // when the category list is re-ordered (e.g. sorted by total M1).
    const abFBlock = hasAbF ? `
      <h4 style="font-size:0.92rem;margin-bottom:6px;color:#4a5568">AB-Filtered (deal-scoped)</h4>
      <div class="chart-grid-2">
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${cs}-m1uv-f"></canvas></div></div>
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${cs}-cvr-f"></canvas></div></div>
      </div>` : '';
    const abOBlock = hasAbO ? `
      <h4 style="font-size:0.92rem;margin-top:14px;margin-bottom:6px;color:#4a5568">AB-Overall (population-wide)</h4>
      <div class="chart-grid-2">
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${cs}-m1uv-o"></canvas></div></div>
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${cs}-cvr-o"></canvas></div></div>
      </div>` : '';
    const noAbNotice = (!hasAbF && !hasAbO) ? `<p class="muted" style="font-size:0.85rem;margin-bottom:8px">AB per-category split is off for this experiment (<code>use_deal_category_split=FALSE</code>) — showing SEO L2 view only.</p>` : '';
    const seoBlock = renderSeoCatBlock(cat, null);
    div.innerHTML = `${noAbNotice}${abFBlock}${abOBlock}${seoBlock}`;
    subContent.appendChild(div);
  });
  if (cats.length) initCatCharts(name, cats[0]);
}

function renderSeoCatBlock(cat, _unused) {
  // Per-L2 SEO detail moved into the embedded upstream report (SEO tab).
  return `<p class="muted" style="font-size:0.85rem;margin-top:14px">Detailed per-L2 SEO winners / losers / charts for <strong>${cat}</strong> are inside the embedded SEO report — see the <em>SEO</em> tab.</p>`;
}

function initCatCharts(name, cat) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const cs = slug(cat);
  const filt = ((D.per_category||{})[cat] || {}).daily || [];
  const ovr = ((D.per_category_overall||{})[cat] || {}).daily || [];
  // Double-rAF guarantees the browser has performed layout on the freshly-shown
  // parent tab before Chart.js measures the canvas. Single setTimeout(0) was firing
  // before the display:none → display:block transition completed layout, so charts
  // saw 0×0 dims and rendered empty. With double-rAF the first frame triggers
  // layout, the second frame fires after layout completes — canvas now has its
  // 280px height, lineChart measures correctly.
  const draw = () => {
    if (filt.length) {
      lineChart(`ch-${sl}-${cs}-m1uv-f`, filt, 'm1uv_ctrl', 'm1uv_treat', 'M1+VFM/UV ($)');
      lineChart(`ch-${sl}-${cs}-cvr-f`,  filt, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
    }
    if (ovr.length) {
      lineChart(`ch-${sl}-${cs}-m1uv-o`, ovr, 'm1uv_ctrl', 'm1uv_treat', 'M1+VFM/UV ($)');
      lineChart(`ch-${sl}-${cs}-cvr-o`,  ovr, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
    }
  };
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(() => requestAnimationFrame(draw));
  } else {
    setTimeout(draw, 32);
  }
}

function ppCell(v) {
  if (v === null || v === undefined) return `<td class="muted">n/a</td>`;
  const cls = v >= 0 ? '#22543d' : '#742a2a';
  return `<td><strong style="color:${cls}">${fmtPp(v)}</strong></td>`;
}

function renderSeo(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`seo-${sl}`);
  if (!root) return;
  const s = D.seo;
  if (!s || s.status !== 'ok') {
    root.innerHTML = `<div class="skipped">SEO eval: ${(s && s.status) || 'n/a'}${(s && s.reason) ? ' — ' + s.reason : ''}</div>`;
    return;
  }
  const b64gz = s.upstream_html_b64_gz;
  const b64plain = s.upstream_html_b64;
  if (!b64gz && !b64plain) {
    root.innerHTML = `<div class="skipped">SEO upstream HTML missing from <code>seo_${sl}.json</code> — re-run <code>run-seo-evaluation</code> against upstream commit 3100dc8 or later.</div>`;
    return;
  }
  // Show a brief loading state — gzip decompression of large reports can take a
  // few hundred ms in the browser; better than a blank tab while it spins.
  root.innerHTML = '<p class="muted" style="padding:14px">Decompressing SEO report…</p>';
  decodeUpstreamHtml(b64gz, b64plain)
    .then(html => mountSeoIframe(root, html, name, s))
    .catch(err => {
      root.innerHTML = `<div class="skipped">SEO upstream HTML failed to decode: ${err && err.message ? err.message : err}</div>`;
    });
}

// Decode the upstream SEO HTML. Prefers the gzip+base64 field (introduced 2026-05-06
// to keep the combined report small enough to email as a single file) and falls back
// to plain base64 for older payloads. Uses native DecompressionStream — supported in
// Chrome/Edge/Safari/Firefox 113+ — no JS lib required. Returns a Promise<string>.
function decodeUpstreamHtml(b64gz, b64plain) {
  if (b64gz) {
    if (typeof DecompressionStream !== 'function') {
      return Promise.reject(new Error('Browser missing DecompressionStream support — please use Chrome 80+ / Firefox 113+ / Safari 16.4+ / Edge 80+.'));
    }
    const raw = atob(b64gz);
    const bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return new Response(stream).text();
  }
  // Fallback: plain base64 (legacy payloads).
  const raw = atob(b64plain);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  return Promise.resolve(new TextDecoder('utf-8').decode(bytes));
}

// Mount the decoded upstream HTML into a sandboxed srcdoc iframe + render the
// caveats banner above it. Sandbox flags: allow-same-origin needed for upstream's
// JSON-from-script tag pattern; allow-scripts needed for its Chart.js + tab
// switching to run. srcdoc gives the upstream report its own document context —
// no Chart.js double-init, no CSS / DOM-id collisions across experiments.
function mountSeoIframe(root, html, name, s) {
  const iframe = document.createElement('iframe');
  iframe.setAttribute('sandbox', 'allow-same-origin allow-scripts');
  iframe.setAttribute('srcdoc', html);
  iframe.style.cssText = 'width:100%;height:90vh;border:0;background:#fff;';
  iframe.title = `Upstream SEO report — ${name}`;
  root.innerHTML = '';
  root.appendChild(iframe);
  const caveats = (s.caveats || []).filter(Boolean);
  if (caveats.length) {
    const banner = document.createElement('div');
    banner.style.cssText = 'background:#fefcbf;padding:10px 14px;border-radius:6px;margin-bottom:10px;font-size:0.85rem';
    banner.innerHTML = '<strong>SEO caveats:</strong><ul style="margin:4px 0 0 18px">' +
      caveats.map(c => `<li>${typeof c === 'string' ? c : (c.message || JSON.stringify(c))}</li>`).join('') +
      '</ul>';
    root.insertBefore(banner, iframe);
  }
}


function renderDeals(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`deals-${sl}`);
  if (!root) return;
  const d = D.deal || {};
  const renderTable = (rows) => {
    if (!rows || !rows.length) return '<p class="muted">No data.</p>';
    let h = `<thead><tr><th class="label">Deal</th><th>Category</th><th>m1 Δ</th></tr></thead><tbody>`;
    rows.forEach(r => {
      const display = r.deal_title || r.title || r.company_name || r.company || ((r.deal_url||'').split('/').pop());
      const company = r.company_name || r.company || '';
      const cls = r.m1_delta >= 0 ? 'win' : 'lose';
      const md = r.m1_delta || 0;
      h += `<tr class="deal-row ${cls}">
        <td><a href="${r.deal_url}" target="_blank" rel="noopener">${(display||'').replace(/&/g,'&amp;').replace(/</g,'&lt;')}</a><div class="meta">${company||''}${company?' · ':''}<code>${(r.deal_uuid||'').slice(0,8)}</code></div></td>
        <td>${r.category||r.deal_category||''}</td>
        <td><strong style="color:${md>=0?'#22543d':'#742a2a'}">${fmtMoney(md)}</strong></td>
      </tr>`;
    });
    h += `</tbody>`;
    return h;
  };
  let html = `<h3>Top Winners (by m1 delta)</h3><table>${renderTable(d.top_winners)}</table>`;
  html += `<h3 style="margin-top:24px">Top Losers (by m1 delta)</h3><table>${renderTable(d.top_losers)}</table>`;
  root.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', () => {
  header();
  renderExecSummary();
  buildExpTabs();
});
