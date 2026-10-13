"""Step-by-step referral of work requests up the unit's ladder (ارجاع به بالا).

The brief: «از هر فردی به فرد رده بالاتر درخواست کار ارجاع شود، در نهایت
تأیید نهایی با مدیر واحد باشد.» These tests walk that sentence literally:

* an operator's request climbs operator → technician → supervisor → رئیس →
  مدیر, one rung per call, each rung resolved from the org chart;
* the مدیر, already at the top of the unit, is told there is nobody above —
  in Persian, not with a stack trace;
* only the current holder can send it up;
* a member of another unit cannot reach into this one;
* the last rung still ends in the approve gate — escalation never becomes a
  way to close one's own work.

Everything runs over HTTP with real bearer tokens, one login per rung,
because the point is what a person in the factory can actually do.
"""

from __future__ import annotations

import uuid

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel
from apps.organization.application.services import orgService
from apps.organization.application.services.orgService import Actor
from apps.organization.infrastructure import orgRepository
from tests.support.phase6Helpers import PLATFORM_TENANT_CODE, seedPlatform

WORK_ORDERS = "/api/v1/maintenance/work-orders"
PASSWORD = "Escalate-Pass-2026!"

#: The unit's ladder, bottom-up, exactly as seeded.
LADDER = ("OPERATOR", "TECHNICIAN", "SUPERVISOR", "HEAD", "MGR")


class EscalationTestBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
            TenantRepositoryDjango,
        )

        tenant = TenantRepositoryDjango().getByCode(PLATFORM_TENANT_CODE)
        assert tenant is not None, "seedPlatform() must run first"
        self.tenantId = tenant.id
        orgService.seedDefaults(self.tenantId)
        self.departments = {x.code: x for x in orgRepository.listDepartments(self.tenantId)}
        self.positions = {x.code: x for x in orgRepository.listPositions(self.tenantId)}
        self.engineering = self.departments["ENG"]
        self.quality = self.departments["QA"]

        self.device = DeviceModel.objects.create(tenantId=self.tenantId, code="DEV-1", name="پمپ ۱")

        # A real account per rung, so each step of the ladder is a real
        # login with real grants — not an administrator impersonating them.
        from apps.identity.infrastructure.models import TenantMembershipModel, UserModel

        self.actor = Actor(id=None, name="تست")
        self.people: dict[str, uuid.UUID] = {}

        def plantAccount(username: str, displayName: str):
            # A real account: password, tenant membership, org posting —
            # each rung of the ladder logs in like a person, not a token.
            user = UserModel.objects.create(
                tenantId=self.tenantId,
                username=username,
                email=f"{username}@plant.local",
                passwordHash=make_password(PASSWORD),
                displayName=displayName,
            )
            TenantMembershipModel.objects.create(
                userId=user.id, tenantId=self.tenantId, status="active", isPrimary=True
            )
            return user

        displayNames = {
            "OPERATOR": "اکبری اپراتور",
            "TECHNICIAN": "رضا تکنسین",
            "SUPERVISOR": "کریمی سرپرست",
            "HEAD": "صادقی رئیس",
            "MGR": "علی مدیر",
        }
        for code in LADDER:
            user = plantAccount(f"esc-{code.lower()}", displayNames[code])
            self.people[code] = user.id
            orgService.assignUser(
                self.tenantId,
                userId=user.id,
                departmentId=self.engineering.id,
                positionId=self.positions[code].id,
                userDisplayName=displayNames[code],
                isPrimary=True,
                actor=self.actor,
            )
        # A رئیس of another unit, for the cross-unit refusal.
        qaHead = plantAccount("esc-qa-head", "مریم رئیس QA")
        self.qaHead = qaHead.id
        orgService.assignUser(
            self.tenantId,
            userId=qaHead.id,
            departmentId=self.quality.id,
            positionId=self.positions["HEAD"].id,
            userDisplayName="مریم رئیس QA",
            isPrimary=True,
            actor=self.actor,
        )

    def login(self, who: str) -> APIClient:
        """Sign in as one of the ladder's people. Accepts a position code
        (``OPERATOR``) or a raw username (``esc-qa-head``)."""
        username = who if who.startswith("esc-") else f"esc-{who.lower()}"
        client = APIClient()
        response = client.post(
            "/api/v1/auth/login",
            {"tenantCode": PLATFORM_TENANT_CODE, "identifier": username, "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.json()['data']['accessToken']}")
        return client

    def personAt(self, username: str) -> str:
        return str(self.people[username.upper()])

    def raiseRequest(self, *, ownerCode: str = "OPERATOR") -> WorkOrderModel:
        """A fresh request raised by one of the unit's own people."""
        return WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device.id,
            title="درخواست کار تست",
            orgDepartmentId=self.engineering.id,
            requestedByUserId=self.people[ownerCode],
        )


