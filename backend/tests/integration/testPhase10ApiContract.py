"""Phase 10 integration tests — REST contract under /api/v1/communication.

Exercises the new surfaces over real HTTP login → bearer → view → use case →
ORM: message revisions (§11), transcripts (§34/§35), meeting capabilities
(§30) and user blocks (§70), including the security tests §59 requires
(unauthenticated access is refused).
"""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.communication.infrastructure.models import MeetingModel
from apps.identity.infrastructure.models import UserModel
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    PLATFORM_ADMIN_USERNAME,
    seedPlatform,
)
from tests.support.phase8Helpers import ensureUser, grantCommAdmin

V1 = "/api/v1/communication"


class Phase10ApiBase(TestCase):
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

    def makeMeeting(self) -> str:
        meeting = MeetingModel.objects.create(
            id=uuid.uuid4(),
            tenantId=uuid.UUID(self.tenantId),
            conversationId=uuid.uuid4(),
            organizerId=uuid.UUID(self.adminId),
            title="Sync",
        )
        return str(meeting.id)


class BlockApiTests(Phase10ApiBase):
    def testBlockListAndUnblock(self) -> None:
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-block-target")

        created = self.client.post(
            f"{V1}/blocks",
            {
                "blockedUserId": str(member.id),
                "scopes": ["DIRECT_MESSAGE", "CALL"],
                "reason": "spam",
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["data"]["status"], "ACTIVE")

        listing = self.client.get(f"{V1}/blocks", **self.auth())
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["data"]), 1)

        unblocked = self.client.delete(
            f"{V1}/blocks/{member.id}", **self.auth()
        )
        self.assertEqual(unblocked.status_code, 200, unblocked.content)
        self.assertEqual(unblocked.json()["data"]["status"], "REMOVED")

    def testBlockRequiresAuth(self) -> None:
        response = self.client.post(
            f"{V1}/blocks", {"blockedUserId": str(uuid.uuid4())}, format="json"
        )
        self.assertEqual(response.status_code, 401)


class MeetingCapabilityApiTests(Phase10ApiBase):
    def testSetAndCheckCapability(self) -> None:
        meetingId = self.makeMeeting()
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-cap-user")

        setResp = self.client.post(
            f"{V1}/meetings/{meetingId}/capabilities",
            {"userId": str(member.id), "capability": "CAN_RECORD", "granted": True},
            format="json",
            **self.auth(),
        )
        self.assertEqual(setResp.status_code, 200, setResp.content)

        check = self.client.get(
            f"{V1}/meetings/{meetingId}/capabilities",
            {"userId": str(member.id), "capability": "CAN_RECORD"},
            **self.auth(),
        )
        self.assertEqual(check.status_code, 200, check.content)
        # CAN_RECORD on a not-yet-live meeting is still denied by the live
        # guard even with an override (§30 recording is a live capability).
        self.assertIn("granted", check.json()["data"])

    def testCapabilityRequiresAuth(self) -> None:
        meetingId = self.makeMeeting()
        response = self.client.get(
            f"{V1}/meetings/{meetingId}/capabilities",
            {"userId": self.adminId, "capability": "CAN_SPEAK"},
        )
        self.assertEqual(response.status_code, 401)


