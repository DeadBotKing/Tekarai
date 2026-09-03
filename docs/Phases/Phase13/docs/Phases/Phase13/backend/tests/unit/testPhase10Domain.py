"""Phase 10 domain unit tests (docs/Phases/Phase10.md).

Framework-free tests of the new domain rules: meeting capability matrix
(§30), transcript lifecycle (§34/§35), message revision records (§11) and
user blocks (§70).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.test import SimpleTestCase

from apps.communication.domain.entities.phase10Records import (
    MeetingTranscript,
    MessageRevision,
    TranscriptSegment,
    UserBlock,
)
from apps.communication.domain.services import meetingPermissions
from apps.communication.domain.valueObjects import phase10Types as t
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    InvalidStateTransitionError,
    ValidationFailedError,
)


def _now() -> datetime:
    return datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


class MeetingPermissionMatrixTests(SimpleTestCase):
    def setUp(self) -> None:
        self.organizer = uuid.uuid4()
        self.other = uuid.uuid4()

    def testOrganizerIsHostAndCanEverything(self) -> None:
        for cap in t.MEETING_CAPABILITIES:
            self.assertTrue(
                meetingPermissions.can(
                    cap,
                    userId=self.organizer,
                    organizerId=self.organizer,
                    meetingIsLive=True,
                ),
                cap,
            )

    def testParticipantCanSpeakAndShareButNotEnd(self) -> None:
        self.assertTrue(
            meetingPermissions.can(
                t.CAP_SPEAK,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_PARTICIPANT,
                meetingIsLive=True,
            )
        )
        self.assertTrue(
            meetingPermissions.can(
                t.CAP_SHARE_SCREEN,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_PARTICIPANT,
                meetingIsLive=True,
            )
        )
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_END_MEETING,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_PARTICIPANT,
                meetingIsLive=True,
            )
        )
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_REMOVE_PARTICIPANT,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_PARTICIPANT,
                meetingIsLive=True,
            )
        )

    def testGuestIsRestrictedObserver(self) -> None:
        self.assertTrue(
            meetingPermissions.can(
                t.CAP_JOIN,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_GUEST,
            )
        )
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_VIDEO,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_GUEST,
                meetingIsLive=True,
            )
        )
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_RECORD,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_GUEST,
                meetingIsLive=True,
            )
        )

    def testCoHostCannotEndButCanModerate(self) -> None:
        self.assertTrue(
            meetingPermissions.can(
                t.CAP_REMOVE_PARTICIPANT,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_CO_HOST,
                meetingIsLive=True,
            )
        )
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_END_MEETING,
                userId=self.other,
                organizerId=self.organizer,
                participantRole=t.MEETING_ROLE_CO_HOST,
                meetingIsLive=True,
            )
        )

    def testRecordingRequiresLiveMeeting(self) -> None:
        # not live -> even host cannot "record" via the live guard
        self.assertFalse(
            meetingPermissions.can(
                t.CAP_RECORD,
                userId=self.organizer,
                organizerId=self.organizer,
                meetingIsLive=False,
            )
        )

    def testUnknownCapabilityIsDenied(self) -> None:
        self.assertFalse(
            meetingPermissions.can(
                "CAN_FLY",
                userId=self.other,
                organizerId=self.organizer,
            )
        )


class TranscriptTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.meeting = uuid.uuid4()
        self.user = uuid.uuid4()

    def testRequestThenProcessThenReady(self) -> None:
        tr = MeetingTranscript.request(
            self.tenant, self.meeting, self.user, "fa-IR", _now()
        )
        self.assertEqual(tr.transcriptStatus, t.TRANSCRIPT_PENDING)
        tr.transitionTo(t.TRANSCRIPT_PROCESSING, _now())
        self.assertEqual(tr.transcriptStatus, t.TRANSCRIPT_PROCESSING)
        tr.transitionTo(t.TRANSCRIPT_READY, _now(), contentReference="doc://transcript/1")
        self.assertEqual(tr.transcriptStatus, t.TRANSCRIPT_READY)
        self.assertEqual(tr.contentReference, "doc://transcript/1")
        self.assertTrue(tr.isReady())
        self.assertIn("transcriptReady", [e.name for e in tr.pullEvents()])

    def testReadyRequiresContentReference(self) -> None:
        tr = MeetingTranscript.request(
            self.tenant, self.meeting, self.user, "en-US", _now()
        )
        tr.transitionTo(t.TRANSCRIPT_PROCESSING, _now())
        with self.assertRaises(ValidationFailedError):
            tr.transitionTo(t.TRANSCRIPT_READY, _now(), contentReference="")

    def testIllegalTransitionRejected(self) -> None:
        tr = MeetingTranscript.request(
            self.tenant, self.meeting, self.user, "en-US", _now()
        )
        with self.assertRaises(InvalidStateTransitionError):
            tr.transitionTo(t.TRANSCRIPT_READY, _now(), contentReference="x")

    def testInvalidLanguageRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MeetingTranscript(
                id=uuid.uuid4(),
                tenantId=self.tenant,
                meetingId=self.meeting,
                language="",
                createdAt=_now(),
            )

    def testSegmentValidation(self) -> None:
        with self.assertRaises(ValidationFailedError):
            TranscriptSegment(
                id=uuid.uuid4(),
                tenantId=self.tenant,
                transcriptId=uuid.uuid4(),
                sequence=1,
                speakerId=self.user,
                startTimeSeconds=10.0,
                endTimeSeconds=5.0,  # end before start
                text="hello",
                confidence=0.9,
            )
        with self.assertRaises(ValidationFailedError):
            TranscriptSegment(
                id=uuid.uuid4(),
                tenantId=self.tenant,
                transcriptId=uuid.uuid4(),
                sequence=1,
                speakerId=None,
                startTimeSeconds=0.0,
                endTimeSeconds=1.0,
                text="",  # empty text
                confidence=0.9,
            )


class MessageRevisionTests(SimpleTestCase):
    def testRevisionNumbersStartAtOne(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MessageRevision.record(
                tenantId=uuid.uuid4(),
                messageId=uuid.uuid4(),
                conversationId=uuid.uuid4(),
                previousBody="old",
                newBody="new",
                editedBy=uuid.uuid4(),
                now=_now(),
                revisionNumber=0,
            )

    def testRevisionRecordsBothBodies(self) -> None:
        rev = MessageRevision.record(
            tenantId=uuid.uuid4(),
            messageId=uuid.uuid4(),
            conversationId=uuid.uuid4(),
            previousBody="old body",
            newBody="new body",
            editedBy=uuid.uuid4(),
            now=_now(),
            revisionNumber=1,
        )
        snap = rev.snapshot()
        self.assertEqual(snap["previousBody"], "old body")
        self.assertEqual(snap["newBody"], "new body")
        self.assertEqual(snap["revisionNumber"], 1)


class UserBlockTests(SimpleTestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.a = uuid.uuid4()
        self.b = uuid.uuid4()

    def testCannotBlockSelf(self) -> None:
        with self.assertRaises(BusinessRuleViolationError):
            UserBlock.create(
                tenantId=self.tenant,
                blockerId=self.a,
                blockedUserId=self.a,
                scopes=(t.BLOCK_DIRECT_MESSAGE,),
                now=_now(),
            )

    def testRequiresScope(self) -> None:
        with self.assertRaises(ValidationFailedError):
            UserBlock.create(
                tenantId=self.tenant,
                blockerId=self.a,
                blockedUserId=self.b,
                scopes=(),
                now=_now(),
            )

    def testBlockCoversScopeAndLifts(self) -> None:
        block = UserBlock.create(
            tenantId=self.tenant,
            blockerId=self.a,
            blockedUserId=self.b,
            scopes=(t.BLOCK_DIRECT_MESSAGE, t.BLOCK_CALL),
            now=_now(),
        )
        self.assertTrue(block.covers(t.BLOCK_DIRECT_MESSAGE))
        self.assertTrue(block.covers(t.BLOCK_CALL))
        self.assertFalse(block.covers(t.BLOCK_MEETING_INVITATION))
        block.lift(_now())
        self.assertFalse(block.isActive())
        self.assertFalse(block.covers(t.BLOCK_DIRECT_MESSAGE))

    def testDoubleLiftRejected(self) -> None:
        block = UserBlock.create(
            tenantId=self.tenant,
            blockerId=self.a,
            blockedUserId=self.b,
            scopes=(t.BLOCK_DIRECT_MESSAGE,),
            now=_now(),
        )
        block.lift(_now())
        from apps.sharedKernel.domain.errors import ConflictError

        with self.assertRaises(ConflictError):
            block.lift(_now())
