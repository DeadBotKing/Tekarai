"""Django adapters for Phase 14 search, sync and retention ports."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.communication.infrastructure.models import (
    CommunicationRetentionRunModel,
    CommunicationSyncReceiptModel,
    ConversationModel,
    ConversationParticipantModel,
    LegalHoldModel,
    MeetingModel,
    MeetingParticipantModel,
    MeetingTranscriptModel,
    MessageAttachmentModel,
    MessageDeliveryModel,
    MessageMentionModel,
    MessageModel,
    MessageReactionModel,
    MessageReadStateModel,
    MessageReportModel,
    MessageRevisionModel,
    PinnedMessageModel,
    RecordingModel,
    TranscriptSegmentModel,
)
from apps.sharedKernel.domain.errors import ConflictError


class UnifiedCommunicationSearchDjango:
    """Permission-aware cross-aggregate search with hard tenant boundaries."""

    def search(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        conversationIds = list(
            ConversationParticipantModel.objects.filter(
                tenantId=tenantId, userId=userId, leftAt__isnull=True
            ).values_list("conversationId", flat=True)
        )
        meetingIds = set(
            MeetingParticipantModel.objects.filter(tenantId=tenantId, userId=userId).values_list(
                "meetingId", flat=True
            )
        )
        meetingIds.update(
            MeetingModel.objects.filter(
                tenantId=tenantId, conversationId__in=conversationIds
            ).values_list("id", flat=True)
        )
        results: list[dict[str, Any]] = []
        perScope = min(limit, 50)
        if "MESSAGES" in scopes:
            rows = MessageModel.objects.filter(
                tenantId=tenantId,
                conversationId__in=conversationIds,
                deletedAt__isnull=True,
                body__icontains=query,
            ).order_by("-createdAt")[:perScope]
            results.extend(
                {
                    "scope": "MESSAGES",
                    "id": str(row.id),
                    "conversationId": str(row.conversationId),
                    "title": row.body[:120],
                    "excerpt": row.body[:500],
                    "occurredAt": row.createdAt.isoformat(),
                }
                for row in rows
            )
        if "CONVERSATIONS" in scopes:
            rows = ConversationModel.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                tenantId=tenantId,
                id__in=conversationIds,
                isActive=True,
            ).order_by("-updatedAt")[:perScope]
            results.extend(
                {
                    "scope": "CONVERSATIONS",
                    "id": str(row.id),
                    "conversationId": str(row.id),
                    "title": row.name,
                    "excerpt": row.description,
                    "occurredAt": row.updatedAt.isoformat(),
                }
                for row in rows
            )
        if "CHANNELS" in scopes:
            rows = ConversationModel.objects.filter(
                Q(name__icontains=query) | Q(description__icontains=query),
                tenantId=tenantId,
                id__in=conversationIds,
                conversationType="CHANNEL",
                isActive=True,
            ).order_by("-updatedAt")[:perScope]
            results.extend(
                {
                    "scope": "CHANNELS",
                    "id": str(row.id),
                    "conversationId": str(row.id),
                    "title": row.name,
                    "excerpt": row.description,
                    "occurredAt": row.updatedAt.isoformat(),
                }
                for row in rows
            )
        if "ATTACHMENTS" in scopes:
            allowedMessageIds = MessageModel.objects.filter(
                tenantId=tenantId,
                conversationId__in=conversationIds,
                deletedAt__isnull=True,
            ).values("id")
            rows = MessageAttachmentModel.objects.filter(
                Q(fileName__icontains=query) | Q(documentRef__icontains=query),
                tenantId=tenantId,
                messageId__in=allowedMessageIds,
                scanStatus="CLEAN",
            ).order_by("-createdAt")[:perScope]
            results.extend(
                {
                    "scope": "ATTACHMENTS",
                    "id": str(row.id),
                    "messageId": str(row.messageId),
                    "title": row.fileName,
                    "excerpt": row.mimeType,
                    "occurredAt": row.createdAt.isoformat(),
                }
                for row in rows
            )
        if "MEETINGS" in scopes:
            rows = MeetingModel.objects.filter(
                Q(title__icontains=query) | Q(description__icontains=query),
                tenantId=tenantId,
                id__in=meetingIds,
            ).order_by("-createdAt")[:perScope]
            results.extend(
                {
                    "scope": "MEETINGS",
                    "id": str(row.id),
                    "conversationId": str(row.conversationId),
                    "title": row.title,
                    "excerpt": row.description,
                    "occurredAt": row.createdAt.isoformat(),
                }
                for row in rows
            )
        if "TRANSCRIPTS" in scopes:
            transcriptIds = MeetingTranscriptModel.objects.filter(
                tenantId=tenantId, meetingId__in=meetingIds, transcriptStatus="COMPLETED"
            ).values("id")
            rows = TranscriptSegmentModel.objects.filter(
                tenantId=tenantId, transcriptId__in=transcriptIds, text__icontains=query
            ).order_by("-createdAt")[:perScope]
            results.extend(
                {
                    "scope": "TRANSCRIPTS",
                    "id": str(row.id),
                    "transcriptId": str(row.transcriptId),
                    "title": f"Transcript segment {row.sequence}",
                    "excerpt": row.text[:500],
                    "occurredAt": row.createdAt.isoformat(),
                }
                for row in rows
            )
        # Stable global newest-first order, followed by a single global limit.
        results.sort(key=lambda item: (item["occurredAt"], item["scope"], item["id"]), reverse=True)
        return tuple(results[:limit])


class OfflineSyncReceiptStoreDjango:
    def find(
        self, tenantId: uuid.UUID, userId: uuid.UUID, clientBatchId: str
    ) -> tuple[str, dict[str, Any]] | None:
        row = CommunicationSyncReceiptModel.objects.filter(
            tenantId=tenantId, userId=userId, clientBatchId=clientBatchId
        ).first()
        return (row.requestHash, dict(row.result)) if row else None

    def save(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        clientBatchId: str,
        requestHash: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            row, created = CommunicationSyncReceiptModel.objects.get_or_create(
                tenantId=tenantId,
                userId=userId,
                clientBatchId=clientBatchId,
                defaults={"requestHash": requestHash, "result": result},
            )
        except IntegrityError:
            row = CommunicationSyncReceiptModel.objects.get(
                tenantId=tenantId, userId=userId, clientBatchId=clientBatchId
            )
            created = False
        if not created and row.requestHash != requestHash:
            raise ConflictError("The offline batch id is already bound to different operations.")
        return dict(row.result)


class CommunicationRetentionStoreDjango:
    """Purge expired metadata while excluding every active legal-hold path."""

    @transaction.atomic
    def sweep(
        self,
        tenantId: uuid.UUID,
        cutoff: datetime,
        requestedById: uuid.UUID,
        *,
        dryRun: bool,
    ) -> dict[str, int]:
        holds = LegalHoldModel.objects.filter(tenantId=tenantId, holdStatus="ACTIVE")
        heldConversations = holds.filter(holdScope="CONVERSATION").values("targetId")
        heldUsers = holds.filter(holdScope="USER").values("targetId")
        heldMeetings = holds.filter(holdScope="MEETING").values("targetId")
        heldRecordings = holds.filter(holdScope="RECORDING").values("targetId")
        heldTranscripts = holds.filter(holdScope="TRANSCRIPT").values("targetId")

        expiredMessages = (
            MessageModel.objects.filter(
                tenantId=tenantId, deletedAt__isnull=False, deletedAt__lt=cutoff
            )
            .exclude(conversationId__in=heldConversations)
            .exclude(senderId__in=heldUsers)
        )
        messageIds = list(expiredMessages.values_list("id", flat=True))

        expiredRecordings = (
            RecordingModel.objects.filter(tenantId=tenantId, createdAt__lt=cutoff)
            .exclude(meetingId__in=heldMeetings)
            .exclude(id__in=heldRecordings)
        )
        recordingIds = list(expiredRecordings.values_list("id", flat=True))

        expiredTranscripts = (
            MeetingTranscriptModel.objects.filter(tenantId=tenantId, createdAt__lt=cutoff)
            .exclude(meetingId__in=heldMeetings)
            .exclude(id__in=heldTranscripts)
        )
        transcriptIds = list(expiredTranscripts.values_list("id", flat=True))

        counts = {
            "messages": len(messageIds),
            "attachments": MessageAttachmentModel.objects.filter(
                tenantId=tenantId, messageId__in=messageIds
            ).count(),
            "recordings": len(recordingIds),
            "transcripts": len(transcriptIds),
            "transcriptSegments": TranscriptSegmentModel.objects.filter(
                tenantId=tenantId, transcriptId__in=transcriptIds
            ).count(),
        }
        if not dryRun:
            for model in (
                MessageAttachmentModel,
                MessageReactionModel,
                MessageMentionModel,
                MessageReadStateModel,
                MessageDeliveryModel,
                MessageRevisionModel,
                MessageReportModel,
                PinnedMessageModel,
            ):
                model.objects.filter(tenantId=tenantId, messageId__in=messageIds).delete()
            expiredMessages.delete()
            TranscriptSegmentModel.objects.filter(
                tenantId=tenantId, transcriptId__in=transcriptIds
            ).delete()
            expiredTranscripts.delete()
            expiredRecordings.delete()
        CommunicationRetentionRunModel.objects.create(
            tenantId=tenantId,
            requestedById=requestedById,
            dryRun=dryRun,
            status="COMPLETED",
            cutoff=cutoff,
            counts=counts,
        )
        return counts


__all__ = [
    "CommunicationRetentionStoreDjango",
    "OfflineSyncReceiptStoreDjango",
    "UnifiedCommunicationSearchDjango",
]
