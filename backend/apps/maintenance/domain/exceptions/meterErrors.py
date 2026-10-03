"""Meter-reading domain errors (stable codes, mapped by the API handler).

``MeterReadingImmutableError`` is a *conflict*, not a validation failure: the
request was well formed, but the append-only contract forbids the operation.
409 tells a client "this will never work" rather than "fix your payload".
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ConflictError, DomainError, TekaraiError


class MeterReadingImmutableError(DomainError):
    """Meter readings are append-only; corrections are appended, never applied."""

    code = "MAINT_METER_READING_IMMUTABLE"
    httpStatus = 409


class MeterIngestionConflictError(ConflictError):
    """An ingestion key was reused for a materially different reading.

    Replaying the *same* payload is idempotent and returns the stored reading.
    Reusing the key for a different value is a gateway bug that would silently
    hide a sample, so it is surfaced rather than absorbed.
    """

    code = "MAINT_METER_INGESTION_CONFLICT"
    httpStatus = 409


class MeterPointNotBoundError(TekaraiError):
    """A sensor pushed a key that resolves to no active meter point."""

    code = "MAINT_METER_POINT_NOT_BOUND"
    httpStatus = 404


class MeterReadingAlreadyCorrectedError(ConflictError):
    """A reading that has already been superseded cannot be corrected twice.

    Correcting a correction is legitimate; correcting the *same* row twice
    would fork the chain and leave two "current" values for one observation.
    """

    code = "MAINT_METER_READING_ALREADY_CORRECTED"
    httpStatus = 409


__all__ = [
    "MeterIngestionConflictError",
    "MeterPointNotBoundError",
    "MeterReadingAlreadyCorrectedError",
    "MeterReadingImmutableError",
]
