"""Loading a request bundle (feature definitions, sites, profiles) from JSON.

Strict: NaN/Infinity literals in the JSON text are rejected at parse time.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import InvalidRequestError
from .models import FeatureDefinition, Profile, Site, feature_definitions_by_id

SCHEMA_VERSION = "analogue_engine.bundle.v0"


def _reject_constant(name: str) -> Any:
    raise InvalidRequestError(
        f"JSON constant {name} is not allowed; use null with status 'missing'",
        code="non_finite_number",
    )


def loads_strict(text: str) -> Any:
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise InvalidRequestError(f"invalid JSON: {exc}", code="invalid_json") from None


def _list(data: Mapping[str, Any], key: str) -> list:
    value = data.get(key, [])
    if not isinstance(value, list):
        raise InvalidRequestError(f"bundle: '{key}' must be a list", code="invalid_type")
    return value


@dataclass(frozen=True)
class Bundle:
    feature_definitions: dict[str, FeatureDefinition]
    sites: dict[str, Site]
    profiles: dict[str, Profile]


def parse_bundle(data: Mapping[str, Any]) -> Bundle:
    if not isinstance(data, Mapping):
        raise InvalidRequestError("bundle: expected a JSON object", code="invalid_type")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise InvalidRequestError(
            f"unsupported schema_version {data.get('schema_version')!r}; expected {SCHEMA_VERSION!r}",
            code="unsupported_schema",
        )
    definitions = feature_definitions_by_id(_list(data, "feature_definitions"))
    sites: dict[str, Site] = {}
    for raw in _list(data, "sites"):
        site = Site.from_dict(raw)
        if site.id in sites:
            raise InvalidRequestError(f"duplicate site id '{site.id}'", code="duplicate_site")
        sites[site.id] = site
    profiles: dict[str, Profile] = {}
    for raw in _list(data, "profiles"):
        profile = Profile.from_dict(raw)
        if profile.id in profiles:
            raise InvalidRequestError(f"duplicate profile id '{profile.id}'", code="duplicate_profile")
        profiles[profile.id] = profile
    return Bundle(definitions, sites, profiles)


def load_bundle(path: str | Path) -> Bundle:
    return parse_bundle(loads_strict(Path(path).read_text(encoding="utf-8")))


# --------------------------------------------------------------------------- CSV (long format)

CSV_COLUMNS = (
    "site_id", "body", "data_mode", "site_name", "area_ref",
    "feature_id", "value", "status", "unit",
    "method_id", "method_version", "spatial_support", "temporal_support",
    "source_ref", "uncertainty",
)
EMPTY_SET_TOKEN = "[]"


def _csv_value(text: str, definition: FeatureDefinition, where: str) -> Any:
    """Decode a CSV cell according to the feature kind (empty cell -> null)."""
    text = text.strip()
    if text == "":
        return None
    kind = definition.kind
    if kind == "scalar":
        try:
            number = float(text)
        except ValueError:
            raise InvalidRequestError(f"{where}: '{text}' is not a number", code="value_type_mismatch") from None
        return number  # NaN/inf are rejected by Measurement.from_dict
    if kind == "boolean":
        low = text.lower()
        if low in ("true", "1", "yes"):
            return True
        if low in ("false", "0", "no"):
            return False
        raise InvalidRequestError(f"{where}: '{text}' is not true/false", code="value_type_mismatch")
    if kind == "categorical":
        return text
    if kind == "set":
        if text == EMPTY_SET_TOKEN:
            return []
        items = [item.strip() for item in text.split(";")]
        if any(not item for item in items):
            raise InvalidRequestError(
                f"{where}: empty item in set '{text}' (use '{EMPTY_SET_TOKEN}' for an empty set)",
                code="value_type_mismatch",
            )
        return items
    if kind == "composition":
        out: dict[str, float] = {}
        for part in text.split(";"):
            if part.count("=") != 1:
                raise InvalidRequestError(
                    f"{where}: composition must look like 'basalt=0.5;clay=0.2'", code="value_type_mismatch"
                )
            key, number = (s.strip() for s in part.split("="))
            if key in out:
                raise InvalidRequestError(f"{where}: component '{key}' given twice", code="value_type_mismatch")
            try:
                out[key] = float(number)
            except ValueError:
                raise InvalidRequestError(f"{where}: '{number}' is not a number", code="value_type_mismatch") from None
        return out
    raise InvalidRequestError(f"{where}: unsupported kind '{kind}'", code="invalid_enum")


def load_sites_csv(path: str | Path, feature_definitions: Any) -> dict[str, Site]:
    """Read sites from a long-format CSV: one row per (site, feature).

    Site-level columns (body, data_mode, site_name, area_ref) must be identical
    on every row of the same site. Value encoding by feature kind:
    scalar ``12.5`` | boolean ``true/false`` | categorical ``evaporite`` |
    set ``basalt;clay`` (``[]`` = empty set) | composition ``basalt=0.5;clay=0.2``.
    An empty value cell means missing (use status ``missing``).
    """
    definitions = feature_definitions_by_id(feature_definitions)
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing_cols = [c for c in ("site_id", "body", "data_mode", "feature_id", "value", "status", "unit")
                        if c not in (reader.fieldnames or [])]
        if missing_cols:
            raise InvalidRequestError(f"CSV is missing columns {missing_cols}", code="missing_field")
        site_fields: dict[str, dict[str, Any]] = {}
        measurements: dict[str, list[dict[str, Any]]] = {}
        for line, row in enumerate(reader, start=2):
            where = f"{Path(path).name}:{line}"
            sid = (row.get("site_id") or "").strip()
            fid = (row.get("feature_id") or "").strip()
            if fid not in definitions:
                raise InvalidRequestError(f"{where}: unknown feature_id '{fid}'", code="unknown_feature")
            fields = {
                "id": sid,
                "body": (row.get("body") or "").strip(),
                "data_mode": (row.get("data_mode") or "").strip(),
                "name": (row.get("site_name") or "").strip() or None,
                "area_ref": (row.get("area_ref") or "").strip() or None,
            }
            previous = site_fields.setdefault(sid, fields)
            if previous != fields:
                raise InvalidRequestError(
                    f"{where}: site-level columns for '{sid}' differ from an earlier row", code="inconsistent_site"
                )
            uncertainty_text = (row.get("uncertainty") or "").strip()
            try:
                uncertainty = float(uncertainty_text) if uncertainty_text else None
            except ValueError:
                raise InvalidRequestError(
                    f"{where}: uncertainty '{uncertainty_text}' is not a number", code="invalid_number"
                ) from None
            measurement = {
                "feature_id": fid,
                "value": _csv_value(row.get("value") or "", definitions[fid], where),
                "status": (row.get("status") or "").strip(),
                "unit": (row.get("unit") or "").strip(),
                "uncertainty": uncertainty,
            }
            for key in ("method_id", "method_version", "spatial_support", "temporal_support", "source_ref"):
                measurement[key] = (row.get(key) or "").strip() or None
            measurements.setdefault(sid, []).append(measurement)
    return {sid: Site.from_dict({**site_fields[sid], "measurements": measurements[sid]}) for sid in site_fields}


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, tuple):
        return ";".join(value) if value else EMPTY_SET_TOKEN
    if isinstance(value, dict):
        return ";".join(f"{k}={v!r}" for k, v in value.items())
    return str(value)


def write_sites_csv(sites: Iterable[Site], path: str | Path) -> None:
    """Inverse of ``load_sites_csv`` (used to produce templates)."""
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for site in sites:
            for m in site.measurements.values():
                writer.writerow([
                    site.id, site.body, site.data_mode, site.name or "", site.area_ref or "",
                    m.feature_id, _cell(m.value), m.status, m.unit,
                    m.method_id or "", m.method_version or "", m.spatial_support or "", m.temporal_support or "",
                    m.source_ref or "", "" if m.uncertainty is None else repr(m.uncertainty),
                ])
