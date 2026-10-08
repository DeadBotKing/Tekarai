"""The «کاربر + واحد + سمت» → permission resolution, tested in isolation.

No database. These are the rules that decide who can do what, so they are
pinned on their own, including the cases where two postings collide and the
cases where the answer must be "nothing".
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.organization.domain.services.accessMatrix import (
    AssignmentSnapshot,
    RuleSnapshot,
    buildAccessProfile,
    canActOnRecord,
    matrixView,
    scopeFilterFor,
)
from apps.organization.domain.valueObjects.orgStructure import (
    ACTION_APPROVE,
    ACTION_CREATE,
    ACTION_EDIT,
    ACTION_VIEW,
    ACTIONS,
    CAPABILITIES,
    CAPABILITY_BY_KEY,
    SCOPE_ALL,
    SCOPE_DEPARTMENT,
    SCOPE_OWN,
    SCOPE_TEAM,
    actionCodesFor,
    actionsFor,
    defaultScopeFor,
    isScoped,
    scopeCovers,
    widestScope,
)

ENG = "dept-eng"
QA = "dept-qa"
MANAGER = "pos-manager"
TECHNICIAN = "pos-technician"
SUPERVISOR = "pos-supervisor"

WO_VIEW = "maintenance.workorder.list"
WO_EDIT = "maintenance.workorder.update"
WO_APPROVE = "maintenance.workorder.approve"


def posting(user, department, position, *, level=0, active=True) -> AssignmentSnapshot:
    return AssignmentSnapshot(
        userId=user,
        departmentId=department,
        positionId=position,
        positionLevel=level,
        isActive=active,
    )


def rule(position, capability, action, scope, *, department="", active=True) -> RuleSnapshot:
    return RuleSnapshot(
        positionId=position,
        capability=capability,
        action=action,
        scope=scope,
        departmentId=department,
        isActive=active,
    )


class ScopeVocabularyTests(SimpleTestCase):
    def testScopesAreOrderedWeakestToStrongest(self):
        self.assertTrue(scopeCovers(SCOPE_ALL, SCOPE_OWN))
        self.assertTrue(scopeCovers(SCOPE_DEPARTMENT, SCOPE_TEAM))
        self.assertFalse(scopeCovers(SCOPE_OWN, SCOPE_DEPARTMENT))
        self.assertFalse(scopeCovers(SCOPE_TEAM, SCOPE_ALL))

    def testTheWidestScopeWins(self):
        self.assertEqual(widestScope(SCOPE_OWN, SCOPE_ALL), SCOPE_ALL)
        self.assertEqual(widestScope(SCOPE_DEPARTMENT, SCOPE_TEAM), SCOPE_DEPARTMENT)

    def testAnUnknownScopeNeverCoversAnything(self):
        """Fail closed: a typo in a seed must not become a wildcard."""
        self.assertFalse(scopeCovers("supervisorish", SCOPE_OWN))


class CapabilityCatalogueTests(SimpleTestCase):
    def testEveryCellMapsToAtLeastOneRealActionCode(self):
        """A tick that grants nothing is worse than no tick at all."""
        for capability in CAPABILITIES:
            for action in capability["actions"]:
                codes = actionCodesFor(capability["key"], action)
                self.assertTrue(codes, f"{capability['key']}.{action}")
                for code in codes:
                    self.assertIn(".", code)

    def testCapabilityActionsAreReturnedInCatalogueOrder(self):
        actions = actionsFor("workOrder")
        self.assertEqual(actions, tuple(x for x in ACTIONS if x in actions))

    def testAnUnknownCapabilityGrantsNothing(self):
        self.assertEqual(actionCodesFor("nonsense", ACTION_VIEW), ())
        self.assertEqual(actionsFor("nonsense"), ())

    def testAnUnknownActionOnAKnownCapabilityGrantsNothing(self):
        self.assertEqual(actionCodesFor("workOrder", "teleport"), ())

    def testUnscopedCapabilitiesDefaultToPlantWide(self):
        self.assertFalse(isScoped("inventory"))
        self.assertEqual(defaultScopeFor("inventory"), SCOPE_ALL)
        self.assertTrue(isScoped("workOrder"))

    def testEveryCapabilityDeclaresAGroupAndPersianLabel(self):
        for capability in CAPABILITIES:
            self.assertTrue(capability["labelFa"])
            self.assertTrue(capability["group"])


class ProfileBuildingTests(SimpleTestCase):
    def testNoAssignmentMeansNoAccess(self):
        """A user who has not been posted anywhere can do nothing."""
        profile = buildAccessProfile("u1", [], [rule(MANAGER, "workOrder", ACTION_VIEW, SCOPE_ALL)])
        self.assertEqual(profile.grants, ())
        self.assertFalse(profile.can(WO_VIEW))

    def testAPositionAloneGrantsNothingWithoutADepartment(self):
        """«مدیر» is not a level of trust; «مدیر واحد فنی» is."""
        rules = [rule(MANAGER, "workOrder", ACTION_APPROVE, SCOPE_ALL)]
        profile = buildAccessProfile("u1", [posting("u1", "", MANAGER)], rules)
        # An assignment with no department still resolves only org-wide
        # rules, and cannot reach a department-specific one.
        self.assertTrue(profile.can(WO_APPROVE))
        scoped = buildAccessProfile(
            "u1",
            [posting("u1", "", MANAGER)],
            [rule(MANAGER, "workOrder", ACTION_APPROVE, SCOPE_ALL, department=ENG)],
        )
        self.assertFalse(scoped.can(WO_APPROVE))

    def testTheGridCellBecomesRealActionCodes(self):
        rules = [rule(TECHNICIAN, "workOrder", ACTION_VIEW, SCOPE_OWN)]
        profile = buildAccessProfile("u1", [posting("u1", ENG, TECHNICIAN)], rules)
        codes = {x.actionCode for x in profile.grants}
        self.assertIn("maintenance.workorder.list", codes)
        self.assertIn("maintenance.workorder.view", codes)

    def testADepartmentRuleOverridesTheOrganisationDefault(self):
        """Including when it is narrower — a plant saying «فقط خودش» in
        one unit must be obeyed, not widened back."""
        rules = [
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_DEPARTMENT),
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_OWN, department=QA),
        ]
        inEng = buildAccessProfile("u1", [posting("u1", ENG, SUPERVISOR)], rules)
        inQa = buildAccessProfile("u2", [posting("u2", QA, SUPERVISOR)], rules)
        self.assertEqual(inEng.scopeFor(WO_VIEW), SCOPE_DEPARTMENT)
        self.assertEqual(inQa.scopeFor(WO_VIEW), SCOPE_OWN)

    def testTwoPostingsGiveTheUnionAtTheWidestScope(self):
        """Adding a responsibility must never remove access."""
        rules = [
            rule(TECHNICIAN, "workOrder", ACTION_VIEW, SCOPE_OWN),
            rule(MANAGER, "workOrder", ACTION_VIEW, SCOPE_ALL),
        ]
        profile = buildAccessProfile(
            "u1", [posting("u1", ENG, TECHNICIAN), posting("u1", QA, MANAGER)], rules
        )
        self.assertEqual(profile.scopeFor(WO_VIEW), SCOPE_ALL)

    def testAnInactiveAssignmentGrantsNothing(self):
        rules = [rule(MANAGER, "workOrder", ACTION_APPROVE, SCOPE_ALL)]
        profile = buildAccessProfile("u1", [posting("u1", ENG, MANAGER, active=False)], rules)
        self.assertFalse(profile.can(WO_APPROVE))

    def testAnInactiveRuleGrantsNothing(self):
        rules = [rule(MANAGER, "workOrder", ACTION_APPROVE, SCOPE_ALL, active=False)]
        profile = buildAccessProfile("u1", [posting("u1", ENG, MANAGER)], rules)
        self.assertFalse(profile.can(WO_APPROVE))

    def testAnotherUsersAssignmentIsIgnored(self):
        rules = [rule(MANAGER, "workOrder", ACTION_APPROVE, SCOPE_ALL)]
        profile = buildAccessProfile("u1", [posting("u2", ENG, MANAGER)], rules)
        self.assertFalse(profile.can(WO_APPROVE))

    def testAnUnscopedCapabilityIsAlwaysPlantWide(self):
        """Narrowing a shared catalogue would silently break the warehouse."""
        rules = [rule(TECHNICIAN, "inventory", ACTION_VIEW, SCOPE_OWN)]
        profile = buildAccessProfile("u1", [posting("u1", ENG, TECHNICIAN)], rules)
        self.assertEqual(profile.scopeFor("maintenance.inventory.view"), SCOPE_ALL)

    def testAMissingScopeFallsBackToTheCapabilityDefault(self):
        rules = [rule(SUPERVISOR, "workOrder", ACTION_VIEW, "")]
        profile = buildAccessProfile("u1", [posting("u1", ENG, SUPERVISOR)], rules)
        self.assertEqual(profile.scopeFor(WO_VIEW), SCOPE_DEPARTMENT)

    def testTheProfileRemembersWhereEachGrantWasEarned(self):
        rules = [rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_DEPARTMENT)]
        profile = buildAccessProfile(
            "u1", [posting("u1", ENG, SUPERVISOR), posting("u1", QA, SUPERVISOR)], rules
        )
        self.assertEqual(set(profile.departmentsFor(WO_VIEW)), {ENG, QA})

    def testTheMatrixIsAdditiveWithNoWayToDeny(self):
        """An empty cell grants nothing; subtraction lives in identity."""
        rules = [rule(TECHNICIAN, "workOrder", ACTION_VIEW, SCOPE_OWN)]
        profile = buildAccessProfile("u1", [posting("u1", ENG, TECHNICIAN)], rules)
        self.assertTrue(profile.can(WO_VIEW))
        self.assertFalse(profile.can(WO_APPROVE))


class ScopeFilterTests(SimpleTestCase):
    def profileFor(self, scope, *, action=ACTION_VIEW, position=TECHNICIAN):
        rules = [rule(position, "workOrder", action, scope)]
        return buildAccessProfile("u1", [posting("u1", ENG, position)], rules)

    def testNoGrantFailsClosed(self):
        """The bug that leaks data is a missing grant falling through to
        "show everything"."""
        profile = buildAccessProfile("u1", [], [])
        result = scopeFilterFor(profile, WO_VIEW)
        self.assertTrue(result.denied)
        self.assertFalse(result.unrestricted)

    def testOwnScopeFiltersToTheUser(self):
        result = scopeFilterFor(self.profileFor(SCOPE_OWN), WO_VIEW)
        self.assertEqual(result.userIds, ("u1",))
        self.assertFalse(result.unrestricted)

    def testTeamScopeIncludesTheUserThemselves(self):
        """A supervisor with an empty roster must still see their own work."""
        result = scopeFilterFor(
            self.profileFor(SCOPE_TEAM, position=SUPERVISOR), WO_VIEW, teamUserIds=()
        )
        self.assertEqual(result.userIds, ("u1",))

    def testTeamScopeAddsTheRoster(self):
        result = scopeFilterFor(
            self.profileFor(SCOPE_TEAM, position=SUPERVISOR),
            WO_VIEW,
            teamUserIds=("u2", "u3"),
        )
        self.assertEqual(set(result.userIds), {"u1", "u2", "u3"})

    def testTeamScopeDoesNotDuplicateTheUser(self):
        result = scopeFilterFor(
            self.profileFor(SCOPE_TEAM, position=SUPERVISOR),
            WO_VIEW,
            teamUserIds=("u1", "u2"),
        )
        self.assertEqual(result.userIds, ("u1", "u2"))

    def testDepartmentScopeFiltersToTheUnitsTheGrantWasEarnedIn(self):
        result = scopeFilterFor(self.profileFor(SCOPE_DEPARTMENT, position=SUPERVISOR), WO_VIEW)
        self.assertEqual(result.departmentIds, (ENG,))

    def testAllScopeDoesNotNarrowAnything(self):
        result = scopeFilterFor(self.profileFor(SCOPE_ALL, position=MANAGER), WO_VIEW)
        self.assertTrue(result.unrestricted)
        self.assertEqual(result.userIds, ())
        self.assertEqual(result.departmentIds, ())


class RecordLevelTests(SimpleTestCase):
    """The list filter and the per-record check must agree."""

    def technician(self):
        return buildAccessProfile(
            "u1",
            [posting("u1", ENG, TECHNICIAN)],
            [rule(TECHNICIAN, "workOrder", ACTION_EDIT, SCOPE_OWN)],
        )

    def testTechnicianMayEditTheirOwnWorkOrder(self):
        """The brief's «Edit فقط WO خودش», exactly."""
        self.assertTrue(canActOnRecord(self.technician(), WO_EDIT, ownerUserId="u1"))

    def testTechnicianMayNotEditSomebodyElses(self):
        self.assertFalse(canActOnRecord(self.technician(), WO_EDIT, ownerUserId="u2"))

    def testTechnicianMayNotApproveAtAll(self):
        self.assertFalse(canActOnRecord(self.technician(), WO_APPROVE, ownerUserId="u1"))

    def testDepartmentScopeAcceptsAnyRecordInTheUnit(self):
        profile = buildAccessProfile(
            "u1",
            [posting("u1", ENG, SUPERVISOR)],
            [rule(SUPERVISOR, "workOrder", ACTION_EDIT, SCOPE_DEPARTMENT)],
        )
        self.assertTrue(canActOnRecord(profile, WO_EDIT, ownerUserId="u9", departmentId=ENG))
        self.assertFalse(canActOnRecord(profile, WO_EDIT, ownerUserId="u9", departmentId=QA))

    def testAllScopeAcceptsEverything(self):
        profile = buildAccessProfile(
            "u1",
            [posting("u1", ENG, MANAGER)],
            [rule(MANAGER, "workOrder", ACTION_EDIT, SCOPE_ALL)],
        )
        self.assertTrue(canActOnRecord(profile, WO_EDIT, ownerUserId="u9", departmentId=QA))

    def testTeamScopeAcceptsATeammatesRecord(self):
        profile = buildAccessProfile(
            "u1",
            [posting("u1", ENG, SUPERVISOR)],
            [rule(SUPERVISOR, "workOrder", ACTION_EDIT, SCOPE_TEAM)],
        )
        self.assertTrue(canActOnRecord(profile, WO_EDIT, ownerUserId="u2", teamUserIds=("u2",)))
        self.assertFalse(canActOnRecord(profile, WO_EDIT, ownerUserId="u7", teamUserIds=("u2",)))


