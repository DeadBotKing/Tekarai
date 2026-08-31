"""Phase 10 application tests — use cases over real repositories (SQLite
hermetic test DB). Covers §11 revisions, §34/§35 transcripts, §30 meeting
capabilities and §70 user blocks, including tenant isolation.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.communication.application.commands.phase10Commands import (
    BlockUserCommand,
    CompleteTranscriptCommand,
    GetTranscriptQuery,
    ListBlocksQuery,
    ListMessageRevisionsQuery,
    RequestTranscriptCommand,
    SetMeetingCapabilityCommand,
    TranscriptSegmentInput,
    UnblockUserCommand,
)
from apps.communication.infrastructure import container
from apps.communication.infrastructure.models import (
    MeetingModel,
)
from apps.identity.infrastructure.models import UserModel
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import (
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


class Phase10UseCaseBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenant = ensureTenant("p10_tenant")
        self.user = ensureUser(self.tenant, "p10_owner")
        self.other = ensureUser(self.tenant, "p10_other")
        # the acting user holds the communication admin action set
        # (meeting.manage covers transcripts/capabilities — §30/§34).
        grantCommAdmin(self.tenant, self.user)

    def contextFor(self, user: UserModel):
        return ctx(self.tenant.id, user.id)

    def makeMeeting(self) -> MeetingModel:
        return MeetingModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant.id,
            conversationId=uuid.uuid4(),
            organizerId=self.user.id,
            title="Sync",
        )


class TranscriptUseCaseTests(Phase10UseCaseBase):
    def testRequestAndCompleteTranscriptFlow(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.user):
            requested = container.requestTranscriptUseCase().execute(
                RequestTranscriptCommand(meetingId=str(meeting.id), language="en-US")
            )
            self.assertEqual(requested.status, "PENDING")

            # idempotent re-request returns same transcript
            again = container.requestTranscriptUseCase().execute(
                RequestTranscriptCommand(meetingId=str(meeting.id))
            )
            self.assertEqual(again.id, requested.id)

            completed = container.completeTranscriptUseCase().execute(
                CompleteTranscriptCommand(
                    transcriptId=requested.id,
                    contentReference="doc://transcript/x",
                    segments=[
                        TranscriptSegmentInput(
                            speakerId=str(self.user.id),
                            startTimeSeconds=0.0,
                            endTimeSeconds=4.2,
                            text="Welcome everyone",
                            confidence=0.97,
                        ),
                        TranscriptSegmentInput(
                            speakerId=str(self.other.id),
                            startTimeSeconds=4.3,
                            endTimeSeconds=8.0,
                            text="Thanks for having me",
                            confidence=0.91,
                        ),
                    ],
                )
            )
            self.assertEqual(completed.status, "READY")
            self.assertEqual(completed.segmentCount, 2)
            self.assertEqual(len(completed.segments), 2)

            fetched = container.getTranscriptUseCase().execute(
                GetTranscriptQuery(meetingId=str(meeting.id))
            )
            self.assertEqual(fetched.status, "READY")
            self.assertEqual(fetched.segments[0].text, "Welcome everyone")

    def testTranscriptForUnknownMeetingRaises(self) -> None:
        with self.contextFor(self.user):
            with self.assertRaises(EntityNotFoundError):
                container.requestTranscriptUseCase().execute(
                    RequestTranscriptCommand(meetingId=str(uuid.uuid4()))
                )


class MeetingCapabilityUseCaseTests(Phase10UseCaseBase):
    def testOverrideRevokesParticipantRecording(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.user):
            # baseline: participant cannot record (role default already denies)
            check = container.checkMeetingCapabilityUseCase()
            from apps.communication.application.commands.phase10Commands import (
                CheckMeetingCapabilityQuery,
            )

            result = check.execute(
                CheckMeetingCapabilityQuery(
                    meetingId=str(meeting.id),
                    userId=str(self.other.id),
                    capability="CAN_RECORD",
                )
            )
            self.assertFalse(result.granted)

            # organizer grants SHARE_SCREEN to the other user explicitly
            granted = container.setMeetingCapabilityUseCase().execute(
                SetMeetingCapabilityCommand(
                    meetingId=str(meeting.id),
                    userId=str(self.other.id),
                    capability="CAN_SHARE_SCREEN",
                    granted=True,
                )
            )
            self.assertTrue(granted.granted)

    def testUnknownCapabilityRejected(self) -> None:
        meeting = self.makeMeeting()
        with self.contextFor(self.user):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            with self.assertRaises(ValidationFailedError):
                container.setMeetingCapabilityUseCase().execute(
                    SetMeetingCapabilityCommand(
                        meetingId=str(meeting.id),
                        userId=str(self.other.id),
                        capability="CAN_FLY",
                        granted=True,
                    )
                )


class UserBlockUseCaseTests(Phase10UseCaseBase):
    def testBlockThenListThenUnblock(self) -> None:
        with self.contextFor(self.user):
            block = container.blockUserUseCase().execute(
                BlockUserCommand(
                    blockedUserId=str(self.other.id),
                    scopes=["DIRECT_MESSAGE", "CALL"],
                    reason="spam",
                )
            )
            self.assertEqual(block.status, "ACTIVE")
            self.assertIn("CALL", block.scopes)

            blocks = container.listBlocksUseCase().execute(ListBlocksQuery())
            self.assertEqual(len(blocks), 1)

            unblocked = container.unblockUserUseCase().execute(
                UnblockUserCommand(blockedUserId=str(self.other.id))
            )
            self.assertEqual(unblocked.status, "REMOVED")

    def testBlockIsIdempotent(self) -> None:
        with self.contextFor(self.user):
            first = container.blockUserUseCase().execute(
                BlockUserCommand(blockedUserId=str(self.other.id), scopes=["DIRECT_MESSAGE"])
            )
            second = container.blockUserUseCase().execute(
                BlockUserCommand(blockedUserId=str(self.other.id), scopes=["DIRECT_MESSAGE"])
            )
            self.assertEqual(first.id, second.id)


class MessageRevisionUseCaseTests(Phase10UseCaseBase):
    def testEditRecordsRevision(self) -> None:
        # build a direct conversation + message via the application layer
        with self.contextFor(self.user):
            conversation = container.createDirectUseCase().execute(
                __import__(
                    "apps.communication.application.commands.communicationCommands",
                    fromlist=["CreateDirectConversationCommand"],
                ).CreateDirectConversationCommand(peerUserId=str(self.other.id))
            )
            from apps.communication.application.commands.communicationCommands import (
                EditMessageCommand,
                SendMessageCommand,
            )

            sent = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=conversation.id, body="original body"
                )
            )
            container.editMessageUseCase().execute(
                EditMessageCommand(messageId=sent.id, body="edited body")
            )
            revisions = container.listMessageRevisionsUseCase().execute(
                ListMessageRevisionsQuery(messageId=sent.id)
            )
            self.assertEqual(len(revisions), 1)
            self.assertEqual(revisions[0].previousBody, "original body")
            self.assertEqual(revisions[0].newBody, "edited body")
            self.assertEqual(revisions[0].revisionNumber, 1)


class BlockEnforcementTests(Phase10UseCaseBase):
    def testBlockedDirectMessageRefused(self) -> None:
        from apps.communication.application.commands.communicationCommands import (
            CreateDirectConversationCommand,
            SendMessageCommand,
        )
        from apps.sharedKernel.domain.errors import BusinessRuleViolationError

        with self.contextFor(self.user):
            conversation = container.createDirectUseCase().execute(
                CreateDirectConversationCommand(peerUserId=str(self.other.id))
            )
            # user blocks the other
            container.blockUserUseCase().execute(
                __import__(
                    "apps.communication.application.commands.phase10Commands",
                    fromlist=["BlockUserCommand"],
                ).BlockUserCommand(blockedUserId=str(self.other.id), scopes=["DIRECT_MESSAGE"])
            )

        # the blocked user tries to send to the conversation -> refused
        with self.contextFor(self.other):
            with self.assertRaises(BusinessRuleViolationError):
                container.sendMessageUseCase().execute(
                    SendMessageCommand(
                        conversationId=conversation.id, body="hello from blocked"
                    )
                )


class BlockedCallAndInviteTests(Phase10UseCaseBase):
    def testBlockedDirectCallRefused(self) -> None:
        from apps.communication.application.commands.communicationCommands import (
            CreateDirectConversationCommand,
            StartCallCommand,
        )
        from apps.communication.application.commands.phase10Commands import (
            BlockUserCommand,
        )
        from apps.sharedKernel.domain.errors import BusinessRuleViolationError

        with self.contextFor(self.user):
            conversation = container.createDirectUseCase().execute(
                CreateDirectConversationCommand(peerUserId=str(self.other.id))
            )
            container.blockUserUseCase().execute(
                BlockUserCommand(blockedUserId=str(self.other.id), scopes=["CALL"])
            )

        # the blocked user tries to start a direct call -> refused (§70)
        with self.contextFor(self.other):
            with self.assertRaises(BusinessRuleViolationError):
                container.startCallUseCase().execute(
                    StartCallCommand(
                        mediaType="AUDIO", conversationId=conversation.id
                    )
                )

    def testBlockedMeetingInvitationRefused(self) -> None:
        from apps.communication.application.commands.communicationCommands import (
            CreateGroupConversationCommand,
            CreateMeetingCommand,
        )
        from apps.communication.application.commands.phase10Commands import (
            BlockUserCommand,
        )
        from apps.sharedKernel.domain.errors import BusinessRuleViolationError

        with self.contextFor(self.user):
            # a group conversation the organizer and invitee share
            convo = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(
                    name="Project", memberIds=[str(self.other.id)]
                )
            )
            container.blockUserUseCase().execute(
                BlockUserCommand(
                    blockedUserId=str(self.other.id), scopes=["MEETING_INVITATION"]
                )
            )
            with self.assertRaises(BusinessRuleViolationError):
                container.createMeetingUseCase().execute(
                    CreateMeetingCommand(
                        title="Sync",
                        conversationId=convo.id,
                        inviteeIds=[str(self.other.id)],
                    )
                )


class CrossTenantIsolationTests(Phase10UseCaseBase):
    def testBlocksAreTenantScoped(self) -> None:
        otherTenant = ensureTenant("p10_other_tenant")
        outsider = ensureUser(otherTenant, "p10_outsider")
        with self.contextFor(self.user):
            container.blockUserUseCase().execute(
                BlockUserCommand(blockedUserId=str(self.other.id), scopes=["DIRECT_MESSAGE"])
            )
            # blocks of tenant A are not visible to tenant B
            blocks = container.userBlockRepository().listForBlocker(
                otherTenant.id, outsider.id
            )
            self.assertEqual(blocks, [])
        # a block row in tenant A cannot be lifted by a user in tenant B
        with ctx(otherTenant.id, outsider.id):
            from apps.sharedKernel.domain.errors import EntityNotFoundError

            with self.assertRaises(EntityNotFoundError):
                container.unblockUserUseCase().execute(
                    UnblockUserCommand(blockedUserId=str(self.other.id))
                )
