/* Planalogy — Analog Finder, one screen with two globes.
   Click anywhere on Mars (or Earth): the area around the click (100 km radius) is averaged and every cell of the
   other planet is ranked against it. The other globe flies to the best match, a thin arc links the two places.
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
const cache = {};
/* .json.gz files: unpack in the browser when the server sends them as plain bytes */
async function readJson(r){
  const buf = new Uint8Array(await r.arrayBuffer());
  if (buf[0] === 0x1f && buf[1] === 0x8b){
    const s = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(s).text());
  }
  return JSON.parse(new TextDecoder().decode(buf));
}
const load = f => cache[f] || (cache[f] = fetch(DATA + f).then(r => { if (!r.ok) throw new Error(f + ': ' + r.status); return readJson(r); }));
const pct = x => x == null ? '–' : Math.round(x * 100);
const region = it => REGION[(Math.floor(it.lat) + .5) + ',' + (Math.floor(it.lon) + .5)];
const sspName = s => String(s).replace(/^ssp(\d)(\d)(\d)$/, 'SSP$1-$2.$3');
const words = s => String(s).replace(/_/g, ' ');

/* score -> colour (stretched over the current ranking) */
const STOPS = [[0, [40, 70, 150, .08]], [.4, [64, 128, 220, .3]], [.65, [96, 190, 240, .48]], [.82, [250, 210, 110, .62]], [1, [255, 110, 60, .74]]];
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

const SHORT = {'Rover navigation and mobility':'Rover driving', 'Sample science and geology':'Sample science', 'Thermal environment testing':'Thermal testing', 'Ground-ice prospecting (ISRU)':'Ice prospecting'};
const SLIDE = {
  mars: {kicker:'Mars', title:'Pick a target', lede:'Choose a landing site, or click anywhere on the globe. These measured values are what Earth is compared with.'},
  moon: {kicker:'Moon', title:'Lunar base sites', lede:'Planned and proposed sites. The same search works for the Moon once its data grid is added, so they are shown without scores for now.'},
  earth:{kicker:'Earth', title:'Analogs', lede:''}
};

