/* Planalogy — Analog Finder, one screen.
   Flow: pick a target on Mars -> switch to Earth -> choose a mission -> move through the years -> tune the 8 parameters.
   Every Earth land cell is ranked against the Mars cell with the analogue engine's comparators, reproduced in
   js/scoring.js on raw values exported by backend/web_export.py (data/planalogy/*.json). */
(function(){
const TT = window.TT, h = TT.h, PS = window.PlanalogyScoring;
const DATA = 'data/planalogy/';
const TOP = 8;
const REGION = {
  '-23.5,-68.5': 'Atacama Desert, Chile', '34.5,76.5': 'Ladakh / Aksai Chin', '37.5,75.5': 'Pamir, Xinjiang',
  '40.5,78.5': 'Tarim Basin margin', '38.5,76.5': 'Kashgar, Tarim Basin', '31.5,-5.5': 'Pre-Saharan Morocco',
  '41.5,79.5': 'Northern Tarim Basin', '14.5,40.5': 'Danakil Depression', '30.5,69.5': 'Balochistan',
  '30.5,81.5': 'Ngari, western Tibet', '44.5,83.5': 'Junggar Basin', '30.5,84.5': 'Tibetan Plateau',
  '30.5,87.5': 'Tibetan Plateau', '31.5,81.5': 'Western Tibetan Plateau', '30.5,83.5': 'Tibetan Plateau',
  '67.5,177.5': 'Chukotka', '70.5,-54.5': 'West Greenland', '37.5,45.5': 'Lake Urmia basin, Iran',
  '-24.5,-69.5': 'Atacama Desert, Chile', '-24.5,-67.5': 'Salar de Arizaro', '39.5,73.5': 'Kara-Kul, Pamir',
  '-77.5,161.5': 'McMurdo Dry Valleys', '75.5,-89.5': 'Devon Island (Haughton)', '39.5,99.5': 'Hexi Corridor, Gansu'
};
/* Moon: planned and proposed sites (same records as the team's site database). Shown as a preview, not scored. */
const MOON_SITES = [
  {id:'m1', name:'Shackleton crater rim', lat:-89.67, lon:129.78, kind:'base', note:'Proposed outpost location'},
  {id:'m2', name:'Malapert Massif', lat:-86.0, lon:0.3, kind:'landing', note:'Artemis III candidate region'},
  {id:'m3', name:'Haworth', lat:-86.9, lon:-4.0, kind:'landing', note:'Artemis III candidate region'},
  {id:'m4', name:'Mons Mouton', lat:-84.6, lon:31.0, kind:'landing', note:'Artemis III candidate region'},
  {id:'m5', name:'Nobile rim', lat:-85.28, lon:53.27, kind:'landing', note:'Artemis III candidate region'},
  {id:'m6', name:'de Gerlache rim', lat:-88.5, lon:-87.1, kind:'landing', note:'Artemis III candidate region'},
  {id:'m7', name:'Mare Tranquillitatis pit', lat:8.3355, lon:33.222, kind:'base', note:'Lava tube skylight'},
  {id:'m8', name:'Marius Hills Hole', lat:14.1, lon:-56.738, kind:'base', note:'Lava tube skylight'}
];
const DEFAULT_FW = {slope_deg:1, roughness_m:1, relief_m:1, surface_temp_swing_K:2, surface_temp_min_K:1, air_temp_swing_K:1, ati_percentile:1, albedo:1, mineral_groups:1, rock_group:1, inside_impact_structure:1, ground_ice_flag:1};
const BODIES = [['mars', 'Mars', 'target'], ['moon', 'Moon', 'preview'], ['earth', 'Earth', 'analogs']];
const cache = {};
const load = f => cache[f] || (cache[f] = fetch(DATA + f).then(r => { if (!r.ok) throw new Error(f + ': ' + r.status); return r.json(); }));
const pct = x => x == null ? '–' : Math.round(x * 100);
const region = it => REGION[it.lat + ',' + it.lon];
const sspName = s => String(s).replace(/^ssp(\d)(\d)(\d)$/, 'SSP$1-$2.$3');
const words = s => String(s).replace(/_/g, ' ');

/* score -> colour (stretched over the current ranking) */
const STOPS = [[0, [40, 70, 150, .16]], [.4, [64, 128, 220, .5]], [.65, [96, 190, 240, .78]], [.82, [250, 210, 110, .92]], [1, [255, 110, 60, 1]]];
function ramp(t){
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < STOPS.length; i++){
    const [t1, c1] = STOPS[i]; const [t0, c0] = STOPS[i - 1];
    if (t <= t1){ const k = (t - t0) / (t1 - t0); return c0.map((v, j) => v + (c1[j] - v) * k); }
  }
  return STOPS[STOPS.length - 1][1];
}
const rgba = c => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${c[3].toFixed(3)})`;

/* one feature value of a cell, written for people */
function show(f, v){
  if (v == null || (Array.isArray(v) && !v.length)) return null;
  if (f.kind === 'boolean') return v ? 'yes' : 'no';
  if (f.kind === 'set') return v.map(words).join(', ');
  if (f.kind === 'categorical') return words(v);
  if (f.id === 'ati_percentile') return Math.round(v * 100) + ' % rank';
  const a = Math.abs(v), d = a >= 100 ? 0 : a >= 10 ? 1 : 2;
  return (+v).toFixed(d) + (f.unit && f.unit !== '1' ? ' ' + (f.unit === 'deg' ? '°' : f.unit) : '');
}

TT.pages.finder = function(root){
  const st = {m:null, target:'gale', custom:null, preset:null, year:'now', scen:null, dry:true, cw:{}, on:{}, fw:Object.assign({}, DEFAULT_FW),
              req:[], reqF:[], res:null, sims:null, sel:null, moonSel:null, view:'mars', hires:null, fresh:new Set(), lost:[], landed:false};
  let g3 = null, dead = false;
  const simCache = new Map();

  /* ---------- skeleton ---------- */
  const cv = h('canvas', {class:'view grab', role:'application', 'aria-label':'Globe. Drag to rotate, scroll to zoom, arrow keys also work.'});
  const bsw = h('div', {class:'bsw', role:'radiogroup', 'aria-label':'Body shown'});
  const status = h('div', {class:'statusline', role:'status', 'aria-live':'polite'});
  const tl = h('div', {class:'tl now', hidden:true, role:'group', 'aria-label':'Year and climate scenario'});
  const cta = h('button', {class:'btn primary cta', type:'button', onclick: () => setView('earth')}, 'Find analogs on Earth');
  const stage = h('div', {class:'stage'}, cv, bsw, status, tl, cta);
  const leftP = h('aside', {class:'glass panel-l', 'aria-label':'Target, mission and parameters'});
  const rightP = h('aside', {class:'glass panel-r', 'aria-label':'Results'});
  root.appendChild(h('div', {class:'explore finder'}, stage, leftP, rightP));

  /* ---------- left panel: everything visible at once ---------- */
  const targetSeg = h('div', {class:'seg f-seg', role:'radiogroup', 'aria-label':'Mars target'});
  const targetInfo = h('p', {class:'p-lead'});
  const presetBox = h('div', {class:'f-presets'});
  const verdict = h('p', {class:'p-lead'});
  const sliders = h('div', {class:'prs'});
  const dryInp = h('input', {type:'checkbox', id:'f-dry', checked:true, onchange: e => { st.dry = e.target.checked; rescore(); }});
  leftP.append(h('div', {class:'panel-body'},
    h('section', {class:'panel-sec'}, h('h4', null, 'Target on Mars'), targetSeg, targetInfo),
    h('section', {class:'panel-sec'}, h('h4', null, 'Mission'), presetBox, verdict),
    h('section', {class:'panel-sec'}, h('h4', null, 'Parameters', h('span', {class:'h-note'}, 'on or off, weight 0 to 5')), sliders,
      h('label', {class:'f-switch', for:'f-dry'}, dryInp, h('span', null, 'Dry, bare land only')))));

  /* ---------- right panel ---------- */
  const legend = h('span', {class:'f-legend'});
  const rHead = h('div', {class:'panel-head'});
  const rBody = h('div', {class:'panel-body'});
  rightP.append(rHead, rBody);

  /* ---------- globe ---------- */
  if (TT.webgl) g3 = TT.createGlobe(cv, {body:'mars', markerPx:26, dist:2.9,
    onPick: it => { if (it.body === 'earth') select(it.id, true); else if (it.body === 'mars' && it.key) setTarget(it.key); else if (it.body === 'moon') moonSelect(it.id); },
    onPin: (lat, lon) => { if (st.view === 'mars') pickAt(lat, lon); }});
  if (!g3){ cv.style.display = 'none'; stage.appendChild(h('p', {class:'no-gl'}, 'The globes need WebGL, which this browser has switched off. The lists and scores still work.')); }

  /* ---------- state helpers ---------- */
  const cats = () => st.m.categories;
  const presetTarget = () => st.m.targets.find(t => t.key === st.target);
  const target = () => st.target === 'custom' ? st.custom : presetTarget();
  const targetName = () => target().name;
  const shortName = n => n.split(' (')[0];
  function applyPreset(p){
    st.preset = p.id;
    const mx = Math.max(...Object.values(p.category_weights));
    st.cw = {}; st.on = {};
    cats().forEach(c => { const w = mx > 0 ? (p.category_weights[c.id] || 0) * 5 / mx : 0; st.cw[c.id] = Math.round(w * 10) / 10; st.on[c.id] = w > 0; });
    st.fw = Object.assign({}, DEFAULT_FW, p.feature_weights);
    st.req = p.requirements || []; st.reqF = p.required_features || [];
  }
  const missing = () => new Set(st.sims ? st.sims.targetMissing : []);
  const noData = c => { const miss = missing(); return st.m.features.filter(f => f.category === c.id).every(f => miss.has(f.id)); };
  function effectiveFW(){ const fw = Object.assign({}, st.fw); missing().forEach(f => { fw[f] = 0; }); return fw; }
  function effectiveCW(){ const cw = {}; cats().forEach(c => { cw[c.id] = st.on[c.id] && !noData(c) ? (st.cw[c.id] || 0) : 0; }); return cw; }

  const scens = () => Object.keys(st.m.files.earth_by_scenario || {});
  const yearFile = year => { const by = st.m.files.earth_by_scenario; return (by && by[st.scen] && by[st.scen][year]) || st.m.files.earth[year]; };
  async function earthTable(year){
    const base = await load(st.m.files.earth.now);
    if (year === 'now') return base;
    const file = yearFile(year), key = 'earth@' + file;
    if (!cache[key]) cache[key] = load(file).then(yt => PS.earthForYear(base, yt));
    return cache[key];
  }

  async function rescore(){
    if (dead || !st.m) return;
    const t = target(), y = st.year, sc = st.scen, tk = st.target === 'custom' ? t.lat + ',' + t.lon : st.target;
    try {
      const earth = await earthTable(y), today = y === 'now' ? earth : await earthTable('now');
      if (dead || y !== st.year || sc !== st.scen || t !== target()) return;
      const simsOf = (table, key) => { if (!simCache.has(key)) simCache.set(key, PS.similarities(st.m, table, t.values)); return simCache.get(key); };
      st.sims = simsOf(earth, tk + '@' + (y === 'now' ? y : y + '@' + sc));
      const opt = {categoryWeights: effectiveCW(), featureWeights: effectiveFW(), requirements: st.req,
                   requiredFeatures: st.reqF.filter(f => !st.sims.targetMissing.includes(f)), onlyDryBare: st.dry};
      st.res = PS.scoreCells(st.m, earth, st.sims, opt);
      /* which cells are candidates in that year but not today, and the other way round */
      st.fresh = new Set(); st.lost = [];
      if (y !== 'now'){
        const now = PS.scoreCells(st.m, today, simsOf(today, tk + '@now'), opt);
        const a = new Set(now.ranked.map(x => x.id)), b = new Set(st.res.ranked.map(x => x.id));
        b.forEach(id => { if (!a.has(id)) st.fresh.add(id); }); now.ranked.forEach(x => { if (!b.has(x.id)) st.lost.push(x); });
      }
      if (st.sel && !st.res.ranked.some(x => x.id === st.sel)) st.sel = null;
      paintOverlay(); pushMarkers(); drawRight(); drawStatus(); drawSliders();
      if (st.view === 'earth' && !st.landed) land();
    } catch(e){
      console.error(e); st.res = null;
      status.textContent = /positive weight/.test(e.message) ? 'Switch on at least one parameter.' : 'Could not compute scores.';
      if (st.view === 'earth'){ TT.clear(rBody); rBody.append(h('p', {class:'muted small'}, status.textContent)); }
    }
  }
  const rescoreSoon = TT.debounce(rescore, 60);

  /* ---------- score overlay on the Earth globe ---------- */
  const ov = document.createElement('canvas'); ov.width = 1440; ov.height = 720;
  function paintOverlay(){
    const x = ov.getContext('2d'); x.clearRect(0, 0, 1440, 720);
    const r = st.res.ranked;
    if (r.length){
      const hi = r[0].score, lo = r[r.length - 1].score, span = (hi - lo) || 1;
      for (let i = r.length - 1; i >= 0; i--){
        const it = r[i]; x.fillStyle = rgba(ramp((it.score - lo) / span));
        x.fillRect((it.lon - .5 + 180) * 4, (90 - it.lat - .5) * 4, 4, 4);
      }
      /* against today: white outline = becomes a candidate, red outline = drops out */
      const box = it => x.strokeRect((it.lon - .5 + 180) * 4 + .5, (90 - it.lat - .5) * 4 + .5, 3, 3);
      x.lineWidth = 1; x.strokeStyle = '#ff6b6b'; st.lost.forEach(box);
      x.strokeStyle = '#fff'; r.forEach(it => { if (st.fresh.has(it.id)) box(it); });
      drawLegend(lo, hi);
    } else drawLegend(null, null);
    if (g3) g3.setOverlay('earth', ov);
  }
  function drawLegend(lo, hi){
    TT.clear(legend);
    if (lo == null) return;
    const bar = h('span', {class:'f-ramp', style:{background:`linear-gradient(90deg,${[0, .4, .65, .82, 1].map(t => rgba(ramp(t)).replace(/,[\d.]+\)$/, ',1)')).join(',')})`}});
    legend.append(h('span', null, Math.round(lo * 100)), bar, h('span', null, Math.round(hi * 100)));
  }

  /* ---------- markers and views ---------- */
  function pushMarkers(){
    if (!g3 || !st.m) return;
    const items = []; let sel = null;
    if (st.view === 'earth'){
      if (st.res) st.res.ranked.slice(0, TOP).forEach(it => items.push({id: it.id, lat: it.lat, lon: it.lon, body:'earth', kind:'analog'}));
      sel = st.sel;
    } else if (st.view === 'mars'){
      st.m.targets.forEach(t => items.push({id:'t-' + t.key, key: t.key, lat: t.lat, lon: t.lon, body:'mars', kind:'landing'}));
      if (st.custom) items.push({id:'t-custom', lat: st.custom.lat, lon: st.custom.lon, body:'mars', kind:'user'});
      sel = 't-' + st.target;
    } else {
      MOON_SITES.forEach(s => items.push({id: s.id, lat: s.lat, lon: s.lon, body:'moon', kind: s.kind}));
      sel = st.moonSel;
    }
    g3.setMarkers(items); g3.setSelection(sel, []);
  }
  function drawBodies(){
    TT.clear(bsw);
    BODIES.forEach(([id, name, role]) => bsw.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': st.view === id, class:'b-' + id,
      onclick: () => setView(id)}, h('b', null, name), h('small', null, role))));
  }
  function land(){
    const top = st.res && st.res.ranked[0]; if (!top || !g3) return;
    st.landed = true; g3.focus(top.lat, top.lon, {dist:3.0});
  }
  function setView(v){
    st.view = v; st.landed = false;
    if (g3){
      g3.setBody(v); g3.setPinMode(v === 'mars');
      if (v === 'mars'){ const t = target(); g3.focus(t.lat, t.lon, {dist:3.1}); }
      else if (v === 'moon') g3.focus(-38, 12, {dist:3.1});
      else if (st.sel){ const it = st.res && st.res.ranked.find(x => x.id === st.sel); if (it){ st.landed = true; g3.focus(it.lat, it.lon, {dist:2.1}); } }
      else land();
    }
    drawBodies(); pushMarkers(); drawYears(); drawRight(); drawStatus();
    cta.hidden = v !== 'mars';
  }

  /* ---------- Mars target ---------- */
  function setTarget(key){
    st.target = key; st.sel = null; st.landed = false;
    drawTargets(); drawRight(); rescore();
    if (g3 && st.view === 'mars'){ const t = target(); g3.focus(t.lat, t.lon, {dist:3.1}); pushMarkers(); }
  }
  async function pickAt(lat, lon){
    try {
      status.textContent = 'Reading the Mars grid…';
      const mars = await load(st.m.files.mars);
      const cell = PS.marsCell(st.m, mars, lat, lon);
      if (!cell){ TT.toast('No Mars data for that point.', true); drawStatus(); return; }
      st.custom = {key:'custom', lat: cell.lat, lon: cell.lon, values: cell.values, name:'Mars ' + TT.fmtCoord(cell.lat, cell.lon, 1)};
      setTarget('custom');
    } catch(e){ console.error(e); TT.toast('Could not load Mars data.', true); drawStatus(); }
  }

  /* ---------- left panel drawing ---------- */
  function drawTargets(){
    TT.clear(targetSeg);
    st.m.targets.forEach(t => targetSeg.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': t.key === st.target, title: t.name,
      onclick: () => setTarget(t.key)}, shortName(t.name).replace(' Crater', ''))));
    const t = target();
    TT.clear(targetInfo);
    targetInfo.append(st.target === 'custom' ? h('b', null, 'Your point, ' + TT.fmtCoord(t.lat, t.lon, 1)) : h('b', null, t.name + ', ' + TT.fmtCoord(t.lat, t.lon, 1)),
      h('br'), 'Or click anywhere on the Mars globe.');
  }
  function drawPresets(){
    TT.clear(presetBox);
    st.m.presets.forEach(p => presetBox.appendChild(h('button', {class:'btn sm f-preset', type:'button', 'aria-pressed': st.preset === p.id, title: p.mission,
      onclick: () => { applyPreset(p); drawPresets(); drawSliders(); rescore(); }}, p.name)));
    const p = st.m.presets.find(x => x.id === st.preset);
    verdict.textContent = !p ? 'Your own weights.' : p.mission + '. ' + (p.weights_used === 'calibrated' ? 'Weights tuned on known analogs.' : 'Weights from the science team.')
      + (st.req.length ? ' Earth site must have ground ice.' : '');
  }
  function drawSliders(){
    TT.clear(sliders);
    cats().forEach(c => {
      const id = 'w-' + c.id, na = !!st.sims && noData(c), on = st.on[c.id] && !na;
      const val = h('output', {for:id}, na ? 'n/a' : on ? (st.cw[c.id] || 0).toFixed(1) : 'off');
      const box = h('input', {type:'checkbox', id:'on-' + c.id, checked: on, disabled: na, 'aria-label':'Use ' + c.label,
        onchange: e => { st.on[c.id] = e.target.checked; if (e.target.checked && !(st.cw[c.id] > 0)) st.cw[c.id] = 2.5; st.preset = null; drawPresets(); drawSliders(); rescore(); }});
      const inp = h('input', {id, type:'range', min:'0', max:'5', step:'0.5', value:String(on ? st.cw[c.id] || 0 : 0), class:'f-range', disabled: na, 'aria-label': c.label + ' weight',
        oninput: e => { const v = +e.target.value; st.cw[c.id] = v; st.on[c.id] = v > 0; box.checked = v > 0; val.textContent = v > 0 ? v.toFixed(1) : 'off'; row.classList.toggle('off', !(v > 0));
          if (st.preset){ st.preset = null; drawPresets(); } rescoreSoon(); }});
      const row = h('div', {class:'pr' + (on ? '' : ' off'), title: na ? 'No data at this Mars cell' : null}, box, h('label', {for:'on-' + c.id}, c.label), inp, val);
      sliders.appendChild(row);
    });
  }

  /* ---------- the time arc: today on the left, the projected years along a shallow orbit ---------- */
  function drawYears(){
    const ys = st.m ? st.m.years.map(String) : []; tl.hidden = ys.length < 2 || st.view !== 'earth'; if (tl.hidden) return;
    TT.clear(tl);
    const W = 1000, Y0 = 52, SAG = 30, n = ys.length, cur = Math.max(0, ys.indexOf(String(st.year)));
    const at = i => { const t = i / (n - 1), x = 60 + t * (W - 120); return [x, Y0 + SAG * 4 * t * (1 - t)]; };
    const path = k => { let d = ''; for (let i = 0; i <= 40; i++){ const t = (i / 40) * k, x = 60 + t * (W - 120), y = Y0 + SAG * 4 * t * (1 - t); d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); } return d; };
    const fut = st.year !== 'now';
    tl.className = 'tl ' + (fut ? 'future' : 'now');
    tl.insertAdjacentHTML('beforeend', '<svg viewBox="0 0 ' + W + ' 96" preserveAspectRatio="none" aria-hidden="true"><path class="arc" vector-effect="non-scaling-stroke" d="' + path(1) + '"/>' + (cur ? '<path class="arc-done" vector-effect="non-scaling-stroke" d="' + path(cur / (n - 1)) + '"/>' : '') + '</svg>');
    tl.appendChild(h('button', {class:'tl-now', type:'button', title:'Back to today', onclick: () => setYear('now')}, fut ? 'Projected' : 'Today'));
    tl.appendChild(h('div', {class:'tl-what'}, fut ? 'Earth in ' + st.year : 'Measured climate'));
    const ss = scens();
    if (ss.length > 1){
      const box = h('div', {class:'tl-scen', role:'radiogroup', 'aria-label':'Climate scenario'});
      ss.forEach(s => box.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': s === st.scen, title: (st.m.scenario_labels || {})[s] || s,
        onclick: () => { st.scen = s; if (st.year === 'now') st.year = ys[Math.min(2, n - 1)]; drawYears(); rescore(); }}, sspName(s))));
      tl.appendChild(box);
    }
    const stops = h('div', {role:'radiogroup', 'aria-label':'Year'});
    ys.forEach((y, i) => { const [x, yy] = at(i);
      stops.appendChild(h('button', {class:'tl-stop', type:'button', role:'radio', 'aria-checked': i === cur, style:{left: (x / W * 100) + '%', top: yy + 'px'},
        onclick: () => setYear(y)}, h('i'), h('span', null, y === 'now' ? 'Today' : y))); });
    tl.appendChild(stops);
  }
  function setYear(y){ st.year = String(y); drawYears(); rescore(); }

  /* ---------- status line ---------- */
  function drawStatus(){
    if (!st.m) return;
    if (st.view === 'mars'){ status.textContent = 'Target: ' + targetName() + '. Click the globe to move it.'; return; }
    if (st.view === 'moon'){ status.textContent = 'Moon preview: sites are shown, scoring needs the Moon grid (next step).'; return; }
    if (!st.res){ status.textContent = ''; return; }
    const n = st.res.ranked.length.toLocaleString() + (st.dry ? ' dry, bare' : '') + ' Earth cells ranked against ' + shortName(targetName());
    status.textContent = st.year === 'now' ? n : n + ' for ' + st.year + ' (' + sspName(st.scen) + '). Against today ' + st.lost.length + ' drop out (red outline) and ' + st.fresh.size + ' join (white outline).';
  }

  /* ---------- right panel ---------- */
  function knownName(id){ const k = st.m.presets.flatMap(p => p.known_analogs).find(a => a.id === id); return k ? k.name : null; }
  function siteRow(it){
    const known = knownName(it.id);
    return h('button', {class:'f-site', type:'button', 'aria-current': st.sel === it.id ? 'true' : null, onclick: () => select(it.id, true)},
      h('span', {class:'f-pos'}, '#' + it.position),
      h('span', {class:'f-name'}, region(it) ? region(it) : TT.fmtCoord(it.lat, it.lon, 1),
        known ? h('span', {class:'badge measured'}, 'known analog') : null,
        st.fresh.has(it.id) ? h('span', {class:'badge derived'}, 'new in ' + st.year) : null,
        h('span', {class:'f-bar'}, h('i', {style:{width: pct(it.score) + '%'}}))),
      h('span', {class:'f-score'}, pct(it.score)));
  }
  function drawRight(){
    if (!st.m) return;
    TT.clear(rHead); TT.clear(rBody);
    if (st.view === 'mars') return drawTargetCard();
    if (st.view === 'moon') return drawMoon();
    if (!st.res){ rHead.append(h('h2', null, 'Best analogs')); rBody.append(h('p', {class:'muted small'}, 'Ranking…')); return; }
    const it = st.sel && st.res.ranked.find(x => x.id === st.sel);
    if (it) return drawCard(it);
    rHead.append(h('h2', null, 'Best analogs'), h('div', {class:'r-legend'}, h('span', null, 'Similarity to ' + shortName(targetName())), legend));
    const r = st.res;
    if (!r.ranked.length){ rBody.append(h('p', {class:'muted small'}, 'No Earth cell passes. Switch a parameter back on or turn off the dry-land filter.')); return; }
    r.ranked.slice(0, TOP).forEach(x => rBody.appendChild(siteRow(x)));
    const ks = (st.m.presets.find(p => p.id === st.preset) || st.m.presets[0]).known_analogs;
    rBody.appendChild(h('h4', {class:'f-sub'}, 'Where known test sites rank'));
    ks.forEach(k => { const x = r.ranked.find(y => y.id === k.id);
      rBody.appendChild(x ? siteRow(x) : h('div', {class:'f-site off'}, h('span', {class:'f-pos'}, '–'), h('span', {class:'f-name'}, k.name,
        h('span', {class:'tiny muted', style:{display:'block', fontWeight:400}}, r.partial.some(y => y.id === k.id) ? 'incomplete data' : r.excluded.some(y => y.id === k.id) ? 'no ground ice' : 'not dry, bare land' + (st.year === 'now' ? '' : ' in ' + st.year))), h('span', null))); });
  }
  function drawTargetCard(){
    const t = target();
    rHead.append(h('h2', null, st.target === 'custom' ? 'Your Mars point' : shortName(t.name)));
    const rows = st.m.features.map(f => { const v = show(f, t.values[f.id]);
      return h('div', {class:'tv' + (v == null ? ' off' : '')}, h('span', null, f.label.replace(' (proxy)', '').replace(' (rank within planet)', '')), h('b', null, v == null ? 'no data' : v)); });
    TT.append(rBody, [h('p', {class:'p-lead'}, TT.fmtCoord(t.lat, t.lon, 1) + ', one 1° cell (about 59 km on Mars). These measured values are what Earth is compared with.'), rows]);
  }
  function drawMoon(){
    rHead.append(h('h2', null, 'Moon sites'));
    rBody.append(h('p', {class:'p-lead'}, 'Planned and proposed lunar base sites. The same search works for the Moon once its data grid is added; today they are shown without scores.'));
    MOON_SITES.forEach(s => rBody.appendChild(h('button', {class:'f-site moon', type:'button', 'aria-current': st.moonSel === s.id ? 'true' : null, onclick: () => moonSelect(s.id)},
      h('span', {class:'f-name'}, s.name, h('span', {class:'tiny muted', style:{display:'block', fontWeight:400}}, s.note + ', ' + TT.fmtCoord(s.lat, s.lon, 1))))));
  }
  function moonSelect(id){
    st.moonSel = id; const s = MOON_SITES.find(x => x.id === id);
    if (g3 && s) g3.focus(s.lat, s.lon, {dist:2.1});
    pushMarkers(); drawRight();
  }
  function drawCard(it){
    rHead.append(h('button', {class:'btn ghost sm back', type:'button', onclick: () => { st.sel = null; pushMarkers(); drawRight(); }}, 'All sites'));
    const cw = effectiveCW(), card = PS.card(st.m, it, {categoryWeights: cw, featureWeights: effectiveFW()});
    const known = knownName(it.id), th = st.m.thresholds || {strong_at_least:75, weak_at_most:40};
    const bars = cats().filter(c => cw[c.id] > 0 && card.categories[c.id] != null).map(c => { const s = card.categories[c.id] * 100;
      return h('div', {class:'f-cat'}, h('span', null, c.label), h('span', {class:'f-bar ' + (s >= th.strong_at_least ? 'good' : s > th.weak_at_most ? 'mid' : 'low')}, h('i', {style:{width: Math.max(2, s) + '%'}})), h('span', null, Math.round(s))); });
    TT.append(rBody, [
      h('div', {class:'f-card-head'},
        h('div', null, h('div', {class:'tiny muted'}, '#' + it.position + ' of ' + st.res.ranked.length.toLocaleString()),
          h('h3', null, region(it) || 'Earth cell'),
          h('div', {class:'tiny muted'}, TT.fmtCoord(it.lat, it.lon, 1) + ', 1° cell')),
        h('div', {class:'f-big'}, h('b', null, pct(it.score)), h('span', null, '/100'))),
      known ? h('span', {class:'badge measured'}, 'Known analog: ' + known) : null,
      st.fresh.has(it.id) ? h('span', {class:'badge derived'}, 'Becomes a candidate by ' + st.year) : null,
      h('div', {class:'f-group'}, h('h4', null, 'Match with ' + shortName(targetName()) + ', by parameter'), bars),
      hiresBlock(it)]);
  }
  /* 1-km zoom-in for the sites the Data team downloaded in high resolution (process_future_hires.py) */
  function hiresBlock(it){
    const site = st.hires && st.hires.sites.find(s => s.lat === it.lat && s.lon === it.lon);
    if (!site || !site.today) return null;
    const ss = Object.keys(site.scenarios || {}); if (!ss.length) return null;
    const sc = ss.includes(st.scen) ? st.scen : ss[0], yrs = Object.keys(site.scenarios[sc]).sort();
    const cols = [['Today', site.today]].concat(yrs.map(y => [y, site.scenarios[sc][y]]));
    const f = (v, d) => v == null ? '–' : (+v).toFixed(d);
    const row = (label, key, d, unit) => h('tr', null, h('td', null, label), cols.map(([, v], i) => h('td', {class: i && v[key] != null && cols[0][1][key] != null ? (v[key] > cols[0][1][key] ? 'up' : v[key] < cols[0][1][key] ? 'down' : '') : ''}, f(v[key], d) + (unit || ''))));
    const map = site.maps && site.maps[sc], nm = cols[cols.length - 1][1].n_models;
    return h('div', {class:'hr'},
      h('h4', null, 'Inside this cell', h('span', {class:'km'}, '1 km')),
      h('p', {class:'tiny muted', style:{margin:0}}, 'Climate today and projected, ' + sspName(sc) + (nm ? ', mean of ' + nm + ' model' + (nm > 1 ? 's' : '') : '') + '.'),
      h('table', null, h('thead', null, h('tr', null, h('th', null, ''), cols.map(([y]) => h('th', null, y)))),
        h('tbody', null, row('Air temperature', 'tmean_C', 1, ' °C'), row('Day–night swing', 'air_temp_swing_K', 1, ' K'), row('Rain per year', 'precip_mm_yr', 0, ' mm'),
          row('Hyper-arid share', 'share_hyperarid_pct', 0, ' %'), row('Dry enough for Mars', 'share_mars_dry_pct', 0, ' %'))),
      map ? h('a', {href: DATA + 'hires/' + map, target:'_blank', rel:'noopener'}, h('img', {src: DATA + 'hires/' + map, alt:'1-km maps of temperature and aridity for this cell, today and projected', loading:'lazy'})) : null,
      h('p', {class:'tiny muted', style:{margin:'6px 0 0'}}, 'Fine pattern from today\'s climate; the change itself comes from coarse climate models.'));
  }
  function select(id, fly){
    st.sel = id; const it = st.res && st.res.ranked.find(x => x.id === id);
    if (st.view !== 'earth') setView('earth');
    pushMarkers(); drawRight();
    if (fly && g3 && it){ st.landed = true; g3.focus(it.lat, it.lon, {dist:2.1}); }
  }

  /* ---------- start ---------- */
  rHead.append(h('h2', null, 'Loading…'));
  load('manifest.json').then(m => {
    if (dead) return; st.m = m; st.scen = m.scenario || scens()[0] || null;
    applyPreset(m.presets[0]); drawTargets(); drawPresets(); drawSliders(); setView('mars'); rescore();
    load(m.files.mars).catch(() => {});                       /* warm up, so the first click on Mars answers at once */
    if (m.files.hires) load(m.files.hires).then(d => { st.hires = d; if (st.sel) drawRight(); }).catch(() => {});
  }).catch(e => { console.error(e); TT.clear(rHead); rHead.append(h('h2', null, 'No data')); rBody.append(h('p', {class:'muted small'}, 'The analog data could not be loaded. Run python -m backend.web_export and reload.')); });

  return { destroy(){ dead = true; g3 && g3.dispose(); } };
};
})();
