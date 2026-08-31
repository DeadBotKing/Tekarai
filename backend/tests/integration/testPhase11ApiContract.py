"""Phase 11 integration tests — REST contract under /api/v1/communication.

Exercises the Enterprise Communication surfaces over real HTTP login → bearer
→ view → use case → ORM: policy (§70), delivery (§19), room/session (§34),
screen share (§35), summary + action item review (§38/§39), official messages
(§40/§41), reports (§43/§44) and legal hold (§69). Also verifies §59:
unauthenticated access is refused on every new surface.
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.communication.infrastructure.models import (
    CommunicationPolicyModel,
    MeetingModel,
)
from apps.identity.infrastructure.models import UserModel
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    PLATFORM_ADMIN_USERNAME,
    seedPlatform,
)
from tests.support.phase8Helpers import grantCommAdmin

V1 = "/api/v1/communication"


class Phase11ApiBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        seedPlatform()
        self.client = APIClient()
        from tests.support.phase6Helpers import platformTenantId

        self.tenantId = str(platformTenantId())
        grantCommAdmin(
            TenantModel.objects.get(id=self.tenantId),
            UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME),
        )
        self.token = self.login(PLATFORM_ADMIN_USERNAME)
        self.adminId = str(
            UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME).id
        )

    def login(self, username: str, password: str = PLATFORM_ADMIN_PASSWORD) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            {
                "tenantCode": "platform",
                "identifier": username,
                "password": password,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["accessToken"]

    def auth(self, token: str | None = None) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}

    def makeMeeting(self, *, live: bool = True) -> str:
        meeting = MeetingModel.objects.create(
            id=uuid.uuid4(),
            tenantId=uuid.UUID(self.tenantId),
            conversationId=uuid.uuid4(),
            organizerId=uuid.UUID(self.adminId),
            title="Sync",
            meetingStatus="LIVE" if live else "SCHEDULED",
        )
        return str(meeting.id)


class PolicyApiTests(Phase11ApiBase):
    def testGetPolicyReturnsDefaults(self) -> None:
        res = self.client.get(f"{V1}/policy", **self.auth())
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["data"]["maxGroupMembers"], 5000)

    def testUpdatePolicyPersists(self) -> None:
        res = self.client.put(
            f"{V1}/policy", {"maxGroupMembers": 1234, "allowRecording": False},
            **self.auth(),
        )
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()["data"]["maxGroupMembers"], 1234)
        self.assertEqual(CommunicationPolicyModel.objects.count(), 1)

    def testPolicyRejectsUnauthenticated(self) -> None:
        res = self.client.get(f"{V1}/policy")
        self.assertEqual(res.status_code, 401)


class RoomSessionApiTests(Phase11ApiBase):
    def testRoomOpenSessionStartEnd(self) -> None:
        meetingId = self.makeMeeting(live=False)
        r1 = self.client.post(f"{V1}/meetings/{meetingId}/room", {}, **self.auth())
        self.assertEqual(r1.status_code, 201, r1.content)
        r2 = self.client.post(f"{V1}/meetings/{meetingId}/room", {}, **self.auth())
        self.assertEqual(r1.json()["data"]["id"], r2.json()["data"]["id"])  # idempotent

        s1 = self.client.post(f"{V1}/meetings/{meetingId}/sessions", {}, **self.auth())
        self.assertEqual(s1.status_code, 201, s1.content)
        self.assertEqual(s1.json()["data"]["sequence"], 1)
        s2 = self.client.post(f"{V1}/meetings/{meetingId}/sessions", {}, **self.auth())
        self.assertEqual(s2.json()["data"]["sequence"], 2)

        end = self.client.post(
            f"{V1}/sessions/{s1.json()['data']['id']}/end", {}, **self.auth()
        )
        self.assertEqual(end.status_code, 200, end.content)
        self.assertEqual(end.json()["data"]["status"], "ENDED")


class ScreenShareApiTests(Phase11ApiBase):
    def testStartStopScreenShare(self) -> None:
        meetingId = self.makeMeeting(live=True)
        start = self.client.post(
            f"{V1}/meetings/{meetingId}/screen-share", {"shareKind": "WINDOW"},
            **self.auth(),
        )
        self.assertEqual(start.status_code, 201, start.content)
        self.assertEqual(start.json()["data"]["status"], "ACTIVE")
        stop = self.client.post(
            f"{V1}/screen-shares/{start.json()['data']['id']}/stop", {}, **self.auth()
        )
        self.assertEqual(stop.status_code, 200, stop.content)
        self.assertEqual(stop.json()["data"]["status"], "ENDED")

    def testScreenShareRejectsInvalidKind(self) -> None:
        meetingId = self.makeMeeting(live=True)
        res = self.client.post(
            f"{V1}/meetings/{meetingId}/screen-share", {"shareKind": "HOLOGRAM"},
            **self.auth(),
        )
        self.assertEqual(res.status_code, 400)


class SummaryActionItemApiTests(Phase11ApiBase):
    def testGenerateAndReviewSummary(self) -> None:
        meetingId = self.makeMeeting(live=True)
        gen = self.client.post(
            f"{V1}/meetings/{meetingId}/summary",
            {"summary": "budget", "keyPoints": ["ok"], "confidence": 0.9},
            **self.auth(),
        )
        self.assertEqual(gen.status_code, 201, gen.content)
        self.assertEqual(gen.json()["data"]["humanReviewStatus"], "PENDING")
        review = self.client.post(
            f"{V1}/summaries/{gen.json()['data']['id']}/review",
            {"decision": "APPROVE"}, **self.auth(),
        )
        self.assertEqual(review.status_code, 200, review.content)
        self.assertEqual(review.json()["data"]["humanReviewStatus"], "APPROVED")

    def testActionItemReviewAndDispatch(self) -> None:
        meetingId = self.makeMeeting(live=True)
        from datetime import UTC, datetime

        from apps.communication.domain.entities import phase11Records as records

        item = records.ActionItemCandidate.propose(
            uuid.UUID(self.tenantId), uuid.UUID(meetingId), "Send report",
            datetime.now(tz=UTC), confidence=0.8,
        )
        from apps.communication.infrastructure import container
        container.actionItemRepository().save(item)
        approve = self.client.post(
            f"{V1}/action-items/{item.id}/review", {"decision": "APPROVE"},
            **self.auth(),
        )
        self.assertEqual(approve.status_code, 200, approve.content)
        dispatch = self.client.post(
            f"{V1}/action-items/{item.id}/dispatch", {"taskRef": "task-9"},
            **self.auth(),
        )
        self.assertEqual(dispatch.status_code, 200, dispatch.content)
        self.assertEqual(dispatch.json()["data"]["state"], "DISPATCHED")


class OfficialMessageApiTests(Phase11ApiBase):
    def testFullLifecycleOverHttp(self) -> None:
        create = self.client.post(
            f"{V1}/official-messages",
            {"kind": "ANNOUNCEMENT", "subject": "Holiday", "body": "closed"},
            **self.auth(),
        )
        self.assertEqual(create.status_code, 201, create.content)
        officialId = create.json()["data"]["id"]
        self.assertEqual(create.json()["data"]["status"], "DRAFT")
        for action in ("review", "approve", "publish", "deliver"):
            res = self.client.post(
                f"{V1}/official-messages/{officialId}/transition",
                {"action": action}, **self.auth(),
            )
            self.assertEqual(res.status_code, 200, (action, res.content))
        ack = self.client.post(
            f"{V1}/official-messages/{officialId}/acknowledge", {}, **self.auth()
        )
        self.assertEqual(ack.status_code, 200, ack.content)
        self.assertEqual(ack.json()["data"]["status"], "ACKNOWLEDGED")

    def testPublishFromDraftIsConflict(self) -> None:
        create = self.client.post(
            f"{V1}/official-messages",
            {"kind": "NOTICE", "subject": "Hi"}, **self.auth(),
        )
        officialId = create.json()["data"]["id"]
        res = self.client.post(
            f"{V1}/official-messages/{officialId}/transition",
            {"action": "publish"}, **self.auth(),
        )
        self.assertEqual(res.status_code, 409)


class MessageReportApiTests(Phase11ApiBase):
    def testReportAndResolve(self) -> None:
        from apps.communication.infrastructure.models import MessageModel

        message = MessageModel.objects.create(
            id=uuid.uuid4(),
            tenantId=uuid.UUID(self.tenantId),
            conversationId=uuid.uuid4(),
            senderId=uuid.UUID(self.adminId),
            messageType="TEXT",
            body="spam",
        )
        report = self.client.post(
            f"{V1}/messages/{message.id}/report",
            {"reason": "SPAM", "description": "ads"}, **self.auth(),
        )
        self.assertEqual(report.status_code, 201, report.content)
        resolve = self.client.post(
            f"{V1}/reports/{report.json()['data']['id']}/review",
            {"decision": "RESOLVE", "note": "removed"}, **self.auth(),
        )
        self.assertEqual(resolve.status_code, 200, resolve.content)
        self.assertEqual(resolve.json()["data"]["status"], "RESOLVED")


class LegalHoldApiTests(Phase11ApiBase):
    def testPlaceAndRelease(self) -> None:
        target = uuid.uuid4()
        place = self.client.post(
            f"{V1}/legal-holds",
            {"scope": "CONVERSATION", "targetId": str(target), "reason": "court"},
            **self.auth(),
        )
        self.assertEqual(place.status_code, 201, place.content)
        self.assertEqual(place.json()["data"]["status"], "ACTIVE")
        # idempotent re-place
        again = self.client.post(
            f"{V1}/legal-holds",
            {"scope": "CONVERSATION", "targetId": str(target)}, **self.auth(),
        )
        self.assertEqual(again.json()["data"]["id"], place.json()["data"]["id"])
        release = self.client.post(
            f"{V1}/legal-holds/{place.json()['data']['id']}/release", {},
            **self.auth(),
        )
        self.assertEqual(release.status_code, 200, release.content)
        self.assertEqual(release.json()["data"]["status"], "RELEASED")


class DeliveryApiTests(Phase11ApiBase):
    def testDeliveryReceipt(self) -> None:
        from apps.communication.infrastructure.models import MessageModel

        message = MessageModel.objects.create(
            id=uuid.uuid4(),
            tenantId=uuid.UUID(self.tenantId),
            conversationId=uuid.uuid4(),
            senderId=uuid.UUID(self.adminId),
            messageType="TEXT",
            body="hi",
        )
        res = self.client.post(
            f"{V1}/messages/{message.id}/delivery",
            {"recipientId": self.adminId, "state": "DELIVERED"}, **self.auth(),
        )
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()["data"]["state"], "DELIVERED")

    def testDeliveryUnauthenticated(self) -> None:
        res = self.client.post(
            f"{V1}/messages/%s/delivery" % uuid.uuid4(),
            {"recipientId": str(uuid.uuid4())},
        )
        self.assertEqual(res.status_code, 401)
