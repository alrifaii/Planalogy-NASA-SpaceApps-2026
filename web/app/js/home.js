/* Planalogy — home page */
(function(){
const TT = window.TT, h = TT.h;

TT.pages.home = function(root){
  const S = TT.Store; let hero = null;
  const cv = h('canvas', {'aria-hidden':'true'});
  const heroEl = h('section', {class:'hero', 'aria-labelledby':'hh'}, cv, h('div', {class:'hero-shade'}),
    h('div', {class:'wrap'}, h('div', {class:'hero-copy'},
      h('h1', {id:'hh'}, 'Find Earth’s Extremes. ', h('em', null, 'Prepare for Other Worlds.')),
      h('p', {class:'lede'}, 'Explore potential Moon and Mars base locations and discover Earth\u2019s most remarkable planetary analog environments through interactive 3D visualization and scientific data.'),
      h('div', {class:'hero-actions'}, h('a', {class:'btn primary', href:'#finder'}, 'Find Earth analogs'), h('a', {class:'btn', href:'#explore'}, 'Explore the planets'), h('a', {class:'btn ghost', href:'#about'}, 'How it works')))));
  root.appendChild(heroEl);
  hero = TT.createHero(cv, S.all());
  if (!hero){
    /* no WebGL: three flat discs painted with the same NASA maps */
    heroEl.removeChild(cv);
    const disc = (b, size, x, y) => h('div', {'aria-hidden':'true', style:{position:'absolute', width:size, height:size, right:x, top:y, borderRadius:'50%', backgroundImage:'url(' + TT.TEX[b].map + ')', backgroundSize:'cover', boxShadow:'inset -30px -20px 60px rgba(0,0,0,.7)'}});
    heroEl.insertBefore(h('div', {style:{position:'absolute', inset:0, overflow:'hidden'}}, disc('earth', 'min(46vw,420px)', '6%', '16%'), disc('mars', 'min(20vw,180px)', '40%', '8%'), disc('moon', 'min(14vw,130px)', '36%', '66%')), heroEl.firstChild);
  }

  const bodies = h('div', {class:'wrap bodies', role:'list'});
  const blurb = {earth:'Analog sites: polar deserts, impact craters, volcanic fields and field stations.', moon:'South polar landing regions, a crater-rim base candidate and lava-tube pits.', mars:'Landing regions and mid-latitude ice-bearing terrain for a base.'};
  function drawBodies(){
    TT.clear(bodies);
    TT.BODY_ORDER.forEach(b => {
      const recs = S.byBody(b), by = k => recs.filter(r => r.kind === k).length, parts = [];
      if (by('landing')) parts.push(by('landing') + ' landing'); if (by('base')) parts.push(by('base') + ' base'); if (by('analog')) parts.push(by('analog') + ' analog');
      bodies.appendChild(h('a', {class:'bodycard', role:'listitem', href:'#explore-' + b},
        h('b', null, h('span', {class:'dot', style:{background:TT.BODIES[b].color, width:'12px', height:'12px'}}), TT.BODIES[b].name),
        h('p', {class:'muted small', style:{margin:'6px 0 10px'}}, blurb[b]), h('span', {class:'mono'}, parts.join(' · ') || 'No published locations')));
    });
  }
  drawBodies(); root.appendChild(bodies);

  return {destroy(){ hero && hero.dispose(); }, refresh: drawBodies};
};
})();
