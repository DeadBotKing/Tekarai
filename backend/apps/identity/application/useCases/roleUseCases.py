"""RBAC administration use cases (Phase 07 §14–§17, §31, §28).

Role/permission mutations bump the authorization cache version (§28) so a
revoked role dies immediately (§35.9). Every mutation is audited and emits
a §27 security event (ROLE_ASSIGNED / ROLE_REMOVED / PERMISSION_CHANGED).
"""

from __future__ import annotations

from apps.identity.application.commands.identityCommands import (
    AssignRoleCommand,
    CreateRoleCommand,
    DeleteRoleCommand,
    RemoveRoleCommand,
    UpdateRoleCommand,
)
from apps.identity.application.dto.identityDtos import RoleDto
from apps.identity.application.queries.identityQueries import ListRolesQuery
from apps.identity.domain.repositories.identityRepositories import (
    AccessRepository,
    RoleRepository,
    SecurityEventRecorder,
    UserRepository,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import (
    AUDIT_PERMISSION_CHANGE,
    AUDIT_ROLE_CHANGE,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

VALID_SCOPES = {"SYSTEM", "GLOBAL", "TENANT", "ORGANIZATION", "DEPARTMENT", "PROJECT", "RESOURCE"}


class CreateRoleUseCase(UseCase[CreateRoleCommand, RoleDto]):
    requiredAction = "role.create"

    def __init__(
        self,
        roleRepository: RoleRepository,
        accessRepository: AccessRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository
        self.accessRepository = accessRepository

    def validateCommand(self, command: CreateRoleCommand) -> None:
        if not command.code or not command.name:
            raise ValidationFailedError("Role code and name are required.")
        if command.scopeType not in VALID_SCOPES:
            raise ValidationFailedError(
                "Invalid scope type.", fieldErrors={"scopeType": command.scopeType}
            )
        for action in command.actions:
            if "." not in action:
                raise ValidationFailedError(
                    "Permission codes must look like resource.action.",
                    fieldErrors={"actions": action},
                )

    def perform(self, command: CreateRoleCommand) -> RoleDto:
        roleId = self.roleRepository.create(
            command.code.lower(), command.name, command.scopeType, command.actions
        )
        self.accessRepository.ensureCatalogue([(a, "") for a in command.actions])
        self.audit(
            AUDIT_ROLE_CHANGE,
            resourceType="Role",
            resourceId=str(roleId),
            after={"code": command.code, "actions": command.actions},
        )
        return RoleDto(
            id=str(roleId),
            code=command.code.lower(),
            name=command.name,
            scopeType=command.scopeType,
            actions=list(command.actions),
        )


class UpdateRoleUseCase(UseCase[UpdateRoleCommand, RoleDto]):
    requiredAction = "role.update"

    def __init__(
        self,
        roleRepository: RoleRepository,
        accessRepository: AccessRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository
        self.accessRepository = accessRepository
        self.securityEvents = securityEvents

    def perform(self, command: UpdateRoleCommand) -> RoleDto:
        roleId = asUuid(command.roleId)
        role = self.roleRepository.getById(roleId)
        if role is None:
            raise EntityNotFoundError("Role", command.roleId)
        actions = command.actions if command.actions else None
        self.roleRepository.update(roleId, name=command.name or None, actions=actions)
        if actions:
            self.accessRepository.ensureCatalogue([(a, "") for a in actions])
            self.securityEvents.record(
                "PERMISSION_CHANGED", result="success", reason=f"role_update:{roleId}"
            )
        self.audit(
            AUDIT_ROLE_CHANGE,
            resourceType="Role",
            resourceId=str(roleId),
            after={"name": command.name, "actions": command.actions},
        )
        return RoleDto(
            id=str(roleId),
            code=role.code,
            name=command.name or role.name,
            scopeType=role.scopeType,
            actions=list(actions or []),
        )


class DeleteRoleUseCase(UseCase[DeleteRoleCommand, object]):
    """Deletion is blocked while the role is still assigned (§17)."""

    requiredAction = "role.delete"

    def __init__(
        self,
        roleRepository: RoleRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository

    def perform(self, command: DeleteRoleCommand) -> object:
        roleId = asUuid(command.roleId)
        self.roleRepository.delete(roleId)  # raises ConflictError if assigned
        self.audit(
            AUDIT_ROLE_CHANGE, resourceType="Role", resourceId=str(roleId), after={"deleted": True}
        )
        return {"deleted": True, "roleId": str(roleId)}


class AssignRoleUseCase(UseCase[AssignRoleCommand, object]):
    """§17 — grant a role to a user (audit + cache invalidation §28)."""

    requiredAction = "user.assignRole"

    def __init__(
        self,
        roleRepository: RoleRepository,
        accessRepository: AccessRepository,
        userRepository: UserRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository
        self.accessRepository = accessRepository
        self.userRepository = userRepository
        self.securityEvents = securityEvents

    def perform(self, command: AssignRoleCommand) -> object:
        userId = asUuid(command.userId)
        roleId = asUuid(command.roleId)
        role = self.roleRepository.getById(roleId)
        if role is None:
            raise EntityNotFoundError("Role", command.roleId)
        user = self.userRepository.getById(userId)
        if user is None:
            raise EntityNotFoundError("User", command.userId)
        tenantId = asUuid(command.tenantId) if command.tenantId else user.tenantId
        self.accessRepository.grantRoleToUser(userId, tenantId, roleId)
        self.securityEvents.record(
            "ROLE_ASSIGNED",
            userId=userId,
            tenantId=tenantId,
            reason=f"role:{role.code}",
        )
        self.audit(
            AUDIT_ROLE_CHANGE,
            resourceType="User",
            resourceId=str(userId),
            tenantId=tenantId,
            after={"roleId": str(roleId), "roleCode": role.code},
        )
        return {"assigned": True, "roleId": str(roleId), "userId": str(userId)}


class RemoveRoleUseCase(UseCase[RemoveRoleCommand, object]):
    """§31 — revoke a role: effective immediately via §28 invalidation."""

    requiredAction = "user.assignRole"

    def __init__(
        self,
        roleRepository: RoleRepository,
        accessRepository: AccessRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository
        self.accessRepository = accessRepository
        self.securityEvents = securityEvents

    def perform(self, command: RemoveRoleCommand) -> object:
        userId = asUuid(command.userId)
        roleId = asUuid(command.roleId)
        role = self.roleRepository.getById(roleId)
        if role is None:
            raise EntityNotFoundError("Role", command.roleId)
        self.accessRepository.revokeRoleFromUser(userId, roleId)
        self.securityEvents.record("ROLE_REMOVED", userId=userId, reason=f"role:{role.code}")
        self.audit(
            AUDIT_PERMISSION_CHANGE,
            resourceType="User",
            resourceId=str(userId),
            after={"removedRoleId": str(roleId), "roleCode": role.code},
        )
        return {"removed": True, "roleId": str(roleId), "userId": str(userId)}


class ListRolesUseCase(UseCase[ListRolesQuery, list[RoleDto]]):
    requiredAction = "role.list"

    def __init__(
        self,
        roleRepository: RoleRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.roleRepository = roleRepository

    def perform(self, query: ListRolesQuery) -> list[RoleDto]:
        return [
            RoleDto(
                id=str(role.id),
                code=role.code,
                name=role.name,
                scopeType=role.scopeType,
                actions=list(role.actions),
            )
            for role in self.roleRepository.list()
        ]
