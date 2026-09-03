"""AssignUserToTenantUseCase (§4 "Assign User to Tenant")."""

from __future__ import annotations

from apps.identity.application.commands.identityCommands import AssignUserToTenantCommand
from apps.identity.application.dto.identityDtos import UserDto, userDtoFromDomain
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.repositories.identityRepositories import (
    TenantMembershipRepository,
    UserRepository,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, UseCase
from apps.sharedKernel.domain.errors import (
    DuplicateActiveMembershipError,
    EntityNotFoundError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


class AssignUserToTenantUseCase(UseCase[AssignUserToTenantCommand, UserDto]):
    requiredAction = "user.assignTenant"

    def __init__(
        self,
        userRepository: UserRepository,
        membershipRepository: TenantMembershipRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.membershipRepository = membershipRepository

    def perform(self, command: AssignUserToTenantCommand) -> UserDto:
        userId = asUuid(command.userId)
        targetTenantId = asUuid(command.targetTenantId)
        user = self.userRepository.getById(userId)
        if user is None:
            raise EntityNotFoundError("User", command.userId)
        if self.membershipRepository.existsActive(userId, targetTenantId):
            raise DuplicateActiveMembershipError(
                "User already has an active membership in this tenant.",
            )
        membership = TenantMembership.establish(
            userId=userId,
            tenantId=targetTenantId,
            now=self.clock.nowUtc(),
        )
        self.membershipRepository.create(membership)
        self.collectEventsFrom(membership)
        self.audit(
            AUDIT_CREATE,
            resourceType="TenantMembership",
            resourceId=str(membership.id),
            tenantId=targetTenantId,
            after=membership.snapshot(),
        )
        return userDtoFromDomain(user)
