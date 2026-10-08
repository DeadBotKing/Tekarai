"""Public contract for dropping a user's cached authorisation.

Other bounded contexts may import exactly this module — never Identity's
infrastructure. It exists because permissions are not only granted by
Identity any more: the organisation chart («کاربر + واحد + سمت») changes
what a person may do, and a revoked posting has to stop working on the very
next request rather than when a cache entry happens to expire.

Kept to one verb on purpose. A caller should be able to say "this user's
access changed" without knowing that a cache exists, what it is keyed by,
or which backend is behind it.
"""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger(__name__)


def invalidateUser(userId: uuid.UUID | str) -> None:
    """Make this user's next permission check re-read from the database."""
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion

    bumpVersion(uuid.UUID(str(userId)))


def invalidateUsers(userIds: list[str] | list[uuid.UUID]) -> int:
    """Invalidate several users, reporting how many succeeded.

    Failures are logged and swallowed rather than raised. The caller has
    already committed a permission change; refusing to return would leave
    the database and the caller's view of it disagreeing, and the worst
    case here is a short window of stale access that the TTL closes anyway.
    """
    invalidated = 0
    for userId in userIds:
        try:
            invalidateUser(userId)
            invalidated += 1
        except Exception:  # noqa: BLE001 — see docstring
            logger.exception("Authorization cache bump failed", extra={"userId": str(userId)})
    return invalidated
