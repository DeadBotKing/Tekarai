"""User-lifecycle use case (Phase 07 §3/§31) — the 8-state machine.

All transitions go through ``User.transitionTo`` (invalid transitions are
domain errors). §19 two-step authorization: permission ``user.suspend`` AND
the UserAccountPolicy resource policy (never act on yourself; GLOBAL scope
crosses tenants).
"""

from __future__ import annotations

import uuid

from apps.identity.application.commands.identityCommands import ChangeUserStatusCommand
from apps.identity.application.dto.identityDtos import UserDto, userDtoFromDomain
from apps.identity.domain.policies.resourcePolicies import POLICIES, AccessRequest
from apps.identity.domain.repositories.identityRepositories import UserRepository
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


class ChangeUserStatusUseCase(UseCase[ChangeUserStatusCommand, UserDto]):
    requiredAction = "user.suspend"

    def __init__(
        self,
        repository: UserRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: ChangeUserStatusCommand) -> UserDto:
        context = currentContext()
        actorId = uuid.UUID(context.actorId) if context.actorId else None
        if actorId is None:
            from apps.sharedKernel.domain.errors import AuthenticationRequiredError

            raise AuthenticationRequiredError()
        user = self.repository.getById(asUuid(command.userId))
        if user is None:
            raise EntityNotFoundError("User", command.userId)

        request = AccessRequest(
            actorId=actorId,
            tenantId=user.tenantId,
            isGlobalScope=self.permissionGate.hasPermission(
                actorId, "tenant.list", tenantId=user.tenantId
            ),
            actions=frozenset({"user.update"}),
        )
        policy = POLICIES["User"]
        allowed = (
            policy.canUpdate(request, user)
            if command.target in {"suspended", "active"}
            else policy.canDisable(request, user)
        )
        if not allowed:
            raise PermissionDeniedError(action="user.suspend")

        now = self.clock.nowUtc()
        user.transitionTo(command.target, now)
        self.repository.update(user)
        self.collectEventsFrom(user)
        self.audit(
            AUDIT_UPDATE,
            resourceType="User",
            resourceId=str(user.id),
            tenantId=user.tenantId,
            before={"status": "…"},
            after={"status": command.target},
        )
        return userDtoFromDomain(user)
