/* Planalogy — data model, store (seed + shared db overlay + sandbox fallback), comparison logic, search */
(function(){
const TT = window.TT;
const SEED = window.TT_SEED || {bodies:{}, sources:{}, locations:[]};

TT.BODIES = SEED.bodies;
TT.BODY_ORDER = ['earth','moon','mars'];
TT.TERRAINS = ['Impact crater','Massif or plateau','Lava tube or pit','Fretted terrain','Plain','Polar desert','Hyperarid desert','Volcanic field'];

/* parameter catalogue: label, unit, group, and how it takes part in comparisons */
TT.PARAMS = [
  {key:'diameter_km', label:'Diameter', unit:'km', group:'Physical', num:true, scale:'log', rule:'ratio', tol:2},
  {key:'depth_km', label:'Depth', unit:'km', group:'Physical', num:true, scale:'log', rule:'ratio', tol:2},
  {key:'height_km', label:'Height above surroundings', unit:'km', group:'Physical', num:true, scale:'log', rule:'ratio', tol:2},
  {key:'slope_deg', label:'Slope', unit:'°', group:'Terrain', num:true, scale:'lin', note:'Shown, not scored.'},
  {key:'composition', label:'Surface composition', unit:'', group:'Terrain', num:false},
  {key:'elevation_m', label:'Elevation', unit:'m', group:'Physical', num:true, scale:'lin', rule:'diff', tol:500, sameBody:true, note:'Each body uses its own reference level, so elevations are only scored within one body.'},
  {key:'abs_lat', label:'Absolute latitude', unit:'°', group:'Position', num:true, scale:'lin', rule:'diff', tol:10, derived:true, note:'Computed from the stored latitude.'},
  {key:'temp_mean_c', label:'Mean temperature', unit:'°C', group:'Climate', num:true, scale:'lin', rule:'diff', tol:10},
  {key:'precip_mm_yr', label:'Annual precipitation', unit:'mm/yr', group:'Climate', num:true, scale:'lin', note:'Shown, not scored: it has no Moon or Mars counterpart.'},
  {key:'illumination', label:'Illumination', unit:'', group:'Environment', num:false},
  {key:'shadow', label:'Shadow conditions', unit:'', group:'Environment', num:false},
  {key:'volatiles', label:'Water and ice indicators', unit:'', group:'Environment', num:false},
  {key:'access', label:'Accessibility', unit:'', group:'Environment', num:false}
];
TT.PARAM = {}; TT.PARAMS.forEach(p => TT.PARAM[p.key] = p);

/* ---------- validation of untrusted records (shared db content is data, not code) ---------- */
const str = (v, n) => typeof v === 'string' ? v.slice(0, n || 2000) : '';
const numOrNull = v => (typeof v === 'number' && isFinite(v)) ? v : null;
TT.sanitize = function(d){
  if (!d || typeof d !== 'object' || d.tombstone) return null;
  const id = str(d.id, 80);
  if (!/^[a-zA-Z0-9_-]{2,80}$/.test(id)) return null;
  if (!TT.BODIES[d.body]) return null;
  const lat = numOrNull(d.lat), lon = numOrNull(d.lon);
  if (lat == null || lon == null || Math.abs(lat) > 90 || lon < -360 || lon > 360) return null;
  const r = {
    id, name: str(d.name, 140) || id, body: d.body, kind: TT.KINDS[d.kind] && d.kind !== 'user' ? d.kind : 'landing',
    status_label: str(d.status_label, 300), region: str(d.region, 200), terrain: str(d.terrain, 80),
    lat, lon: TT.normLon(lon), summary: str(d.summary, 3000), geology: str(d.geology, 3000), environment: str(d.environment, 3000),
    relevance: str(d.relevance, 3000), rationale: str(d.rationale, 2000), published: d.published !== false,
    updated: str(d.updated, 20), verification: d.verification === 'reviewed' ? 'reviewed' : 'sample',
    tags: Array.isArray(d.tags) ? d.tags.slice(0, 20).map(t => str(t, 40)).filter(Boolean) : [],
    analog_for: Array.isArray(d.analog_for) ? d.analog_for.slice(0, 40).map(t => str(t, 80)).filter(Boolean) : [],
    sources: Array.isArray(d.sources) ? d.sources.slice(0, 40).map(t => str(t, 60)).filter(Boolean) : [],
    srcdefs: {}, params: {}, images: []
  };
  if (d.srcdefs && typeof d.srcdefs === 'object') for (const k of Object.keys(d.srcdefs).slice(0, 40)){
    const s = d.srcdefs[k] || {};
    r.srcdefs[k] = {id:k, title:str(s.title,300), publisher:str(s.publisher,200), url:/^https?:\/\//.test(s.url||'') ? str(s.url,500) : '', year:str(s.year,10), note:str(s.note,500)};
  }
  const P = d.params && typeof d.params === 'object' ? d.params : {};
  for (const k of Object.keys(P).slice(0, 40)){
    const p = P[k] || {};
    const status = ['measured','derived','unavailable'].includes(p.status) ? p.status : 'unavailable';
    const v = typeof p.v === 'number' ? numOrNull(p.v) : (typeof p.v === 'string' ? str(p.v, 300) : null);
    r.params[k] = {label: str(p.label, 80), num: p.num === true || typeof p.v === 'number', v: status === 'unavailable' ? null : v, unit: str(p.unit, 20), status, src: str(p.src, 60), date: str(p.date, 20), unc: str(p.unc, 120), note: str(p.note, 400), q: ['<','>','~'].includes(p.q) ? p.q : '',
      range: Array.isArray(p.range) && p.range.length === 2 && p.range.every(x => typeof x === 'number' && isFinite(x)) ? p.range : null};
  }
  if (Array.isArray(d.images)) r.images = d.images.slice(0, 12).map(im => ({id:str(im.id,80), url:/^(https?:\/\/|\/_blob\/|blob:|data:image\/)/.test(im.url||'') ? str(im.url,2000) : '', caption:str(im.caption,300), credit:str(im.credit,200), license:str(im.license,120)})).filter(im => im.url);
  return r;
};

/* ---------- parameters ---------- */
TT.paramOf = function(rec, key){
  if (key === 'abs_lat') return {v: Math.abs(rec.lat), unit:'°', status:'derived', src:'', date:'', unc:'', note:'Computed from the stored latitude.', q:'', range:null};
  return rec.params && rec.params[key] || {v:null, unit:'', status:'unavailable', src:'', date:'', unc:'', note:'No value stored for this parameter.', q:'', range:null};
};
/* the standard catalogue plus any custom parameters the given records carry (admins can add new ones without a code change) */
TT.paramList = function(recs){
  const list = TT.PARAMS.slice(), seen = new Set(Object.keys(TT.PARAM));
  recs.forEach(r => Object.keys(r.params || {}).forEach(k => {
    if (seen.has(k)) return; seen.add(k); const p = r.params[k];
    list.push({key:k, label:p.label || k.replace(/_/g, ' '), unit:p.unit || '', group:'Other', num:!!p.num || typeof p.v === 'number', scale:'lin', custom:true});
  }));
  return list;
};
TT.paramText = function(p){
  if (!p || p.status === 'unavailable') return null;
  if (typeof p.v === 'string') return p.v;
  const u = p.unit ? ' ' + p.unit : '';
  if (typeof p.v === 'number') return (p.q ? p.q + ' ' : '') + TT.fmtNum(p.v) + u;
  if (p.range) return TT.fmtNum(p.range[0]) + ' to ' + TT.fmtNum(p.range[1]) + u;
  return null;
};
TT.scorable = function(p){ return p && p.status !== 'unavailable' && typeof p.v === 'number' && !p.q; };

/* ---------- sources ---------- */
TT.source = function(rec, id){ return (rec && rec.srcdefs && rec.srcdefs[id]) || SEED.sources[id] || null; };
TT.recordSources = function(rec){
  const ids = []; const add = i => { if (i && ids.indexOf(i) < 0) ids.push(i); };
  (rec.sources || []).forEach(add);
  Object.keys(rec.params || {}).forEach(k => add(rec.params[k].src));
  return ids.map(i => TT.source(rec, i)).filter(Boolean);
};

/* ---------- store ---------- */
const listeners = new Set();
const S = TT.Store = {
  mode: 'seed',          // seed (read only) | db | sandbox
  seedMap: new Map(),
  pub: new Map(), drafts: new Map(), tomb: new Set(),
  pins: TT.lsGet('tt_pins', []),
  assets: new Map(),     // db metadata for uploaded assets
  dbReady: false, error: '',
  on(fn){ listeners.add(fn); return () => listeners.delete(fn); },
  emit(){ listeners.forEach(f => { try { f(); } catch(e){ console.error(e); } }); },
  pinsSave(){ TT.lsSet('tt_pins', S.pins); }
};
SEED.locations.forEach(l => { const r = TT.sanitize(l); if (r) S.seedMap.set(r.id, r); });

S.all = function(){
  const m = new Map(S.seedMap);
  S.tomb.forEach(id => m.delete(id));
  S.pub.forEach((r, id) => m.set(id, r));
  return Array.from(m.values()).filter(r => r.published !== false);
};
S.get = function(id){ return S.all().find(r => r.id === id) || null; };
S.getAny = function(id){ return S.drafts.get(id) || S.get(id); };
S.byBody = body => S.all().filter(r => r.body === body);
S.isSeed = id => S.seedMap.has(id);
S.adminList = function(){
  const live = new Map(S.all().map(r => [r.id, r]));
  const out = [];
  live.forEach((r, id) => out.push({rec: S.drafts.get(id) || r, live: r, state: S.drafts.has(id) ? 'changes' : 'published'}));
  S.drafts.forEach((r, id) => { if (!live.has(id)) out.push({rec: r, live: null, state: 'draft'}); });
  return out.sort((a, b) => (b.rec.updated || '').localeCompare(a.rec.updated || '') || a.rec.name.localeCompare(b.rec.name));
};
S.uniqueId = function(base){
  let id = TT.slug(base) || 'location', n = 2; const have = new Set([...S.seedMap.keys(), ...S.pub.keys(), ...S.drafts.keys()]);
  const root = id; while (have.has(id)) id = root + '-' + n++;
  return id;
};

/* shared db wiring happens once capabilities are resolved (see caps.js) */
S.attachDb = function(db, canEdit){
  S.db = db; S.mode = 'db'; S.canWrite = canEdit;
  let timer = setTimeout(() => { if (!S.dbReady){ S.error = 'The shared database did not answer yet; showing the built-in sample records.'; S.emit(); } }, 10000);
  db.collection('tt_published').onSnapshot(snap => {
    S.pub = new Map(); S.tomb = new Set();
    snap.docs.forEach(d => { const x = d.data(); if (x && x.tombstone) S.tomb.add(d.id); else { const r = TT.sanitize(x); if (r) S.pub.set(r.id, r); } });
    S.dbReady = true; S.error = ''; clearTimeout(timer); S.emit();
  }, e => { S.error = 'Shared database unavailable (' + (e && e.code || 'error') + '). Showing sample records.'; S.emit(); });
  if (canEdit){
    db.collection('tt_drafts').onSnapshot(snap => {
      S.drafts = new Map();
      snap.docs.forEach(d => { const r = TT.sanitize(Object.assign({}, d.data(), {published: false})); if (r) S.drafts.set(r.id, r); });
      S.emit();
    }, () => {});
    db.collection('tt_assets').onSnapshot(snap => { S.assets = new Map(snap.docs.map(d => [d.id, d.data()])); S.emit(); }, () => {});
  }
};
S.enableSandbox = function(){
  if (S.mode === 'sandbox') return;
  S.mode = 'sandbox'; S.canWrite = true;
  const sb = TT.lsGet('tt_sandbox_v1', {pub:[], drafts:[], tomb:[]});
  sb.pub.forEach(x => { const r = TT.sanitize(x); if (r) S.pub.set(r.id, r); });
  sb.drafts.forEach(x => { const r = TT.sanitize(Object.assign({}, x, {published:false})); if (r) S.drafts.set(r.id, r); });
  (sb.tomb || []).forEach(id => S.tomb.add(id));
  S.emit();
};
S.sbSave = function(){ if (S.mode === 'sandbox') TT.lsSet('tt_sandbox_v1', {pub:[...S.pub.values()], drafts:[...S.drafts.values()], tomb:[...S.tomb]}); };
const clone = o => JSON.parse(JSON.stringify(o));
const guard = () => { if (!S.canWrite) throw new Error('This account cannot write to the shared data.'); };

S.saveDraft = async function(rec){
  guard(); rec = clone(rec); rec.published = false; rec.updated = TT.isoDate();
  if (S.mode === 'db') await S.db.doc('tt_drafts/' + rec.id).set(rec); else S.drafts.set(rec.id, TT.sanitize(rec));
  S.sbSave(); S.emit(); return rec;
};
S.publish = async function(rec){
  guard(); rec = clone(rec); rec.published = true; rec.updated = TT.isoDate();
  if (S.mode === 'db'){ await S.db.doc('tt_published/' + rec.id).set(rec); await S.db.doc('tt_drafts/' + rec.id).delete(); }
  else { S.pub.set(rec.id, TT.sanitize(rec)); S.tomb.delete(rec.id); S.drafts.delete(rec.id); }
  S.sbSave(); S.emit();
};
S.unpublish = async function(id){
  guard(); const live = S.get(id); if (!live) return;
  const keep = clone(S.drafts.get(id) || live); keep.published = false; keep.updated = TT.isoDate();
  if (S.mode === 'db'){
    await S.db.doc('tt_drafts/' + id).set(keep);
    if (S.isSeed(id)) await S.db.doc('tt_published/' + id).set({id, tombstone:true, updated:TT.isoDate()}); else await S.db.doc('tt_published/' + id).delete();
  } else { S.drafts.set(id, TT.sanitize(keep)); S.pub.delete(id); if (S.isSeed(id)) S.tomb.add(id); }
  S.sbSave(); S.emit();
};
S.remove = async function(id){
  guard();
  if (S.mode === 'db'){
    await S.db.doc('tt_drafts/' + id).delete();
    if (S.isSeed(id)) await S.db.doc('tt_published/' + id).set({id, tombstone:true, updated:TT.isoDate()}); else await S.db.doc('tt_published/' + id).delete();
  } else { S.drafts.delete(id); S.pub.delete(id); if (S.isSeed(id)) S.tomb.add(id); }
  S.sbSave(); S.emit();
};
S.discardDraft = async function(id){
  guard(); if (S.mode === 'db') await S.db.doc('tt_drafts/' + id).delete(); else S.drafts.delete(id);
  S.sbSave(); S.emit();
};
S.putAsset = async function(meta){
  guard(); meta = clone(meta);
  if (S.mode === 'db') await S.db.doc('tt_assets/' + meta.id).set(meta); else S.assets.set(meta.id, meta);
  S.emit();
};
S.dropAsset = async function(id){
  guard(); if (S.mode === 'db') await S.db.doc('tt_assets/' + id).delete(); else S.assets.delete(id);
  S.emit();
};

/* user-selected points */
S.addPin = function(body, lat, lon){
  const n = (S.pins.reduce((m, p) => Math.max(m, p.n || 0), 0)) + 1;
  const p = {id:'pin-' + n, n, kind:'user', body, lat: Math.round(lat*1e4)/1e4, lon: Math.round(TT.normLon(lon)*1e4)/1e4, name:'Selected point ' + n};
  S.pins.push(p); S.pinsSave(); S.emit(); return p;
};
S.removePin = function(id){ S.pins = S.pins.filter(p => p.id !== id); S.pinsSave(); S.emit(); };
S.pin = id => S.pins.find(p => p.id === id) || null;

/* ---------- comparison ---------- */
TT.Cmp = {
  rules: TT.PARAMS.filter(p => p.rule),
  weights: Object.assign({}, TT.lsGet('tt_weights', {})),
  weight(key){ const w = this.weights[key]; return typeof w === 'number' ? w : 1; },
  setWeight(key, w){ this.weights[key] = w; TT.lsSet('tt_weights', this.weights); },
  /* returns per-parameter rows and a count: how many scored parameters agree, with weights */
  pair(a, b){
    const rows = []; let tot = 0, ag = 0, n = 0, na = 0;
    for (const r of this.rules){
      const pa = TT.paramOf(a, r.key), pb = TT.paramOf(b, r.key);
      const row = {rule:r, pa, pb, state:'', agree:null, w:this.weight(r.key)};
      if (r.sameBody && a.body !== b.body) row.state = 'Not scored across bodies (different reference levels)';
      else if (!TT.scorable(pa) || !TT.scorable(pb)) row.state = 'Not scored: value unavailable or only bounded for ' + (!TT.scorable(pa) ? a.name : b.name);
      else {
        const x = pa.v, y = pb.v; let ok;
        if (r.rule === 'ratio'){ ok = x > 0 && y > 0 && Math.max(x, y) / Math.min(x, y) <= r.tol; row.detail = x > 0 && y > 0 ? '×' + TT.fmtNum(Math.max(x,y)/Math.min(x,y)) + ' apart (limit ×' + r.tol + ')' : 'needs positive values'; }
        else { const d = Math.abs(x - y); ok = d <= r.tol; row.detail = TT.fmtNum(d) + ' ' + r.unit + ' apart (limit ' + r.tol + ' ' + r.unit + ')'; }
        row.agree = ok; row.state = 'scored'; n++; tot += row.w; if (ok){ ag += row.w; na++; }
      }
      rows.push(row);
    }
    return {rows, comparable:n, agreeing:na, weightTotal:tot, weightAgree:ag};
  }
};

/* ---------- local search (also the fallback when AI is unavailable) ---------- */
const SYN = {
  body:{moon:['moon','lunar','selene'], mars:['mars','martian','red planet'], earth:['earth','terrestrial']},
  kind:{landing:['landing','land','lander','artemis'], base:['base','outpost','habitat','settlement','exploration zone'], analog:['analog','analogue','resemble','similar','like','match']},
  terrain:{'Impact crater':['crater'], 'Lava tube or pit':['lava tube','cave','pit','skylight'], 'Polar desert':['polar desert'], 'Hyperarid desert':['hyperarid','arid','dry'], 'Volcanic field':['volcanic','volcano','caldera','basalt'], 'Fretted terrain':['fretted','mensae'], 'Massif or plateau':['massif','mountain','plateau']}
};
TT.parseQuery = function(q){
  q = (q || '').toLowerCase(); const f = {body:null, kind:null, terrain:null};
  for (const k in SYN.body) if (SYN.body[k].some(w => new RegExp('\\b' + w + '\\b').test(q))) f.body = f.body || k;
  for (const k in SYN.kind) if (SYN.kind[k].some(w => q.indexOf(w) >= 0)) f.kind = f.kind || k;
  for (const k in SYN.terrain) if (SYN.terrain[k].some(w => q.indexOf(w) >= 0)) f.terrain = f.terrain || k;
  return f;
};
TT.search = function(q, limit){
  const toks = (q || '').toLowerCase().split(/[^a-z0-9°.\-]+/).filter(t => t.length > 1 && !['the','and','for','that','with','near','are','which','what','where','sites','site','places','place','show','find','any','from','has','have'].includes(t));
  if (!toks.length) return [];
  const f = TT.parseQuery(q); const out = [];
  for (const r of S.all()){
    let s = 0; const name = r.name.toLowerCase(), hay = [r.region, r.terrain, r.status_label, r.summary, r.geology, r.environment, r.relevance, r.tags.join(' ')].join(' ').toLowerCase();
    for (const t of toks){ if (name.indexOf(t) >= 0) s += 6; else if (r.tags.some(x => x.toLowerCase().indexOf(t) >= 0)) s += 3; else if (hay.indexOf(t) >= 0) s += 1; }
    if (f.body && r.body === f.body) s += 3; if (f.kind && r.kind === f.kind) s += 2; if (f.terrain && r.terrain === f.terrain) s += 2;
    if (s > 0) out.push({rec: r, score: s});
  }
  out.sort((a, b) => b.score - a.score);
  return out.slice(0, limit || 8);
};

/* related records: analogs for a target, targets for an analog */
TT.related = function(rec){
  const all = S.all();
  if (rec.kind === 'analog') return {label:'Possible Moon and Mars counterparts', items: rec.analog_for.map(id => all.find(r => r.id === id)).filter(Boolean)};
  return {label:'Earth analogs linked to this site', items: all.filter(r => r.kind === 'analog' && r.analog_for.indexOf(rec.id) >= 0)};
};
TT.nearest = function(body, lat, lon, n){
  const R = TT.BODIES[body].radius_km;
  return S.all().filter(r => r.body === body).map(r => ({rec:r, km: TT.haversineKm({lat,lon}, r, R)})).sort((a,b) => a.km - b.km).slice(0, n || 3);
};

TT.bodyChip = body => { const b = TT.BODIES[body]; return TT.h('span', {class:'chip'}, TT.h('span', {class:'dot', style:{background:b.color}}), b.name); };
TT.kindChip = kind => { const k = TT.KINDS[kind]; return TT.h('span', {class:'chip'}, TT.markerIcon(kind, 12), k.label); };
})();
