"""Identity DTOs (§7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class UserDto:
    id: str
    tenantId: str
    username: str
    email: str
    displayName: str
    status: str
    createdAt: str


@dataclass(frozen=True)
class UserPageDto:
    items: list[UserDto] = field(default_factory=list)
    totalCount: int = 0
    page: int = 1
    pageSize: int = 50

    def asMeta(self) -> dict[str, Any]:
        return {
            "pagination": {
                "totalCount": self.totalCount,
                "page": self.page,
                "pageSize": self.pageSize,
                "totalPages": max(1, -(-self.totalCount // self.pageSize)),
                "hasNext": self.page * self.pageSize < self.totalCount,
                "hasPrevious": self.page > 1,
            }
        }


@dataclass(frozen=True)
class SessionTokenDto:
    token: str
    tokenType: str = "Bearer"
    expiresAt: str = ""
    user: UserDto | None = None


@dataclass(frozen=True)
class AccountDto:
    user: UserDto
    permissions: list[str] = field(default_factory=list)


def userDtoFromDomain(user: Any) -> UserDto:
    return UserDto(
        id=str(user.id),
        tenantId=str(user.tenantId),
        username=user.username,
        email=user.email,
        displayName=user.displayName,
        status=str(user.status),
        createdAt=user.createdAt.isoformat(),
    )


@dataclass(frozen=True)
class AuthTokenDto:
    """§7 token pair — short-lived JWT access + opaque rotating refresh."""

    accessToken: str
    refreshToken: str = ""
    tokenType: str = "Bearer"
    expiresIn: int = 0
    expiresAt: str = ""
    user: UserDto | None = None
    mfaRequired: bool = False
    mfaChallenge: str = ""


@dataclass(frozen=True)
class SessionDto:
    id: str
    userId: str
    issuedAt: str
    lastActivityAt: str
    expiresAt: str
    status: str
    ipAddress: str = ""
    userAgent: str = ""
    device: str = ""
    current: bool = False


@dataclass(frozen=True)
class ApiKeyDto:
    id: str
    name: str
    prefix: str
    ownerType: str
    ownerId: str
    scopes: list[str] = field(default_factory=list)
    createdAt: str = ""
    expiresAt: str = ""
    revokedAt: str = ""
    lastUsedAt: str = ""


@dataclass(frozen=True)
class ApiKeyCreatedDto:
    apiKey: ApiKeyDto
    rawKey: str  # shown exactly once (§22)


@dataclass(frozen=True)
class ServiceAccountDto:
    id: str
    tenantId: str
    code: str
    name: str
    description: str
    status: str
    scopes: list[str] = field(default_factory=list)
    createdAt: str = ""
    disabledAt: str = ""


@dataclass(frozen=True)
class RoleDto:
    id: str
    code: str
    name: str
    scopeType: str
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MfaSetupDto:
    factorId: str
    factorType: str
    secret: str  # shown once so the authenticator app can enroll
    otpauthUrl: str


@dataclass(frozen=True)
class MfaConfirmedDto:
    factorId: str
    recoveryCodes: list[str] = field(default_factory=list)  # shown once (§24)
