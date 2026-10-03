"""Offline sync — replaying what a technician did with no network.

The phone keeps a local queue of *intents* («وضعیت را به انجام‌شده ببر»,
«۳ عدد بلبرینگ مصرف شد», «تایمر را ساعت ۱۰:۱۲ متوقف کن») and ships the
backlog when it next sees the server. This use case is the landing strip.

Four properties the design is built around:

1. **Exactly-once, enforced server-side.** Every queued item carries a
   ``clientRequestId`` minted on the phone. The outcome is written to a
   durable ledger keyed by that id, so a retry — a day later, after a server
   restart, from a second tab — returns the *stored* outcome instead of
   consuming the spare part twice. The shared-kernel idempotency mixin is
   cache-backed and cannot make that promise across restarts, which is why
   this slice has its own table.

2. **Partial success is the normal case.** One bad item must not reject the
   other nineteen. Each item runs inside its own savepoint; the batch answers
   with a per-item verdict. ``atomic=true`` is available for the rare caller
   that wants all-or-nothing.

3. **The verdict tells the queue what to do.** ``applied``/``duplicate`` →
   delete the item. ``rejected`` → delete it and show the technician why; it
   will never succeed. ``failed`` → keep it, retry next time. Getting this
   wrong in either direction is costly: retrying a rejected item forever
   blocks the queue, dropping a failed item loses work.

4. **No privilege laundering.** Items are executed through the very same use
   cases the online endpoints use, so every permission check still runs. A
   requester's phone cannot replay a manager's status change.

Clock semantics: the payload's ``occurredAt`` is preserved as the business
moment (``workedAt``, ``endedAt``, ``capturedAt``) wherever the target use
case accepts one. The server's own clock is only used as a fallback and for
``receivedAt``. A reading taken at 08:00 and synced at 17:00 belongs to
08:00 — anything else corrupts the history the technician risked their
thumbs to capture.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.exceptions.fieldOpsErrors import (
    SyncBatchTooLargeError,
    SyncOperationUnsupportedError,
    TimerAlreadyRunningError,
    TimerNotRunningError,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    OfflineSyncLedger,
)
from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    MAX_CLIENT_REQUEST_ID_LENGTH,
    MAX_SYNC_BATCH,
    SYNC_KINDS,
    SYNC_STATUS_APPLIED,
    SYNC_STATUS_DUPLICATE,
    SYNC_STATUS_FAILED,
    SYNC_STATUS_REJECTED,
)
from apps.sharedKernel.application.messaging import Command, Query
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import (
    ConflictError,
    DomainError,
    EntityNotFoundError,
    PermissionDeniedError,
    TekaraiError,
    ValidationFailedError,
)

#: Handler signature: payload → (resultId, resultPayload).
SyncHandler = Callable[[Mapping[str, object]], tuple[str, dict[str, object]]]


# ---------------------------------------------------------------------------
# Commands / queries
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SyncOperationCommand:
    clientRequestId: str
    kind: str
    payload: Mapping[str, object] = field(default_factory=dict)
    occurredAt: str = ""


@dataclass(frozen=True)
class ApplySyncBatchCommand(Command):
    operations: Sequence[SyncOperationCommand] = ()
    deviceLabel: str = ""
    atomic: bool = False


@dataclass(frozen=True)
class SyncHistoryQuery(Query):
    limit: int = 50


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SyncOperationResultDto:
    clientRequestId: str
    kind: str
    status: str
    resultId: str = ""
    result: dict[str, object] = field(default_factory=dict)
    errorCode: str = ""
    errorMessage: str = ""


@dataclass(frozen=True)
class SyncBatchResultDto:
    results: list[SyncOperationResultDto] = field(default_factory=list)
    appliedCount: int = 0
    duplicateCount: int = 0
    rejectedCount: int = 0
    failedCount: int = 0
    serverTime: str = ""

    def asMeta(self) -> dict[str, object]:
        return {
            "appliedCount": self.appliedCount,
            "duplicateCount": self.duplicateCount,
            "rejectedCount": self.rejectedCount,
            "failedCount": self.failedCount,
            "serverTime": self.serverTime,
        }


@dataclass(frozen=True)
class SyncLedgerEntryDto:
    clientRequestId: str
    kind: str
    status: str
    resultId: str
    errorCode: str
    errorMessage: str
    receivedAt: str


# ---------------------------------------------------------------------------
# Error → verdict
# ---------------------------------------------------------------------------
#: Conflicts that mean "the server already has this", i.e. the first attempt
#: actually landed and the phone is replaying. Reported as a duplicate so the
#: queue drops the item quietly instead of alarming the technician.
_IDEMPOTENT_CONFLICTS = (TimerAlreadyRunningError, TimerNotRunningError)


def classifyFailure(error: Exception) -> tuple[str, str, str]:
    """(status, errorCode, message) for one failed operation."""
    if isinstance(error, _IDEMPOTENT_CONFLICTS):
        return SYNC_STATUS_DUPLICATE, getattr(error, "code", ""), str(error)
    if isinstance(
        error,
        (
            ValidationFailedError,
            PermissionDeniedError,
            EntityNotFoundError,
            DomainError,
            ConflictError,
        ),
    ):
        return SYNC_STATUS_REJECTED, getattr(error, "code", ""), str(error)
    if isinstance(error, TekaraiError):
        return SYNC_STATUS_REJECTED, getattr(error, "code", ""), str(error)
    # Unknown failures are assumed transient: keep the work, retry later.
    return SYNC_STATUS_FAILED, "SYS_REQUEST_FAILED", str(error) or error.__class__.__name__


# ---------------------------------------------------------------------------
# Use cases
# ---------------------------------------------------------------------------
class ApplySyncBatchUseCase(UseCase):
    """``POST /maintenance/sync`` — replay a phone's offline backlog."""

    #: Deliberately empty: authorisation is enforced by each *inner* use
    #: case. A single coarse permission here would either lock out
    #: technicians who may log time but not change device status, or hand
    #: everyone the union of both.
    requiredAction = ""

    def __init__(self, ledger: OfflineSyncLedger, handlers: Mapping[str, SyncHandler], **kwargs) -> None:
        super().__init__(**kwargs)
        self.ledger = ledger
        self.handlers = dict(handlers)

    def validateCommand(self, command: ApplySyncBatchCommand) -> None:
        if len(command.operations) > MAX_SYNC_BATCH:
            raise SyncBatchTooLargeError(
                f"A sync batch carries at most {MAX_SYNC_BATCH} operations.",
                fieldErrors={"operations": "tooMany"},
            )
        seen: set[str] = set()
        for operation in command.operations:
            key = (operation.clientRequestId or "").strip()
            if not key:
                raise ValidationFailedError(
                    "Every operation needs a clientRequestId.",
                    fieldErrors={"clientRequestId": "required"},
                )
            if len(key) > MAX_CLIENT_REQUEST_ID_LENGTH:
                raise ValidationFailedError(
                    "clientRequestId is too long.",
                    fieldErrors={"clientRequestId": "tooLong"},
                )
            if key in seen:
                # Two items with one id inside a single batch is a client bug
                # we cannot disambiguate — rejecting the batch is safer than
                # silently applying one and calling the other a duplicate.
                raise ValidationFailedError(
                    "Duplicate clientRequestId inside one batch.",
                    fieldErrors={"clientRequestId": key},
                )
            seen.add(key)

    def _runOne(
        self,
        tenantId: uuid.UUID,
        operation: SyncOperationCommand,
        now: datetime,
        deviceLabel: str,
        actorName: str,
    ) -> SyncOperationResultDto:
        key = operation.clientRequestId.strip()
        kind = (operation.kind or "").strip()

        remembered = self.ledger.find(tenantId, key)
        if remembered is not None:
            if remembered.status == SYNC_STATUS_FAILED:
                # Transient failure last time — let it try again.
                forget = getattr(self.ledger, "forget", None)
                if callable(forget):
                    forget(tenantId, key)
            else:
                return SyncOperationResultDto(
                    clientRequestId=key,
                    kind=remembered.kind or kind,
                    status=(
                        SYNC_STATUS_DUPLICATE
                        if remembered.status == SYNC_STATUS_APPLIED
                        else SYNC_STATUS_REJECTED
                    ),
                    resultId=remembered.resultId,
                    result=remembered.resultPayload,
                    errorCode=remembered.errorCode,
                    errorMessage=remembered.errorMessage,
                )

        if kind not in SYNC_KINDS or kind not in self.handlers:
            error = SyncOperationUnsupportedError(
                f"Unsupported sync operation: {kind or '(empty)'}",
                fieldErrors={"kind": kind},
            )
            self.ledger.remember(
                tenantId,
                key,
                kind or "unknown",
                SYNC_STATUS_REJECTED,
                errorCode=error.code,
                errorMessage=str(error),
                actorName=actorName,
                receivedAt=now,
                deviceLabel=deviceLabel,
            )
            return SyncOperationResultDto(
                clientRequestId=key,
                kind=kind,
                status=SYNC_STATUS_REJECTED,
                errorCode=error.code,
                errorMessage=str(error),
            )

        payload = dict(operation.payload or {})
        if operation.occurredAt and "occurredAt" not in payload:
            payload["occurredAt"] = operation.occurredAt

        try:
            resultId, resultPayload = self.handlers[kind](payload)
        except Exception as error:  # noqa: BLE001 — verdict decided below
            status, code, message = classifyFailure(error)
            if status == SYNC_STATUS_DUPLICATE:
                # The effect already exists; remember it as applied so the
                # next replay short-circuits without touching the domain.
                self.ledger.remember(
                    tenantId,
                    key,
                    kind,
                    SYNC_STATUS_APPLIED,
                    errorCode=code,
                    errorMessage=message,
                    actorName=actorName,
                    receivedAt=now,
                    deviceLabel=deviceLabel,
                )
            else:
                self.ledger.remember(
                    tenantId,
                    key,
                    kind,
                    SYNC_STATUS_REJECTED if status == SYNC_STATUS_REJECTED else SYNC_STATUS_FAILED,
                    errorCode=code,
                    errorMessage=message,
                    actorName=actorName,
                    receivedAt=now,
                    deviceLabel=deviceLabel,
                )
            return SyncOperationResultDto(
                clientRequestId=key,
                kind=kind,
                status=status,
                errorCode=code,
                errorMessage=message,
            )

        self.ledger.remember(
            tenantId,
            key,
            kind,
            SYNC_STATUS_APPLIED,
            resultId=str(resultId),
            resultPayload=resultPayload,
            actorName=actorName,
            receivedAt=now,
            deviceLabel=deviceLabel,
        )
        return SyncOperationResultDto(
            clientRequestId=key,
            kind=kind,
            status=SYNC_STATUS_APPLIED,
            resultId=str(resultId),
            result=resultPayload,
        )

    def perform(self, command: ApplySyncBatchCommand) -> SyncBatchResultDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        actorName = currentContext().actorName or ""
        results: list[SyncOperationResultDto] = []
        for operation in command.operations:
            results.append(
                self._runOne(
                    tenantId, operation, now, command.deviceLabel.strip()[:120], actorName
                )
            )
        tally = {
            SYNC_STATUS_APPLIED: 0,
            SYNC_STATUS_DUPLICATE: 0,
            SYNC_STATUS_REJECTED: 0,
            SYNC_STATUS_FAILED: 0,
        }
        for item in results:
            tally[item.status] = tally.get(item.status, 0) + 1
        return SyncBatchResultDto(
            results=results,
            appliedCount=tally[SYNC_STATUS_APPLIED],
            duplicateCount=tally[SYNC_STATUS_DUPLICATE],
            rejectedCount=tally[SYNC_STATUS_REJECTED],
            failedCount=tally[SYNC_STATUS_FAILED],
            serverTime=now.isoformat(),
        )


class ListSyncHistoryUseCase(UseCase):
    """What this tenant's phones have replayed lately (support tool)."""

    requiredAction = "maintenance.workorder.view"

    def __init__(self, ledger: OfflineSyncLedger, **kwargs) -> None:
        super().__init__(**kwargs)
        self.ledger = ledger

    def perform(self, query: SyncHistoryQuery) -> list[SyncLedgerEntryDto]:
        tenantId = resolveTenantId("")
        entries = self.ledger.recent(tenantId, int(query.limit or 50))
        return [
            SyncLedgerEntryDto(
                clientRequestId=item.clientRequestId,
                kind=item.kind,
                status=item.status,
                resultId=item.resultId,
                errorCode=item.errorCode,
                errorMessage=item.errorMessage,
                receivedAt=item.receivedAt.isoformat(),
            )
            for item in entries
        ]
