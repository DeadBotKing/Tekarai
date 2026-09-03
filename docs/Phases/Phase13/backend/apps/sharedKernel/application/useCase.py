"""UseCase template — the eight canonical steps (Phase 06 §8) with the
transaction boundary in the application layer (§9).

Steps (spec §8):
1. Validate input          → ``validateCommand``
2. Check authorization     → ``checkAuthorization``
3. Check business rules    → ``businessRules``
4. Create domain entity    → ``perform`` (inside the unit of work)
5. Persist entity          → ``perform`` (repository, inside the UoW)
6. Generate domain event   → aggregates record events; dispatcher publishes
7. Audit operation         → ``AuditRecorder`` inside the same UoW
8. Return DTO              → ``perform`` returns a DTO, never HTTP

Subclasses implement the three hooks; ``execute`` orchestrates. Use cases
never see HTTP: they raise domain/application errors which the API layer
maps (§15).
"""

from __future__ import annotations

import uuid

from apps.sharedKernel.application.messaging import Command, Query
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.entities import AggregateRoot

#: Audit action names — sensitive operations are auditable (§32 Phase 5 list).
AUDIT_CREATE = "CREATE"
AUDIT_UPDATE = "UPDATE"
AUDIT_DELETE = "DELETE"
AUDIT_LOGIN = "LOGIN"
AUDIT_LOGOUT = "LOGOUT"
AUDIT_PERMISSION_CHANGE = "PERMISSION_CHANGE"
AUDIT_ROLE_CHANGE = "ROLE_CHANGE"
AUDIT_EXPORT = "EXPORT"
AUDIT_APPROVAL = "APPROVAL"
AUDIT_REJECTION = "REJECTION"


class UseCase[TMessage: Command | Query, TResult]:
    """Orchestrates one business transaction (Application Layer, §4/§8)."""

    #: Required action-based permission (BR-PER-001); empty = no permission
    #: step (authentication-only endpoints such as login).
    requiredAction: str = ""

    def __init__(
        self,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        self.unitOfWork = unitOfWork
        self.auditRecorder = auditRecorder
        self.eventDispatcher = eventDispatcher
        self.permissionGate = permissionGate
        self.clock = clock
        self._pendingEvents: list = []

    # -- orchestration ------------------------------------------------------

    def execute(self, message: TMessage) -> TResult:
        self._pendingEvents = []
        self.validateCommand(message)
        self.checkAuthorization(message)
        self.businessRules(message)
        with self.unitOfWork:
            result = self.perform(message)
        self.publishPendingEvents()
        return result

    # -- hooks ---------------------------------------------------------------

    def validateCommand(self, message: TMessage) -> None:
        """Step 1 — structural validation of the command itself."""

    def checkAuthorization(self, message: TMessage) -> None:
        """Step 2 — server-side authorization (§44 six layers)."""
        if not self.requiredAction:
            return
        from apps.sharedKernel.domain.errors import PermissionDeniedError

        context = currentContext()
        if not context.actorId:
            raise PermissionDeniedError(action=self.requiredAction)
        allowed = self.permissionGate.hasPermission(
            uuid.UUID(context.actorId),
            self.requiredAction,
            tenantId=uuid.UUID(context.actorTenantId) if context.actorTenantId else None,
        )
        if not allowed:
            raise PermissionDeniedError(action=self.requiredAction)

    def businessRules(self, message: TMessage) -> None:
        """Step 3 — business-rule checks that precede state changes."""

    def perform(self, message: TMessage) -> TResult:
        """Steps 4–5 (entity + persistence) and 7 (audit) inside the UoW,
        then step 8 (DTO) as the return value. Must be implemented."""
        raise NotImplementedError

    # -- helpers -------------------------------------------------------------

    def collectEventsFrom(self, aggregate: AggregateRoot) -> None:
        """Step 6 — take the aggregate's recorded events for post-commit
        publishing (§36); call inside ``perform`` after persisting."""
        self._pendingEvents.extend(aggregate.pullEvents())

    def publishPendingEvents(self) -> None:
        events, self._pendingEvents = self._pendingEvents, []
        for event in events:
            self.eventDispatcher.dispatch(event)

    def audit(
        self,
        action: str,
        resourceType: str,
        resourceId: str,
        tenantId: uuid.UUID | None = None,
        *,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> None:
        """Step 7 — audit write; correlation/actor/ip come from context (§19)."""
        self.auditRecorder.record(
            action=action,
            resourceType=resourceType,
            resourceId=resourceId,
            tenantId=tenantId,
            before=before,
            after=after,
        )

    def nowUtc(self) -> object:
        return self.clock.nowUtc()
