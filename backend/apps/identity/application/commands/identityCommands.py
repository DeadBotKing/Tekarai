"""Identity commands (§5)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateUserCommand(Command):
    tenantId: str
    username: str
    email: str
    password: str
    displayName: str = ""


@dataclass(frozen=True)
class AssignUserToTenantCommand(Command):
    userId: str
    targetTenantId: str


@dataclass(frozen=True)
class AuthenticateUserCommand(Command):
    tenantCode: str
    username: str
    password: str


@dataclass(frozen=True)
class RefreshSessionCommand(Command):
    token: str


@dataclass(frozen=True)
class LogoutCommand(Command):
    token: str


@dataclass(frozen=True)
class ChangeUserStatusCommand(Command):
    userId: str
    target: str
