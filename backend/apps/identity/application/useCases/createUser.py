"""CreateUserUseCase — §8 template for the Identity context.

Rules enforced: BR-USR-001 (User is an identity record, not an employee),
tenant-scoped uniqueness of username/email (Phase 05 ConstraintCatalog
UQ_User_email / UQ_User_username → DUP_IDENTIFIER), password policy (§31).
"""

from __future__ import annotations

from apps.identity.application.commands.identityCommands import CreateUserCommand
from apps.identity.application.dto.identityDtos import UserDto, userDtoFromDomain
from apps.identity.domain.entities.user import User
from apps.identity.domain.repositories.identityRepositories import UserRepository
from apps.identity.domain.services.passwordHasher import PasswordHasher
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, UseCase
from apps.sharedKernel.domain.errors import (
    DuplicateIdentifierError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import EmailAddress, asUuid


class CreateUserUseCase(UseCase[CreateUserCommand, UserDto]):
    requiredAction = "user.create"

    def __init__(
        self,
        repository: UserRepository,
        passwordHasher: PasswordHasher,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.passwordHasher = passwordHasher

    def validateCommand(self, command: CreateUserCommand) -> None:
        if (
            command.username.strip().lower() != command.username.lower()
            or not command.username.strip()
        ):
            raise ValidationFailedError(
                "Username must be non-empty lowercase.",
                fieldErrors={"username": "format"},
            )
        EmailAddress(command.email)  # raises ValidationFailedError
        validatePasswordStrength(command.password)

    def businessRules(self, command: CreateUserCommand) -> None:
        tenantId = asUuid(command.tenantId)
        if self.repository.existsByUsername(tenantId, command.username):
            raise DuplicateIdentifierError(
                "Username already registered in this tenant.",
                details={"field": "username", "ruleId": "BR-TEN-005"},
            )
        if self.repository.existsByEmail(tenantId, str(EmailAddress(command.email))):
            raise DuplicateIdentifierError(
                "Email already registered in this tenant.",
                details={"field": "email", "ruleId": "BR-TEN-005"},
            )

    def perform(self, command: CreateUserCommand) -> UserDto:
        tenantId = asUuid(command.tenantId)
        user = User.register(
            tenantId=tenantId,
            username=command.username,
            email=command.email,
            passwordHash=self.passwordHasher.hash(command.password),
            displayName=command.displayName or command.username,
            now=self.clock.nowUtc(),
        )
        self.repository.create(user)
        self.collectEventsFrom(user)
        self.audit(
            AUDIT_CREATE,
            resourceType="User",
            resourceId=str(user.id),
            tenantId=tenantId,
            after=user.snapshot(),
        )
        return userDtoFromDomain(user)
