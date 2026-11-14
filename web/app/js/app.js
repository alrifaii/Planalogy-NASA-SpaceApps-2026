/* Planalogy — shell and hash router. Two pages: the Analog Finder and About. */
(function(){
const TT = window.TT, h = TT.h;
TT.pages = TT.pages || {};
const main = TT.$('#main'), nav = TT.$('#nav'), foot = TT.$('#foot');
TT.$('#skip').addEventListener('click', () => TT.focusMain());

const parse = () => (location.hash || '').replace(/^#/, '') === 'about' ? 'about' : 'finder';
const titles = {finder:'Planalogy — Analog Finder', about:'About — Planalogy'};
let current = null, first = true;
function route(){
  if (current && current.destroy){ try { current.destroy(); } catch(e){ console.error(e); } }
  current = null;
  const name = parse(); TT.clear(main); window.scrollTo(0, 0);
  document.title = titles[name]; document.body.dataset.route = name;
  nav.querySelectorAll('a').forEach(a => { if (a.dataset.r === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  foot.hidden = name === 'finder';
  try { current = TT.pages[name](main) || null; }
  catch(e){ console.error(e); main.appendChild(h('div', {class:'wrap page'}, h('h1', null, 'Something went wrong'), h('p', {class:'muted'}, 'This page failed to load: ' + e.message))); }
  if (!first) TT.focusMain(); first = false;
}
window.addEventListener('hashchange', route);
route();
})();
