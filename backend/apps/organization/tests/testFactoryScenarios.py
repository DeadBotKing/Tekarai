"""The four factory scenarios, as executable tests.

These are written from the brief's own wording rather than from the code,
so they are allowed to fail. They cover two different claims that are easy
to confuse:

1. **Does the person hold the permission?** — resolved from the chart.
2. **Does the permission actually narrow what they can reach?** — scope,
   enforced against real work orders.

The second is the one that matters. A grant that says `department` but
returns every unit's records is worse than no grant, because it reads as
a control while behaving as a wildcard.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase

from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel
from apps.organization.application.services import orgService
from apps.organization.application.services.accessContract import (
    accessProfileFor,
    scopeFilterForUser,
    userCanActOnRecord,
)
from apps.organization.application.services.orgService import Actor
from apps.organization.infrastructure import orgRepository


class FactoryScenarioTestBase(TestCase):
    """One plant: three units, the seeded titles, and real work orders."""

    def setUp(self) -> None:
        cache.clear()
        self.tenantId = uuid.uuid4()
        self.actor = Actor(id=uuid.uuid4(), name="مدیر سیستم")
        orgService.seedDefaults(self.tenantId)
        self.departments = {x.code: x for x in orgRepository.listDepartments(self.tenantId)}
        self.positions = {x.code: x for x in orgRepository.listPositions(self.tenantId)}

        self.engineering = self.departments["ENG"]
        self.quality = self.departments["QA"]
        self.production = self.departments["PROD"]

        # علی — فنی و مهندسی / مدیر
        self.ali = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=self.ali,
            departmentId=self.engineering.id,
            positionId=self.positions["MGR"].id,
            userDisplayName="علی",
            actor=self.actor,
        )
        # رضا — فنی و مهندسی / تکنسین
        self.reza = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=self.reza,
            departmentId=self.engineering.id,
            positionId=self.positions["TECHNICIAN"].id,
            userDisplayName="رضا",
            actor=self.actor,
        )
        # مریم — QA / رئیس
        self.maryam = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=self.maryam,
            departmentId=self.quality.id,
            positionId=self.positions["HEAD"].id,
            userDisplayName="مریم",
            actor=self.actor,
        )

        self.device = DeviceModel.objects.create(tenantId=self.tenantId, code="DEV-1", name="پمپ ۱")

    def workOrder(self, *, department, owner=None, title="کار") -> WorkOrderModel:
        return WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device.id,
            title=title,
            orgDepartmentId=department.id,
            requestedByUserId=owner,
        )


class ScenarioOneUnitManagerTests(FactoryScenarioTestBase):
    """علی — فنی و مهندسی / مدیر: all eight verbs on his unit's work."""

    def testManagerHoldsAllEightWorkOrderVerbs(self) -> None:
        profile = accessProfileFor(self.tenantId, self.ali)
        held = {
            verb: profile.scopeFor(code)
            for verb, code in (
                ("view", "maintenance.workorder.list"),
                ("create", "maintenance.workorder.create"),
                ("edit", "maintenance.workorder.update"),
                ("delete", "maintenance.workorder.delete"),
                ("approve", "maintenance.workorder.approve"),
                ("assign", "maintenance.workorder.assign"),
                ("close", "maintenance.workorder.close"),
                ("export", "maintenance.workorder.export"),
            )
        }
        missing = sorted(verb for verb, scope in held.items() if scope == "")
        self.assertEqual(missing, [], f"مدیر باید هر هشت عملیات را داشته باشد؛ ندارد: {missing}")

    def testManagerSeesEveryWorkOrderOfHisOwnUnit(self) -> None:
        mine = self.workOrder(department=self.engineering, owner=self.reza, title="مال واحد من")
        scopeFilter = scopeFilterForUser(self.tenantId, self.ali, "maintenance.workorder.list")
        self.assertFalse(scopeFilter.denied)
        self.assertIn(str(self.engineering.id), scopeFilter.departmentIds)
        self.assertTrue(
            userCanActOnRecord(
                self.tenantId,
                self.ali,
                "maintenance.workorder.list",
                ownerUserId=str(mine.requestedByUserId),
                departmentId=str(mine.orgDepartmentId),
            )
        )

    def testUnitManagerDoesNotAutomaticallySeeAnotherUnit(self) -> None:
        """A مدیر of one unit is still bounded by that unit.

        Scope `all` belongs to a مدیر کارخانه, which is a position the
        administrator creates deliberately — not something every manager
        row grants by default.
        """
        theirs = self.workOrder(department=self.production, title="مال تولید")
        self.assertFalse(
            userCanActOnRecord(
                self.tenantId,
                self.ali,
                "maintenance.workorder.list",
                ownerUserId="",
                departmentId=str(theirs.orgDepartmentId),
            ),
            "مدیر فنی نباید به‌صورت خودکار کارهای واحد تولید را ببیند.",
        )


