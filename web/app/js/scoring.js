/* Planalogy — browser scoring for precomputed analogue-engine similarities.
 *
 * The engine score of a complete cell is linear in the effective weights:
 *   score = Σ w_j s_j / Σ w_j,   w_j = (W_g / Σ W) · (a_j / Σ_{k in g} a_k)
 * Similarities s_j come precomputed from backend/web_export.py; this file only
 * applies weights, requirements and ordering. Same rules as the Python engine:
 *   - a cell with no value for a feature that has positive weight (or is
 *     required) is "partial" and is not ranked;
 *   - a failed requirement ("equals") excludes the cell, whatever its score;
 *   - order: score (rounded to 12 decimals) descending, then cell id ascending.
 * Works as a browser global (window.PlanalogyScoring) and as a CommonJS module.
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.PlanalogyScoring = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  /** Effective weights per feature from category weights and in-category feature weights. */
  function effectiveWeights(features, categoryWeights, featureWeights) {
    const cats = {};
    features.forEach(f => { (cats[f.category] = cats[f.category] || []).push(f.id); });
    let totalW = 0;
    Object.keys(cats).forEach(c => {
      const W = +(categoryWeights[c] || 0);
      if (!(W >= 0) || !isFinite(W)) throw new Error('Category weight must be a finite number >= 0: ' + c);
      totalW += W;
    });
    if (!(totalW > 0)) throw new Error('At least one category needs a positive weight.');
    const w = {};
    Object.keys(cats).forEach(c => {
      const W = +(categoryWeights[c] || 0) / totalW;
      const ids = cats[c];
      const inner = ids.reduce((s, id) => s + Math.max(0, +(featureWeights[id] ?? 1)), 0);
      ids.forEach(id => {
        const a = Math.max(0, +(featureWeights[id] ?? 1));
        w[id] = W > 0 && inner > 0 ? W * a / inner : 0;
      });
    });
    return w;
  }

  /** Score every cell. Returns {ranked, partial, excluded}; ranked carries position. */
  function scoreCells(manifest, cells, sims, settings) {
    const features = manifest.features;
    const fIndex = {};
    sims.columns.forEach((f, i) => { fIndex[f] = i; });
    const cIndex = {};
    cells.columns.forEach((c, i) => { cIndex[c] = i; });
    const w = effectiveWeights(features, settings.categoryWeights, settings.featureWeights || {});
    const required = new Set(settings.requiredFeatures || []);
    (settings.requirements || []).forEach(r => required.add(r.feature));
    const reqs = settings.requirements || [];
    const ranked = [], partial = [], excluded = [];

    for (const row of cells.rows) {
      const id = row[cIndex.id];
      const s = sims.by_id[id];
      if (!s) continue;
      let num = 0, den = 0, blocked = false;
      const missing = [];
      for (const f of features) {
        const sv = s[fIndex[f.id]], wf = w[f.id];
        if (sv === null || sv === undefined) {
          if (wf > 0 || required.has(f.id)) { blocked = true; missing.push(f.id); }
          continue;
        }
        num += wf * sv; den += wf;
      }
      const failed = [];
      let unevaluable = false;
      for (const r of reqs) {
        const v = row[cIndex[r.feature]];
        if (v === null || v === undefined) unevaluable = true;
        else if (v !== r.equals) failed.push(r);
      }
      const item = { id, lat: row[cIndex.lat], lon: row[cIndex.lon], score: den > 0 ? num / den : null,
                     missing, failed, row, sims: s };
      if (failed.length) excluded.push(item);
      else if (blocked || unevaluable) partial.push(item);
      else ranked.push(item);
    }
    const key = x => Math.round(x.score * 1e12) / 1e12;
    ranked.sort((a, b) => (key(b) - key(a)) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    ranked.forEach((x, i) => { x.position = i + 1; });
    return { ranked, partial, excluded, weights: w };
  }

  /** Category scores for one cell (weighted by in-category feature weights). */
  function categoryScores(manifest, item, featureWeights) {
    const out = {};
    const fIndex = {};
    manifest.features.forEach((f, i) => { fIndex[f.id] = i; });
    manifest.categories.forEach(c => {
      let num = 0, den = 0;
      manifest.features.filter(f => f.category === c.id).forEach(f => {
        const sv = item.sims[fIndex[f.id]], a = Math.max(0, +((featureWeights || {})[f.id] ?? 1));
        if (sv !== null && sv !== undefined && a > 0) { num += a * sv; den += a; }
      });
      out[c.id] = den > 0 ? num / den : null;
    });
    return out;
  }

  /** A site card: what matches, partly, does not; missing data. */
  function card(manifest, item, settings) {
    const t = manifest.thresholds || { strong_at_least: 75, weak_at_most: 40 };
    const cs = categoryScores(manifest, item, settings.featureWeights);
    const active = c => +(settings.categoryWeights[c] || 0) > 0;
    const groups = { matches: [], partial: [], mismatches: [] };
    manifest.categories.forEach(c => {
      const v = cs[c.id];
      if (v === null || !active(c.id)) return;
      const pct = Math.round(v * 1000) / 10;
      const g = pct >= t.strong_at_least ? 'matches' : pct > t.weak_at_most ? 'partial' : 'mismatches';
      groups[g].push({ id: c.id, label: c.label, score: pct });
    });
    Object.values(groups).forEach(a => a.sort((x, y) => y.score - x.score));
    return { score: item.score === null ? null : Math.round(item.score * 1000) / 10, categories: cs, ...groups,
             missing: item.missing, failed: item.failed };
  }

  return { effectiveWeights, scoreCells, categoryScores, card };
});
