"""Authorization cache (Phase 07 §28) with hard invalidation.

Grants are cached per (userId, tenantId) for a short TTL; every role or
permission mutation BUMPS THE USER'S VERSION STAMP, so stale grants die
immediately — a revoked permission never stays valid for an unknown period
(invariant §35.9). Cache backend is swappable (LocMem → Redis) behind the
same calls.
"""

from __future__ import annotations

import uuid

CACHE_PREFIX = "tekarai:authz"
DEFAULT_TTL_SECONDS = 60


def grantsCacheKey(userId: uuid.UUID, tenantId: uuid.UUID) -> str:
    return f"{CACHE_PREFIX}:grants:{userId}:{tenantId}"


def versionKey(userId: uuid.UUID) -> str:
    return f"{CACHE_PREFIX}:version:{userId}"


def currentVersion(userId: uuid.UUID) -> int:
    from django.core.cache import cache

    return int(cache.get(versionKey(userId)) or 0)


def bumpVersion(userId: uuid.UUID) -> None:
    """Invalidate every cached decision for this user (§28)."""
    from django.core.cache import cache

    try:
        cache.incr(versionKey(userId))
    except ValueError:
        cache.add(versionKey(userId), 1, timeout=None)


def readGrants(userId: uuid.UUID, tenantId: uuid.UUID) -> list | None:
    from django.core.cache import cache

    return cache.get(f"{grantsCacheKey(userId, tenantId)}:v{currentVersion(userId)}")


def writeGrants(userId: uuid.UUID, tenantId: uuid.UUID, grants: list) -> None:
    from django.core.cache import cache

    cache.set(
        f"{grantsCacheKey(userId, tenantId)}:v{currentVersion(userId)}",
        grants,
        timeout=DEFAULT_TTL_SECONDS,
    )
