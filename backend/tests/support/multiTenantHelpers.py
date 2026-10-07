"""Builds a second, independent tenant so isolation can actually be tested.

Almost every suite in this repository runs inside one tenant. That is enough
to prove a feature works and useless for proving a tenant cannot reach another
tenant's rows: when the only tenant in the database is your own, every query
looks correctly scoped and a missing filter has nothing to leak.

These helpers create a real second tenant with its own administrator, going
through the application's own use cases rather than writing models directly,
so the fixture cannot drift away from how tenants are really made.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

PASSWORD = "Second-Tenant-2026!"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def createTenantWithAdmin(
    code: str,
    *,
    username: str | None = None,
    password: str = PASSWORD,
    roleCodes: tuple[str, ...] = ("platformAdmin",),
) -> dict[str, object]:
    """A tenant, an active admin inside it, and a usable membership.

    Returns the ids plus the credentials needed to log in through the real
    `/api/v1/auth/login` endpoint, because a test that fabricates a token
    proves nothing about the authentication path it is trying to exercise.
    """

    from apps.identity.application.commands.identityCommands import CreateUserCommand
    from apps.identity.domain.entities.tenantMembership import TenantMembership
    from apps.identity.infrastructure.container import createUserUseCase
    from apps.identity.infrastructure.models import RoleModel
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        AccessRepositoryDjango,
        TenantMembershipRepositoryDjango,
    )
    from apps.sharedKernel.application.requestContext import RequestContext, requestScope
    from apps.tenancy.application.commands.tenantCommands import CreateTenantCommand
    from apps.tenancy.infrastructure.container import createTenantUseCase

    userName = username or f"{code}-admin"

    tenantUseCase = createTenantUseCase()
    tenantUseCase.requiredAction = ""  # fixture seeding has no actor
    with requestScope(RequestContext(actorId="", tenantId="")):
        tenantDto = tenantUseCase.execute(
            CreateTenantCommand(code=code, name=f"Tenant {code}")
        )
    tenantId = uuid.UUID(str(tenantDto.id))

    userUseCase = createUserUseCase()
    userUseCase.requiredAction = ""
    with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
        userDto = userUseCase.execute(
            CreateUserCommand(
                tenantId=str(tenantId),
                username=userName,
                email=f"{userName}@example.test",
                password=password,
                displayName=f"{code} administrator",
            )
        )
    userId = uuid.UUID(str(userDto.id))

    access = AccessRepositoryDjango()
    for roleCode in roleCodes:
        role = RoleModel.objects.filter(code=roleCode).first()
        if role is not None:
            access.grantRoleToUser(userId, tenantId, role.id)

    memberships = TenantMembershipRepositoryDjango()
    if memberships.get(userId, tenantId) is None:
        memberships.create(
            TenantMembership.establish(userId=userId, tenantId=tenantId, now=_now())
        )

    return {
        "tenantId": tenantId,
        "userId": userId,
        "code": code,
        "username": userName,
        "password": password,
    }


def clearRateLimiter() -> None:
    """Drop the login rate-limit counters.

    The limiter is real and should stay on, but it counts across a whole test
    run: a suite with four classes that each log in once trips it and fails
    with 429 for reasons that have nothing to do with what is being tested.
    Clearing the counter is honest here — the limiter has its own tests.
    """

    from django.core.cache import cache

    cache.clear()


def loginAs(client, tenant: dict[str, object]) -> str:
    """Real login against the real endpoint; returns the access token."""

    clearRateLimiter()
    response = client.post(
        "/api/v1/auth/login",
        {
            "tenantCode": tenant["code"],
            "identifier": tenant["username"],
            "password": tenant["password"],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    return str(response.json()["data"]["accessToken"])


def authHeaders(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def loginPlatform(client) -> str:
    """Platform-admin access token, rate limiter cleared first."""

    from tests.support.phase6Helpers import loginViaApi

    clearRateLimiter()
    return str(loginViaApi(client)["accessToken"])
