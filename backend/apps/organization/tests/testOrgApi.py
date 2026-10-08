"""The organisation API over HTTP, with real authentication.

The service tests prove the rules hold when called directly. These prove
they survive routing, permissions and serialisation — that a refusal
arrives as a 422 with a Persian sentence the browser can show, that the
catalogue the UI draws its grid from is actually served, and that a user
can always see their own access.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.application.services.permissionCatalog import ACTIONS
from apps.organization.application.services import orgService
from apps.organization.infrastructure import orgRepository
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/organization"


class OrganizationApiTestBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.client.post(f"{BASE}/seed", {}, format="json", **self.auth)
        self.departments = {x.code: x for x in orgRepository.listDepartments(self.tenantId)}
        self.positions = {x.code: x for x in orgRepository.listPositions(self.tenantId)}

    def get(self, path):
        return self.client.get(f"{BASE}{path}", **self.auth)

    def post(self, path, body):
        return self.client.post(f"{BASE}{path}", body, format="json", **self.auth)

    def patch(self, path, body):
        return self.client.patch(f"{BASE}{path}", body, format="json", **self.auth)


class OrganizationCatalogueApiTests(OrganizationApiTestBase):
    def testEveryMatrixActionCodeExistsInThePermissionCatalogue(self) -> None:
        """The grid must only promise permissions the system enforces.

        This is the test that keeps the matrix honest: a readable front end
        onto real action codes, not a parallel permission system that looks
        authoritative and controls nothing.
        """
        from apps.organization.domain.valueObjects.orgStructure import (
            CAPABILITIES,
            actionCodesFor,
        )

        known = {code for code, _ in ACTIONS}
        missing = sorted(
            {
                code
                for capability in CAPABILITIES
                for action in capability["actions"]
                for code in actionCodesFor(capability["key"], action)
                if code not in known
            }
        )
        self.assertEqual(missing, [])

    def testSeedIsIdempotentOverHttp(self) -> None:
        response = self.post("/seed", {})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["departments"], 0)


class DepartmentApiTests(OrganizationApiTestBase):
    def testListReturnsTheSeededUnitsWithMemberCounts(self) -> None:
        response = self.get("/departments")
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["data"]["items"]
        self.assertEqual(len(items), 5)
        self.assertEqual({x["memberCount"] for x in items}, {0})
        self.assertIn("فنی و مهندسی", [x["name"] for x in items])

    def testAdministratorCanAddAUnit(self) -> None:
        response = self.post("/departments", {"name": "انبار", "code": "WH"})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["code"], "WH")

    def testDuplicateCodeReturnsAPersianRefusal(self) -> None:
        response = self.post("/departments", {"name": "تکراری", "code": "ENG"})
        self.assertEqual(response.status_code, 422, response.content)
        error = response.json()["error"]
        self.assertEqual(error["code"], "department.codeTaken")
        self.assertIn("ENG", error["message"])

    def testMissingNameIsAValidationErrorNotARuleRefusal(self) -> None:
        """400 and 422 must stay distinguishable to the client."""
        response = self.post("/departments", {"code": "XX"})
        self.assertEqual(response.status_code, 400, response.content)

    def testUnitCanBeRenamedAndDeactivated(self) -> None:
        department = self.departments["QA"]
        response = self.patch(
            f"/departments/{department.id}", {"name": "تضمین کیفیت", "status": "inactive"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["name"], "تضمین کیفیت")
        self.assertEqual(data["statusLabel"], "غیرفعال")

    def testDeletingASeededUnitIsRefused(self) -> None:
        response = self.client.delete(
            f"{BASE}/departments/{self.departments['ENG'].id}", **self.auth
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"]["code"], "department.systemProtected")

    def testUnknownUnitIsANotFound(self) -> None:
        response = self.get(f"/departments/{uuid.uuid4()}")
        self.assertEqual(response.status_code, 404, response.content)

    def testAnonymousRequestIsRejected(self) -> None:
        response = APIClient().get(f"{BASE}/departments")
        self.assertIn(response.status_code, (401, 403))


class PositionApiTests(OrganizationApiTestBase):
    def testListReturnsSixSeededPositionsHighestFirst(self) -> None:
        response = self.get("/positions")
        self.assertEqual(response.status_code, 200, response.content)
        items = response.json()["data"]["items"]
        self.assertEqual(len(items), 6)
        self.assertEqual(items[0]["name"], "مدیر")

    def testAdministratorCanAddAPosition(self) -> None:
        response = self.post("/positions", {"name": "سرپرست برق", "code": "SUP_ELEC", "level": 60})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["data"]["level"], 60)

    def testDuplicatePositionCodeIsRefused(self) -> None:
        response = self.post("/positions", {"name": "دیگر", "code": "MGR"})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"]["code"], "position.codeTaken")


class AssignmentApiTests(OrganizationApiTestBase):
    def testPostingAUserReturnsTheResolvedNames(self) -> None:
        response = self.post(
            "/assignments",
            {
                "userId": str(uuid.uuid4()),
                "departmentId": str(self.departments["ENG"].id),
                "positionId": str(self.positions["MGR"].id),
                "userDisplayName": "علی",
            },
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.json()["data"]
        self.assertEqual(data["departmentName"], "فنی و مهندسی")
        self.assertEqual(data["positionName"], "مدیر")

    def testDuplicatePostingIsRefusedOverHttp(self) -> None:
        payload = {
            "userId": str(uuid.uuid4()),
            "departmentId": str(self.departments["QC"].id),
            "positionId": str(self.positions["SPECIALIST"].id),
        }
        self.assertEqual(self.post("/assignments", payload).status_code, 201)
        response = self.post("/assignments", payload)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"]["code"], "assignment.duplicate")

    def testAssignmentsCanBeFilteredByUnit(self) -> None:
        self.post(
            "/assignments",
            {
                "userId": str(uuid.uuid4()),
                "departmentId": str(self.departments["PROD"].id),
                "positionId": str(self.positions["OPERATOR"].id),
            },
        )
        response = self.get(f"/assignments?departmentId={self.departments['PROD'].id}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["data"]["items"]), 1)
        empty = self.get(f"/assignments?departmentId={self.departments['QA'].id}")
        self.assertEqual(empty.json()["data"]["items"], [])


class AccessMatrixApiTests(OrganizationApiTestBase):
    def testMatrixShipsItsOwnColumnDefinition(self) -> None:
        """The UI must not hardcode which verbs a capability supports."""
        response = self.get("/access-matrix")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        capabilities = {x["key"]: x for x in data["capabilities"]}
        self.assertIn("workOrder", capabilities)
        workOrderActions = [x["value"] for x in capabilities["workOrder"]["actions"]]
        self.assertEqual(len(workOrderActions), 8)
        # A catalogue entry that is not scoped must say so, so the screen
        # does not offer a scope selector that would be ignored.
        self.assertFalse(capabilities["inventory"]["scoped"])
        self.assertTrue(capabilities["workOrder"]["scoped"])

    def testSeededGridMatchesTheBriefsWorkOrderExample(self) -> None:
        """مدیر all eight; رئیس all but Delete; تکنسین view only."""
        data = self.get("/access-matrix").json()["data"]
        matrix = data["matrix"]
        manager = matrix[str(self.positions["MGR"].id)]["workOrder"]
        head = matrix[str(self.positions["HEAD"].id)]["workOrder"]
        technician = matrix[str(self.positions["TECHNICIAN"].id)]["workOrder"]
        self.assertEqual(len(manager), 8)
        self.assertNotIn("delete", head)
        self.assertEqual(sorted(technician), ["edit", "view"])
        self.assertEqual(technician["view"], "own")
        self.assertEqual(technician["edit"], "own")

    def testTickingACellWritesItAndReturnsTheNewGrid(self) -> None:
        response = self.post(
            "/access-matrix",
            {
                "positionId": str(self.positions["TECHNICIAN"].id),
                "capability": "workOrder",
                "action": "create",
                "scope": "own",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        matrix = response.json()["data"]["matrix"]
        self.assertEqual(matrix[str(self.positions["TECHNICIAN"].id)]["workOrder"]["create"], "own")

    def testUntickingACellRevokesIt(self) -> None:
        response = self.post(
            "/access-matrix",
            {
                "positionId": str(self.positions["HEAD"].id),
                "capability": "workOrder",
                "action": "approve",
                "granted": False,
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        matrix = response.json()["data"]["matrix"]
        self.assertNotIn("approve", matrix[str(self.positions["HEAD"].id)]["workOrder"])

    def testUnsupportedCellIsRefusedWithAReason(self) -> None:
        response = self.post(
            "/access-matrix",
            {
                "positionId": str(self.positions["MGR"].id),
                "capability": "report",
                "action": "close",
            },
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"]["code"], "rule.unsupportedCell")

    def testPerUnitGridOverridesTheDefault(self) -> None:
        unitId = str(self.departments["QC"].id)
        self.post(
            "/access-matrix",
            {
                "positionId": str(self.positions["SUPERVISOR"].id),
                "departmentId": unitId,
                "capability": "workOrder",
                "action": "view",
                "scope": "own",
            },
        )
        scoped = self.get(f"/access-matrix?departmentId={unitId}").json()["data"]["matrix"]
        default = self.get("/access-matrix").json()["data"]["matrix"]
        supervisorId = str(self.positions["SUPERVISOR"].id)
        self.assertEqual(scoped[supervisorId]["workOrder"]["view"], "own")
        self.assertEqual(default[supervisorId]["workOrder"]["view"], "team")

    def testMatrixEditsAppearInTheAuditTrail(self) -> None:
        self.post(
            "/access-matrix",
            {
                "positionId": str(self.positions["OPERATOR"].id),
                "capability": "workOrder",
                "action": "create",
                "scope": "own",
            },
        )
        response = self.get("/audit")
        self.assertEqual(response.status_code, 200, response.content)
        summaries = [x["summary"] for x in response.json()["data"]["items"]]
        self.assertTrue(any("workOrder.create" in x for x in summaries))


class MyAccessApiTests(OrganizationApiTestBase):
    def testUserCanAlwaysSeeTheirOwnAccess(self) -> None:
        response = self.get("/my-access")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertIn("capabilities", data)
        self.assertIn("catalogue", data)

    def testUnpostedUserReportsNoCapabilities(self) -> None:
        """Honest emptiness beats a screen that implies access exists."""
        data = self.get("/my-access").json()["data"]
        self.assertEqual(data["assignments"], [])
        self.assertEqual(data["capabilities"], {})

    def testPostingTheSignedInUserShowsUpInTheirOwnAccess(self) -> None:
        userId = self.get("/my-access").json()["data"]["userId"]
        orgService.assignUser(
            self.tenantId,
            userId=uuid.UUID(userId),
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            actor=orgService.Actor(id=None, name="تست"),
        )
        data = self.get("/my-access").json()["data"]
        self.assertEqual(len(data["assignments"]), 1)
        self.assertEqual(data["assignments"][0]["departmentName"], "فنی و مهندسی")
        self.assertEqual(data["capabilities"]["workOrder"]["approve"], "department")


class OrganizationGrantBridgeTests(OrganizationApiTestBase):
    def testAPostingGrantsRealApiAccessToAnOtherwiseUnprivilegedUser(self) -> None:
        """End to end: the chart actually moves the enforcement needle.

        A posting is written, and the permission the matrix promises shows
        up in the grants identity assembles — which is the only reason any
        of this is more than a diagram.
        """
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
        )

        userId = uuid.uuid4()
        before = AccessRepositoryDjango.organizationGrants(userId, self.tenantId)
        self.assertEqual(before, [])

        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["ENG"].id,
            positionId=self.positions["HEAD"].id,
            actor=orgService.Actor(id=None, name="تست"),
        )
        after = AccessRepositoryDjango.organizationGrants(userId, self.tenantId)
        patterns = {x.actionPattern for x in after}
        self.assertIn("maintenance.workorder.approve", patterns)
        self.assertTrue(all(x.effect == "allow" for x in after))

    def testGrantsSurviveTheFullAuthorizationPath(self) -> None:
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
        )

        userId = uuid.uuid4()
        orgService.assignUser(
            self.tenantId,
            userId=userId,
            departmentId=self.departments["PROD"].id,
            positionId=self.positions["MGR"].id,
            actor=orgService.Actor(id=None, name="تست"),
        )
        grants = AccessRepositoryDjango().grantsOfUser(userId, self.tenantId)
        self.assertTrue(any(x.actionPattern == "maintenance.workorder.delete" for x in grants))
