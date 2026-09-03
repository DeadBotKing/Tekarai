"""Phase 11 application use cases — Enterprise Communication governance.

Covers: tenant CommunicationPolicy (§70), delivery receipts (§19), meeting
room/session separation (§34), screen-share sessions (§35), AI-governed meeting
summary + action item candidates with human approval (§38/§39/§77), formal
OfficialMessage lifecycle (§40/§41), moderation MessageReport (§43/§44) and
LegalHold (§69). Business rules live in the domain entities; these use cases
only orchestrate (validate -> authorize -> apply -> persist -> events).
"""

from __future__ import annotations

import uuid

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
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
)
from apps.communication.domain.entities import phase11Records as records
from apps.communication.domain.repositories.communicationRepositories import (
    MeetingRepository,
    MessageRepository,
)
from apps.communication.domain.repositories.phase11Repositories import (
    ActionItemRepository,
    CommunicationPolicyRepository,
    LegalHoldRepository,
    MeetingRoomRepository,
    MeetingSummaryRepository,
    MessageDeliveryRepository,
    MessageReportRepository,
    OfficialMessageRepository,
    ScreenShareRepository,
)
from apps.communication.domain.valueObjects import phase11Types as types
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    EntityNotFoundError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


def _actor():
    from apps.sharedKernel.application.requestContext import currentContext

    context = currentContext()
    return asUuid(context.actorId), asUuid(context.actorTenantId)


# ---------------------------------------------------------------------------
# CommunicationPolicy (§70)
# ---------------------------------------------------------------------------


