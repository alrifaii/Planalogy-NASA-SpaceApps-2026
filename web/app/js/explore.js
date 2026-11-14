/* Planalogy — Explore: full-screen 3D globe (or 2D map), filter panel, location panel, search with AI, camera dock. */
(function(){
const TT = window.TT, h = TT.h;
const SUGGEST = ['Moon base candidates', 'Earth analogs linked to Jezero crater', 'Lava tubes or pits', 'Cold polar deserts on Earth', 'Which sites have missing temperature data?'];

TT.pages.explore = function(root, route){
  const S = TT.Store, C = TT.Caps;
  let body = route.body || TT.lsGet('tt_body', 'moon'); if (!TT.BODIES[body]) body = 'moon';
  const pend = TT.pending || {}; TT.pending = null;
  if (pend.select){ const r = S.get(pend.select); if (r) body = r.body; }
  const st = {kinds:new Set(['landing', 'base', 'analog', 'user']), terrains:new Set(), sel:null, hl:new Set(), grid:false, auto:false, layer:'color', pin:false, mode:TT.webgl ? '3d' : '2d', proj:'equi', q:''};
  let g3 = null, g2 = null, ctrl = null, dead = false;

  /* ---------- skeleton ---------- */
  const cv3 = h('canvas', {class:'view grab', role:'application', 'aria-label':'3D globe. Arrow keys rotate, plus and minus zoom. Use the location list to pick a place without the mouse.'});
  const cv2 = h('canvas', {class:'view grab', role:'application', 'aria-label':'2D map. Arrow keys pan, plus and minus zoom. Use the location list to pick a place without the mouse.', style:{display:'none'}});
  const tip = h('div', {class:'tip', hidden:true});
  const stMain = h('div', {role:'status', 'aria-live':'polite'}), attr = h('div', {class:'attr'});
  const status = h('div', {class:'statusline'}, stMain, attr);
  const ex = h('div', {class:'explore'});

  /* top bar */
  const seg = h('div', {class:'seg', role:'radiogroup', 'aria-label':'Planet'});
  TT.BODY_ORDER.forEach(b => seg.appendChild(h('button', {type:'button', role:'radio', dataset:{b}, onclick: () => setBody(b),
    onkeydown: e => { const i = TT.BODY_ORDER.indexOf(body); let n = -1; if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % 3; else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i + 2) % 3; if (n >= 0){ e.preventDefault(); setBody(TT.BODY_ORDER[n]); seg.children[n].focus(); } }},
    h('span', {class:'dot', style:{background:TT.BODIES[b].color}}), TT.BODIES[b].name)));
  const input = h('input', {class:'input', type:'search', placeholder:'Search places, or ask a question', 'aria-label':'Search locations or ask a question', autocomplete:'off', maxlength:'300'});
  const askBtn = h('button', {class:'btn primary ask', type:'button', onclick: () => ask()}, TT.icon('spark'), 'Ask');
  const dd = h('div', {class:'glass dropdown', hidden:true, 'aria-label':'Search suggestions'});
  const searchbox = h('div', {class:'searchbox'}, h('span', {class:'si', html:TT.icons.search}), input, askBtn, dd);
  const aiBox = h('div', {class:'glass ai', hidden:true, 'aria-live':'polite'});
  const topbar = h('div', {class:'topbar'}, h('div', {class:'topbar-row'}, seg, searchbox), aiBox);

  /* left panel */
  const leftP = h('aside', {class:'glass panel-l', 'aria-label':'Filters and locations'});
  const rightP = h('aside', {class:'glass panel-r', 'aria-label':'Selected location'});
  const kindBox = h('div'), terrBox = h('div', {class:'chips'}), listBox = h('ul', {class:'loclist'}), cmpBox = h('div'), pinBox = h('div');
  const leftCount = h('span', {class:'muted small'});
  leftP.append(
    h('div', {class:'panel-head'}, h('h2', {style:{fontSize:'1.05rem'}}, 'Locations ', leftCount), h('button', {class:'btn ghost sm icon sheet-close', type:'button', 'aria-label':'Close filters', html:TT.icons.close, onclick: () => toggleSheet(null)})),
    h('div', {class:'panel-body'},
      h('div', {class:'panel-sec'}, h('h4', null, 'Marker types'), kindBox),
      h('div', {class:'panel-sec', id:'terr-sec'}, h('h4', null, 'Terrain'), terrBox),
      h('div', {class:'panel-sec'}, h('h4', null, 'Places'), listBox),
      h('div', {class:'panel-sec'}, h('h4', null, 'Compare'), cmpBox),
      h('div', {class:'panel-sec'}, h('h4', null, 'My points'), pinBox)));

  /* dock */
  const mkb = (icon, label, fn, pressed) => { const b = h('button', {class:'btn ghost icon', type:'button', 'aria-label':label, title:label, html:TT.icons[icon], onclick:fn}); if (pressed != null) b.setAttribute('aria-pressed', pressed); return b; };
  const bZoomIn = mkb('plus', 'Zoom in', () => cur() && cur().zoomBy(.7)), bZoomOut = mkb('minus', 'Zoom out', () => cur() && cur().zoomBy(1.4));
  const bReset = mkb('reset', 'Reset view', () => { cur() && cur().resetView(); });
  const bAuto = mkb('rotate', 'Auto-rotate', () => { st.auto = !st.auto; g3 && g3.setAuto(st.auto); bAuto.setAttribute('aria-pressed', st.auto); }, false); bAuto.classList.add('hide-sm');
  const bGrid = mkb('grid', 'Latitude and longitude grid', () => { st.grid = !st.grid; [g3, g2].forEach(g => g && g.setGrid(st.grid)); bGrid.setAttribute('aria-pressed', st.grid); }, false); bGrid.classList.add('hide-sm');
  const bMode = h('button', {class:'btn sm', type:'button', onclick: () => setMode(st.mode === '3d' ? '2d' : '3d')});
  const bPin = h('button', {class:'btn sm', type:'button', 'aria-pressed':'false', onclick: () => setPin(!st.pin)}, TT.icon('pin'), 'Drop point');
  const bLayer = h('button', {class:'btn sm', type:'button', 'aria-pressed':'false', title:'Show Earth topography and bathymetry instead of the colour map', onclick: () => { st.layer = st.layer === 'topo' ? 'color' : 'topo'; bLayer.setAttribute('aria-pressed', st.layer === 'topo'); [g3, g2].forEach(g => g && g.setLayer(st.layer)); drawAttr(); }}, 'Elevation layer');
  const projBox = h('div', {class:'seg', role:'radiogroup', 'aria-label':'Map projection', hidden:true});
  [['equi', 'Flat'], ['polar-s', 'South pole'], ['polar-n', 'North pole']].forEach(([k, l]) => projBox.appendChild(h('button', {type:'button', role:'radio', dataset:{k}, onclick: () => setProj(k)}, l)));
  const bFocus = h('button', {class:'btn sm hide-sm', type:'button', 'aria-pressed':'false', title:'Hide the side panels to see the whole planet', onclick: () => { const on = ex.classList.toggle('focus'); bFocus.setAttribute('aria-pressed', on); bFocus.lastChild.textContent = on ? 'Show panels' : 'Hide panels'; setTimeout(() => cur() && cur().resize(), 30); }}, TT.icon('eye'), h('span', null, 'Hide panels'));
  const bFs = document.fullscreenEnabled ? h('button', {class:'btn sm hide-sm', type:'button', 'aria-pressed':'false', onclick: () => { if (document.fullscreenElement) document.exitFullscreen(); else ex.requestFullscreen().catch(() => TT.toast('Full screen is not allowed in this view. “Hide panels” still clears the screen.', true)); }}, 'Full screen') : null;
  const onFs = () => { if (bFs){ const on = document.fullscreenElement === ex; bFs.setAttribute('aria-pressed', on); bFs.textContent = on ? 'Exit full screen' : 'Full screen'; setTimeout(() => cur() && cur().resize(), 60); } };
  document.addEventListener('fullscreenchange', onFs);
  const bLeft = h('button', {class:'btn sm', type:'button', onclick: () => toggleSheet('l')}, TT.icon('filter'), 'Places');
  const bRight = h('button', {class:'btn sm', type:'button', onclick: () => toggleSheet('r')}, TT.icon('info'), 'Details');
  const dock = h('div', {class:'glass dock', role:'toolbar', 'aria-label':'Map controls'}, bZoomIn, bZoomOut, bReset, bAuto, bGrid, h('span', {class:'div'}), bMode, projBox, bLayer, bPin, h('span', {class:'div'}), bFocus, bFs, h('span', {class:'sheet-btns'}, h('span', {class:'div'}), bLeft, bRight));

  ex.append(cv3, cv2, tip, topbar, leftP, rightP, dock, status);
  root.appendChild(ex);

  /* ---------- helpers ---------- */
  const cur = () => st.mode === '3d' && g3 ? g3 : g2;
  const visible = r => st.kinds.has(r.kind) && (!st.terrains.size || st.terrains.has(r.terrain));
  const pinsOf = b => S.pins.filter(p => p.body === b);
  const rec = id => S.get(id) || S.pin(id);
  function items(){
    const a = S.all().filter(visible).map(r => ({id:r.id, body:r.body, kind:r.kind, lat:r.lat, lon:r.lon, name:r.name}));
    if (st.kinds.has('user')) S.pins.forEach(p => a.push({id:p.id, body:p.body, kind:'user', lat:p.lat, lon:p.lon, name:p.name}));
    return a;
  }
  function pushMarkers(){ const it = items(); [g3, g2].forEach(g => g && g.setMarkers(it)); applySel(); }
  function applySel(){ [g3, g2].forEach(g => g && g.setSelection(st.sel, [...st.hl])); }
  function say(t){ stMain.textContent = t; stMain.hidden = !t; }
  function sayDefault(){
    if (st.pin) say('Click the surface to drop a point. Press Esc to cancel.');
    else say(TT.BODIES[body].name + ' · ' + S.byBody(body).filter(visible).length + ' of ' + S.byBody(body).length + ' places shown · ' + (st.mode === '3d' ? 'drag to rotate, scroll to zoom' : 'drag to pan, scroll to zoom'));
  }
  function drawAttr(){
    const b = TT.BODIES[body];
    const t = [b.tex + (body === 'earth' && st.layer === 'topo' ? ' (topography and bathymetry layer)' : '') + '.'];
    t.push(st.mode === '3d' && body !== 'earth' ? 'Marker positions are real; the surface is a global map with a visual relief shading, not elevation data.' : 'Global map at low resolution: marker positions are real, local surface detail is not.');
    attr.textContent = t.join(' ');
  }
  function toggleSheet(w){ leftP.classList.toggle('open', w === 'l' && !leftP.classList.contains('open')); rightP.classList.toggle('open', w === 'r' && !rightP.classList.contains('open')); }

  /* ---------- body, mode, projection ---------- */
  function setBody(b, quiet){
    if (b === body && g3 && quiet !== 'force') return;
    body = b; TT.lsSet('tt_body', b); if (!quiet) try { history.replaceState(null, '', '#explore-' + b); } catch(e){}
    [g3, g2].forEach(g => { if (g){ g.setBody(b); if (b === 'earth') g.setLayer(st.layer); } });
    if (g2 && st.proj !== 'equi'){ g2.setProjection(st.proj === 'polar-n' ? 'polar-n' : 'polar-s'); }
    if (st.sel){ const r = rec(st.sel); if (!r || r.body !== b){ st.sel = null; st.hl = new Set(); } }
    [...seg.children].forEach(x => { const on = x.dataset.b === b; x.setAttribute('aria-checked', on); x.tabIndex = on ? 0 : -1; });
    bLayer.hidden = b !== 'earth';
    drawKinds(); drawTerrains(); drawList(); drawPins(); drawRight(); pushMarkers(); drawAttr(); sayDefault();
    cur() && cur().resetView(); closeAI();
  }
  function setMode(m){
    if (m === '3d' && !g3){ TT.toast('3D needs WebGL, which is not available in this browser.', true); return; }
    const prev = cur(); st.mode = m;
    if (m === '2d') ensure2d();
    cv3.style.display = m === '3d' ? '' : 'none'; cv2.style.display = m === '2d' ? '' : 'none';
    bMode.textContent = m === '3d' ? 'Switch to 2D map' : 'Switch to 3D globe'; bMode.disabled = !g3 && m === '2d';
    bMode.title = !g3 ? '3D globe is unavailable (no WebGL)' : '';
    bAuto.hidden = m !== '3d'; projBox.hidden = m !== '2d';
    requestAnimationFrame(() => {
      if (dead) return;
      if (m === '2d' && g2){ g2.resize(); if (prev && prev.kind === '3d') g2.focus(prev.view.lat, prev.view.lon, {span:70, dur:0}); else g2.resetView(); }
      if (m === '3d' && g3){ g3.resize(); if (prev && prev.kind === '2d' && st.proj === 'equi') g3.focus(prev.view.lat, prev.view.lon, {dist:2.6, dur:0}); }
      if (st.sel){ const r = rec(st.sel); r && fly(r, 0); }
    });
    drawAttr(); sayDefault();
  }
  function setProj(k, auto){
    st.proj = k; if (!g2) return;
    if (k === 'equi'){ g2.setProjection('equi'); g2.resetView(); } else g2.setProjection(k, 30);
    [...projBox.children].forEach(x => x.setAttribute('aria-checked', x.dataset.k === k));
    if (k !== 'equi'){ say(auto ? 'Flat maps stretch badly near the poles, so this site is shown in a polar view (60° to the pole).' : 'Polar view covers 60° to the pole; sites outside it are hidden.'); setTimeout(sayDefault, 4000); }
    if (st.sel){ const r = rec(st.sel); r && fly(r, 0); }
  }
  function ensure2d(){
    if (g2) return;
    g2 = TT.createMap2D(cv2, {body, onPick:pick, onHover:hover, onPin:dropPin, onBlank:blank});
    g2.setMarkers(items()); applySel(); g2.setGrid(st.grid); if (body === 'earth') g2.setLayer(st.layer);
    requestAnimationFrame(() => { g2.resize(); g2.resetView(); });
  }
  function setPin(on){
    st.pin = on; bPin.setAttribute('aria-pressed', on); [g3, g2].forEach(g => g && g.setPinMode(on)); sayDefault();
  }

  /* ---------- interactions ---------- */
  function pick(it){ select(it.id); }
  function blank(){ closeDD(); }
  function hover(it, x, y){
    if (!it){ tip.hidden = true; return; }
    tip.textContent = it.name; tip.style.left = x + 'px'; tip.style.top = y + 'px'; tip.hidden = false;
  }
  function dropPin(lat, lon){
    const p = S.addPin(body, lat, lon); setPin(false); select(p.id, {fly:false});
    TT.toast('Point added. It is stored in this browser only.');
  }
  function fly(r, dur){
    const g = cur(); if (!g) return;
    if (g.kind === '2d'){
      const polarSite = Math.abs(r.lat) >= 75;
      if (polarSite && st.proj === 'equi') setProj(r.lat < 0 ? 'polar-s' : 'polar-n', true);
      else if (!polarSite && st.proj !== 'equi') setProj('equi', true);
    }
    if (g.kind === '3d') g.focus(r.lat, r.lon, {dist:1.9, dur});
    else if (st.proj !== 'equi') g.focus(r.lat, r.lon, {zoom:5, dur});
    else g.focus(r.lat, r.lon, {span:14, dur});
  }
  function select(id, o){
    o = o || {}; const r = rec(id); if (!r) return;
    if (r.body !== body) setBody(r.body, 'force');
    st.sel = id; st.hl = new Set();
    if (r.kind !== 'user'){ TT.related(r).items.filter(x => x.body === body).forEach(x => st.hl.add(x.id)); }
    applySel(); drawRight(); markCurrent();
    if (o.fly !== false) fly(r);
    if (window.matchMedia('(max-width:900px)').matches){ leftP.classList.remove('open'); rightP.classList.add('open'); }
    closeDD();
  }
  function deselect(){ st.sel = null; st.hl = new Set(); applySel(); drawRight(); markCurrent(); }

  /* ---------- left panel ---------- */
  function drawKinds(){
    TT.clear(kindBox);
    ['landing', 'base', 'analog', 'user'].forEach(k => {
      const n = k === 'user' ? pinsOf(body).length : S.byBody(body).filter(r => r.kind === k).length;
      const cb = h('input', {type:'checkbox', checked:st.kinds.has(k), onchange: e => { e.target.checked ? st.kinds.add(k) : st.kinds.delete(k); drawList(); pushMarkers(); sayDefault(); }});
      kindBox.appendChild(h('label', {class:'check'}, cb, TT.markerIcon(k, 14), h('span', null, TT.KINDS[k].label), h('span', {class:'n'}, n)));
    });
  }
  function drawTerrains(){
    TT.clear(terrBox);
    const ts = [...new Set(S.byBody(body).map(r => r.terrain).filter(Boolean))].sort();
    ts.forEach(t => terrBox.appendChild(h('button', {class:'chip', type:'button', 'aria-pressed':st.terrains.has(t), onclick: e => { st.terrains.has(t) ? st.terrains.delete(t) : st.terrains.add(t); e.currentTarget.setAttribute('aria-pressed', st.terrains.has(t)); drawList(); pushMarkers(); sayDefault(); }}, t)));
    if (!ts.length) terrBox.appendChild(h('span', {class:'muted small'}, 'No terrain classes recorded.'));
    TT.$('#terr-sec', leftP).hidden = !ts.length;
  }
  function drawList(){
    TT.clear(listBox);
    const rs = S.byBody(body).filter(visible).sort((a, b) => a.kind.localeCompare(b.kind) || a.name.localeCompare(b.name));
    leftCount.textContent = '(' + rs.length + ')';
    rs.forEach(r => listBox.appendChild(h('li', null, h('button', {type:'button', dataset:{id:r.id}, 'aria-current':st.sel === r.id, onclick: () => select(r.id)}, TT.markerIcon(r.kind, 14), h('span', null, h('div', {class:'nm'}, r.name), h('div', {class:'rg'}, r.region || TT.KINDS[r.kind].label))))));
    if (!rs.length) listBox.appendChild(h('li', {class:'muted small', style:{padding:'8px'}}, 'Nothing matches the current filters.'));
    drawCmp();
  }
  function markCurrent(){ listBox.querySelectorAll('button').forEach(b => b.setAttribute('aria-current', b.dataset.id === st.sel)); pinBox.querySelectorAll('button[data-id]').forEach(b => b.setAttribute('aria-current', b.dataset.id === st.sel)); }
  function drawCmp(){
    TT.clear(cmpBox); const ids = TT.Compare.ids.filter(id => S.get(id));
    if (!ids.length) cmpBox.appendChild(h('p', {class:'muted small', style:{margin:0}}, 'Add places from their detail panel to compare them side by side.'));
    ids.forEach(id => { const r = S.get(id); cmpBox.appendChild(h('div', {class:'relrow'}, TT.markerIcon(r.kind, 12), h('span', {class:'grow small'}, r.name), h('button', {class:'btn ghost sm icon', type:'button', 'aria-label':'Remove ' + r.name + ' from comparison', html:TT.icons.close, onclick: () => { TT.Compare.remove(id); drawCmp(); drawRight(); }}))); });
    if (ids.length) cmpBox.appendChild(h('a', {class:'btn sm' + (ids.length > 1 ? ' primary' : ''), href:'#compare', 'aria-disabled':ids.length < 2, style:{marginTop:'6px'}}, ids.length > 1 ? 'Open comparison' : 'Add one more to compare'));
  }
  function drawPins(){
    TT.clear(pinBox); const ps = pinsOf(body);
    if (!ps.length) pinBox.appendChild(h('p', {class:'muted small', style:{margin:0}}, 'Use “Drop point” in the toolbar, then click the surface. Points stay in this browser.'));
    ps.forEach(p => pinBox.appendChild(h('div', {class:'relrow'}, TT.markerIcon('user', 12),
      h('button', {class:'btn ghost sm grow', type:'button', dataset:{id:p.id}, 'aria-current':st.sel === p.id, style:{justifyContent:'flex-start', textAlign:'left', padding:'0 6px'}, onclick: () => select(p.id)}, h('span', null, p.name, h('span', {class:'tiny muted mono', style:{display:'block', fontWeight:400}}, TT.fmtCoord(p.lat, p.lon, 2)))),
      h('button', {class:'btn ghost sm icon', type:'button', 'aria-label':'Remove ' + p.name, html:TT.icons.trash, onclick: () => { S.removePin(p.id); if (st.sel === p.id) deselect(); }}))));
  }

  /* ---------- right panel ---------- */
  function drawRight(){
    TT.clear(rightP);
    const close = h('button', {class:'btn ghost sm icon', type:'button', 'aria-label':'Close details', html:TT.icons.close, onclick: () => { deselect(); rightP.classList.remove('open'); }});
    const r = st.sel && rec(st.sel);
    if (!r){
      rightP.append(h('div', {class:'panel-head'}, h('h2', {style:{fontSize:'1.05rem'}}, 'Details'), h('button', {class:'btn ghost sm icon sheet-close', type:'button', 'aria-label':'Close', html:TT.icons.close, onclick: () => rightP.classList.remove('open')})),
        h('div', {class:'panel-body'},
          h('p', {class:'muted'}, 'Select a marker on the ' + (st.mode === '3d' ? 'globe' : 'map') + ' or a place in the list to see its data here.'),
          h('div', {class:'panel-sec'}, h('h4', null, 'Marker legend'), Object.keys(TT.KINDS).map(k => h('div', {class:'check', style:{cursor:'default'}}, TT.markerIcon(k, 14), TT.KINDS[k].label))),
          h('div', {class:'panel-sec'}, h('h4', null, 'About these values'),
            h('p', {class:'small muted'}, 'Each value carries a status: ', TT.badge('measured'), ' reported by a cited source, ', TT.badge('derived'), ' inferred or computed, ', TT.badge('unavailable'), ' not in the dataset. Records are samples, not expert-reviewed.'))));
      return;
    }
    const head = h('div', {class:'panel-head'}, h('div', {style:{minWidth:0}}, h('h2', {style:{fontSize:'1.15rem', marginBottom:'6px'}}, r.name), h('div', {style:{display:'flex', gap:'6px', flexWrap:'wrap'}}, TT.bodyChip(r.body), TT.kindChip(r.kind))), close);
    const bodyEl = h('div', {class:'panel-body'});
    bodyEl.appendChild(h('div', {class:'coord', style:{margin:'4px 0 6px'}}, TT.fmtCoord(r.lat, r.lon, 3), h('button', {class:'btn ghost sm icon', type:'button', 'aria-label':'Copy coordinates', html:TT.icons.copy, onclick: () => { const t = r.lat.toFixed(4) + ', ' + r.lon.toFixed(4); (navigator.clipboard && navigator.clipboard.writeText(t).then(() => TT.toast('Coordinates copied'), () => TT.toast('Copy is not allowed here: ' + t))) || TT.toast(t); }})));
    if (r.kind === 'user'){
      bodyEl.appendChild(h('p', {class:'small muted'}, 'A point you placed. It lives in this browser only and has no stored science data: no terrain class, temperature or elevation. The map is a global image and cannot show local detail.'));
      const near = TT.nearest(r.body, r.lat, r.lon, 3);
      bodyEl.appendChild(h('div', {class:'panel-sec'}, h('h4', null, 'Nearest known places'), near.map(n => h('div', {class:'relrow'}, TT.markerIcon(n.rec.kind, 12), h('span', {class:'grow small'}, n.rec.name, h('span', {class:'tiny muted mono', style:{display:'block'}}, TT.fmtNum(n.km) + ' km away')), h('button', {class:'btn sm', type:'button', onclick: () => select(n.rec.id)}, 'Show'))), !near.length ? h('p', {class:'muted small'}, 'No places recorded on this body.') : null));
      bodyEl.appendChild(h('div', {class:'panel-sec'}, h('button', {class:'btn danger sm', type:'button', onclick: () => { S.removePin(r.id); deselect(); }}, TT.icon('trash'), 'Remove point')));
      rightP.append(head, bodyEl); return;
    }
    const im = r.images[0];
    bodyEl.appendChild(im ? h('figure', {style:{margin:'0 0 10px'}}, h('img', {class:'panel-img', src:im.url, alt:im.caption || 'Image of ' + r.name, loading:'lazy'}), h('figcaption', {class:'tiny muted', style:{marginTop:'4px'}}, (im.caption ? im.caption + ' · ' : '') + 'Credit: ' + (im.credit || 'not recorded') + ' · ' + (im.license || 'license not recorded')))
      : h('p', {class:'panel-img-empty'}, 'No site image has been added for this location. The map shows a global base map only.'));
    if (r.status_label) bodyEl.appendChild(h('p', {class:'small', style:{color:'var(--accent2)', margin:'0 0 8px'}}, r.status_label));
    bodyEl.appendChild(h('p', {class:'small', style:{color:'#d5dcea'}}, r.summary || 'No summary has been written for this place.'));
    const kv = h('dl', {class:'kv'});
    const row = (label, val, status) => { kv.appendChild(h('dt', null, label)); kv.appendChild(h('dd', {class:'val' + (val && val.length > 24 ? ' long' : '')}, val ? val : h('span', {class:'na'}, 'Not available'), status ? h('span', null, ' ', TT.badge(status)) : null)); };
    row('Terrain class', r.terrain || null);
    const missingKeys = [];
    TT.paramList([r]).filter(p => !p.derived && p.key !== 'precip_mm_yr').forEach(p => { const x = TT.paramOf(r, p.key); if (TT.paramText(x)) row(p.label, TT.paramText(x), x.status); else missingKeys.push(p.label); });
    if (missingKeys.length) { kv.appendChild(h('dt', null, 'Not available')); kv.appendChild(h('dd', {class:'na', style:{fontStyle:'normal'}}, missingKeys.join(', '))); }
    bodyEl.appendChild(h('div', {class:'panel-sec'}, h('h4', null, 'Key facts'), kv));
    const acts = h('div', {class:'panel-sec', style:{display:'flex', gap:'8px', flexWrap:'wrap'}},
      h('a', {class:'btn primary sm', href:'#location-' + r.id}, 'View full details'),
      h('button', {class:'btn sm', type:'button', onclick: () => fly(r)}, TT.icon('pin'), 'Fly to'),
      h('button', {class:'btn sm', type:'button', 'aria-pressed':TT.Compare.has(r.id), onclick: e => { TT.Compare.toggle(r.id); e.currentTarget.setAttribute('aria-pressed', TT.Compare.has(r.id)); e.currentTarget.lastChild.textContent = TT.Compare.has(r.id) ? 'In comparison' : 'Compare'; drawCmp(); }}, TT.icon('compare'), h('span', null, TT.Compare.has(r.id) ? 'In comparison' : 'Compare')));
    bodyEl.appendChild(acts);
    const rel = TT.related(r);
    if (rel.items.length){
      bodyEl.appendChild(h('div', {class:'panel-sec'}, h('h4', null, rel.label),
        rel.items.map(x => h('div', {class:'relrow'}, TT.markerIcon(x.kind, 12), h('span', {class:'grow small'}, x.name, h('span', {class:'tiny muted', style:{display:'block'}}, TT.BODIES[x.body].name + ' · ' + TT.KINDS[x.kind].short)),
          h('button', {class:'btn sm', type:'button', onclick: () => select(x.id)}, x.body === body ? 'Show' : 'Show on ' + TT.BODIES[x.body].name))),
        r.kind === 'analog' && r.rationale ? h('p', {class:'tiny muted'}, 'Why: ' + r.rationale) : null,
        h('p', {class:'tiny muted'}, 'Links are editorial inferences from the sources, not measured matches.')));
    }
    bodyEl.appendChild(h('div', {class:'panel-sec tiny muted'}, 'Updated ' + (r.updated || 'unknown') + ' · ', h('span', {class:'badge ' + (r.verification === 'reviewed' ? 'measured' : 'sample')}, r.verification === 'reviewed' ? 'reviewed' : 'sample data')));
    rightP.append(head, bodyEl);
  }

  /* ---------- search and AI ---------- */
  function closeDD(){ dd.hidden = true; }
  function drawDD(){
    TT.clear(dd); const q = input.value.trim();
    if (!q){
      dd.appendChild(h('div', {class:'tiny muted', style:{padding:'6px 10px'}}, 'Try asking'));
      SUGGEST.forEach(s => dd.appendChild(h('button', {class:'row', type:'button', onclick: () => { input.value = s; closeDD(); ask(); }}, TT.icon('spark'), h('span', null, s))));
    } else {
      const res = TT.search(q, 6);
      if (res.length) dd.appendChild(h('div', {class:'tiny muted', style:{padding:'6px 10px'}}, 'Places'));
      res.forEach(x => dd.appendChild(h('button', {class:'row', type:'button', onclick: () => { closeDD(); select(x.rec.id); }}, TT.markerIcon(x.rec.kind, 14), h('span', null, h('b', {style:{fontWeight:600}}, x.rec.name), h('span', {class:'tiny muted', style:{display:'block'}}, TT.BODIES[x.rec.body].name + ' · ' + (x.rec.region || TT.KINDS[x.rec.kind].label))))));
      dd.appendChild(h('button', {class:'row', type:'button', onclick: () => { closeDD(); ask(); }}, TT.icon('spark'), h('span', null, (C.sample ? 'Ask: ' : 'Search: '), h('b', {style:{fontWeight:600}}, q))));
    }
    dd.hidden = false;
  }
  input.addEventListener('focus', drawDD);
  input.addEventListener('input', TT.debounce(() => { if (document.activeElement === input) drawDD(); }, 120));
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter'){ e.preventDefault(); closeDD(); ask(); }
    else if (e.key === 'ArrowDown'){ const f = dd.querySelector('button'); if (f){ e.preventDefault(); f.focus(); } }
    else if (e.key === 'Escape'){ closeDD(); }
  });
  dd.addEventListener('keydown', e => {
    const bs = [...dd.querySelectorAll('button')], i = bs.indexOf(document.activeElement);
    if (e.key === 'ArrowDown'){ e.preventDefault(); (bs[i + 1] || bs[0]).focus(); } else if (e.key === 'ArrowUp'){ e.preventDefault(); i <= 0 ? input.focus() : bs[i - 1].focus(); } else if (e.key === 'Escape'){ closeDD(); input.focus(); }
  });
  const onDoc = e => { if (!searchbox.contains(e.target)) closeDD(); };
  document.addEventListener('pointerdown', onDoc);

  const put = (el, ...kids) => kids.forEach(k => TT.append(el, k));
  function closeAI(){ if (ctrl){ ctrl.abort(); ctrl = null; } aiBox.hidden = true; TT.clear(aiBox); st.hl = new Set(); if (st.sel){ const r = rec(st.sel); r && r.kind !== 'user' && TT.related(r).items.filter(x => x.body === body).forEach(x => st.hl.add(x.id)); } applySel(); }
  function aiHead(title){ return h('div', {style:{display:'flex', alignItems:'center', justifyContent:'space-between', gap:'8px'}}, h('h3', null, TT.icon('spark'), title), h('button', {class:'btn ghost sm icon', type:'button', 'aria-label':'Close search results', html:TT.icons.close, onclick: closeAI})); }
  function resultRow(rec0, why){
    return h('button', {class:'res', type:'button', onclick: () => select(rec0.id)}, TT.markerIcon(rec0.kind, 14),
      h('span', {style:{minWidth:0}}, h('b', {style:{fontWeight:600}}, rec0.name), h('span', {class:'muted small', style:{display:'block'}}, TT.BODIES[rec0.body].name + ' · ' + TT.KINDS[rec0.kind].label + (rec0.region ? ' · ' + rec0.region : '')), why ? h('span', {class:'small', style:{display:'block', marginTop:'3px', color:'#d5dcea'}}, why) : null));
  }
  function highlightResults(list){
    if (!list.length) return;
    const counts = {}; list.forEach(x => counts[x.rec.body] = (counts[x.rec.body] || 0) + 1);
    const target = list[0].rec.body; if (target !== body) setBody(target, 'force');
    st.sel = null; st.hl = new Set(list.filter(x => x.rec.body === body).map(x => x.rec.id)); applySel(); drawRight(); markCurrent();
    const first = list.find(x => x.rec.body === body); first && fly(first.rec, 900);
    const g = cur(); if (g && g.kind === '3d') g.focus(first.rec.lat, first.rec.lon, {dist:2.7});
  }
  const hintLine = () => h('p', {class:'tiny muted', style:{margin:'12px 0 0'}}, C.sample ? 'Answers use only the records in this database and can be wrong. Open a place to check its sources. Asking sends your question and a summary of the database to Claude through your account.' : 'Keyword search over the records in this database.');
  async function ask(){
    const q = input.value.trim();
    if (ctrl){ ctrl.abort(); ctrl = null; }
    aiBox.hidden = false; TT.clear(aiBox);
    if (q.length < 3){ put(aiBox, aiHead('Search'), h('p', {class:'muted'}, 'Type at least three characters, or try one of these:'), h('div', {class:'chips'}, SUGGEST.map(s => h('button', {class:'chip', type:'button', onclick: () => { input.value = s; ask(); }}, s)))); return; }
    const local = () => TT.search(q, 8).map(x => ({rec:x.rec, why:''}));
    if (!C.sample){
      const res = local();
      put(aiBox, aiHead('Search results'), h('div', {class:'notice info', style:{marginTop:'10px'}}, TT.icon('info'), h('span', null, 'AI search is not available in this view, so this is keyword matching on names, tags and text.')),
        res.length ? res.map(x => resultRow(x.rec)) : h('p', {class:'muted'}, 'No records match “' + q + '”. The database may not cover this.'), hintLine());
      highlightResults(res); return;
    }
    ctrl = new AbortController(); const mine = ctrl;
    put(aiBox, aiHead('AI search'), h('p', {style:{display:'flex', gap:'10px', alignItems:'center'}}, h('span', {class:'spin'}), 'Searching the Planalogy database…'), h('button', {class:'btn sm', type:'button', onclick: closeAI}, 'Cancel'));
    askBtn.disabled = true;
    try {
      const out = await TT.AI.ask(q, {signal:mine.signal});
      if (mine !== ctrl || dead) return;
      TT.clear(aiBox);
      const chips = []; if (out.filters.body) chips.push(TT.BODIES[out.filters.body].name); if (out.filters.kind) chips.push(TT.KINDS[out.filters.kind].label);
      put(aiBox, aiHead('AI search'), h('p', {class:'answer'}, out.answer || (out.results.length ? '' : 'The database has no matching records.')),
        chips.length ? h('div', {class:'chips', style:{marginBottom:'6px'}}, chips.map(c => h('span', {class:'chip'}, c))) : null,
        out.results.map(x => resultRow(x.rec, x.why)),
        out.gaps ? h('div', {class:'notice info', style:{marginTop:'10px'}}, TT.icon('info'), h('span', null, 'Gaps: ' + out.gaps)) : null,
        !out.results.length ? h('div', {class:'chips', style:{marginTop:'8px'}}, SUGGEST.map(s => h('button', {class:'chip', type:'button', onclick: () => { input.value = s; ask(); }}, s))) : null, hintLine());
      highlightResults(out.results);
    } catch(e){
      if (mine !== ctrl || dead || (e && e.code === 'cancelled') || (e && e.name === 'AbortError')) return;
      TT.clear(aiBox); const res = local();
      put(aiBox, aiHead('Search results'), h('div', {class:'notice bad', style:{marginTop:'10px'}}, TT.icon('info'), h('span', null, TT.AI.errorText(e) + (res.length ? ' Keyword matches are shown instead.' : ''))),
        res.length ? res.map(x => resultRow(x.rec)) : h('p', {class:'muted'}, 'No keyword matches either.'), h('button', {class:'btn sm', type:'button', style:{marginTop:'8px'}, onclick: () => ask()}, 'Try again'));
      highlightResults(res);
    } finally { askBtn.disabled = false; if (mine === ctrl) ctrl = null; }
  }

  /* ---------- keyboard ---------- */
  const onKey = e => { if (e.key === 'Escape' && !document.querySelector('.scrim')){ if (st.pin) setPin(false); else if (!dd.hidden) closeDD(); else if (!aiBox.hidden) closeAI(); else if (leftP.classList.contains('open') || rightP.classList.contains('open')){ leftP.classList.remove('open'); rightP.classList.remove('open'); } } };
  document.addEventListener('keydown', onKey);

  /* ---------- start ---------- */
  if (TT.webgl) g3 = TT.createGlobe(cv3, {body, onPick:pick, onHover:hover, onPin:dropPin, onBlank:blank});
  if (!g3) st.mode = '2d';
  bMode.textContent = st.mode === '3d' ? 'Switch to 2D map' : 'Switch to 3D globe'; bMode.disabled = !g3; if (!g3) bMode.title = '3D globe is unavailable (no WebGL)';
  bAuto.hidden = st.mode !== '3d'; projBox.hidden = st.mode !== '2d';
  [...projBox.children].forEach(x => x.setAttribute('aria-checked', x.dataset.k === st.proj));
  if (st.mode === '2d') ensure2d();
  cv3.style.display = st.mode === '3d' ? '' : 'none'; cv2.style.display = st.mode === '2d' ? '' : 'none';
  setBody(body, 'force');
  if (pend.select){ select(pend.select); }
  if (!g3 && !TT.webgl){ say('3D is not available in this browser: showing the 2D map.'); setTimeout(sayDefault, 5000); }

  return {
    destroy(){ dead = true; if (ctrl) ctrl.abort(); document.removeEventListener('keydown', onKey); document.removeEventListener('fullscreenchange', onFs); if (document.fullscreenElement === ex) document.exitFullscreen(); document.removeEventListener('pointerdown', onDoc); g3 && g3.dispose(); g2 && g2.dispose(); },
    refresh(){
      if (st.sel && !rec(st.sel)){ st.sel = null; st.hl = new Set(); }
      drawKinds(); drawTerrains(); drawList(); drawPins(); drawRight(); pushMarkers(); sayDefault();
    }
  };
};
})();
