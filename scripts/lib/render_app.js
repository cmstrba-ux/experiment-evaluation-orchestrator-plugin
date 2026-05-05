// Frontend for the combined experiment-evaluation report.
// Inputs (from <script id="data">): { run_id, data_through, experiments: { <name>: payload } }
// payload schema is documented in render.py (build_payload).

const ROOT = JSON.parse(document.getElementById('data').textContent);
const charts = {};

const fmtPct = x => (x>=0?'+':'') + (x*100).toFixed(2) + '%';
const fmtPctOf = x => (x>=0?'+':'') + (x||0).toFixed(2) + '%';
const fmtP = p => p < 0.001 ? '<0.001' : p.toFixed(3);
const fmtMoney = x => (x>=0?'+':'') + '$' + Math.abs(x||0).toLocaleString(undefined,{maximumFractionDigits:0});
const fmtMoney2 = x => (x>=0?'+':'') + '$' + Math.abs(x||0).toFixed(4);
const fmtPp = x => (x>=0?'+':'') + (x||0).toFixed(2) + 'pp';

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

function lineChart(id, daily, ctrlKey, treatKey, ylabel) {
  const ctx = document.getElementById(id);
  if (!ctx || !daily || !daily.length) return;
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(ctx, {
    type:'line',
    data:{ labels: daily.map(d=>d.d || d.event_date),
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
  meta.textContent = `${names.length} experiment${names.length!==1?'s':''} · run ${ROOT.run_id} · data through ${ROOT.data_through}`;
}

function scoreboard() {
  const root = document.getElementById('scoreboard');
  Object.entries(ROOT.experiments).forEach(([name, D]) => {
    const f = D.ab_filtered_stats || {};
    const o = D.ab_overall_stats || {};
    const v = D.ab_filtered_verdict || '?';
    const cls = v === 'SHIP' ? 'win' : v === 'KILL' ? 'lose' : 'flat';
    const labelBadge = (D.ab_label||'').startsWith('FINAL') ? 'badge-final' : 'badge-prelim';
    const srm = (D.srm_filtered||{}).verdict || 'pass';
    const srmBadge = srm === 'pass' ? 'badge-pass' : 'badge-fail';
    const om = D.overall_m1uv, oc = D.overall_cvr;

    // SEO headline block: prefer DiD when available; fall back to variant-only raw pre/post.
    const seoStatus = D.seo && D.seo.status === 'ok';
    const did = (D.seo && D.seo.did_overall && D.seo.did_overall.did) || {};
    const seoSig = D.seo && D.seo.signal_level;
    const seoBadgeCls = seoSig === 'full' ? 'badge-pass' : seoSig === 'partial' ? 'badge-prelim' : 'badge-fail';
    let seoBlock = '';
    if (seoStatus) {
      if (Object.keys(did).length) {
        seoBlock = `
          <div class="row" style="border-top:1px solid var(--border);margin-top:6px;padding-top:8px"><span class="lbl"><strong>SEO DiD</strong> · signal</span><span><span class="badge ${seoBadgeCls}">${seoSig}</span></span></div>
          <div class="row"><span class="lbl">Impressions DiD</span><span>${fmtPp(did.imp_pp ?? 0)}</span></div>
          <div class="row"><span class="lbl">Clicks DiD</span><span>${fmtPp(did.clk_pp ?? 0)}</span></div>
          <div class="row"><span class="lbl">CTR DiD</span><span>${fmtPp(did.ctr_pp ?? 0)}</span></div>`;
      } else {
        const ov = ((D.seo.pre_post)||{}).overall || {};
        seoBlock = `
          <div class="row" style="border-top:1px solid var(--border);margin-top:6px;padding-top:8px"><span class="lbl"><strong>SEO</strong> · signal</span><span><span class="badge ${seoBadgeCls}">${seoSig||'?'}</span> <span class="muted" style="font-size:0.78rem">no control</span></span></div>
          <div class="row"><span class="lbl">Impressions Δ (variant raw)</span><span>${fmtPctOf(ov.impressions_pct_total||0)}</span></div>
          <div class="row"><span class="lbl">Clicks Δ (variant raw)</span><span>${fmtPctOf(ov.clicks_pct_total||0)}</span></div>`;
      }
    }

    const card = document.createElement('div');
    card.className = `card ${cls}`;
    card.innerHTML = `
      <h3>${name}</h3>
      <div style="margin:6px 0">
        <span class="badge ${labelBadge}">${D.ab_label||'?'}</span>
        <span class="badge ${srmBadge}">SRM ${srm}</span>
      </div>
      ${om ? `<div class="row"><span class="lbl">M1/UV Δ (filtered)</span><span>${fmtPctOf(om.mean_delta_pct)} (p=${fmtP(om.p_value)})</span></div>` : `<div class="row"><span class="lbl">Filtered MPV mean Δ</span><span>$${(f.mean_delta||0).toFixed(4)} (p=${fmtP(f.p_value||1)})</span></div>`}
      ${oc ? `<div class="row"><span class="lbl">CVR Δ (filtered)</span><span>${fmtPctOf(oc.mean_delta_pct)} (p=${fmtP(oc.p_value)})</span></div>` : ''}
      <div class="row"><span class="lbl">Overall MPV mean Δ</span><span>$${(o.mean_delta||0).toFixed(4)} (p=${fmtP(o.p_value||1)})</span></div>
      ${(D.srm_filtered||{}).chi_sq !== undefined ? `<div class="row"><span class="lbl">SRM χ²</span><span>${(D.srm_filtered.chi_sq||0).toFixed(3)} (p=${fmtP(D.srm_filtered.p_value||1)})</span></div>` : ''}
      ${seoBlock}
      <div class="verdict">→ ${v}</div>
    `;
    root.appendChild(card);
  });
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
      <button class="tab-btn active" data-sub="overview">Overview</button>
      <button class="tab-btn" data-sub="categories">Per Category</button>
      <button class="tab-btn" data-sub="seo">SEO</button>
      <button class="tab-btn" data-sub="deals">Deals</button>
    </div>
    <div class="sub-content" data-sub="overview" style="padding-top:18px">
      <h3 style="margin-bottom:8px">${D.alternate_name||name} — Overview</h3>
      <p class="muted" style="margin-bottom:12px">Window: ${D.start_date} → ${D.end_date}. AB-Filtered metrics shown over time.</p>
      <div class="chart-grid-2">
        <div><h4 style="font-size:0.95rem;margin-bottom:6px">M1/UV (margin per unique visitor)</h4><div class="chart-wrap"><canvas id="ch-${sl}-m1uv"></canvas></div></div>
        <div><h4 style="font-size:0.95rem;margin-bottom:6px">CVR (orders / UDV)</h4><div class="chart-wrap"><canvas id="ch-${sl}-cvr"></canvas></div></div>
      </div>
      <div class="bar-grid" style="margin-top:18px" id="kpi-${sl}"></div>
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
      if (sub === 'categories') renderCategories(name);
      if (sub === 'seo') renderSeo(name);
      if (sub === 'deals') renderDeals(name);
    };
  });
  renderOverview(name);
  renderCategories(name);  // build structure even when not active so initial click is fast
  renderSeo(name);
  renderDeals(name);
}

