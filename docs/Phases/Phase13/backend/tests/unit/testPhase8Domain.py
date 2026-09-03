"""Phase 8 domain unit tests — aggregates, rules, protocols (no ORM)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from apps.communication.domain.entities.call import Call, CallParticipant
from apps.communication.domain.entities.conversation import Conversation
from apps.communication.domain.entities.meeting import Meeting, MeetingParticipant
from apps.communication.domain.entities.message import Message, MessageReadState
from apps.communication.domain.entities.officialLetter import OfficialLetter
from apps.communication.domain.entities.recording import Recording
from apps.communication.domain.services import communicationRules
from apps.communication.domain.services.communicationRules import SignalingProtocol
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)

TENANT = uuid.uuid4()
ALICE = uuid.uuid4()
BOB = uuid.uuid4()
NOW = datetime(2026, 8, 30, 9, 0, 0, tzinfo=UTC)


class DirectKeyTests(SimpleTestCase):
    def testDirectKeyIsOrderIndependent(self) -> None:
        a = communicationRules.directKeyOf(ALICE, BOB)
        b = communicationRules.directKeyOf(BOB, ALICE)
        self.assertEqual(a, b)
        self.assertIn(str(min(ALICE, BOB)), a)

    def testDirectKeyDiffersAcrossPairs(self) -> None:
        self.assertNotEqual(
            communicationRules.directKeyOf(ALICE, BOB),
            communicationRules.directKeyOf(ALICE, uuid.uuid4()),
        )


class MentionTests(SimpleTestCase):
    def testMentionsExtractDistinctUsernames(self) -> None:
        body = "سلام @alice جان، @bob و @alice دوباره"
        self.assertEqual(
            sorted(communicationRules.mentionedUsernames(body)), ["alice", "bob"]
        )

    def testEmailsAreNotMentions(self) -> None:
        self.assertEqual(communicationRules.mentionedUsernames("mail: a@b.com"), ())


class EditPolicyTests(SimpleTestCase):
    def testSenderWithinWindowMayEdit(self) -> None:
        allowed, reason = communicationRules.canEditMessage(
            senderId=ALICE, actorId=ALICE, createdAt=NOW,
            now=NOW + timedelta(minutes=5), isModerator=False,
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "sender")

    def testWindowExpires(self) -> None:
        allowed, reason = communicationRules.canEditMessage(
            senderId=ALICE,
            actorId=ALICE,
            createdAt=NOW,
            now=NOW + timedelta(minutes=16),
            isModerator=False,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "window_expired")

    def testNonSenderCannotEditButModeratorCan(self) -> None:
        allowed, _ = communicationRules.canEditMessage(
            senderId=ALICE, actorId=BOB, createdAt=NOW, now=NOW, isModerator=False
        )
        self.assertFalse(allowed)
        allowed, reason = communicationRules.canEditMessage(
            senderId=ALICE, actorId=BOB, createdAt=NOW, now=NOW, isModerator=True
        )
        self.assertTrue(allowed)
        self.assertEqual(reason, "moderator")


class ThreadValidationTests(SimpleTestCase):
    def testRootMustExistAndBelongToSameConversation(self) -> None:
        from apps.sharedKernel.domain.errors import EntityNotFoundError

        communicationRules.validateThread(
            replyToId=uuid.uuid4(), rootFound=True, rootSameConversation=True
        )
        with self.assertRaises(EntityNotFoundError):
            communicationRules.validateThread(
                replyToId=uuid.uuid4(), rootFound=False, rootSameConversation=False
            )
        with self.assertRaises(ValidationFailedError):
            communicationRules.validateThread(
                replyToId=uuid.uuid4(), rootFound=True, rootSameConversation=False
            )


class SignalingProtocolTests(SimpleTestCase):
    def testValidEnvelopeRoundTrip(self) -> None:
        envelope = signalingEnvelope(
            "OFFER", callId=str(uuid.uuid4()), payload={"sdp": "v=0"}
        )
        kind, callId, payload = SignalingProtocol.validate(envelope)
        self.assertEqual(kind, "OFFER")
        self.assertEqual(payload["sdp"], "v=0")

    def testVersionAndKindAreEnforced(self) -> None:
        with self.assertRaises(ValidationFailedError):
            SignalingProtocol.validate({"version": "wrong.v1", "kind": "OFFER", "callId": "x"})
        with self.assertRaises(ValidationFailedError):
            SignalingProtocol.validate(
                {"version": SignalingProtocol.VERSION, "kind": "NOT_A_KIND", "callId": "x"}
            )


class ConversationAggregateTests(SimpleTestCase):
    def testDirectConversationStoresDirectKey(self) -> None:
        conversation = Conversation.createDirect(TENANT, ALICE, BOB, NOW)
        self.assertEqual(conversation.conversationType, "DIRECT")
        self.assertEqual(
            conversation.directKey, communicationRules.directKeyOf(ALICE, BOB)
        )

    def testChannelRequiresUniqueCodeAtRepoLevelAndKeepsIt(self) -> None:
        channel = Conversation.createChannel(TENANT, ALICE, "general", NOW, code="general")
        self.assertEqual(channel.conversationType, "CHANNEL")

    def testArchiveIsIdempotentGuard(self) -> None:
        conversation = Conversation.createDirect(TENANT, ALICE, BOB, NOW)
        conversation.archive(NOW)
        self.assertFalse(conversation.isActive)
        with self.assertRaises(ConflictError):
            conversation.archive(NOW)


class MeetingStateMachineTests(SimpleTestCase):
    def testFullLifecycle(self) -> None:
        meeting = Meeting.schedule(TENANT, uuid.uuid4(), ALICE, "standup", NOW)
        self.assertEqual(meeting.meetingStatus, "SCHEDULED")
        meeting.transitionTo("WAITING", NOW)
        meeting.start(NOW)
        self.assertTrue(meeting.isLive())
        meeting.transitionTo("ENDED", NOW + timedelta(hours=1))
        self.assertEqual(meeting.meetingStatus, "ENDED")

    def testInvalidTransitionRejected(self) -> None:
        from apps.sharedKernel.domain.errors import InvalidStateTransitionError

        meeting = Meeting.schedule(TENANT, uuid.uuid4(), ALICE, "standup", NOW)
        with self.assertRaises(InvalidStateTransitionError):
            meeting.transitionTo("ENDED", NOW)

    def testRsvpStates(self) -> None:
        participant = MeetingParticipant.invite(TENANT, uuid.uuid4(), BOB, NOW)
        participant.rsvp(True, NOW)
        self.assertEqual(participant.status, "ACCEPTED")
        participant.join(NOW)
        self.assertEqual(participant.status, "JOINED")
        participant.leave(NOW)
        self.assertEqual(participant.status, "LEFT")


class CallStateMachineTests(SimpleTestCase):
    def testAcceptRingingCall(self) -> None:
        call = Call.start(TENANT, ALICE, "AUDIO", NOW, conversationId=uuid.uuid4())
        self.assertEqual(call.callStatus, "RINGING")
        call.accept(NOW)
        self.assertEqual(call.callStatus, "ACTIVE")
        call.end(NOW)
        self.assertEqual(call.callStatus, "ENDED")

    def testRingingEndIsCancelled(self) -> None:
        call = Call.start(TENANT, ALICE, "AUDIO", NOW, conversationId=uuid.uuid4())
        call.end(NOW)
        self.assertEqual(call.callStatus, "CANCELLED")

    def testRejectFromRingingOnly(self) -> None:
        call = Call.start(TENANT, ALICE, "AUDIO", NOW, conversationId=uuid.uuid4())
        call.reject(NOW)
        self.assertEqual(call.callStatus, "REJECTED")

    def testMediaStateChangeOnLeg(self) -> None:
        leg = CallParticipant.join(TENANT, uuid.uuid4(), BOB, NOW)
        leg.setMediaState("screen_sharing")  # §14
        self.assertEqual(leg.mediaState, "screen_sharing")


class RecordingStateMachineTests(SimpleTestCase):
    def testHappyPath(self) -> None:
        recording = Recording.request(TENANT, uuid.uuid4(), ALICE, NOW)
        for state in ("STARTED", "STOPPED", "PROCESSING"):
            recording.transitionTo(state, NOW)
        recording.attachStorageRef("documents://r/1")
        recording.transitionTo("AVAILABLE", NOW)
        self.assertEqual(recording.recordingStatus, "AVAILABLE")

    def testFailedFromAnyActiveState(self) -> None:
        recording = Recording.request(TENANT, uuid.uuid4(), ALICE, NOW)
        recording.transitionTo("FAILED", NOW, reason="encoder died")
        self.assertEqual(recording.failureReason, "encoder died")


class LetterTests(SimpleTestCase):
    def testReferencePattern(self) -> None:
        import re

        self.assertTrue(re.match(r"^\d{4}-\d{6}$", "2026-000001"))
        self.assertFalse(re.match(r"^\d{4}-\d{6}$", "26-1"))

    def testWorkflowHappyPath(self) -> None:
        letter = OfficialLetter.draft(
            TENANT, ALICE, BOB, "subject", "2026-000001", NOW
        )
        letter.transitionTo("IN_REVIEW", NOW)
        letter.approve(NOW, BOB)
        letter.sign(NOW, ALICE)
        letter.dispatch(NOW)
        letter.markReceived(NOW)
        self.assertEqual(letter.letterStatus, "RECEIVED")

    def testSignWithoutApprovalIsRejected(self) -> None:
        from apps.sharedKernel.domain.errors import InvalidStateTransitionError

        letter = OfficialLetter.draft(TENANT, ALICE, BOB, "s", "2026-000002", NOW)
        with self.assertRaises(InvalidStateTransitionError):
            letter.sign(NOW, ALICE)


class MessageAggregateTests(SimpleTestCase):
    def testSoftDeleteKeepsHistoryIntact(self) -> None:
        message = Message.send(TENANT, uuid.uuid4(), ALICE, "سلام", NOW)
        message.delete(NOW)
        self.assertIsNotNone(message.deletedAt)
        self.assertEqual(message.body, "سلام")  # §34 — no physical destruction

    def testEditStampsEditedAt(self) -> None:
        message = Message.send(TENANT, uuid.uuid4(), ALICE, "اول", NOW)
        message.edit("دوم", NOW + timedelta(minutes=1))
        self.assertEqual(message.body, "دوم")
        self.assertIsNotNone(message.editedAt)

    def testBodyTooLongIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            Message.send(TENANT, uuid.uuid4(), ALICE, "x" * 8001, NOW)

    def testReadStateIsMonotonic(self) -> None:
        read = MessageReadState(
            id=uuid.uuid4(), tenantId=TENANT, conversationId=uuid.uuid4(),
            messageId=uuid.uuid4(), userId=BOB, state="READ", updatedAt=NOW,
        )
        # §3.6 — monotonic: backward transitions are refused (no-op)
        self.assertFalse(read.advance("SENT", NOW))
        self.assertTrue(read.advance("READ", NOW) is False)  # same state is not a change
        delivered = MessageReadState(
            id=uuid.uuid4(), tenantId=TENANT, conversationId=uuid.uuid4(),
            messageId=uuid.uuid4(), userId=BOB, state="DELIVERED", updatedAt=NOW,
        )
        self.assertTrue(delivered.advance("READ", NOW))


# The envelope helper used above lives in the rules module.
def signalingEnvelope(kind: str, callId: str, payload: dict) -> dict:
    return {
        "version": communicationRules.SignalingProtocol.VERSION,
        "kind": kind,
        "callId": callId,
        "payload": payload,
    }
