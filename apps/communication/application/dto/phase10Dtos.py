"""Phase 10 DTOs + domain->DTO mappers."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.communication.domain.entities.phase10Records import (
    MeetingTranscript,
    MessageRevision,
    TranscriptSegment,
    UserBlock,
)


@dataclass(frozen=True)
class MessageRevisionDto:
    id: str
    messageId: str
    revisionNumber: int
    editedBy: str
    editedAt: str
    previousBody: str
    newBody: str


@dataclass(frozen=True)
class TranscriptSegmentDto:
    sequence: int
    speakerId: str
    startTimeSeconds: float
    endTimeSeconds: float
    text: str
    confidence: float


@dataclass(frozen=True)
class TranscriptDto:
    id: str
    meetingId: str
    language: str
    status: str
    segmentCount: int
    contentReference: str = ""
    segments: list[TranscriptSegmentDto] = field(default_factory=list)


@dataclass(frozen=True)
class UserBlockDto:
    id: str
    blockerId: str
    blockedUserId: str
    scopes: list[str]
    status: str
    reason: str = ""


@dataclass(frozen=True)
class MeetingCapabilityDto:
    meetingId: str
    userId: str
    capability: str
    granted: bool
    source: str  # ROLE | OVERRIDE


@dataclass(frozen=True)
class CallSessionDto:
    provider: str
    sessionRef: str
    mediaType: str
    transport: str = "webrtc-signaling"


def revisionDtoFromDomain(revision: MessageRevision) -> MessageRevisionDto:
    return MessageRevisionDto(
        id=str(revision.id),
        messageId=str(revision.messageId),
        revisionNumber=revision.revisionNumber,
        editedBy=str(revision.editedBy),
        editedAt=revision.editedAt.isoformat(),
        previousBody=revision.previousBody,
        newBody=revision.newBody,
    )


def segmentDtoFromDomain(segment: TranscriptSegment) -> TranscriptSegmentDto:
    return TranscriptSegmentDto(
        sequence=segment.sequence,
        speakerId=str(segment.speakerId) if segment.speakerId else "",
        startTimeSeconds=segment.startTimeSeconds,
        endTimeSeconds=segment.endTimeSeconds,
        text=segment.text,
        confidence=segment.confidence,
    )


def transcriptDtoFromDomain(
    transcript: MeetingTranscript,
    segments: list[TranscriptSegment] | None = None,
) -> TranscriptDto:
    return TranscriptDto(
        id=str(transcript.id),
        meetingId=str(transcript.meetingId),
        language=transcript.language,
        status=transcript.transcriptStatus,
        segmentCount=transcript.segmentCount,
        contentReference=transcript.contentReference,
        segments=[segmentDtoFromDomain(s) for s in (segments or [])],
    )


def blockDtoFromDomain(block: UserBlock) -> UserBlockDto:
    return UserBlockDto(
        id=str(block.id),
        blockerId=str(block.blockerId),
        blockedUserId=str(block.blockedUserId),
        scopes=list(block.scopes),
        status=block.blockStatus,
        reason=block.reason,
    )