class MatrixViewTests(SimpleTestCase):
    def testTheViewFoldsInOrganisationWideDefaults(self):
        """A screen showing blank cells that nonetheless grant access will
        not be trusted, and an untrusted permission screen gets bypassed."""
        rules = [
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_DEPARTMENT),
            rule(SUPERVISOR, "workOrder", ACTION_CREATE, SCOPE_TEAM, department=ENG),
        ]
        view = matrixView(rules, departmentId=ENG)
        self.assertEqual(view[SUPERVISOR]["workOrder"][ACTION_VIEW], SCOPE_DEPARTMENT)
        self.assertEqual(view[SUPERVISOR]["workOrder"][ACTION_CREATE], SCOPE_TEAM)

    def testADepartmentOverrideReplacesTheDefaultInTheView(self):
        rules = [
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_DEPARTMENT),
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_OWN, department=ENG),
        ]
        self.assertEqual(
            matrixView(rules, departmentId=ENG)[SUPERVISOR]["workOrder"][ACTION_VIEW], SCOPE_OWN
        )

    def testAnotherDepartmentsOverrideIsNotShown(self):
        rules = [
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_DEPARTMENT),
            rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_OWN, department=QA),
        ]
        self.assertEqual(
            matrixView(rules, departmentId=ENG)[SUPERVISOR]["workOrder"][ACTION_VIEW],
            SCOPE_DEPARTMENT,
        )

    def testInactiveRulesAreNotShown(self):
        rules = [rule(SUPERVISOR, "workOrder", ACTION_VIEW, SCOPE_ALL, active=False)]
        self.assertEqual(matrixView(rules), {})


