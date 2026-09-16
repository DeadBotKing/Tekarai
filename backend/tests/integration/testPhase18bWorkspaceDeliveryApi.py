"""Phase 18b — Projects & Tasks public REST contract.

Step 1 of the execution plan opens the two workspace-delivery contexts and
wires the demo UI to them. These tests pin the public boundary so the
frontend has a stable, verified contract to consume.
"""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from tests.support.phase6Helpers import loginViaApi, seedPlatform


class WorkspaceDeliveryApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

    def createProject(self, code: str = "NOVA-99", name: str = "Nova Plant Modernization") -> dict:
        response = self.client.post(
            "/api/v1/projects/",
            {
                "code": code,
                "name": name,
                "description": "Modernize production planning.",
                "ownerName": "Maya Chen",
                "dueDate": "2026-12-31",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def createTask(self, title: str = "Validate data contract", projectId: str = "") -> dict:
        response = self.client.post(
            "/api/v1/tasks/",
            {"title": title, "priority": "high", "projectId": projectId},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]


class ProjectApiTests(WorkspaceDeliveryApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/v1/projects/").status_code, 401)
        self.assertEqual(anonymous.post("/api/v1/projects/", {}, format="json").status_code, 401)

    def testCreateListDetailUpdateAndStatusFlow(self) -> None:
        created = self.createProject()
        self.assertEqual(created["status"], "active")
        self.assertEqual(created["code"], "NOVA-99")

        listed = self.client.get("/api/v1/projects/", **self.auth)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertTrue(listed.json()["success"])
        self.assertGreaterEqual(listed.json()["meta"]["totalCount"], 1)
        self.assertIn(created["id"], [item["id"] for item in listed.json()["data"]])

        detail = self.client.get(f"/api/v1/projects/{created['id']}", **self.auth)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["data"]["name"], "Nova Plant Modernization")

        updated = self.client.patch(
            f"/api/v1/projects/{created['id']}",
            {"name": "Nova Plant Modernization v2", "progress": 40, "health": 90},
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["name"], "Nova Plant Modernization v2")
        self.assertEqual(updated.json()["data"]["progress"], 40)

        transitioned = self.client.post(
            f"/api/v1/projects/{created['id']}/status",
            {"target": "completed"},
            format="json",
            **self.auth,
        )
        self.assertEqual(transitioned.status_code, 200, transitioned.content)
        self.assertEqual(transitioned.json()["data"]["status"], "completed")

    def testDuplicateBusinessCodeIsRejected(self) -> None:
        self.createProject(code="DUP-01")
        duplicate = self.client.post(
            "/api/v1/projects/",
            {"code": "DUP-01", "name": "Duplicate"},
            format="json",
            **self.auth,
        )
        self.assertEqual(duplicate.status_code, 409, duplicate.content)
        self.assertFalse(duplicate.json()["success"])

    def testInvalidStatusTransitionIsRejected(self) -> None:
        created = self.createProject()
        # active → archived is allowed; archived → active is not.
        archived = self.client.post(
            f"/api/v1/projects/{created['id']}/status",
            {"target": "archived"},
            format="json",
            **self.auth,
        )
        self.assertEqual(archived.status_code, 200, archived.content)
        resurrect = self.client.post(
            f"/api/v1/projects/{created['id']}/status",
            {"target": "active"},
            format="json",
            **self.auth,
        )
        self.assertEqual(resurrect.status_code, 409, resurrect.content)


class TaskApiTests(WorkspaceDeliveryApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/v1/tasks/").status_code, 401)
        self.assertEqual(anonymous.post("/api/v1/tasks/", {}, format="json").status_code, 401)

    def testCreateListUpdateAndStatusFlow(self) -> None:
        project = self.createProject()
        created = self.createTask(projectId=project["id"])
        self.assertEqual(created["status"], "todo")
        self.assertEqual(created["priority"], "high")
        self.assertEqual(created["projectId"], project["id"])

        listed = self.client.get("/api/v1/tasks/", **self.auth)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertGreaterEqual(listed.json()["meta"]["totalCount"], 1)

        updated = self.client.patch(
            f"/api/v1/tasks/{created['id']}",
            {"title": "Validate data contract v2", "priority": "critical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.json()["data"]["title"], "Validate data contract v2")
        self.assertEqual(updated.json()["data"]["priority"], "critical")

        moved = self.client.post(
            f"/api/v1/tasks/{created['id']}/status",
            {"target": "done"},
            format="json",
            **self.auth,
        )
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(moved.json()["data"]["status"], "done")

    def testUnknownTaskIs404(self) -> None:
        missing = self.client.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000000",
            **self.auth,
        )
        self.assertEqual(missing.status_code, 404, missing.content)


class LoginContractTests(TestCase):
    def testLoginPayloadCarriesEffectivePermissions(self) -> None:
        cache.clear()
        seedPlatform()
        client = APIClient()
        from tests.support.phase6Helpers import loginPayload

        response = client.post("/api/v1/auth/login", loginPayload(), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        permissions = response.json()["data"].get("permissions")
        self.assertIsInstance(permissions, list)
        self.assertIn("project.view", permissions)
        self.assertIn("project.create", permissions)
        self.assertIn("task.view", permissions)
        self.assertIn("task.create", permissions)


class SeedWorkspaceCommandTests(TestCase):
    def testSeedIsIdempotentAndProvisionsAllAggregates(self) -> None:
        from django.core.management import call_command

        from apps.identity.infrastructure.models import UserModel
        from apps.projects.infrastructure.models import ProjectModel
        from apps.tasks.infrastructure.models import TaskModel
        from apps.tenancy.infrastructure.models import TenantModel

        call_command("seedWorkspace", verbosity=0)
        first = (
            TenantModel.objects.count(),
            UserModel.objects.count(),
            ProjectModel.objects.count(),
            TaskModel.objects.count(),
        )
        self.assertGreaterEqual(first[0], 2)  # platform + acme
        self.assertGreaterEqual(first[1], 3)  # platform-admin + acme-admin + acme-member
        self.assertGreaterEqual(first[2], 8)  # 4 projects per tenant
        self.assertGreaterEqual(first[3], 12)  # 6 tasks per tenant
        self.assertTrue(TenantModel.objects.filter(code="acme").exists())
        self.assertTrue(UserModel.objects.filter(username="acme-admin").exists())

        # Re-running must not create duplicates.
        call_command("seedWorkspace", verbosity=0)
        second = (
            TenantModel.objects.count(),
            UserModel.objects.count(),
            ProjectModel.objects.count(),
            TaskModel.objects.count(),
        )
        self.assertEqual(first, second)
