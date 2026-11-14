/* Planalogy — About and methodology. Everything that explains how values are labelled, compared and searched lives here. */
(function(){
const TT = window.TT, h = TT.h;

TT.pages.about = function(root){
  const page = h('div', {class:'wrap page prose'}); root.appendChild(page);
  const sec = (id, title, ...kids) => page.appendChild(h('section', {id}, h('h2', null, title), kids));

  page.appendChild(h('h1', null, 'About Planalogy'));
  page.appendChild(h('p', {class:'lede'}, 'A student prototype for the NASA Space Apps Challenge topic “Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars”. It helps a researcher find places on Earth whose terrain, climate or geology resemble a planned Moon or Mars site, and see exactly how far that resemblance goes.'));

  sec('what', 'What you can do here',
    h('ul', null, h('li', null, h('b', null, 'Explore'), ' a 3D globe or 2D map of the Moon, Mars and Earth with candidate landing sites, potential base sites, Earth analog sites and points you place yourself.'),
      h('li', null, h('b', null, 'Read'), ' a detail page for each place, with every value labelled by status and tied to a numbered source.'),
      h('li', null, h('b', null, 'Compare'), ' two to four places side by side.'),
      h('li', null, h('b', null, 'Ask'), ' questions in plain language and get answers drawn only from the records in the database.'),
      h('li', null, h('b', null, 'Maintain'), ' the data through the admin area, without changing code.')));

  sec('finder', 'How the Analog Finder scores sites',
    h('ul', null,
      h('li', null, 'Every dry, bare 1° cell of Earth is compared with a Mars target, feature by feature: relief, day–night ground temperature swing, coldest ground temperature, thermal inertia (rank within each planet), albedo, rock type, impact structure and ground ice.'),
      h('li', null, 'Each feature gives a similarity from 0 to 1 with a fixed scale; the score is their weighted average. A missing value is never counted as zero: the cell is listed as incomplete instead.'),
      h('li', null, 'Mission presets set the weights. A preset uses weights learned from known analogs only if they also find a hidden known analog better; otherwise it keeps the science team’s weights.'),
      h('li', null, 'Requirements, such as ground ice for ice drilling, exclude sites instead of lowering their score. Pressure, sunlight, UV, dust and gravity are never scored: Earth cannot reproduce them.'),
      h('li', null, 'Similarity is not suitability. Cells are about 110 km wide; check imagery and the literature before naming a site.')));

  sec('status', 'How values are labelled',
    h('p', null, 'No number appears without a status, a source and, where known, a date and an uncertainty.'),
    h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, 'Status'), h('th', null, 'Meaning'))), h('tbody', null,
      h('tr', null, h('td', null, TT.badge('measured')), h('td', null, 'A figure reported by a cited source. It is as reliable as that source, and may be a model result or an older catalogue value; the note says so when known.')),
      h('tr', null, h('td', null, TT.badge('derived')), h('td', null, 'Computed or inferred from other values, such as absolute latitude from latitude. Not directly measured.')),
      h('tr', null, h('td', null, TT.badge('unavailable')), h('td', null, 'No value in this dataset. Planalogy never fills a gap with an estimate; the site shows “Not available”, and the note usually says why.')))),
    h('p', null, 'Whole records carry a review status too. ', h('span', {class:'badge sample'}, 'sample data'), ' means the figures were compiled from the cited public sources by the project team and have not been checked by a domain expert. ', h('span', {class:'badge measured'}, 'reviewed'), ' is reserved for records an expert has signed off.'));

  sec('analogs', 'How analog links are made',
    h('p', null, 'An analog link says “this Earth place is worth studying for that Moon or Mars place”. Each link has a written rationale and cites its source. These links are ', h('b', null, 'editorial inferences'), ', not measured matches, and carry no score. Whether two places actually agree on terrain size, temperature or position is shown separately on the Compare page.'));

  sec('method', 'How comparison works',
    h('p', null, 'Compare counts how many shared numeric parameters of two places agree within a stated tolerance. It shows the count (for example “3 of 4 scored parameters agree”) and the full table behind it. It does not produce a similarity percentage, because a single number would hide which parameters drove it and how arbitrary the tolerances are.'),
    h('table', {class:'t'}, h('thead', null, h('tr', null, ['Parameter', 'Rule', 'Agrees when', 'Notes'].map(t => h('th', null, t)))), h('tbody', null,
      TT.Cmp.rules.map(r => h('tr', null, h('td', null, r.label), h('td', null, r.rule === 'ratio' ? 'Ratio of the two values' : 'Difference'), h('td', {class:'val'}, r.rule === 'ratio' ? 'within a factor of ' + r.tol : 'within ' + r.tol + ' ' + r.unit), h('td', {class:'small'}, r.note || (r.rule === 'ratio' ? 'Sizes span orders of magnitude, so a ratio is used.' : ''))))
      , h('tr', null, h('td', null, 'Annual precipitation'), h('td', null, 'Shown only'), h('td', null, '—'), h('td', {class:'small'}, 'It has no Moon or Mars counterpart.')))),
    h('ul', null, h('li', null, 'A parameter is scored only if both places have a numeric value. Unavailable values, bounded values (such as “less than 10”) and text values are shown but not scored.'),
      h('li', null, 'With fewer than two comparable parameters, Compare says there is not enough shared data instead of scoring.'),
      h('li', null, 'Every parameter has a weight, 1 by default. You can change the weights on the Compare page; the result then reads “agrees on n of m scored parameters (weight a of b)”.'),
      h('li', null, 'Tolerances are our own and are judgements, not scientific standards. Treat the count as a way to read the table, not as a verdict.')));

  sec('ai', 'How AI search works',
    h('p', null, 'Type a question into the search box on the Explore page and press Ask. Planalogy sends your question together with a compact summary of every published record to Claude, with instructions to use only those records. The reply is a short answer and a list of record ids with a one-line reason each.'),
    h('ul', null, h('li', null, 'Returned ids are checked against the database. Any id that does not exist is dropped, so the map can only show real records.'),
      h('li', null, 'The answer states gaps (for example, which values are unavailable) instead of guessing.'),
      h('li', null, 'It can still be wrong or incomplete. Open a place and check its sources before relying on a statement.'),
      h('li', null, 'If AI search is unavailable or fails, the search box falls back to keyword matching, and says so.'),
      h('li', null, 'There is no API key in this page. In this prototype the request runs through the viewer’s own Claude account. In a production build the key lives on the server, and a server route does the retrieval (filters and PostGIS queries) before calling the model.')));

  sec('imagery', 'Imagery and resolution',
    h('p', null, 'The globe and maps use global, low-resolution base maps. Marker positions are real; the surface behind them is not detailed enough to show a crater rim, a boulder field or a landing ellipse.'),
    h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, 'Body'), h('th', null, 'Base map'))), h('tbody', null, TT.BODY_ORDER.map(b => h('tr', null, h('td', null, TT.BODIES[b].name), h('td', {class:'small'}, TT.BODIES[b].tex + (b === 'earth' ? '. An elevation layer shows topography and bathymetry.' : '. The shading relief on the 3D globe is a visual aid, not elevation data.')))))),
    h('p', null, 'Detail at the scale of a landing site needs tiled map services (for example the Moon Trek and Mars Trek portals), loaded through a server. That is part of the production plan, not of this prototype.'));

  sec('coords', 'Coordinates and reference levels',
    h('p', null, 'Coordinates are copied from the cited sources and converted to degrees north and east, with west and south negative. Latitude and longitude conventions (planetocentric or planetographic, east-positive or west-positive) differ between datasets and have not been harmonised across all sources, so treat positions as accurate to the precision shown at best. Elevations use each body’s own reference level, so they are only compared within one body.'));

  sec('status2', 'What is real and what is a mockup',
    h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, 'Part'), h('th', null, 'In this prototype'))), h('tbody', null,
      h('tr', null, h('td', null, 'Records'), h('td', {class:'small'}, 'Real figures from cited public sources, compiled by hand and not expert-reviewed. The Artemis III landing-region list used here dates from 2024 and may since have been superseded.')),
      h('tr', null, h('td', null, 'Shared data and admin'), h('td', {class:'small'}, 'When published with a shared database, edits by the owner and editors update the public site immediately. Where no database is connected, the admin is a browser-only sandbox, clearly labelled.')),
      h('tr', null, h('td', null, 'Sign-in and sign-out'), h('td', {class:'small'}, 'Handled by the Claude account of the viewer. The page cannot end that session, so the admin offers “Leave admin” instead of a logout button.')),
      h('tr', null, h('td', null, 'Your points'), h('td', {class:'small'}, 'Stored in your browser only.')),
      h('tr', null, h('td', null, 'Body constants'), h('td', {class:'small'}, 'Gravity, radius and mean temperature come from the NASA planetary fact sheets and were not re-fetched while building.')))));

  sec('arch', 'Production plan',
    h('p', null, 'This prototype is a static front end. A production version would use the stack below; the data model in the prototype maps onto it directly.'),
    h('table', {class:'t'}, h('thead', null, h('tr', null, h('th', null, 'Layer'), h('th', null, 'Choice'))), h('tbody', null,
      [['Front end', 'Next.js, React, TypeScript, Tailwind CSS'], ['3D and maps', 'three.js for the globe; tiled map services for local detail'], ['Database', 'PostgreSQL with PostGIS: locations (point geometry), parameters (value, unit, source, date, uncertainty, status), sources, assets, links between locations, users and roles'], ['Authentication', 'Email sign-in with owner, editor and viewer roles; protected admin routes'], ['Files', 'Object storage for images, with credit and license per file'], ['AI search', 'Server route: PostGIS and keyword retrieval, then a model call with the key held on the server']].map(r => h('tr', null, h('td', null, r[0]), h('td', {class:'small'}, r[1]))))));

  sec('a11y', 'Accessibility',
    h('p', null, 'Marker types differ by shape as well as colour. The globe and map can be driven from the keyboard (arrow keys to move, plus and minus to zoom), and every place is reachable from the list without using the map. Motion respects the reduced-motion setting. Colour pairs were chosen for contrast on the dark background.'));

  const srcs = Object.values((window.TT_SEED && window.TT_SEED.sources) || {}).sort((a, b) => (a.title || '').localeCompare(b.title || ''));
  sec('sources', 'Sources used in the sample data',
    h('ul', null, srcs.map(s => h('li', {class:'small'}, s.url ? h('a', {href:s.url, target:'_blank', rel:'noopener noreferrer'}, s.title) : s.title, h('span', {class:'muted'}, ' — ' + [s.publisher, s.year].filter(Boolean).join(', '))))));

  page.querySelectorAll('table.t').forEach(t => { const w = h('div', {class:'cmp-scroll'}); t.replaceWith(w); w.appendChild(t); });
  if (TT.scrollTo){ const t = TT.scrollTo; TT.scrollTo = null; setTimeout(() => { const el = document.getElementById(t); el && el.scrollIntoView(); }, 30); }
  return null;
};
})();