const AREA_KM = 100;                 /* radius of the area you pick, the same on every planet */
const R_KM = {earth: 6371, mars: 3389.5, moon: 1737.4};
const PXD = 8;                       /* overlay pixels per degree (2880 x 1440 texture) */
const NAME = {earth:'Earth', mars:'Mars', moon:'Moon'};
const START = {mars: {lat:-4.6, lon:137.4, label:'Gale crater'}, earth: {lat:29.6, lon:35.4, label:'Wadi Rum, Jordan'}};
const toRad = d => d * Math.PI / 180;
function distKm(body, la1, lo1, la2, lo2){
  const p1 = toRad(la1), p2 = toRad(la2), dp = p2 - p1, dl = toRad(lo2 - lo1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R_KM[body] * Math.asin(Math.min(1, Math.sqrt(a)));
}

TT.pages.finder = function(root){
  const st = {m:null, preset:null, cw:{}, on:{}, fw:Object.assign({}, DEFAULT_FW), req:[], reqF:[], dry:true,
              year:'now', scen:null, pair:'mars', area:null, res:null, sims:null, sel:null, moonSel:null,
              fresh:new Set(), lost:[], nowScore:null, nowRank:null, climate:null, show:'change', busy:false};
  let dead = false, gL = null, gE = null, ui = {};

  /* ---------- skeleton ---------- */
  const scroll = h('div', {class:'fp-scroll'});
  const orbs = h('div', {class:'orbs', role:'radiogroup', 'aria-label':'Planets'});
  const panel = h('aside', {class:'fpanel', 'aria-label':'Controls'}, scroll, orbs);
  const status = h('div', {class:'s-status', role:'status', 'aria-live':'polite'});
  const legend = h('div', {class:'s-legend'});
  const band = h('div', {class:'s-band'});
  const cvL = h('canvas', {class:'view', role:'application', 'aria-label':'Mars globe. Click to pick an area, drag to turn.'});
  const cvE = h('canvas', {class:'view', role:'application', 'aria-label':'Earth globe. Click to pick an area, drag to turn.'});
  const tagL = h('div', {class:'g-tag'}), tagE = h('div', {class:'g-tag'});
  const wrapL = h('div', {class:'g-wrap'}, cvL, tagL), wrapE = h('div', {class:'g-wrap'}, cvE, tagE);
  const link = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); link.setAttribute('class', 'g-link'); link.setAttribute('aria-hidden', 'true');
  const globes = h('div', {class:'s-globes'}, wrapL, wrapE, link);
  const stage = h('div', {class:'stage'}, h('div', {class:'s-info'}, status, legend), globes, band);
  root.appendChild(h('div', {class:'finder'}, panel, stage));

  if (TT.webgl){
    gL = TT.createGlobe(cvL, {body:'mars', markerPx:20, dist:3.35, onPin: (la, lo) => pickArea(st.pair, la, lo), onPick: it => it.body !== 'earth' && pickResult(it)});
    gE = TT.createGlobe(cvE, {body:'earth', markerPx:20, dist:3.35, onPin: (la, lo) => pickArea('earth', la, lo), onPick: it => it.body === 'earth' && pickResult(it)});
    gL.setPinMode(true); gE.setPinMode(true);
  } else stage.appendChild(h('p', {class:'no-gl'}, 'The globes need WebGL, which this browser has switched off.'));

  /* ---------- weights, presets ---------- */
  const cats = () => st.m.categories;
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

  /* ---------- data ---------- */
  const scens = () => st.m.scenarios ? st.m.scenarios.map(x => x.id) : Object.keys(st.m.files.earth_by_scenario || {});
  const scenInfo = id => (st.m.scenarios || []).find(x => x.id === id) || null;
  const yearFile = year => { const si = scenInfo(st.scen), by = st.m.files.earth_by_scenario;
    return (si && si.files && si.files[year]) || (by && by[st.scen] && by[st.scen][year]) || st.m.files.earth[year]; };
  async function earthTable(year){
    const base = await load(st.m.files.earth.now);
    if (year === 'now') return base;
    const file = yearFile(year), key = 'earth@' + file;
    if (!cache[key]) cache[key] = load(file).then(yt => PS.earthForYear(base, yt));
    return cache[key];
  }
  /* Mars rows carry no id; give each one, so Mars cells can be ranked too */
  let marsP = null;
  const marsTable = () => marsP || (marsP = load(st.m.files.mars).then(t => {
    if (t.columns.includes('id')) return t;
    const ia = t.columns.indexOf('lat'), io = t.columns.indexOf('lon');
    return {columns: ['id'].concat(t.columns), rows: t.rows.map(r => ['M' + r[ia] + '_' + r[io]].concat(r))};
  }));
  const target = () => st.area ? (st.area.body === 'earth' ? 'mars' : 'earth') : 'earth';   // planet whose cells are ranked

  /* values of an area: mean of numbers, majority of yes/no, most frequent class or set */
  function areaValues(table, body, lat, lon){
    const ix = {}; table.columns.forEach((c, i) => { ix[c] = i; });
    const rows = [], dLat = AREA_KM / R_KM[body] * 180 / Math.PI;
    for (const r of table.rows){
      const la = r[ix.lat]; if (Math.abs(la - lat) > dLat) continue;
      if (distKm(body, lat, lon, la, r[ix.lon]) <= AREA_KM) rows.push(r);
    }
    if (!rows.length) return null;
    const values = {};
    st.m.features.forEach(f => {
      const vs = rows.map(r => r[ix[f.id]]).filter(v => v !== null && v !== undefined && !(Array.isArray(v) && !v.length && f.kind !== 'set'));
      if (!vs.length){ values[f.id] = null; return; }
      if (f.kind === 'scalar') values[f.id] = vs.reduce((a, b) => a + b, 0) / vs.length;
      else if (f.kind === 'boolean') values[f.id] = vs.filter(Boolean).length * 2 >= vs.length;
      else { const n = new Map(); vs.forEach(v => { const k = JSON.stringify(v); n.set(k, (n.get(k) || 0) + 1); });
        values[f.id] = JSON.parse([...n.entries()].sort((a, b) => b[1] - a[1])[0][0]); }
    });
    return {values, n: rows.length};
  }

  /* ---------- scoring ---------- */
  async function rescore(){
    if (dead || !st.m || !st.area || st.pair === 'moon') return;
    const a = st.area, y = st.year, sc = st.scen, tgt = target();
    try {
      const nowE = await earthTable('now'), yearE = await earthTable(y), mars = await marsTable();
      if (dead || a !== st.area || y !== st.year || sc !== st.scen) return;
      const values = tbl => a.body === 'earth' ? areaValues(tbl, 'earth', a.lat, a.lon) : a.marsValues;
      const cand = tgt === 'earth' ? yearE : mars;
      const tv = values(yearE);
      if (!tv){ TT.toast('No land data in that area. Pick an area on land.', true); return; }
      a.values = tv.values; a.n = tv.n;
      st.sims = PS.similarities(st.m, cand, a.values);
      const opt = {categoryWeights: effectiveCW(), featureWeights: effectiveFW(), requirements: st.req,
                   requiredFeatures: st.reqF.filter(f => !st.sims.targetMissing.includes(f)), onlyDryBare: tgt === 'earth' && st.dry};
      st.res = PS.scoreCells(st.m, cand, st.sims, opt);
      st.fresh = new Set(); st.lost = []; st.nowScore = null; st.nowRank = null; st.climate = null;
      if (y !== 'now'){
        const tvNow = values(nowE);
        const simsNow = PS.similarities(st.m, tgt === 'earth' ? nowE : mars, tvNow.values);
        const now = PS.scoreCells(st.m, tgt === 'earth' ? nowE : mars, simsNow, opt);
        const A = new Set(now.ranked.map(x => x.id)), B = new Set(st.res.ranked.map(x => x.id));
        B.forEach(id => { if (!A.has(id)) st.fresh.add(id); }); now.ranked.forEach(x => { if (!B.has(x.id)) st.lost.push(x); });
        st.nowScore = new Map(now.ranked.map(x => [x.id, x.score])); st.nowRank = new Map(now.ranked.map(x => [x.id, x.position]));
        st.climate = climateOf(nowE, yearE, y, sc);
      }
      if (st.sel && !st.res.ranked.some(x => x.id === st.sel)) st.sel = null;
      paintAll(); pushMarkers(); drawArea(); drawResults(); drawSliders(); drawStatus();
      if (!st.sel) flyToBest();
    } catch(e){
      console.error(e); st.res = null; st.lost = []; st.fresh = new Set(); paintAll();
      status.textContent = /positive weight/.test(e.message) ? 'Switch on at least one parameter.' : 'Could not compute scores.';
      if (ui.results){ TT.clear(ui.results); ui.results.append(h('p', {class:'note'}, status.textContent)); }
    }
  }
  const rescoreSoon = TT.debounce(rescore, 80);

  const climateCache = new Map();
  function climateOf(today, year, y, sc){
    const key = y + '@' + sc; if (climateCache.has(key)) return climateCache.get(key);
    const ix = {}; today.columns.forEach((c, i) => ix[c] = i);
    const byId = new Map(year.rows.map(r => [r[ix.id], r]));
    let thaw = 0, wet = 0, dry = 0, dT = 0, nT = 0;
    today.rows.forEach(a => { const b = byId.get(a[ix.id]); if (!b) return;
      if (a[ix.ground_ice_flag] === true && b[ix.ground_ice_flag] === false) thaw++;
      if (a[ix.dry_bare] && !b[ix.dry_bare]) wet++; if (!a[ix.dry_bare] && b[ix.dry_bare]) dry++;
      const t0 = a[ix.surface_temp_min_K], t1 = b[ix.surface_temp_min_K]; if (typeof t0 === 'number' && typeof t1 === 'number'){ dT += t1 - t0; nT++; } });
    const out = {thaw, wet, dry, warm: nT ? dT / nT : 0}; climateCache.set(key, out); return out;
  }

  /* ---------- painting: heat map on the ranked planet, area rings on both ---------- */
  const ovL = document.createElement('canvas'), ovE = document.createElement('canvas');
  [ovL, ovE].forEach(c => { c.width = 360 * PXD; c.height = 180 * PXD; });
  const LOST = 'rgba(255,75,75,.85)', FRESH = 'rgba(92,240,160,.85)';
  function cellPainter(x, body){
    const g = PS.gridOf(st.m, body), sx = g.lon_step * PXD, sy = g.lat_step * PXD;
    return (it, inset) => { const i = inset || 0; x.fillRect((it.lon - g.lon_step / 2 + 180) * PXD + i, (90 - it.lat - g.lat_step / 2) * PXD + i, sx - 2 * i, sy - 2 * i); };
  }
  function diverge(d, span){
    const t = Math.max(-1, Math.min(1, d / span)), k = Math.abs(t), end = t >= 0 ? [70, 150, 255] : [255, 150, 40], grey = [150, 150, 160];
    const c = grey.map((g, i) => g + (end[i] - g) * k | 0);
    return `rgba(${c[0]},${c[1]},${c[2]},${(.22 + .5 * k).toFixed(2)})`;
  }
  function ring(x, body, lat, lon, km, stroke, fill){
    const d = km / R_KM[body], p1 = toRad(lat), l1 = toRad(lon), pts = [];
    for (let b = 0; b <= 360; b += 4){
      const br = toRad(b), p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(br));
      const l2 = l1 + Math.atan2(Math.sin(br) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2));
      pts.push([((l2 * 180 / Math.PI + 540) % 360) * PXD, (90 - p2 * 180 / Math.PI) * PXD]);
    }
    const draw = shift => { x.beginPath(); pts.forEach(([px, py], i) => { const X = px + shift; if (!i) x.moveTo(X, py); else x.lineTo(X, py); }); x.closePath(); };
    const wraps = pts.some(p => p[0] < 360 * PXD * .25) && pts.some(p => p[0] > 360 * PXD * .75);
    const fix = wraps ? pts.map(p => [p[0] < 180 * PXD ? p[0] + 360 * PXD : p[0], p[1]]) : pts;
    pts.splice(0, pts.length, ...fix);
    [0, -360 * PXD].forEach(sh => { draw(sh); if (fill){ x.fillStyle = fill; x.fill(); } x.lineWidth = 3; x.strokeStyle = stroke; x.stroke(); });
  }
  function paintAll(){
    const xL = ovL.getContext('2d'), xE = ovE.getContext('2d');
    xL.clearRect(0, 0, ovL.width, ovL.height); xE.clearRect(0, 0, ovE.width, ovE.height);
    const tgt = target(), xT = tgt === 'earth' ? xE : xL;
    let lo = null, hi = null, dmax = null;
    if (st.res && st.pair !== 'moon'){
      /* Mars has no dry-land filter, so only its closest 15 % are painted; the rest of the planet stays clean */
      const r = tgt === 'mars' ? st.res.ranked.slice(0, Math.ceil(st.res.ranked.length * .15)) : st.res.ranked, cell = cellPainter(xT, tgt), fut = st.year !== 'now' && st.nowScore, change = fut && st.show === 'change';
      if (r.length){
        hi = r[0].score; lo = r[r.length - 1].score; const span = (hi - lo) || 1;
        if (change){ const ds = r.filter(it => st.nowScore.has(it.id)).map(it => Math.abs(it.score - st.nowScore.get(it.id))).sort((a, b) => a - b); dmax = ds.length ? Math.max(.01, ds[Math.floor(ds.length * .95)]) : .01; }
        for (let i = r.length - 1; i >= 0; i--){
          const it = r[i];
          if (change){ if (st.fresh.has(it.id)) continue; xT.fillStyle = diverge(it.score - st.nowScore.get(it.id), dmax); }
          else xT.fillStyle = rgba(ramp((it.score - lo) / span));
          cell(it);
        }
        if (fut){ xT.fillStyle = LOST; st.lost.forEach(it => cell(it)); xT.fillStyle = FRESH; r.forEach(it => { if (st.fresh.has(it.id)) cell(it); }); }
        const best = st.sel ? r.find(x => x.id === st.sel) : r[0];
        if (best) ring(xT, tgt, best.lat, best.lon, AREA_KM, 'rgba(255,255,255,.95)', null);
      }
    }
    if (st.area){
      const xs = st.area.body === 'earth' ? xE : xL;
      ring(xs, st.area.body, st.area.lat, st.area.lon, AREA_KM, 'rgba(255,190,120,.95)', 'rgba(255,170,90,.18)');
    }
    if (gL) gL.setOverlay(st.pair, ovL); if (gE) gE.setOverlay('earth', ovE);
    drawLegend(lo, hi, dmax);
  }
  function drawLegend(lo, hi, dmax){
    TT.clear(legend);
    if (lo == null) return;
    const fut = st.year !== 'now' && st.nowScore;
    if (fut){
      const seg = h('div', {class:'seg s-mode', role:'radiogroup', 'aria-label':'Map shows'});
      [['change', 'Change since today'], ['score', 'Similarity']].forEach(([id, label]) => seg.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': st.show === id,
        onclick: () => { st.show = id; paintAll(); }}, label)));
      legend.appendChild(seg);
    }
    if (dmax != null){
      const bar = h('span', {class:'f-ramp', style:{background:`linear-gradient(90deg,${diverge(-dmax, dmax)},rgba(150,150,160,.4),${diverge(dmax, dmax)})`}});
      legend.append(h('span', null, 'less similar'), bar, h('span', null, 'more similar'));
    } else {
      const bar = h('span', {class:'f-ramp', style:{background:`linear-gradient(90deg,${[0, .4, .65, .82, 1].map(t => rgba(ramp(t)).replace(/,[\d.]+\)$/, ',1)')).join(',')})`}});
      legend.append(h('span', null, 'Similarity'), h('span', null, Math.round(lo * 100)), bar, h('span', null, Math.round(hi * 100)));
    }
    if (fut) legend.append(h('span', {class:'lg-key lost'}, st.lost.length + ' drop out'), h('span', {class:'lg-key fresh'}, st.fresh.size + ' new'));
  }

  /* ---------- markers ---------- */
  function pushMarkers(){
    if (!gL || !st.m) return;
    const tgt = target(), top = st.res ? st.res.ranked.slice(0, TOP).map(it => ({id: it.id, lat: it.lat, lon: it.lon, body: tgt, kind:'analog'})) : [];
    if (st.pair === 'moon'){
      gL.setMarkers(MOON_SITES.map(s => ({id: s.id, lat: s.lat, lon: s.lon, body:'moon', kind: s.kind}))); gL.setSelection(st.moonSel, []);
      gE.setMarkers([]); return;
    }
    gL.setMarkers(tgt === 'mars' ? top : []); gE.setMarkers(tgt === 'earth' ? top : []);
    const sel = st.sel || (top[0] && top[0].id) || null;
    (tgt === 'earth' ? gE : gL).setSelection(sel, []);
    (tgt === 'earth' ? gL : gE).setSelection(null, []);
  }

  /* ---------- the link between the two globes ---------- */
  let linkT0 = 0, linkRaf = 0;
  const NS = 'http://www.w3.org/2000/svg';
  const pathEl = document.createElementNS(NS, 'path'), dotA = document.createElementNS(NS, 'circle'), dotB = document.createElementNS(NS, 'circle'), spark = document.createElementNS(NS, 'circle');
  pathEl.setAttribute('class', 'lk-path'); [dotA, dotB].forEach(d => { d.setAttribute('r', '4'); d.setAttribute('class', 'lk-dot'); }); spark.setAttribute('r', '3.5'); spark.setAttribute('class', 'lk-spark');
  link.append(pathEl, dotA, dotB, spark);
  function linkPoints(){
    if (!st.area || !st.res || !st.res.ranked.length || !gL) return null;
    const best = (st.sel && st.res.ranked.find(x => x.id === st.sel)) || st.res.ranked[0];
    const src = st.area.body === 'earth' ? [gE, cvE] : [gL, cvL], dst = target() === 'earth' ? [gE, cvE] : [gL, cvL];
    const box = globes.getBoundingClientRect();
    const at = ([g, cv], la, lo) => { const s = g.screenOf(la, lo), r = cv.getBoundingClientRect(); return {x: r.left - box.left + s.x, y: r.top - box.top + s.y, v: s.visible}; };
    return [at(src, st.area.lat, st.area.lon), at(dst, best.lat, best.lon)];
  }
  function linkFrame(){
    linkRaf = 0; if (dead) return;
    const p = linkPoints(), t = (performance.now() - linkT0) / 1000;
    if (!p || !p[0].v || !p[1].v){ link.style.opacity = '0'; } else {
      link.style.opacity = '1';
      const [a, b] = p, mx = (a.x + b.x) / 2, my = Math.min(a.y, b.y) - 90 - Math.abs(b.x - a.x) * .08;
      const d = `M${a.x.toFixed(1)} ${a.y.toFixed(1)} Q${mx.toFixed(1)} ${my.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`;
      pathEl.setAttribute('d', d);
      const len = pathEl.getTotalLength(), k = Math.min(1, t / 1.1), e = 1 - Math.pow(1 - k, 3);
      pathEl.style.strokeDasharray = len; pathEl.style.strokeDashoffset = String(len * (1 - e));
      dotA.setAttribute('cx', a.x); dotA.setAttribute('cy', a.y); dotB.setAttribute('cx', b.x); dotB.setAttribute('cy', b.y);
      dotB.style.opacity = String(Math.max(0, (k - .85) / .15));
      const sp = pathEl.getPointAtLength(len * ((t * .45) % 1)); spark.setAttribute('cx', sp.x); spark.setAttribute('cy', sp.y);
      spark.style.opacity = k < 1 ? '0' : '.9';
    }
    linkRaf = requestAnimationFrame(linkFrame);
  }
  function restartLink(){ linkT0 = performance.now(); if (!linkRaf) linkRaf = requestAnimationFrame(linkFrame); }

  /* ---------- picking ---------- */
  async function pickArea(body, lat, lon, quiet){
    if (body === 'moon'){ TT.toast('The Moon has no data grid yet, so its areas cannot be compared.'); return; }
    st.sel = null;
    if (body === 'mars'){
      const mars = await marsTable();
      const v = areaValues(mars, 'mars', lat, lon);
      if (!v){ TT.toast('No Mars data there.', true); return; }
      st.area = {body:'mars', lat, lon, marsValues: v, values: v.values, n: v.n, label: quiet || null};
    } else {
      const e = await earthTable(st.year);
      const v = areaValues(e, 'earth', lat, lon);
      if (!v){ TT.toast('That is open water. Pick an area on land.', true); return; }
      st.area = {body:'earth', lat, lon, values: v.values, n: v.n, label: quiet || null};
    }
    (body === 'earth' ? gE : gL).focus(lat, lon, {dist:3.35});
    drawOrbs(); drawArea(); paintAll(); await rescore(); restartLink();
  }
  function flyToBest(){
    const it = st.res && st.res.ranked[0]; if (!it) return;
    (target() === 'earth' ? gE : gL).focus(it.lat, it.lon, {dist:3.35});
    restartLink();
  }
  function pickResult(it){ select(it.id, true); }
  function select(id, fly){
    st.sel = id; const it = st.res && st.res.ranked.find(x => x.id === id);
    pushMarkers(); paintAll(); drawResults();
    if (fly && it) (target() === 'earth' ? gE : gL).focus(it.lat, it.lon, {dist:2.3});
    const sec = TT.$('#f-results'); if (sec) sec.scrollIntoView({behavior: TT.reduced() ? 'auto' : 'smooth', block:'start'});
    restartLink();
  }

  /* ---------- panel ---------- */
  function sec(title, note, ...kids){ return h('section', {class:'fsec'}, h('h3', null, title, note ? h('span', {class:'h-note'}, note) : null), ...kids); }
  function build(){
    ui = {};
    ui.areaBox = h('div', {class:'area'});
    ui.presetBox = h('div', {class:'f-presets'}); ui.verdict = h('p', {class:'note one'});
    ui.sliders = h('div', {class:'prs'});
    const dryInp = h('input', {type:'checkbox', class:'ck', id:'f-dry', checked: st.dry, onchange: e => { st.dry = e.target.checked; rescore(); }});
    ui.resHead = h('h3', null, 'Best matches'); ui.results = h('div', {class:'list'});
    TT.clear(scroll);
    scroll.append(
      ui.areaBox,
      sec('Mission', null, ui.presetBox, ui.verdict),
      sec('Parameters', 'on or off, weight 0 to 5', ui.sliders, h('label', {class:'f-switch', for:'f-dry'}, dryInp, h('span', null, 'Earth: dry, bare land only'))),
      h('section', {class:'fsec', id:'f-results'}, ui.resHead, ui.results));
  }
  function fmtArea(a){ return TT.fmtCoord(a.lat, a.lon, 1); }
  function drawArea(){
    if (!ui.areaBox) return; TT.clear(ui.areaBox);
    if (st.pair === 'moon'){
      ui.areaBox.append(h('div', {class:'kicker k-moon'}, 'Moon preview'), h('h1', null, 'Lunar base sites'),
        h('p', {class:'lede'}, 'The Moon has no data grid yet, so it cannot be compared. Planned and proposed sites:'));
      const list = h('div', {class:'list'});
      MOON_SITES.forEach(s => list.appendChild(h('button', {class:'f-site moon', type:'button', 'aria-current': st.moonSel === s.id ? 'true' : null,
        onclick: () => { st.moonSel = s.id; gL.focus(s.lat, s.lon, {dist:2.2}); pushMarkers(); drawArea(); }},
        h('span', {class:'f-name'}, h('span', {class:'f-nm'}, s.name), h('span', {class:'f-why'}, s.note + ', ' + TT.fmtCoord(s.lat, s.lon, 1))))));
      ui.areaBox.append(list); return;
    }
    const a = st.area;
    if (!a){ ui.areaBox.append(h('h1', null, 'Pick an area'), h('p', {class:'lede'}, 'Click anywhere on Mars or on Earth. The other planet shows where it is most alike.')); return; }
    const other = NAME[target()];
    ui.areaBox.append(
      h('div', {class:'kicker k-' + a.body}, 'Your area on ' + NAME[a.body]),
      h('h1', null, a.label || fmtArea(a)),
      h('p', {class:'lede'}, (a.label ? fmtArea(a) + '. ' : '') + AREA_KM + ' km around the point, ' + a.n + ' cells averaged. ' + other + ' shows where it is most alike. Click anywhere on either globe to pick a new area.'));
  }
  function drawPresets(){
    if (!ui.presetBox) return;
    TT.clear(ui.presetBox);
    st.m.presets.forEach(p => ui.presetBox.appendChild(h('button', {class:'chip', type:'button', 'aria-pressed': st.preset === p.id, title: p.name + '. ' + p.mission,
      onclick: () => { applyPreset(p); st.sel = null; drawPresets(); drawSliders(); rescore(); }}, SHORT[p.name] || p.name)));
    const p = st.m.presets.find(x => x.id === st.preset);
    ui.verdict.textContent = !p ? 'Your own weights.' : p.name + (p.weights_used === 'calibrated' ? ', tuned on known analogs.' : ', science team weights.');
  }
  function drawSliders(){
    if (!ui.sliders) return;
    TT.clear(ui.sliders);
    cats().forEach(c => {
      const id = 'w-' + c.id, na = !!st.sims && noData(c), on = st.on[c.id] && !na;
      const val = h('output', {for:id}, na ? 'n/a' : on ? (st.cw[c.id] || 0).toFixed(1) : 'off');
      const box = h('input', {type:'checkbox', class:'ck', id:'on-' + c.id, checked: on, disabled: na, 'aria-label':'Use ' + c.label,
        onchange: e => { st.on[c.id] = e.target.checked; if (e.target.checked && !(st.cw[c.id] > 0)) st.cw[c.id] = 2.5; st.preset = null; drawPresets(); drawSliders(); rescore(); }});
      const inp = h('input', {id, type:'range', min:'0', max:'5', step:'0.5', value:String(on ? st.cw[c.id] || 0 : 0), class:'f-range', disabled: na, 'aria-label': c.label + ' weight',
        oninput: e => { const v = +e.target.value; st.cw[c.id] = v; st.on[c.id] = v > 0; box.checked = v > 0; val.textContent = v > 0 ? v.toFixed(1) : 'off'; row.classList.toggle('off', !(v > 0));
          if (st.preset){ st.preset = null; drawPresets(); } rescoreSoon(); }});
      const row = h('div', {class:'pr' + (on ? '' : ' off'), title: na ? 'No data in this area' : null}, box, h('label', {for:'on-' + c.id}, c.label), inp, val);
      ui.sliders.appendChild(row);
    });
  }
  function knownName(id){ const k = st.m.presets.flatMap(p => p.known_analogs).find(a => a.id === id); return k ? k.name : null; }
  function placeName(it){
    if (target() === 'earth') return region(it) || TT.fmtCoord(it.lat, it.lon, 1);
    const near = st.m.targets.map(t => [t, distKm('mars', it.lat, it.lon, t.lat, t.lon)]).sort((a, b) => a[1] - b[1])[0];
    return near && near[1] < 400 ? 'Near ' + near[0].name.split(' (')[0] : TT.fmtCoord(it.lat, it.lon, 1);
  }
  function rankMove(it){
    if (st.year === 'now' || !st.nowRank) return null;
    const was = st.nowRank.get(it.id);
    if (was == null) return h('span', {class:'mv up'}, 'new');
    const d = was - it.position; if (!d) return h('span', {class:'mv'}, '=');
    return h('span', {class:'mv ' + (d > 0 ? 'up' : 'down'), title:'Rank ' + was + ' today'}, (d > 0 ? '▲' : '▼') + Math.abs(d));
  }
  function siteRow(it){
    const known = target() === 'earth' ? knownName(it.id) : null;
    return h('button', {class:'f-site', type:'button', 'aria-current': st.sel === it.id ? 'true' : null, onclick: () => select(it.id, true)},
      h('span', {class:'f-pos'}, it.position),
      h('span', {class:'f-name'}, h('span', {class:'f-nm'}, placeName(it), known ? h('span', {class:'badge measured'}, 'known') : null,
          st.fresh.has(it.id) ? h('span', {class:'badge derived'}, 'new') : null),
        h('span', {class:'f-bar'}, h('i', {style:{width: pct(it.score) + '%'}}))),
      h('span', {class:'f-score'}, pct(it.score), rankMove(it)));
  }
  function drawResults(){
    if (!ui.results || !st.m) return;
    TT.clear(ui.results);
    if (st.pair === 'moon'){ ui.resHead.textContent = ''; return; }
    const other = NAME[target()];
    if (!st.res){ ui.resHead.textContent = 'Best matches'; ui.results.append(h('p', {class:'note'}, st.area ? 'Ranking…' : 'Pick an area first.')); return; }
    const it = st.sel && st.res.ranked.find(x => x.id === st.sel);
    if (it){ ui.resHead.textContent = 'Selected place on ' + other; drawCard(it); return; }
    ui.resHead.textContent = 'Best matches on ' + other;
    const r = st.res;
    if (!r.ranked.length){ ui.results.append(h('p', {class:'note'}, 'No cell passes. Switch a parameter back on or turn off the dry-land filter.')); return; }
    r.ranked.slice(0, 5).forEach(x => ui.results.appendChild(siteRow(x)));
    if (target() !== 'earth') return;
    const ks = (st.m.presets.find(p => p.id === st.preset) || st.m.presets[0]).known_analogs;
    ui.results.appendChild(h('h4', {class:'f-sub'}, 'Known test sites'));
    ks.forEach(k => { const x = r.ranked.find(y => y.id === k.id);
      ui.results.appendChild(x ? siteRow(x) : h('div', {class:'f-site off'}, h('span', {class:'f-pos'}, '–'), h('span', {class:'f-name'}, h('span', {class:'f-nm'}, k.name),
        h('span', {class:'f-why'}, r.partial.some(y => y.id === k.id) ? 'incomplete data' : r.excluded.some(y => y.id === k.id) ? 'no ground ice' + (st.year === 'now' ? '' : ' in ' + st.year) : 'not dry, bare land' + (st.year === 'now' ? '' : ' in ' + st.year))),
        h('span', {class:'f-score'}, st.nowRank && st.nowRank.has(k.id) ? h('span', {class:'mv down'}, 'lost') : null))); });
  }
  function drawCard(it){
    const cw = effectiveCW(), card = PS.card(st.m, it, {categoryWeights: cw, featureWeights: effectiveFW()});
    const known = target() === 'earth' ? knownName(it.id) : null, th = st.m.thresholds || {strong_at_least:75, weak_at_most:40};
    const bars = cats().filter(c => cw[c.id] > 0 && card.categories[c.id] != null).map(c => { const s = card.categories[c.id] * 100;
      return h('div', {class:'f-cat'}, h('span', null, c.label), h('span', {class:'f-bar ' + (s >= th.strong_at_least ? 'good' : s > th.weak_at_most ? 'mid' : 'low')}, h('i', {style:{width: Math.max(2, s) + '%'}})), h('span', null, Math.round(s))); });
    /* your area next to this place, parameter by parameter */
    const rowsCmp = st.m.features.map(f => { const a = show(f, st.area.values[f.id]), b = show(f, it.row ? valueOf(it, f.id) : null);
      return (a == null && b == null) ? null : h('tr', null, h('td', null, f.label.replace(' (proxy)', '').replace(' (rank within planet)', '')), h('td', null, a == null ? '–' : a), h('td', null, b == null ? '–' : b)); }).filter(Boolean);
    TT.append(ui.results, [
      h('button', {class:'btn ghost sm back', type:'button', onclick: () => { st.sel = null; pushMarkers(); paintAll(); drawResults(); restartLink(); }}, 'All matches'),
      h('div', {class:'f-card-head'},
        h('div', null, h('h4', null, placeName(it)),
          h('div', {class:'meta'}, 'Rank ' + it.position + ' of ' + st.res.ranked.length.toLocaleString() + ', ' + TT.fmtCoord(it.lat, it.lon, 2))),
        h('div', {class:'f-big'}, h('b', null, pct(it.score)), h('span', null, '/100'))),
      known ? h('span', {class:'badge measured'}, 'Known analog: ' + known) : null,
      st.fresh.has(it.id) ? h('span', {class:'badge derived'}, 'Becomes a candidate by ' + st.year) : null,
      h('div', {class:'f-group'}, h('div', {class:'meta'}, 'Match by parameter'), bars),
      rowsCmp.length ? h('table', {class:'cmp'}, h('thead', null, h('tr', null, h('th', null, ''), h('th', null, 'Your area'), h('th', null, 'This place'))), h('tbody', null, rowsCmp)) : null,
      target() === 'earth' ? hiresBlock(it) : null]);
  }
  function valueOf(it, fid){ const cols = it.cols || (st.lastCols && st.lastCols[target()]); return cols && cols[fid] !== undefined ? it.row[cols[fid]] : null; }
  function hiresBlock(it){
    const site = st.hires && st.hires.sites.find(s => Math.abs(s.lat - it.lat) <= .5 && Math.abs(s.lon - it.lon) <= .5);
    if (!site || !site.today) return null;
    const ss = Object.keys(site.scenarios || {}); if (!ss.length) return null;
    const sc = ss.includes(st.scen) ? st.scen : ss[0], yrs = Object.keys(site.scenarios[sc]).sort();
    const cols = [['Today', site.today]].concat(yrs.map(y => [y, site.scenarios[sc][y]]));
    const f = (v, d) => v == null ? '–' : (+v).toFixed(d);
    const row = (label, key, d, unit) => h('tr', null, h('td', null, label), cols.map(([, v], i) => h('td', {class: i && v[key] != null && cols[0][1][key] != null ? (v[key] > cols[0][1][key] ? 'up' : v[key] < cols[0][1][key] ? 'down' : '') : ''}, f(v[key], d) + (unit || ''))));
    const map = site.maps && site.maps[sc], nm = cols[cols.length - 1][1].n_models;
    return h('div', {class:'hr'},
      h('h4', null, 'Inside this area', h('span', {class:'km'}, '1 km')),
      h('p', {class:'meta'}, 'Today and projected, ' + sspName(sc) + (nm ? ', mean of ' + nm + ' model' + (nm > 1 ? 's' : '') : '') + '.'),
      h('table', null, h('thead', null, h('tr', null, h('th', null, ''), cols.map(([y]) => h('th', null, y)))),
        h('tbody', null, row('Air temperature', 'tmean_C', 1, ' °C'), row('Day–night swing', 'air_temp_swing_K', 1, ' K'), row('Rain per year', 'precip_mm_yr', 0, ' mm'),
          row('Hyper-arid share', 'share_hyperarid_pct', 0, ' %'), row('Dry enough for Mars', 'share_mars_dry_pct', 0, ' %'))),
      map ? h('a', {href: DATA + 'hires/' + map, target:'_blank', rel:'noopener'}, h('img', {src: DATA + 'hires/' + map, alt:'1-km maps of temperature and aridity, today and projected', loading:'lazy'})) : null);
  }

  /* ---------- planets at the foot of the panel ---------- */
  function drawOrbs(){
    TT.clear(orbs);
    const active = st.pair === 'moon' ? 'moon' : (st.area ? st.area.body : 'mars');
    [['earth', 'Earth'], ['moon', 'Moon'], ['mars', 'Mars']].forEach(([id, name]) => orbs.appendChild(
      h('button', {type:'button', role:'radio', class:'orb-b', 'aria-checked': active === id, title: id === 'earth' ? 'Start from an area on Earth' : id === 'mars' ? 'Start from an area on Mars' : 'Moon preview',
        onclick: () => setPair(id)}, h('i', {class:'orb orb-' + id}), h('span', null, name))));
  }
  function setPair(id){
    if (id === 'moon'){ st.pair = 'moon'; gL.setBody('moon'); gL.focus(-60, 20, {dist:3.35}); }
    else {
      if (st.pair === 'moon'){ st.pair = 'mars'; gL.setBody('mars'); }
      const s = START[id];
      pickArea(id, s.lat, s.lon, s.label);
    }
    tagL.textContent = NAME[st.pair]; drawOrbs(); drawArea(); drawResults(); pushMarkers(); paintAll(); drawBand(); drawStatus();
    link.style.opacity = '0';
  }

  /* ---------- time arc ---------- */
  function drawBand(){
    TT.clear(band);
    const ys = st.m ? st.m.years.map(String) : [];
    if (st.pair === 'moon' || ys.length < 2){ band.append(h('p', {class:'s-hint'}, 'Moon preview: sites only, not scored.')); return; }
    const tl = h('div', {class:'tl', role:'group', 'aria-label':'Year and climate scenario on Earth'}); band.appendChild(tl);
    const W = 1000, Y0 = 52, SAG = 30, n = ys.length, cur = Math.max(0, ys.indexOf(String(st.year)));
    const at = i => { const t = i / (n - 1), x = 60 + t * (W - 120); return [x, Y0 + SAG * 4 * t * (1 - t)]; };
    const path = k => { let d = ''; for (let i = 0; i <= 40; i++){ const t = (i / 40) * k, x = 60 + t * (W - 120), y = Y0 + SAG * 4 * t * (1 - t); d += (i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1); } return d; };
    const fut = st.year !== 'now';
    tl.className = 'tl ' + (fut ? 'future' : 'now');
    tl.insertAdjacentHTML('beforeend', '<svg viewBox="0 0 ' + W + ' 96" preserveAspectRatio="none" aria-hidden="true"><path class="arc" vector-effect="non-scaling-stroke" d="' + path(1) + '"/>' + (cur ? '<path class="arc-done" vector-effect="non-scaling-stroke" d="' + path(cur / (n - 1)) + '"/>' : '') + '</svg>');
    tl.appendChild(h('button', {class:'tl-now', type:'button', title:'Back to today', onclick: () => setYear('now')}, fut ? 'Projected' : 'Today'));
    tl.appendChild(h('div', {class:'tl-what'}, fut ? 'Earth in ' + st.year : 'Earth today'));
    const ss = scens();
    if (ss.length > 1){
      const box = h('div', {class:'tl-scen', role:'radiogroup', 'aria-label':'Climate scenario'});
      ss.forEach(s => box.appendChild(h('button', {type:'button', role:'radio', 'aria-checked': s === st.scen, title: (scenInfo(s) && scenInfo(s).label) || s,
        onclick: () => { st.scen = s; if (st.year === 'now') st.year = ys[Math.min(2, n - 1)]; drawBand(); rescore(); }}, sspName(s))));
      tl.appendChild(box);
    }
    const stops = h('div', {role:'radiogroup', 'aria-label':'Year'});
    ys.forEach((y, i) => { const [x, yy] = at(i);
      stops.appendChild(h('button', {class:'tl-stop', type:'button', role:'radio', 'aria-checked': i === cur, style:{left: (x / W * 100) + '%', top: yy + 'px'},
        onclick: () => setYear(y)}, h('i'), h('span', null, y === 'now' ? 'Today' : y))); });
    tl.appendChild(stops);
  }
  function setYear(y){ if (st.year === 'now' && y !== 'now') st.show = 'change'; st.year = String(y); drawBand(); rescore(); }

  function drawStatus(){
    if (!st.m) return;
    tagL.textContent = NAME[st.pair] + (st.pair === 'moon' ? ' (preview)' : st.area && st.area.body === 'mars' ? ' · your area' : ' · matches');
    tagE.textContent = 'Earth' + (st.area && st.area.body === 'earth' ? ' · your area' : ' · matches') + (st.year === 'now' ? '' : ' · ' + st.year);
    if (st.pair === 'moon'){ status.textContent = 'Moon, ' + MOON_SITES.length + ' candidate base sites'; return; }
    if (!st.res){ status.textContent = ''; return; }
    const tgt = target(), n = st.res.ranked.length.toLocaleString() + (tgt === 'earth' && st.dry ? ' dry, bare' : '') + ' ' + NAME[tgt] + ' cells ranked against your area';
    if (st.year === 'now' || !st.climate){ status.textContent = n + '.'; return; }
    const c = st.climate;
    status.textContent = 'Earth in ' + st.year + ' (' + sspName(st.scen) + '): the coldest ground is ' + c.warm.toFixed(1) + ' K warmer on average, permafrost thaws in ' + c.thaw.toLocaleString()
      + ' cells, ' + c.wet.toLocaleString() + ' become too wet and ' + c.dry.toLocaleString() + ' turn dry. ' + n + '.';
  }

  /* hook for the demo recorder and tests */
  TT.finder = {pickArea, setYear: y => setYear(y), select: id => select(id, true), state: st};

  /* ---------- start ---------- */
  build(); drawOrbs();
  load('manifest.json').then(async m => {
    if (dead) return; st.m = m; st.scen = m.scenario || scens()[0] || null;
    applyPreset(m.presets[0]);
    /* column positions of the ranked tables, for the comparison table in the card */
    const [e0, m0] = await Promise.all([load(m.files.earth.now), marsTable()]);
    const cols = t => { const o = {}; t.columns.forEach((c, i) => o[c] = i); return o; };
    st.lastCols = {earth: cols(e0), mars: cols(m0)};
    drawPresets(); drawSliders(); drawBand();
    await pickArea('mars', START.mars.lat, START.mars.lon, START.mars.label);
    if (m.files.hires) load(m.files.hires).then(d => { st.hires = d; if (st.sel) drawResults(); }).catch(() => {});
  }).catch(e => { console.error(e); TT.clear(scroll); scroll.append(h('h1', null, 'No data'), h('p', {class:'lede'}, 'The analog data could not be loaded. Start the app with the start file.')); });

  return { destroy(){ dead = true; TT.finder = null; if (linkRaf) cancelAnimationFrame(linkRaf); gL && gL.dispose(); gE && gE.dispose(); } };
};
})();