class TheLadderTests(EscalationTestBase):
    def testARequestClimbsTheWholeLadderOneRungPerCall(self) -> None:
        order = self.raiseRequest(ownerCode="OPERATOR")
        path = f"{WORK_ORDERS}/{order.id}/escalate"

        # Every rung: the current holder sends it up, the server names the
        # person one position above them in the same unit.
        for step, code in enumerate(("TECHNICIAN", "SUPERVISOR", "HEAD", "MGR"), start=1):
            sender = LADDER[step - 1]
            client = self.login(sender)
            response = client.post(path, {"note": f"پله {step}"}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            data = response.json()["data"]
            self.assertEqual(
                data["assignedToUserId"], self.personAt(code), f"رung {step}: باید به {code} می‌رفت"
            )
            self.assertEqual(data["status"], "assigned")

        # And the top of the unit is the end of the ladder.
        manager = self.login("MGR")
        response = manager.post(path, {"note": "بالاتر نداریم"}, format="json")
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("رده بالاتر", str(response.json()["errors"]))

    def testEachRungIsRecordedInTheTimeline(self) -> None:
        order = self.raiseRequest(ownerCode="OPERATOR")
        operator = self.login("OPERATOR")
        self.assertEqual(
            operator.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json").status_code,
            200,
        )
        history = operator.get(f"{WORK_ORDERS}/{order.id}/history").json()["data"]
        escalated = [entry for entry in history if entry["action"] == "escalated"]
        self.assertEqual(len(escalated), 1)
        self.assertIn("رضا تکنسین", escalated[0]["note"])
        self.assertEqual(escalated[0]["actorName"], "اکبری اپراتور")

    def testOnlyTheCurrentHolderCanSendItUp(self) -> None:
        # The operator holds the request; the technician, one rung up but
        # not the holder, must not be able to move it. The scope guard
        # refuses before the domain rule is even consulted — «own» means
        # the order is his, not merely one rung below him.
        order = self.raiseRequest(ownerCode="OPERATOR")
        technician = self.login("TECHNICIAN")
        response = technician.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json")
        self.assertEqual(response.status_code, 403, response.content)

    def testAnotherUnitsMemberCannotReachIn(self) -> None:
        order = self.raiseRequest(ownerCode="OPERATOR")
        qaHead = self.login("QA-HEAD")
        response = qaHead.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json")
        self.assertEqual(response.status_code, 403, response.content)

    def testARequestWithoutAUnitSaysSoHonestly(self) -> None:
        order = WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device.id,
            title="بدون واحد",
            requestedByUserId=self.people["OPERATOR"],
        )
        operator = self.login("OPERATOR")
        response = operator.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json")
        self.assertEqual(response.status_code, 422, response.content)
        # The refusal must say what happened and what to do — a guard whose
        # message nobody can act on is a guard people learn to ignore.
        self.assertIn("منتسب نشده", str(response.json()["errors"]))
        self.assertIn("ساختار سازمانی", str(response.json()["errors"]))

    def testClosedOrdersHaveNothingToRefer(self) -> None:
        order = self.raiseRequest(ownerCode="OPERATOR")
        order.status = "pendingApproval"
        order.save(update_fields=["status"])
        operator = self.login("OPERATOR")
        response = operator.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json")
        self.assertEqual(response.status_code, 409, response.content)


class TheApproveGateTests(EscalationTestBase):
    """The ladder ends at the manager — and the manager's role is to approve."""

    def testTheManagerApprovesWhatTheLadderBroughtHim(self) -> None:
        # The request climbs to the manager, the technician does the work
        # under him, and only then the gate: the technician cannot approve
        # their own work; the manager can.
        order = self.raiseRequest(ownerCode="OPERATOR")
        order.status = "inProgress"
        order.assignedToUserId = self.people["TECHNICIAN"]
        order.assignedToName = "رضا تکنسین"
        order.save(update_fields=["status", "assignedToUserId", "assignedToName"])

        technician = self.login("TECHNICIAN")
        submitted = technician.post(
            f"{WORK_ORDERS}/{order.id}/status",
            {"target": "pendingApproval", "resolutionNote": "انجام شد"},
            format="json",
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)

        # The same person who did the work cannot also bless it.
        refused = technician.post(f"{WORK_ORDERS}/{order.id}/approve", {}, format="json")
        self.assertEqual(refused.status_code, 403, refused.content)

        manager = self.login("MGR")
        approved = manager.post(
            f"{WORK_ORDERS}/{order.id}/approve", {"note": "تأیید مدیر واحد"}, format="json"
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.json()["data"]["status"], "completed")

    def testEscalationNeverSkipsTheGate(self) -> None:
        # However many rungs the request climbs, its status stays on the
        # work path — escalation moves responsibility, it does not complete
        # or approve anything.
        order = self.raiseRequest(ownerCode="OPERATOR")
        operator = self.login("OPERATOR")
        response = operator.post(f"{WORK_ORDERS}/{order.id}/escalate", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertIn(data["status"], ("assigned", "inProgress"))
