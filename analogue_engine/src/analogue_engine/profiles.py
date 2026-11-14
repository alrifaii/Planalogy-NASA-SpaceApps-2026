"""Explicit profile transformations.

Reducing the active feature set changes the basis of comparison, so it must
be an explicit act that yields a *new profile version*, applied to all
candidates. The engine never does it silently.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable

from .errors import ProfileError
from .models import Profile, feature_definitions_by_id


def profile_to_dict(profile: Profile) -> dict[str, Any]:
    """Serialise a Profile back to the JSON contract (inverse of Profile.from_dict)."""
    features = []
    for f in profile.features:
        item: dict[str, Any] = {"feature_id": f.feature_id, "weight": f.weight}
        if f.range_min is not None:
            item["range"] = {"min": f.range_min, "max": f.range_max}
        elif f.tau is not None:
            item["tau"] = f.tau
        if f.tau_unit is not None:
            item["tau_unit"] = f.tau_unit
        features.append(item)
    constraints = []
    for c in profile.constraints:
        item = {"id": c.id, "feature_id": c.feature_id, "type": c.type}
        if c.type == "equals":
            item["value"] = c.value
        else:
            item["limit"] = c.limit
            item["unit"] = c.unit
        if c.description:
            item["description"] = c.description
        constraints.append(item)
    out: dict[str, Any] = {
        "id": profile.id,
        "version": profile.version,
        "target_id": profile.target_id,
        "calibration_status": profile.calibration_status,
        "features": features,
        "required_features": list(profile.required_features),
        "constraints": constraints,
        "declared_limitations": list(profile.declared_limitations),
    }
    if profile.dimension_weights is not None:
        out["dimension_weights"] = dict(profile.dimension_weights)
    if profile.description:
        out["description"] = profile.description
    return out


def restrict_profile(
    profile: Profile,
    keep_features: Iterable[str],
    new_version: str,
    feature_definitions: Any = None,
) -> Profile:
    """Return a copy of ``profile`` with only ``keep_features`` active.

    * Raises if a required or constrained feature would be dropped
      (requirements do not disappear silently) or if the version is unchanged.
    * If the profile has ``dimension_weights``, ``feature_definitions`` is
      needed so that dimensions left without active features are dropped;
      the remaining dimension weights keep their raw values (and are
      renormalised among themselves at resolution).
    """
    keep = list(dict.fromkeys(keep_features))
    active = profile.active_feature_ids
    unknown = [f for f in keep if f not in active]
    if unknown:
        raise ProfileError(f"cannot keep non-active features {unknown}", code="unknown_feature")
    if not keep:
        raise ProfileError("a profile needs at least one active feature", code="no_active_features")
    if new_version == profile.version:
        raise ProfileError("a restricted profile must have a new version", code="version_not_changed")
    dropped = [f for f in active if f not in keep]
    blocked = [f for f in dropped if f in profile.required_features] + [
        c.feature_id for c in profile.constraints if c.feature_id in dropped
    ]
    if blocked:
        raise ProfileError(
            f"cannot drop required/constrained features {sorted(set(blocked))}; "
            "edit the requirements explicitly first",
            code="cannot_drop_requirement",
        )

    dimension_weights = None
    if profile.dimension_weights is not None:
        if feature_definitions is None:
            raise ProfileError(
                "restrict_profile needs feature_definitions when the profile has dimension_weights "
                "(to drop dimensions left without active features)",
                code="feature_definitions_required",
            )
        definitions = feature_definitions_by_id(feature_definitions)
        remaining_dims = {definitions[f].dimension for f in keep if f in definitions}
        dimension_weights = {d: w for d, w in profile.dimension_weights.items() if d in remaining_dims}

    return replace(
        profile,
        version=new_version,
        features=tuple(f for f in profile.features if f.feature_id in keep),
        dimension_weights=dimension_weights,
        description=(profile.description or "") + f" [restricted from {profile.version} to {keep}]",
    )
