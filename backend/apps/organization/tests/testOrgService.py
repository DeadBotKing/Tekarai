"""Database tests for managing the chart.

The emphasis is on the refusals and on invalidation. A permission system is
judged by what it will not let you do and by how fast a revocation takes
effect, so those get more coverage here than the happy paths.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase

from apps.identity.infrastructure.services import authorizationCache
from apps.organization.application.services import orgService
from apps.organization.application.services.accessContract import (
    accessProfileFor,
    grantsForUser,
    primaryDepartmentIdFor,
    scopeFilterForUser,
    userCanActOnRecord,
)
from apps.organization.application.services.orgService import Actor, OrganizationRuleViolation
from apps.organization.infrastructure import orgRepository
from apps.organization.infrastructure.models import (
    OrganizationAccessRuleModel,
    OrganizationAuditModel,
    OrganizationDepartmentModel,
)
from apps.organization.infrastructure.orgRepository import OrganizationNotFound


class OrganizationServiceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.tenantId = uuid.uuid4()
        self.actor = Actor(id=uuid.uuid4(), name="مدیر سیستم")
        orgService.seedDefaults(self.tenantId)
        self.departments = {x.code: x for x in orgRepository.listDepartments(self.tenantId)}
        self.positions = {x.code: x for x in orgRepository.listPositions(self.tenantId)}

    # --- seeding -----------------------------------------------------------

    def testSeedCreatesTheFiveDefaultUnits(self) -> None:
        self.assertEqual(sorted(self.departments), ["ENG", "HSE", "PROD", "QA", "QC"])
        self.assertEqual(self.departments["ENG"].name, "فنی و مهندسی")

    def testSeedCreatesTheSixDefaultPositions(self) -> None:
        self.assertEqual(len(self.positions), 6)
        self.assertEqual(self.positions["MGR"].name, "مدیر")
        # Level orders the grid's columns; it confers nothing on its own.
        self.assertGreater(self.positions["MGR"].level, self.positions["TECHNICIAN"].level)

    def testSeedIsIdempotent(self) -> None:
        again = orgService.seedDefaults(self.tenantId)
        self.assertEqual(again["departments"], 0)
        self.assertEqual(again["positions"], 0)
        self.assertEqual(again["rules"], 0)

    def testSeedIsScopedToOneTenant(self) -> None:
        otherTenant = uuid.uuid4()
        self.assertEqual(orgRepository.listDepartments(otherTenant), [])

    # --- departments -------------------------------------------------------

    def testAdministratorCanOpenANewUnitWithoutCode(self) -> None:
        department = orgService.createDepartment(
            self.tenantId, name="انبار", code="WH", actor=self.actor
        )
        self.assertEqual(department.code, "WH")
        self.assertEqual(department.name, "انبار")
        self.assertFalse(department.isSystem)

    def testCodeIsDerivedAndNormalisedWhenOmitted(self) -> None:
        department = orgService.createDepartment(self.tenantId, name="it support", actor=self.actor)
        self.assertEqual(department.code, "ITSUPPORT")

    def testDuplicateUnitCodeIsRefused(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.createDepartment(self.tenantId, name="دیگر", code="ENG", actor=self.actor)
        self.assertEqual(caught.exception.code, "department.codeTaken")

    def testBlankUnitNameIsRefused(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.createDepartment(self.tenantId, name="   ", actor=self.actor)
        self.assertEqual(caught.exception.code, "department.nameRequired")

    def testUnitCannotBeItsOwnParent(self) -> None:
        engineering = self.departments["ENG"]
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.updateDepartment(
                self.tenantId, engineering.id, parentId=engineering.id, actor=self.actor
            )
        self.assertEqual(caught.exception.code, "department.selfParent")

    def testReparentingThatWouldCreateACycleIsRefused(self) -> None:
        parent = self.departments["ENG"]
        child = orgService.createDepartment(
            self.tenantId, name="برق", code="ELEC", parentId=parent.id, actor=self.actor
        )
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.updateDepartment(
                self.tenantId, parent.id, parentId=child.id, actor=self.actor
            )
        self.assertEqual(caught.exception.code, "department.cycle")

    def testSeededUnitsCannotBeDeleted(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.deleteDepartment(self.tenantId, self.departments["QC"].id, actor=self.actor)
        self.assertEqual(caught.exception.code, "department.systemProtected")

    def testUnitWithMembersCannotBeDeleted(self) -> None:
        department = orgService.createDepartment(
            self.tenantId, name="تدارکات", code="PROC", actor=self.actor
        )
        orgService.assignUser(
            self.tenantId,
            userId=uuid.uuid4(),
            departmentId=department.id,
            positionId=self.positions["SPECIALIST"].id,
            actor=self.actor,
        )
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.deleteDepartment(self.tenantId, department.id, actor=self.actor)
        self.assertEqual(caught.exception.code, "department.hasMembers")

    def testUnitWithChildrenCannotBeDeleted(self) -> None:
        parent = orgService.createDepartment(
            self.tenantId, name="پشتیبانی", code="SUP", actor=self.actor
        )
        orgService.createDepartment(
            self.tenantId, name="نقلیه", code="FLEET", parentId=parent.id, actor=self.actor
        )
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.deleteDepartment(self.tenantId, parent.id, actor=self.actor)
        self.assertEqual(caught.exception.code, "department.hasChildren")

    def testEmptyUnitCanBeDeleted(self) -> None:
        department = orgService.createDepartment(
            self.tenantId, name="موقت", code="TMP", actor=self.actor
        )
        orgService.deleteDepartment(self.tenantId, department.id, actor=self.actor)
        self.assertFalse(OrganizationDepartmentModel.objects.filter(id=department.id).exists())

    # --- positions ---------------------------------------------------------

    def testAdministratorCanDefineANewPosition(self) -> None:
        position = orgService.createPosition(
            self.tenantId, name="سرپرست برق", code="SUP_ELEC", level=60, actor=self.actor
        )
        self.assertEqual(position.code, "SUP_ELEC")
        self.assertEqual(position.level, 60)

    def testNewPositionStartsWithNoPermissions(self) -> None:
        """A title nobody has described yet must grant nothing.

        Inheriting from a similar level would be guessing about authority.
        """
        position = orgService.createPosition(
            self.tenantId, name="مدیر کارخانه", code="PLANT_MGR", level=120, actor=self.actor
        )
        rules = orgRepository.listRules(self.tenantId, positionId=position.id)
        self.assertEqual(rules, [])

    def testPositionInUseCannotBeDeleted(self) -> None:
        position = orgService.createPosition(
            self.tenantId, name="کارشناس مکانیک", code="SPEC_MECH", actor=self.actor
        )
        orgService.assignUser(
            self.tenantId,
            userId=uuid.uuid4(),
            departmentId=self.departments["ENG"].id,
            positionId=position.id,
            actor=self.actor,
        )
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.deletePosition(self.tenantId, position.id, actor=self.actor)
        self.assertEqual(caught.exception.code, "position.inUse")

    def testSeededPositionsCannotBeDeleted(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.deletePosition(self.tenantId, self.positions["MGR"].id, actor=self.actor)
        self.assertEqual(caught.exception.code, "position.systemProtected")

    # --- assignments -------------------------------------------------------

    def testAssigningAUserGrantsTheMatrixOfThatPosition(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        profile = accessProfileFor(self.tenantId, userId)
        self.assertEqual(profile.scopeFor("maintenance.workorder.list"), "own")
        self.assertEqual(profile.scopeFor("maintenance.workorder.close"), "")

    def testSamePositionInDifferentUnitIsADifferentPrincipal(self) -> None:
        """The brief's central claim, as a test.

        «علی، فنی و مهندسی، مدیر» and «رضا، فنی و مهندسی، تکنسین» differ,
        and so does the same title in another unit once that unit overrides
        a cell.
        """
        ali, reza = uuid.uuid4(), uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=ali,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["MGR"].id,
            actor=self.actor,
        )
        orgService.assignUser(
            self.tenantId,
            userId=reza,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        aliProfile = accessProfileFor(self.tenantId, ali)
        rezaProfile = accessProfileFor(self.tenantId, reza)
        self.assertEqual(aliProfile.scopeFor("maintenance.workorder.delete"), "department")
        self.assertEqual(rezaProfile.scopeFor("maintenance.workorder.delete"), "")

    def testDuplicatePostingIsRefused(self) -> None:
        userId = uuid.uuid4()
        payload = {
            "userId": userId,
            "departmentId": self.departments["QC"].id,
            "positionId": self.positions["SPECIALIST"].id,
            "actor": self.actor,
        }
        orgService.assignUser(self.tenantId, **payload)
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.assignUser(self.tenantId, **payload)
        self.assertEqual(caught.exception.code, "assignment.duplicate")

    def testPostingIntoADeactivatedUnitIsRefused(self) -> None:
        orgService.updateDepartment(
            self.tenantId, self.departments["QA"].id, status="inactive", actor=self.actor
        )
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.assignUser(
                self.tenantId,
                userId=uuid.uuid4(),
                departmentId=self.departments["QA"].id,
                positionId=self.positions["MGR"].id,
                actor=self.actor,
            )
        self.assertEqual(caught.exception.code, "assignment.departmentInactive")

    def testUserCannotReportToThemselves(self) -> None:
        userId = uuid.uuid4()
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.assignUser(
                self.tenantId,
                userId=userId,
                departmentId=self.departments["ENG"].id,
                positionId=self.positions["SUPERVISOR"].id,
                reportsToUserId=userId,
                actor=self.actor,
            )
        self.assertEqual(caught.exception.code, "assignment.selfReporting")

    def testOnlyOnePostingStaysPrimary(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            isPrimary=True,
            actor=self.actor,
        )
        second = orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["PROD"].id,
            positionId=self.positions["SUPERVISOR"].id,
            isPrimary=True,
            actor=self.actor,
        )
        self.assertEqual(primaryDepartmentIdFor(self.tenantId, userId), str(second.departmentId))

    def testTwoPostingsUnionTheirPermissions(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["PROD"].id,
            positionId=self.positions["HEAD"].id,
            isPrimary=False,
            actor=self.actor,
        )
        profile = accessProfileFor(self.tenantId, userId)
        # The wider of the two postings wins, not the first one found.
        self.assertEqual(profile.scopeFor("maintenance.workorder.list"), "department")

    def testRemovingAPostingRemovesTheAccess(self) -> None:
        userId = uuid.uuid4()
        assignment = orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            actor=self.actor,
        )
        self.assertTrue(grantsForUser(self.tenantId, userId))
        orgService.removeAssignment(self.tenantId, assignment.id, actor=self.actor)
        self.assertEqual(grantsForUser(self.tenantId, userId), [])

    def testDeactivatingAUnitRemovesAccessForItsMembers(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["HSE"].id,
            positionId=self.positions["HEAD"].id,
            actor=self.actor,
        )
        self.assertTrue(grantsForUser(self.tenantId, userId))
        orgService.updateDepartment(
            self.tenantId, self.departments["HSE"].id, status="inactive", actor=self.actor
        )
        self.assertEqual(grantsForUser(self.tenantId, userId), [])

    # --- the matrix --------------------------------------------------------

    def testGrantingACellTakesEffectImmediately(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        self.assertEqual(
            accessProfileFor(self.tenantId, userId).scopeFor("maintenance.workorder.create"), ""
        )
        orgService.setAccessCell(
            self.tenantId,
            positionId=self.positions["TECHNICIAN"].id,
            capability="workOrder",
            action="create",
            scope="own",
            actor=self.actor,
        )
        self.assertEqual(
            accessProfileFor(self.tenantId, userId).scopeFor("maintenance.workorder.create"),
            "own",
        )

    def testDepartmentOverrideBeatsTheOrganisationWideDefault(self) -> None:
        """A unit may be stricter than the default, not only more generous."""
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["QC"].id,
            positionId=self.positions["SUPERVISOR"].id,
            actor=self.actor,
        )
        self.assertEqual(
            accessProfileFor(self.tenantId, userId).scopeFor("maintenance.workorder.list"),
            "team",
        )
        orgService.setAccessCell(
            self.tenantId,
            positionId=self.positions["SUPERVISOR"].id,
            departmentId=self.departments["QC"].id,
            capability="workOrder",
            action="view",
            scope="own",
            actor=self.actor,
        )
        self.assertEqual(
            accessProfileFor(self.tenantId, userId).scopeFor("maintenance.workorder.list"),
            "own",
        )

    def testRevokingACellRemovesIt(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            actor=self.actor,
        )
        orgService.clearAccessCell(
            self.tenantId,
            positionId=self.positions["HEAD"].id,
            capability="workOrder",
            action="approve",
            actor=self.actor,
        )
        self.assertEqual(
            accessProfileFor(self.tenantId, userId).scopeFor("maintenance.workorder.approve"), ""
        )

    def testCellOutsideTheCatalogueIsRefused(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.setAccessCell(
                self.tenantId,
                positionId=self.positions["MGR"].id,
                capability="workOrder",
                action="transmogrify",
                actor=self.actor,
            )
        self.assertEqual(caught.exception.code, "rule.unknownAction")

    def testUnknownCapabilityIsRefused(self) -> None:
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.setAccessCell(
                self.tenantId,
                positionId=self.positions["MGR"].id,
                capability="teleportation",
                action="view",
                actor=self.actor,
            )
        self.assertEqual(caught.exception.code, "rule.unknownCapability")

    def testVerbNotSupportedByACapabilityIsRefused(self) -> None:
        """A tick that no code would ever check must not be storable."""
        with self.assertRaises(OrganizationRuleViolation) as caught:
            orgService.setAccessCell(
                self.tenantId,
                positionId=self.positions["MGR"].id,
                capability="report",
                action="close",
                actor=self.actor,
            )
        self.assertEqual(caught.exception.code, "rule.unsupportedCell")

    def testUnscopedCapabilityIsForcedToPlantWide(self) -> None:
        row = orgService.setAccessCell(
            self.tenantId,
            positionId=self.positions["SPECIALIST"].id,
            capability="inventory",
            action="view",
            scope="own",
            actor=self.actor,
        )
        self.assertEqual(row.scope, "all")

    def testMatrixViewFoldsDefaultsIntoTheUnitGrid(self) -> None:
        matrix = orgService.accessMatrixFor(self.tenantId, self.departments["ENG"].id)
        self.assertEqual(matrix[str(self.positions["MGR"].id)]["workOrder"]["delete"], "department")

    # --- scope ---------------------------------------------------------------

    def testTechnicianListIsNarrowedToTheirOwnRecords(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        scopeFilter = scopeFilterForUser(self.tenantId, userId, "maintenance.workorder.list")
        self.assertFalse(scopeFilter.denied)
        self.assertFalse(scopeFilter.unrestricted)
        self.assertEqual(scopeFilter.userIds, (str(userId),))

    def testTechnicianMayEditTheirOwnWorkOrderOnly(self) -> None:
        """The brief's worked example: «تکنسین … Edit فقط WO خودش»."""
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["TECHNICIAN"].id,
            actor=self.actor,
        )
        self.assertTrue(
            userCanActOnRecord(
                self.tenantId,
                userId,
                "maintenance.workorder.update",
                ownerUserId=str(userId),
                departmentId=str(self.departments["ENG"].id),
            )
        )
        self.assertFalse(
            userCanActOnRecord(
                self.tenantId,
                userId,
                "maintenance.workorder.update",
                ownerUserId=str(uuid.uuid4()),
                departmentId=str(self.departments["ENG"].id),
            )
        )

    def testUserWithNoPostingIsDeniedRatherThanUnfiltered(self) -> None:
        """Fail closed: a missing grant must never mean "show everything"."""
        scopeFilter = scopeFilterForUser(self.tenantId, uuid.uuid4(), "maintenance.workorder.list")
        self.assertTrue(scopeFilter.denied)
        self.assertFalse(scopeFilter.unrestricted)

    def testFactoryManagerSeesEveryUnit(self) -> None:
        userId = uuid.uuid4()
        position = orgService.createPosition(
            self.tenantId, name="مدیر کارخانه", code="PLANT_MGR", level=120, actor=self.actor
        )
        orgService.setAccessCell(
            self.tenantId,
            positionId=position.id,
            capability="workOrder",
            action="view",
            scope="all",
            actor=self.actor,
        )
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=position.id,
            actor=self.actor,
        )
        scopeFilter = scopeFilterForUser(self.tenantId, userId, "maintenance.workorder.list")
        self.assertTrue(scopeFilter.unrestricted)

    def testSupervisorTeamScopeCoversDirectReportsAndSelf(self) -> None:
        supervisorId, technicianId = uuid.uuid4(), uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=supervisorId,
            departmentId=self.departments["PROD"].id,
            positionId=self.positions["SUPERVISOR"].id,
            actor=self.actor,
        )
        orgService.setAccessCell(
            self.tenantId,
            positionId=self.positions["SUPERVISOR"].id,
            capability="workOrder",
            action="view",
            scope="team",
            actor=self.actor,
        )
        orgService.assignUser(
            self.tenantId,
            userId=technicianId,
            departmentId=self.departments["PROD"].id,
            positionId=self.positions["TECHNICIAN"].id,
            reportsToUserId=supervisorId,
            actor=self.actor,
        )
        scopeFilter = scopeFilterForUser(self.tenantId, supervisorId, "maintenance.workorder.list")
        self.assertIn(str(technicianId), scopeFilter.userIds)
        self.assertIn(str(supervisorId), scopeFilter.userIds)

    # --- invalidation and audit ---------------------------------------------

    def testPermissionChangeBumpsTheAuthorizationVersion(self) -> None:
        """A revoked permission must die now, not when a TTL expires."""
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            actor=self.actor,
        )
        before = authorizationCache.currentVersion(userId)
        orgService.clearAccessCell(
            self.tenantId,
            positionId=self.positions["HEAD"].id,
            capability="workOrder",
            action="approve",
            actor=self.actor,
        )
        self.assertGreater(authorizationCache.currentVersion(userId), before)

    def testEveryStructuralChangeIsAudited(self) -> None:
        orgService.createDepartment(self.tenantId, name="مالی", code="FIN", actor=self.actor)
        entry = OrganizationAuditModel.objects.filter(
            tenantId=self.tenantId, entity="department", action="created"
        ).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.actorName, "مدیر سیستم")

    def testMatrixEditRecordsWhoChangedIt(self) -> None:
        orgService.setAccessCell(
            self.tenantId,
            positionId=self.positions["OPERATOR"].id,
            capability="workOrder",
            action="create",
            scope="own",
            actor=self.actor,
        )
        row = OrganizationAccessRuleModel.objects.get(
            tenantId=self.tenantId,
            positionId=self.positions["OPERATOR"].id,
            capability="workOrder",
            action="create",
        )
        self.assertEqual(row.updatedByName, "مدیر سیستم")

    def testDeletingAUnitKeepsTheAuditTrail(self) -> None:
        department = orgService.createDepartment(
            self.tenantId, name="آزمایشگاه", code="LAB", actor=self.actor
        )
        orgService.deleteDepartment(self.tenantId, department.id, actor=self.actor)
        self.assertTrue(
            OrganizationAuditModel.objects.filter(
                tenantId=self.tenantId, entityId=department.id, action="deleted"
            ).exists()
        )

    # --- isolation -----------------------------------------------------------

    def testOneTenantCannotReadAnotherTenantsChart(self) -> None:
        otherTenant = uuid.uuid4()
        orgService.seedDefaults(otherTenant)
        theirEngineering = {x.code: x for x in orgRepository.listDepartments(otherTenant)}["ENG"]
        with self.assertRaises(OrganizationNotFound):
            orgRepository.getDepartment(self.tenantId, theirEngineering.id)

    def testPostingInOneTenantGrantsNothingInAnother(self) -> None:
        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["MGR"].id,
            actor=self.actor,
        )
        self.assertEqual(grantsForUser(uuid.uuid4(), userId), [])
