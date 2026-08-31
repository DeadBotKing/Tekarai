"""Phase 10 domain aggregates: message revision history, meeting transcript
(+ segments) and user blocks.

These records extend the Phase 08 communication context with the capabilities
Phase 10 (``docs/Phases/Phase10.md``) adds:

- ``MessageRevision`` (§11) — every message edit keeps the previous body, so
  compliance/audit can reconstruct what was said; the message itself only
  carries ``editedAt``.
- ``MeetingTranscript`` + ``TranscriptSegment`` (§34/§35) — the transcript is
  independent of the recording; segments carry speaker/time/text/confidence
  and are what the AI meeting-summary use case consumes (§36/§37).
- ``UserBlock`` (§70) — a user blocks another user for direct messages, calls
  and meeting invitations; enforced by the communication policies.

All aggregates are framework-free (no Django/Redis/ORM imports).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.phase10Types import (
    BLOCK_ACTIVE,
    BLOCK_SCOPES,
    MAX_SEGMENT_CONFIDENCE,
    MIN_SEGMENT_CONFIDENCE,
    TRANSCRIPT_PROCESSING,
    TRANSCRIPT_READY,
    TRANSCRIPT_STATES,
    TRANSCRIPT_TRANSITIONS,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    InvalidStateTransitionError,
    ValidationFailedError,
)

PREVIOUS_BODY_MAX = 8000


class MessageRevision(AggregateRoot):
    """§11 — an immutable record of one message edit.

    The row captures the body *before* the edit plus who/when; revisions are
    append-only (never updated or deleted by normal behaviour), which gives
    the enterprise compliance trail the spec requires.
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        conversationId: uuid.UUID,
        previousBody: str,
        newBody: str,
        editedBy: uuid.UUID,
        editedAt: datetime,
        revisionNumber: int,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.messageId = messageId
        self.conversationId = conversationId
        self.previousBody = previousBody
        self.newBody = newBody
        self.editedBy = editedBy
        self.editedAt = editedAt
        self.revisionNumber = revisionNumber

    @staticmethod
    def record(
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        conversationId: uuid.UUID,
        previousBody: str,
        newBody: str,
        editedBy: uuid.UUID,
        now: datetime,
        revisionNumber: int,
    ) -> MessageRevision:
        if revisionNumber < 1:
            raise ValidationFailedError(
                "Revision number must start at 1.",
                fieldErrors={"revisionNumber": str(revisionNumber)},
            )
        if len(previousBody) > PREVIOUS_BODY_MAX or len(newBody) > PREVIOUS_BODY_MAX:
            raise ValidationFailedError(
                "Revision body is too long.", fieldErrors={"body": f"max {PREVIOUS_BODY_MAX}"}
            )
        return MessageRevision(
            id=newId(),
            tenantId=tenantId,
            messageId=messageId,
            conversationId=conversationId,
            previousBody=previousBody,
            newBody=newBody,
            editedBy=editedBy,
            editedAt=now,
            revisionNumber=revisionNumber,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "messageId": str(self.messageId),
            "revisionNumber": self.revisionNumber,
            "editedBy": str(self.editedBy),
            "editedAt": self.editedAt.isoformat(),
            "previousBody": self.previousBody,
            "newBody": self.newBody,
        }


