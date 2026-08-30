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
