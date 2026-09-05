"""Framework-free queue vocabularies and retry math for Phase 13-P.

This module defines the closed vocabularies and small pure helpers used
by async execution:

- ``JOB_KINDS`` — the eight enqueuable work kinds. Seven are domain work
  (owned by future phases, executed through caller-registered handlers);
  ``EVENT_DISPATCH`` is the internal event-transport kind executed by the
  worker itself (§P.6);
- ``JOB_STATUSES`` — the six lifecycle states (three terminal);
- ``computeBackoff`` — deterministic exponential retry delays.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ValidationFailedError

JOB_KINDS = (
    "DOCUMENT_ANALYSIS",
    "TRANSCRIPTION",
    "REPORT_GENERATION",
    "EMBEDDING",
    "INDEXING",
    "PREDICTION",
    "GENERIC",
    "EVENT_DISPATCH",
)
JOB_STATUSES = (
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "DEAD",
)
TERMINAL_JOB_STATUSES = (
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "DEAD",
)

#: Priority range; higher values claim first (contract §P.4.1).
MIN_JOB_PRIORITY = 0
MAX_JOB_PRIORITY = 9
DEFAULT_JOB_PRIORITY = 5


def ensureJobKind(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in JOB_KINDS:
        raise ValidationFailedError("Unknown job kind.", fieldErrors={"kind": normalized})
    return normalized


def ensureJobStatus(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in JOB_STATUSES:
        raise ValidationFailedError("Unknown job status.", fieldErrors={"status": normalized})
    return normalized


def ensureJobPriority(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError("Job priority must be an integer.")
    if value < MIN_JOB_PRIORITY or value > MAX_JOB_PRIORITY:
        raise ValidationFailedError("Job priority is out of range.")
    return value


def computeBackoff(attempts: int, baseSeconds: int, multiplier: float, maxSeconds: int) -> int:
    """Exponential retry delay after ``attempts`` failed attempts.

    ``delay = min(maxSeconds, baseSeconds * multiplier ** (attempts - 1))``
    with attempts clamped to at least one, so the first retry waits exactly
    ``baseSeconds``. All inputs are validated; the result is whole seconds.
    """

    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not isinstance(baseSeconds, int)
        or isinstance(baseSeconds, bool)
        or not isinstance(maxSeconds, int)
        or isinstance(maxSeconds, bool)
        or not isinstance(multiplier, (int, float))
        or isinstance(multiplier, bool)
    ):
        raise ValidationFailedError("Backoff inputs have invalid types.")
    if attempts < 1 or baseSeconds < 0 or maxSeconds < 0 or multiplier < 1:
        raise ValidationFailedError("Backoff inputs are out of range.")
    delay = float(baseSeconds) * (float(multiplier) ** (max(1, attempts) - 1))
    return min(maxSeconds, int(delay))


__all__ = [
    "DEFAULT_JOB_PRIORITY",
    "JOB_KINDS",
    "JOB_STATUSES",
    "MAX_JOB_PRIORITY",
    "MIN_JOB_PRIORITY",
    "TERMINAL_JOB_STATUSES",
    "computeBackoff",
    "ensureJobKind",
    "ensureJobPriority",
    "ensureJobStatus",
]
