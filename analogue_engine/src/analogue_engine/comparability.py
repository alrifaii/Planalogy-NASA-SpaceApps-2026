"""Pairwise comparability check for one feature.

Having two values with status 'valid' is not enough: both must share the
canonical unit, satisfy the feature's comparability protocol (method,
version, spatial/temporal support) and the body policy. The check never
infers that two different methods or supports are equivalent; only
equivalences declared in the protocol are accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import FeatureDefinition, Measurement, Site

# Component statuses
COMPARED = "compared"
MISSING = "missing"  # no usable candidate value (insufficient information)
PENDING = "comparability_pending"  # critical metadata absent (insufficient information)
INCOMPATIBLE = "incompatible"  # values exist but must not be compared

INSUFFICIENT_STATUSES = (MISSING, PENDING)


@dataclass(frozen=True)
class ComparabilityOutcome:
    status: str
    reason_code: str | None = None
    message: str | None = None


def check_comparability(
    definition: FeatureDefinition,
    target: Site,
    target_measurement: Measurement,
    candidate: Site,
    candidate_measurement: Measurement | None,
) -> ComparabilityOutcome:
    """Decide whether target and candidate values of one feature are comparable.

    The target measurement has already been validated by profile resolution.
    """
    fid = definition.id
    m = candidate_measurement
    if m is None:
        return ComparabilityOutcome(MISSING, "not_provided", f"candidate has no measurement for '{fid}'")
    if m.status == "missing":
        return ComparabilityOutcome(MISSING, "value_missing", f"candidate value for '{fid}' is missing")
    if m.status == "flagged":
        return ComparabilityOutcome(
            MISSING, "quality_flagged", f"candidate value for '{fid}' is quality-flagged and not used"
        )
    if m.unit != definition.canonical_unit:
        return ComparabilityOutcome(
            INCOMPATIBLE,
            "unit_mismatch",
            f"'{fid}': candidate unit '{m.unit}' differs from canonical unit "
            f"'{definition.canonical_unit}'; v0 performs no unit conversion",
        )
    protocol = definition.protocol
    if not protocol.cross_body_comparable and candidate.body != target.body:
        return ComparabilityOutcome(
            INCOMPATIBLE,
            "body_not_comparable",
            f"'{fid}': protocol '{protocol.id}' does not allow comparison across bodies "
            f"('{target.body}' vs '{candidate.body}')",
        )
    # A known mismatch is decisive even if other metadata is absent: more
    # metadata could never make this pair comparable.
    for name in protocol.must_match:
        a, b = target_measurement.metadata(name), m.metadata(name)
        if b is not None and not protocol.values_match(name, a, b):
            return ComparabilityOutcome(
                INCOMPATIBLE,
                f"protocol_mismatch:{name}",
                f"'{fid}': {name} differs ('{a}' vs '{b}') and protocol '{protocol.id}' "
                "declares no equivalence",
            )
    absent = [name for name in protocol.required_metadata if m.metadata(name) is None]
    if absent:
        return ComparabilityOutcome(
            PENDING,
            "metadata_missing",
            f"'{fid}': candidate lacks required metadata {absent} for protocol '{protocol.id}'",
        )
    return ComparabilityOutcome(COMPARED)