class ScenarioTwoTechnicianTests(FactoryScenarioTestBase):
    """رضا — فنی و مهندسی / تکنسین: view و edit، هر دو فقط own."""

    def testTechnicianHoldsExactlyViewAndEditOnHisOwn(self) -> None:
        profile = accessProfileFor(self.tenantId, self.reza)
        self.assertEqual(profile.scopeFor("maintenance.workorder.list"), "own")
        self.assertEqual(profile.scopeFor("maintenance.workorder.update"), "own")

    def testTechnicianHoldsNothingBeyondViewAndEdit(self) -> None:
        profile = accessProfileFor(self.tenantId, self.reza)
        for code in (
            "maintenance.workorder.delete",
            "maintenance.workorder.approve",
            "maintenance.workorder.assign",
            "maintenance.workorder.close",
            "maintenance.workorder.export",
        ):
            self.assertEqual(profile.scopeFor(code), "", f"تکنسین نباید {code} را داشته باشد.")

    def testTechnicianListIsNarrowedToHisOwnRecords(self) -> None:
        scopeFilter = scopeFilterForUser(self.tenantId, self.reza, "maintenance.workorder.list")
        self.assertFalse(scopeFilter.unrestricted)
        self.assertEqual(scopeFilter.userIds, (str(self.reza),))

    def testTechnicianMayEditHisOwnWorkOrderButNotAColleaguesInTheSameUnit(self) -> None:
        own = self.workOrder(department=self.engineering, owner=self.reza)
        colleague = self.workOrder(department=self.engineering, owner=uuid.uuid4())
        self.assertTrue(
            userCanActOnRecord(
                self.tenantId,
                self.reza,
                "maintenance.workorder.update",
                ownerUserId=str(own.requestedByUserId),
                departmentId=str(own.orgDepartmentId),
            )
        )
        self.assertFalse(
            userCanActOnRecord(
                self.tenantId,
                self.reza,
                "maintenance.workorder.update",
                ownerUserId=str(colleague.requestedByUserId),
                departmentId=str(colleague.orgDepartmentId),
            ),
            "تکنسین نباید کار همکارش را — حتی در همان واحد — ویرایش کند.",
        )


class ScenarioThreeHeadOfAnotherUnitTests(FactoryScenarioTestBase):
    """مریم — QA / رئیس: «رئیس بودن» به‌تنهایی کار فنی را باز نمی‌کند."""

    def testHeadOfQualityIsNotGivenEngineeringWorkByVirtueOfRank(self) -> None:
        engineeringWork = self.workOrder(department=self.engineering, title="کار فنی")
        self.assertFalse(
            userCanActOnRecord(
                self.tenantId,
                self.maryam,
                "maintenance.workorder.list",
                ownerUserId="",
                departmentId=str(engineeringWork.orgDepartmentId),
            ),
            "رئیس QA نباید به‌خاطر رئیس‌بودن به کارهای فنی دسترسی پیدا کند.",
        )

    def testSeniorityAloneGrantsNothing(self) -> None:
        """سطح بالاتر، دسترسیِ سطح پایین‌تر را به ارث نمی‌برد."""
        self.assertGreater(self.positions["HEAD"].level, self.positions["TECHNICIAN"].level)
        maryamScope = accessProfileFor(self.tenantId, self.maryam).scopeFor(
            "maintenance.workorder.list"
        )
        # She holds the grant — but bounded to her own unit, not everywhere.
        self.assertEqual(maryamScope, "department")

    def testHeadOfQualityStillRunsHerOwnUnit(self) -> None:
        qualityWork = self.workOrder(department=self.quality, title="کار QA")
        self.assertTrue(
            userCanActOnRecord(
                self.tenantId,
                self.maryam,
                "maintenance.workorder.list",
                ownerUserId="",
                departmentId=str(qualityWork.orgDepartmentId),
            )
        )


