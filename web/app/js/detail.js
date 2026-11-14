/* Planalogy — location detail page and the small context maps used by Compare and Detail. */
(function(){
const TT = window.TT, h = TT.h;

/* small map for a single location: polar view near the poles (flat maps stretch badly there), flat map elsewhere */
TT.contextMap = function(canvas, r, o){
  o = o || {};
  const polar = Math.abs(r.lat) >= 70;
  const m = TT.createMap2D(canvas, {body:r.body, interactive:o.interactive !== false, projection:polar ? (r.lat < 0 ? 'polar-s' : 'polar-n') : 'equi', ext:30, minPx:o.minPx || 22, onPick:o.onPick});
  m.setMarkers([{id:r.id, kind:r.kind, lat:r.lat, lon:r.lon, body:r.body, name:r.name}].concat(o.extra || []));
  m.setSelection(r.id, []);
  requestAnimationFrame(() => { m.resize(); if (polar) m.resetView(); else m.focus(r.lat, r.lon, {span:o.span || 36, dur:0}); });
  m.polar = polar;
  return Promise.resolve(m);
};

TT.pages.detail = function(root, route){
  const S = TT.Store;
  let g = null, m = null, last = '';
  const host = h('div'); root.appendChild(host);

  function find(){ return S.get(route.id) || (S.canWrite ? S.getAny(route.id) : null); }
  function dispose(){ g && g.dispose(); m && m.dispose(); g = m = null; }

  function render(){
    dispose(); TT.clear(host);
    const r = find(); last = JSON.stringify(r) + TT.Compare.ids.join();
    if (!r){
      host.appendChild(h('div', {class:'wrap page'}, h('h1', null, S.dbReady || S.mode === 'seed' ? 'Location not found' : 'Loading…'),
        h('p', {class:'lede'}, 'There is no published location with the address “' + route.id + '”. It may have been unpublished or renamed.'),
        h('div', {style:{display:'flex', gap:'10px', flexWrap:'wrap', marginTop:'14px'}}, h('a', {class:'btn primary', href:'#explore'}, 'Open Explore'), h('a', {class:'btn', href:'#compare'}, 'Compare'))));
      return;
    }
    const isDraft = !S.get(r.id);
    const srcs = TT.recordSources(r);
    const refIdx = id => srcs.findIndex(s => s.id === id) + 1;
    const ref = id => { const n = refIdx(id); return n ? h('sup', {class:'ref'}, h('button', {class:'ref', type:'button', 'aria-label':'Source ' + n, onclick: () => { const t = document.getElementById('src-' + n); t && (t.scrollIntoView({behavior:TT.reduced() ? 'auto' : 'smooth', block:'center'}), t.focus()); }}, '[' + n + ']')) : null; };

    /* header */
    host.appendChild(h('section', {class:'dhead'}, h('div', {class:'wrap'},
      h('div', {class:'crumbs'}, h('a', {href:'#explore-' + r.body}, 'Explore'), ' / ', TT.BODIES[r.body].name, ' / ', r.name),
      h('h1', null, r.name),
      h('div', {style:{display:'flex', gap:'8px', flexWrap:'wrap', margin:'12px 0 8px'}}, TT.bodyChip(r.body), TT.kindChip(r.kind), r.terrain ? h('span', {class:'chip'}, r.terrain) : null,
        h('span', {class:'badge ' + (r.verification === 'reviewed' ? 'measured' : 'sample'), title:r.verification === 'reviewed' ? 'Reviewed by a domain expert' : 'Compiled from cited public sources, not expert-reviewed'}, r.verification === 'reviewed' ? 'reviewed' : 'sample data'),
        isDraft ? h('span', {class:'badge draft'}, 'draft: not public') : null),
      r.status_label ? h('p', {class:'lede', style:{margin:0}}, r.status_label) : null)));

    const main = h('div'), side = h('div', {class:'side'});
    host.appendChild(h('div', {class:'wrap dgrid'}, main, side));
    if (isDraft) main.appendChild(h('div', {class:'notice info'}, TT.icon('info'), h('span', null, 'Preview of an unpublished draft. Visitors cannot see this page until it is published.')));

    /* overview */
    const text = (title, t, empty) => h('section', {class:'sec'}, h('h2', null, title), t ? h('p', {style:{maxWidth:'70ch', color:'#d5dcea'}}, t) : h('p', {class:'na'}, empty || 'Not available: no text has been written for this section.'));
    main.appendChild(text('Overview', r.summary, 'Not available: no summary has been written yet.'));

    /* identity + parameters */
    const kv = h('dl', {class:'kv plain', style:{maxWidth:'520px', gridTemplateColumns:'150px 1fr'}});
    [['Body', TT.BODIES[r.body].name], ['Region', r.region || null], ['Terrain class', r.terrain || null], ['Latitude', TT.fmtLat(r.lat, 4)], ['Longitude', TT.fmtLon(r.lon, 4)], ['Marker type', TT.KINDS[r.kind].label]].forEach(([k, v]) => { kv.appendChild(h('dt', null, k)); kv.appendChild(h('dd', {class:'val'}, v || h('span', {class:'na'}, 'Not available'))); });
    const pt = h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, 'Parameter'), h('th', null, 'Value'), h('th', null, 'Status'), h('th', null, 'Source and date'))), h('tbody'));
    TT.paramList([r]).forEach(p => {
      const x = TT.paramOf(r, p.key), t = TT.paramText(x);
      pt.lastChild.appendChild(h('tr', null,
        h('td', null, p.label, p.unit && !t ? h('span', {class:'muted'}, ' (' + p.unit + ')') : null),
        h('td', null, t ? h('span', {class:'val'}, t) : h('span', {class:'na'}, 'Not available'), x.unc ? h('div', {class:'tiny muted'}, 'Uncertainty: ' + x.unc) : null, x.note ? h('div', {class:'tiny muted', style:{maxWidth:'44ch'}}, x.note) : null),
        h('td', null, TT.badge(x.status)),
        h('td', {class:'small'}, x.src ? [(TT.source(r, x.src) || {}).publisher || x.src, ' ', ref(x.src)] : (x.status === 'derived' && p.derived ? 'Computed here' : h('span', {class:'na'}, '—')), x.date ? h('div', {class:'tiny muted mono'}, x.date) : null)));
    });
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Key facts'),
      h('div', {class:'legend'}, h('span', null, TT.badge('measured'), ' reported by a cited source'), h('span', null, TT.badge('derived'), ' computed or inferred'), h('span', null, TT.badge('unavailable'), ' not in this dataset, never estimated')),
      kv, h('div', {class:'cmp-scroll', style:{marginTop:'16px'}}, pt)));
    main.appendChild(text('Geology', r.geology));
    main.appendChild(text('Environment', r.environment));
    main.appendChild(text(r.body === 'earth' ? 'Relevance as an analog' : 'Relevance to exploration', r.relevance));

    /* related */
    const rel = TT.related(r);
    const relSec = h('section', {class:'sec'}, h('h2', null, rel.label));
    if (rel.items.length){
      rel.items.forEach(x => relSec.appendChild(h('div', {class:'relrow', style:{maxWidth:'640px'}}, TT.markerIcon(x.kind, 14), h('span', {class:'grow'}, h('a', {href:'#location-' + x.id, style:{fontWeight:600}}, x.name), h('span', {class:'tiny muted', style:{display:'block'}}, TT.BODIES[x.body].name + ' · ' + (x.region || TT.KINDS[x.kind].label))),
        h('button', {class:'btn sm', type:'button', onclick: () => { if (TT.Compare.add(r.id) && TT.Compare.add(x.id)){ location.hash = '#compare'; } }}, TT.icon('compare'), 'Compare both'))));
      if (r.kind === 'analog') relSec.appendChild(h('p', {class:'small muted', style:{maxWidth:'70ch'}}, h('b', null, 'Why these links: '), r.rationale || 'No rationale has been recorded.'));
      relSec.appendChild(h('p', {class:'tiny muted'}, 'Links are editorial inferences drawn from the cited sources. They are not measured matches and carry no similarity score. Use Compare to see which parameters actually agree.'));
    } else relSec.appendChild(h('p', {class:'na'}, 'No links recorded yet.'));
    main.appendChild(relSec);

    /* images */
    const gal = h('div', {style:{display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(240px,1fr))', gap:'14px'}});
    r.images.forEach(im => gal.appendChild(h('figure', {style:{margin:0}}, h('img', {src:im.url, alt:im.caption || 'Image of ' + r.name, loading:'lazy', style:{width:'100%', aspectRatio:'4/3', objectFit:'cover', borderRadius:'10px', background:'#050913', border:'1px solid var(--line)'}}),
      h('figcaption', {class:'tiny muted', style:{marginTop:'6px'}}, im.caption || '', h('div', null, 'Credit: ' + (im.credit || 'not recorded') + ' · License: ' + (im.license || 'not recorded'))))));
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Images'),
      r.images.length ? gal : h('p', {class:'na'}, 'No site images have been added for this location. The globe and map beside this text use a global base map, which cannot show local terrain.')));

    /* sources */
    const ol = h('ol', {class:'src-list'});
    srcs.forEach((s, i) => ol.appendChild(h('li', {id:'src-' + (i + 1), tabindex:'-1'}, s.url ? h('a', {href:s.url, target:'_blank', rel:'noopener noreferrer'}, s.title) : s.title, h('span', {class:'muted'}, ' — ' + [s.publisher, s.year].filter(Boolean).join(', ')), s.note ? h('div', {class:'tiny muted'}, s.note) : null)));
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Sources'), srcs.length ? ol : h('p', {class:'na'}, 'No sources are recorded for this location.'),
      h('p', {class:'tiny muted', style:{marginTop:'14px'}}, 'Last updated ' + (r.updated || 'unknown') + '. ' + (r.verification === 'reviewed' ? 'Reviewed by a domain expert.' : 'Compiled from the sources above by the Planalogy team; not expert-reviewed. Check the sources before relying on any figure.'))));

    /* side: globe / map */
    const extra = rel.items.filter(x => x.body === r.body).map(x => ({id:x.id, kind:x.kind, lat:x.lat, lon:x.lon, body:x.body, name:x.name}));
    const all = [{id:r.id, kind:r.kind, lat:r.lat, lon:r.lon, body:r.body, name:r.name}].concat(extra);
    const cvG = h('canvas', {'aria-label':'3D globe centred on ' + r.name}), cvM = h('canvas', {'aria-label':'Map of ' + r.name, style:{display:'none'}});
    const cap = h('div', {class:'cap'});
    const seg = h('div', {class:'seg tabs', role:'radiogroup', 'aria-label':'View'});
    const go = id => { if (id !== r.id) location.hash = '#location-' + id; };
    function show(which){
      [...seg.children].forEach(b => b.setAttribute('aria-checked', b.dataset.v === which));
      cvG.style.display = which === 'g' ? '' : 'none'; cvM.style.display = which === 'm' ? '' : 'none';
      if (which === 'g' && g){ requestAnimationFrame(() => g.resize()); cap.textContent = 'Globe on a global base map (' + TT.BODIES[r.body].tex.split(' — ')[0] + '). Drag to rotate; markers are clickable.'; }
      if (which === 'm'){
        if (!m) TT.contextMap(cvM, r, {extra, onPick:it => go(it.id)}).then(x => { m = x; requestAnimationFrame(() => { m.resize(); }); });
        cap.textContent = Math.abs(r.lat) >= 70 ? 'Polar map: 60° to the pole, azimuthal equidistant, so distance from the pole is true. Global base map, low resolution.' : 'Flat map (equirectangular), centred on the site. Global base map, low resolution.';
      }
    }
    if (TT.webgl) seg.appendChild(h('button', {type:'button', role:'radio', dataset:{v:'g'}, onclick: () => show('g')}, 'Globe'));
    seg.appendChild(h('button', {type:'button', role:'radio', dataset:{v:'m'}, onclick: () => show('m')}, 'Map'));
    side.appendChild(h('div', {class:'mini'}, seg, cvG, cvM, cap));
    if (TT.webgl){
      g = TT.createGlobe(cvG, {body:r.body, dist:2.3, markerPx:26, onPick:it => go(it.id)});
      if (g){ g.setMarkers(all); g.setSelection(r.id, extra.map(x => x.id)); g.focus(r.lat, r.lon, {dist:2.1, dur:0}); }
    }
    show(g ? 'g' : 'm');
    if (!g) seg.hidden = true;

    const cmpBtn = h('button', {class:'btn', type:'button', 'aria-pressed':TT.Compare.has(r.id), onclick: e => { TT.Compare.toggle(r.id); const on = TT.Compare.has(r.id); e.currentTarget.setAttribute('aria-pressed', on); e.currentTarget.lastChild.textContent = on ? 'In comparison' : 'Add to compare'; last = JSON.stringify(r) + TT.Compare.ids.join(); }}, TT.icon('compare'), h('span', null, TT.Compare.has(r.id) ? 'In comparison' : 'Add to compare'));
    side.appendChild(h('div', {style:{display:'flex', gap:'10px', flexWrap:'wrap'}},
      h('a', {class:'btn primary', href:'#explore-' + r.body, onclick: () => { TT.pending = {select:r.id}; }}, TT.icon('globe'), 'Open in Explore'), cmpBtn,
      h('button', {class:'btn', type:'button', onclick: () => { const t = r.lat.toFixed(5) + ', ' + r.lon.toFixed(5); (navigator.clipboard && navigator.clipboard.writeText(t).then(() => TT.toast('Coordinates copied'), () => TT.toast(t))) || TT.toast(t); }}, TT.icon('copy'), 'Copy coordinates')));
    if (TT.Compare.ids.length > 1) side.appendChild(h('a', {class:'btn ghost sm', href:'#compare'}, 'Open comparison (' + TT.Compare.ids.length + ')'));
  }
  render();
  return {destroy: dispose, refresh(){ const r = find(); if (JSON.stringify(r) + TT.Compare.ids.join() !== last) render(); }};
};
})();
