"""The permit API over HTTP, with real authentication.

The service tests prove the rules hold when called directly. These prove
they are still there once the request has come through routing, permissions
and serialisation — including that a safety refusal arrives as a 422 the
client can tell apart from a validation error, and that the Persian reason
actually reaches the browser.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.identity.application.services.permissionCatalog import ACTIONS
from apps.safety.domain.valueObjects.permitState import PERMIT_TYPES
from apps.safety.infrastructure.models import PermitToWorkModel
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform


class PermitApiTestBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        self.now = timezone.now()

    def createPermit(self, **overrides):
        payload = {
            "permitType": "general",
            "title": "تعویض واشر خط آب",
            "riskLevel": "low",
            "validFrom": (self.now - timedelta(minutes=5)).isoformat(),
            "validTo": (self.now + timedelta(hours=6)).isoformat(),
        }
        payload.update(overrides)
        response = self.client.post(
            "/api/v1/safety/permits", payload, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def act(self, permitId, action, **body):
        return self.client.post(
            f"/api/v1/safety/permits/{permitId}/{action}", body, format="json", **self.auth
        )

    def confirmAllMandatory(self, permit):
        for item in permit["precautions"]:
            if item["isMandatory"]:
                response = self.client.post(
                    f"/api/v1/safety/permits/{permit['id']}/precautions/{item['id']}/confirm",
                    {},
                    format="json",
                    **self.auth,
                )
                self.assertEqual(response.status_code, 200, response.content)
        return self.detail(permit["id"])

    def permitFromAnotherRequester(self, **overrides):
        """A permit raised by somebody else, so the logged-in admin may approve it.

        The suite only has one real account, and the segregation-of-duties
        guard correctly fires before every other check — which would mask
        the rules underneath it. Seeding the requester directly is the only
        way to exercise what comes after.
        """
        import uuid as _uuid

        from apps.safety.application.services.permitService import Actor, createPermit

        payload = {
            "permitType": "general",
            "title": "کار تیم دیگر",
            "riskLevel": "low",
            "validFrom": self.now - timedelta(minutes=5),
            "validTo": self.now + timedelta(hours=6),
        }
        payload.update(overrides)
        permit = createPermit(
            self.tenantId,
            actor=Actor(id=_uuid.uuid4(), name="تکنسین دیگر"),
            now=self.now,
            **payload,
        )
        return self.detail(permit.id)

    def detail(self, permitId):
        response = self.client.get(f"/api/v1/safety/permits/{permitId}", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]


class PermitCrudApiTests(PermitApiTestBase):
    def testAuthenticationIsRequired(self):
        response = self.client.get("/api/v1/safety/permits")
        self.assertIn(response.status_code, (401, 403))

    def testCreateReturnsTheSeededChecklist(self):
        permit = self.createPermit(permitType="hotWork")
        self.assertTrue(permit["precautions"])
        self.assertTrue(any(x["isMandatory"] for x in permit["precautions"]))

    def testListReturnsPermitsAndFormOptions(self):
        self.createPermit()
        response = self.client.get("/api/v1/safety/permits", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()["data"]
        self.assertEqual(len(body["items"]), 1)
        self.assertEqual(len(body["options"]["types"]), len(PERMIT_TYPES))
        # The form must not have to hardcode which types need isolation.
        electrical = next(
            x for x in body["options"]["types"] if x["value"] == "electrical"
        )
        self.assertTrue(electrical["requiresIsolation"])

    def testListCanBeFilteredToLivePermits(self):
        self.createPermit()
        response = self.client.get("/api/v1/safety/permits?liveOnly=true", **self.auth)
        self.assertEqual(response.json()["data"]["items"], [])

    def testDetailCarriesTheAuditTrail(self):
        permit = self.createPermit()
        detail = self.detail(permit["id"])
        self.assertTrue(detail["events"])
        self.assertEqual(detail["events"][0]["action"], "created")

    def testValidityIsReturnedAsComputedFields(self):
        permit = self.createPermit()
        self.assertIn("isExpired", permit["validity"])
        self.assertFalse(permit["validity"]["isExpired"])

    def testAnUnknownPermitIs404(self):
        import uuid

        response = self.client.get(f"/api/v1/safety/permits/{uuid.uuid4()}", **self.auth)
        self.assertEqual(response.status_code, 404)

    def testAnUnknownActionIsRejected(self):
        permit = self.createPermit()
        response = self.act(permit["id"], "teleport")
        self.assertEqual(response.status_code, 400)


class SafetyRefusalApiTests(PermitApiTestBase):
    def testSelfApprovalIsRefusedWith422AndAReason(self):
        """The platform admin raising and signing their own permit — the
        exact shortcut a real plant takes under time pressure."""
        permit = self.createPermit()
        permit = self.confirmAllMandatory(permit)
        self.assertEqual(self.act(permit["id"], "submit").status_code, 200)

        response = self.act(permit["id"], "approve")
        self.assertEqual(response.status_code, 422, response.content)
        body = response.json()
        self.assertEqual(body["error"]["code"], "permit.approval.selfApproval")
        self.assertEqual(body["error"]["category"], "safetyRule")
        self.assertIn("تأیید", body["error"]["message"])

    def testASafetyRefusalIsDistinguishableFromAValidationError(self):
        """422 means the plant was not ready; 400 means the request was
        malformed. The client has to show different things."""
        response = self.client.post(
            "/api/v1/safety/permits", {"permitType": "nonsense"}, format="json", **self.auth
        )
        self.assertEqual(response.status_code, 400)

    def testAnIllegalTransitionIsRefused(self):
        permit = self.createPermit()
        response = self.act(permit["id"], "activate")
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"]["code"], "permit.transition.illegal")

    def testApprovalIsRefusedWhileTheChecklistIsIncomplete(self):
        permit = self.permitFromAnotherRequester()
        self.act(permit["id"], "submit")
        response = self.act(permit["id"], "approve")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "permit.issue.notReady")

    def testRejectionWithoutAReasonIsRefused(self):
        permit = self.createPermit()
        self.act(permit["id"], "submit")
        response = self.act(permit["id"], "reject", reason="")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "permit.reject.reasonRequired")

    def testTheChecklistLocksAfterTheWindowClosesOnIt(self):
        permit = self.createPermit()
        permit = self.confirmAllMandatory(permit)
        self.act(permit["id"], "submit")
        self.act(permit["id"], "reject", reason="شرایط مناسب نیست")
        item = permit["precautions"][0]
        response = self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/precautions/{item['id']}/confirm",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)


class IsolationApiTests(PermitApiTestBase):
    def addIsolation(self, permitId, code="ISO-1"):
        response = self.client.post(
            f"/api/v1/safety/permits/{permitId}/isolations",
            {
                "pointCode": code,
                "description": "کلید اصلی تابلو برق",
                "energyType": "electrical",
                "isolationMethod": "قفل و برچسب",
                "lockTag": "LK-001",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]

    def testAnElectricalPermitCannotBeApprovedWithoutIsolations(self):
        permit = self.permitFromAnotherRequester(
            permitType="electrical", riskLevel="medium", title="کار برقی"
        )
        permit = self.confirmAllMandatory(permit)
        self.act(permit["id"], "submit")
        response = self.act(permit["id"], "approve")
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("جداسازی", response.json()["error"]["message"])

    def testAFullyPreparedElectricalPermitIsApprovedOverHttp(self):
        """The happy path has to be reachable through the API too, or the
        plant quietly goes back to paper."""
        permit = self.permitFromAnotherRequester(
            permitType="electrical", riskLevel="medium", title="کار برقی آماده"
        )
        detail = self.addIsolation(permit["id"])
        point = detail["isolations"][0]
        for verb in ("apply", "verify"):
            response = self.client.post(
                f"/api/v1/safety/permits/{permit['id']}/isolations/{point['id']}/{verb}",
                {},
                format="json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 200, response.content)
        permit = self.confirmAllMandatory(permit)
        self.act(permit["id"], "submit")
        response = self.act(permit["id"], "approve")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["status"], "approved")

    def testApplyAndVerifyAreRecordedSeparately(self):
        permit = self.createPermit(permitType="electrical", riskLevel="medium")
        detail = self.addIsolation(permit["id"])
        point = detail["isolations"][0]
        self.assertFalse(point["isApplied"])

        response = self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/isolations/{point['id']}/apply",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["data"]["isolations"][0]["isApplied"])
        self.assertFalse(response.json()["data"]["isolations"][0]["isVerified"])

        response = self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/isolations/{point['id']}/verify",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["data"]["isolations"][0]["isVerified"])

    def testHighRiskRefusesSelfVerificationOverHttp(self):
        """One user doing both halves of the two-person rule."""
        permit = self.createPermit(permitType="electrical", riskLevel="high")
        detail = self.addIsolation(permit["id"])
        point = detail["isolations"][0]
        self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/isolations/{point['id']}/apply",
            {},
            format="json",
            **self.auth,
        )
        response = self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/isolations/{point['id']}/verify",
            {},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            response.json()["error"]["code"], "permit.isolation.selfVerification"
        )

    def testTheRegisterLocksOnceThePermitIsIssued(self):
        permit = self.createPermit(permitType="general")
        permit = self.confirmAllMandatory(permit)
        self.act(permit["id"], "submit")
        self.act(permit["id"], "cancel", reason="لغو شد")
        response = self.client.post(
            f"/api/v1/safety/permits/{permit['id']}/isolations",
            {"pointCode": "ISO-9", "description": "x", "energyType": "electrical"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def testReadinessTellsTheUserExactlyWhatIsOutstanding(self):
        permit = self.createPermit(permitType="electrical", riskLevel="medium")
        detail = self.detail(permit["id"])
        self.assertFalse(detail["readiness"]["isReadyToIssue"])
        self.assertTrue(detail["readiness"]["blockers"])


class ExpiryScanApiTests(PermitApiTestBase):
    def testTheScanEndpointIsReadOnly(self):
        """A page refresh must never expire a permit."""
        permit = self.createPermit(validTo=(self.now + timedelta(minutes=30)).isoformat())
        response = self.client.get("/api/v1/safety/permits/expiry-scan", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()["data"]["applied"])
        self.assertEqual(
            PermitToWorkModel.objects.get(id=permit["id"]).status, "draft"
        )

    def expiredApprovedPermit(self):
        """An authorised permit whose window has already closed."""
        import uuid as _uuid

        from apps.safety.application.services.permitService import (
            Actor,
            approvePermit,
            confirmPrecaution,
            createPermit,
            submitPermit,
        )
        from apps.safety.infrastructure.permitRepository import precautionRows

        requester = Actor(id=_uuid.uuid4(), name="تکنسین")
        supervisor = Actor(id=_uuid.uuid4(), name="سرپرست")
        past = self.now - timedelta(hours=10)
        permit = createPermit(
            self.tenantId,
            permitType="general",
            title="کار گذشته",
            actor=requester,
            validFrom=past,
            validTo=past + timedelta(hours=4),
            now=past,
        )
        for row in precautionRows(self.tenantId, permit.id):
            if row.isMandatory:
                confirmPrecaution(self.tenantId, permit.id, row.id, actor=requester, now=past)
        submitPermit(self.tenantId, permit.id, actor=requester, now=past)
        approvePermit(self.tenantId, permit.id, actor=supervisor, now=past)
        return permit

    def testTheCommandDefaultsToADryRun(self):
        """A cron line must not start expiring permits by accident."""
        permit = self.expiredApprovedPermit()
        out = StringIO()
        call_command("scanPermitExpiry", stdout=out)
        output = out.getvalue()
        self.assertIn(permit.number, output)
        self.assertIn("پیش‌نمایش", output)
        self.assertEqual(PermitToWorkModel.objects.get(id=permit.id).status, "approved")

    def testTheCommandAppliesWhenAsked(self):
        permit = self.expiredApprovedPermit()
        out = StringIO()
        call_command("scanPermitExpiry", "--apply", stdout=out)
        self.assertNotIn("پیش‌نمایش", out.getvalue())
        self.assertEqual(PermitToWorkModel.objects.get(id=permit.id).status, "expired")

    def testTheCommandNeverAutoExpiresWorkInProgress(self):
        """The loudest line in the output, and the one change it refuses."""
        from apps.safety.application.services.permitService import Actor, activatePermit

        permit = self.expiredApprovedPermit()
        activatePermit(
            self.tenantId,
            permit.id,
            actor=Actor(id=None, name="تکنسین"),
            now=permit.validFrom,
        )
        out = StringIO()
        call_command("scanPermitExpiry", "--apply", stdout=out)
        self.assertIn("هشدار", out.getvalue())
        self.assertEqual(PermitToWorkModel.objects.get(id=permit.id).status, "active")


class PermissionCatalogTests(TestCase):
    def testTheFivePermitActionsAreRegistered(self):
        keys = {key for key, _ in ACTIONS}
        for action in (
            "safety.permit.view",
            "safety.permit.request",
            "safety.permit.approve",
            "safety.permit.isolate",
            "safety.permit.close",
        ):
            self.assertIn(action, keys)

    def testATechnicianCannotApprove(self):
        """If the technician preset carried approve, the segregation rule
        would be the only thing standing between a crew and their own
        authorisation — and it only catches the *same* person."""
        from apps.identity.application.services.permissionCatalog import (
            MAINTENANCE_TECHNICIAN_ROLE,
            ROLE_PRESETS,
        )

        technician = ROLE_PRESETS[MAINTENANCE_TECHNICIAN_ROLE]
        self.assertIn("safety.permit.request", technician)
        self.assertIn("safety.permit.isolate", technician)
        self.assertNotIn("safety.permit.approve", technician)
        self.assertNotIn("safety.permit.close", technician)

    def testAManagerCanApproveAndClose(self):
        from apps.identity.application.services.permissionCatalog import (
            MAINTENANCE_MANAGER_ROLE,
            ROLE_PRESETS,
        )

        manager = ROLE_PRESETS[MAINTENANCE_MANAGER_ROLE]
        self.assertIn("safety.permit.approve", manager)
        self.assertIn("safety.permit.close", manager)
