/* Planalogy — comparison page. Parameters are shown side by side with their status; agreement is a transparent count, never a hidden percentage. */
(function(){
const TT = window.TT, h = TT.h;
const MAX = 4;
const CMP = TT.Compare = {
  ids: TT.lsGet('tt_compare', []).filter(x => typeof x === 'string').slice(0, MAX), onChange: null,
  has(id){ return this.ids.indexOf(id) >= 0; },
  toggle(id){
    if (this.has(id)) this.ids = this.ids.filter(x => x !== id);
    else if (this.ids.length >= MAX){ TT.toast('You can compare up to ' + MAX + ' locations. Remove one first.', true); return false; }
    else this.ids.push(id);
    this.save(); return true;
  },
  add(id){ if (!this.has(id)) return this.toggle(id); return true; },
  remove(id){ this.ids = this.ids.filter(x => x !== id); this.save(); },
  save(){ TT.lsSet('tt_compare', this.ids); this.onChange && this.onChange(); }
};

/* modal picker */
TT.pickLocation = function(exclude, cb){
  TT.modal((dlg, close) => {
    const list = h('div', {style:{maxHeight:'52vh', overflow:'auto', marginTop:'10px'}});
    const q = h('input', {class:'input', type:'search', placeholder:'Search by name, region or tag', 'aria-label':'Search locations'});
    const draw = () => {
      TT.clear(list); const t = q.value.trim().toLowerCase();
      TT.BODY_ORDER.forEach(b => {
        const rs = TT.Store.byBody(b).filter(r => exclude.indexOf(r.id) < 0 && (!t || (r.name + ' ' + r.region + ' ' + r.tags.join(' ')).toLowerCase().indexOf(t) >= 0));
        if (!rs.length) return;
        list.appendChild(h('h4', {class:'muted', style:{margin:'12px 0 6px'}}, TT.BODIES[b].name));
        rs.forEach(r => list.appendChild(h('button', {class:'btn ghost', style:{width:'100%', justifyContent:'flex-start', textAlign:'left'}, onclick: () => { close(); cb(r.id); }}, TT.markerIcon(r.kind, 14), h('span', null, r.name, h('span', {class:'muted small', style:{display:'block', fontWeight:400}}, r.region)))));
      });
      if (!list.firstChild) list.appendChild(h('p', {class:'muted'}, 'No locations match.'));
    };
    q.addEventListener('input', draw); draw();
    dlg.append(h('h3', null, 'Add a location to compare'), q, list, h('div', {class:'acts'}, h('button', {class:'btn', onclick: () => close()}, 'Cancel')));
  }, {label:'Add a location'});
};

/* bar chart as SVG: linear (diverging around zero) or log scale; every bar carries its value as text */
function barChart(param, recs){
  const rows = recs.map(r => { const p = TT.paramOf(r, param.key); return {r, p, v: TT.scorable(p) ? p.v : null}; });
  const vals = rows.filter(x => x.v != null).map(x => x.v);
  const wrap = h('figure', {class:'chart', style:{margin:'18px 0'}});
  wrap.appendChild(h('figcaption', {class:'small', style:{marginBottom:'6px'}}, h('b', null, param.label), ' (' + param.unit + ')' + (param.scale === 'log' ? ' — log scale' : '')));
  if (!vals.length){ wrap.appendChild(h('p', {class:'na small'}, 'No scored values for the selected locations.')); return wrap; }
  const W = 640, rowH = 34, L = 190, Rm = 90, innerW = W - L - Rm, Hh = rows.length * rowH + 8;
  const ns = 'http://www.w3.org/2000/svg'; const svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 ' + W + ' ' + Hh); svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', param.label + ': ' + rows.map(x => x.r.name + ' ' + (x.v != null ? TT.fmtNum(x.v) : 'not available')).join('; '));
  const el = (n, a, t) => { const e = document.createElementNS(ns, n); for (const k in a) e.setAttribute(k, a[k]); if (t != null) e.textContent = t; svg.appendChild(e); return e; };
  let x0, scale;
  if (param.scale === 'log'){
    const lo = Math.floor(Math.log10(Math.min(...vals)) - .1), hi = Math.ceil(Math.log10(Math.max(...vals)) + .05); x0 = L; scale = v => L + (Math.log10(v) - lo) / (hi - lo) * innerW;
    for (let e = lo; e <= hi; e++){ const x = L + (e - lo) / (hi - lo) * innerW; el('line', {x1:x, x2:x, y1:0, y2:Hh - 6, stroke:'rgba(169,199,232,.15)'}); }
  } else {
    const mn = Math.min(0, ...vals), mx = Math.max(0, ...vals), span = (mx - mn) || 1; scale = v => L + (v - mn) / span * innerW; x0 = scale(0);
    el('line', {x1:x0, x2:x0, y1:0, y2:Hh - 6, stroke:'rgba(169,199,232,.4)'});
  }
  rows.forEach((x, i) => {
    const y = i * rowH + 4, name = x.r.name.length > 28 ? x.r.name.slice(0, 27) + '…' : x.r.name;
    el('text', {x:L - 10, y:y + 19, 'text-anchor':'end'}, name);
    if (x.v == null){ el('text', {x:L + 8, y:y + 19, class:'na'}, x.p.status === 'unavailable' ? 'not available' : 'bounded value, not charted'); return; }
    const xv = scale(x.v), bx = Math.min(x0, xv), bw = Math.max(2, Math.abs(xv - x0));
    el('rect', {x:bx, y:y + 5, width:bw, height:18, rx:3, fill:TT.BODIES[x.r.body].color, opacity:.9});
    el('text', {x:Math.min(Math.max(bx + bw, x0) + 8, W - 6), y:y + 19, class:'v', 'text-anchor':'start'}, TT.fmtNum(x.v) + (x.p.status === 'derived' ? ' (derived)' : ''));
  });
  wrap.appendChild(svg); return wrap;
}

TT.pages.compare = function(root){
  const S = TT.Store; let maps = [];
  const page = h('div', {class:'wrap page'}); root.appendChild(page);
  const weightsOpen = {v:false};
  function render(){
    maps.forEach(m => m.dispose()); maps = [];
    TT.clear(page);
    CMP.ids = CMP.ids.filter(id => S.get(id));
    const recs = CMP.ids.map(id => S.get(id));
    page.append(h('h1', null, 'Compare locations'),
      h('p', {class:'lede'}, 'Put two to four places side by side. Each value shows whether it was measured, derived or is unavailable, and where it came from.'));
    const slots = h('div', {class:'slots'});
    for (let i = 0; i < MAX; i++){
      const r = recs[i];
      if (!r){
        slots.appendChild(h('div', {class:'slot empty'}, h('button', {class:'btn', onclick: () => TT.pickLocation(CMP.ids, id => { CMP.add(id); render(); })}, TT.icon('plus'), 'Add location'), i < 2 ? h('span', {class:'tiny muted', style:{marginTop:'8px'}}, 'At least two are needed') : null));
        continue;
      }
      const im = r.images[0], cv = im ? h('img', {src:im.url, alt:im.caption || 'Image of ' + r.name, title:'Credit: ' + (im.credit || 'not recorded') + ' · License: ' + (im.license || 'not recorded'), style:{width:'100%', height:'120px', objectFit:'cover', display:'block'}}) : h('canvas', {'aria-hidden':'true'});
      const s = h('div', {class:'slot filled'}, cv, h('div', {class:'in'},
        h('a', {href:'#location-' + r.id, style:{fontFamily:'var(--f-head)', fontWeight:600, color:'var(--text)'}}, r.name),
        h('div', {style:{display:'flex', gap:'6px', flexWrap:'wrap'}}, TT.bodyChip(r.body), TT.kindChip(r.kind)),
        h('div', {class:'mono tiny muted'}, TT.fmtCoord(r.lat, r.lon, 2)),
        h('div', {style:{marginTop:'auto'}}, h('button', {class:'btn sm ghost', onclick: () => { CMP.remove(r.id); render(); }}, 'Remove'))));
      slots.appendChild(s);
      if (!im) requestAnimationFrame(() => TT.contextMap(cv, r, {interactive:false}).then(m => m && maps.push(m)));
    }
    page.appendChild(slots);
    if (recs.length < 2){
      page.appendChild(h('div', {class:'card'}, h('p', {style:{margin:0}}, 'Add at least two locations to see the comparison. You can also add locations from the Explore page.'), h('div', {style:{display:'flex', gap:'10px', marginTop:'12px', flexWrap:'wrap'}},
        h('a', {class:'btn primary', href:'#explore'}, 'Open Explore'), h('button', {class:'btn', onclick: () => { const ex = ['earth-mcmurdo-dry-valleys', 'mars-deuteronilus-mensae']; ex.forEach(id => S.get(id) && CMP.add(id)); render(); }}, 'Try an example: McMurdo vs Deuteronilus'))));
      return;
    }
    /* table */
    const plist = TT.paramList(recs), hasData = p => recs.some(r => TT.paramText(TT.paramOf(r, p.key)));
    const groups = {}, nodata = []; plist.forEach(p => { if (hasData(p)) (groups[p.group] = groups[p.group] || []).push(p); else nodata.push(p.label); });
    const thead = h('tr', null, h('th', null, 'Parameter'), recs.map(r => h('th', null, r.name)));
    const tb = h('tbody');
    const cell = (r, p) => { const x = TT.paramOf(r, p.key), t = TT.paramText(x);
      return h('td', null, t ? h('div', {class:'val'}, t) : h('div', {class:'na'}, 'Not available'),
        h('div', {style:{marginTop:'3px', display:'flex', gap:'6px', flexWrap:'wrap', alignItems:'center'}}, TT.badge(x.status), x.unc ? h('span', {class:'tiny muted'}, x.unc) : null),
        x.note && x.status !== 'unavailable' ? h('div', {class:'tiny muted', style:{marginTop:'3px'}}, x.note) : null); };
    tb.appendChild(h('tr', null, h('td', null, 'Body'), recs.map(r => h('td', null, TT.bodyChip(r.body)))));
    tb.appendChild(h('tr', null, h('td', null, 'Marker type'), recs.map(r => h('td', null, TT.kindChip(r.kind)))));
    tb.appendChild(h('tr', null, h('td', null, 'Terrain class'), recs.map(r => h('td', null, r.terrain || h('span', {class:'na'}, 'Not available')))));
    tb.appendChild(h('tr', null, h('td', null, 'Coordinates'), recs.map(r => h('td', {class:'val'}, TT.fmtCoord(r.lat, r.lon, 3)))));
    Object.keys(groups).forEach(g => { tb.appendChild(h('tr', {class:'grp'}, h('td', {colspan: recs.length + 1}, g))); groups[g].forEach(p => tb.appendChild(h('tr', null, h('td', null, p.label, p.unit ? h('span', {class:'muted'}, ' (' + p.unit + ')') : null), recs.map(r => cell(r, p))))); });
    tb.appendChild(h('tr', {class:'grp'}, h('td', {colspan: recs.length + 1}, 'Provenance')));
    tb.appendChild(h('tr', null, h('td', null, 'Sources'), recs.map(r => h('td', {class:'small'}, TT.recordSources(r).slice(0, 4).map(s => h('div', null, s.publisher.split(',')[0] + (s.year ? ' ' + s.year : '')))))));
    tb.appendChild(h('tr', null, h('td', null, 'Last updated'), recs.map(r => h('td', {class:'val'}, r.updated || 'Unknown'))));
    page.appendChild(h('div', {class:'sec'}, h('h2', null, 'Side by side'), h('div', {class:'cmp-scroll'}, h('table', {class:'t'}, h('thead', null, thead), tb)),
      nodata.length ? h('p', {class:'small na', style:{marginTop:'10px'}}, 'No data for any selected location: ' + nodata.join(', ') + '.') : null));

    /* charts */
    const charts = h('div', {class:'sec'}, h('h2', null, 'Charts'), h('p', {class:'muted small'}, 'Bars are coloured by body and always labelled with their value. Locations with no scored value are listed as not available rather than drawn as zero.'));
    plist.filter(p => p.num).forEach(p => {
      if (recs.some(r => TT.scorable(TT.paramOf(r, p.key)))) charts.appendChild(barChart(p, recs));
    });
    page.appendChild(charts);

    /* agreement */
    const ref = recs[0];
    const ag = h('div', {class:'sec'}, h('h2', null, 'Parameter agreement'),
      h('p', {class:'muted small', style:{maxWidth:'70ch'}}, 'This counts how many shared numeric parameters fall inside a stated tolerance of ' + ref.name + '. It is not a similarity percentage and says nothing about parameters that are unavailable. ',
        h('a', {href:'#about', onclick: () => { TT.scrollTo = 'method'; }}, 'How it works')),
      h('button', {class:'btn sm', 'aria-expanded': weightsOpen.v, onclick: () => { weightsOpen.v = !weightsOpen.v; render(); }}, weightsOpen.v ? 'Hide weights' : 'Adjust weights'));
    if (weightsOpen.v){
      const box = h('div', {class:'card', style:{margin:'12px 0', display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(220px,1fr))', gap:'12px'}});
      TT.Cmp.rules.forEach(r => { const id = 'w-' + r.key; box.appendChild(h('div', null, h('label', {class:'f', for:id}, r.label + ': weight ' + TT.Cmp.weight(r.key)),
        h('input', {id, type:'range', min:'0', max:'3', step:'1', value:TT.Cmp.weight(r.key), style:{width:'100%', accentColor:'var(--accent)'}, onchange: e => { TT.Cmp.setWeight(r.key, +e.target.value); render(); }}),
        h('div', {class:'hint'}, r.rule === 'ratio' ? 'Agrees within a factor of ' + r.tol : 'Agrees within ' + r.tol + ' ' + r.unit))); });
      ag.appendChild(box);
    }
    recs.slice(1).forEach(o => {
      const res = TT.Cmp.pair(ref, o);
      const head = res.comparable < 2 || res.weightTotal === 0
        ? h('b', null, 'Not enough shared data to score ' + o.name + ' against ' + ref.name + ' (' + res.comparable + ' comparable parameter' + (res.comparable === 1 ? '' : 's') + ').')
        : h('b', null, o.name + ': ' + res.agreeing + ' of ' + res.comparable + ' scored parameters agree (weight ' + res.weightAgree + ' of ' + res.weightTotal + ').');
      const t = h('table', {class:'t', style:{marginTop:'8px'}}, h('thead', null, h('tr', null, h('th', null, 'Parameter'), h('th', null, ref.name), h('th', null, o.name), h('th', null, 'Result'))),
        h('tbody', null, res.rows.map(row => h('tr', null, h('td', null, row.rule.label, h('span', {class:'tiny muted'}, ' weight ' + row.w)),
          h('td', {class:'val'}, TT.paramText(row.pa) || h('span', {class:'na'}, 'n/a')), h('td', {class:'val'}, TT.paramText(row.pb) || h('span', {class:'na'}, 'n/a')),
          row.agree == null ? h('td', {class:'small muted'}, row.state) : h('td', {class:'small ' + (row.agree ? 'ok' : 'no')}, (row.agree ? 'Agrees: ' : 'Differs: ') + row.detail)))));
      ag.appendChild(h('div', {class:'agree'}, head, t));
    });
    page.appendChild(ag);
    /* body context */
    const ctx = [...new Set(recs.map(r => r.body))];
    page.appendChild(h('div', {class:'sec'}, h('h2', null, 'Body context'), h('div', {class:'cmp-scroll'}, h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, ''), ctx.map(b => h('th', null, TT.BODIES[b].name)))),
      h('tbody', null, h('tr', null, h('td', null, 'Surface gravity'), ctx.map(b => h('td', {class:'val'}, TT.BODIES[b].gravity + ' m/s²'))),
        h('tr', null, h('td', null, 'Mean radius'), ctx.map(b => h('td', {class:'val'}, TT.fmtNum(TT.BODIES[b].radius_km) + ' km'))),
        h('tr', null, h('td', null, 'Global mean temperature'), ctx.map(b => { const t = TT.BODIES[b].mean_temp_c; return t == null ? h('td', {class:'na'}, 'Not a single value: swings with day, night and latitude') : h('td', {class:'val'}, t + ' °C'); }))))),
      h('p', {class:'tiny muted'}, 'Body constants: NASA Planetary Fact Sheets (not re-fetched during this build). These describe the whole body, not the locations above.')));
  }
  render();
  return {destroy(){ maps.forEach(m => m.dispose()); }, refresh: render};
};
})();
