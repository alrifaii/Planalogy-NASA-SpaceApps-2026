"""analogue_engine: explainable similarity between planetary reference sites
and terrestrial candidate areas.

Public API::

    from analogue_engine import compare, rank, sensitivity_analysis, load_bundle

Similarity is not operational suitability; see docs/math-model.md.
"""

from .adapters import backend_payload, sites_from_wide_records
from .calibration import CalibrationResult, CalibrationSettings, calibrate_weights
from .timeline import TimelineResult, Trajectory, rank_over_years
from .engine import MODEL_ID, MODEL_VERSION, compare, rank
from .errors import AnalogueEngineError, DataModeError, InvalidRequestError, ProfileError
from .io import Bundle, load_bundle, load_sites_csv, loads_strict, parse_bundle, write_sites_csv
from .models import (
    ComparabilityProtocol,
    Constraint,
    FeatureDefinition,
    Measurement,
    Profile,
    ProfileFeature,
    Site,
)
from .profiles import profile_to_dict, restrict_profile
from .results import (
    ComparisonResult,
    ComponentResult,
    ConstraintResult,
    DimensionResult,
    RankedEntry,
    RankingResult,
    to_json,
)
from .sensitivity import SensitivityReport, sensitivity_analysis

__version__ = MODEL_VERSION

__all__ = [
    "MODEL_ID",
    "MODEL_VERSION",
    "AnalogueEngineError",
    "Bundle",
    "ComparabilityProtocol",
    "ComparisonResult",
    "ComponentResult",
    "Constraint",
    "ConstraintResult",
    "DataModeError",
    "DimensionResult",
    "FeatureDefinition",
    "InvalidRequestError",
    "Measurement",
    "Profile",
    "ProfileError",
    "ProfileFeature",
    "RankedEntry",
    "RankingResult",
    "SensitivityReport",
    "Site",
    "CalibrationResult",
    "CalibrationSettings",
    "backend_payload",
    "calibrate_weights",
    "compare",
    "profile_to_dict",
    "rank_over_years",
    "TimelineResult",
    "Trajectory",
    "sites_from_wide_records",
    "load_bundle",
    "load_sites_csv",
    "loads_strict",
    "write_sites_csv",
    "parse_bundle",
    "rank",
    "restrict_profile",
    "sensitivity_analysis",
    "to_json",
]
