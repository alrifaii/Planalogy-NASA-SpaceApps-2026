"""Input records: sites, measurements, feature definitions and profiles.

All records are immutable dataclasses with a strict ``from_dict`` parser.
Parsers reject NaN/inf, booleans used as numbers, unknown enum values and
internally inconsistent records. They never fill in defaults that change
scientific meaning (for example, a missing value is never turned into 0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .errors import InvalidRequestError, ProfileError

DATA_MODES = ("synthetic", "real")
MEASUREMENT_STATUSES = ("valid", "missing", "flagged")
CALIBRATION_STATUSES = ("uncalibrated", "provisional", "science_reviewed")
METADATA_FIELDS = ("method_id", "method_version", "spatial_support", "temporal_support")
FEATURE_KINDS = ("scalar", "boolean", "categorical", "set", "composition")
KINDS_WITH_VOCABULARY = ("categorical", "set", "composition")
NUMERIC_CONSTRAINT_TYPES = ("max_abs_difference", "min_value", "max_value")
CONSTRAINT_TYPES = NUMERIC_CONSTRAINT_TYPES + ("equals",)


# --------------------------------------------------------------------------- helpers


def _finite_number(value: Any, where: str) -> float:
    """Return ``value`` as float or raise. Rejects bool, NaN and +/-inf."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidRequestError(
            f"{where}: expected a finite number, got {value!r}",
            code="invalid_number",
            where=where,
        )
    number = float(value)
    if not math.isfinite(number):
        raise InvalidRequestError(
            f"{where}: NaN and infinite values are not allowed (got {value!r}); "
            "encode an absent measurement as null with status 'missing'",
            code="non_finite_number",
            where=where,
        )
    return number


def _optional_number(value: Any, where: str) -> float | None:
    return None if value is None else _finite_number(value, where)