class SeedMatrixSanityTests(SimpleTestCase):
    """The shipped default matrix has to make organisational sense."""

    def testTheDefaultMatrixMatchesTheBriefForATechnician(self):
        from apps.organization.domain.valueObjects.orgStructure import DEFAULT_ACCESS_MATRIX

        technician = DEFAULT_ACCESS_MATRIX["TECHNICIAN"]
        self.assertEqual(technician["workOrder"][ACTION_EDIT], SCOPE_OWN)
        self.assertNotIn(ACTION_APPROVE, technician["workOrder"])
        self.assertNotIn("close", technician["workOrder"])

    def testManagersOutrankSupervisorsOnWorkOrders(self):
        from apps.organization.domain.valueObjects.orgStructure import (
            DEFAULT_ACCESS_MATRIX,
            SCOPE_RANK,
        )

        manager = DEFAULT_ACCESS_MATRIX["MGR"]["workOrder"][ACTION_VIEW]
        supervisor = DEFAULT_ACCESS_MATRIX["SUPERVISOR"]["workOrder"][ACTION_VIEW]
        self.assertGreater(SCOPE_RANK[manager], SCOPE_RANK[supervisor])

    def testOnlyManagersManageUnitMembersInTheDefault(self):
        from apps.organization.domain.valueObjects.orgStructure import DEFAULT_ACCESS_MATRIX

        self.assertIn("unitMembers", DEFAULT_ACCESS_MATRIX["MGR"])
        self.assertNotIn(ACTION_CREATE, DEFAULT_ACCESS_MATRIX["HEAD"].get("unitMembers", {}))
        self.assertNotIn("unitMembers", DEFAULT_ACCESS_MATRIX["TECHNICIAN"])

    def testEveryDefaultCellNamesARealCapabilityActionAndScope(self):
        from apps.organization.domain.valueObjects.orgStructure import (
            DEFAULT_ACCESS_MATRIX,
            SCOPES,
        )

        for positionCode, capabilities in DEFAULT_ACCESS_MATRIX.items():
            for capabilityKey, actions in capabilities.items():
                self.assertIn(capabilityKey, CAPABILITY_BY_KEY, f"{positionCode}/{capabilityKey}")
                for action, scope in actions.items():
                    self.assertTrue(
                        actionCodesFor(capabilityKey, action),
                        f"{positionCode}/{capabilityKey}/{action}",
                    )
                    self.assertIn(scope, SCOPES)