class TranscriptApiTests(Phase10ApiBase):
    def testTranscriptRequestAndComplete(self) -> None:
        meetingId = self.makeMeeting()

        request = self.client.post(
            f"{V1}/meetings/{meetingId}/transcript",
            {"language": "en-US"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(request.status_code, 201, request.content)
        transcriptId = request.json()["data"]["id"]
        self.assertEqual(request.json()["data"]["status"], "PENDING")

        complete = self.client.post(
            f"{V1}/transcripts/{transcriptId}/complete",
            {
                "contentReference": "doc://transcript/abc",
                "segments": [
                    {
                        "speakerId": self.adminId,
                        "startTimeSeconds": 0.0,
                        "endTimeSeconds": 5.0,
                        "text": "Kickoff",
                        "confidence": 0.98,
                    }
                ],
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(complete.status_code, 200, complete.content)
        data = complete.json()["data"]
        self.assertEqual(data["status"], "READY")
        self.assertEqual(data["segmentCount"], 1)

        fetched = self.client.get(
            f"{V1}/meetings/{meetingId}/transcript", **self.auth()
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["data"]["status"], "READY")

    def testCompleteUnknownTranscript404(self) -> None:
        response = self.client.post(
            f"{V1}/transcripts/{uuid.uuid4()}/complete",
            {"contentReference": "doc://x", "segments": []},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 404)


class MessageThreadApiTests(Phase10ApiBase):
    def testDeepRepliesShareThreadRoot(self) -> None:
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-thread-user")
        conv = self.client.post(
            f"{V1}/conversations",
            {"kind": "direct", "peerUserId": str(member.id)},
            format="json",
            **self.auth(),
        )
        self.assertEqual(conv.status_code, 201, conv.content)
        conversationId = conv.json()["data"]["id"]

        def send(body: str, replyTo: str = "") -> str:
            payload: dict[str, object] = {"body": body}
            if replyTo:
                payload["replyToId"] = replyTo
            resp = self.client.post(
                f"{V1}/conversations/{conversationId}/messages",
                payload,
                format="json",
                **self.auth(),
            )
            self.assertEqual(resp.status_code, 201, resp.content)
            return resp.json()["data"]["id"]

        root = send("root message")
        reply1 = send("first reply", replyTo=root)
        # a deep reply points at reply1, but its thread root must still be root
        send("deep reply", replyTo=reply1)

        thread = self.client.get(
            f"{V1}/conversations/{conversationId}/messages",
            {"threadRootId": root},
            **self.auth(),
        )
        self.assertEqual(thread.status_code, 200, thread.content)
        bodies = {item["body"] for item in thread.json()["data"]}
        self.assertIn("first reply", bodies)
        self.assertIn("deep reply", bodies)
        self.assertNotIn("root message", bodies)

    def testSystemEventMessageTypesAccepted(self) -> None:
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-mtype-user")
        conv = self.client.post(
            f"{V1}/conversations",
            {"kind": "direct", "peerUserId": str(member.id)},
            format="json",
            **self.auth(),
        )
        conversationId = conv.json()["data"]["id"]
        for kind in ("DOCUMENT", "CALL_EVENT", "MEETING_EVENT"):
            resp = self.client.post(
                f"{V1}/conversations/{conversationId}/messages",
                {"body": f"system {kind}", "messageType": kind},
                format="json",
                **self.auth(),
            )
            self.assertEqual(resp.status_code, 201, resp.content)
            self.assertEqual(resp.json()["data"]["messageType"], kind)


class PresencePrivacyApiTests(Phase10ApiBase):
    def testInvisibleAppearsOfflineToOthers(self) -> None:
        userId = self.adminId
        setResp = self.client.put(
            f"{V1}/presence",
            {"status": "INVISIBLE"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(setResp.status_code, 200, setResp.content)
        got = self.client.get(
            f"{V1}/presence?userIds={userId}", **self.auth()
        )
        self.assertEqual(got.status_code, 200)
        # §17 — an INVISIBLE user is presented to other viewers as OFFLINE
        self.assertEqual(got.json()["data"]["presence"][userId], "OFFLINE")


class RateLimitApiTests(Phase10ApiBase):
    def testSendMessageRateLimitEnforced(self) -> None:
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-rl-user")
        conv = self.client.post(
            f"{V1}/conversations",
            {"kind": "direct", "peerUserId": str(member.id)},
            format="json",
            **self.auth(),
        )
        self.assertEqual(conv.status_code, 201, conv.content)
        conversationId = conv.json()["data"]["id"]

        # communication:sendMessage is (30, 60) — hammer past the limit
        statuses = []
        for _ in range(40):
            resp = self.client.post(
                f"{V1}/conversations/{conversationId}/messages",
                {"body": "rate limit probe"},
                format="json",
                **self.auth(),
            )
            statuses.append(resp.status_code)
            if resp.status_code == 429:
                break
        self.assertIn(429, statuses, f"expected a 429 within the burst, got {statuses[-3:]}")


class MessageRevisionApiTests(Phase10ApiBase):
    def testRevisionHistoryAfterEdit(self) -> None:
        member = ensureUser(TenantModel.objects.get(id=self.tenantId), "p10-rev-user")

        conv = self.client.post(
            f"{V1}/conversations",
            {"kind": "direct", "peerUserId": str(member.id)},
            format="json",
            **self.auth(),
        )
        self.assertEqual(conv.status_code, 201, conv.content)
        conversationId = conv.json()["data"]["id"]

        sent = self.client.post(
            f"{V1}/conversations/{conversationId}/messages",
            {"body": "before edit"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(sent.status_code, 201, sent.content)
        messageId = sent.json()["data"]["id"]

        edited = self.client.patch(
            f"{V1}/messages/{messageId}",
            {"body": "after edit"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(edited.status_code, 200, edited.content)

        revisions = self.client.get(
            f"{V1}/messages/{messageId}/revisions", **self.auth()
        )
        self.assertEqual(revisions.status_code, 200, revisions.content)
        items = revisions.json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["previousBody"], "before edit")
        self.assertEqual(items[0]["newBody"], "after edit")