function renderOverview(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const daily = D.overall_daily || [];
  if (daily.length && daily[0].m1uv_ctrl !== undefined) {
    lineChart(`ch-${sl}-m1uv`, daily, 'm1uv_ctrl', 'm1uv_treat', 'M1/UV ($)');
    lineChart(`ch-${sl}-cvr`,  daily, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
  } else {
    // fall back to legacy filtered.daily ({d, ctrl, treat})
    lineChart(`ch-${sl}-m1uv`, D.raw_filtered_daily, 'ctrl', 'treat', 'M1/UV ($)');
  }
  const kpi = document.getElementById(`kpi-${sl}`);
  if (!kpi) return;
  let html = '';
  const om = D.overall_m1uv, oc = D.overall_cvr, srm = D.srm_filtered || {};
  if (om) {
    const cls = (om.mean_delta_pct||0) > 0.1 ? 'win' : (om.mean_delta_pct||0) < -0.1 ? 'lose' : '';
    html += `<div class="kpi ${cls}"><div class="label">M1/UV — daily mean Δ</div><div class="value">${fmtPctOf(om.mean_delta_pct)}</div><div class="delta">absolute ${fmtMoney2(om.mean_delta)} · p=${fmtP(om.p_value)} · n=${om.n}d</div></div>`;
  }
  if (oc) {
    const cls = (oc.mean_delta_pct||0) > 0.1 ? 'win' : (oc.mean_delta_pct||0) < -0.1 ? 'lose' : '';
    html += `<div class="kpi ${cls}"><div class="label">CVR — daily mean Δ</div><div class="value">${fmtPctOf(oc.mean_delta_pct)}</div><div class="delta">absolute ${(oc.mean_delta>=0?'+':'')+((oc.mean_delta||0)*100).toFixed(3)}pp · p=${fmtP(oc.p_value)} · n=${oc.n}d</div></div>`;
  }
  if (srm.verdict) {
    const cls = srm.verdict === 'pass' ? 'win' : 'lose';
    const obs = srm.observed || {};
    html += `<div class="kpi ${cls}"><div class="label">SRM check</div><div class="value">${(srm.verdict||'').toUpperCase()}</div><div class="delta">χ²=${(srm.chi_sq||0).toFixed(3)} · p=${fmtP(srm.p_value||1)} · ctrl ${(obs.control||0).toLocaleString()} vs treat ${(obs.treatment||0).toLocaleString()}</div></div>`;
  }
  kpi.innerHTML = html;
}

function renderCategories(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`heatmap-${sl}`);
  if (!root) return;
  const cats = D.categories || [];
  if (!cats.length) {
    root.innerHTML = '<p class="muted" style="padding:14px">No per-category data available.</p>';
    return;
  }
  const cell = (s) => {
    if (!s || s.p_value === undefined) return `<div class="hm-cell muted">n/a</div>`;
    const sig = s.p_value < 0.05 ? ' hm-sig' : '';
    return `<div class="hm-cell${sig}" style="background:${colorFor(s.mean_delta_pct)}"><div class="pct">${fmtPctOf(s.mean_delta_pct)}</div><span class="pval">p=${fmtP(s.p_value)}</span></div>`;
  };
  let html = `
    <div class="hm-cell hm-head"></div>
    <div class="hm-cell hm-head" style="grid-column:span 2">AB-Filtered (deal-scoped)</div>
    <div class="hm-cell hm-head" style="grid-column:span 2">AB-Overall (population-wide)</div>
    <div class="hm-cell hm-head"></div>
    <div class="hm-cell hm-head">M1/UV %Δ</div>
    <div class="hm-cell hm-head">CVR %Δ</div>
    <div class="hm-cell hm-head">M1/UV %Δ</div>
    <div class="hm-cell hm-head">CVR %Δ</div>`;
  cats.forEach(cat => {
    const pf = D.per_category[cat] || {m1uv:{},cvr:{}};
    const po = (D.per_category_overall||{})[cat] || {m1uv:{},cvr:{}};
    html += `<div class="hm-cell hm-row-label">${cat}</div>`;
    html += cell(pf.m1uv);
    html += cell(pf.cvr);
    html += cell(po.m1uv);
    html += cell(po.cvr);
  });
  root.innerHTML = html;

  // sub-tabs
  const subRoot = document.getElementById(`cat-subtabs-${sl}`);
  const subContent = document.getElementById(`cat-subcontent-${sl}`);
  subRoot.innerHTML = '';
  subContent.innerHTML = '';
  cats.forEach((cat, i) => {
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
    div.innerHTML = `
      <h4 style="font-size:0.92rem;margin-bottom:6px;color:#4a5568">AB-Filtered (deal-scoped)</h4>
      <div class="chart-grid-2">
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${i}-m1uv-f"></canvas></div></div>
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${i}-cvr-f"></canvas></div></div>
      </div>
      <h4 style="font-size:0.92rem;margin-top:14px;margin-bottom:6px;color:#4a5568">AB-Overall (population-wide)</h4>
      <div class="chart-grid-2">
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${i}-m1uv-o"></canvas></div></div>
        <div><div class="chart-wrap"><canvas id="ch-${sl}-${i}-cvr-o"></canvas></div></div>
      </div>`;
    subContent.appendChild(div);
  });
  if (cats.length) initCatCharts(name, cats[0]);
}