class TranscriptSegment(AggregateRoot):
    """§35 — one timed, attributed slice of a transcript."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        transcriptId: uuid.UUID,
        sequence: int,
        speakerId: uuid.UUID | None,
        startTimeSeconds: float,
        endTimeSeconds: float,
        text: str,
        confidence: float,
    ) -> None:
        super().__init__(id)
        if endTimeSeconds < startTimeSeconds:
            raise ValidationFailedError(
                "Segment end must not precede start.",
                fieldErrors={"endTimeSeconds": str(endTimeSeconds)},
            )
        if not (MIN_SEGMENT_CONFIDENCE <= confidence <= MAX_SEGMENT_CONFIDENCE):
            raise ValidationFailedError(
                "Segment confidence out of range.",
                fieldErrors={"confidence": str(confidence)},
            )
        if not text.strip():
            raise ValidationFailedError(
                "Segment text is required.", fieldErrors={"text": "empty"}
            )
        self.tenantId = tenantId
        self.transcriptId = transcriptId
        self.sequence = sequence
        self.speakerId = speakerId
        self.startTimeSeconds = startTimeSeconds
        self.endTimeSeconds = endTimeSeconds
        self.text = text.strip()
        self.confidence = confidence

    def snapshot(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "speakerId": str(self.speakerId) if self.speakerId else "",
            "startTimeSeconds": self.startTimeSeconds,
            "endTimeSeconds": self.endTimeSeconds,
            "text": self.text,
            "confidence": self.confidence,
        }


class MeetingTranscript(AggregateRoot):
    """§34 — the transcript aggregate; independent of the recording.

    Content (the heavy text) is referenced, not stored, via
    ``contentReference``; the aggregate owns lifecycle and the segment index
    that feeds AI analysis (§36).
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        language: str,
        createdAt: datetime,
        *,
        transcriptStatus: str = "PENDING",
        contentReference: str = "",
        updatedAt: datetime | None = None,
        segmentCount: int = 0,
    ) -> None:
        super().__init__(id)
        if transcriptStatus not in TRANSCRIPT_STATES:
            raise ValidationFailedError(
                "Unknown transcript status.",
                fieldErrors={"transcriptStatus": transcriptStatus},
            )
        if not language.strip() or len(language) > 10:
            raise ValidationFailedError(
                "Language is required (BCP-47 style, e.g. fa-IR).",
                fieldErrors={"language": language},
            )
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.language = language.strip()
        self.createdAt = createdAt
        self.transcriptStatus = transcriptStatus
        self.contentReference = contentReference
        self.updatedAt = updatedAt or createdAt
        self.segmentCount = segmentCount

    @staticmethod
    def request(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        requestedBy: uuid.UUID,
        language: str,
        now: datetime,
    ) -> MeetingTranscript:
        transcript = MeetingTranscript(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            language=language,
            createdAt=now,
        )
        transcript.recordEvent(
            DomainEvent(
                name="transcriptRequested",
                occurredAt=now,
                tenantId=tenantId,
                actorId=requestedBy,
                payload={"meetingId": str(meetingId)},
            )
        )
        return transcript

    def transitionTo(self, target: str, now: datetime, *, contentReference: str = "") -> None:
        allowed = TRANSCRIPT_TRANSITIONS.get(self.transcriptStatus, ())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Transcript cannot move {self.transcriptStatus} → {target}."
            )
        self.transcriptStatus = target
        self.updatedAt = now
        if target == TRANSCRIPT_READY:
            if not contentReference:
                raise ValidationFailedError(
                    "A READY transcript requires a content reference.",
                    fieldErrors={"contentReference": "empty"},
                )
            self.contentReference = contentReference
        eventName = {
            TRANSCRIPT_PROCESSING: "transcriptProcessing",
            TRANSCRIPT_READY: "transcriptReady",
            "FAILED": "transcriptFailed",
        }.get(target, "transcriptUpdated")
        self.recordEvent(
            DomainEvent(name=eventName, occurredAt=now, tenantId=self.tenantId)
        )

    def applySegmentCount(self, count: int) -> None:
        if count < 0:
            raise ValidationFailedError(
                "Segment count cannot be negative.", fieldErrors={"segmentCount": str(count)}
            )
        self.segmentCount = count

    def isReady(self) -> bool:
        return self.transcriptStatus == TRANSCRIPT_READY

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "meetingId": str(self.meetingId),
            "language": self.language,
            "status": self.transcriptStatus,
            "segmentCount": self.segmentCount,
            "contentReference": self.contentReference,
        }


class UserBlock(AggregateRoot):
    """§70 — a user blocks another user across communication channels.

    Blocks are per-tenant and directional (blocker → blocked). A block applies
    to a set of scopes (direct message / call / meeting invitation); an
    organizational policy may override, but by default the block stands.
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        blockerId: uuid.UUID,
        blockedUserId: uuid.UUID,
        scopes: tuple[str, ...],
        createdAt: datetime,
        *,
        reason: str = "",
        blockStatus: str = BLOCK_ACTIVE,
        removedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if blockerId == blockedUserId:
            raise BusinessRuleViolationError(
                "A user cannot block themselves.", ruleId="PHASE10-BR_NoSelfBlock"
            )
        for scope in scopes:
            if scope not in BLOCK_SCOPES:
                raise ValidationFailedError(
                    "Unknown block scope.", fieldErrors={"scope": scope}
                )
        if not scopes:
            raise ValidationFailedError(
                "At least one block scope is required.",
                fieldErrors={"scopes": "empty"},
            )
        self.tenantId = tenantId
        self.blockerId = blockerId
        self.blockedUserId = blockedUserId
        self.scopes = tuple(sorted(set(scopes)))
        self.reason = reason[:300]
        self.createdAt = createdAt
        self.blockStatus = blockStatus
        self.removedAt = removedAt

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        blockerId: uuid.UUID,
        blockedUserId: uuid.UUID,
        scopes: tuple[str, ...],
        now: datetime,
        *,
        reason: str = "",
    ) -> UserBlock:
        block = UserBlock(
            id=newId(),
            tenantId=tenantId,
            blockerId=blockerId,
            blockedUserId=blockedUserId,
            scopes=scopes,
            createdAt=now,
            reason=reason,
        )
        block.recordEvent(
            DomainEvent(
                name="userBlocked",
                occurredAt=now,
                tenantId=tenantId,
                actorId=blockerId,
                payload={"blockedUserId": str(blockedUserId), "scopes": list(block.scopes)},
            )
        )
        return block

    def lift(self, now: datetime) -> None:
        if self.blockStatus != BLOCK_ACTIVE:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Block is already lifted.")
        self.blockStatus = "REMOVED"
        self.removedAt = now
        self.recordEvent(
            DomainEvent(
                name="userBlockLifted",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.blockerId,
                payload={"blockedUserId": str(self.blockedUserId)},
            )
        )

    def isActive(self) -> bool:
        return self.blockStatus == BLOCK_ACTIVE

    def covers(self, scope: str) -> bool:
        return self.isActive() and scope in self.scopes

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "blockerId": str(self.blockerId),
            "blockedUserId": str(self.blockedUserId),
            "scopes": list(self.scopes),
            "status": self.blockStatus,
        }
