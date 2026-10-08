"""The scenarios over HTTP, against the real work-order endpoint.

The scenario tests next door prove the *primitive* resolves correctly.
These prove the primitive is actually wired into the endpoint a browser
calls — which is a different claim, and the one that was false before this
change: a correct scope that nothing applies is a diagram, not a control.

Everything here goes through `/api/v1/maintenance/work-orders` with a real
bearer token. Work orders are created directly in the database with their
attribution stamped, because the point is what the *list* and *detail*
endpoints hand back, not how a row was written.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel
from apps.organization.application.services import orgService
from apps.organization.application.services.orgService import Actor
from apps.organization.infrastructure import orgRepository
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

WORK_ORDERS = "/api/v1/maintenance/work-orders"


class ScenarioEnforcementTestBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.actor = Actor(id=None, name="تست")

        orgService.seedDefaults(self.tenantId)
        self.departments = {x.code: x for x in orgRepository.listDepartments(self.tenantId)}
        self.positions = {x.code: x for x in orgRepository.listPositions(self.tenantId)}
        self.engineering = self.departments["ENG"]
        self.quality = self.departments["QA"]
        self.production = self.departments["PROD"]

        self.device = DeviceModel.objects.create(tenantId=self.tenantId, code="DEV-1", name="پمپ ۱")
        # The signed-in account is the person each test posts into a unit.
        # Read from the organisation endpoint, which reports the actor id
        # the authorisation path actually uses.
        profile = self.client.get("/api/v1/organization/my-access", **self.auth)
        self.assertEqual(profile.status_code, 200, profile.content)
        self.me = uuid.UUID(str(profile.json()["data"]["userId"]))

    def post(self, *, department, owner=None, title="کار") -> WorkOrderModel:
        return WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device.id,
            title=title,
            orgDepartmentId=department.id,
            requestedByUserId=owner,
        )

    def assign(self, positionCode: str, department) -> None:
        orgService.assignUser(
            self.tenantId,
            userId=self.me,
            departmentId=department.id,
            positionId=self.positions[positionCode].id,
            actor=self.actor,
        )

    def visibleTitles(self) -> list[str]:
        response = self.client.get(WORK_ORDERS, **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return sorted(x["title"] for x in response.json()["data"])


class PlantWithThreeUnitsTests(ScenarioEnforcementTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.post(department=self.engineering, title="WO فنی")
        self.post(department=self.quality, title="WO کیفیت")
        self.post(department=self.production, title="WO تولید")

    def testQualityHeadSeesOnlyQualityWorkOverHttp(self) -> None:
        """سناریوی ۴ — the decisive one."""
        self.assign("HEAD", self.quality)
        self.assertEqual(self.visibleTitles(), ["WO کیفیت"])

    def testEngineeringManagerSeesOnlyEngineeringWorkOverHttp(self) -> None:
        self.assign("MGR", self.engineering)
        self.assertEqual(self.visibleTitles(), ["WO فنی"])

    def testPlantManagerSeesEveryUnitOverHttp(self) -> None:
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
            userId=self.me,
            departmentId=self.engineering.id,
            positionId=position.id,
            actor=self.actor,
        )
        self.assertEqual(self.visibleTitles(), ["WO تولید", "WO فنی", "WO کیفیت"])

    def testTechnicianSeesOnlyWhatHeRaisedOverHttp(self) -> None:
        self.assign("TECHNICIAN", self.engineering)
        self.post(department=self.engineering, owner=self.me, title="WO خودم")
        self.assertEqual(self.visibleTitles(), ["WO خودم"])

    def testTechnicianAlsoSeesWorkAssignedToHim(self) -> None:
        """«کار خودش» must include the job he was told to do."""
        self.assign("TECHNICIAN", self.engineering)
        WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device.id,
            title="WO واگذارشده",
            orgDepartmentId=self.engineering.id,
            requestedByUserId=uuid.uuid4(),
            assignedToUserId=self.me,
        )
        self.assertEqual(self.visibleTitles(), ["WO واگذارشده"])

    def testQueryParameterCannotWidenTheScope(self) -> None:
        """A client must not be able to ask its way out of its unit."""
        self.assign("HEAD", self.quality)
        response = self.client.get(f"{WORK_ORDERS}?department=general&pageSize=100", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        titles = sorted(x["title"] for x in response.json()["data"])
        self.assertNotIn("WO فنی", titles)
        self.assertNotIn("WO تولید", titles)

    def testUserWithNoPostingSeesNothingRatherThanEverything(self) -> None:
        """Fail closed once the chart is in use."""
        self.assertEqual(self.visibleTitles(), [])

    def testTwoPostingsUnionTheUnitsOverHttp(self) -> None:
        self.assign("HEAD", self.quality)
        orgService.assignUser(
            self.tenantId,
            userId=self.me,
            departmentId=self.production.id,
            positionId=self.positions["HEAD"].id,
            isPrimary=False,
            actor=self.actor,
        )
        self.assertEqual(self.visibleTitles(), ["WO تولید", "WO کیفیت"])

    def testRevokingThePostingRemovesVisibilityImmediately(self) -> None:
        self.assign("HEAD", self.quality)
        self.assertEqual(self.visibleTitles(), ["WO کیفیت"])
        assignment = orgRepository.listAssignments(self.tenantId, userId=self.me)[0]
        orgService.removeAssignment(self.tenantId, assignment.id, actor=self.actor)
        self.assertEqual(self.visibleTitles(), [])


class RecordLevelEnforcementTests(ScenarioEnforcementTestBase):
    def testOpeningAnotherUnitsWorkOrderIsRefused(self) -> None:
        self.assign("HEAD", self.quality)
        theirs = self.post(department=self.engineering, title="WO فنی")
        response = self.client.get(f"{WORK_ORDERS}/{theirs.id}", **self.auth)
        self.assertEqual(response.status_code, 403, response.content)

    def testOpeningOwnUnitsWorkOrderIsAllowed(self) -> None:
        self.assign("HEAD", self.quality)
        mine = self.post(department=self.quality, title="WO کیفیت")
        response = self.client.get(f"{WORK_ORDERS}/{mine.id}", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)

    def testTechnicianCannotOpenAColleaguesWorkOrder(self) -> None:
        self.assign("TECHNICIAN", self.engineering)
        colleague = self.post(department=self.engineering, owner=uuid.uuid4(), title="WO همکار")
        response = self.client.get(f"{WORK_ORDERS}/{colleague.id}", **self.auth)
        self.assertEqual(response.status_code, 403, response.content)

    def testTechnicianCanOpenHisOwnWorkOrder(self) -> None:
        self.assign("TECHNICIAN", self.engineering)
        mine = self.post(department=self.engineering, owner=self.me, title="WO خودم")
        response = self.client.get(f"{WORK_ORDERS}/{mine.id}", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)

    def testListAndDetailNeverDisagree(self) -> None:
        """Every row a user is shown must be one they can open."""
        self.assign("HEAD", self.quality)
        self.post(department=self.engineering, title="WO فنی")
        self.post(department=self.quality, title="WO کیفیت الف")
        self.post(department=self.quality, title="WO کیفیت ب")

        listed = self.client.get(WORK_ORDERS, **self.auth).json()["data"]
        self.assertTrue(listed)
        for row in listed:
            detail = self.client.get(f"{WORK_ORDERS}/{row['id']}", **self.auth)
            self.assertEqual(detail.status_code, 200, row["title"])


class BackwardCompatibilityTests(ScenarioEnforcementTestBase):
    """A plant that has not adopted the chart must be unaffected.

    This is the test that keeps the feature safe to deploy: absence of
    configuration stays permissive, while absence of permission does not.
    """

    def setUp(self) -> None:
        super().setUp()
        for department in orgRepository.listDepartments(self.tenantId):
            WorkOrderModel.objects.filter(orgDepartmentId=department.id).delete()
        # Wipe the chart entirely — this tenant does not use it.
        orgRepository.OrganizationAssignmentModel.objects.filter(tenantId=self.tenantId).delete()
        orgRepository.OrganizationDepartmentModel.objects.filter(tenantId=self.tenantId).delete()

    def testWithoutAnyUnitsEveryWorkOrderIsStillVisible(self) -> None:
        self.post(department=self.engineering, title="WO قدیمی")
        self.assertEqual(self.visibleTitles(), ["WO قدیمی"])

    def testLegacyWorkOrdersWithoutAttributionStayVisibleToPlantWideUsers(self) -> None:
        WorkOrderModel.objects.create(
            tenantId=self.tenantId, deviceId=self.device.id, title="WO بدون واحد"
        )
        self.assertIn("WO بدون واحد", self.visibleTitles())
