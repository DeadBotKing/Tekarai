"""Phase 11 domain unit tests (docs/Phases/Phase11.md).

Framework-free tests of the Enterprise Communication domain rules:
§70 CommunicationPolicy, §19 delivery receipts, §34 room/session, §35 screen
share, §38 meeting summary human-review, §39 action item candidates, §40/§41
OfficialMessage lifecycle, §43/§44 reports, §69 legal hold, plus the
§34 constants (READ_ONLY participant, ANNOUNCEMENT channel, VOICE message,
PRESENTER/OBSERVER meeting roles, INSTANT/RECURRING meeting types).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.test import SimpleTestCase

from apps.communication.domain.entities import phase11Records as r
from apps.communication.domain.valueObjects import phase11Types as t
from apps.sharedKernel.domain.errors import (
    ConflictError,
    ValidationFailedError,
)


def _now() -> datetime:
    return datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


class ConstantsTests(SimpleTestCase):
    def testNewConstantsPresent(self) -> None:
        self.assertEqual(t.PARTICIPANT_READ_ONLY, "READ_ONLY")
        self.assertEqual(t.CHANNEL_ANNOUNCEMENT, "ANNOUNCEMENT")
        self.assertEqual(t.MESSAGE_VOICE, "VOICE")
        self.assertIn(t.MEETING_TYPE_INSTANT, t.MEETING_TYPES)
        self.assertIn(t.MEETING_TYPE_RECURRING, t.MEETING_TYPES)
        self.assertEqual(t.MEETING_ROLE_PRESENTER, "PRESENTER")
        self.assertEqual(t.MEETING_ROLE_OBSERVER, "OBSERVER")

    def testObserverCanJoinButNotShareOrSpeak(self) -> None:
        caps = t.roleCapabilitiesV11(t.MEETING_ROLE_OBSERVER)
        self.assertIn(t.CAP_JOIN, caps)
        self.assertNotIn(t.CAP_SHARE_SCREEN, caps)
        self.assertNotIn(t.CAP_SPEAK, caps)
        self.assertNotIn(t.CAP_VIDEO, caps)

    def testPresenterCanShareSpeakAndVideo(self) -> None:
        caps = t.roleCapabilitiesV11(t.MEETING_ROLE_PRESENTER)
        self.assertIn(t.CAP_SHARE_SCREEN, caps)
        self.assertIn(t.CAP_SPEAK, caps)
        self.assertIn(t.CAP_VIDEO, caps)
        self.assertIn(t.CAP_CHAT, caps)

    def testValidateOneOfRejectsUnknown(self) -> None:
        with self.assertRaises(ValidationFailedError):
            t.validateOneOf("NOPE", t.DELIVERY_STATES, field="deliveryState")

    def testValidateOneOfAcceptsKnown(self) -> None:
        self.assertEqual(
            t.validateOneOf("DELIVERED", t.DELIVERY_STATES, field="state"), "DELIVERED"
        )


class CommunicationPolicyTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()

    def testDefaultPolicyUsesPolicyDefaults(self) -> None:
        policy = r.CommunicationPolicy.default(self.tenant)
        self.assertEqual(policy.maxGroupMembers, t.DEFAULT_MAX_GROUP_MEMBERS)
        self.assertEqual(policy.messageRetentionDays, t.DEFAULT_MESSAGE_RETENTION_DAYS)
        self.assertIn("application/pdf", policy.allowedFileTypes)

    def testUpdateChangesValuesAndRecordsEvent(self) -> None:
        policy = r.CommunicationPolicy.default(self.tenant)
        policy.update({"maxGroupMembers": 42, "allowRecording": False}, _now())
        self.assertEqual(policy.maxGroupMembers, 42)
        self.assertFalse(policy.allowRecording)
        names = [e.name for e in policy.pullEvents()]
        self.assertIn("communicationPolicyUpdated", names)

    def testNonPositiveLimitRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.CommunicationPolicy(id=uuid.uuid4(), tenantId=self.tenant, maxGroupMembers=0)

    def testUpdateNonPositiveRejected(self) -> None:
        policy = r.CommunicationPolicy.default(self.tenant)
        with self.assertRaises(ValidationFailedError):
            policy.update({"maxAttachmentSize": -5}, _now())


class MessageDeliveryTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.message = uuid.uuid4()
        self.recipient = uuid.uuid4()

    def testSentToDelivered(self) -> None:
        d = r.MessageDelivery.mark(self.tenant, self.message, self.recipient)
        self.assertEqual(d.state, t.DELIVERY_SENT)
        d.markDelivered(_now())
        self.assertEqual(d.state, t.DELIVERY_DELIVERED)
        self.assertIsNotNone(d.deliveredAt)

    def testDeliveredCannotFail(self) -> None:
        d = r.MessageDelivery.mark(self.tenant, self.message, self.recipient)
        d.markDelivered(_now())
        with self.assertRaises(ConflictError):
            d.markFailed(_now(), "device offline")

    def testSentCanFailWithReason(self) -> None:
        d = r.MessageDelivery.mark(self.tenant, self.message, self.recipient)
        d.markFailed(_now(), "bounce")
        self.assertEqual(d.state, t.DELIVERY_FAILED)
        self.assertEqual(d.failedReason, "bounce")


class MeetingRoomSessionTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.meeting = uuid.uuid4()

    def testOpenRoomRecordsEvent(self) -> None:
        room = r.MeetingRoom.open(self.tenant, self.meeting, _now())
        self.assertTrue(room.isActive)
        self.assertTrue(room.roomRef.startswith("room-"))
        self.assertIn("meetingRoomOpened", [e.name for e in room.pullEvents()])

    def testCloseRoom(self) -> None:
        room = r.MeetingRoom.open(self.tenant, self.meeting, _now())
        room.close(_now())
        self.assertFalse(room.isActive)

    def testSessionStartAndEnd(self) -> None:
        room = r.MeetingRoom.open(self.tenant, self.meeting, _now())
        session = r.MeetingSession.start(self.tenant, self.meeting, room.id, 1, _now())
        self.assertEqual(session.status, t.SESSION_LIVE)
        session.end(_now())
        self.assertEqual(session.status, t.SESSION_ENDED)

    def testEndingNonLiveSessionRejected(self) -> None:
        room = r.MeetingRoom.open(self.tenant, self.meeting, _now())
        session = r.MeetingSession.start(self.tenant, self.meeting, room.id, 1, _now())
        session.end(_now())
        with self.assertRaises(ConflictError):
            session.end(_now())


class ScreenShareTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.meeting = uuid.uuid4()
        self.user = uuid.uuid4()

    def testBeginAndEnd(self) -> None:
        share = r.ScreenShareSession.begin(
            self.tenant, self.meeting, self.user, "SCREEN", _now()
        )
        self.assertEqual(share.status, t.SCREEN_SHARE_ACTIVE)
        share.end(_now())
        self.assertEqual(share.status, t.SCREEN_SHARE_ENDED)

    def testUnknownKindRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.ScreenShareSession.begin(
                self.tenant, self.meeting, self.user, "HOLOGRAM", _now()
            )

    def testEndAlreadyEndedRejected(self) -> None:
        share = r.ScreenShareSession.begin(
            self.tenant, self.meeting, self.user, "WINDOW", _now()
        )
        share.end(_now())
        with self.assertRaises(ConflictError):
            share.end(_now())


class MeetingSummaryTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.meeting = uuid.uuid4()

    def _summary(self) -> r.MeetingSummary:
        return r.MeetingSummary.generate(
            self.tenant, self.meeting, _now(),
            summary="discussed budget",
            keyPoints=["budget approved"],
            decisions=["hire two"],
            actionItems=["send report"],
            risks=["timeline"],
            topics=["finance"],
            confidence=0.82,
            modelReference="tekarai.ai.summary.v1",
        )

    def testGenerateStartsPendingReview(self) -> None:
        s = self._summary()
        self.assertEqual(s.humanReviewStatus, t.AI_REVIEW_PENDING)
        self.assertEqual(s.confidence, 0.82)
        self.assertIn("meetingSummaryGenerated", [e.name for e in s.pullEvents()])

    def testApproveRecordsReviewer(self) -> None:
        s = self._summary()
        reviewer = uuid.uuid4()
        s.approve(reviewer, _now())
        self.assertEqual(s.humanReviewStatus, t.AI_REVIEW_APPROVED)
        self.assertEqual(s.reviewedBy, reviewer)

    def testReject(self) -> None:
        s = self._summary()
        s.reject(uuid.uuid4(), _now())
        self.assertEqual(s.humanReviewStatus, t.AI_REVIEW_REJECTED)

    def testConfidenceOutOfRangeRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.MeetingSummary(
                id=uuid.uuid4(), tenantId=self.tenant, meetingId=self.meeting,
                confidence=1.5,
            )


class ActionItemCandidateTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.meeting = uuid.uuid4()

    def testApproveThenDispatchStoresOnlyRef(self) -> None:
        item = r.ActionItemCandidate.propose(
            self.tenant, self.meeting, "Send Q3 report", _now(), confidence=0.7
        )
        self.assertEqual(item.state, t.ACTION_CANDIDATE)
        item.approve(uuid.uuid4(), _now())
        item.markDispatched("task-abc-123")
        self.assertEqual(item.state, t.ACTION_DISPATCHED)
        self.assertEqual(item.dispatchedItemRef, "task-abc-123")

    def testCannotDispatchUnapproved(self) -> None:
        item = r.ActionItemCandidate.propose(
            self.tenant, self.meeting, "do work", _now()
        )
        with self.assertRaises(ConflictError):
            item.markDispatched("task-1")

    def testRejectEndsWorkflow(self) -> None:
        item = r.ActionItemCandidate.propose(
            self.tenant, self.meeting, "maybe", _now()
        )
        item.reject(uuid.uuid4(), _now(), "duplicate")
        self.assertEqual(item.state, t.ACTION_REJECTED)
        with self.assertRaises(ConflictError):
            item.approve(uuid.uuid4(), _now())

    def testEmptyTitleRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.ActionItemCandidate.propose(self.tenant, self.meeting, "   ", _now())


class OfficialMessageTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.author = uuid.uuid4()

    def _msg(self) -> r.OfficialMessage:
        return r.OfficialMessage.draft(
            self.tenant, self.author, "ANNOUNCEMENT", "New policy", "body", _now(),
            recipientIds=(uuid.uuid4(),),
        )

    def testFullLifecycleToAcknowledged(self) -> None:
        m = self._msg()
        self.assertEqual(m.status, t.OFFICIAL_DRAFT)
        m.submitForReview(_now())
        m.approve(uuid.uuid4(), _now())
        m.publish(_now())
        self.assertEqual(m.status, t.OFFICIAL_PUBLISHED)
        self.assertIsNotNone(m.publishedAt)
        m.markDelivered(_now())
        recipient = uuid.uuid4()
        m.acknowledge(recipient, _now())
        self.assertEqual(m.status, t.OFFICIAL_ACKNOWLEDGED)
        self.assertIn(recipient, m.acknowledgedBy)

    def testCannotPublishDraftDirectly(self) -> None:
        m = self._msg()
        with self.assertRaises(ConflictError):
            m.publish(_now())

    def testReturnToDraftFromReview(self) -> None:
        m = self._msg()
        m.submitForReview(_now())
        m.returnToDraft(uuid.uuid4(), _now())
        self.assertEqual(m.status, t.OFFICIAL_DRAFT)

    def testUnknownKindRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.OfficialMessage.draft(
                self.tenant, self.author, "SPAM", "s", "b", _now()
            )

    def testEmptySubjectRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.OfficialMessage.draft(
                self.tenant, self.author, "NOTICE", "  ", "b", _now()
            )


class MessageReportTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.message = uuid.uuid4()
        self.reporter = uuid.uuid4()

    def _report(self) -> r.MessageReport:
        return r.MessageReport.open(
            self.tenant, self.message, self.reporter, "SPAM", _now()
        )

    def testOpenStartsOpen(self) -> None:
        rep = self._report()
        self.assertEqual(rep.status, t.REPORT_OPEN)
        self.assertIn("messageReported", [e.name for e in rep.pullEvents()])

    def testResolveFlow(self) -> None:
        rep = self._report()
        rep.resolve(uuid.uuid4(), _now(), "content removed")
        self.assertEqual(rep.status, t.REPORT_RESOLVED)
        self.assertEqual(rep.resolutionNote, "content removed")

    def testDismissFlow(self) -> None:
        rep = self._report()
        rep.dismiss(uuid.uuid4(), _now(), "not a violation")
        self.assertEqual(rep.status, t.REPORT_DISMISSED)

    def testUnknownReasonRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.MessageReport.open(
                self.tenant, self.message, self.reporter, "BOGUS", _now()
            )


class LegalHoldTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.target = uuid.uuid4()

    def testPlaceAndRelease(self) -> None:
        hold = r.LegalHold.place(
            self.tenant, "CONVERSATION", self.target, _now(), reason="court order"
        )
        self.assertEqual(hold.status, t.LEGAL_HOLD_ACTIVE)
        hold.release(_now())
        self.assertEqual(hold.status, t.LEGAL_HOLD_RELEASED)
        self.assertIsNotNone(hold.releasedAt)

    def testReleaseInactiveRejected(self) -> None:
        hold = r.LegalHold.place(self.tenant, "USER", self.target, _now())
        hold.release(_now())
        with self.assertRaises(ConflictError):
            hold.release(_now())

    def testUnknownScopeRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            r.LegalHold.place(self.tenant, "GALAXY", self.target, _now())
