"""Public contract: what the rest of the system may ask the org chart.

This is the only module other bounded contexts import. It answers three
questions and nothing else:

* **What may this user do?** — ``grantsForUser``, consumed by identity when
  it assembles a user's permissions, so that a posting in the chart
  produces real access without identity knowing what a «واحد» is.
* **How far does it reach?** — ``scopeFilterForUser``, used by list
  endpoints to narrow results, and ``userCanActOnRecord`` for the
  per-record check. Both derive from the same resolution so a user never
  sees a row they cannot open.
* **Where does this person sit?** — ``primaryDepartmentIdFor``, so a work
  order can be stamped with the unit that raised it.

Keeping this surface small is what stops the organisation chart from
leaking into every context as a dependency.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

from apps.organization.domain.services.accessMatrix import (
    AccessProfile,
    ScopeFilter,
    buildAccessProfile,
    canActOnRecord,
    scopeFilterFor,
)


def _repository():
    """Resolved lazily so importing this module never touches the ORM.

    Mirrors the pattern used by maintenance's ``inventoryContract``: a
    contract that imports Django models at module scope cannot be imported
    during app loading, which is exactly when identity wants it.
    """
    from apps.organization.infrastructure import orgRepository

    return orgRepository


def accessProfileFor(tenantId: uuid.UUID, userId: uuid.UUID) -> AccessProfile:
    """Resolve everything one user may do, from their postings and the matrix."""
    repository = _repository()
    assignments = repository.assignmentSnapshotsFor(tenantId, userId)
    if not assignments:
        # Short-circuit before touching the rules table. Most requests in a
        # plant that has not adopted the chart yet land here, and this keeps
        # the authorisation path at one indexed query for them.
        return AccessProfile(userId=str(userId))
    positionIds = [x.positionId for x in assignments]
    rules = repository.ruleSnapshotsFor(tenantId, positionIds)
    return buildAccessProfile(str(userId), assignments, rules)


def grantsForUser(tenantId: uuid.UUID, userId: uuid.UUID) -> list[dict]:
    """Action codes this user earns from the chart, for identity to merge.

    Returned as plain dicts rather than identity's ``AccessGrant`` so the
    two contexts do not share a type. Every grant is ``allow`` — the matrix
    is additive by design, and identity's deny-grants still override it.
    """
    profile = accessProfileFor(tenantId, userId)
    return [
        {
            "actionPattern": grant.actionCode,
            "scopeType": "TENANT",
            "scopeRef": "",
            "effect": "allow",
            "orgScope": grant.scope,
        }
        for grant in profile.grants
    ]


def scopeForUser(tenantId: uuid.UUID, userId: uuid.UUID, actionCode: str) -> str:
    """Widest scope this user holds for one action code, or "" if none."""
    return accessProfileFor(tenantId, userId).scopeFor(actionCode)


def scopeFilterForUser(tenantId: uuid.UUID, userId: uuid.UUID, actionCode: str) -> ScopeFilter:
    """How a list endpoint should narrow its query for this user.

    The team roster is fetched here rather than inside the domain because
    "who reports to me" is a database question.
    """
    profile = accessProfileFor(tenantId, userId)
    teamUserIds: tuple[str, ...] = ()
    if profile.scopeFor(actionCode) == "team":
        teamUserIds = tuple(_repository().teamMemberIdsFor(tenantId, userId))
    return scopeFilterFor(profile, actionCode, teamUserIds=teamUserIds)


def userCanActOnRecord(
    tenantId: uuid.UUID,
    userId: uuid.UUID,
    actionCode: str,
    *,
    ownerUserId: str = "",
    departmentId: str = "",
) -> bool:
    """Per-record check — the other half of ``scopeFilterForUser``."""
    profile = accessProfileFor(tenantId, userId)
    teamUserIds: tuple[str, ...] = ()
    if profile.scopeFor(actionCode) == "team":
        teamUserIds = tuple(_repository().teamMemberIdsFor(tenantId, userId))
    return canActOnRecord(
        profile,
        actionCode,
        ownerUserId=ownerUserId,
        departmentId=departmentId,
        teamUserIds=teamUserIds,
    )


def primaryDepartmentIdFor(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    """The unit a person's work is attributed to, or "" if unposted."""
    return _repository().primaryDepartmentFor(tenantId, userId)


def departmentIdsForUser(tenantId: uuid.UUID, userId: uuid.UUID) -> list[str]:
    return _repository().departmentIdsForUser(tenantId, userId)


def hasOrganizationStructure(tenantId: uuid.UUID) -> bool:
    """Whether this tenant uses the chart at all.

    Lets callers keep working unchanged on an installation that has not
    adopted departments yet — adding this feature must not lock out a plant
    that has not filled it in.
    """
    return bool(_repository().listDepartments(tenantId, includeInactive=False))


@lru_cache(maxsize=1)
def capabilityCatalogue() -> tuple[dict, ...]:
    """The grid definition, for anyone rendering or validating it."""
    from apps.organization.domain.valueObjects.orgStructure import CAPABILITIES

    return CAPABILITIES
