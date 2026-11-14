# Mathematical model — `analogue_engine` v0.2.0

Model id: `analogue_engine.adapted_gower`, version `0.2.0`.

This document states the equations, the assumptions behind them, the
alternatives we did not take and the sources consulted. **Software
verification (tests passing on synthetic fixtures) is not scientific
validation.** Variables, tau values and profiles still need justification and
review by the science/data team.

## 1. Pipeline

```
input records ─► comparability (per feature) ─► discrepancies ─► similarities
             ─► fixed weights ─► S_obs, coverage, constraints ─► category ─► ranking
```

| Step | Function | File |
|---|---|---|
| Parse & reject malformed input | `Site/Measurement/Profile.from_dict` | `models.py` |
| Validate profile vs target, fix weights | `resolve_profile`, `compute_effective_weights` | `resolution.py` |
| Comparability mask m_j | `check_comparability` | `comparability.py` |
| Discrepancy and similarity | `clipped_linear` | `comparators.py` |
| Aggregate, constraints, category | `_compare_resolved` | `engine.py` |
| Order and separate | `rank` | `engine.py` |
| Stability | `sensitivity_analysis` | `sensitivity.py` |

## 2. What each number means

* **measurement** `x_j` (candidate), `t_j` (target): a physical value with a
  definition, canonical unit, method/version and spatial (temporal) support.
* **tau** `τ_j > 0`: the difference, in the canonical unit, that *exhausts*
  the similarity of component j. It is not measurement error, a safety margin
  or an acceptance threshold.
* **weight**: priority of a comparison. Two levels: dimension weight `W_g` and
  internal weight `a_j`.
* **constraint**: a requirement that cannot be compensated by good scores in
  other features.

We look for *closeness to the target*, never for "bigger is better". A
deliberately harder test site would be a different target, not a hidden
change in what a weight means.

## 3. Scalar comparator (adapted Gower)

For a feature that is comparable in both sites:

```
Δ_j = x_j − t_j            (signed, kept in the output)
|Δ_j|                       (kept in the output)
d_j = min(1, |Δ_j| / τ_j)   (normalised discrepancy)
s_j = 1 − d_j               (similarity in [0, 1])
```

Properties (tested): s_j = 1 iff Δ_j = 0; s_j is non-increasing in |Δ_j|;
symmetric in the sign of Δ_j; saturates at 0 for |Δ_j| ≥ τ_j while Δ_j still
records how different the sites are.

**Difference from standard Gower (1971, §2.2(c)).** Gower divides by the
range R_k "in the population or the sample". Using the sample range would make
every score depend on which candidates are in the catalogue (adding one
extreme site would change everyone's score). We instead use a scale τ_j fixed
by the profile version, and clip at 1 because |Δ| can exceed τ. Consequence
(tested): adding or filtering candidates never changes existing scores.

## 3b. Other comparators (v0.2)

All comparators return s in [0, 1], give 1 for identical values and never
increase with the difference. They plug into the same aggregation (§5).

| Comparator | kind | Similarity | Source / note |
|---|---|---|---|
| `clipped_linear_v1` with `range` | scalar | 1 − min(1, \|x − t\| / (max − min)) | Min-max with **fixed** bounds: (x−min)/(max−min) − (t−min)/(max−min) = (x−t)/(max−min), the min cancels. Gower §2.2(c) R_k = range |
| `log_ratio_v1` | scalar > 0 | 1 − min(1, \|log10 x − log10 t\| / τ), τ in decades | Quantities spanning orders of magnitude (crater density, wt% H, pressure). Undefined for x ≤ 0 → candidate excluded with `comparison_failed:non_positive_value` |
| `boolean_match_v1` | boolean | 1 if equal else 0 (false/false counts) | Gower §2.1 "alternatives", Table 2 |
| `categorical_match_v1` | categorical | 1 if same category else 0 | Gower §2.2(b) |
| `jaccard_v1` | set | \|A∩B\| / \|A∪B\|; joint absences ignored; ∅ vs ∅ → 1 (convention) | Gower §2.3, S_J = a/(a+b+c); Jaccard (1912) |
| `cosine_v1` | composition | a·b / (\|a\| \|b\|), non-negative so in [0, 1] | Compares proportions, not amounts. Compositions are constrained (sum to 1); log-ratio methods (Aitchison 1982) are the rigorous alternative. Zero vector → undefined → excluded |

Choosing between boolean (false/false = match) and Jaccard (joint absence
ignored) is Gower's dichotomous-vs-alternative question (§2.1, §4.1
discussion) and belongs to science. Using cosine and Jaccard on the same
minerals double-counts P7.

## 4. Weights

Raw weights may be un-normalised. Within each level:

