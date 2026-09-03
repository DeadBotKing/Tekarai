"""Phase 8 application tests — use cases over the real ORM (§38).

The ten critical scenarios required by the spec, plus idempotency,
outbox and presence behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest import mock

from django.test import TestCase

from apps.communication.application.commands.communicationCommands import (
    AcceptCallCommand,
    AddParticipantCommand,
    ArchiveConversationCommand,
    ChangeParticipantRoleCommand,
    CreateChannelCommand,
    CreateDirectConversationCommand,
    CreateGroupConversationCommand,
    CreateLetterCommand,
    CreateMeetingCommand,
    DeleteMessageCommand,
    EditMessageCommand,
    EndMeetingCommand,
    JoinChannelCommand,
    JoinMeetingCommand,
    LeaveConversationCommand,
    MarkConversationReadCommand,
    PinMessageCommand,
    ReactToMessageCommand,
    RelaySignalCommand,
    SendMessageCommand,
    SignLetterCommand,
    StartCallCommand,
    StartMeetingCommand,
    StartRecordingCommand,
    SubmitLetterCommand,
    UpdatePresenceCommand,
)
from apps.communication.application.dto.communicationDtos import messageDtoFromDomain
from apps.communication.application.queries.communicationQueries import (
    ListConversationsQuery,
    ListMessagesQuery,
    PresenceQuery,
    SearchMessagesQuery,
)
from apps.communication.infrastructure import container
from apps.communication.infrastructure.metrics.communicationMetrics import (
    communicationMetrics,
)
from apps.communication.infrastructure.models import OutboxModel
from apps.communication.infrastructure.realtime.realtimeInfra import (
    ChannelsRealtimeBroadcaster,
)
from apps.communication.domain.services.communicationRules import SignalingProtocol
from apps.sharedKernel.application.requestContext import RequestContext
from apps.sharedKernel.domain.errors import (
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from tests.support.phase8Helpers import asUser, ensureTenant, ensureUser, grantCommAdmin


def _envelope(callId: str, kind: str = "OFFER", payload: dict | None = None) -> dict:
    return SignalingProtocol.envelope(
        kind, callId=callId, fromUser="x", payload=payload or {"sdp": "v=0"}
    )


class Phase8UseCaseTestBase(TestCase):
    """Seeds tenant A (admin + member) and tenant B (one user)."""

    def setUp(self) -> None:
        super().setUp()
        self.tenantA = ensureTenant("phase8-tenant-a")
        self.tenantB = ensureTenant("phase8-tenant-b")
        self.admin = ensureUser(self.tenantA, "p8-admin")
        self.member = ensureUser(self.tenantA, "p8-member")
        self.outsider = ensureUser(self.tenantA, "p8-outsider")
        self.foreign = ensureUser(self.tenantB, "p8-foreign")
        grantCommAdmin(self.tenantA, self.admin)
        with asUser(self.tenantA.id, self.admin.id):
            self.conversation = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(
                    name="اتاق پروژه", memberIds=[str(self.member.id)]
                )
            )
            self.message = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=str(self.conversation.id), body="پیام اول"
                )
            )

    # helpers ---------------------------------------------------------------

    def sendAs(self, user, body: str, *, conversationId: str | None = None):
        with asUser(self.tenantA.id, user.id):
            return container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=conversationId or str(self.conversation.id),
                    body=body,
                )
            )


# §38 scenario 1 — unauthorized conversation access --------------------------


class UnauthorizedConversationAccessTests(Phase8UseCaseTestBase):
    def testNonMemberCannotSendOrRead(self) -> None:
        with asUser(self.tenantA.id, self.outsider.id):
            with self.assertRaises(PermissionDeniedError):
                container.sendMessageUseCase().execute(
                    SendMessageCommand(
                        conversationId=str(self.conversation.id), body="spam"
                    )
                )
            with self.assertRaises(PermissionDeniedError):
                container.listMessagesUseCase().execute(
                    ListMessagesQuery(conversationId=str(self.conversation.id))
                )

    def testNonChannelConversationCannotBeJoined(self) -> None:
        with asUser(self.tenantA.id, self.outsider.id):
            with self.assertRaises((EntityNotFoundError, PermissionDeniedError)):
                container.joinChannelUseCase().execute(
                    JoinChannelCommand(conversationId=str(self.conversation.id))
                )


# §38 scenario 2 — cross-tenant isolation --------------------------------------


class CrossTenantIsolationTests(Phase8UseCaseTestBase):
    def testForeignTenantCannotReadConversationOrMessages(self) -> None:
        with asUser(self.tenantB.id, self.foreign.id):
            with self.assertRaises(EntityNotFoundError):
                container.listMessagesUseCase().execute(
                    ListMessagesQuery(conversationId=str(self.conversation.id))
                )
            with self.assertRaises(EntityNotFoundError):
                container.editMessageUseCase().execute(
                    EditMessageCommand(messageId=str(self.message.id), body="hacked")
                )

    def testDirectConversationRefusesForeignPeer(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            with self.assertRaises(EntityNotFoundError):
                container.createDirectUseCase().execute(
                    CreateDirectConversationCommand(peerUserId=str(self.foreign.id))
                )


# §38 scenario 3 — duplicate messages -------------------------------------------


class DuplicateMessageTests(Phase8UseCaseTestBase):
    def testClientRequestIdMakesRetryIdempotent(self) -> None:
        key = f"retry-{uuid.uuid4()}"
        first = self.sendAs(self.admin, "offline retry", )
        with asUser(self.tenantA.id, self.admin.id):
            again = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=str(self.conversation.id),
                    body="offline retry",
                    clientRequestId=key,
                )
            )
            third = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=str(self.conversation.id),
                    body="offline retry",
                    clientRequestId=key,
                )
            )
        self.assertEqual(again.id, third.id)
        self.assertNotEqual(first.id, again.id)

    def testDuplicateDirectConversationReturnsExisting(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            first = container.createDirectUseCase().execute(
                CreateDirectConversationCommand(peerUserId=str(self.member.id))
            )
            second = container.createDirectUseCase().execute(
                CreateDirectConversationCommand(peerUserId=str(self.member.id))
            )
        self.assertEqual(first.id, second.id)

    def testDuplicateChannelCodeRejected(self) -> None:
        from apps.sharedKernel.domain.errors import DuplicateIdentifierError

        with asUser(self.tenantA.id, self.admin.id):
            container.createChannelUseCase().execute(
                CreateChannelCommand(name="اخبار", code="news", visibility="PUBLIC")
            )
            with self.assertRaises(DuplicateIdentifierError):
                container.createChannelUseCase().execute(
                    CreateChannelCommand(name="دیگر", code="news", visibility="PUBLIC")
                )


# §38 scenario 4 — duplicate participants -----------------------------------------


class DuplicateParticipantTests(Phase8UseCaseTestBase):
    def testIdenticalAddIsIdempotentRetry(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            first = container.addParticipantUseCase().execute(
                AddParticipantCommand(
                    conversationId=str(self.conversation.id),
                    userId=str(self.outsider.id),
                )
            )
            second = container.addParticipantUseCase().execute(
                AddParticipantCommand(
                    conversationId=str(self.conversation.id),
                    userId=str(self.outsider.id),
                )
            )
        self.assertEqual(first.id, second.id)

    def testConflictingRoleAddRejected(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            with self.assertRaises(ConflictError):
                container.addParticipantUseCase().execute(
                    AddParticipantCommand(
                        conversationId=str(self.conversation.id),
                        userId=str(self.member.id),
                        role="MODERATOR",
                    )
                )

    def testOwnerCannotLeaveWithoutTransfer(self) -> None:
        from apps.sharedKernel.domain.errors import BusinessRuleViolationError

        with asUser(self.tenantA.id, self.admin.id):
            with self.assertRaises(BusinessRuleViolationError):
                container.leaveConversationUseCase().execute(
                    LeaveConversationCommand(conversationId=str(self.conversation.id))
                )

    def testOwnershipTransferBlockedViaChangeRole(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            with self.assertRaises(PermissionDeniedError):
                container.changeParticipantRoleUseCase().execute(
                    ChangeParticipantRoleCommand(
                        conversationId=str(self.conversation.id),
                        userId=str(self.member.id),
                        role="OWNER",
                    )
                )


# §38 scenario 5 — invalid meeting state ---------------------------------------------


class MeetingStateTests(Phase8UseCaseTestBase):
    def createMeeting(self):
        with asUser(self.tenantA.id, self.admin.id):
            return container.createMeetingUseCase().execute(
                CreateMeetingCommand(
                    conversationId=str(self.conversation.id),
                    title="جلسه بررسی",
                    inviteeIds=[str(self.member.id)],
                )
            )

    def testJoinCancelledMeetingRejected(self) -> None:
        meeting = self.createMeeting()
        with asUser(self.tenantA.id, self.admin.id):
            container.cancelMeetingUseCase().execute(
                __import__(
                    "apps.communication.application.commands.communicationCommands",
                    fromlist=["CancelMeetingCommand"],
                ).CancelMeetingCommand(meetingId=str(meeting.id))
            )
        with asUser(self.tenantA.id, self.member.id):
            with self.assertRaises(ConflictError):
                container.joinMeetingUseCase().execute(
                    JoinMeetingCommand(meetingId=str(meeting.id))
                )

    def testEndTwiceRejected(self) -> None:
        meeting = self.createMeeting()
        with asUser(self.tenantA.id, self.admin.id):
            container.startMeetingUseCase().execute(
                StartMeetingCommand(meetingId=str(meeting.id))
            )
            container.endMeetingUseCase().execute(
                EndMeetingCommand(meetingId=str(meeting.id))
            )
            with self.assertRaises(Exception):
                container.endMeetingUseCase().execute(
                    EndMeetingCommand(meetingId=str(meeting.id))
                )

    def testMeetingsAreIdempotentByClientRequestId(self) -> None:
        key = f"meeting-{uuid.uuid4()}"
        with asUser(self.tenantA.id, self.admin.id):
            first = container.createMeetingUseCase().execute(
                CreateMeetingCommand(
                    conversationId=str(self.conversation.id),
                    title="جلسه",
                    inviteeIds=[],
                    clientRequestId=key,
                )
            )
            second = container.createMeetingUseCase().execute(
                CreateMeetingCommand(
                    conversationId=str(self.conversation.id),
                    title="جلسه",
                    inviteeIds=[],
                    clientRequestId=key,
                )
            )
        self.assertEqual(first.id, second.id)


# §38 scenario 6 — unauthorized recording ----------------------------------------------


class RecordingAuthorizationTests(Phase8UseCaseTestBase):
    def testStartRequiresPermission(self) -> None:
        meeting = None
        with asUser(self.tenantA.id, self.admin.id):
            meeting = container.createMeetingUseCase().execute(
                CreateMeetingCommand(
                    conversationId=str(self.conversation.id),
                    title="جلسه ضبط",
                )
            )
            container.startMeetingUseCase().execute(
                StartMeetingCommand(meetingId=str(meeting.id))
            )
        with asUser(self.tenantA.id, self.member.id):  # no recording.manage
            with self.assertRaises(PermissionDeniedError):
                container.startRecordingUseCase().execute(
                    StartRecordingCommand(meetingId=str(meeting.id))
                )

    def testRecordingNonLiveMeetingRejected(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            meeting = container.createMeetingUseCase().execute(
                CreateMeetingCommand(conversationId=str(self.conversation.id), title="غیرفعال")
            )
            with self.assertRaises(ConflictError):
                container.startRecordingUseCase().execute(
                    StartRecordingCommand(meetingId=str(meeting.id))
                )


# §38 scenario 7 — call authorization -----------------------------------------------------


class CallAuthorizationTests(Phase8UseCaseTestBase):
    def testNonMemberCannotAcceptCall(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            call = container.startCallUseCase().execute(
                StartCallCommand(conversationId=str(self.conversation.id), mediaType="AUDIO")
            )
        with asUser(self.tenantA.id, self.outsider.id):
            with self.assertRaises(PermissionDeniedError):
                container.acceptCallUseCase().execute(AcceptCallCommand(callId=str(call.id)))

    def testCallIdempotency(self) -> None:
        key = f"call-{uuid.uuid4()}"
        with asUser(self.tenantA.id, self.admin.id):
            first = container.startCallUseCase().execute(
                StartCallCommand(
                    conversationId=str(self.conversation.id),
                    mediaType="AUDIO",
                    clientRequestId=key,
                )
            )
            second = container.startCallUseCase().execute(
                StartCallCommand(
                    conversationId=str(self.conversation.id),
                    mediaType="AUDIO",
                    clientRequestId=key,
                )
            )
        self.assertEqual(first.id, second.id)

    def testSignalingRequiresCallLeg(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            call = container.startCallUseCase().execute(
                StartCallCommand(conversationId=str(self.conversation.id), mediaType="VIDEO")
            )
        with asUser(self.tenantA.id, self.outsider.id):
            with self.assertRaises(PermissionDeniedError):
                container.relaySignalUseCase().execute(
                    RelaySignalCommand(envelope=_envelope(str(call.id)))
                )
        self.assertGreater(
            communicationMetrics().snapshot()["failedSignalingRequests"], 0  # §39
        )


# §38 scenario 8 — edit authorization ------------------------------------------------------


class EditAuthorizationTests(Phase8UseCaseTestBase):
    def testOnlySenderWithinWindowMayEdit(self) -> None:
        with asUser(self.tenantA.id, self.member.id):
            with self.assertRaises(PermissionDeniedError):
                container.editMessageUseCase().execute(
                    EditMessageCommand(messageId=str(self.message.id), body="تغییر")
                )

    def testWindowExpiryRejected(self) -> None:
        from apps.communication.infrastructure.repositories import (
            communicationRepositoriesImpl as impl,
        )

        target = self.sendAs(self.member, "پیام قدیمی")
        # age the message beyond the 15-minute window (§33)
        impl.MessageModel.objects.filter(id=target.id).update(
            createdAt=datetime.now(UTC) - timedelta(minutes=20)
        )
        with asUser(self.tenantA.id, self.member.id):  # sender, not moderator
            with self.assertRaises(PermissionDeniedError):
                container.editMessageUseCase().execute(
                    EditMessageCommand(messageId=str(target.id), body="دیر")
                )

    def testModeratorElevatedEdit(self) -> None:
        target = self.sendAs(self.member, "پیام عضو")
        with asUser(self.tenantA.id, self.admin.id):  # OWNER is moderating
            dto = container.editMessageUseCase().execute(
                EditMessageCommand(messageId=str(target.id), body="ویرایش مدیر")
            )
        self.assertTrue(dto.editedAt)


# §38 scenario 9 — delete authorization -----------------------------------------------------


class DeleteAuthorizationTests(Phase8UseCaseTestBase):
    def testMemberCannotDeleteOthersMessage(self) -> None:
        with asUser(self.tenantA.id, self.member.id):
            with self.assertRaises(PermissionDeniedError):
                container.deleteMessageUseCase().execute(
                    DeleteMessageCommand(messageId=str(self.message.id))
                )

    def testSenderSoftDeletesOwnMessage(self) -> None:
        target = self.sendAs(self.member, "پیام من")
        with asUser(self.tenantA.id, self.member.id):
            container.deleteMessageUseCase().execute(
                DeleteMessageCommand(messageId=str(target.id))
            )
        page = None
        with asUser(self.tenantA.id, self.admin.id):
            page = container.listMessagesUseCase().execute(
                ListMessagesQuery(conversationId=str(self.conversation.id))
            )
        deleted = [item for item in page.items if item.id == target.id][0]
        self.assertTrue(deleted.deleted)
        self.assertEqual(deleted.body, "")  # §34 — withheld from transport


# §38 scenario 10 — event delivery failure ------------------------------------------------------


class EventDeliveryFailureTests(Phase8UseCaseTestBase):
    def testOutboxRowStaysPendingWhenDispatcherFails(self) -> None:
        from apps.sharedKernel.infrastructure.djangoPorts import (
            InProcessEventDispatcher,
        )

        # a broken dispatcher must leave committed rows PENDING (§29/§38)
        with asUser(self.tenantA.id, self.admin.id):
            with mock.patch.object(
                InProcessEventDispatcher,
                "dispatch",
                side_effect=RuntimeError("broker down"),
            ):
                with self.assertRaises(RuntimeError):
                    container.sendMessageUseCase().execute(
                        SendMessageCommand(
                            conversationId=str(self.conversation.id), body="رویداد"
                        )
                    )
        pending = OutboxModel.objects.filter(publishedAt__isnull=True).count()
        self.assertGreater(pending, 0)  # failure → row stays PENDING (§29/§38)

        # a dispatcher outage must not lose the row either
        dispatcher = container.outboxDispatcher()
        broken = mock.Mock()
        broken.dispatch.side_effect = RuntimeError("broker down")
        original = dispatcher.eventDispatcher
        dispatcher.eventDispatcher = broken
        result = dispatcher.dispatchDue()
        dispatcher.eventDispatcher = original
        self.assertGreater(result["failed"], 0)
        self.assertGreater(
            OutboxModel.objects.filter(publishedAt__isnull=True).count(), 0
        )

        # once healthy again the rows drain
        healthy = container.outboxDispatcher().dispatchDue()
        self.assertGreater(healthy["published"], 0)
        self.assertEqual(OutboxModel.objects.filter(publishedAt__isnull=True).count(), 0)


# extra §38-adjacent behaviour ------------------------------------------------------


class ChannelsAndPresenceTests(Phase8UseCaseTestBase):
    def testPublicChannelSelfJoin(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            channel = container.createChannelUseCase().execute(
                CreateChannelCommand(name="اعلام", code="announcements", visibility="PUBLIC")
            )
        with asUser(self.tenantA.id, self.outsider.id):
            joined = container.joinChannelUseCase().execute(
                JoinChannelCommand(conversationId=str(channel.id))
            )
            listing = container.listConversationsUseCase().execute(
                ListConversationsQuery()
            )
        self.assertTrue(joined.role)
        self.assertIn(str(channel.id), [item.id for item in listing])

    def testPresenceSetAndBulkGet(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            container.updatePresenceUseCase().execute(
                UpdatePresenceCommand(status="DO_NOT_DISTURB")
            )
            result = container.getPresenceUseCase().execute(
                PresenceQuery(userIds=f"{self.admin.id},{self.member.id}")
            )
        self.assertEqual(result["presence"][str(self.admin.id)], "DO_NOT_DISTURB")
        self.assertEqual(result["presence"][str(self.member.id)], "OFFLINE")

    def testSearchRestrictedToMembership(self) -> None:
        self.sendAs(self.admin, "کیلیدواژه ویژه")
        with asUser(self.tenantA.id, self.member.id):
            hits = container.searchMessagesUseCase().execute(
                SearchMessagesQuery(query="کیلیدواژه")
            )
        self.assertTrue(hits)
        with asUser(self.tenantB.id, self.foreign.id):
            hits = container.searchMessagesUseCase().execute(
                SearchMessagesQuery(query="کیلیدواژه")
            )
        self.assertEqual(hits, [])

    def testArchiveHidesFromDefaultListing(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            container.archiveConversationUseCase().execute(
                ArchiveConversationCommand(conversationId=str(self.conversation.id))
            )
            listing = container.listConversationsUseCase().execute(
                ListConversationsQuery()
            )
            withArchived = container.listConversationsUseCase().execute(
                ListConversationsQuery(includeArchived=True)
            )
        self.assertNotIn(str(self.conversation.id), [item.id for item in listing])
        self.assertIn(str(self.conversation.id), [item.id for item in withArchived])


class LettersAndPinsTests(Phase8UseCaseTestBase):
    def testLetterLifecycleWithApprovals(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            letter = container.createLetterUseCase().execute(
                CreateLetterCommand(
                    recipientId=str(self.member.id), subject="ابلاد رسمی", body="متن"
                )
            )
            self.assertRegex(letter.referenceNumber, r"^\d{4}-\d{6}$")
            inReview = container.letterTransitionUseCase().execute(
                SubmitLetterCommand(letterId=str(letter.id))
            )
            from apps.communication.application.commands.communicationCommands import (
                ApproveLetterCommand,
            )

            container.letterTransitionUseCase().execute(
                ApproveLetterCommand(letterId=str(letter.id))
            )
            signed = container.letterTransitionUseCase().execute(
                SignLetterCommand(letterId=str(letter.id))
            )
        self.assertEqual(inReview.letterStatus, "IN_REVIEW")
        self.assertEqual(signed.letterStatus, "SIGNED")

    def testLetterRequiresPermission(self) -> None:
        with asUser(self.tenantA.id, self.member.id):
            with self.assertRaises(PermissionDeniedError):
                container.createLetterUseCase().execute(
                    CreateLetterCommand(
                        recipientId=str(self.admin.id), subject="بدون مجوز"
                    )
                )

    def testModeratorPinsMessage(self) -> None:
        with asUser(self.tenantA.id, self.admin.id):
            pin = container.pinMessageUseCase().execute(
                PinMessageCommand(
                    conversationId=str(self.conversation.id),
                    messageId=str(self.message.id),
                )
            )
            with self.assertRaises(ConflictError):
                container.pinMessageUseCase().execute(  # duplicate pin
                    PinMessageCommand(
                        conversationId=str(self.conversation.id),
                        messageId=str(self.message.id),
                    )
                )

        self.assertEqual(pin.messageId, self.message.id)


class ReadReceiptTests(Phase8UseCaseTestBase):
    def testBulkReadUpToWatermark(self) -> None:
        second = self.sendAs(self.admin, "پیام دوم")
        with asUser(self.tenantA.id, self.member.id):
            result = container.markConversationReadUseCase().execute(
                MarkConversationReadCommand(
                    conversationId=str(self.conversation.id),
                    uptoMessageId=str(second.id),
                )
            )
        self.assertGreaterEqual(result["messagesUpdated"], 1)
