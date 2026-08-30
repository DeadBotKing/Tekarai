"""Phase 6 test support — platform seeding shared by the new suites."""

from __future__ import annotations

import os
import uuid

from django.core.management import call_command

PLATFORM_ADMIN_PASSWORD = "Platform-Admin-2026!"
PLATFORM_TENANT_CODE = "platform"
PLATFORM_ADMIN_USERNAME = "platform-admin"


def seedPlatform() -> None:
    """Idempotent first-run seed (bootstrapPlatform command)."""
    os.environ["PLATFORM_ADMIN_PASSWORD"] = PLATFORM_ADMIN_PASSWORD
    os.environ.setdefault("PLATFORM_ADMIN_USERNAME", PLATFORM_ADMIN_USERNAME)
    call_command("bootstrapPlatform", verbosity=0)


def platformTenantId() -> uuid.UUID:
    from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
        TenantRepositoryDjango,
    )

    tenant = TenantRepositoryDjango().getByCode(PLATFORM_TENANT_CODE)
    assert tenant is not None, "seedPlatform() must run first"
    return tenant.id


def loginPayload(password: str = PLATFORM_ADMIN_PASSWORD) -> dict[str, str]:
    return {
        "tenantCode": PLATFORM_TENANT_CODE,
        "username": PLATFORM_ADMIN_USERNAME,
        "password": password,
    }
