"""Phase 11 application tests — use cases over real repositories (SQLite
hermetic test DB). Covers §70 policy, §19 delivery, §34 room/session, §35
screen share, §38 summary review, §39 action items, §40/§41 official messages,
§43/§44 reports and §69 legal hold — including tenant isolation and
idempotency.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.communication.application.commands.phase11Commands import (
    AcknowledgeOfficialMessageCommand,
    CreateOfficialMessageCommand,
    DispatchActionItemCommand,
    EndMeetingSessionCommand,
    GenerateMeetingSummaryCommand,
    OpenMeetingRoomCommand,
    PlaceLegalHoldCommand,
    RecordDeliveryCommand,
    ReleaseLegalHoldCommand,
    ReportMessageCommand,
    ReviewActionItemCommand,
    ReviewMeetingSummaryCommand,
    ReviewMessageReportCommand,
    StartMeetingSessionCommand,
    StartScreenShareCommand,
    StopScreenShareCommand,
    TransitionOfficialMessageCommand,
    UpdateCommunicationPolicyCommand,
)
from apps.communication.application.useCases.phase11UseCases import (
    retentionPurgeAllowed,
)
from apps.communication.infrastructure import container
from apps.communication.infrastructure.models import (
    CommunicationPolicyModel,
    LegalHoldModel,
    MeetingModel,
    MeetingSessionModel,
    MessageModel,
    OfficialMessageModel,
)
from apps.communication.infrastructure.repositories.phase11RepositoriesImpl import (
    LegalHoldRepositoryDjango,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    ConflictError,
    EntityNotFoundError,
)
from tests.support.phase8Helpers import ensureTenant, ensureUser, grantCommAdmin


def ctx(tenantId: uuid.UUID, userId: uuid.UUID):
    return requestScope(
        RequestContext(
            actorId=str(userId),
            tenantId=str(tenantId),
            actorTenantId=str(tenantId),
        )
    )


class Phase11UseCaseBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenant = ensureTenant("p11_tenant")
        self.other = ensureTenant("p11_other")
        self.user = ensureUser(self.tenant, "p11_owner")
        self.user2 = ensureUser(self.tenant, "p11_member")
        self.alien = ensureUser(self.other, "p11_alien")
        grantCommAdmin(self.tenant, self.user)

    def contextFor(self, tenant, user):
        return ctx(tenant.id, user.id)

    def makeMeeting(self, *, live: bool = False) -> MeetingModel:
        return MeetingModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant.id,
            conversationId=uuid.uuid4(),
            organizerId=self.user.id,
            title="Sync",
            meetingStatus="LIVE" if live else "SCHEDULED",
        )

    def makeMessage(self) -> MessageModel:
        return MessageModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant.id,
            conversationId=uuid.uuid4(),
            senderId=self.user.id,
            messageType="TEXT",
            body="hello",
        )


class CommunicationPolicyUseCaseTests(Phase11UseCaseBase):
    def testGetReturnsDefaultsWhenAbsent(self) -> None:
        with self.contextFor(self.tenant, self.user):
            policy = container.getCommunicationPolicyUseCase().execute(object())
        self.assertEqual(policy.maxGroupMembers, 5000)
        self.assertEqual(CommunicationPolicyModel.objects.count(), 0)

    def testUpdatePersistsAndIsReadable(self) -> None:
        with self.contextFor(self.tenant, self.user):
            container.updateCommunicationPolicyUseCase().execute(
                UpdateCommunicationPolicyCommand(changes={"maxGroupMembers": 77})
            )
            policy = container.getCommunicationPolicyUseCase().execute(object())
        self.assertEqual(policy.maxGroupMembers, 77)
        self.assertEqual(CommunicationPolicyModel.objects.count(), 1)

    def testPolicyIsTenantScoped(self) -> None:
        with self.contextFor(self.tenant, self.user):
            container.updateCommunicationPolicyUseCase().execute(
                UpdateCommunicationPolicyCommand(changes={"maxGroupMembers": 77})
            )
        # other tenant must not see the updated value
        with self.contextFor(self.other, self.alien):
            policy = container.getCommunicationPolicyUseCase().execute(object())
        self.assertEqual(policy.maxGroupMembers, 5000)


class MessageDeliveryUseCaseTests(Phase11UseCaseBase):
    def testMarkDelivered(self) -> None:
        message = self.makeMessage()
        with self.contextFor(self.tenant, self.user):
            result = container.recordDeliveryUseCase().execute(
                RecordDeliveryCommand(
                    messageId=str(message.id),
                    recipientId=str(self.user2.id),
                    state="DELIVERED",
                )
            )
        self.assertEqual(result["state"], "DELIVERED")

    def testDeliveryForMissingMessageRaises(self) -> None:
        with self.contextFor(self.tenant, self.user):
            with self.assertRaises(EntityNotFoundError):
                container.recordDeliveryUseCase().execute(
                    RecordDeliveryCommand(
                        messageId=str(uuid.uuid4()),
                        recipientId=str(self.user2.id),
                    )
                )

    def testCrossTenantMessageNotDeliverable(self) -> None:
        message = self.makeMessage()
        with self.contextFor(self.other, self.alien):
            with self.assertRaises(EntityNotFoundError):
                container.recordDeliveryUseCase().execute(
                    RecordDeliveryCommand(
                        messageId=str(message.id),
                        recipientId=str(self.alien.id),
                    )
                )


class MeetingRoomSessionUseCaseTests(Phase11UseCaseBase):
    def testOpenRoomIdempotent(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.tenant, self.user):
            room1 = container.openMeetingRoomUseCase().execute(
                OpenMeetingRoomCommand(meetingId=str(meeting.id))
            )
            room2 = container.openMeetingRoomUseCase().execute(
                OpenMeetingRoomCommand(meetingId=str(meeting.id))
            )
        self.assertEqual(room1.id, room2.id)

    def testStartAndEndSession(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.tenant, self.user):
            session = container.startMeetingSessionUseCase().execute(
                StartMeetingSessionCommand(meetingId=str(meeting.id))
            )
            self.assertEqual(session.sequence, 1)
            ended = container.endMeetingSessionUseCase().execute(
                EndMeetingSessionCommand(sessionId=str(session.id))
            )
        self.assertEqual(ended.status, "ENDED")
        self.assertEqual(
            MeetingSessionModel.objects.get(id=session.id).sessionStatus, "ENDED"
        )

    def testRecurringSessionsIncrementSequence(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.tenant, self.user):
            s1 = container.startMeetingSessionUseCase().execute(
                StartMeetingSessionCommand(meetingId=str(meeting.id))
            )
            container.endMeetingSessionUseCase().execute(
                EndMeetingSessionCommand(sessionId=str(s1.id))
            )
            s2 = container.startMeetingSessionUseCase().execute(
                StartMeetingSessionCommand(meetingId=str(meeting.id))
            )
        self.assertEqual(s2.sequence, 2)


class ScreenShareUseCaseTests(Phase11UseCaseBase):
    def testStartAndStopOnLiveMeeting(self) -> None:
        meeting = self.makeMeeting(live=True)
        with self.contextFor(self.tenant, self.user):
            share = container.startScreenShareUseCase().execute(
                StartScreenShareCommand(meetingId=str(meeting.id), shareKind="SCREEN")
            )
            self.assertEqual(share.status, "ACTIVE")
            stopped = container.stopScreenShareUseCase().execute(
                StopScreenShareCommand(shareId=str(share.id))
            )
        self.assertEqual(stopped.status, "ENDED")

    def testScreenShareRequiresLiveMeeting(self) -> None:
        meeting = self.makeMeeting(live=False)
        with self.contextFor(self.tenant, self.user):
            with self.assertRaises(BusinessRuleViolationError):
                container.startScreenShareUseCase().execute(
                    StartScreenShareCommand(meetingId=str(meeting.id))
                )


class MeetingSummaryActionItemUseCaseTests(Phase11UseCaseBase):
    def _summary(self, meeting_id: str):
        return GenerateMeetingSummaryCommand(
            meetingId=meeting_id,
            summary="budget approved",
            keyPoints=["budget"],
            decisions=["hire"],
            actionItems=["send report"],
            risks=["time"],
            topics=["finance"],
            confidence=0.9,
        )

    def testGenerateThenApproveSummary(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.tenant, self.user):
            summary = container.generateMeetingSummaryUseCase().execute(
                self._summary(str(meeting.id))
            )
            self.assertEqual(summary.humanReviewStatus, "PENDING")
            reviewed = container.reviewMeetingSummaryUseCase().execute(
                ReviewMeetingSummaryCommand(summaryId=str(summary.id), decision="APPROVE")
            )
        self.assertEqual(reviewed.humanReviewStatus, "APPROVED")

    def testActionItemApproveThenDispatchStoresRef(self) -> None:
        from datetime import UTC, datetime

        from apps.communication.domain.entities import phase11Records as records

        meeting = self.makeMeeting()
        now = datetime.now(tz=UTC)
        item = records.ActionItemCandidate.propose(
            self.tenant.id, meeting.id, "Send report", now, confidence=0.8
        )
        container.actionItemRepository().save(item)
        with self.contextFor(self.tenant, self.user):
            container.reviewActionItemUseCase().execute(
                ReviewActionItemCommand(itemId=str(item.id), decision="APPROVE")
            )
            dispatched = container.dispatchActionItemUseCase().execute(
                DispatchActionItemCommand(itemId=str(item.id), taskRef="task-xyz")
            )
        self.assertEqual(dispatched.state, "DISPATCHED")
        self.assertEqual(dispatched.dispatchedItemRef, "task-xyz")

    def testDispatchUnapprovedRejected(self) -> None:
        from datetime import UTC, datetime

        from apps.communication.domain.entities import phase11Records as records

        meeting = self.makeMeeting()
        item = records.ActionItemCandidate.propose(
            self.tenant.id, meeting.id, "raw candidate", datetime.now(tz=UTC)
        )
        container.actionItemRepository().save(item)
        with self.contextFor(self.tenant, self.user):
            with self.assertRaises(ConflictError):
                container.dispatchActionItemUseCase().execute(
                    DispatchActionItemCommand(itemId=str(item.id), taskRef="task-1")
                )


class OfficialMessageUseCaseTests(Phase11UseCaseBase):
    def testFullLifecycleAndAcknowledge(self) -> None:
        with self.contextFor(self.tenant, self.user):
            message = container.createOfficialMessageUseCase().execute(
                CreateOfficialMessageCommand(
                    kind="ANNOUNCEMENT",
                    subject="Holiday",
                    body="office closed",
                    recipientIds=[str(self.user2.id)],
                )
            )
            for action in ("review", "approve", "publish", "deliver"):
                message = container.transitionOfficialMessageUseCase().execute(
                    TransitionOfficialMessageCommand(
                        officialId=str(message.id), action=action
                    )
                )
            acked = container.acknowledgeOfficialMessageUseCase().execute(
                AcknowledgeOfficialMessageCommand(officialId=str(message.id))
            )
        self.assertEqual(acked.status, "ACKNOWLEDGED")
        self.assertEqual(OfficialMessageModel.objects.count(), 1)

    def testCannotPublishDraft(self) -> None:
        with self.contextFor(self.tenant, self.user):
            message = container.createOfficialMessageUseCase().execute(
                CreateOfficialMessageCommand(kind="NOTICE", subject="Hi")
            )
            with self.assertRaises(ConflictError):
                container.transitionOfficialMessageUseCase().execute(
                    TransitionOfficialMessageCommand(
                        officialId=str(message.id), action="publish"
                    )
                )


class MessageReportUseCaseTests(Phase11UseCaseBase):
    def testReportThenResolve(self) -> None:
        message = self.makeMessage()
        with self.contextFor(self.tenant, self.user2):
            report = container.reportMessageUseCase().execute(
                ReportMessageCommand(
                    messageId=str(message.id), reason="SPAM", description="ads"
                )
            )
        with self.contextFor(self.tenant, self.user):
            resolved = container.reviewMessageReportUseCase().execute(
                ReviewMessageReportCommand(
                    reportId=str(report.id), decision="RESOLVE", note="removed"
                )
            )
        self.assertEqual(resolved.status, "RESOLVED")

    def testReportMissingMessageRaises(self) -> None:
        with self.contextFor(self.tenant, self.user):
            with self.assertRaises(EntityNotFoundError):
                container.reportMessageUseCase().execute(
                    ReportMessageCommand(messageId=str(uuid.uuid4()), reason="SPAM")
                )


class LegalHoldUseCaseTests(Phase11UseCaseBase):
    def testPlaceIsIdempotent(self) -> None:
        target = uuid.uuid4()
        with self.contextFor(self.tenant, self.user):
            h1 = container.placeLegalHoldUseCase().execute(
                PlaceLegalHoldCommand(scope="CONVERSATION", targetId=str(target))
            )
            h2 = container.placeLegalHoldUseCase().execute(
                PlaceLegalHoldCommand(scope="CONVERSATION", targetId=str(target))
            )
        self.assertEqual(h1.id, h2.id)
        self.assertEqual(LegalHoldModel.objects.count(), 1)

    def testPurgeBlockedWhileActive(self) -> None:
        target = uuid.uuid4()
        repo = LegalHoldRepositoryDjango()
        with self.contextFor(self.tenant, self.user):
            container.placeLegalHoldUseCase().execute(
                PlaceLegalHoldCommand(scope="MEETING", targetId=str(target))
            )
        self.assertFalse(
            retentionPurgeAllowed(repo, self.tenant.id, "MEETING", target)
        )
        # a different target is purgeable
        self.assertTrue(
            retentionPurgeAllowed(repo, self.tenant.id, "MEETING", uuid.uuid4())
        )

    def testPurgeAllowedAfterRelease(self) -> None:
        target = uuid.uuid4()
        repo = LegalHoldRepositoryDjango()
        with self.contextFor(self.tenant, self.user):
            hold = container.placeLegalHoldUseCase().execute(
                PlaceLegalHoldCommand(scope="USER", targetId=str(target))
            )
            container.releaseLegalHoldUseCase().execute(
                ReleaseLegalHoldCommand(holdId=str(hold.id))
            )
        self.assertTrue(
            retentionPurgeAllowed(repo, self.tenant.id, "USER", target)
        )

    def testCrossTenantHoldNotVisible(self) -> None:
        target = uuid.uuid4()
        repo = LegalHoldRepositoryDjango()
        with self.contextFor(self.tenant, self.user):
            container.placeLegalHoldUseCase().execute(
                PlaceLegalHoldCommand(scope="USER", targetId=str(target))
            )
        # other tenant sees no hold → purge "allowed" from their view
        self.assertTrue(
            retentionPurgeAllowed(repo, self.other.id, "USER", target)
        )
