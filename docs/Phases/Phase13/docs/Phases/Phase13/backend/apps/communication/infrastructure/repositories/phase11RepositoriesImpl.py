"""Phase 11 Django repository implementations.

Thin ORM <-> domain mappers. Every query is scoped by ``tenantId`` so no data
leaks across tenants (§4). No business logic lives here (§79).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from apps.communication.domain.entities import phase11Records as d
from apps.communication.infrastructure.models import (
    ActionItemCandidateModel,
    CommunicationPolicyModel,
    LegalHoldModel,
    MeetingRoomModel,
    MeetingSessionModel,
    MeetingSummaryModel,
    MessageDeliveryModel,
    MessageReportModel,
    OfficialMessageModel,
    ScreenShareSessionModel,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# CommunicationPolicy (§70)
# ---------------------------------------------------------------------------


class CommunicationPolicyRepositoryDjango:
    def getForTenant(self, tenantId: uuid.UUID) -> d.CommunicationPolicy | None:
        model = CommunicationPolicyModel.objects.filter(tenantId=tenantId).first()
        return self.toDomain(model) if model else None

    def save(self, policy: d.CommunicationPolicy) -> None:
        CommunicationPolicyModel.objects.update_or_create(
            tenantId=policy.tenantId,
            defaults={
                "id": policy.id,
                "messageRetentionDays": policy.messageRetentionDays,
                "recordingRetentionDays": policy.recordingRetentionDays,
                "transcriptRetentionDays": policy.transcriptRetentionDays,
                "presenceRetentionDays": policy.presenceRetentionDays,
                "auditRetentionDays": policy.auditRetentionDays,
                "maxAttachmentSize": policy.maxAttachmentSize,
                "maxMessageLength": policy.maxMessageLength,
                "maxGroupMembers": policy.maxGroupMembers,
                "maxMeetingParticipants": policy.maxMeetingParticipants,
                "allowedFileTypes": list(policy.allowedFileTypes),
                "allowExternalUsers": policy.allowExternalUsers,
                "allowRecording": policy.allowRecording,
                "allowScreenSharing": policy.allowScreenSharing,
                "allowMessageEdit": policy.allowMessageEdit,
                "allowMessageDelete": policy.allowMessageDelete,
                "updatedAt": policy.updatedAt or _now(),
            },
        )

    @staticmethod
    def toDomain(model: CommunicationPolicyModel) -> d.CommunicationPolicy:
        return d.CommunicationPolicy(
            id=model.id,
            tenantId=model.tenantId,
            messageRetentionDays=model.messageRetentionDays,
            recordingRetentionDays=model.recordingRetentionDays,
            transcriptRetentionDays=model.transcriptRetentionDays,
            presenceRetentionDays=model.presenceRetentionDays,
            auditRetentionDays=model.auditRetentionDays,
            maxAttachmentSize=model.maxAttachmentSize,
            maxMessageLength=model.maxMessageLength,
            maxGroupMembers=model.maxGroupMembers,
            maxMeetingParticipants=model.maxMeetingParticipants,
            allowedFileTypes=tuple(model.allowedFileTypes or ()),
            allowExternalUsers=model.allowExternalUsers,
            allowRecording=model.allowRecording,
            allowScreenSharing=model.allowScreenSharing,
            allowMessageEdit=model.allowMessageEdit,
            allowMessageDelete=model.allowMessageDelete,
            updatedAt=model.updatedAt,
        )


# ---------------------------------------------------------------------------
# MessageDelivery (§19)
# ---------------------------------------------------------------------------


class MessageDeliveryRepositoryDjango:
    def get(
        self, tenantId: uuid.UUID, messageId: uuid.UUID, recipientId: uuid.UUID
    ) -> d.MessageDelivery | None:
        model = MessageDeliveryModel.objects.filter(
            tenantId=tenantId, messageId=messageId, recipientId=recipientId
        ).first()
        return self.toDomain(model) if model else None

    def save(self, delivery: d.MessageDelivery) -> None:
        MessageDeliveryModel.objects.update_or_create(
            messageId=delivery.messageId,
            recipientId=delivery.recipientId,
            defaults={
                "id": delivery.id,
                "tenantId": delivery.tenantId,
                "deliveryState": delivery.state,
                "failedReason": delivery.failedReason,
                "deliveredAt": delivery.deliveredAt,
                "updatedAt": delivery.updatedAt or _now(),
            },
        )

    def listForMessage(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> list[d.MessageDelivery]:
        return [
            self.toDomain(m)
            for m in MessageDeliveryModel.objects.filter(
                tenantId=tenantId, messageId=messageId
            )
        ]

    @staticmethod
    def toDomain(model: MessageDeliveryModel) -> d.MessageDelivery:
        return d.MessageDelivery(
            id=model.id,
            tenantId=model.tenantId,
            messageId=model.messageId,
            recipientId=model.recipientId,
            state=model.deliveryState,
            failedReason=model.failedReason,
            deliveredAt=model.deliveredAt,
            updatedAt=model.updatedAt,
        )


# ---------------------------------------------------------------------------
# MeetingRoom / MeetingSession (§34)
# ---------------------------------------------------------------------------


class MeetingRoomRepositoryDjango:
    def findByMeeting(self, tenantId: uuid.UUID, meetingId: uuid.UUID) -> d.MeetingRoom | None:
        model = MeetingRoomModel.objects.filter(
            tenantId=tenantId, meetingId=meetingId, isActive=True
        ).first()
        return self._roomToDomain(model) if model else None

    def getById(self, tenantId: uuid.UUID, roomId: uuid.UUID) -> d.MeetingRoom | None:
        model = MeetingRoomModel.objects.filter(tenantId=tenantId, id=roomId).first()
        return self._roomToDomain(model) if model else None

    def save(self, room: d.MeetingRoom) -> None:
        MeetingRoomModel.objects.create(
            id=room.id,
            tenantId=room.tenantId,
            meetingId=room.meetingId,
            roomRef=room.roomRef,
            capacity=room.capacity,
            isActive=room.isActive,
            createdAt=room.createdAt or _now(),
        )

    def saveSession(self, session: d.MeetingSession) -> None:
        MeetingSessionModel.objects.update_or_create(
            id=session.id,
            defaults={
                "tenantId": session.tenantId,
                "meetingId": session.meetingId,
                "roomId": session.roomId,
                "sequence": session.sequence,
                "sessionStatus": session.status,
                "participantCount": session.participantCount,
                "startedAt": session.startedAt,
                "endedAt": session.endedAt,
            },
        )

    def listSessions(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[d.MeetingSession]:
        return [
            d.MeetingSession(
                id=m.id,
                tenantId=m.tenantId,
                meetingId=m.meetingId,
                roomId=m.roomId,
                sequence=m.sequence,
                status=m.sessionStatus,
                startedAt=m.startedAt,
                endedAt=m.endedAt,
                participantCount=m.participantCount,
            )
            for m in MeetingSessionModel.objects.filter(
                tenantId=tenantId, meetingId=meetingId
            ).order_by("sequence")
        ]

    @staticmethod
    def _roomToDomain(model: MeetingRoomModel) -> d.MeetingRoom:
        return d.MeetingRoom(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            roomRef=model.roomRef,
            capacity=model.capacity,
            isActive=model.isActive,
            createdAt=model.createdAt,
        )


# ---------------------------------------------------------------------------
# ScreenShareSession (§35)
# ---------------------------------------------------------------------------


class ScreenShareRepositoryDjango:
    def activeForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[d.ScreenShareSession]:
        return [
            d.ScreenShareSession(
                id=m.id,
                tenantId=m.tenantId,
                meetingId=m.meetingId,
                sharerId=m.sharerId,
                shareKind=m.shareKind,
                sessionId=m.sessionId,
                status=m.shareStatus,
                startedAt=m.startedAt,
                endedAt=m.endedAt,
            )
            for m in ScreenShareSessionModel.objects.filter(
                tenantId=tenantId, meetingId=meetingId, shareStatus="ACTIVE"
            )
        ]

    def save(self, share: d.ScreenShareSession) -> None:
        ScreenShareSessionModel.objects.create(
            id=share.id,
            tenantId=share.tenantId,
            meetingId=share.meetingId,
            sessionId=share.sessionId,
            sharerId=share.sharerId,
            shareKind=share.shareKind,
            shareStatus=share.status,
            startedAt=share.startedAt,
            endedAt=share.endedAt,
        )


# ---------------------------------------------------------------------------
# MeetingSummary (§38)
# ---------------------------------------------------------------------------


class MeetingSummaryRepositoryDjango:
    def findForMeeting(self, tenantId: uuid.UUID, meetingId: uuid.UUID) -> d.MeetingSummary | None:
        model = MeetingSummaryModel.objects.filter(
            tenantId=tenantId, meetingId=meetingId
        ).order_by("-generatedAt").first()
        return self.toDomain(model) if model else None

    def getById(self, tenantId: uuid.UUID, summaryId: uuid.UUID) -> d.MeetingSummary | None:
        model = MeetingSummaryModel.objects.filter(tenantId=tenantId, id=summaryId).first()
        return self.toDomain(model) if model else None

    def save(self, summary: d.MeetingSummary) -> None:
        MeetingSummaryModel.objects.update_or_create(
            id=summary.id,
            defaults={
                "tenantId": summary.tenantId,
                "meetingId": summary.meetingId,
                "transcriptId": summary.transcriptId,
                "summary": summary.summary,
                "keyPoints": list(summary.keyPoints),
                "decisions": list(summary.decisions),
                "actionItems": list(summary.actionItems),
                "risks": list(summary.risks),
                "topics": list(summary.topics),
                "confidence": summary.confidence,
                "modelReference": summary.modelReference,
                "humanReviewStatus": summary.humanReviewStatus,
                "reviewedBy": summary.reviewedBy,
                "generatedAt": summary.generatedAt or _now(),
            },
        )

    @staticmethod
    def toDomain(model: MeetingSummaryModel) -> d.MeetingSummary:
        return d.MeetingSummary(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            transcriptId=model.transcriptId,
            summary=model.summary,
            keyPoints=tuple(model.keyPoints or ()),
            decisions=tuple(model.decisions or ()),
            actionItems=tuple(model.actionItems or ()),
            risks=tuple(model.risks or ()),
            topics=tuple(model.topics or ()),
            confidence=model.confidence,
            modelReference=model.modelReference,
            humanReviewStatus=model.humanReviewStatus,
            reviewedBy=model.reviewedBy,
            generatedAt=model.generatedAt,
        )


# ---------------------------------------------------------------------------
# ActionItemCandidate (§39)
# ---------------------------------------------------------------------------


class ActionItemRepositoryDjango:
    def save(self, item: d.ActionItemCandidate) -> None:
        ActionItemCandidateModel.objects.update_or_create(
            id=item.id,
            defaults={
                "tenantId": item.tenantId,
                "meetingId": item.meetingId,
                "summaryId": item.summaryId,
                "title": item.title,
                "description": item.description,
                "suggestedAssigneeId": item.suggestedAssigneeId,
                "confidence": item.confidence,
                "candidateState": item.state,
                "reviewNote": item.reviewNote,
                "dispatchedItemRef": item.dispatchedItemRef,
                "reviewedBy": item.reviewedBy,
            },
        )

    def getById(self, tenantId: uuid.UUID, itemId: uuid.UUID) -> d.ActionItemCandidate | None:
        model = ActionItemCandidateModel.objects.filter(tenantId=tenantId, id=itemId).first()
        return self.toDomain(model) if model else None

    def listForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[d.ActionItemCandidate]:
        return [
            self.toDomain(m)
            for m in ActionItemCandidateModel.objects.filter(
                tenantId=tenantId, meetingId=meetingId
            )
        ]

    def listPending(
        self, tenantId: uuid.UUID, *, limit: int = 50
    ) -> list[d.ActionItemCandidate]:
        return [
            self.toDomain(m)
            for m in ActionItemCandidateModel.objects.filter(
                tenantId=tenantId, candidateState="CANDIDATE"
            ).order_by("createdAt")[:limit]
        ]

    @staticmethod
    def toDomain(model: ActionItemCandidateModel) -> d.ActionItemCandidate:
        return d.ActionItemCandidate(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            title=model.title,
            summaryId=model.summaryId,
            description=model.description,
            suggestedAssigneeId=model.suggestedAssigneeId,
            confidence=model.confidence,
            state=model.candidateState,
            reviewNote=model.reviewNote,
            dispatchedItemRef=model.dispatchedItemRef,
            createdAt=model.createdAt,
            reviewedBy=model.reviewedBy,
        )


# ---------------------------------------------------------------------------
# OfficialMessage (§40/§41)
# ---------------------------------------------------------------------------


class OfficialMessageRepositoryDjango:
    def save(self, message: d.OfficialMessage) -> None:
        OfficialMessageModel.objects.update_or_create(
            id=message.id,
            defaults={
                "tenantId": message.tenantId,
                "officialKind": message.kind,
                "subject": message.subject,
                "body": message.body,
                "authorId": message.authorId,
                "officialStatus": message.status,
                "recipientIds": [str(x) for x in message.recipientIds],
                "acknowledgedBy": [str(x) for x in message.acknowledgedBy],
                "publishedAt": message.publishedAt,
                "updatedAt": message.updatedAt or _now(),
            },
        )

    def getById(self, tenantId: uuid.UUID, officialId: uuid.UUID) -> d.OfficialMessage | None:
        model = OfficialMessageModel.objects.filter(tenantId=tenantId, id=officialId).first()
        return self.toDomain(model) if model else None

    def list(
        self, tenantId: uuid.UUID, *, status: str = "", limit: int = 50
    ) -> list[d.OfficialMessage]:
        qs = OfficialMessageModel.objects.filter(tenantId=tenantId)
        if status:
            qs = qs.filter(officialStatus=status)
        return [self.toDomain(m) for m in qs.order_by("-createdAt")[:limit]]

    @staticmethod
    def toDomain(model: OfficialMessageModel) -> d.OfficialMessage:
        return d.OfficialMessage(
            id=model.id,
            tenantId=model.tenantId,
            kind=model.officialKind,
            subject=model.subject,
            body=model.body,
            authorId=model.authorId,
            status=model.officialStatus,
            recipientIds=tuple(uuid.UUID(x) for x in (model.recipientIds or [])),
            acknowledgedBy=tuple(uuid.UUID(x) for x in (model.acknowledgedBy or [])),
            publishedAt=model.publishedAt,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )


# ---------------------------------------------------------------------------
# MessageReport (§43/§44)
# ---------------------------------------------------------------------------


class MessageReportRepositoryDjango:
    def save(self, report: d.MessageReport) -> None:
        MessageReportModel.objects.update_or_create(
            id=report.id,
            defaults={
                "tenantId": report.tenantId,
                "messageId": report.messageId,
                "reportedById": report.reportedById,
                "reason": report.reason,
                "description": report.description,
                "reportStatus": report.status,
                "reviewedById": report.reviewedById,
                "reviewedAt": report.reviewedAt,
                "resolutionNote": report.resolutionNote,
            },
        )

    def getById(self, tenantId: uuid.UUID, reportId: uuid.UUID) -> d.MessageReport | None:
        model = MessageReportModel.objects.filter(tenantId=tenantId, id=reportId).first()
        return self.toDomain(model) if model else None

    def list(
        self, tenantId: uuid.UUID, *, status: str = "", limit: int = 50
    ) -> list[d.MessageReport]:
        qs = MessageReportModel.objects.filter(tenantId=tenantId)
        if status:
            qs = qs.filter(reportStatus=status)
        return [self.toDomain(m) for m in qs.order_by("-createdAt")[:limit]]

    @staticmethod
    def toDomain(model: MessageReportModel) -> d.MessageReport:
        return d.MessageReport(
            id=model.id,
            tenantId=model.tenantId,
            messageId=model.messageId,
            reportedById=model.reportedById,
            reason=model.reason,
            description=model.description,
            status=model.reportStatus,
            reviewedById=model.reviewedById,
            reviewedAt=model.reviewedAt,
            resolutionNote=model.resolutionNote,
            createdAt=model.createdAt,
        )


# ---------------------------------------------------------------------------
# LegalHold (§69)
# ---------------------------------------------------------------------------


class LegalHoldRepositoryDjango:
    def save(self, hold: d.LegalHold) -> None:
        LegalHoldModel.objects.create(
            id=hold.id,
            tenantId=hold.tenantId,
            holdScope=hold.scope,
            targetId=hold.targetId,
            reason=hold.reason,
            holdStatus=hold.status,
            createdById=hold.createdById,
            createdAt=hold.createdAt or _now(),
            releasedAt=hold.releasedAt,
        )

    def activeFor(
        self, tenantId: uuid.UUID, scope: str, targetId: uuid.UUID
    ) -> d.LegalHold | None:
        model = LegalHoldModel.objects.filter(
            tenantId=tenantId, holdScope=scope, targetId=targetId, holdStatus="ACTIVE"
        ).first()
        return self.toDomain(model) if model else None

    def listActiveForTarget(
        self, tenantId: uuid.UUID, targetId: uuid.UUID
    ) -> list[d.LegalHold]:
        return [
            self.toDomain(m)
            for m in LegalHoldModel.objects.filter(
                tenantId=tenantId, targetId=targetId, holdStatus="ACTIVE"
            )
        ]

    @staticmethod
    def toDomain(model: LegalHoldModel) -> d.LegalHold:
        return d.LegalHold(
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