function initCatCharts(name, cat) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const cats = D.categories || [];
  const idx = cats.indexOf(cat);
  if (idx < 0) return;
  const filt = ((D.per_category||{})[cat] || {}).daily || [];
  const ovr = ((D.per_category_overall||{})[cat] || {}).daily || [];
  setTimeout(() => {
    if (filt.length) {
      lineChart(`ch-${sl}-${idx}-m1uv-f`, filt, 'm1uv_ctrl', 'm1uv_treat', 'M1/UV ($)');
      lineChart(`ch-${sl}-${idx}-cvr-f`,  filt, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
    }
    if (ovr.length) {
      lineChart(`ch-${sl}-${idx}-m1uv-o`, ovr, 'm1uv_ctrl', 'm1uv_treat', 'M1/UV ($)');
      lineChart(`ch-${sl}-${idx}-cvr-o`,  ovr, 'cvr_ctrl',  'cvr_treat',  'CVR (orders/UDV)');
    }
  }, 0);
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
  if (!s || s.status !== 'ok' || !s.pre_post) {
    root.innerHTML = `<div class="skipped">SEO eval: ${s?.status || 'n/a'}${s?.reason ? ' — ' + s.reason : ''}</div>`;
    return;
  }
  const pp = s.pre_post;
  const ov = pp.overall || {};
  const impPct = ov.impressions_pct_total ?? 0;
  const clkPct = ov.clicks_pct_total ?? 0;
  const did = s.did_overall || {};
  const dV = did.variant || {}, dC = did.control || {}, dD = did.did || {};

  let html = `
    <div class="bar-grid" style="margin-bottom:14px">
      <div class="kpi"><div class="label">Signal level</div><div class="value">${s.signal_level || '?'}</div><div class="delta">post days: ${s.post_days || pp.effective_post_days} (3-day GSC lag)</div></div>
      <div class="kpi"><div class="label">Pre window</div><div class="value">${pp.pre_start} → ${pp.pre_end}</div><div class="delta">${s.pre_days || 28} days</div></div>
      <div class="kpi"><div class="label">Post window</div><div class="value">${pp.post_start} → ${pp.post_end}</div><div class="delta">${s.post_days || pp.effective_post_days} days</div></div>
      <div class="kpi"><div class="label">URLs with GSC data</div><div class="value">${(ov.urls_with_data||0).toLocaleString()}</div><div class="delta">of ${(pp.total_urls_input||0).toLocaleString()} variant input</div></div>
    </div>`;

  if (Object.keys(did).length) {
    html += `
      <h3>Overall DiD (variant vs control, day-normalized)</h3>
      <table style="margin-bottom:18px">
        <thead><tr>
          <th class="label">Group</th><th>URLs (pre)</th><th>URLs (post)</th>
          <th>Impr/day pre→post (%)</th><th>Clicks/day pre→post (%)</th><th>CTR pre→post (Δpp)</th>
        </tr></thead><tbody>
          <tr><td>Variant</td><td>${(dV.pre_url_count||0).toLocaleString()}</td><td>${(dV.post_url_count||0).toLocaleString()}</td>
            <td>${fmtPctOf(dV.imp_pct_change ?? 0)}</td><td>${fmtPctOf(dV.clk_pct_change ?? 0)}</td><td>${fmtPp(dV.ctr_delta_pp ?? 0)}</td></tr>
          <tr><td>Control</td><td>${(dC.pre_url_count||0).toLocaleString()}</td><td>${(dC.post_url_count||0).toLocaleString()}</td>
            <td>${fmtPctOf(dC.imp_pct_change ?? 0)}</td><td>${fmtPctOf(dC.clk_pct_change ?? 0)}</td><td>${fmtPp(dC.ctr_delta_pp ?? 0)}</td></tr>
          <tr style="background:#edf2f7;font-weight:700">
            <td>DiD (variant − control)</td><td></td><td></td>
            ${ppCell(dD.imp_pp)}${ppCell(dD.clk_pp)}${ppCell(dD.ctr_pp)}
          </tr>
        </tbody>
      </table>`;
  } else {
    html += `<div class="skipped" style="margin-bottom:18px"><strong>DiD not computed.</strong> No control URL set was supplied to seo-impact-analyzer; the pipeline can't compute Difference-in-Differences without a parallel control group. Add a <code>resolve-control-urls</code> step or pass a control set to fix.</div>`;
  }

  // DiD per L2
  const order = s.l2_order || [];
  const perL2 = s.did_per_l2 || {};
  if (order.length && Object.keys(perL2).length) {
    html += `<h3>DiD by L2 category</h3>
      <table>
        <thead><tr><th class="label">L2 Category</th><th>Variant URLs (post)</th><th>Control URLs (post)</th>
          <th>Impressions DiD</th><th>Clicks DiD</th><th>CTR DiD</th></tr></thead><tbody>`;
    order.forEach(l2 => {
      const x = perL2[l2]; if (!x) return;
      const v = x.variant||{}, c = x.control||{}, d = x.did||{};
      const impColor = (d.imp_pp ?? null) === null ? 'transparent' : seoColor(d.imp_pp);
      const clkColor = (d.clk_pp ?? null) === null ? 'transparent' : seoColor(d.clk_pp);
      const ctrColor = seoColor(d.ctr_pp || 0);
      html += `<tr>
        <td>${l2}</td>
        <td>${(v.post_url_count||0).toLocaleString()}</td>
        <td>${(c.post_url_count||0).toLocaleString()}</td>
        <td style="background:${impColor}">${d.imp_pp == null ? 'n/a' : fmtPp(d.imp_pp)}</td>
        <td style="background:${clkColor}">${d.clk_pp == null ? 'n/a' : fmtPp(d.clk_pp)}</td>
        <td style="background:${ctrColor}">${fmtPp(d.ctr_pp || 0)}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
  }

  // Variant-only raw pre/post
  html += `
    <h3 style="margin-top:24px">Variant-only pre/post (raw, full URL set incl. unmapped L2)</h3>
    <p class="muted" style="margin-bottom:8px">Reference numbers from the SEO subagent. Raw % deltas are inflated by post-window asymmetry; the DiD table above is the corrected view.</p>
    <div class="chart-grid-2">
      <div><h4 style="font-size:0.95rem;margin-bottom:6px">Impressions (pre vs post)</h4><div class="chart-wrap"><canvas id="ch-${sl}-seo-imp"></canvas></div></div>
      <div><h4 style="font-size:0.95rem;margin-bottom:6px">Clicks (pre vs post)</h4><div class="chart-wrap"><canvas id="ch-${sl}-seo-clk"></canvas></div></div>
    </div>
    <div class="bar-grid" style="margin-top:14px">
      <div class="kpi ${impPct >= 0 ? 'win':'lose'}"><div class="label">Variant-only Impressions Δ (raw)</div><div class="value">${fmtPctOf(impPct)}</div><div class="delta">${(ov.pre_impressions_total||0).toLocaleString()} → ${(ov.post_impressions_total||0).toLocaleString()}</div></div>
      <div class="kpi ${clkPct >= 0 ? 'win':'lose'}"><div class="label">Variant-only Clicks Δ (raw)</div><div class="value">${fmtPctOf(clkPct)}</div><div class="delta">${(ov.pre_clicks_total||0).toLocaleString()} → ${(ov.post_clicks_total||0).toLocaleString()}</div></div>
    </div>`;

  // L2 winners/losers from per_url top-15
  const topk = s.l2_topk || {};
  const topkOrder = (s.l2_order || []).filter(l2 => topk[l2]);
  if (topkOrder.length) {
    html += `
      <h3 style="margin-top:24px">Per-L2 top 15 winners + losers (by clicks delta)</h3>
      <p class="muted" style="margin-bottom:8px">From <code>per_url</code> output of seo-impact-analyzer (variant-side, top 15 per L2).</p>
      <div class="cat-subtabs" id="seo-l2-subtabs-${sl}"></div>
      <div id="seo-l2-content-${sl}"></div>`;
  }

  html += `<p class="muted" style="margin-top:18px">Full SEO passthrough report: <code>${s.passthrough_html||'n/a'}</code></p>`;
  root.innerHTML = html;

  setTimeout(() => {
    const barOpts = { responsive:true, maintainAspectRatio:false, plugins:{legend:{display:false}} };
    const cImp = document.getElementById(`ch-${sl}-seo-imp`);
    if (cImp) {
      if (charts[`ch-${sl}-seo-imp`]) charts[`ch-${sl}-seo-imp`].destroy();
      charts[`ch-${sl}-seo-imp`] = new Chart(cImp, {
        type:'bar',
        data:{ labels:['Pre','Post'], datasets:[{ data:[ov.pre_impressions_total||0, ov.post_impressions_total||0], backgroundColor:['#4A90D9','#E8734A'] }] },
        options: barOpts
      });
    }
    const cClk = document.getElementById(`ch-${sl}-seo-clk`);
    if (cClk) {
      if (charts[`ch-${sl}-seo-clk`]) charts[`ch-${sl}-seo-clk`].destroy();
      charts[`ch-${sl}-seo-clk`] = new Chart(cClk, {
        type:'bar',
        data:{ labels:['Pre','Post'], datasets:[{ data:[ov.pre_clicks_total||0, ov.post_clicks_total||0], backgroundColor:['#4A90D9','#E8734A'] }] },
        options: barOpts
      });
    }
    if (topkOrder.length) buildSeoL2Subtabs(name);
  }, 0);
}

function buildSeoL2Subtabs(name) {
  const D = ROOT.experiments[name];
  const sl = slug(name);
  const root = document.getElementById(`seo-l2-subtabs-${sl}`);
  const content = document.getElementById(`seo-l2-content-${sl}`);
  if (!root || !content) return;
  const topk = D.seo.l2_topk || {};
  const order = (D.seo.l2_order || []).filter(l2 => topk[l2]);
  root.innerHTML = ''; content.innerHTML = '';
  order.forEach((l2, i) => {
    const btn = document.createElement('button');
    btn.className = 'cat-subtab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = `${l2} (${topk[l2].n_total})`;
    btn.dataset.l2 = l2;
    btn.onclick = () => {
      root.querySelectorAll('.cat-subtab-btn').forEach(b => b.classList.toggle('active', b.dataset.l2 === l2));
      content.querySelectorAll('.cat-subtab-content').forEach(c => c.classList.toggle('active', c.dataset.l2 === l2));
    };
    root.appendChild(btn);
    const div = document.createElement('div');
    div.className = 'cat-subtab-content' + (i === 0 ? ' active' : '');
    div.dataset.l2 = l2;
    const tk = topk[l2];
    const renderRow = (r) => {
      const slug2 = (r.url || '').split('/').pop();
      const cd = r.clk_delta || 0, id_ = r.imp_delta || 0;
      const cls = cd >= 0 ? '#22543d' : '#742a2a';
      const cIcls = id_ >= 0 ? '#22543d' : '#742a2a';
      const flags = [];
      if (r.low_confidence) flags.push('<span class="badge badge-prelim" title="low confidence">low conf</span>');
      if (r.ctr_significant) flags.push('<span class="badge badge-pass" title="CTR sig">CTR sig</span>');
      return `<tr>
        <td><a href="${r.url}" target="_blank" rel="noopener">${slug2.replace(/&/g,'&amp;').replace(/</g,'&lt;')}</a> ${flags.join(' ')}</td>
        <td>${(r.pre_imp||0).toLocaleString()} → ${(r.post_imp||0).toLocaleString()}</td>
        <td style="color:${cIcls}"><strong>${(id_>=0?'+':'')+id_.toLocaleString()}</strong></td>
        <td>${(r.pre_clk||0).toLocaleString()} → ${(r.post_clk||0).toLocaleString()}</td>
        <td style="color:${cls}"><strong>${(cd>=0?'+':'')+cd.toLocaleString()}</strong></td>
        <td>${r.pre_pos == null ? 'n/a' : Number(r.pre_pos).toFixed(1)} → ${r.post_pos == null ? 'n/a' : Number(r.post_pos).toFixed(1)}</td>
      </tr>`;
    };
    const headTr = `<thead><tr>
      <th class="label">URL</th><th>Impressions pre→post</th><th>Δ Impr</th>
      <th>Clicks pre→post</th><th>Δ Clicks</th><th>Avg pos pre→post</th>
    </tr></thead>`;
    div.innerHTML = `
      <p class="muted" style="margin-bottom:6px">${l2}: <strong>${tk.n_total.toLocaleString()}</strong> URLs total in per_url; <strong>${tk.n_with_change.toLocaleString()}</strong> with non-zero clicks delta.</p>
      <h4 style="margin:12px 0 6px;font-size:0.95rem;color:#22543d">Top ${tk.winners.length} winners (clicks gained)</h4>
      <table>${headTr}<tbody>${tk.winners.map(renderRow).join('')}</tbody></table>
      <h4 style="margin:18px 0 6px;font-size:0.95rem;color:#742a2a">Top ${tk.losers.length} losers (clicks lost)</h4>
      <table>${headTr}<tbody>${tk.losers.map(renderRow).join('')}</tbody></table>`;
    content.appendChild(div);
  });
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
  if (d.by_category && d.by_category.length) {
    html += `<h3 style="margin-top:24px">By Category (deal-level)</h3><table><thead><tr><th class="label">Category</th><th>UDV ctrl</th><th>UDV treat</th><th>CVR Δ (pp)</th><th>m1 Δ</th></tr></thead><tbody>`;
    d.by_category.forEach(r => {
      const cls = (r.m1_delta||0)>=0 ? '#22543d' : '#742a2a';
      html += `<tr><td>${r.category||''}</td><td>${(r.udv_ctrl||0).toLocaleString()}</td><td>${(r.udv_treat||0).toLocaleString()}</td><td>${((r.cvr_delta||0)*100).toFixed(3)}pp</td><td style="color:${cls}"><strong>${fmtMoney(r.m1_delta||0)}</strong></td></tr>`;
    });
    html += `</tbody></table>`;
  }
  if (d.by_booking_platform && d.by_booking_platform.length) {
    html += `<h3 style="margin-top:24px">By Booking Platform</h3><table><thead><tr><th class="label">Platform</th><th>Deal count</th><th>UDV</th><th>m1 Δ</th></tr></thead><tbody>`;
    d.by_booking_platform.forEach(r => {
      const cls = (r.m1_delta||0)>=0 ? '#22543d' : '#742a2a';
      html += `<tr><td>${r.booking_platform||'(null)'}</td><td>${(r.deal_count||0).toLocaleString()}</td><td>${(r.udv||0).toLocaleString()}</td><td style="color:${cls}"><strong>${fmtMoney(r.m1_delta||0)}</strong></td></tr>`;
    });
    html += `</tbody></table>`;
  }
  root.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', () => {
  header();
  scoreboard();
  buildExpTabs();
});
