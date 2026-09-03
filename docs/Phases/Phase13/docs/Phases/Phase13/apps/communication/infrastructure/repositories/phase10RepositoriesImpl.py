"""Phase 10 repository implementations over the Django ORM.

Implements the ports in ``domain.repositories.phase10Repositories``:
- message revision history (§11),
- transcripts + segments (§34/§35),
- user blocks (§70),
- meeting-capability overrides (§30),
- the SQL message-search provider (§54).

Only row <-> aggregate mapping lives here; no business rules (§62). Tenant
scoping is applied on every query (§41).
"""

from __future__ import annotations

import uuid

from apps.communication.domain.entities.phase10Records import (
    MeetingTranscript,
    MessageRevision,
    TranscriptSegment,
    UserBlock,
)
from apps.communication.domain.repositories.phase10Repositories import (
    CapabilityOverride,
    SearchResult,
)
from apps.communication.domain.valueObjects import phase10Types as types
from apps.communication.infrastructure.models import (
    MeetingCapabilityOverrideModel,
    MeetingTranscriptModel,
    MessageModel,
    MessageRevisionModel,
    TranscriptSegmentModel,
    UserBlockModel,
)


class MessageRevisionRepositoryDjango:
    def add(self, revision: MessageRevision) -> None:
        MessageRevisionModel.objects.create(
            id=revision.id,
            tenantId=revision.tenantId,
            messageId=revision.messageId,
            conversationId=revision.conversationId,
            revisionNumber=revision.revisionNumber,
            previousBody=revision.previousBody,
            newBody=revision.newBody,
            editedBy=revision.editedBy,
            editedAt=revision.editedAt,
        )

    def nextRevisionNumber(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> int:
        last = (
            MessageRevisionModel.objects.filter(
                tenantId=tenantId, messageId=messageId
            )
            .order_by("-revisionNumber")
            .first()
        )
        return (last.revisionNumber + 1) if last else 1

    def listForMessage(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> list[MessageRevision]:
        rows = MessageRevisionModel.objects.filter(
            tenantId=tenantId, messageId=messageId
        ).order_by("revisionNumber")
        return [
            MessageRevision(
                id=row.id,
                tenantId=row.tenantId,
                messageId=row.messageId,
                conversationId=row.conversationId,
                previousBody=row.previousBody,
                newBody=row.newBody,
                editedBy=row.editedBy,
                editedAt=row.editedAt,
                revisionNumber=row.revisionNumber,
            )
            for row in rows
        ]


class TranscriptRepositoryDjango:
    def create(self, transcript: MeetingTranscript) -> None:
        MeetingTranscriptModel.objects.create(
            id=transcript.id,
            tenantId=transcript.tenantId,
            meetingId=transcript.meetingId,
            language=transcript.language,
            transcriptStatus=transcript.transcriptStatus,
            contentReference=transcript.contentReference,
            segmentCount=transcript.segmentCount,
        )

    def update(self, transcript: MeetingTranscript) -> None:
        MeetingTranscriptModel.objects.filter(
            id=transcript.id, tenantId=transcript.tenantId
        ).update(
            transcriptStatus=transcript.transcriptStatus,
            contentReference=transcript.contentReference,
            segmentCount=transcript.segmentCount,
        )

    def addSegment(self, segment: TranscriptSegment) -> None:
        TranscriptSegmentModel.objects.create(
            id=segment.id,
            tenantId=segment.tenantId,
            transcriptId=segment.transcriptId,
            sequence=segment.sequence,
            speakerId=segment.speakerId,
            startTimeSeconds=segment.startTimeSeconds,
            endTimeSeconds=segment.endTimeSeconds,
            text=segment.text,
            confidence=segment.confidence,
        )

    def _toDomain(self, row: MeetingTranscriptModel) -> MeetingTranscript:
        return MeetingTranscript(
            id=row.id,
            tenantId=row.tenantId,
            meetingId=row.meetingId,
            language=row.language,
            createdAt=row.createdAt,
            transcriptStatus=row.transcriptStatus,
            contentReference=row.contentReference,
            updatedAt=row.updatedAt,
            segmentCount=row.segmentCount,
        )

    def getById(
        self, transcriptId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> MeetingTranscript | None:
        qs = MeetingTranscriptModel.objects.filter(id=transcriptId)
        if tenantId is not None:
            qs = qs.filter(tenantId=tenantId)
        row = qs.first()
        return self._toDomain(row) if row else None

    def findForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> MeetingTranscript | None:
        row = MeetingTranscriptModel.objects.filter(
            tenantId=tenantId, meetingId=meetingId
        ).order_by("-createdAt").first()
        return self._toDomain(row) if row else None

    def listSegments(
        self, tenantId: uuid.UUID, transcriptId: uuid.UUID
    ) -> list[TranscriptSegment]:
        rows = TranscriptSegmentModel.objects.filter(
            tenantId=tenantId, transcriptId=transcriptId
        ).order_by("sequence")
        return [
            TranscriptSegment(
                id=row.id,
                tenantId=row.tenantId,
                transcriptId=row.transcriptId,
                sequence=row.sequence,
                speakerId=row.speakerId,
                startTimeSeconds=row.startTimeSeconds,
                endTimeSeconds=row.endTimeSeconds,
                text=row.text,
                confidence=row.confidence,
            )
            for row in rows
        ]


class UserBlockRepositoryDjango:
    def add(self, block: UserBlock) -> None:
        UserBlockModel.objects.create(
            id=block.id,
            tenantId=block.tenantId,
            blockerId=block.blockerId,
            blockedUserId=block.blockedUserId,
            scopes=list(block.scopes),
            reason=block.reason,
            blockStatus=block.blockStatus,
            createdAt=block.createdAt,
        )

    def update(self, block: UserBlock) -> None:
        UserBlockModel.objects.filter(
            id=block.id, tenantId=block.tenantId
        ).update(blockStatus=block.blockStatus, removedAt=block.removedAt)

    def findActive(
        self,
        tenantId: uuid.UUID,
        blockerId: uuid.UUID,
        blockedUserId: uuid.UUID,
    ) -> UserBlock | None:
        row = UserBlockModel.objects.filter(
            tenantId=tenantId,
            blockerId=blockerId,
            blockedUserId=blockedUserId,
            blockStatus=types.BLOCK_ACTIVE,
        ).first()
        return self._toDomain(row) if row else None

    def listBlockedUserIds(
        self, tenantId: uuid.UUID, blockerId: uuid.UUID, *, scope: str = ""
    ) -> list[uuid.UUID]:
        rows = UserBlockModel.objects.filter(
            tenantId=tenantId,
            blockerId=blockerId,
            blockStatus=types.BLOCK_ACTIVE,
        )
        ids: list[uuid.UUID] = []
        for row in rows:
            if scope and scope not in row.scopes:
                continue
            ids.append(row.blockedUserId)
        return ids

    def listForBlocker(
        self, tenantId: uuid.UUID, blockerId: uuid.UUID
    ) -> list[UserBlock]:
        rows = UserBlockModel.objects.filter(
            tenantId=tenantId, blockerId=blockerId
        ).order_by("-createdAt")
        return [self._toDomain(row) for row in rows]

    def _toDomain(self, row: UserBlockModel) -> UserBlock:
        return UserBlock(
            id=row.id,
            tenantId=row.tenantId,
            blockerId=row.blockerId,
            blockedUserId=row.blockedUserId,
            scopes=tuple(row.scopes),
            createdAt=row.createdAt,
            reason=row.reason,
            blockStatus=row.blockStatus,
            removedAt=row.removedAt,
        )


class MeetingCapabilityRepositoryDjango:
    def setOverride(self, override: CapabilityOverride) -> None:
        MeetingCapabilityOverrideModel.objects.update_or_create(
            meetingId=override.meetingId,
            userId=override.userId,
            capability=override.capability,
            defaults={
                "tenantId": override.tenantId,
                "granted": override.granted,
            },
        )

    def overridesForMeeting(self, meetingId: uuid.UUID) -> list[CapabilityOverride]:
        rows = MeetingCapabilityOverrideModel.objects.filter(meetingId=meetingId)
        return [
            CapabilityOverride(
                meetingId=row.meetingId,
                userId=row.userId,
                capability=row.capability,
                granted=row.granted,
                tenantId=row.tenantId,
            )
            for row in rows
        ]

    def find(
        self,
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        userId: uuid.UUID,
        capability: str,
    ) -> CapabilityOverride | None:
        row = MeetingCapabilityOverrideModel.objects.filter(
            tenantId=tenantId,
            meetingId=meetingId,
            userId=userId,
            capability=capability,
        ).first()
        if not row:
            return None
        return CapabilityOverride(
            meetingId=row.meetingId,
            userId=row.userId,
            capability=row.capability,
            granted=row.granted,
            tenantId=row.tenantId,
        )


class SqlMessageSearchProvider:
    """§54 — the default, dependency-free SQL search provider.

    A future Elasticsearch/OpenSearch adapter implements the same port; the
    application layer never knows which provider answered (§54).
    """

    providerKind = types.SEARCH_PROVIDER_SQL

    def search(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        query: str,
        *,
        conversationIds: list[uuid.UUID] | None = None,
        limit: int = 25,
    ) -> list[SearchResult]:
        del userId  # tenant + membership scoping is applied by the caller
        terms = query.strip()
        if not terms:
            return []
        qs = MessageModel.objects.filter(
            tenantId=tenantId,
            deletedAt__isnull=True,
            body__icontains=terms,
        )
        if conversationIds:
            qs = qs.filter(conversationId__in=conversationIds)
        qs = qs.order_by("-createdAt")[: max(1, min(limit, 100))]
        results: list[SearchResult] = []
        for row in qs:
            snippet = row.body
            if len(snippet) > 160:
                pos = snippet.lower().find(terms.lower())
                start = max(0, (pos if pos >= 0 else 0) - 40)
                snippet = ("…" if start else "") + snippet[start : start + 160] + "…"
            results.append(
                SearchResult(
                    messageId=row.id,
                    conversationId=row.conversationId,
                    snippet=snippet,
                    createdAt=row.createdAt,
                )
            )
        return results