```
W̃_g = W_g / Σ_h W_h          ã_j = a_j / Σ_{k∈g} a_k          w_j = W̃_g · ã_j
```

Rules: no negative or non-finite weight; Σ W_h > 0; a dimension with
W_g > 0 needs Σ a_k > 0; a dimension with W_g = 0 gives w_j = 0. With one
dimension `dimension_weights` may be omitted (W = 1); with several it is
mandatory, so a dimension cannot gain importance merely by having more
variables (Gower §4.1 discusses the analogous problem of secondary characters
outweighing primary ones). Effective weights are computed **once per
search, before any candidate is examined**, and never renormalised per
candidate.

Duplicating a descriptor and splitting its weight leaves score and coverage
unchanged (tested), but duplicating it with full weight would double its
influence. The engine therefore refuses a feature listed twice in a profile.

## 4b. Per-dimension breakdown and declared limitations

For each dimension g, S_g = Σ_{j∈g} a_j m_j s_j / Σ_{j∈g} a_j m_j (internal
weights; null if nothing comparable) and coverage_g = Σ_{j∈g} a_j m_j / Σ_{j∈g} a_j.
For a complete candidate S = Σ_g W̃_g S_g (tested). This answers the
challenge's "excellent geological analog but a poor temperature analog".
Profiles may carry `declared_limitations` (gravity, vacuum, thin atmosphere,
radiation…): copied to every result, never scored.

## 4c. Weight calibration against known analogs (`calibration.py`)

For complete candidates S_i(w) = Σ_j w_j s_ij is linear in the effective
weights. Given known analogs P (accepted by experts) and the other,
unlabelled candidates N, `calibrate_weights` minimises over the simplex:

    L(w) = mean_{p∈P, n∈N} softplus(−(S_p − S_n)/T) + λ · KL(w ‖ w0)

* The pairwise logistic ranking loss pushes known analogs above other
  candidates. T = 0.05 is in score units.
* The KL anchor keeps w near the starting weights w0 (from Science or an
  AI-written profile). With few labels this is what prevents memorisation.
* The optimiser is exponentiated gradient (mirror descent). Each step solves
  the KL term exactly: log w ∝ (log w_t − η g + ηλ log w0)/(1 + ηλ), which is
  stable for any λ. It is deterministic and keeps w > 0 with Σ w = 1.
* Only features that start with a positive weight are tuned. τ, comparators,
  requirements and data are unchanged. The output profile is `<version>-cal`
  with `calibration_status: provisional`.
* Leave-one-out validation: each known analog is hidden, the weights are
  re-tuned on the rest, and the hidden one's rank is recorded. All reported
  ranks come from re-running the engine with the calibrated profile.
* Unlabelled candidates are not assumed to be bad; the best-ranked ones are
  the new-analog suggestions.

Synthetic check (`examples/calibration/`): there are 126 candidates and 6
invented analogs that resemble the reference only in terrain and mineralogy.
Those two categories go from 0.167 to 0.242 and 0.230. The analogs' mean
rank goes from the top 14.9 % to the top 4.1 %. Leave-one-out improves the
hidden ones that started far down (#54→#28, #33→#14, #20→#4); those already
at the top stay or drop one place.

## 4d. Rankings over time (`timeline.py`)

`rank_over_years` ranks one fixed target with one fixed profile against each
year's Earth sites, which can be observations or projections. Because τ,
weights and requirements are fixed and no score depends on other sites, the
change in a site's score between years comes only from its own data. Per
site it reports scores and positions by year, the change (last − first), a
least-squares trend per decade and a status: gaining or losing (|change| ≥
threshold), stable, entering or leaving (present in only one end year). It
also lists which sites entered or left the top k. Projection uncertainty is
not propagated.

## 4e. First run on the Data team's 1° grid (Gale)

`examples/real_data/` maps the Data team's grid to the Science P1–P10
decisions:
* P1: regional relief from a 3×3 block of cells (provisional, coarse).
* P2: ground temperature swing and cold minimum.
* P3: apparent thermal inertia as a within-planet percentile.
* P4: albedo.
* P8: rock group, at half weight.
* P9: impact yes/no.
* P10: ground ice yes/no.
* P5, P6 and P7 are not scored.

The pre-filter keeps dry, bare land: precipitation < 500 mm/yr, NDVI < 0.2,
not ice or water. That leaves 3561 Earth cells; 3148 have complete data.

* **Results:** the best score is 73/100. The top cell is in the Atacama
  (−23.5, −68.5). Kara-Kul ranks #2, the Atacama reference cell #222 (top
  7 %) and Arizaro #285. The polar sites rank low, as Science expected for
  ice-free Gale.
