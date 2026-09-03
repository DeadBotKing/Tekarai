"""Identity repository ORM implementations (Phase 07).

Maps aggregates ↔ models; every selector is tenant-scoped where the contract
demands it (BR-TEN-001). IntegrityErrors map to stable error codes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.db import IntegrityError
from django.db.models import Q

from apps.identity.domain.entities.apiKey import ApiKey
from apps.identity.domain.entities.credential import (
    PasswordHistoryEntry,
    PasswordResetToken,
    VerificationToken,
)
from apps.identity.domain.entities.mfa import MfaFactor
from apps.identity.domain.entities.serviceAccount import ServiceAccount
from apps.identity.domain.entities.session import Session
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.entities.user import User
from apps.identity.domain.repositories.identityRepositories import (
    RoleSummary,
    UserFilters,
    UserPage,
)
from apps.identity.domain.valueObjects.accessGrant import AccessGrant
from apps.identity.domain.valueObjects.userState import UserStatus
from apps.identity.infrastructure.models import (
    ApiKeyModel,
    MfaFactorModel,
    PasswordHistoryModel,
    PasswordResetTokenModel,
    PermissionModel,
    RecoveryCodeModel,
    RoleModel,
    RolePermissionModel,
    ServiceAccountModel,
    SessionModel,
    TenantMembershipModel,
    UserModel,
    UserPermissionModel,
    UserRoleModel,
    VerificationTokenModel,
)
from apps.sharedKernel.domain.errors import DuplicateIdentifierError

USER_SORTABLE = {"createdAt": "createdAt", "username": "username", "status": "status"}


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class UserRepositoryDjango:
    def create(self, user: User) -> None:
        try:
            UserModel.objects.create(
                id=user.id,
                tenantId=user.tenantId,
                username=user.username,
                email=user.email,
                phone=user.phone,
                passwordHash=user.passwordHash,
                displayName=user.displayName,
                status=str(user.status),
                kind=user.kind,
                lastLoginAt=user.lastLoginAt,
                passwordChangedAt=user.passwordChangedAt,
                failedLoginCount=user.failedLoginCount,
                lockedUntil=user.lockedUntil,
                expiresAt=user.expiresAt,
                createdAt=user.createdAt,
            )
        except IntegrityError as exc:
            raise DuplicateIdentifierError(
                "Username or email already registered in this tenant.",
                details={"ruleId": "BR-TEN-005"},
            ) from exc

    def update(self, user: User) -> None:
        UserModel.objects.filter(id=user.id).update(
            displayName=user.displayName,
            status=str(user.status),
            phone=user.phone,
            passwordHash=user.passwordHash,
            lastLoginAt=user.lastLoginAt,
            passwordChangedAt=user.passwordChangedAt,
            failedLoginCount=user.failedLoginCount,
            lockedUntil=user.lockedUntil,
            expiresAt=user.expiresAt,
            updatedAt=utcnow(),
        )

    def getById(self, userId: uuid.UUID, tenantId: uuid.UUID | None = None) -> User | None:
        queryset = UserModel.objects.filter(id=userId, deletedAt__isnull=True)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def getByIdentifier(self, tenantId: uuid.UUID, identifier: str) -> User | None:
        """Login identifier resolution (§4): username or email, extensible."""
        value = identifier.strip().lower()
        model = (
            UserModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
            .filter(Q(username=value) | Q(email=value))
            .first()
        )
        return self.toDomain(model) if model else None

    def getByUsername(self, tenantId: uuid.UUID, username: str) -> User | None:
        model = UserModel.objects.filter(
            tenantId=tenantId, username=username.lower(), deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def existsByUsername(self, tenantId: uuid.UUID, username: str) -> bool:
        return UserModel.objects.filter(tenantId=tenantId, username=username.lower()).exists()

    def existsByEmail(self, tenantId: uuid.UUID, email: str) -> bool:
        return UserModel.objects.filter(tenantId=tenantId, email=email.lower()).exists()

    def list(self, filters: UserFilters) -> UserPage:
        queryset = UserModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.search:
            queryset = queryset.filter(
                Q(username__icontains=filters.search)
                | Q(email__icontains=filters.search)
                | Q(displayName__icontains=filters.search)
            )
        requestedField = filters.ordering.lstrip("-").split(",")[0].strip()
        if requestedField and requestedField not in USER_SORTABLE:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Field is not sortable.",
                fieldErrors={"ordering": requestedField},
            )
        column = USER_SORTABLE.get(requestedField, "createdAt")
        orderBy = f"-{column}" if filters.ordering.startswith("-") else column
        totalCount = queryset.count()
        pageSize = min(100, max(1, filters.pageSize))
        page = max(1, filters.page)
        items = [
            self.toDomain(model)
            for model in queryset.order_by(orderBy)[(page - 1) * pageSize : page * pageSize]
        ]
        return UserPage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: UserModel) -> User:
        return User(
            id=model.id,
            tenantId=model.tenantId,
            username=model.username,
            email=model.email,
            passwordHash=model.passwordHash,
            displayName=model.displayName,
            status=UserStatus(model.status),
            createdAt=model.createdAt,
            kind=model.kind,
            phone=model.phone,
            lastLoginAt=model.lastLoginAt,
            passwordChangedAt=model.passwordChangedAt,
            failedLoginCount=model.failedLoginCount,
            lockedUntil=model.lockedUntil,
            expiresAt=model.expiresAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )


class SessionRepositoryDjango:
    def create(self, session: Session) -> None:
        SessionModel.objects.create(
            id=session.id,
            userId=session.userId,
            tenantId=session.tenantId,
            refreshTokenHash=session.refreshTokenHash,
            issuedAt=session.issuedAt,
            lastActivityAt=session.lastActivityAt,
            expiresAt=session.expiresAt,
            ipAddress=session.ipAddress,
            userAgent=session.userAgent,
            device=session.device,
        )

    def update(self, session: Session) -> None:
        SessionModel.objects.filter(id=session.id).update(
            refreshTokenHash=session.refreshTokenHash,
            revokedAt=session.revokedAt,
            lastActivityAt=session.lastActivityAt,
            expiresAt=session.expiresAt,
        )

    def getById(self, sessionId: uuid.UUID) -> Session | None:
        model = SessionModel.objects.filter(id=sessionId).first()
        return self.toDomain(model) if model else None

    def findActiveByRefreshHash(self, refreshTokenHash: str) -> Session | None:
        model = SessionModel.objects.filter(refreshTokenHash=refreshTokenHash).first()
        if model is None or model.revokedAt is not None:
            return None
        return self.toDomain(model)

    def listActiveForUser(self, userId: uuid.UUID) -> list[Session]:
        models = SessionModel.objects.filter(
            userId=userId, revokedAt__isnull=True, expiresAt__gt=utcnow()
        ).order_by("-lastActivityAt")
        return [self.toDomain(model) for model in models]

    def revokeAllForUser(self, userId: uuid.UUID, now: datetime) -> int:
        return SessionModel.objects.filter(userId=userId, revokedAt__isnull=True).update(
            revokedAt=now
        )

    @staticmethod
    def toDomain(model: SessionModel) -> Session:
        return Session(
            id=model.id,
            userId=model.userId,
            tenantId=model.tenantId,
            refreshTokenHash=model.refreshTokenHash,
            issuedAt=model.issuedAt,
            expiresAt=model.expiresAt,
            lastActivityAt=model.lastActivityAt,
            revokedAt=model.revokedAt,
            ipAddress=model.ipAddress,
            userAgent=model.userAgent,
            device=model.device,
        )


class TenantMembershipRepositoryDjango:
    def create(self, membership: TenantMembership) -> None:
        TenantMembershipModel.objects.create(
            id=membership.id,
            userId=membership.userId,
            tenantId=membership.tenantId,
            status=membership.status,
            isPrimary=membership.isPrimary,
            defaultRole=membership.defaultRole,
            joinedAt=membership.joinedAt,
            leftAt=membership.leftAt,
        )

    def update(self, membership: TenantMembership) -> None:
        TenantMembershipModel.objects.filter(id=membership.id).update(
            status=membership.status,
            isPrimary=membership.isPrimary,
            defaultRole=membership.defaultRole,
            leftAt=membership.leftAt,
        )

    def get(self, userId: uuid.UUID, tenantId: uuid.UUID) -> TenantMembership | None:
        model = TenantMembershipModel.objects.filter(userId=userId, tenantId=tenantId).first()
        return self.toDomain(model) if model else None

    def existsActive(self, userId: uuid.UUID, tenantId: uuid.UUID) -> bool:
        return TenantMembershipModel.objects.filter(
            userId=userId, tenantId=tenantId, status="active"
        ).exists()

    def listForUser(self, userId: uuid.UUID) -> list[TenantMembership]:
        models = TenantMembershipModel.objects.filter(userId=userId).order_by("joinedAt")
        return [self.toDomain(model) for model in models]

    def activeTenantIdsOfUser(self, userId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            TenantMembershipModel.objects.filter(userId=userId, status="active").values_list(
                "tenantId", flat=True
            )
        )

    @staticmethod
    def toDomain(model: TenantMembershipModel) -> TenantMembership:
        return TenantMembership(
            id=model.id,
            userId=model.userId,
            tenantId=model.tenantId,
            joinedAt=model.joinedAt,
            status=model.status,
            isPrimary=model.isPrimary,
            defaultRole=model.defaultRole,
            leftAt=model.leftAt,
        )


class AccessRepositoryDjango:
    """Grants read model (§28 cache + role/permission writes)."""

    def grantsOfUser(self, userId: uuid.UUID, tenantId: uuid.UUID) -> list[AccessGrant]:
        from apps.identity.infrastructure.services import authorizationCache

        cached = authorizationCache.readGrants(userId, tenantId)
        if cached is not None:
            return [self.toGrant(row) for row in cached]
        grants: list[AccessGrant] = []
        roleRows = UserRoleModel.objects.filter(userId=userId).values(
            "roleId", "scopeType", "scopeRef"
        )
        for roleRow in roleRows:
            role = RoleModel.objects.filter(id=roleRow["roleId"], isActive=True).first()
            if role is None:
                continue
            patterns = RolePermissionModel.objects.filter(roleId=role.id).values_list(
                "actionPattern", flat=True
            )
            for pattern in patterns:
                grants.append(
                    AccessGrant(
                        actionPattern=pattern,
                        scopeType=roleRow["scopeType"] or role.scopeType,
                        scopeRef=roleRow["scopeRef"] or "",
                    )
                )
        for direct in UserPermissionModel.objects.filter(userId=userId):
            grants.append(
                AccessGrant(
                    actionPattern=direct.actionPattern,
                    scopeType=direct.scopeType,
                    scopeRef=direct.scopeRef,
                    effect=direct.effect,
                )
            )
        authorizationCache.writeGrants(
            userId,
            tenantId,
            [
                {
                    "actionPattern": g.actionPattern,
                    "scopeType": g.scopeType,
                    "scopeRef": g.scopeRef,
                    "effect": g.effect,
                }
                for g in grants
            ],
        )
        return grants

    @staticmethod
    def toGrant(row: dict) -> AccessGrant:
        return AccessGrant(
            actionPattern=row["actionPattern"],
            scopeType=row["scopeType"],
            scopeRef=row.get("scopeRef", ""),
            effect=row.get("effect", "allow"),
        )

    def ensureCatalogue(self, actions: list[tuple[str, str]]) -> None:
        for code, description in actions:
            PermissionModel.objects.update_or_create(
                code=code,
                defaults={"module": code.split(".")[0], "description": description},
            )

    def ensureRole(
        self,
        roleCode: str,
        roleName: str,
        actions: list[str],
        scopeType: str = "GLOBAL",
    ) -> uuid.UUID:
        role, _ = RoleModel.objects.get_or_create(
            code=roleCode, defaults={"name": roleName, "scopeType": scopeType}
        )
        for pattern in actions:
            permission = PermissionModel.objects.filter(code=pattern).first()
            if permission is None:
                permission = PermissionModel.objects.create(
                    code=pattern, module=pattern.split(".")[0]
                )
            RolePermissionModel.objects.get_or_create(
                roleId=role.id,
                actionPattern=pattern,
                defaults={"permissionId": permission.id},
            )
        return role.id

    def grantRoleToUser(self, userId: uuid.UUID, tenantId: uuid.UUID, roleId: uuid.UUID) -> None:
        from apps.identity.infrastructure.services.authorizationCache import bumpVersion

        role = RoleModel.objects.filter(id=roleId).first()
        scopeType = role.scopeType if role else "TENANT"
        UserRoleModel.objects.get_or_create(
            userId=userId,
            roleId=roleId,
            scopeType=scopeType,
            defaults={"tenantId": tenantId},
        )
        bumpVersion(userId)  # §28 — no stale grants

    def revokeRoleFromUser(self, userId: uuid.UUID, roleId: uuid.UUID) -> None:
        from apps.identity.infrastructure.services.authorizationCache import bumpVersion

        UserRoleModel.objects.filter(userId=userId, roleId=roleId).delete()
        bumpVersion(userId)  # §28 — revocation effective immediately


class RoleRepositoryDjango:
    def create(self, code: str, name: str, scopeType: str, actions: list[str]) -> uuid.UUID:
        try:
            role = RoleModel.objects.create(code=code, name=name, scopeType=scopeType)
        except IntegrityError as exc:
            raise DuplicateIdentifierError(
                "Role code already exists in this scope.",
                details={"ruleId": "PHASE7-UQ_Role_scope_code"},
            ) from exc
        for pattern in actions:
            permission, _ = PermissionModel.objects.get_or_create(
                code=pattern, defaults={"module": pattern.split(".")[0]}
            )
            RolePermissionModel.objects.create(
                roleId=role.id, permissionId=permission.id, actionPattern=pattern
            )
        return role.id

    def update(self, roleId: uuid.UUID, *, name: str | None, actions: list[str] | None) -> None:
        if name is not None:
            RoleModel.objects.filter(id=roleId).update(name=name)
        if actions is not None:
            RolePermissionModel.objects.filter(roleId=roleId).exclude(
                actionPattern__in=actions
            ).delete()
            for pattern in actions:
                permission, _ = PermissionModel.objects.get_or_create(
                    code=pattern, defaults={"module": pattern.split(".")[0]}
                )
                RolePermissionModel.objects.get_or_create(
                    roleId=roleId,
                    actionPattern=pattern,
                    defaults={"permissionId": permission.id},
                )

    def delete(self, roleId: uuid.UUID) -> None:
        assigned = UserRoleModel.objects.filter(roleId=roleId).exists()
        if assigned:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Role is still assigned to users.", details={"roleId": str(roleId)})
        RoleModel.objects.filter(id=roleId).delete()

    def getById(self, roleId: uuid.UUID) -> RoleSummary | None:
        model = RoleModel.objects.filter(id=roleId).first()
        return self.toSummary(model) if model else None

    def list(self) -> list[RoleSummary]:
        return [self.toSummary(m) for m in RoleModel.objects.all().order_by("code")]

    @staticmethod
    def toSummary(model: RoleModel) -> RoleSummary:
        actions = list(
            RolePermissionModel.objects.filter(roleId=model.id).values_list(
                "actionPattern", flat=True
            )
        )
        return RoleSummary(
            id=model.id,
            code=model.code,
            name=model.name,
            scopeType=model.scopeType,
            actions=actions,
        )


class CredentialRepositoryDjango:
    def addPasswordHistory(self, entry: PasswordHistoryEntry) -> None:
        PasswordHistoryModel.objects.create(
            id=entry.id, userId=entry.userId, passwordHash=entry.passwordHash
        )

    def passwordHistoryOf(self, userId: uuid.UUID, limit: int = 5) -> list[str]:
        return list(
            PasswordHistoryModel.objects.filter(userId=userId)
            .order_by("-createdAt")
            .values_list("passwordHash", flat=True)[:limit]
        )

    def saveVerificationToken(self, token: VerificationToken) -> None:
        VerificationTokenModel.objects.create(
            id=token.id,
            userId=token.userId,
            channel=token.channel,
            destination=token.destination,
            tokenHash=token.tokenHash,
            expiresAt=token.expiresAt,
            createdAt=token.createdAt,
        )

    def findVerificationToken(self, tokenHash: str) -> VerificationToken | None:
        model = VerificationTokenModel.objects.filter(tokenHash=tokenHash).first()
        if model is None:
            return None
        return VerificationToken(
            id=model.id,
            userId=model.userId,
            channel=model.channel,
            destination=model.destination,
            tokenHash=model.tokenHash,
            expiresAt=model.expiresAt,
            attemptCount=model.attemptCount,
            verifiedAt=model.verifiedAt,
            createdAt=model.createdAt,
        )

    def markVerificationTokenVerified(self, tokenId: uuid.UUID) -> None:
        VerificationTokenModel.objects.filter(id=tokenId).update(verifiedAt=utcnow())

    def registerVerificationAttempt(self, tokenId: uuid.UUID) -> None:
        from django.db.models import F

        VerificationTokenModel.objects.filter(id=tokenId).update(attemptCount=F("attemptCount") + 1)

    def saveResetToken(self, token: PasswordResetToken) -> None:
        PasswordResetTokenModel.objects.create(
            id=token.id,
            userId=token.userId,
            tokenHash=token.tokenHash,
            expiresAt=token.expiresAt,
            requestIp=token.requestIp,
            createdAt=token.createdAt,
        )

    def findResetToken(self, tokenHash: str) -> PasswordResetToken | None:
        model = PasswordResetTokenModel.objects.filter(tokenHash=tokenHash).first()
        if model is None:
            return None
        return PasswordResetToken(
            id=model.id,
            userId=model.userId,
            tokenHash=model.tokenHash,
            expiresAt=model.expiresAt,
            usedAt=model.usedAt,
            createdAt=model.createdAt,
            requestIp=model.requestIp,
        )

    def markResetTokenUsed(self, tokenId: uuid.UUID) -> None:
        PasswordResetTokenModel.objects.filter(id=tokenId).update(usedAt=utcnow())


class ApiKeyRepositoryDjango:
    def create(self, apiKey: ApiKey) -> None:
        ApiKeyModel.objects.create(
            id=apiKey.id,
            tenantId=apiKey.tenantId,
            name=apiKey.name,
            prefix=apiKey.prefix,
            keyHash=apiKey.keyHash,
            ownerType=apiKey.ownerType,
            ownerId=apiKey.ownerId,
            scopes=list(apiKey.scopes),
            expiresAt=apiKey.expiresAt,
        )

    def revoke(self, apiKeyId: uuid.UUID, now: datetime) -> None:
        ApiKeyModel.objects.filter(id=apiKeyId).update(revokedAt=now)

    def findByKeyHash(self, keyHash: str) -> ApiKey | None:
        model = ApiKeyModel.objects.filter(keyHash=keyHash).first()
        return self.toDomain(model) if model else None

    def getById(self, apiKeyId: uuid.UUID) -> ApiKey | None:
        model = ApiKeyModel.objects.filter(id=apiKeyId).first()
        return self.toDomain(model) if model else None

    def listForOwner(self, ownerType: str, ownerId: uuid.UUID) -> list[ApiKey]:
        models = ApiKeyModel.objects.filter(ownerType=ownerType, ownerId=ownerId)
        return [self.toDomain(model) for model in models]

    def markUsed(self, apiKeyId: uuid.UUID, now: datetime) -> None:
        ApiKeyModel.objects.filter(id=apiKeyId).update(lastUsedAt=now)

    @staticmethod
    def toDomain(model: ApiKeyModel) -> ApiKey:
        return ApiKey(
            id=model.id,
            tenantId=model.tenantId,
            name=model.name,
            keyHash=model.keyHash,
            prefix=model.prefix,
            ownerType=model.ownerType,
            ownerId=model.ownerId,
            createdAt=model.createdAt,
            scopes=tuple(model.scopes or ()),
            expiresAt=model.expiresAt,
            revokedAt=model.revokedAt,
            lastUsedAt=model.lastUsedAt,
        )


class ServiceAccountRepositoryDjango:
    def create(self, account: ServiceAccount) -> None:
        try:
            ServiceAccountModel.objects.create(
                id=account.id,
                tenantId=account.tenantId,
                code=account.code,
                name=account.name,
                description=account.description,
                status=account.status,
                scopes=list(account.scopes),
            )
        except IntegrityError as exc:
            raise DuplicateIdentifierError(
                "Service account code already exists in this tenant.",
                details={"ruleId": "PHASE7-UQ_ServiceAccount_code"},
            ) from exc

    def update(self, account: ServiceAccount) -> None:
        ServiceAccountModel.objects.filter(id=account.id).update(
            name=account.name,
            description=account.description,
            status=account.status,
            scopes=list(account.scopes),
            disabledAt=account.disabledAt,
        )

    def getById(self, accountId: uuid.UUID) -> ServiceAccount | None:
        model = ServiceAccountModel.objects.filter(id=accountId).first()
        return self.toDomain(model) if model else None

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool:
        return ServiceAccountModel.objects.filter(tenantId=tenantId, code=code.lower()).exists()

    def list(self, tenantId: uuid.UUID) -> list[ServiceAccount]:
        models = ServiceAccountModel.objects.filter(tenantId=tenantId).order_by("code")
        return [self.toDomain(model) for model in models]

    @staticmethod
    def toDomain(model: ServiceAccountModel) -> ServiceAccount:
        return ServiceAccount(
            id=model.id,
            tenantId=model.tenantId,
            code=model.code,
            name=model.name,
            description=model.description,
            createdAt=model.createdAt,
            status=model.status,
            scopes=tuple(model.scopes or ()),
            disabledAt=model.disabledAt,
        )


class MfaRepositoryDjango:
    def save(self, factor: MfaFactor) -> None:
        MfaFactorModel.objects.update_or_create(
            id=factor.id,
            defaults={
                "userId": factor.userId,
                "factorType": factor.factorType,
                "secretRef": factor.secretRef,
                "status": factor.status,
                "confirmedAt": factor.confirmedAt,
            },
        )

    def getById(self, factorId: uuid.UUID) -> MfaFactor | None:
        model = MfaFactorModel.objects.filter(id=factorId).first()
        return self.toDomain(model) if model else None

    def activeFactorOf(self, userId: uuid.UUID) -> MfaFactor | None:
        model = MfaFactorModel.objects.filter(userId=userId, status="active").first()
        return self.toDomain(model) if model else None

    def saveRecoveryCodes(self, userId: uuid.UUID, codeHashes: list[str]) -> None:
        RecoveryCodeModel.objects.filter(userId=userId).delete()
        rows = [RecoveryCodeModel(userId=userId, codeHash=h) for h in codeHashes]
        RecoveryCodeModel.objects.bulk_create(rows)

    def consumeRecoveryCode(self, userId: uuid.UUID, codeHash: str) -> bool:
        updated = RecoveryCodeModel.objects.filter(
            userId=userId, codeHash=codeHash, usedAt__isnull=True
        ).update(usedAt=utcnow())
        return updated > 0

    @staticmethod
    def toDomain(model: MfaFactorModel) -> MfaFactor:
        return MfaFactor(
            id=model.id,
            userId=model.userId,
            factorType=model.factorType,
            secretRef=model.secretRef,
            createdAt=model.createdAt,
            status=model.status,
            confirmedAt=model.confirmedAt,
        )


class RecoveryCodeReader:  # helper used by login challenge verification
    @staticmethod
    def hashOf(code: str) -> str:
        import hashlib

        return hashlib.sha256(code.encode("utf-8")).hexdigest()