class GetCommunicationPolicyUseCase(
    CommunicationUseCase[object, records.CommunicationPolicy]
):
    requiredAction = ""

    def __init__(self, policyRepository: CommunicationPolicyRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.policyRepository = policyRepository

    def perform(self, command: object) -> records.CommunicationPolicy:
        _actorId, tenantId = _actor()
        policy = self.policyRepository.getForTenant(tenantId)
        return policy or records.CommunicationPolicy.default(tenantId)


class UpdateCommunicationPolicyUseCase(
    CommunicationUseCase[UpdateCommunicationPolicyCommand, records.CommunicationPolicy]
):
    requiredAction = "conversation.moderate"

    def __init__(self, policyRepository: CommunicationPolicyRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.policyRepository = policyRepository

    def perform(self, command: UpdateCommunicationPolicyCommand) -> records.CommunicationPolicy:
        _actorId, tenantId = _actor()
        policy = self.policyRepository.getForTenant(tenantId) or records.CommunicationPolicy.default(tenantId)
        policy.update(command.changes, self.clock.nowUtc())
        self.policyRepository.save(policy)
        self.collectEventsFrom(policy)
        self.audit(
            "UPDATE",
            "CommunicationPolicy",
            str(tenantId),
            tenantId,
            after={"keys": sorted(command.changes.keys())},
        )
        return policy


# ---------------------------------------------------------------------------
# MessageDelivery (§19)
# ---------------------------------------------------------------------------


class RecordDeliveryUseCase(CommunicationUseCase[RecordDeliveryCommand, dict]):
    requiredAction = ""

    def __init__(
        self,
        deliveryRepository: MessageDeliveryRepository,
        messageRepository: MessageRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.deliveryRepository = deliveryRepository
        self.messageRepository = messageRepository

    def perform(self, command: RecordDeliveryCommand) -> dict:
        _actorId, tenantId = _actor()
        messageId = asUuid(command.messageId)
        recipientId = asUuid(command.recipientId)
        message = self.messageRepository.getById(messageId, tenantId)  # noqa: E501
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        delivery = self.deliveryRepository.get(tenantId, messageId, recipientId) or records.MessageDelivery.mark(
            tenantId, messageId, recipientId
        )
        now = self.clock.nowUtc()
        if command.state == types.DELIVERY_DELIVERED:
            delivery.markDelivered(now)
        elif command.state == types.DELIVERY_FAILED:
            delivery.markFailed(now, command.failedReason)
        self.deliveryRepository.save(delivery)
        self.collectEventsFrom(delivery)
        return {"messageId": str(messageId), "recipientId": str(recipientId), "state": delivery.state}


# ---------------------------------------------------------------------------
# MeetingRoom / MeetingSession (§34)
# ---------------------------------------------------------------------------


class OpenMeetingRoomUseCase(CommunicationUseCase[OpenMeetingRoomCommand, records.MeetingRoom]):
    requiredAction = "meeting.manage"

    def __init__(
        self,
        roomRepository: MeetingRoomRepository,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.roomRepository = roomRepository
        self.meetingRepository = meetingRepository

    def perform(self, command: OpenMeetingRoomCommand) -> records.MeetingRoom:
        _actorId, tenantId = _actor()
        meetingId = asUuid(command.meetingId)
        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        existing = self.roomRepository.findByMeeting(tenantId, meetingId)
        if existing is not None:
            return existing  # idempotent
        room = records.MeetingRoom.open(
            tenantId,
            meetingId,
            self.clock.nowUtc(),
            capacity=command.capacity or None,
        )
        self.roomRepository.save(room)
        self.collectEventsFrom(room)
        return room


class StartMeetingSessionUseCase(CommunicationUseCase[StartMeetingSessionCommand, records.MeetingSession]):
    requiredAction = "meeting.manage"

    def __init__(
        self,
        roomRepository: MeetingRoomRepository,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.roomRepository = roomRepository
        self.meetingRepository = meetingRepository

    def perform(self, command: StartMeetingSessionCommand) -> records.MeetingSession:
        _actorId, tenantId = _actor()
        meetingId = asUuid(command.meetingId)
        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        room = self.roomRepository.findByMeeting(tenantId, meetingId)
        if room is None:
            room = records.MeetingRoom.open(tenantId, meetingId, self.clock.nowUtc())
            self.roomRepository.save(room)
            self.collectEventsFrom(room)
        sessions = self.roomRepository.listSessions(tenantId, meetingId)
        sequence = len(sessions) + 1
        session = records.MeetingSession.start(
            tenantId, meetingId, room.id, sequence, self.clock.nowUtc()
        )
        self.roomRepository.saveSession(session)
        self.collectEventsFrom(session)
        return session


class EndMeetingSessionUseCase(CommunicationUseCase[EndMeetingSessionCommand, records.MeetingSession]):
    requiredAction = "meeting.manage"

    def __init__(self, roomRepository: MeetingRoomRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.roomRepository = roomRepository

    def perform(self, command: EndMeetingSessionCommand) -> records.MeetingSession:
        _actorId, tenantId = _actor()
        # sessions are keyed per meeting; find via listing across rooms is not
        # needed because end carries sessionId — look up through model-less
        # helper by scanning the meeting sessions: caller passes meeting via the
        # room repository search by session id through the ORM-backed list.
        session = self._findSession(tenantId, asUuid(command.sessionId))
        if session is None:
            raise EntityNotFoundError("MeetingSession", command.sessionId)
        session.end(self.clock.nowUtc())
        self.roomRepository.saveSession(session)
        self.collectEventsFrom(session)
        return session

    def _findSession(self, tenantId: uuid.UUID, sessionId: uuid.UUID) -> records.MeetingSession | None:
        from apps.communication.infrastructure.models import MeetingSessionModel

        model = MeetingSessionModel.objects.filter(tenantId=tenantId, id=sessionId).first()
        if model is None:
            return None
        return records.MeetingSession(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            roomId=model.roomId,
            sequence=model.sequence,
            status=model.sessionStatus,
            startedAt=model.startedAt,
            endedAt=model.endedAt,
            participantCount=model.participantCount,
        )


# ---------------------------------------------------------------------------
# Screen share (§35)
# ---------------------------------------------------------------------------


class StartScreenShareUseCase(CommunicationUseCase[StartScreenShareCommand, records.ScreenShareSession]):
    requiredAction = ""

    def __init__(
        self,
        screenShareRepository: ScreenShareRepository,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.screenShareRepository = screenShareRepository
        self.meetingRepository = meetingRepository

    def perform(self, command: StartScreenShareCommand) -> records.ScreenShareSession:
        actorId, tenantId = _actor()
        meetingId = asUuid(command.meetingId)
        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None or not meeting.isLive():
            raise BusinessRuleViolationError(
                "Screen share requires a live meeting.",
                ruleId="PHASE11-SCREEN_SHARE_NOT_LIVE",
            )
        share = records.ScreenShareSession.begin(
            tenantId,
            meetingId,
            actorId,
            command.shareKind,
            self.clock.nowUtc(),
            sessionId=asUuid(command.sessionId) if command.sessionId else None,
        )
        self.screenShareRepository.save(share)
        self.collectEventsFrom(share)
        return share


class StopScreenShareUseCase(CommunicationUseCase[StopScreenShareCommand, records.ScreenShareSession]):
    requiredAction = ""

    def __init__(self, screenShareRepository: ScreenShareRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.screenShareRepository = screenShareRepository

    def perform(self, command: StopScreenShareCommand) -> records.ScreenShareSession:
        _actorId, tenantId = _actor()
        from apps.communication.infrastructure.models import ScreenShareSessionModel

        model = ScreenShareSessionModel.objects.filter(
            tenantId=tenantId, id=asUuid(command.shareId)
        ).first()
        if model is None:
            raise EntityNotFoundError("ScreenShareSession", command.shareId)
        share = records.ScreenShareSession(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            sharerId=model.sharerId,
            shareKind=model.shareKind,
            sessionId=model.sessionId,
            status=model.shareStatus,
            startedAt=model.startedAt,
            endedAt=model.endedAt,
        )
        share.end(self.clock.nowUtc())
        # update the existing row's terminal state
        ScreenShareSessionModel.objects.filter(id=share.id).update(
            shareStatus=share.status, endedAt=share.endedAt
        )
        self.collectEventsFrom(share)
        return share


# ---------------------------------------------------------------------------
# MeetingSummary (§38) + ActionItemCandidate (§39)
# ---------------------------------------------------------------------------


class GenerateMeetingSummaryUseCase(
    CommunicationUseCase[GenerateMeetingSummaryCommand, records.MeetingSummary]
):
    """Persist an AI-produced summary. The AI pipeline runs OUTSIDE the domain;
    here we only validate and store the result with a PENDING human review."""

    requiredAction = "meeting.manage"

    def __init__(
        self,
        summaryRepository: MeetingSummaryRepository,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.summaryRepository = summaryRepository
        self.meetingRepository = meetingRepository

    def perform(self, command: GenerateMeetingSummaryCommand) -> records.MeetingSummary:
        _actorId, tenantId = _actor()
        meetingId = asUuid(command.meetingId)
        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        summary = records.MeetingSummary.generate(
            tenantId,
            meetingId,
            self.clock.nowUtc(),
            transcriptId=asUuid(command.transcriptId) if command.transcriptId else None,
            summary=command.summary,
            keyPoints=list(command.keyPoints),
            decisions=list(command.decisions),
            actionItems=list(command.actionItems),
            risks=list(command.risks),
            topics=list(command.topics),
            confidence=command.confidence,
            modelReference=command.modelReference,
        )
        self.summaryRepository.save(summary)
        self.collectEventsFrom(summary)
        self.emitIntegrationEvent(
            tenantId,
            "MeetingSummaryGenerated",
            {"meetingId": str(meetingId), "summaryId": str(summary.id)},
        )
        return summary


class ReviewMeetingSummaryUseCase(
    CommunicationUseCase[ReviewMeetingSummaryCommand, records.MeetingSummary]
):
    requiredAction = "meeting.manage"

    def __init__(self, summaryRepository: MeetingSummaryRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.summaryRepository = summaryRepository

    def perform(self, command: ReviewMeetingSummaryCommand) -> records.MeetingSummary:
        actorId, tenantId = _actor()
        summary = self.summaryRepository.getById(tenantId, asUuid(command.summaryId))
        if summary is None:
            raise EntityNotFoundError("MeetingSummary", command.summaryId)
        now = self.clock.nowUtc()
        if command.decision == "APPROVE":
            summary.approve(actorId, now)
        elif command.decision == "REJECT":
            summary.reject(actorId, now)
        else:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("decision must be APPROVE or REJECT",
                                        fieldErrors={"decision": command.decision})
        self.summaryRepository.save(summary)
        self.collectEventsFrom(summary)
        return summary


class ReviewActionItemUseCase(CommunicationUseCase[ReviewActionItemCommand, records.ActionItemCandidate]):
    requiredAction = "meeting.manage"

    def __init__(self, actionItemRepository: ActionItemRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.actionItemRepository = actionItemRepository

    def perform(self, command: ReviewActionItemCommand) -> records.ActionItemCandidate:
        actorId, tenantId = _actor()
        item = self.actionItemRepository.getById(tenantId, asUuid(command.itemId))
        if item is None:
            raise EntityNotFoundError("ActionItemCandidate", command.itemId)
        now = self.clock.nowUtc()
        if command.decision == "APPROVE":
            item.approve(actorId, now)
        elif command.decision == "REJECT":
            item.reject(actorId, now, command.note)
        else:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("decision must be APPROVE or REJECT",
                                        fieldErrors={"decision": command.decision})
        self.actionItemRepository.save(item)
        self.collectEventsFrom(item)
        return item


class DispatchActionItemUseCase(
    CommunicationUseCase[DispatchActionItemCommand, records.ActionItemCandidate]
):
    """Hand an APPROVED candidate to the work-management domain by reference (§39)."""

    requiredAction = "meeting.manage"

    def __init__(self, actionItemRepository: ActionItemRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.actionItemRepository = actionItemRepository

    def perform(self, command: DispatchActionItemCommand) -> records.ActionItemCandidate:
        _actorId, tenantId = _actor()
        item = self.actionItemRepository.getById(tenantId, asUuid(command.itemId))
        if item is None:
            raise EntityNotFoundError("ActionItemCandidate", command.itemId)
        item.markDispatched(command.taskRef)
        self.actionItemRepository.save(item)
        self.emitIntegrationEvent(
            tenantId,
            "ActionItemDispatched",
            {"itemId": str(item.id), "taskRef": command.taskRef},
        )
        return item


class ProposeActionItemFromSummaryUseCase:
    """Helper invoked by the AI pipeline to persist task candidates for a
    summary. Kept as a thin factory so the domain stays the owner of state."""

    @staticmethod
    def propose(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        summary: records.MeetingSummary,
        titles: list[str],
        now,
    ) -> list[records.ActionItemCandidate]:
        items = []
        for title in titles:
            items.append(
                records.ActionItemCandidate.propose(
                    tenantId,
                    meetingId,
                    title,
                    now,
                    summaryId=summary.id,
                    confidence=summary.confidence,
                )
            )
        return items


# ---------------------------------------------------------------------------
# OfficialMessage (§40/§41)
# ---------------------------------------------------------------------------


class CreateOfficialMessageUseCase(
    CommunicationUseCase[CreateOfficialMessageCommand, records.OfficialMessage]
):
    requiredAction = "letter.create"

    def __init__(self, officialRepository: OfficialMessageRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.officialRepository = officialRepository

    def perform(self, command: CreateOfficialMessageCommand) -> records.OfficialMessage:
        actorId, tenantId = _actor()
        message = records.OfficialMessage.draft(
            tenantId,
            actorId,
            command.kind,
            command.subject,
            command.body,
            self.clock.nowUtc(),
            recipientIds=tuple(asUuid(x) for x in command.recipientIds),
        )
        self.officialRepository.save(message)
        self.collectEventsFrom(message)
        self.audit("CREATE", "OfficialMessage", str(message.id), tenantId,
                  after={"kind": command.kind, "subject": command.subject})
        return message


class TransitionOfficialMessageUseCase(
    CommunicationUseCase[TransitionOfficialMessageCommand, records.OfficialMessage]
):
    requiredAction = "letter.approve"

    def __init__(self, officialRepository: OfficialMessageRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.officialRepository = officialRepository

    def perform(self, command: TransitionOfficialMessageCommand) -> records.OfficialMessage:
        actorId, tenantId = _actor()
        message = self.officialRepository.getById(tenantId, asUuid(command.officialId))
        if message is None:
            raise EntityNotFoundError("OfficialMessage", command.officialId)
        now = self.clock.nowUtc()
        action = command.action
        if action == "review":
            message.submitForReview(now)
        elif action == "approve":
            message.approve(actorId, now)
        elif action == "return":
            message.returnToDraft(actorId, now)
        elif action == "publish":
            message.publish(now)
            self.emitIntegrationEvent(
                tenantId, "OfficialMessagePublished", {"officialId": str(message.id)}
            )
        elif action == "deliver":
            message.markDelivered(now)
        else:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("unknown official action",
                                        fieldErrors={"action": action})
        self.officialRepository.save(message)
        self.collectEventsFrom(message)
        return message


class AcknowledgeOfficialMessageUseCase(
    CommunicationUseCase[AcknowledgeOfficialMessageCommand, records.OfficialMessage]
):
    requiredAction = ""

    def __init__(self, officialRepository: OfficialMessageRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.officialRepository = officialRepository

    def perform(self, command: AcknowledgeOfficialMessageCommand) -> records.OfficialMessage:
        actorId, tenantId = _actor()
        message = self.officialRepository.getById(tenantId, asUuid(command.officialId))
        if message is None:
            raise EntityNotFoundError("OfficialMessage", command.officialId)
        message.acknowledge(actorId, self.clock.nowUtc())
        self.officialRepository.save(message)
        self.collectEventsFrom(message)
        return message


# ---------------------------------------------------------------------------
# MessageReport (§43/§44)
# ---------------------------------------------------------------------------


class ReportMessageUseCase(CommunicationUseCase[ReportMessageCommand, records.MessageReport]):
    requiredAction = ""

    def __init__(
        self,
        reportRepository: MessageReportRepository,
        messageRepository: MessageRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.reportRepository = reportRepository
        self.messageRepository = messageRepository

    def perform(self, command: ReportMessageCommand) -> records.MessageReport:
        actorId, tenantId = _actor()
        messageId = asUuid(command.messageId)
        message = self.messageRepository.getById(messageId, tenantId)  # noqa: E501
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        report = records.MessageReport.open(
            tenantId, messageId, actorId, command.reason, self.clock.nowUtc(), command.description
        )
        self.reportRepository.save(report)
        self.collectEventsFrom(report)
        return report


class ReviewMessageReportUseCase(
    CommunicationUseCase[ReviewMessageReportCommand, records.MessageReport]
):
    requiredAction = "conversation.moderate"

    def __init__(self, reportRepository: MessageReportRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.reportRepository = reportRepository

    def perform(self, command: ReviewMessageReportCommand) -> records.MessageReport:
        actorId, tenantId = _actor()
        report = self.reportRepository.getById(tenantId, asUuid(command.reportId))
        if report is None:
            raise EntityNotFoundError("MessageReport", command.reportId)
        now = self.clock.nowUtc()
        if command.decision == "RESOLVE":
            report.resolve(actorId, now, command.note)
        elif command.decision == "DISMISS":
            report.dismiss(actorId, now, command.note)
        else:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("decision must be RESOLVE or DISMISS",
                                        fieldErrors={"decision": command.decision})
        self.reportRepository.save(report)
        self.collectEventsFrom(report)
        self.audit("UPDATE", "MessageReport", str(report.id), tenantId,
                  after={"decision": command.decision})
        return report


# ---------------------------------------------------------------------------
# LegalHold (§69)
# ---------------------------------------------------------------------------


class PlaceLegalHoldUseCase(CommunicationUseCase[PlaceLegalHoldCommand, records.LegalHold]):
    requiredAction = "conversation.moderate"

    def __init__(self, legalHoldRepository: LegalHoldRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.legalHoldRepository = legalHoldRepository

    def perform(self, command: PlaceLegalHoldCommand) -> records.LegalHold:
        actorId, tenantId = _actor()
        targetId = asUuid(command.targetId)
        existing = self.legalHoldRepository.activeFor(tenantId, command.scope, targetId)
        if existing is not None:
            return existing  # idempotent
        hold = records.LegalHold.place(
            tenantId, command.scope, targetId, self.clock.nowUtc(),
            reason=command.reason, createdById=actorId,
        )
        self.legalHoldRepository.save(hold)
        self.collectEventsFrom(hold)
        self.audit("CREATE", "LegalHold", str(hold.id), tenantId,
                  after={"scope": command.scope, "targetId": command.targetId})
        return hold


class ReleaseLegalHoldUseCase(
    CommunicationUseCase[ReleaseLegalHoldCommand, records.LegalHold]
):
    requiredAction = "conversation.moderate"

    def __init__(self, legalHoldRepository: LegalHoldRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.legalHoldRepository = legalHoldRepository

    def perform(self, command: ReleaseLegalHoldCommand) -> records.LegalHold:
        _actorId, tenantId = _actor()
        from apps.communication.infrastructure.models import LegalHoldModel

        model = LegalHoldModel.objects.filter(
            tenantId=tenantId, id=asUuid(command.holdId)
        ).first()
        if model is None:
            raise EntityNotFoundError("LegalHold", command.holdId)
        hold = records.LegalHold(
            id=model.id,
            tenantId=model.tenantId,
            scope=model.holdScope,
            targetId=model.targetId,
            reason=model.reason,
            status=model.holdStatus,
            createdById=model.createdById,
            createdAt=model.createdAt,
            releasedAt=model.releasedAt,
        )
        hold.release(self.clock.nowUtc())
        LegalHoldModel.objects.filter(id=hold.id).update(
            holdStatus=hold.status, releasedAt=hold.releasedAt
        )
        self.collectEventsFrom(hold)
        return hold


def retentionPurgeAllowed(
    legalHoldRepository: LegalHoldRepository,
    tenantId: uuid.UUID,
    scope: str,
    targetId: uuid.UUID,
) -> bool:
    """§69 — retention purges must skip resources under an active legal hold."""
    return legalHoldRepository.activeFor(tenantId, scope, targetId) is None
