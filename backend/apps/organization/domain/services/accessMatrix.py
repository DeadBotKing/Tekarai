"""Turning «کاربر + واحد + سمت» into a concrete set of permissions.

Pure functions over plain snapshots: no ORM, no cache, no request. The
whole authorisation decision for the organisation chart is decided here, so
it can be read in one sitting and tested without a database.

The rules, and why each one is the way it is:

* **A grant comes from a (department, position) pair, never from a position
  alone.** «مدیر» is not a level of trust; «مدیر واحد فنی» is. A position
  row by itself grants nothing, which is what stops a new «مدیر تدارکات»
  from silently inheriting the maintenance manager's authority.

* **Rules may be department-specific or apply to every department.** A rule
  with no department is the organisation-wide default for that position
  ("every سرپرست can do this"); a rule naming a department overrides it
  there. Without the default, opening a new unit would mean re-entering the
  entire matrix by hand, and in practice somebody would copy it wrong.

* **The widest scope wins when grants collide.** A user holding two
  assignments picks up the union of both. Intersecting instead would mean
  adding a responsibility could silently *remove* access, which is the
  behaviour that makes people share logins.

* **Deny is not expressible here, on purpose.** This matrix is additive:
  an empty cell grants nothing. Identity's existing ``UserPermission``
  deny-grants remain the only way to subtract, and they still override
  everything, so there is exactly one place to look when someone must be
  locked out.

* **Inactive anything grants nothing.** A deactivated department, position
  or assignment stops contributing immediately, because "غیرفعال" has to
  mean the access is gone, not that it is hidden from a list.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.organization.domain.valueObjects.orgStructure import (
    SCOPE_ALL,
    SCOPE_DEPARTMENT,
    SCOPE_OWN,
    SCOPE_RANK,
    SCOPE_TEAM,
    actionCodesFor,
    defaultScopeFor,
    isScoped,
    scopeCovers,
    widestScope,
)


@dataclass(frozen=True)
class AssignmentSnapshot:
    """One «کاربر در واحد با سمت» posting."""

    userId: str
    departmentId: str
    positionId: str
    positionCode: str = ""
    positionLevel: int = 0
    departmentCode: str = ""
    isActive: bool = True


@dataclass(frozen=True)
class RuleSnapshot:
    """One cell of the matrix.

    ``departmentId`` empty means "every department" — the organisation-wide
    default for this position.
    """

    positionId: str
    capability: str
    action: str
    scope: str
    departmentId: str = ""
    isActive: bool = True

    @property
    def isOrganizationWide(self) -> bool:
        return not self.departmentId


@dataclass(frozen=True)
class EffectiveGrant:
    """One resolved permission: a real action code plus how far it reaches."""

    actionCode: str
    scope: str
    capability: str
    action: str
    #: Departments this grant was earned in. Needed by ``department`` scope:
    #: a user who is رئیس of two units sees both, and only those two.
    departmentIds: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessProfile:
    """Everything the system knows about what one user may do."""

    userId: str
    grants: tuple[EffectiveGrant, ...] = ()
    departmentIds: tuple[str, ...] = ()
    assignments: tuple[AssignmentSnapshot, ...] = ()
    #: Highest position level held, used only for the team-scope question.
    topLevel: int = 0

    def scopeFor(self, actionCode: str) -> str:
        """Widest scope this user holds for an action code, or "" if none."""
        best = ""
        for grant in self.grants:
            if grant.actionCode != actionCode:
                continue
            best = grant.scope if not best else widestScope(best, grant.scope)
        return best

    def can(self, actionCode: str, *, requiredScope: str = SCOPE_OWN) -> bool:
        scope = self.scopeFor(actionCode)
        return bool(scope) and scopeCovers(scope, requiredScope)

    def departmentsFor(self, actionCode: str) -> tuple[str, ...]:
        """Departments in which the user holds this action code."""
        found: list[str] = []
        for grant in self.grants:
            if grant.actionCode != actionCode:
                continue
            for departmentId in grant.departmentIds:
                if departmentId not in found:
                    found.append(departmentId)
        return tuple(found)


def _applicableRules(
    rules: list[RuleSnapshot], assignment: AssignmentSnapshot
) -> dict[tuple[str, str], str]:
    """Resolve the cells one posting earns, department rule beating default.

    Returns ``{(capability, action): scope}``.
    """
    resolved: dict[tuple[str, str], str] = {}
    specific: dict[tuple[str, str], str] = {}

    for rule in rules:
        if not rule.isActive or rule.positionId != assignment.positionId:
            continue
        key = (rule.capability, rule.action)
        if rule.isOrganizationWide:
            # Two organisation-wide rules for one cell should not exist, but
            # if a bad import creates them, prefer the wider rather than
            # whichever row the database happened to return first.
            resolved[key] = widestScope(resolved.get(key, ""), rule.scope or "")
        elif rule.departmentId == assignment.departmentId:
            specific[key] = widestScope(specific.get(key, ""), rule.scope or "")

    # A department-specific rule replaces the default outright — including
    # when it is *narrower*. That is the point of writing one: a plant that
    # says «در واحد ایمنی، سرپرست فقط موارد خودش را ببیند» must be obeyed,
    # not quietly widened back by the organisation default.
    resolved.update(specific)
    return resolved


def buildAccessProfile(
    userId: str,
    assignments: list[AssignmentSnapshot],
    rules: list[RuleSnapshot],
) -> AccessProfile:
    """Compute everything one user may do, from their postings and the matrix."""
    activeAssignments = [x for x in assignments if x.isActive and x.userId == str(userId)]
    if not activeAssignments:
        return AccessProfile(userId=str(userId))

    # (actionCode, capability, action) → scope, plus where it was earned.
    collected: dict[tuple[str, str, str], str] = {}
    origins: dict[tuple[str, str, str], list[str]] = {}

    for assignment in activeAssignments:
        for (capability, action), scope in _applicableRules(rules, assignment).items():
            effectiveScope = scope or defaultScopeFor(capability)
            if not isScoped(capability):
                # An unscoped capability is plant-wide by nature. Storing a
                # narrower scope against it would be meaningless, and acting
                # on it would silently hide the shared catalogue.
                effectiveScope = SCOPE_ALL
            for actionCode in actionCodesFor(capability, action):
                key = (actionCode, capability, action)
                collected[key] = widestScope(collected.get(key, ""), effectiveScope)
                origins.setdefault(key, [])
                if assignment.departmentId not in origins[key]:
                    origins[key].append(assignment.departmentId)

    grants = tuple(
        EffectiveGrant(
            actionCode=actionCode,
            scope=scope,
            capability=capability,
            action=action,
            departmentIds=tuple(origins[(actionCode, capability, action)]),
        )
        for (actionCode, capability, action), scope in sorted(collected.items())
    )

    departmentIds: list[str] = []
    for assignment in activeAssignments:
        if assignment.departmentId not in departmentIds:
            departmentIds.append(assignment.departmentId)

    return AccessProfile(
        userId=str(userId),
        grants=grants,
        departmentIds=tuple(departmentIds),
        assignments=tuple(activeAssignments),
        topLevel=max((x.positionLevel for x in activeAssignments), default=0),
    )


# --- Applying a scope to a query ------------------------------------------


@dataclass(frozen=True)
class ScopeFilter:
    """How a list endpoint should narrow its results for this user.

    Exactly one of the flags is meaningful at a time; the shape is flat so a
    repository can act on it without re-deriving the rules.
    """

    #: Nothing matches. Returned when the user holds no grant at all — the
    #: caller must produce an empty list, never an unfiltered one.
    denied: bool = False
    #: No narrowing: the user sees the whole tenant.
    unrestricted: bool = False
    #: Restrict to records owned by / assigned to these user ids.
    userIds: tuple[str, ...] = ()
    #: Restrict to records belonging to these departments.
    departmentIds: tuple[str, ...] = ()
    scope: str = ""


def scopeFilterFor(
    profile: AccessProfile,
    actionCode: str,
    *,
    teamUserIds: tuple[str, ...] = (),
) -> ScopeFilter:
    """Translate a user's scope for one action into a concrete filter.

    ``teamUserIds`` is supplied by the caller because "who is in my team" is
    a database question; the rule for *using* it lives here.
    """
    scope = profile.scopeFor(actionCode)
    if not scope:
        # Fail closed. A missing grant must not fall through to "show
        # everything" — that is the bug that leaks another plant's data.
        return ScopeFilter(denied=True)

    if scope == SCOPE_ALL:
        return ScopeFilter(unrestricted=True, scope=scope)

    if scope == SCOPE_DEPARTMENT:
        departments = profile.departmentsFor(actionCode) or profile.departmentIds
        return ScopeFilter(departmentIds=tuple(departments), scope=scope)

    if scope == SCOPE_TEAM:
        # The user always belongs to their own team; a supervisor with an
        # empty roster must still see their own work rather than nothing.
        members = tuple(dict.fromkeys((profile.userId, *teamUserIds)))
        return ScopeFilter(userIds=members, scope=scope)

    return ScopeFilter(userIds=(profile.userId,), scope=SCOPE_OWN)


def canActOnRecord(
    profile: AccessProfile,
    actionCode: str,
    *,
    ownerUserId: str = "",
    departmentId: str = "",
    teamUserIds: tuple[str, ...] = (),
) -> bool:
    """Object-level check: may this user do this to *this* record?

    The list filter and this function must agree, or a user will see a row
    they cannot open — or worse, open one they should not have seen. Both
    are derived from the same ``scopeFilterFor`` result for that reason.
    """
    scopeFilter = scopeFilterFor(profile, actionCode, teamUserIds=teamUserIds)
    if scopeFilter.denied:
        return False
    if scopeFilter.unrestricted:
        return True
    if scopeFilter.userIds:
        return str(ownerUserId) in scopeFilter.userIds
    if scopeFilter.departmentIds:
        return str(departmentId) in scopeFilter.departmentIds
    return False


def matrixView(
    rules: list[RuleSnapshot], departmentId: str = ""
) -> dict[str, dict[str, dict[str, str]]]:
    """The grid for one department, as ``{positionId: {capability: {action: scope}}}``.

    Organisation-wide defaults are folded in first so the screen shows what
    is *in force*, not only what was typed for this unit. An administrator
    who sees blank cells that nonetheless grant access will not trust the
    screen, and an untrusted permission screen gets worked around.
    """
    view: dict[str, dict[str, dict[str, str]]] = {}
    for wideFirst in (True, False):
        for rule in rules:
            if not rule.isActive:
                continue
            if rule.isOrganizationWide != wideFirst:
                continue
            if not rule.isOrganizationWide:
                # With no unit selected the caller is asking for the
                # organisation-wide defaults, so every unit's override is
                # excluded. Letting them through would merge all units into
                # one grid and show a scope that applies in none of them.
                if not departmentId or rule.departmentId != departmentId:
                    continue
            view.setdefault(rule.positionId, {}).setdefault(rule.capability, {})[rule.action] = (
                rule.scope
            )
    return view


def describeScope(scope: str) -> int:
    """Numeric rank, exposed so the UI can sort and compare scopes."""
    return SCOPE_RANK.get(scope, -1)