* **Calibration** on Atacama, Arizaro and Kara-Kul changes the weights only
  modestly: Atacama goes to #154 (leave-one-out #167) and Arizaro to #214
  (leave-one-out #225).
* **Data issues found:**
  * Gale's rock group is `impact`, a class that does not exist on Earth, so
    P8 scores 0 for every Earth cell.
  * The Earth permafrost source covers only the northern hemisphere, so the
    Dry Valleys get no ground ice.

## 5. Comparability, missing data and coverage

Each pair of measurements passes a per-feature protocol check:

| Outcome | m_j | Meaning |
|---|---|---|
| `compared` | 1 | same canonical unit, required metadata present, must-match fields equal or explicitly declared equivalent, body policy satisfied |
| `missing` | 0 | no value, status `missing`, or quality `flagged` (insufficient information) |
| `comparability_pending` | 0 | required metadata absent (insufficient information) |
| `incompatible` | 0 | unit mismatch, method/version/support mismatch, or cross-body not allowed |

Order of checks: missing/flagged → unit → body → a present `must_match`
field that differs (`incompatible`, decisive) → absent required metadata
(`pending`). A numeric failure inside the comparator (difference overflowing
to infinity) marks only that component `incompatible`
(`comparison_failed:...`); it never aborts the search.

A large physical difference is **not** missing data: it is compared and gives
s_j = 0 with full coverage (fixture site D).

With effective weights w (Σw = 1):

```
C     = Σ_j w_j m_j                       (weighted coverage, not statistical confidence)
S_obs = Σ_j w_j m_j s_j / Σ_j w_j m_j      (null when C = 0)
```

This is Gower's eq. (5) with δ_ijk = m_j. Implementation note: the code
computes `C = fsum(w·m) / fsum(w)` and `S_obs = fsum(w·m·s) / fsum(w·m)` with
`math.fsum` (exactly rounded, independent of feature order). Mathematically
fsum(w) = 1; dividing by it only removes rounding drift so that a complete
candidate has coverage exactly 1.0 and the identity comparison scores exactly
1.0. Displayed contributions are `w_j m_j s_j / C`, which sum to S_obs; for a
complete candidate this equals w_j s_j.

### Categories and ranking policy

A component is **blocking** if it has positive weight, is a required feature,
or is used by a constraint. Then:

1. any constraint violated → `requirement_not_met` (excluded);
2. else any blocking component `incompatible` → `incompatible` (excluded);
3. else any blocking component `missing`/`pending` (or a constraint unevaluable) → `partial`;
4. else → `complete` (ranked).

Only complete candidates are ordered, by S_obs descending (rounded to 12
decimals for the ordering key only) then by `candidate_id`. Ties are reported
and imply no scientific preference. Partial and excluded candidates are
returned separately, sorted by id, with S_obs, coverage and reasons. Their
S_obs is computed on a reduced basis and is not comparable with complete
scores: fixture site C has S_obs = 1 but is not placed above A or B.

This policy is conservative, not a theorem of scientific optimality. If real
coverage turns out to be poor, the remedy is an explicit reduced profile
(`restrict_profile`, new version) applied to all candidates, never a silent
mix of comparison bases.

Gower (1971, §3 and Appendix) proves positive semi-definiteness of the
similarity matrix only when there are no missing values; this is an additional
reason not to mix complete and partial scores in one ordering.

### Request-level errors vs per-candidate outcomes

Exceptions (whole request invalid): malformed numbers (NaN, inf, bool),
negative weights, zero sums, τ ≤ 0, τ unit ≠ canonical unit, unknown features,
target lacking a valid value or protocol metadata for **any** active feature
(including zero-weight ones), target unit ≠ canonical, synthetic/real mixing,
duplicate ids. Per-candidate problems never raise; they are reported.

## 6. Constraints

`max_abs_difference` (|Δ| ≤ L), `min_value` (x ≥ L), `max_value` (x ≤ L), with
L in the canonical unit (declared in the constraint's `unit` field and
checked), supplied by the profile. A value within rel. 1e-9 / abs. 1e-12 of
L counts as on the limit (satisfied), so floating-point noise such as
|0.4 − 0.1| = 0.30000000000000004 cannot decide a requirement. A constraint on a
non-comparable component is `unevaluable` (insufficient information).
Requirements stay in force when the feature's weight is 0.

## 7. Sensitivity

`sensitivity_analysis` multiplies, one at a time, each positive internal
weight (and each dimension weight when there are several dimensions) and each
τ by 0.8 and 1.2, renormalises, re-ranks (skipping perturbations that are
no-ops by construction: the weight of the only positive-weight feature of a
dimension, and τ of zero-weight features), and records order changes, moved
candidates and score changes. Fixture result: no order change for either
profile. This is stability under assumption changes, not the probability that
a site is valid, and stability does not prove correctness.

## 8. Body and scale

The engine never branches on body or site names. Whether a feature may be
compared across bodies is a per-feature protocol flag
(`cross_body_comparable`) decided by science. Scale enters through
`spatial_support` identifiers that must match (or be declared equivalent).
Equal nominal resolution does not prove equal effective resolution, so the
engine never infers equivalence.

## 9. Not implemented on purpose (v0.2)

Slope/VRM computation from rasters (inputs from the data team), unit
conversion, global search, ML/embeddings, climate simulation, multi-site
planning, spectra, LLM-generated scores, uncertainty propagation (uncertainty
is carried through but unused; unknown uncertainty stays null).

Implemented in v0.2: categorical, boolean, Jaccard, cosine, log ratio and
fixed-range min-max. Still future extensions via `comparators.COMPARATORS`:
Wasserstein distance for distributions, partial similarity between
categories (a category-similarity table), log-ratio (Aitchison) distances for
compositions. Do not add a
distribution comparator *and* medians/percentiles of the same variable
without reviewing double counting.

## 10. Alternatives considered

| Alternative | Why not in v0 |
|---|---|
| Standard Gower with sample range R_k | Catalogue-dependent scores |
| z-scores / Mahalanobis | Need population statistics from the catalogue; less interpretable per component |
| Gaussian kernel exp(−Δ²/2τ²) | Smooth and never exactly 0; reasonable future option (same τ semantics would need restating) |
| Renormalising weights over available features and ranking everyone together | Silently mixes bases; partial sites with one good feature would top the list |
| Imputing missing values | Fabricates measurements |

## 11. Sources consulted (and what exactly was read)

* **Gower, J. C. (1971).** A General Coefficient of Similarity and Some of Its
  Properties. *Biometrics* 27(4), 857–871. https://doi.org/10.2307/2528823.
  Read from the full-text PDF: §1 Introduction, §2.1–2.3 (definition,
  eqs. 1–2, quantitative score 1 − |x_i − x_j|/R_k, choice of range over
  standard deviation), §3 opening (p.s.d. without missing values), §4 and
  §4.1 (weights, eqs. 5–6, hierarchic characters). Proofs in the Appendix not
  read. Used for: per-character scores combined over comparable characters,
  δ indicator for impossible comparisons, weighting. Our fixed τ, clipping,
  two-level weights and complete-only ranking are **our adaptations**, not
  Gower's.
* **R `cluster::daisy` documentation**,
  https://search.r-project.org/CRAN/refmans/cluster/html/daisy.html (read
  online during this session): Gower metric as weighted mean of per-variable
  dissimilarities over non-missing pairs; range scaling; NA when no variable
  is comparable. Consistent with Gower §2.2 and §4.
