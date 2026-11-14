"""Bridge to the Planeology backend (branch `backend`, module `integration`).

The backend keeps one row per location with one column per parameter (a
"wide" table, e.g. ``data/sample_locations.csv``) and its
``run_assessment(target_id, mission_type, similarity_scores)`` expects
``{location_id: score in 0..100}``.

This module converts in both directions without importing the backend or
pandas:

* ``sites_from_wide_records``: wide rows (``df.to_dict("records")`` or
  ``csv.DictReader``) + per-column metadata -> engine ``Site`` objects;
* ``backend_payload``: engine ``RankingResult`` -> the ``similarity_scores``
  dict plus what the backend would otherwise drop (partial / excluded
  candidates with reasons, per-dimension scores, declared limitations).
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping

from .errors import InvalidRequestError
from .io import _csv_value
from .models import FeatureDefinition, Site, feature_definitions_by_id
from .results import RankingResult

SCORE_SCALE = 100.0  # engine scores are in [0, 1]; the backend uses [0, 100]

_METADATA_KEYS = ("method_id", "method_version", "spatial_support", "temporal_support", "source_ref")


def _is_blank(value: Any) -> bool:
    """Empty cell: None, '' or a float NaN (how pandas represents empty cells)."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return isinstance(value, float) and math.isnan(value)


def _coerce_cell(value: Any, definition: FeatureDefinition, where: str) -> Any:
    """Decode a cell by feature kind: strings use the CSV encoding
    (``basalt;clay``, ``basalt=0.5;...``, ``true``); numpy scalars become
    plain Python; other Python values are passed through unchanged."""
    if isinstance(value, str):
        return _csv_value(value, definition, where)
    if hasattr(value, "item") and not isinstance(value, (list, tuple, dict)):
        return value.item()
    return value


def sites_from_wide_records(
    records: Iterable[Mapping[str, Any]],
    column_specs: Mapping[str, Mapping[str, Any]],
    feature_definitions: Any,
    *,
    data_mode: str,
    id_column: str = "location_id",
    body_column: str = "planetary_body",
    name_column: str | None = "location_name",
    area_ref_column: str | None = None,
) -> dict[str, Site]:
    """Build engine sites from a wide table.

    ``column_specs`` maps a table column to its engine metadata, e.g.::

        {"terrain_slope": {"feature_id": "slope_deg", "unit": "deg",
                           "method_id": "...", "method_version": "1",
                           "spatial_support": "dem_20m_3x3",
                           "source_ref": "dataset citation"}}

    Columns not listed are ignored (coordinates, names...). An empty cell
    (None, '' or pandas NaN) becomes a *missing* measurement, never 0.
    ``data_mode`` ('synthetic' or 'real') is explicit for the whole table.
    """
    definitions = feature_definitions_by_id(feature_definitions)
    for column, spec in column_specs.items():
        if not isinstance(spec, Mapping) or "feature_id" not in spec or "unit" not in spec:
            raise InvalidRequestError(
                f"column_specs['{column}'] needs at least 'feature_id' and 'unit'", code="missing_field"
            )
        if spec["feature_id"] not in definitions:
            raise InvalidRequestError(
                f"column_specs['{column}'] maps to unknown feature '{spec['feature_id']}'", code="unknown_feature"
            )
    sites: dict[str, Site] = {}
    for index, row in enumerate(records):
        where = f"row {index}"
        site_id = row.get(id_column)
        if _is_blank(site_id):
            raise InvalidRequestError(f"{where}: empty '{id_column}'", code="missing_field")
        site_id = str(site_id).strip()
        if site_id in sites:
            raise InvalidRequestError(f"duplicate location id '{site_id}'", code="duplicate_site")
        measurements = []
        for column, spec in column_specs.items():
            if column not in row:
                raise InvalidRequestError(f"{where}: column '{column}' not found", code="missing_field")
            raw = row[column]
            blank = _is_blank(raw)
            m = {
                "feature_id": spec["feature_id"],
                "value": None if blank else _coerce_cell(raw, definitions[spec["feature_id"]], f"{where}.{column}"),
                "status": "missing" if blank else "valid",
                "unit": spec["unit"],
                "uncertainty": None,
            }
            for key in _METADATA_KEYS:
                m[key] = spec.get(key)
            measurements.append(m)
        name = None if name_column is None or _is_blank(row.get(name_column)) else str(row[name_column])
        area_ref = None if area_ref_column is None or _is_blank(row.get(area_ref_column)) else str(row[area_ref_column])
        sites[site_id] = Site.from_dict(
            {
                "id": site_id,
                "body": str(row.get(body_column, "")).strip(),
                "data_mode": data_mode,
                "name": name,
                "area_ref": area_ref,
                "measurements": measurements,
            }
        )
    return sites


def _scaled(value: float | None) -> float | None:
    return None if value is None else value * SCORE_SCALE


def backend_payload(result: RankingResult) -> dict[str, Any]:
    """Convert a ranking into what ``integration.run_assessment`` consumes.

    * ``similarity_scores``: {location_id: 0..100}, **ranked candidates only**.
      Partial and excluded candidates are deliberately absent: their observed
      score uses a different basis and must not be sorted with these.
    * ``ranked_order``: the engine's order (ties broken by id).
    * ``not_ranked``: {location_id: {category, score_observed_0_100, coverage,
      reasons}}, so the UI can show "insufficient data" / "requirement not met"
      instead of silently dropping the site.
    * ``dimension_scores``: {location_id: {dimension: 0..100 or null}}.
    * ``coverage``: {location_id: 0..1} (weighted; the engine's definition).
    * ``declared_limitations``, ``warnings``, provenance fields.
    """
    ranked = [e.result for e in result.ranked]
    others = list(result.partial) + list(result.excluded)
    everyone = ranked + others
    return {
        "similarity_scores": {r.candidate_id: _scaled(r.score_observed) for r in ranked},
        "ranked_order": [r.candidate_id for r in ranked],
        "not_ranked": {
            r.candidate_id: {
                "category": r.category,
                "score_observed_0_100": _scaled(r.score_observed),
                "coverage": r.coverage,
                "reasons": list(r.reasons),
            }
            for r in others
        },
        "dimension_scores": {
            r.candidate_id: {d.dimension: _scaled(d.score_observed) for d in r.dimensions} for r in everyone
        },
        "coverage": {r.candidate_id: r.coverage for r in everyone},
        "declared_limitations": list(result.declared_limitations),
        "warnings": list(result.warnings),
        "target_id": result.target_id,
        "profile_id": result.profile_id,
        "profile_version": result.profile_version,
        "model_id": result.model_id,
        "model_version": result.model_version,
        "data_mode": result.data_mode,
        "calibration_status": result.calibration_status,
        "score_scale": "0-100 (engine score x 100)",
    }
