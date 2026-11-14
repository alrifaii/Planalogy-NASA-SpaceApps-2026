/* Planalogy — admin area. Access is limited to the artifact owner and editors (db mode) or runs as an in-browser sandbox. */
(function(){
const TT = window.TT, h = TT.h;
const clone = o => JSON.parse(JSON.stringify(o));
const ASSET_KINDS = ['Surface image', 'Satellite image', 'Terrain image', '3D texture', 'Elevation map', 'Other'];
const LICENSES = ['Public domain (NASA / US Government)', 'CC0 1.0', 'CC BY 4.0', 'CC BY-SA 4.0', 'Used with permission', 'Other (explain in credit)'];
const defsOf = params => TT.PARAMS.filter(p => !p.derived).concat(Object.keys(params || {}).filter(k => !TT.PARAM[k]).map(k => ({key:k, label:params[k].label || k.replace(/_/g, ' '), unit:params[k].unit || '', num:params[k].num != null ? !!params[k].num : typeof params[k].v === 'number', custom:true})));
const QUAL = [['', 'exactly'], ['~', 'about (~)'], ['<', 'less than (<)'], ['>', 'more than (>)']];

TT.pages.admin = function(root, route){
  const S = TT.Store, C = TT.Caps;
  const shell = h('div'); root.appendChild(shell);
  const st = {edit:null, dirty:false, q:'', body:'', state:''};
  let previewMap = null, previewTimer = 0, errs = {};

  const mode = () => C.db ? (C.canEdit ? 'db' : 'denied') : (S.mode === 'sandbox' ? 'sandbox' : 'offer');
  const allSources = () => {
    const m = new Map(Object.entries((window.TT_SEED && window.TT_SEED.sources) || {}));
    const add = r => Object.keys(r.srcdefs || {}).forEach(k => m.set(k, r.srcdefs[k]));
    S.all().forEach(add); S.drafts.forEach(add); return m;
  };
  const cites = id => { const n = new Set(); [...S.all(), ...S.drafts.values()].forEach(r => { if ((r.sources || []).indexOf(id) >= 0 || Object.values(r.params || {}).some(p => p.src === id)) n.add(r.id); }); return n.size; };

  function render(){
    if (previewMap){ previewMap.dispose(); previewMap = null; }
    TT.clear(shell);
    if (!C.ready){ shell.appendChild(h('div', {class:'login'}, h('div', {class:'card'}, h('p', {style:{display:'flex', gap:'10px', alignItems:'center', margin:0}}, h('span', {class:'spin'}), 'Checking your access…')))); return; }
    const m = mode();
    if (m === 'denied'){
      shell.appendChild(h('div', {class:'login'}, h('div', {class:'card'}, h('h1', {style:{fontSize:'1.6rem'}}, 'Admin is restricted'),
        h('p', {class:'muted'}, 'You are signed in, but your account cannot edit this site. Only the owner and editors can open the admin area.'),
        h('p', {class:'small muted'}, 'Sign-in and sign-out are handled by your Claude account, not by this page. Ask the site owner to add you as an editor.'),
        h('div', {style:{display:'flex', gap:'10px', flexWrap:'wrap'}}, h('a', {class:'btn primary', href:'#'}, 'Back to the site'), h('a', {class:'btn', href:'#explore'}, 'Open Explore')))));
      return;
    }
    if (m === 'offer'){
      shell.appendChild(h('div', {class:'login'}, h('div', {class:'card'}, h('h1', {style:{fontSize:'1.6rem'}}, 'Admin sign-in'),
        h('div', {class:'notice', style:{marginTop:'14px'}}, TT.icon('info'), h('span', null, 'No shared database is connected to this view, so changes cannot reach the public site. This is a mockup of the admin area that keeps everything in your own browser.')),
        h('p', {class:'muted small'}, 'In the live version, only the site owner and invited editors can sign in, and published changes appear for every visitor without a code change.'),
        h('div', {style:{display:'flex', gap:'10px', flexWrap:'wrap', marginTop:'8px'}}, h('button', {class:'btn primary', type:'button', onclick: () => { S.enableSandbox(); }}, 'Open sandbox admin'), h('a', {class:'btn', href:'#'}, 'Back to the site')))));
      return;
    }
    const nav = [['dashboard', 'dash', 'Dashboard', '#admin'], ['locations', 'list', 'Locations', '#admin-locations'], ['assets', 'image', 'Images and files', '#admin-assets'], ['sources', 'book', 'Sources', '#admin-sources']];
    const aside = h('aside', {'aria-label':'Admin sections'}, nav.map(n => h('a', {href:n[3], 'aria-current':route.sub === n[0] ? 'page' : null}, TT.icon(n[1]), n[2])),
      h('hr', {style:{border:0, borderTop:'1px solid var(--line)', margin:'12px 0', width:'100%'}}), h('a', {href:'#'}, TT.icon('out'), 'Leave admin'),
      h('p', {class:'tiny muted', style:{padding:'8px 12px'}}, 'Role: ' + (m === 'sandbox' ? 'sandbox visitor' : C.isOwner ? 'owner' : 'editor')));
    const main = h('main', {id:'admin-main'});
    shell.appendChild(h('div', {class:'adm'}, aside, main));
    main.appendChild(m === 'sandbox'
      ? h('div', {class:'notice'}, TT.icon('info'), h('span', null, h('b', null, 'Sandbox. '), 'Changes are saved in this browser only and do not update the public site. Nothing here is a real backend.'))
      : h('div', {class:'notice info'}, TT.icon('check'), h('span', null, 'Connected to the shared database. Published changes appear on the public site straight away.')));
    if (S.error) main.appendChild(h('div', {class:'notice bad'}, TT.icon('info'), h('span', null, S.error)));
    if (TT.adminIntent && !st.edit){ const it = TT.adminIntent; TT.adminIntent = null; if (it.neu) startNew(); else if (it.edit) startEdit(it.edit); }
    if (st.edit) editor(main);
    else if (route.sub === 'locations') locations(main);
    else if (route.sub === 'assets') assets(main);
    else if (route.sub === 'sources') sources(main);
    else dashboard(main);
  }

  /* ---------- dashboard ---------- */
  function dashboard(main){
    const pub = S.all(), missing = r => TT.PARAMS.filter(p => !p.derived && TT.paramOf(r, p.key).status === 'unavailable').length;
    const stat = (n, l) => h('div', {class:'stat'}, h('b', null, n), h('span', null, l));
    const upd = pub.map(r => r.updated).filter(Boolean).sort().pop();
    main.append(h('h1', null, 'Dashboard'), h('p', {class:'muted'}, 'What is on the public site, and what still needs work.'),
      h('div', {class:'stats'}, stat(pub.length, 'Published locations'), stat(S.drafts.size, 'Drafts and pending changes'), TT.BODY_ORDER.map(b => stat(S.byBody(b).length, TT.BODIES[b].name + ' locations')), stat(pub.filter(r => r.kind === 'analog').length, 'Earth analogs'), stat(S.assets.size, 'Library images'), h('div', {class:'stat'}, h('b', {style:{fontSize:'1.15rem', lineHeight:'2.1rem'}}, upd || '—'), h('span', null, 'Latest update'))));
    main.appendChild(h('div', {style:{display:'flex', gap:'10px', flexWrap:'wrap', margin:'4px 0 26px'}}, h('button', {class:'btn primary', type:'button', onclick: () => { TT.adminIntent = {neu:true}; location.hash = '#admin-locations'; }}, TT.icon('plus'), 'New location'), h('a', {class:'btn', href:'#explore'}, 'View public site')));
    const need = pub.map(r => ({r, m:missing(r), noimg:!r.images.length, nosrc:!TT.recordSources(r).length})).filter(x => x.m || x.noimg || x.nosrc).sort((a, b) => b.m - a.m).slice(0, 8);
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Needs attention'), h('div', {class:'cmp-scroll'}, h('table', {class:'t'}, h('thead', null, h('tr', null, ['Location', 'Missing values', 'Images', 'Sources', ''].map(t => h('th', null, t)))),
      h('tbody', null, need.map(x => h('tr', null, h('td', null, x.r.name), h('td', {class:'val'}, x.m + ' of ' + TT.PARAMS.filter(p => !p.derived).length), h('td', null, x.noimg ? 'none' : x.r.images.length), h('td', null, x.nosrc ? 'none' : TT.recordSources(x.r).length), h('td', null, h('button', {class:'btn sm', type:'button', onclick: () => { TT.adminIntent = {edit:x.r.id}; location.hash = '#admin-locations'; }}, 'Edit')))))))));
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Recently changed'), h('table', {class:'t'}, h('tbody', null, S.adminList().slice(0, 6).map(x => h('tr', null, h('td', null, x.rec.name), h('td', null, TT.bodyChip(x.rec.body)), h('td', null, stateBadge(x.state)), h('td', {class:'val'}, x.rec.updated || '—')))))));
  }
  const stateBadge = s => h('span', {class:'badge ' + (s === 'published' ? 'measured' : 'draft')}, s === 'published' ? 'published' : s === 'changes' ? 'unpublished changes' : 'draft');

  /* ---------- locations list ---------- */
  function locations(main){
    main.appendChild(h('div', {style:{display:'flex', justifyContent:'space-between', gap:'12px', alignItems:'center', flexWrap:'wrap'}}, h('div', null, h('h1', null, 'Locations'), h('p', {class:'muted', style:{margin:0}}, 'Create, edit, publish or remove places.')), h('button', {class:'btn primary', type:'button', onclick: newLoc}, TT.icon('plus'), 'New location')));
    const q = h('input', {class:'input', type:'search', placeholder:'Filter by name or region', 'aria-label':'Filter locations', value:st.q, oninput: e => { st.q = e.target.value; drawRows(); }});
    const bs = h('select', {class:'input', 'aria-label':'Filter by body', onchange: e => { st.body = e.target.value; drawRows(); }}, h('option', {value:''}, 'All bodies'), TT.BODY_ORDER.map(b => h('option', {value:b, selected:st.body === b}, TT.BODIES[b].name)));
    const ss = h('select', {class:'input', 'aria-label':'Filter by state', onchange: e => { st.state = e.target.value; drawRows(); }}, [['', 'All states'], ['published', 'Published'], ['changes', 'Unpublished changes'], ['draft', 'Draft only']].map(o => h('option', {value:o[0], selected:st.state === o[0]}, o[1])));
    main.appendChild(h('div', {class:'row3', style:{margin:'16px 0'}}, q, bs, ss));
    const tb = h('tbody');
    main.appendChild(h('div', {class:'cmp-scroll'}, h('table', {class:'t'}, h('thead', null, h('tr', null, ['Name', 'Body', 'Type', 'State', 'Updated', 'Actions'].map(t => h('th', null, t)))), tb)));
    function drawRows(){
      TT.clear(tb); const t = st.q.trim().toLowerCase();
      const rows = S.adminList().filter(x => (!st.body || x.rec.body === st.body) && (!st.state || x.state === st.state) && (!t || (x.rec.name + ' ' + x.rec.region).toLowerCase().indexOf(t) >= 0));
      rows.forEach(x => { const r = x.rec, id = r.id;
        tb.appendChild(h('tr', null, h('td', null, h('b', null, r.name), h('div', {class:'tiny muted mono'}, id)), h('td', null, TT.bodyChip(r.body)), h('td', null, TT.kindChip(r.kind)), h('td', null, stateBadge(x.state)), h('td', {class:'val'}, r.updated || '—'),
          h('td', null, h('div', {style:{display:'flex', gap:'6px', flexWrap:'wrap'}},
            h('button', {class:'btn sm', type:'button', onclick: () => openEdit(id)}, TT.icon('edit'), 'Edit'),
            h('a', {class:'btn sm ghost', href:'#location-' + id, 'aria-label':'Preview ' + r.name}, TT.icon('eye'), 'Preview'),
            x.state !== 'published' ? h('button', {class:'btn sm', type:'button', onclick: () => doPublish(r)}, 'Publish') : null,
            x.live ? h('button', {class:'btn sm', type:'button', onclick: () => doUnpublish(r)}, 'Unpublish') : null,
            h('button', {class:'btn sm danger', type:'button', 'aria-label':'Delete ' + r.name, onclick: () => doDelete(r, x)}, TT.icon('trash'))))));
      });
      if (!rows.length) tb.appendChild(h('tr', null, h('td', {colspan:6, class:'muted'}, 'No locations match.')));
    }
    drawRows();
  }
  const guard = async fn => { try { await fn(); } catch(e){ console.error(e); TT.toast('Could not save: ' + (e && e.message || 'unknown error'), true); } };
  async function doPublish(r){
    const errs = validate(r, true); if (Object.keys(errs).length){ TT.toast('This record has problems and cannot be published. Open it to see them.', true); return; }
    if (await TT.confirm({title:'Publish “' + r.name + '”?', body:'It becomes visible to every visitor of the public site' + (S.mode === 'sandbox' ? ' (in this sandbox, only in your browser)' : '') + '.', ok:'Publish'})) guard(async () => { await S.publish(r); TT.toast('Published'); });
  }
  async function doUnpublish(r){ if (await TT.confirm({title:'Unpublish “' + r.name + '”?', body:'Visitors will no longer see it. A draft copy is kept so you can publish it again.', ok:'Unpublish'})) guard(async () => { await S.unpublish(r.id); TT.toast('Unpublished. A draft copy was kept.'); }); }
  async function doDelete(r, x){ if (await TT.confirm({title:'Delete “' + r.name + '”?', body:'This removes the location' + (x.live ? ' from the public site' : '') + (S.isSeed(r.id) ? ' (it is one of the built-in sample records, so it is hidden rather than erased)' : '') + ' and any draft. This cannot be undone.', ok:'Delete', danger:true})) guard(async () => { await S.remove(r.id); TT.toast('Deleted'); }); }

  /* ---------- editor ---------- */
  function blank(){
    const params = {}; TT.PARAMS.filter(p => !p.derived).forEach(p => params[p.key] = {v:null, unit:p.unit, status:'unavailable', src:'', date:'', unc:'', note:'', q:'', range:null});
    return {id:'', name:'', body:'moon', kind:'landing', status_label:'', region:'', terrain:'', lat:null, lon:null, summary:'', geology:'', environment:'', relevance:'', rationale:'', params, tags:[], analog_for:[], sources:[], srcdefs:{}, images:[], verification:'sample', published:false, updated:''};
  }
  function startNew(){ st.edit = blank(); st.edit._new = true; st.edit._lat = ''; st.edit._lon = ''; st.dirty = false; errs = {}; }
  function newLoc(){ startNew(); render(); window.scrollTo(0, 0); }
  function openEdit(id){ if (startEdit(id)){ render(); window.scrollTo(0, 0); } }
  function startEdit(id){
    const r = S.getAny(id); if (!r) return false;
    const e = clone(r); TT.PARAMS.filter(p => !p.derived).forEach(p => { if (!e.params[p.key]) e.params[p.key] = {v:null, unit:p.unit, status:'unavailable', src:'', date:'', unc:'', note:'', q:'', range:null}; e.params[p.key]._raw = typeof e.params[p.key].v === 'number' ? String(e.params[p.key].v) : (e.params[p.key].v || ''); });
    Object.keys(e.params).filter(k => !TT.PARAM[k]).forEach(k => { const x = e.params[k]; x._raw = typeof x.v === 'number' ? String(x.v) : (x.v || ''); });
    e._lat = String(e.lat); e._lon = String(e.lon); st.edit = e; st.dirty = false; errs = {}; return true;
  }
  function build(e){
    const num = v => { const n = Number(String(v).trim()); return String(v).trim() !== '' && isFinite(n) ? n : null; };
    const out = {id:e.id, name:e.name.trim(), body:e.body, kind:e.kind, status_label:e.status_label.trim(), region:e.region.trim(), terrain:e.terrain.trim(), lat:num(e._lat), lon:num(e._lon), summary:e.summary.trim(), geology:e.geology.trim(), environment:e.environment.trim(), relevance:e.relevance.trim(), rationale:e.rationale.trim(),
      tags:e.tags, analog_for:e.kind === 'analog' ? e.analog_for : [], sources:e.sources, srcdefs:{}, images:e.images, verification:e.verification, params:{}};
    e.sources.forEach(id => { if (e.srcdefs[id]) out.srcdefs[id] = e.srcdefs[id]; });
    defsOf(e.params).forEach(p => {
      const x = e.params[p.key]; if (!x) return; const raw = (x._raw == null ? '' : String(x._raw)).trim();
      let v = null; if (x.status !== 'unavailable' && raw !== ''){ v = p.num ? num(raw) : raw; }
      out.params[p.key] = {v, unit:p.num ? (x.unit || p.unit) : '', status:x.status, src:x.src || '', date:x.date || '', unc:x.unc || '', note:x.note || '', q:p.num ? (x.q || '') : '', range:x.status === 'unavailable' ? null : (x.range || null)};
      if (p.custom){ out.params[p.key].label = p.label; out.params[p.key].num = !!p.num; }
    });
    return out;
  }
  function validate(r0, isBuilt){
    const r = isBuilt ? r0 : build(r0), er = {}; const raw = isBuilt ? null : r0;
    if (!r.name || r.name.length < 2) er.name = 'Give the location a name of at least two characters.';
    if (!TT.BODIES[r.body]) er.body = 'Choose a body.';
    if (r.lat == null || Math.abs(r.lat) > 90) er.lat = 'Latitude must be a number from −90 to 90.';
    if (r.lon == null || r.lon < -360 || r.lon > 360) er.lon = 'Longitude must be a number from −180 to 180 (or 0 to 360).';
    ['summary', 'geology', 'environment', 'relevance', 'rationale'].forEach(k => { if ((r[k] || '').length > 3000) er[k] = 'Keep this under 3,000 characters.'; });
    defsOf(r.params).forEach(p => {
      const x = r.params[p.key]; if (!x) return;
      if (x.status !== 'unavailable'){
        if ((x.v == null || x.v === '') && !x.range) er['p-' + p.key] = p.num ? 'Enter a number, or set the status to unavailable.' : 'Enter a value, or set the status to unavailable.';
        else if (p.key.endsWith('_km') && x.v < 0) er['p-' + p.key] = 'This cannot be negative.';
        if (x.status === 'measured' && !x.src) er['p-' + p.key + '-src'] = 'A measured value needs a source.';
        if (x.src && r.sources.indexOf(x.src) < 0) er['p-' + p.key + '-src'] = 'Attach this source to the location first.';
        if (x.date && !/^\d{4}(-\d{2}(-\d{2})?)?$/.test(x.date)) er['p-' + p.key + '-date'] = 'Use YYYY, YYYY-MM or YYYY-MM-DD.';
      }
    });
    r.images.forEach((im, i) => { if (!im.credit || !im.license) er['img-' + i] = 'Every image needs a credit and a license.'; });
    Object.values(r.srcdefs).forEach(s => { if (s.url && !/^https?:\/\//.test(s.url)) er['src-' + s.id] = 'Source links must start with http:// or https://.'; });
    return er;
  }
  function showErr(){ shell.querySelectorAll('[data-err]').forEach(el => { const m = errs[el.dataset.err]; el.textContent = m || ''; el.hidden = !m; }); shell.querySelectorAll('[data-key]').forEach(el => el.classList.toggle('bad', !!errs[el.dataset.key])); }

  function editor(main){
    const e = st.edit, isNew = !!e._new;
    const touch = () => { st.dirty = true; };
    const fld = (label, key, input, hint) => { input.dataset.key = key; input.id = 'f-' + key; return h('div', {class:'field'}, h('label', {class:'f', for:'f-' + key}, label), input, hint ? h('div', {class:'hint'}, hint) : null, h('div', {class:'err', 'data-err':key, hidden:true, role:'alert'})); };
    const txt = (key, label, o) => { o = o || {}; return fld(label, o.errKey || key, h('input', {class:'input', type:'text', value:e[key] || '', maxlength:o.max || 200, placeholder:o.ph || '', list:o.list, oninput: ev => { e[key] = ev.target.value; touch(); }}), o.hint); };
    const area = (key, label, hint) => fld(label, key, h('textarea', {class:'input', rows:'4', maxlength:'3000', oninput: ev => { e[key] = ev.target.value; touch(); }}, e[key] || ''), hint);
    const sel = (key, label, opts, after) => fld(label, key, h('select', {class:'input', onchange: ev => { e[key] = ev.target.value; touch(); after && after(); }}, opts.map(o => h('option', {value:o[0], selected:e[key] === o[0]}, o[1]))));

    const head = h('div', {style:{display:'flex', gap:'12px', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap'}}, h('div', null, h('h1', null, isNew ? 'New location' : 'Edit: ' + e.name), h('p', {class:'muted small', style:{margin:0}}, 'Saved drafts stay private until you publish.')),
      h('button', {class:'btn', type:'button', onclick: cancel}, 'Back to list'));
    const form = h('form', {novalidate:true, onsubmit: ev => ev.preventDefault()});
    main.append(head, form);
    const sec = (t, ...kids) => form.appendChild(h('section', {class:'card', style:{margin:'16px 0'}}, h('h2', {style:{fontSize:'1.1rem', marginBottom:'12px'}}, t), kids));

    sec('Basics', h('div', {class:'row2'}, txt('name', 'Name', {max:140}), sel('body', 'Body', TT.BODY_ORDER.map(b => [b, TT.BODIES[b].name]), () => { refreshAfterKind(); preview(); })),
      h('div', {class:'row2'}, sel('kind', 'Marker type', [['landing', TT.KINDS.landing.label], ['base', TT.KINDS.base.label], ['analog', TT.KINDS.analog.label]], () => { refreshAfterKind(); preview(); }), txt('terrain', 'Terrain class', {list:'terrains', max:80, hint:'Pick a suggestion or type your own.'})),
      h('div', {class:'row2'}, txt('region', 'Region', {max:200}), txt('status_label', 'Status line', {max:300, ph:'e.g. Artemis III candidate landing region', hint:'Shown under the name.'})),
      h('datalist', {id:'terrains'}, TT.TERRAINS.map(t => h('option', {value:t}))),
      h('p', {class:'tiny muted', style:{margin:0}}, 'Address: ', h('span', {class:'mono'}, '#location-' + (e.id || '(assigned on first save)'))));

    const pv = h('div', {class:'mini', style:{maxWidth:'380px'}}, h('canvas', {style:{aspectRatio:'4/3'}, 'aria-label':'Map preview of the entered coordinates'}), h('div', {class:'cap'}, 'Preview of the coordinates on the global base map.'));
    const dup = h('div', {class:'small', style:{color:'var(--warn)', marginTop:'8px'}});
    sec('Coordinates', h('div', {class:'row2', style:{alignItems:'start'}}, h('div', null,
      fld('Latitude (degrees, −90 to 90, south is negative)', 'lat', h('input', {class:'input', type:'text', inputmode:'decimal', value:e._lat, oninput: ev => { e._lat = ev.target.value; touch(); preview(); }})),
      fld('Longitude (degrees, −180 to 180, west is negative)', 'lon', h('input', {class:'input', type:'text', inputmode:'decimal', value:e._lon, oninput: ev => { e._lon = ev.target.value; touch(); preview(); }})), dup), pv));
    function preview(){
      clearTimeout(previewTimer); previewTimer = setTimeout(() => {
        const lat = Number(e._lat), lon = Number(e._lon), cv = pv.firstChild, ok = String(e._lat).trim() !== '' && String(e._lon).trim() !== '' && isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 360;
        if (previewMap){ previewMap.dispose(); previewMap = null; }
        pv.lastChild.textContent = ok ? 'Preview of the coordinates on the global base map.' : 'Enter valid coordinates to see a preview.'; dup.textContent = '';
        if (!ok){ const x = cv.getContext('2d'); x && x.clearRect(0, 0, cv.width, cv.height); return; }
        TT.contextMap(cv, {id:'preview', name:e.name || 'Preview', body:e.body, kind:e.kind, lat, lon:TT.normLon(lon)}, {span:60, interactive:false}).then(m => previewMap = m);
        const near = S.all().filter(r => r.id !== e.id && r.body === e.body).map(r => ({r, km:TT.haversineKm({lat, lon}, r, TT.BODIES[e.body].radius_km)})).sort((a, b) => a.km - b.km)[0];
        if (near && near.km < 5) dup.textContent = 'Note: ' + near.r.name + ' is only ' + TT.fmtNum(near.km) + ' km from this point.';
      }, 250);
    }

    sec('Descriptions', area('summary', 'Summary'), h('div', {class:'row2'}, area('geology', 'Geology'), area('environment', 'Environment')), area('relevance', 'Relevance to exploration or as an analog'),
      h('div', {id:'rat-wrap'}));
    const ratWrap = TT.$('#rat-wrap', form);
    function refreshAfterKind(){
      TT.clear(ratWrap);
      if (e.kind === 'analog'){
        const targets = S.all().filter(r => r.kind !== 'analog' && r.id !== e.id && r.body !== e.body);
        ratWrap.append(area('rationale', 'Why this is an analog (editorial)', 'Say what you are comparing and cite the source. This text is shown next to the link.'),
          h('div', {class:'field'}, h('span', {class:'f', style:{display:'block', fontSize:'.8rem', fontWeight:600, color:'var(--text2)', margin:'0 0 6px'}}, 'Counterpart locations on the Moon and Mars'),
            h('div', {style:{display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(230px,1fr))', gap:'2px 12px'}}, targets.map(t => h('label', {class:'check'}, h('input', {type:'checkbox', checked:e.analog_for.indexOf(t.id) >= 0, onchange: ev => { ev.target.checked ? e.analog_for.push(t.id) : e.analog_for = e.analog_for.filter(x => x !== t.id); touch(); }}), h('span', null, t.name, h('span', {class:'tiny muted', style:{display:'block'}}, TT.BODIES[t.body].name)))))));
      }
    }
    refreshAfterKind();

    /* parameters */
    const psec = h('div');
    defsOf(e.params).forEach(p => {
      const x = e.params[p.key] || (e.params[p.key] = {v:null, unit:p.unit, status:'unavailable', src:'', date:'', unc:'', note:'', q:'', range:null});
      if (x._raw == null) x._raw = '';
      const valIn = h('input', {class:'input', type:'text', inputmode:p.num ? 'decimal' : 'text', value:x._raw, disabled:x.status === 'unavailable', oninput: ev => { x._raw = ev.target.value; touch(); }});
      const unitIn = h('input', {class:'input', type:'text', value:x.unit || p.unit, maxlength:'20', disabled:!p.num || x.status === 'unavailable', oninput: ev => { x.unit = ev.target.value; touch(); }});
      const stSel = h('select', {class:'input', onchange: ev => { x.status = ev.target.value; const off = x.status === 'unavailable'; valIn.disabled = off; unitIn.disabled = off || !p.num; qSel && (qSel.disabled = off); touch(); }}, ['measured', 'derived', 'unavailable'].map(s => h('option', {value:s, selected:x.status === s}, s)));
      const qSel = p.num ? h('select', {class:'input', 'aria-label':'Qualifier for ' + p.label, disabled:x.status === 'unavailable', onchange: ev => { x.q = ev.target.value; touch(); }}, QUAL.map(q => h('option', {value:q[0], selected:(x.q || '') === q[0]}, q[1]))) : null;
      const srcSel = h('select', {class:'input', 'data-key':'p-' + p.key + '-src', onchange: ev => { x.src = ev.target.value; touch(); }}, h('option', {value:''}, 'None'), e.sources.map(id => { const s = allSources().get(id); return h('option', {value:id, selected:x.src === id}, s ? (s.publisher || s.title).slice(0, 50) + (s.year ? ' ' + s.year : '') : id); }), x.src && e.sources.indexOf(x.src) < 0 ? h('option', {value:x.src, selected:true}, x.src + ' (not attached)') : null);
      psec.appendChild(h('fieldset', {style:{border:'1px solid var(--line)', borderRadius:'10px', padding:'12px 14px', margin:'0 0 12px', minWidth:0}}, h('legend', {style:{padding:'0 6px', fontWeight:600}}, p.label + (p.unit ? ' (' + p.unit + ')' : '') + (p.custom ? ' · custom' : '')),
        h('div', {class:'row3'}, h('div', {class:'field'}, h('label', {class:'f'}, 'Status'), stSel), h('div', {class:'field'}, h('label', {class:'f'}, 'Value'), h('div', {style:{display:'flex', gap:'6px'}}, qSel, valIn), h('div', {class:'err', 'data-err':'p-' + p.key, hidden:true, role:'alert'})), h('div', {class:'field'}, h('label', {class:'f'}, 'Unit'), unitIn)),
        h('div', {class:'row3'}, h('div', {class:'field'}, h('label', {class:'f'}, 'Source'), srcSel, h('div', {class:'err', 'data-err':'p-' + p.key + '-src', hidden:true, role:'alert'})), h('div', {class:'field'}, h('label', {class:'f'}, 'Date of the value'), h('input', {class:'input', type:'text', value:x.date || '', placeholder:'YYYY-MM-DD', maxlength:'20', 'data-key':'p-' + p.key + '-date', oninput: ev => { x.date = ev.target.value; touch(); }}), h('div', {class:'err', 'data-err':'p-' + p.key + '-date', hidden:true, role:'alert'})), h('div', {class:'field'}, h('label', {class:'f'}, 'Uncertainty'), h('input', {class:'input', type:'text', value:x.unc || '', placeholder:'e.g. ± 50 m', maxlength:'120', oninput: ev => { x.unc = ev.target.value; touch(); }}))),
        h('div', {class:'field', style:{margin:0}}, h('label', {class:'f'}, 'Note (for an unavailable value, say why)'), h('input', {class:'input', type:'text', value:x.note || '', maxlength:'400', oninput: ev => { x.note = ev.target.value; touch(); }})),
        p.custom ? h('button', {class:'btn sm ghost', type:'button', style:{marginTop:'10px'}, onclick: () => { delete e.params[p.key]; touch(); rebuildForParams(); }}, 'Remove this parameter') : null));
    });
    const cp = {label:'', unit:'', num:'1'}, cpErr = h('div', {class:'err', hidden:true, role:'alert'});
    const addParam = h('details', {style:{marginTop:'6px'}}, h('summary', {style:{cursor:'pointer', fontWeight:600}}, 'Add a custom parameter'),
      h('p', {class:'tiny muted'}, 'For any other measured quantity, such as radiation dose or dust cover. It then appears on the location page and in comparisons.'),
      h('div', {class:'row3', style:{marginTop:'8px'}}, h('div', {class:'field'}, h('label', {class:'f'}, 'Name'), h('input', {class:'input', type:'text', maxlength:'80', oninput: ev => { cp.label = ev.target.value; }})),
        h('div', {class:'field'}, h('label', {class:'f'}, 'Unit'), h('input', {class:'input', type:'text', maxlength:'20', oninput: ev => { cp.unit = ev.target.value; }})),
        h('div', {class:'field'}, h('label', {class:'f'}, 'Type'), h('select', {class:'input', onchange: ev => { cp.num = ev.target.value; }}, h('option', {value:'1'}, 'Number'), h('option', {value:'0'}, 'Text')))),
      cpErr, h('button', {class:'btn sm', type:'button', onclick: () => {
        const label = cp.label.trim(); if (!label){ cpErr.textContent = 'Give the parameter a name.'; cpErr.hidden = false; return; }
        let key = (TT.slug(label).replace(/-/g, '_').slice(0, 36) || 'param'), k0 = key, n = 2; while (TT.PARAM[key] || e.params[key]) key = k0 + '_' + n++;
        e.params[key] = {label, num:cp.num === '1', v:null, unit:cp.unit.trim(), status:'unavailable', src:'', date:'', unc:'', note:'', q:'', range:null, _raw:''}; touch(); rebuildForParams();
      }}, 'Add parameter'));
    sec('Parameters', h('p', {class:'small muted', style:{marginTop:0}}, 'Never estimate a missing value. Set its status to unavailable and the public site will say so.'), psec, addParam);

    /* sources */
    const srcBox = h('div'), srcPick = h('select', {class:'input', 'aria-label':'Add a known source'});
    function drawSources(){
      TT.clear(srcBox); const all = allSources();
      e.sources.forEach(id => { const s = all.get(id) || {title:id}; srcBox.appendChild(h('div', {class:'relrow'}, h('span', {class:'grow small'}, s.title, h('span', {class:'tiny muted', style:{display:'block'}}, [s.publisher, s.year].filter(Boolean).join(', '))), h('div', {class:'err', 'data-err':'src-' + id, hidden:true}), h('button', {class:'btn sm ghost', type:'button', onclick: () => { e.sources = e.sources.filter(x => x !== id); Object.values(e.params).forEach(p => { if (p.src === id) p.src = ''; }); touch(); drawSources(); rebuildForParams(); }}, 'Remove'))); });
      if (!e.sources.length) srcBox.appendChild(h('p', {class:'na small'}, 'No sources attached.'));
      TT.clear(srcPick); srcPick.appendChild(h('option', {value:''}, 'Choose a source to attach…'));
      [...all.entries()].filter(([id]) => e.sources.indexOf(id) < 0).sort((a, b) => (a[1].title || '').localeCompare(b[1].title || '')).forEach(([id, s]) => srcPick.appendChild(h('option', {value:id}, (s.title || id).slice(0, 80) + (s.year ? ' (' + s.year + ')' : ''))));
    }
    const rebuildForParams = () => { /* source dropdowns in the parameter cards depend on the attached list: rebuild the form */ const y = window.scrollY; render(); window.scrollTo(0, y); };
    const cs = {title:'', publisher:'', url:'', year:'', note:''};
    const csErr = h('div', {class:'err', hidden:true});
    sec('Sources', srcBox, h('div', {style:{display:'flex', gap:'8px', marginTop:'10px'}}, srcPick, h('button', {class:'btn', type:'button', onclick: () => { const id = srcPick.value; if (!id) return; e.sources.push(id); const s = allSources().get(id); if (s && !(window.TT_SEED.sources[id])) e.srcdefs[id] = s; touch(); drawSources(); rebuildForParams(); }}, 'Attach')),
      h('details', {style:{marginTop:'14px'}}, h('summary', {style:{cursor:'pointer', fontWeight:600}}, 'Add a source that is not in the list'),
        h('div', {class:'row2', style:{marginTop:'10px'}}, ['title', 'publisher', 'url', 'year'].map(k => h('div', {class:'field'}, h('label', {class:'f'}, {title:'Title', publisher:'Publisher or authors', url:'Link (https://…)', year:'Year'}[k]), h('input', {class:'input', type:'text', maxlength:k === 'year' ? '10' : '300', oninput: ev => { cs[k] = ev.target.value; }})))),
        csErr, h('button', {class:'btn sm', type:'button', onclick: () => {
          if (!cs.title.trim()){ csErr.textContent = 'A title is required.'; csErr.hidden = false; return; }
          if (cs.url && !/^https?:\/\//.test(cs.url)){ csErr.textContent = 'The link must start with http:// or https://.'; csErr.hidden = false; return; }
          let id = 'c-' + (TT.slug(cs.title).slice(0, 30) || 'source'), n = 2; const root0 = id; const all = allSources(); while (all.has(id)) id = root0 + '-' + n++;
          e.srcdefs[id] = {id, title:cs.title.trim(), publisher:cs.publisher.trim(), url:cs.url.trim(), year:cs.year.trim(), note:''}; e.sources.push(id); touch(); rebuildForParams();
        }}, 'Add and attach')));
    drawSources();

    /* images */
    const imgBox = h('div');
    function drawImgs(){
      TT.clear(imgBox);
      e.images.forEach((im, i) => imgBox.appendChild(h('div', {class:'relrow', style:{alignItems:'flex-start'}}, h('img', {class:'thumb', src:im.url, alt:''}), h('div', {class:'grow'},
        h('input', {class:'input', placeholder:'Caption / description', value:im.caption || '', maxlength:'300', 'aria-label':'Caption', oninput: ev => { im.caption = ev.target.value; touch(); }}),
        h('div', {class:'row2', style:{marginTop:'6px'}}, h('input', {class:'input', placeholder:'Credit (required)', value:im.credit || '', maxlength:'200', 'aria-label':'Credit', oninput: ev => { im.credit = ev.target.value; touch(); }}), h('input', {class:'input', placeholder:'License (required)', value:im.license || '', maxlength:'120', 'aria-label':'License', list:'licenses', oninput: ev => { im.license = ev.target.value; touch(); }})),
        h('div', {class:'err', 'data-err':'img-' + i, hidden:true})), h('button', {class:'btn sm ghost', type:'button', onclick: () => { e.images.splice(i, 1); touch(); drawImgs(); }}, 'Remove'))));
      if (!e.images.length) imgBox.appendChild(h('p', {class:'na small'}, 'No images attached.'));
    }
    const libPick = h('select', {class:'input', 'aria-label':'Attach an image from the library'}, h('option', {value:''}, 'Attach from the image library…'), [...S.assets.values()].map(a => h('option', {value:a.id}, (a.caption || a.name || a.id).slice(0, 70))));
    sec('Images', imgBox, h('datalist', {id:'licenses'}, LICENSES.map(l => h('option', {value:l}))), h('div', {style:{display:'flex', gap:'8px', marginTop:'10px'}}, libPick, h('button', {class:'btn', type:'button', onclick: () => { const a = S.assets.get(libPick.value); if (!a) return; e.images.push({id:a.id, url:a.url, caption:a.caption || '', credit:a.credit || '', license:a.license || ''}); touch(); drawImgs(); }}, 'Attach')),
      h('p', {class:'tiny muted'}, 'Add new files in “Images and files”. Every image needs a credit and a license.'));
    drawImgs();

    sec('Publishing', h('div', {class:'row2'}, h('div', {class:'field'}, h('label', {class:'f', for:'f-tags'}, 'Tags (comma separated)'), h('input', {class:'input', id:'f-tags', type:'text', value:e.tags.join(', '), oninput: ev => { e.tags = ev.target.value.split(',').map(t => t.trim()).filter(Boolean).slice(0, 20); touch(); }}), h('div', {class:'hint'}, 'Used by search, such as “polar”, “lava tube”.')),
      sel('verification', 'Data review status', [['sample', 'Sample: from cited sources, not expert-reviewed'], ['reviewed', 'Reviewed by a domain expert']])));

    const bar = h('div', {class:'glass', style:{position:'sticky', bottom:'12px', display:'flex', gap:'10px', justifyContent:'flex-end', flexWrap:'wrap', padding:'12px', marginTop:'18px', zIndex:5}},
      h('span', {class:'small muted', style:{marginRight:'auto', alignSelf:'center'}, role:'status', id:'save-msg'}),
      h('button', {class:'btn', type:'button', onclick: cancel}, 'Cancel'),
      h('button', {class:'btn', type:'button', onclick: () => save(false)}, 'Save draft'),
      h('button', {class:'btn primary', type:'button', onclick: () => save(true)}, 'Publish…'));
    form.appendChild(bar);
    preview(); showErr();

    async function save(publish){
      errs = validate(e); showErr();
      const n = Object.keys(errs).length;
      if (n){ TT.$('#save-msg').textContent = n + ' problem' + (n > 1 ? 's' : '') + ' to fix before saving.'; const first = shell.querySelector('[data-err]:not([hidden])'); first && first.scrollIntoView({block:'center', behavior:'smooth'}); return; }
      const out = build(e); out.lon = TT.normLon(out.lon);
      if (!out.id) out.id = S.uniqueId(out.name);
      if (publish && !(await TT.confirm({title:'Publish “' + out.name + '”?', body:'It becomes visible to every visitor' + (S.mode === 'sandbox' ? ' (in this sandbox, only in your browser)' : '') + '.', ok:'Publish'}))) return;
      guard(async () => { if (publish) await S.publish(out); else await S.saveDraft(out); TT.toast(publish ? 'Published' : 'Draft saved'); st.edit = null; st.dirty = false; render(); window.scrollTo(0, 0); });
    }
    async function cancel(){
      if (st.dirty && !(await TT.confirm({title:'Discard your changes?', body:'You have unsaved edits to this location.', ok:'Discard', danger:true}))) return;
      st.edit = null; st.dirty = false; render(); window.scrollTo(0, 0);
    }
  }

  /* ---------- assets ---------- */
  function assets(main){
    main.append(h('h1', null, 'Images and files'), h('p', {class:'muted'}, 'Store images with their credit and license, then attach them to locations. Only images are displayed on the site; 3D textures and elevation maps can be stored here, but applying them to the globe needs the production tile pipeline.'));
    const f = {caption:'', credit:'', license:LICENSES[0], url:'', kind:ASSET_KINDS[0], loc:''}, msg = h('div', {role:'status', class:'small', style:{marginTop:'8px'}});
    const need = () => { if (!f.caption.trim() || !f.credit.trim() || !f.license.trim()){ msg.textContent = 'Caption, credit and license are all required.'; msg.style.color = 'var(--danger)'; return false; } return true; };
    const meta = h('div', {class:'row3'}, ['caption', 'credit'].map(k => h('div', {class:'field'}, h('label', {class:'f', for:'a-' + k}, k === 'caption' ? 'Caption / alt text' : 'Credit'), h('input', {class:'input', id:'a-' + k, type:'text', maxlength:'300', oninput: ev => { f[k] = ev.target.value; }}))),
      h('div', {class:'field'}, h('label', {class:'f', for:'a-license'}, 'License'), h('input', {class:'input', id:'a-license', list:'licenses2', value:f.license, maxlength:'120', oninput: ev => { f.license = ev.target.value; }}), h('datalist', {id:'licenses2'}, LICENSES.map(l => h('option', {value:l})))));
    const meta2 = h('div', {class:'row2', style:{marginTop:'10px'}},
      h('div', {class:'field'}, h('label', {class:'f', for:'a-kind'}, 'Type of asset'), h('select', {class:'input', id:'a-kind', onchange: ev => { f.kind = ev.target.value; }}, ASSET_KINDS.map(k => h('option', {value:k}, k)))),
      h('div', {class:'field'}, h('label', {class:'f', for:'a-loc'}, 'Associated location (optional)'), h('select', {class:'input', id:'a-loc', onchange: ev => { f.loc = ev.target.value; }}, h('option', {value:''}, 'None'), S.adminList().map(x => h('option', {value:x.rec.id}, x.rec.name)))));
    const file = h('input', {type:'file', accept:'image/png,image/jpeg,image/webp,image/svg+xml', class:'sr', id:'a-file', onchange: ev => { const x = ev.target.files[0]; ev.target.value = ''; x && upload(x); }});
    const upBox = C.assets
      ? h('div', {class:'drop'}, h('p', {style:{margin:'0 0 10px'}}, 'PNG, JPEG, WebP or SVG, up to 20 MiB.'), h('label', {class:'btn primary', for:'a-file'}, TT.icon('upload'), 'Choose an image'), file)
      : h('div', {class:'notice'}, TT.icon('info'), h('span', null, 'File upload is not available in this view' + (S.mode === 'sandbox' ? ' (sandbox)' : '') + '. You can still register an image that is already online using its link.'));
    const urlIn = h('input', {class:'input', type:'url', placeholder:'https://…', 'aria-label':'Image link'});
    main.append(h('div', {class:'card', style:{marginBottom:'20px'}}, h('h2', {style:{fontSize:'1.1rem', marginBottom:'12px'}}, 'Add an image or file'), meta, meta2, upBox,
      h('div', {style:{display:'flex', gap:'8px', marginTop:'12px'}}, urlIn, h('button', {class:'btn', type:'button', onclick: () => addUrl(urlIn)}, 'Add by link')), msg));
    async function upload(x){
      if (!need()) return; msg.style.color = ''; msg.textContent = 'Uploading…';
      try { const res = await C.assets.upload(x); await S.putAsset({id:res.id, url:'/_blob/' + res.id, name:x.name, size:res.sizeBytes || x.size, type:res.contentType || x.type, caption:f.caption.trim(), credit:f.credit.trim(), license:f.license.trim(), kind:f.kind, loc:f.loc, uploaded:TT.isoDate(), managed:true}); msg.textContent = 'Added.'; }
      catch(e){ msg.style.color = 'var(--danger)'; msg.textContent = 'Upload failed: ' + (e && e.message || 'unknown error'); }
    }
    async function addUrl(inp){
      const u = inp.value.trim(); if (!need()) return;
      if (!/^https:\/\//.test(u)){ msg.style.color = 'var(--danger)'; msg.textContent = 'The link must start with https://'; return; }
      try { await S.putAsset({id:'url-' + Date.now().toString(36), url:u, name:u.split('/').pop().slice(0, 60), caption:f.caption.trim(), credit:f.credit.trim(), license:f.license.trim(), kind:f.kind, loc:f.loc, uploaded:TT.isoDate(), managed:false}); inp.value = ''; msg.style.color = ''; msg.textContent = 'Added.'; }
      catch(e){ msg.style.color = 'var(--danger)'; msg.textContent = 'Could not save: ' + (e && e.message || 'unknown error'); }
    }
    const grid = h('div', {style:{display:'grid', gridTemplateColumns:'repeat(auto-fill,minmax(250px,1fr))', gap:'14px'}});
    [...S.assets.values()].forEach(a => {
      const users = [...S.all(), ...S.drafts.values()].filter(r => r.images.some(i => i.id === a.id)).length;
      grid.appendChild(h('div', {class:'card', style:{padding:'12px'}}, h('img', {src:a.url, alt:a.caption || '', style:{width:'100%', aspectRatio:'4/3', objectFit:'cover', borderRadius:'8px', background:'#050913'}}),
        h('p', {class:'small', style:{margin:'8px 0 2px'}}, a.caption || a.name), h('p', {class:'tiny muted', style:{margin:0}}, (a.kind || 'Image') + (a.loc && S.getAny(a.loc) ? ' · for ' + S.getAny(a.loc).name : '') + ' · uploaded ' + (a.uploaded || 'unknown')), h('p', {class:'tiny muted', style:{margin:0}}, 'Credit: ' + a.credit + ' · ' + a.license + (a.name ? ' · ' + a.name : '')), h('p', {class:'tiny muted', style:{margin:'2px 0 8px'}}, 'Used by ' + users + ' location' + (users === 1 ? '' : 's') + (a.size ? ' · ' + TT.fmtNum(a.size / 1024) + ' KiB' : '')),
        h('button', {class:'btn sm danger', type:'button', onclick: async () => { if (await TT.confirm({title:'Delete this image?', body:users ? 'It is attached to ' + users + ' location(s). They will show a broken image until you remove it from them.' : 'This removes it from the library.', ok:'Delete', danger:true})) guard(async () => { if (a.managed && C.assets) await C.assets.delete(a.id); await S.dropAsset(a.id); TT.toast('Deleted'); }); }}, TT.icon('trash'), 'Delete')));
    });
    main.appendChild(h('section', {class:'sec'}, h('h2', null, 'Library (' + S.assets.size + ')'), S.assets.size ? grid : h('p', {class:'na'}, 'No images yet.')));
  }

  /* ---------- sources ---------- */
  function sources(main){
    main.append(h('h1', null, 'Sources'), h('p', {class:'muted'}, 'Every citation in the database. To add one, attach it from a location’s edit form.'));
    const rows = [...allSources().entries()].map(([id, s]) => ({id, s, n:cites(id)})).sort((a, b) => b.n - a.n || (a.s.title || '').localeCompare(b.s.title || ''));
    main.appendChild(h('div', {class:'cmp-scroll'}, h('table', {class:'t'}, h('thead', null, h('tr', null, ['Title', 'Publisher', 'Year', 'Cited by', 'Origin'].map(t => h('th', null, t)))),
      h('tbody', null, rows.map(x => h('tr', null, h('td', null, x.s.url ? h('a', {href:x.s.url, target:'_blank', rel:'noopener noreferrer'}, x.s.title) : x.s.title), h('td', {class:'small'}, x.s.publisher || '—'), h('td', {class:'val'}, x.s.year || '—'), h('td', {class:'val'}, x.n), h('td', {class:'small muted'}, window.TT_SEED.sources[x.id] ? 'built in' : 'added in admin')))))));
  }

  render();
  return {destroy(){ clearTimeout(previewTimer); previewMap && previewMap.dispose(); }, refresh(){ if (!st.edit) render(); }};
};
})();