class ScenarioFourDepartmentVersusPlantWideTests(FactoryScenarioTestBase):
    """The decisive one: department scope must really mean one department.

    مریم با `WorkOrder.View = department` باید کارهای QA را ببیند و نه کارهای
    فنی و تولید — و مدیر کارخانه با `Scope = all` باید همه را ببیند.
    """

    def setUp(self) -> None:
        super().setUp()
        self.engineeringWork = self.workOrder(department=self.engineering, title="WO فنی")
        self.qualityWork = self.workOrder(department=self.quality, title="WO کیفیت")
        self.productionWork = self.workOrder(department=self.production, title="WO تولید")

        # مدیر کارخانه — a position the administrator defines, with plant-wide scope.
        self.plantManagerPosition = orgService.createPosition(
            self.tenantId, name="مدیر کارخانه", code="PLANT_MGR", level=120, actor=self.actor
        )
        for action in ("view", "create", "edit", "approve", "assign", "close", "export"):
            orgService.setAccessCell(
                self.tenantId,
                positionId=self.plantManagerPosition.id,
                capability="workOrder",
                action=action,
                scope="all",
                actor=self.actor,
            )
        self.plantManager = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=self.plantManager,
            departmentId=self.engineering.id,
            positionId=self.plantManagerPosition.id,
            userDisplayName="مدیر کارخانه",
            actor=self.actor,
        )

    def visibleTitlesFor(self, userId) -> list[str]:
        """Apply the scope filter to the real work-order table."""
        scopeFilter = scopeFilterForUser(self.tenantId, userId, "maintenance.workorder.list")
        if scopeFilter.denied:
            return []
        queryset = WorkOrderModel.objects.filter(tenantId=self.tenantId)
        if not scopeFilter.unrestricted:
            if scopeFilter.scope == "department":
                queryset = queryset.filter(orgDepartmentId__in=scopeFilter.departmentIds)
            else:
                queryset = queryset.filter(requestedByUserId__in=scopeFilter.userIds)
        return sorted(queryset.values_list("title", flat=True))

    def testQualityHeadSeesOnlyQualityWork(self) -> None:
        self.assertEqual(self.visibleTitlesFor(self.maryam), ["WO کیفیت"])

    def testEngineeringManagerSeesOnlyEngineeringWork(self) -> None:
        self.assertEqual(self.visibleTitlesFor(self.ali), ["WO فنی"])

    def testPlantManagerSeesEveryUnit(self) -> None:
        self.assertEqual(
            self.visibleTitlesFor(self.plantManager),
            ["WO تولید", "WO فنی", "WO کیفیت"],
        )

    def testTechnicianSeesOnlyWhatHeRaised(self) -> None:
        his = self.workOrder(department=self.engineering, owner=self.reza, title="WO رضا")
        self.assertEqual(self.visibleTitlesFor(self.reza), [his.title])

    def testScopeFilterReportsTheDepartmentItResolvedTo(self) -> None:
        scopeFilter = scopeFilterForUser(self.tenantId, self.maryam, "maintenance.workorder.list")
        self.assertEqual(scopeFilter.scope, "department")
        self.assertEqual(scopeFilter.departmentIds, (str(self.quality.id),))
        self.assertNotIn(str(self.engineering.id), scopeFilter.departmentIds)

    def testPersonPostedInTwoUnitsSeesBoth(self) -> None:
        """چند انتساب = اجتماع واحدها، نه دسترسی کل کارخانه."""
        orgService.assignUser(
            self.tenantId,
            userId=self.maryam,
            departmentId=self.production.id,
            positionId=self.positions["HEAD"].id,
            isPrimary=False,
            actor=self.actor,
        )
        self.assertEqual(self.visibleTitlesFor(self.maryam), ["WO تولید", "WO کیفیت"])
