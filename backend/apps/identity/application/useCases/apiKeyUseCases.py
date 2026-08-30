"""API-key use cases (Phase 07 §22, §31, §21).

The RAW key exists exactly once — in the command's return value. Only the
SHA-256 hash is persisted (§22; DoD §41). Revocation is immediate
(invariant §35.6) and both create/revoke emit §27 security events.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from apps.identity.application.commands.identityCommands import (
    CreateApiKeyCommand,
    RevokeApiKeyCommand,
)
from apps.identity.application.dto.identityDtos import (
    ApiKeyCreatedDto,
    ApiKeyDto,
)
from apps.identity.application.queries.identityQueries import ListApiKeysQuery
from apps.identity.domain.entities.apiKey import ApiKey
from apps.identity.domain.repositories.identityRepositories import (
    ApiKeyRepository,
    SecurityEventRecorder,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_CREATE,
    AUDIT_DELETE,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

KEY_LIFETIME_DAYS = 365


class CreateApiKeyUseCase(UseCase[CreateApiKeyCommand, ApiKeyCreatedDto]):
    requiredAction = "apikey.create"

    def __init__(
        self,
        apiKeyRepository: ApiKeyRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.apiKeyRepository = apiKeyRepository
        self.securityEvents = securityEvents

    def validateCommand(self, command: CreateApiKeyCommand) -> None:
        if not command.name.strip():
            raise ValidationFailedError("API key name is required.")
        if command.ownerType not in {"user", "serviceAccount"}:
            raise ValidationFailedError(
                "ownerType must be user or serviceAccount.",
                fieldErrors={"ownerType": command.ownerType},
            )

    def perform(self, command: CreateApiKeyCommand) -> ApiKeyCreatedDto:

        import uuid

        context = currentContext()
        ownerId = asUuid(command.ownerId) if command.ownerId else uuid.UUID(context.actorId)

        rawKey = f"tek_{secrets.token_urlsafe(32)}"
        expiresAt = None
        if command.expiresAt:
            expiresAt = datetime.fromisoformat(command.expiresAt)
            if expiresAt.tzinfo is None:
                expiresAt = expiresAt.replace(tzinfo=UTC)
        apiKey = ApiKey.issue(
            tenantId=asUuid(command.tenantId),
            name=command.name.strip(),
            keyHash=hashlib.sha256(rawKey.encode("utf-8")).hexdigest(),
            prefix=rawKey[:8],
            ownerType=command.ownerType,
            ownerId=ownerId,
            now=self.clock.nowUtc(),
            scopes=tuple(command.scopes),
            expiresAt=expiresAt,
        )
        self.apiKeyRepository.create(apiKey)
        self.collectEventsFrom(apiKey)
        self.securityEvents.record(
            "API_KEY_CREATED", tenantId=apiKey.tenantId, reason=f"name:{apiKey.name}"
        )
        self.audit(
            AUDIT_CREATE,
            resourceType="ApiKey",
            resourceId=str(apiKey.id),
            tenantId=apiKey.tenantId,
            after={"name": apiKey.name, "prefix": apiKey.prefix},
        )
        return ApiKeyCreatedDto(
            apiKey=ApiKeyDto(
                id=str(apiKey.id),
                name=apiKey.name,
                prefix=apiKey.prefix,
                ownerType=apiKey.ownerType,
                ownerId=str(apiKey.ownerId),
                scopes=list(apiKey.scopes),
                createdAt=apiKey.createdAt.isoformat(),
                expiresAt=apiKey.expiresAt.isoformat() if apiKey.expiresAt else "",
            ),
            rawKey=rawKey,  # shown exactly once (§22)
        )


class RevokeApiKeyUseCase(UseCase[RevokeApiKeyCommand, object]):
    requiredAction = "apikey.revoke"

    def __init__(
        self,
        apiKeyRepository: ApiKeyRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.apiKeyRepository = apiKeyRepository
        self.securityEvents = securityEvents

    def perform(self, command: RevokeApiKeyCommand) -> object:
        apiKeyId = asUuid(command.apiKeyId)
        apiKey = self.apiKeyRepository.getById(apiKeyId)
        if apiKey is None:
            raise EntityNotFoundError("ApiKey", command.apiKeyId)
        now = self.clock.nowUtc()
        apiKey.revoke(now)
        self.apiKeyRepository.revoke(apiKeyId, now)
        self.collectEventsFrom(apiKey)
        self.securityEvents.record(
            "API_KEY_REVOKED",
            tenantId=apiKey.tenantId,
            reason=f"prefix:{apiKey.prefix}",
        )
        self.audit(
            AUDIT_DELETE,
            resourceType="ApiKey",
            resourceId=str(apiKeyId),
            tenantId=apiKey.tenantId,
        )
        return {"revoked": True, "apiKeyId": str(apiKeyId)}


class ListApiKeysUseCase(UseCase[ListApiKeysQuery, list[ApiKeyDto]]):
    """Owners see their keys (hashes never leave; only metadata §22)."""

    def __init__(
        self,
        apiKeyRepository: ApiKeyRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.apiKeyRepository = apiKeyRepository

    def perform(self, query: ListApiKeysQuery) -> list[ApiKeyDto]:
        context = currentContext()
        ownerId = asUuid(query.ownerId) if query.ownerId else asUuid(context.actorId)
        keys = self.apiKeyRepository.listForOwner(query.ownerType, ownerId)
        return [
            ApiKeyDto(
                id=str(k.id),
                name=k.name,
                prefix=k.prefix,
                ownerType=k.ownerType,
                ownerId=str(k.ownerId),
                scopes=list(k.scopes),
                createdAt=k.createdAt.isoformat(),
                expiresAt=k.expiresAt.isoformat() if k.expiresAt else "",
                revokedAt=k.revokedAt.isoformat() if k.revokedAt else "",
                lastUsedAt=k.lastUsedAt.isoformat() if k.lastUsedAt else "",
            )
            for k in keys
        ]
