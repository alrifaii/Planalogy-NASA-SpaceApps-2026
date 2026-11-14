"""Exception hierarchy for request-level failures.

Only problems that make the *whole request* meaningless raise exceptions.
Per-candidate problems (missing values, incompatible protocols, failed
requirements) are reported inside the results instead, so a single bad
candidate never hides the others.

Error taxonomy (see docs/data-contract.md):

* ``InvalidRequestError``  - malformed input (NaN, negative weight, unknown id...)
* ``ProfileError``         - the profile cannot be evaluated against this target
* ``DataModeError``        - synthetic and real records mixed in one search
"""

from __future__ import annotations

from typing import Any


class AnalogueEngineError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier."""

    code = "analogue_engine_error"

    def __init__(self, message: str, *, code: str | None = None, **details: Any) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, "details": self.details}


class InvalidRequestError(AnalogueEngineError):
    """Input records are malformed or violate the contract."""

    code = "invalid_request"


class ProfileError(InvalidRequestError):
    """The profile is inconsistent or cannot be applied to the target."""

    code = "invalid_profile"


class DataModeError(InvalidRequestError):
    """Synthetic and real records were mixed in one comparison or search."""

    code = "data_mode_mismatch"