def _required_str(data: Mapping[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestError(
            f"{where}: field '{key}' is required and must be a non-empty string",
            code="missing_field",
            where=where,
            field=key,
        )
    return value


def _optional_str(data: Mapping[str, Any], key: str, where: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidRequestError(
            f"{where}: field '{key}' must be a non-empty string or null",
            code="invalid_field",
            where=where,
            field=key,
        )
    return value


def _string_list(data: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = data.get(key, []) or []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise InvalidRequestError(
            f"{where}: '{key}' must be a list of non-empty strings", code="invalid_type", where=where
        )
    return tuple(value)


def _enum(value: Any, allowed: Iterable[str], where: str, key: str) -> str:
    allowed = tuple(allowed)
    if value not in allowed:
        raise InvalidRequestError(
            f"{where}: '{key}' must be one of {list(allowed)}, got {value!r}",
            code="invalid_enum",
            where=where,
            field=key,
        )
    return value


def _mapping(data: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise InvalidRequestError(f"{where}: expected an object", code="invalid_type", where=where)
    return data


# --------------------------------------------------------------------------- values


def parse_value(raw: Any, where: str) -> Any:
    """Parse a JSON value into one of the supported value shapes.

    number -> float (finite), bool -> bool, str -> str, list[str] -> sorted
    tuple (a presence set), object -> dict[str, float >= 0] (a composition).
    Whether the shape fits the feature is checked later (``check_value``).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return _finite_number(raw, where)
    if isinstance(raw, str):
        if not raw.strip():
            raise InvalidRequestError(f"{where}: empty string value", code="invalid_value", where=where)
        return raw
    if isinstance(raw, (list, tuple)):
        if not all(isinstance(x, str) and x.strip() for x in raw):
            raise InvalidRequestError(
                f"{where}: a list value must contain non-empty strings (a presence set)",
                code="invalid_value",
                where=where,
            )
        if len(set(raw)) != len(raw):
            raise InvalidRequestError(f"{where}: duplicated items in set value", code="invalid_value", where=where)
        return tuple(sorted(raw))
    if isinstance(raw, Mapping):
        if not all(isinstance(key, str) for key in raw):
            raise InvalidRequestError(f"{where}: composition keys must be strings", code="invalid_value")
        out: dict[str, float] = {}
        for key in sorted(raw):
            v = _finite_number(raw[key], f"{where}[{key}]")
            if v < 0:
                raise InvalidRequestError(
                    f"{where}[{key}]: composition values must be >= 0 (got {v})", code="invalid_value", where=where
                )
            out[key] = v
        return out
    raise InvalidRequestError(f"{where}: unsupported value {raw!r}", code="invalid_value", where=where)


def value_matches_kind(value: Any, kind: str, categories: tuple[str, ...] | None) -> str | None:
    """Return None if ``value`` fits ``kind``; otherwise a short explanation."""
    if kind == "scalar":
        return None if isinstance(value, float) else "expected a number"
    if kind == "boolean":
        return None if isinstance(value, bool) else "expected true/false"
    if kind == "categorical":
        if not isinstance(value, str):
            return "expected a category string"
        return None if value in (categories or ()) else f"'{value}' is not in the declared categories {list(categories or ())}"
    if kind == "set":
        if not isinstance(value, tuple):
            return "expected a list of present items"
        unknown = [x for x in value if x not in (categories or ())]
        return None if not unknown else f"items {unknown} are not in the declared vocabulary {list(categories or ())}"
    if kind == "composition":
        if not isinstance(value, dict):
            return "expected an object {component: amount}"
        expected = set(categories or ())
        if set(value) != expected:
            return (
                f"composition keys must be exactly {sorted(expected)} "
                f"(missing {sorted(expected - set(value))}, unknown {sorted(set(value) - expected)}); "
                "write 0 explicitly for absent components"
            )
        return None
    return f"unknown kind '{kind}'"


# --------------------------------------------------------------------------- measurement


@dataclass(frozen=True)
class Measurement:
    """One processed value of one feature at one site.

    ``value`` is in ``unit``; the engine requires ``unit`` to equal the
    feature's canonical unit (v0 performs no unit conversion).
    """

    feature_id: str
    value: Any  # float | bool | str | tuple[str, ...] | dict[str, float] | None (see FEATURE_KINDS)
    status: str
    unit: str
    method_id: str | None = None
    method_version: str | None = None
    spatial_support: str | None = None
    temporal_support: str | None = None
    source_ref: str | None = None
    uncertainty: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str = "measurement") -> "Measurement":
        data = _mapping(data, where)
        feature_id = _required_str(data, "feature_id", where)
        where = f"{where}[{feature_id}]"
        status = _enum(data.get("status"), MEASUREMENT_STATUSES, where, "status")
        value = parse_value(data.get("value"), f"{where}.value")
        if status == "valid" and value is None:
            raise InvalidRequestError(
                f"{where}: status 'valid' requires a value; use status 'missing' for absent data",
                code="inconsistent_measurement",
                where=where,
            )
        if status == "missing" and value is not None:
            raise InvalidRequestError(
                f"{where}: status 'missing' must have value null (got {value!r})",
                code="inconsistent_measurement",
                where=where,
            )
        uncertainty = _optional_number(data.get("uncertainty"), f"{where}.uncertainty")
        if uncertainty is not None and uncertainty < 0:
            raise InvalidRequestError(
                f"{where}: uncertainty must be >= 0", code="invalid_number", where=where
            )
        return cls(
            feature_id=feature_id,
            value=value,
            status=status,
            unit=_required_str(data, "unit", where),
            method_id=_optional_str(data, "method_id", where),
            method_version=_optional_str(data, "method_version", where),
            spatial_support=_optional_str(data, "spatial_support", where),
            temporal_support=_optional_str(data, "temporal_support", where),
            source_ref=_optional_str(data, "source_ref", where),
            uncertainty=uncertainty,
        )

    def metadata(self, name: str) -> str | None:
        return getattr(self, name)


# --------------------------------------------------------------------------- site


@dataclass(frozen=True)
class Site:
    """An analysed area (target reference or candidate)."""

    id: str
    body: str
    data_mode: str
    measurements: Mapping[str, Measurement]
    name: str | None = None
    area_ref: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Site":
        data = _mapping(data, "site")
        site_id = _required_str(data, "id", "site")
        where = f"site[{site_id}]"
        raw = data.get("measurements", [])
        if not isinstance(raw, list):
            raise InvalidRequestError(
                f"{where}: 'measurements' must be a list", code="invalid_type", where=where
            )
        measurements: dict[str, Measurement] = {}
        for i, item in enumerate(raw):
            m = Measurement.from_dict(item, f"{where}.measurements[{i}]")
            if m.feature_id in measurements:
                raise InvalidRequestError(
                    f"{where}: duplicate measurement for feature '{m.feature_id}'",
                    code="duplicate_measurement",
                    where=where,
                    feature_id=m.feature_id,
                )
            measurements[m.feature_id] = m
        return cls(
            id=site_id,
            body=_required_str(data, "body", where),
            data_mode=_enum(data.get("data_mode"), DATA_MODES, where, "data_mode"),
            measurements=measurements,
            name=_optional_str(data, "name", where),
            area_ref=_optional_str(data, "area_ref", where),
        )


# --------------------------------------------------------------------------- features


@dataclass(frozen=True)
class ComparabilityProtocol:
    """Per-feature rules deciding whether two measurements may be compared.

    * ``required_metadata``: fields that must be present in both measurements;
      absence means comparability is *pending* (insufficient information).
    * ``must_match``: fields that must be equal (or declared equivalent);
      a difference means the comparison is *incompatible*.
    * ``equivalent_values``: explicit equivalence classes declared by the
      science/data team, e.g. two support identifiers known to be equivalent.
      The engine never infers equivalence on its own.
    * ``cross_body_comparable``: whether target and candidate may lie on
      different bodies. It is a property of the feature definition, decided
      by science; the engine never branches on body names.
    """

    id: str
    required_metadata: tuple[str, ...]
    must_match: tuple[str, ...]
    cross_body_comparable: bool
    equivalent_values: Mapping[str, tuple[frozenset[str], ...]] = field(default_factory=dict)
    description: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "ComparabilityProtocol":
        data = _mapping(data, where)
        protocol_id = _required_str(data, "id", where)

        def field_list(key: str) -> tuple[str, ...]:
            values = data.get(key, [])
            if not isinstance(values, list):
                raise InvalidRequestError(f"{where}.{key}: expected a list", code="invalid_type")
            for v in values:
                _enum(v, METADATA_FIELDS, where, key)
            if len(set(values)) != len(values):
                raise InvalidRequestError(f"{where}.{key}: duplicated entries", code="invalid_field")
            return tuple(values)

        required = field_list("required_metadata")
        must_match = field_list("must_match")
        missing = [f for f in must_match if f not in required]
        if missing:
            raise InvalidRequestError(
                f"{where}: every 'must_match' field must also be in 'required_metadata' "
                f"(missing {missing}); otherwise two absent values would count as a match",
                code="invalid_protocol",
                where=where,
            )
        cross_body = data.get("cross_body_comparable")
        if not isinstance(cross_body, bool):
            raise InvalidRequestError(
                f"{where}: 'cross_body_comparable' must be explicitly true or false",
                code="missing_field",
                where=where,
            )
        equivalences: dict[str, tuple[frozenset[str], ...]] = {}
        raw_eq = data.get("equivalent_values", {}) or {}
        for key, groups in _mapping(raw_eq, f"{where}.equivalent_values").items():
            _enum(key, METADATA_FIELDS, where, "equivalent_values")
            if not isinstance(groups, list) or not all(
                isinstance(g, list) and all(isinstance(x, str) for x in g) for g in groups
            ):
                raise InvalidRequestError(
                    f"{where}.equivalent_values.{key}: expected a list of lists of strings",
                    code="invalid_type",
                )
            sets = tuple(frozenset(g) for g in groups)
            seen: set[str] = set()
            for s in sets:
                if seen & s:
                    raise InvalidRequestError(
                        f"{where}.equivalent_values.{key}: a value appears in two groups",
                        code="invalid_protocol",
                    )
                seen |= s
            equivalences[key] = sets
        return cls(
            id=protocol_id,
            required_metadata=required,
            must_match=must_match,
            cross_body_comparable=cross_body,
            equivalent_values=equivalences,
            description=_optional_str(data, "description", where),
        )

    def values_match(self, name: str, a: str, b: str) -> bool:
        if a == b:
            return True
        return any(a in group and b in group for group in self.equivalent_values.get(name, ()))


@dataclass(frozen=True)
class FeatureDefinition:
    """What a feature *is*: physical definition, canonical unit and comparator."""

    id: str
    dimension: str
    definition: str
    canonical_unit: str
    kind: str
    comparator_id: str
    protocol: ComparabilityProtocol
    # Vocabulary for categorical / set / composition kinds (declared by science/data,
    # identical for every body). None for scalar and boolean.
    categories: tuple[str, ...] | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FeatureDefinition":
        from .comparators import get_comparator_spec  # local import avoids a cycle

        data = _mapping(data, "feature_definition")
        feature_id = _required_str(data, "id", "feature_definition")
        where = f"feature_definition[{feature_id}]"
        kind = _enum(data.get("kind"), FEATURE_KINDS, where, "kind")
        comparator_id = _required_str(data, "comparator_id", where)
        spec = get_comparator_spec(comparator_id)
        if spec.kind != kind:
            raise InvalidRequestError(
                f"{where}: comparator '{comparator_id}' works on kind '{spec.kind}', not '{kind}'",
                code="comparator_kind_mismatch",
            )
        categories = data.get("categories")
        if kind in KINDS_WITH_VOCABULARY:
            if (
                not isinstance(categories, list)
                or not categories
                or not all(isinstance(c, str) and c.strip() for c in categories)
                or len(set(categories)) != len(categories)
            ):
                raise InvalidRequestError(
                    f"{where}: kind '{kind}' needs 'categories': a non-empty list of distinct strings",
                    code="missing_categories",
                )
            bad = [c for c in categories if c != c.strip() or ";" in c or "=" in c or c == "[]"]
            if bad:
                raise InvalidRequestError(
                    f"{where}: category names {bad} must not contain ';' or '=', be '[]', or have "
                    "leading/trailing spaces (they are separators in the CSV format)",
                    code="invalid_categories",
                )
            categories = tuple(categories)
        elif categories is not None:
            raise InvalidRequestError(
                f"{where}: 'categories' is only used by kinds {list(KINDS_WITH_VOCABULARY)}",
                code="unexpected_categories",
            )
        return cls(
            id=feature_id,
            dimension=_required_str(data, "dimension", where),
            definition=_required_str(data, "definition", where),
            canonical_unit=_required_str(data, "canonical_unit", where),
            kind=kind,
            comparator_id=comparator_id,
            protocol=ComparabilityProtocol.from_dict(
                data.get("comparability_protocol"), f"{where}.comparability_protocol"
            ),
            categories=categories,
        )


def feature_definitions_by_id(definitions: Any) -> dict[str, FeatureDefinition]:
    """Accept a list or mapping of definitions (objects or dicts); reject duplicates."""
    if isinstance(definitions, Mapping):
        items = [(key, value) for key, value in definitions.items()]
    elif isinstance(definitions, (list, tuple)):
        items = [(None, value) for value in definitions]
    else:
        raise InvalidRequestError(
            "feature_definitions must be a list or a mapping", code="invalid_type"
        )
    result: dict[str, FeatureDefinition] = {}
    for key, item in items:
        definition = item if isinstance(item, FeatureDefinition) else FeatureDefinition.from_dict(item)
        if key is not None and key != definition.id:
            raise InvalidRequestError(
                f"feature definition mapping key '{key}' does not match its id '{definition.id}'",
                code="invalid_feature_definition",
            )
        if definition.id in result:
            raise InvalidRequestError(
                f"duplicate feature definition '{definition.id}'",
                code="duplicate_feature_definition",
                feature_id=definition.id,
            )
        result[definition.id] = definition
    return result


# --------------------------------------------------------------------------- profile


@dataclass(frozen=True)
class ProfileFeature:
    """Active feature in a profile: internal weight a_j and scale tau_j.

    The scale can be given as ``tau`` or as a fixed ``range`` {min, max}
    (min-max scaling with declared bounds); then tau = max - min. Comparators
    without a scale (categorical, boolean, Jaccard, cosine) take neither.
    """

    feature_id: str
    weight: float
    tau: float | None = None
    tau_unit: str | None = None
    range_min: float | None = None  # kept for transparency when tau came from a range
    range_max: float | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "ProfileFeature":
        data = _mapping(data, where)
        feature_id = _required_str(data, "feature_id", where)
        where = f"{where}[{feature_id}]"
        weight = _finite_number(data.get("weight"), f"{where}.weight")
        if weight < 0:
            raise ProfileError(
                f"{where}: negative weights are not allowed (got {weight})",
                code="negative_weight",
                feature_id=feature_id,
            )
        has_tau, has_range = data.get("tau") is not None, data.get("range") is not None
        if has_tau and has_range:
            raise ProfileError(f"{where}: give either 'tau' or 'range', not both", code="tau_and_range")
        tau = range_min = range_max = None
        if has_tau:
            tau = _finite_number(data.get("tau"), f"{where}.tau")
        elif has_range:
            rng = _mapping(data["range"], f"{where}.range")
            range_min = _finite_number(rng.get("min"), f"{where}.range.min")
            range_max = _finite_number(rng.get("max"), f"{where}.range.max")
            if range_max <= range_min:
                raise ProfileError(f"{where}: range max must be > min", code="non_positive_tau", feature_id=feature_id)
            tau = range_max - range_min
            if not math.isfinite(tau):
                raise ProfileError(f"{where}: range width overflows", code="non_finite_number")
        if tau is not None and tau <= 0:
            raise ProfileError(
                f"{where}: tau must be strictly positive (got {tau})",
                code="non_positive_tau",
                feature_id=feature_id,
            )
        return cls(
            feature_id=feature_id,
            weight=weight,
            tau=tau,
            tau_unit=_optional_str(data, "tau_unit", where),
            range_min=range_min,
            range_max=range_max,
        )


@dataclass(frozen=True)
class Constraint:
    """A non-compensable requirement on one active feature.

    Numeric (scalar features; ``limit`` and ``unit`` required):

    * ``max_abs_difference``: |x - t| <= limit
    * ``min_value``:          x >= limit
    * ``max_value``:          x <= limit

    Exact (boolean / categorical features; ``value`` required):

    * ``equals``:             x == value   (e.g. ground ice must be present)

    Limits and values come from the profile (science/backend), never from the engine.
    """

    id: str
    feature_id: str
    type: str
    limit: float | None = None
    unit: str | None = None  # numeric types: must equal the canonical unit
    value: bool | str | None = None  # 'equals' only
    description: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], where: str) -> "Constraint":
        data = _mapping(data, where)
        constraint_id = _required_str(data, "id", where)
        where = f"{where}[{constraint_id}]"
        ctype = _enum(data.get("type"), CONSTRAINT_TYPES, where, "type")
        limit = unit = value = None
        if ctype in NUMERIC_CONSTRAINT_TYPES:
            limit = _finite_number(data.get("limit"), f"{where}.limit")
            if ctype == "max_abs_difference" and limit < 0:
                raise ProfileError(f"{where}: max_abs_difference limit must be >= 0", code="invalid_constraint")
            unit = _required_str(data, "unit", where)
        else:
            value = data.get("value")
            if not isinstance(value, (bool, str)) or (isinstance(value, str) and not value.strip()):
                raise ProfileError(
                    f"{where}: 'equals' needs 'value' (true/false or a category)", code="invalid_constraint"
                )
        return cls(
            id=constraint_id,
            feature_id=_required_str(data, "feature_id", where),
            type=ctype,
            limit=limit,
            unit=unit,
            value=value,
            description=_optional_str(data, "description", where),
        )


@dataclass(frozen=True)
class Profile:
    """A versioned search configuration supplied by backend/science.

    ``features`` (ordered) *is* the active feature set of the search.
    """

    id: str
    version: str
    target_id: str
    calibration_status: str
    features: tuple[ProfileFeature, ...]
    dimension_weights: Mapping[str, float] | None = None
    required_features: tuple[str, ...] = ()
    constraints: tuple[Constraint, ...] = ()
    description: str | None = None
    # Conditions the analog cannot reproduce (e.g. gravity, vacuum, thin
    # atmosphere, radiation). Supplied by science; reported, never scored.
    declared_limitations: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Profile":
        data = _mapping(data, "profile")
        profile_id = _required_str(data, "id", "profile")
        where = f"profile[{profile_id}]"
        raw_features = data.get("features")
        if not isinstance(raw_features, list) or not raw_features:
            raise ProfileError(f"{where}: 'features' must be a non-empty list", code="no_active_features")
        features = tuple(
            ProfileFeature.from_dict(f, f"{where}.features[{i}]") for i, f in enumerate(raw_features)
        )
        dimension_weights = None
        if data.get("dimension_weights") is not None:
            dimension_weights = {
                str(k): _finite_number(v, f"{where}.dimension_weights[{k}]")
                for k, v in _mapping(data["dimension_weights"], f"{where}.dimension_weights").items()
            }
        required = data.get("required_features", []) or []
        if not isinstance(required, list) or not all(isinstance(r, str) for r in required):
            raise ProfileError(f"{where}: 'required_features' must be a list of ids", code="invalid_type")
        raw_constraints = data.get("constraints", []) or []
        if not isinstance(raw_constraints, list):
            raise ProfileError(f"{where}: 'constraints' must be a list", code="invalid_type")
        constraints = tuple(
            Constraint.from_dict(c, f"{where}.constraints[{i}]") for i, c in enumerate(raw_constraints)
        )
        return cls(
            id=profile_id,
            version=_required_str(data, "version", where),
            target_id=_required_str(data, "target_id", where),
            calibration_status=_enum(
                data.get("calibration_status"), CALIBRATION_STATUSES, where, "calibration_status"
            ),
            features=features,
            dimension_weights=dimension_weights,
            required_features=tuple(required),
            constraints=constraints,
            description=_optional_str(data, "description", where),
            declared_limitations=_string_list(data, "declared_limitations", where),
        )

    @property
    def active_feature_ids(self) -> tuple[str, ...]:
        return tuple(f.feature_id for f in self.features)


# --------------------------------------------------------------------------- coercion


def as_site(value: Any) -> Site:
    return value if isinstance(value, Site) else Site.from_dict(value)


def as_profile(value: Any) -> Profile:
    return value if isinstance(value, Profile) else Profile.from_dict(value)
