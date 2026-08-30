"""Identity repository ORM implementations (§10)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.db import IntegrityError

from apps.identity.domain.entities.session import Session
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.entities.user import User
from apps.identity.domain.repositories.identityRepositories import (
    UserFilters,
    UserPage,
)
from apps.identity.domain.valueObjects.accessGrant import AccessGrant
from apps.identity.domain.valueObjects.userState import UserStatus
from apps.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    SessionModel,
    TenantMembershipModel,
    UserModel,
    UserPermissionModel,
    UserRoleModel,
)
from apps.sharedKernel.domain.errors import DuplicateIdentifierError

USER_SORTABLE = {"createdAt": "createdAt", "username": "username", "status": "status"}


class UserRepositoryDjango:
    def create(self, user: User) -> None:
        try:
            UserModel.objects.create(
                id=user.id,
                tenantId=user.tenantId,
                username=user.username,
                email=user.email,
                passwordHash=user.passwordHash,
                displayName=user.displayName,
                status=str(user.status),
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
            updatedAt=datetime.now(tz=UTC),
        )

    def getById(self, userId: uuid.UUID, tenantId: uuid.UUID | None = None) -> User | None:
        queryset = UserModel.objects.filter(id=userId, deletedAt__isnull=True)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
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
            from django.db.models import Q

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
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )


class SessionRepositoryDjango:
    def create(self, session: Session) -> None:
        SessionModel.objects.create(
            id=session.id,
            userId=session.userId,
            tenantId=session.tenantId,
            tokenHash=session.tokenHash,
            issuedAt=session.issuedAt,
            expiresAt=session.expiresAt,
        )

    def update(self, session: Session) -> None:
        SessionModel.objects.filter(id=session.id).update(
            revokedAt=session.revokedAt,
            lastUsedAt=session.lastUsedAt,
            expiresAt=session.expiresAt,
        )

    def findActiveByTokenHash(self, tokenHash: str) -> Session | None:
        model = SessionModel.objects.filter(tokenHash=tokenHash).first()
        if model is None or model.revokedAt is not None:
            return None
        return Session(
            id=model.id,
            userId=model.userId,
            tenantId=model.tenantId,
            tokenHash=model.tokenHash,
            issuedAt=model.issuedAt,
            expiresAt=model.expiresAt,
            lastUsedAt=model.lastUsedAt,
        )


class TenantMembershipRepositoryDjango:
    def create(self, membership: TenantMembership) -> None:
        TenantMembershipModel.objects.create(
            id=membership.id,
            userId=membership.userId,
            tenantId=membership.tenantId,
            joinedAt=membership.joinedAt,
        )

    def existsActive(self, userId: uuid.UUID, tenantId: uuid.UUID) -> bool:
        return TenantMembershipModel.objects.filter(
            userId=userId, tenantId=tenantId, leftAt__isnull=True
        ).exists()

    def activeTenantIdsOfUser(self, userId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            TenantMembershipModel.objects.filter(userId=userId, leftAt__isnull=True).values_list(
                "tenantId", flat=True
            )
        )


class AccessRepositoryDjango:
    """Grants read model: roles→permissions ∪ direct user permissions."""

    def grantsOfUser(self, userId: uuid.UUID, tenantId: uuid.UUID) -> list[AccessGrant]:
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
        del tenantId  # grants are user-scoped; tenant handled by evaluator
        return grants

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
        role = RoleModel.objects.filter(id=roleId).first()
        scopeType = role.scopeType if role else "TENANT"
        UserRoleModel.objects.get_or_create(
            userId=userId,
            roleId=roleId,
            scopeType=scopeType,
            defaults={"tenantId": tenantId},
        )
