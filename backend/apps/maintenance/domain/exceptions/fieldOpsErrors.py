"""Field-operations domain errors — timers, scanning, offline sync.

Each carries a stable code the mobile client can branch on *without* parsing
Persian prose, and an HTTP status that tells a replaying offline queue what to
do: 409 means «the server already knows, stop retrying», 422 means «this
payload will never be accepted, drop it and tell the technician», 404 means
«the target vanished while you were offline».
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import (
    ConflictError,
    TekaraiError,
    ValidationFailedError,
)


class TimerAlreadyRunningError(ConflictError):
    """This technician already has a running stopwatch on this order."""

    code = "MAINT_TIMER_ALREADY_RUNNING"
    httpStatus = 409

    def __init__(
        self, message: str = "", *, fieldErrors: dict[str, str] | None = None
    ) -> None:
        super().__init__(message or "A timer is already running.")
        self.fieldErrors = fieldErrors or {}


class TimerNotRunningError(ConflictError):
    """Stop/cancel was requested for a span that is already closed.

    A replaying offline queue hits this constantly: the stop reached the
    server on the first attempt and the phone retried. The sync layer maps it
    to «duplicate», never to a user-visible failure.
    """

    code = "MAINT_TIMER_NOT_RUNNING"
    httpStatus = 409

    def __init__(
        self, message: str = "", *, fieldErrors: dict[str, str] | None = None
    ) -> None:
        super().__init__(message or "This timer is not running.")
        self.fieldErrors = fieldErrors or {}


class TimerSpanInvalidError(ValidationFailedError):
    """The measured span is impossible (future, negative, or absurdly long)."""

    code = "MAINT_TIMER_SPAN_INVALID"
    httpStatus = 422


class ScanCodeUnreadableError(ValidationFailedError):
    """The scanned text is not a Tekarai code in any recognised shape."""

    code = "MAINT_SCAN_CODE_UNREADABLE"
    httpStatus = 422


class ScanTargetNotFoundError(TekaraiError):
    """The code was well formed but points at nothing in this tenant.

    Distinct from «unreadable» on purpose: a technician holding a label from
    another plant needs a different message than one holding a damaged label.
    """

    code = "MAINT_SCAN_TARGET_NOT_FOUND"
    httpStatus = 404


class SyncOperationUnsupportedError(ValidationFailedError):
    """The queue replayed an operation kind this server does not know.

    Happens when a phone running an older (or newer) build syncs. The item is
    rejected permanently rather than retried forever.
    """

    code = "MAINT_SYNC_KIND_UNSUPPORTED"
    httpStatus = 422


class SyncConflictError(ConflictError):
    """The record moved on while the phone was offline.

    Raised only when the queued item declared the value it was based on and
    the server now holds a different one. Without this check the stale write
    wins by virtue of arriving last, and the person who changed the record in
    the meantime never learns their edit was undone.
    """

    code = "MAINT_SYNC_CONFLICT"
    httpStatus = 409

    def __init__(
        self,
        message: str = "",
        *,
        expected: str = "",
        current: str = "",
        fieldErrors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message or "This record changed while you were offline.")
        self.expected = expected
        self.current = current
        self.fieldErrors = fieldErrors or {}


class SyncBatchTooLargeError(ValidationFailedError):
    """A single sync batch exceeded the per-request operation ceiling."""

    code = "MAINT_SYNC_BATCH_TOO_LARGE"
    httpStatus = 400


__all__ = [
    "ScanCodeUnreadableError",
    "ScanTargetNotFoundError",
    "SyncBatchTooLargeError",
    "SyncConflictError",
    "SyncOperationUnsupportedError",
    "TimerAlreadyRunningError",
    "TimerNotRunningError",
    "TimerSpanInvalidError",
]