* **Foucher, F. et al. (2021).** Definition and use of functional analogues in
  planetary exploration. *Planetary and Space Science* 197, 105162.
  https://doi.org/10.1016/j.pss.2021.105162. Read from the open-access PDF
  (full text): abstract, §1 Introduction, Fig. 1, §2.1.5 Engineering
  analogue sites. Used for: analogues should be chosen for the properties
  relevant to the intended use, not by overall resemblance — hence
  task-specific profiles and explicit limitations. It does **not** supply our
  weights or validate the algorithm.
* **Sappington, Longshore & Thompson (2007).** Quantifying Landscape
  Ruggedness for Animal Habitat Analysis. *J. Wildlife Management*.
  https://doi.org/10.2193/2005-723. Only the abstract (USGS record) was read:
  VRM, built from the dispersion of surface normals, is less correlated with
  slope than earlier indices. Habitat conclusions are not used.
* **Ilich et al. (2023).** MultiscaleDTM, *Transactions in GIS*,
  https://doi.org/10.1111/tgis.13067. **Not accessible in this session**
  (HTTP 403). The VRM formula VRM = 1 − ‖Σ n_i‖ / N (unit normals n_i) and the
  reference to its eq. (5) come from the project brief and remain to be
  checked against the original. Consequence for the code: none — VRM is an
  input from the data team.
* **Jaccard, P. (1912).** The distribution of the flora in the alpine zone.
  *New Phytologist* 11(2), 37–50. Only the bibliographic record was checked
  (journal, volume, pages); the DOI was not confirmed and the paper was not
  read. The formula used is the one in Gower §2.3.
* **Aitchison, J. (1982).** The statistical analysis of compositional data.
  *JRSS B* 44(2), 139–160. https://doi.org/10.1111/j.2517-6161.1982.tb01195.x.
  Bibliographic record checked only; cited as the reason cosine on
  compositions is a pragmatic choice, not the rigorous one.
* **Stern et al. (2025)**, reserve reading, not consulted.
