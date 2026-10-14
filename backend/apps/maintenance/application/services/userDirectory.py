"""Platform-user lookups for the maintenance app (v0.16.0).

The workforce directory (پرسنل نت) is its own thing: a technician exists as
a person with a specialty and a shift before any account exists. Linking a
person to the account they sign in with is what lets features such as the
user dashboard match work by identity instead of by display name — names
drift, ids do not.

Cross-context access goes through Identity's PUBLIC application facade
(RULE F / ADR-021) — never Identity's internals.
"""

from __future__ import annotations

import uuid

from apps.identity.application.services import principalDirectory


def findActiveUser(
    tenantId: uuid.UUID, userId: uuid.UUID
) -> tuple[uuid.UUID, str] | None:
    """One living user of this tenant as ``(id, displayName)``, or None.

    A deleted account cannot hold a link; a missing one was never linkable.
    """
    if not principalDirectory.userExists(tenantId, userId):
        return None
    return userId, principalDirectory.userDisplayNameOf(tenantId, userId)


def userDisplayNames(tenantId: uuid.UUID, userIds) -> dict[uuid.UUID, str]:
    """Display names for a batch of user ids — the list view's lookup."""
    names: dict[uuid.UUID, str] = {}
    for userId in {value for value in userIds if value is not None}:
        name = principalDirectory.userDisplayNameOf(tenantId, userId)
        if name:
            names[userId] = name
    return names
