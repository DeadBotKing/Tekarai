"""Phase 11 domain records — Enterprise Communication extensions.

Framework-free aggregates/entities (no Django/ORM), following the explicit
constructor style used by the Phase 08/10 records (each __init__ calls
``super().__init__(id)`` so the aggregate event buffer exists). These COMPLEMENT
the Phase 08/10 records without mutating them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.communication.domain.valueObjects import phase11Types as t
from apps.communication.domain.valueObjects.phase10Types import SCREEN_SHARE_KINDS
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError

# ---------------------------------------------------------------------------
# §70 CommunicationPolicy — tenant-level configuration (limits/retention).
# ---------------------------------------------------------------------------


class CommunicationPolicy(AggregateRoot):
    """Tenant-wide communication policy (one active row per tenant).

    Limits are NEVER read from hard-coded call sites (§46/§70/§79); use cases
    resolve the policy and fall back to PolicyDefaults when no row exists.
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        *,
        messageRetentionDays: int = t.DEFAULT_MESSAGE_RETENTION_DAYS,
        recordingRetentionDays: int = t.DEFAULT_RECORDING_RETENTION_DAYS,
        transcriptRetentionDays: int = t.DEFAULT_TRANSCRIPT_RETENTION_DAYS,
        presenceRetentionDays: int = t.DEFAULT_PRESENCE_RETENTION_DAYS,
        auditRetentionDays: int = t.DEFAULT_AUDIT_RETENTION_DAYS,
        maxAttachmentSize: int = t.DEFAULT_MAX_ATTACHMENT_SIZE,
        maxMessageLength: int = t.DEFAULT_MAX_MESSAGE_LENGTH,
        maxGroupMembers: int = t.DEFAULT_MAX_GROUP_MEMBERS,
        maxMeetingParticipants: int = t.DEFAULT_MAX_MEETING_PARTICIPANTS,
        allowedFileTypes: tuple[str, ...] = t.DEFAULT_ALLOWED_FILE_TYPES,
        allowExternalUsers: bool = False,
        allowRecording: bool = True,
        allowScreenSharing: bool = True,
        allowMessageEdit: bool = True,
        allowMessageDelete: bool = True,
        updatedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.messageRetentionDays = messageRetentionDays
        self.recordingRetentionDays = recordingRetentionDays
        self.transcriptRetentionDays = transcriptRetentionDays
        self.presenceRetentionDays = presenceRetentionDays
        self.auditRetentionDays = auditRetentionDays
        self.maxAttachmentSize = maxAttachmentSize
        self.maxMessageLength = maxMessageLength
        self.maxGroupMembers = maxGroupMembers
        self.maxMeetingParticipants = maxMeetingParticipants
        self.allowedFileTypes = tuple(allowedFileTypes)
        self.allowExternalUsers = allowExternalUsers
        self.allowRecording = allowRecording
        self.allowScreenSharing = allowScreenSharing
        self.allowMessageEdit = allowMessageEdit
        self.allowMessageDelete = allowMessageDelete
        self.updatedAt = updatedAt
        for name, value in (
            ("messageRetentionDays", self.messageRetentionDays),
            ("recordingRetentionDays", self.recordingRetentionDays),
            ("maxAttachmentSize", self.maxAttachmentSize),
            ("maxMessageLength", self.maxMessageLength),
            ("maxGroupMembers", self.maxGroupMembers),
            ("maxMeetingParticipants", self.maxMeetingParticipants),
        ):
            if not value or value <= 0:
                raise ValidationFailedError(
                    f"{name} must be positive.", fieldErrors={name: str(value)}
                )

    @staticmethod
    def default(tenantId: uuid.UUID) -> CommunicationPolicy:
        return CommunicationPolicy(id=newId(), tenantId=tenantId)

    def update(self, changes: dict, now: datetime) -> None:
        positive = {
            "messageRetentionDays", "recordingRetentionDays",
            "transcriptRetentionDays", "presenceRetentionDays",
            "auditRetentionDays", "maxAttachmentSize", "maxMessageLength",
            "maxGroupMembers", "maxMeetingParticipants",
        }
        for key, value in changes.items():
            if value is None or not hasattr(self, key):
                continue
            if key in positive and value <= 0:
                raise ValidationFailedError(
                    f"{key} must be positive.", fieldErrors={key: str(value)}
                )
            setattr(self, key, tuple(value) if key == "allowedFileTypes" else value)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="communicationPolicyUpdated",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"keys": sorted(changes.keys())},
            )
        )

    def snapshot(self) -> dict:
        return {
            "tenantId": str(self.tenantId),
            "messageRetentionDays": self.messageRetentionDays,
            "recordingRetentionDays": self.recordingRetentionDays,
            "transcriptRetentionDays": self.transcriptRetentionDays,
            "presenceRetentionDays": self.presenceRetentionDays,
            "auditRetentionDays": self.auditRetentionDays,
            "maxAttachmentSize": self.maxAttachmentSize,
            "maxMessageLength": self.maxMessageLength,
            "maxGroupMembers": self.maxGroupMembers,
            "maxMeetingParticipants": self.maxMeetingParticipants,
            "allowedFileTypes": list(self.allowedFileTypes),
            "allowExternalUsers": self.allowExternalUsers,
            "allowRecording": self.allowRecording,
            "allowScreenSharing": self.allowScreenSharing,
            "allowMessageEdit": self.allowMessageEdit,
            "allowMessageDelete": self.allowMessageDelete,
        }


# ---------------------------------------------------------------------------
# §19 MessageDelivery — per-recipient delivery receipt.
# ---------------------------------------------------------------------------


class MessageDelivery(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        recipientId: uuid.UUID,
        *,
        state: str = t.DELIVERY_SENT,
        failedReason: str = "",
        deliveredAt: datetime | None = None,
        updatedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(state, t.DELIVERY_STATES, field="deliveryState")
        self.tenantId = tenantId
        self.messageId = messageId
        self.recipientId = recipientId
        self.state = state
        self.failedReason = failedReason
        self.deliveredAt = deliveredAt
        self.updatedAt = updatedAt

    @staticmethod
    def mark(
        tenantId: uuid.UUID, messageId: uuid.UUID, recipientId: uuid.UUID
    ) -> MessageDelivery:
        return MessageDelivery(
            id=newId(), tenantId=tenantId, messageId=messageId, recipientId=recipientId
        )

    def _transition(self, target: str, now: datetime) -> None:
        if target not in t.DELIVERY_TRANSITIONS.get(self.state, ()):
            raise ConflictError(f"Cannot move delivery {self.state} -> {target}.")
        self.state = target
        self.updatedAt = now
        if target == t.DELIVERY_DELIVERED:
            self.deliveredAt = now
        self.recordEvent(
            DomainEvent(
                name="messageDelivered" if target == t.DELIVERY_DELIVERED else "messageDeliveryFailed",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.recipientId,
                payload={"messageId": str(self.messageId), "state": target},
            )
        )

    def markDelivered(self, now: datetime) -> None:
        self._transition(t.DELIVERY_DELIVERED, now)

    def markFailed(self, now: datetime, reason: str = "") -> None:
        self.failedReason = reason
        self._transition(t.DELIVERY_FAILED, now)


# ---------------------------------------------------------------------------
# §34 MeetingRoom / MeetingSession
# ---------------------------------------------------------------------------


class MeetingRoom(AggregateRoot):
    """A reusable room (definition) that hosts many sessions over time."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        roomRef: str,
        *,
        capacity: int = t.DEFAULT_MAX_MEETING_PARTICIPANTS,
        isActive: bool = True,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if not capacity or capacity <= 0:
            raise ValidationFailedError(
                "Room capacity must be positive.", fieldErrors={"capacity": str(capacity)}
            )
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.roomRef = roomRef
        self.capacity = capacity
        self.isActive = isActive
        self.createdAt = createdAt

    @staticmethod
    def open(
        tenantId: uuid.UUID, meetingId: uuid.UUID, now: datetime, *, capacity: int | None = None
    ) -> MeetingRoom:
        room = MeetingRoom(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            roomRef=f"room-{uuid.uuid4().hex[:12]}",
            capacity=capacity or t.DEFAULT_MAX_MEETING_PARTICIPANTS,
            createdAt=now,
        )
        room.recordEvent(
            DomainEvent(
                name="meetingRoomOpened",
                occurredAt=now,
                tenantId=tenantId,
                payload={"meetingId": str(meetingId), "roomRef": room.roomRef},
            )
        )
        return room

    def close(self, now: datetime) -> None:
        self.isActive = False
        self.recordEvent(
            DomainEvent(
                name="meetingRoomClosed",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"meetingId": str(self.meetingId)},
            )
        )


class MeetingSession(AggregateRoot):
    """A concrete live instance of a meeting within a room."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        roomId: uuid.UUID,
        sequence: int,
        *,
        status: str = t.SESSION_WAITING,
        startedAt: datetime | None = None,
        endedAt: datetime | None = None,
        participantCount: int = 0,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.roomId = roomId
        self.sequence = sequence
        self.status = status
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.participantCount = participantCount

    @staticmethod
    def start(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        roomId: uuid.UUID,
        sequence: int,
        now: datetime,
    ) -> MeetingSession:
        session = MeetingSession(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            roomId=roomId,
            sequence=sequence,
            status=t.SESSION_LIVE,
            startedAt=now,
        )
        session.recordEvent(
            DomainEvent(
                name="meetingSessionStarted",
                occurredAt=now,
                tenantId=tenantId,
                payload={"meetingId": str(meetingId), "sequence": sequence},
            )
        )
        return session

    def end(self, now: datetime) -> None:
        if self.status != t.SESSION_LIVE:
            raise ConflictError("Only a LIVE session can end.")
        self.status = t.SESSION_ENDED
        self.endedAt = now
        self.recordEvent(
            DomainEvent(
                name="meetingSessionEnded",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"meetingId": str(self.meetingId), "sequence": self.sequence},
            )
        )

    def fail(self, now: datetime) -> None:
        self.status = t.SESSION_FAILED
        self.endedAt = now


# ---------------------------------------------------------------------------
# §35 ScreenShareSession
# ---------------------------------------------------------------------------


class ScreenShareSession(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        sharerId: uuid.UUID,
        shareKind: str,
        *,
        sessionId: uuid.UUID | None = None,
        status: str = t.SCREEN_SHARE_ACTIVE,
        startedAt: datetime | None = None,
        endedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(shareKind, SCREEN_SHARE_KINDS, field="shareKind")
        t.validateOneOf(status, t.SCREEN_SHARE_STATES, field="screenShareStatus")
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.sharerId = sharerId
        self.shareKind = shareKind
        self.sessionId = sessionId
        self.status = status
        self.startedAt = startedAt
        self.endedAt = endedAt

    @staticmethod
    def begin(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        sharerId: uuid.UUID,
        shareKind: str,
        now: datetime,
        *,
        sessionId: uuid.UUID | None = None,
    ) -> ScreenShareSession:
        share = ScreenShareSession(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            sharerId=sharerId,
            shareKind=shareKind,
            sessionId=sessionId,
            startedAt=now,
        )
        share.recordEvent(
            DomainEvent(
                name="screenShareStarted",
                occurredAt=now,
                tenantId=tenantId,
                actorId=sharerId,
                payload={"meetingId": str(meetingId), "kind": shareKind},
            )
        )
        return share

    def end(self, now: datetime) -> None:
        if self.status != t.SCREEN_SHARE_ACTIVE:
            raise ConflictError("Screen share is not active.")
        self.status = t.SCREEN_SHARE_ENDED
        self.endedAt = now
        self.recordEvent(
            DomainEvent(
                name="screenShareStopped",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.sharerId,
                payload={"meetingId": str(self.meetingId)},
            )
        )


# ---------------------------------------------------------------------------
# §38 MeetingSummary — persisted, AI-governed output.
# ---------------------------------------------------------------------------


class MeetingSummary(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        *,
        transcriptId: uuid.UUID | None = None,
        summary: str = "",
        keyPoints: tuple[str, ...] = (),
        decisions: tuple[str, ...] = (),
        actionItems: tuple[str, ...] = (),
        risks: tuple[str, ...] = (),
        topics: tuple[str, ...] = (),
        confidence: float = 0.0,
        modelReference: str = "",
        humanReviewStatus: str = t.AI_REVIEW_PENDING,
        generatedAt: datetime | None = None,
        reviewedBy: uuid.UUID | None = None,
    ) -> None:
        super().__init__(id)
        if not (0.0 <= confidence <= 1.0):
            raise ValidationFailedError(
                "confidence must be within [0,1].", fieldErrors={"confidence": str(confidence)}
            )
        t.validateOneOf(humanReviewStatus, t.AI_REVIEW_STATES, field="humanReviewStatus")
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.transcriptId = transcriptId
        self.summary = summary
        self.keyPoints = tuple(keyPoints)
        self.decisions = tuple(decisions)
        self.actionItems = tuple(actionItems)
        self.risks = tuple(risks)
        self.topics = tuple(topics)
        self.confidence = confidence
        self.modelReference = modelReference
        self.humanReviewStatus = humanReviewStatus
        self.generatedAt = generatedAt
        self.reviewedBy = reviewedBy

    @staticmethod
    def generate(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        now: datetime,
        *,
        summary: str,
        keyPoints: list[str],
        decisions: list[str],
        actionItems: list[str],
        risks: list[str],
        topics: list[str],
        confidence: float,
        modelReference: str,
        transcriptId: uuid.UUID | None = None,
    ) -> MeetingSummary:
        record = MeetingSummary(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            transcriptId=transcriptId,
            summary=summary,
            keyPoints=tuple(keyPoints),
            decisions=tuple(decisions),
            actionItems=tuple(actionItems),
            risks=tuple(risks),
            topics=tuple(topics),
            confidence=confidence,
            modelReference=modelReference,
            humanReviewStatus=t.AI_REVIEW_PENDING,
            generatedAt=now,
        )
        record.recordEvent(
            DomainEvent(
                name="meetingSummaryGenerated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"meetingId": str(meetingId), "confidence": confidence},
            )
        )
        return record

    def approve(self, reviewerId: uuid.UUID, now: datetime) -> None:
        self.humanReviewStatus = t.AI_REVIEW_APPROVED
        self.reviewedBy = reviewerId
        self.recordEvent(
            DomainEvent(
                name="meetingSummaryApproved",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=reviewerId,
                payload={"meetingId": str(self.meetingId)},
            )
        )

    def reject(self, reviewerId: uuid.UUID, now: datetime) -> None:
        self.humanReviewStatus = t.AI_REVIEW_REJECTED
        self.reviewedBy = reviewerId


# ---------------------------------------------------------------------------
# §39 ActionItemCandidate — AI-extracted task candidate awaiting human approval.
# ---------------------------------------------------------------------------


class ActionItemCandidate(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        title: str,
        *,
        summaryId: uuid.UUID | None = None,
        description: str = "",
        suggestedAssigneeId: uuid.UUID | None = None,
        confidence: float = 0.0,
        state: str = t.ACTION_CANDIDATE,
        reviewNote: str = "",
        dispatchedItemRef: str = "",
        createdAt: datetime | None = None,
        reviewedBy: uuid.UUID | None = None,
    ) -> None:
        super().__init__(id)
        if not title.strip():
            raise ValidationFailedError("Action item title is required.", fieldErrors={"title": "empty"})
        if not (0.0 <= confidence <= 1.0):
            raise ValidationFailedError("confidence must be within [0,1].",
                                        fieldErrors={"confidence": str(confidence)})
        t.validateOneOf(state, t.ACTION_STATES, field="actionState")
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.summaryId = summaryId
        self.title = title.strip()
        self.description = description
        self.suggestedAssigneeId = suggestedAssigneeId
        self.confidence = confidence
        self.state = state
        self.reviewNote = reviewNote
        self.dispatchedItemRef = dispatchedItemRef
        self.createdAt = createdAt
        self.reviewedBy = reviewedBy

    @staticmethod
    def propose(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        title: str,
        now: datetime,
        *,
        summaryId: uuid.UUID | None = None,
        description: str = "",
        suggestedAssigneeId: uuid.UUID | None = None,
        confidence: float = 0.0,
    ) -> ActionItemCandidate:
        return ActionItemCandidate(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            summaryId=summaryId,
            title=title,
            description=description,
            suggestedAssigneeId=suggestedAssigneeId,
            confidence=confidence,
            createdAt=now,
        )

    def approve(self, reviewerId: uuid.UUID, now: datetime) -> None:
        if self.state != t.ACTION_CANDIDATE:
            raise ConflictError("Only a CANDIDATE can be approved.")
        self.state = t.ACTION_APPROVED
        self.reviewedBy = reviewerId

    def reject(self, reviewerId: uuid.UUID, now: datetime, note: str = "") -> None:
        if self.state != t.ACTION_CANDIDATE:
            raise ConflictError("Only a CANDIDATE can be rejected.")
        self.state = t.ACTION_REJECTED
        self.reviewedBy = reviewerId
        self.reviewNote = note

    def markDispatched(self, taskRef: str) -> None:
        """Record that an approved candidate was handed to the work-management domain.

        Communication only stores the reference; the work item itself is
        owned by the work-management domain (§39/§72).
        """
        if self.state != t.ACTION_APPROVED:
            raise ConflictError("Only an APPROVED candidate can be dispatched.")
        if not taskRef.strip():
            raise ValidationFailedError("taskRef is required.")
        self.state = t.ACTION_DISPATCHED
        self.dispatchedItemRef = taskRef


# ---------------------------------------------------------------------------
# §40/§41 OfficialMessage — formal communication with governed lifecycle.
# ---------------------------------------------------------------------------


class OfficialMessage(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        kind: str,
        subject: str,
        body: str,
        authorId: uuid.UUID,
        *,
        status: str = t.OFFICIAL_DRAFT,
        recipientIds: tuple[uuid.UUID, ...] = (),
        acknowledgedBy: tuple[uuid.UUID, ...] = (),
        publishedAt: datetime | None = None,
        createdAt: datetime | None = None,
        updatedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(kind, t.OFFICIAL_KINDS, field="kind")
        t.validateOneOf(status, t.OFFICIAL_STATES, field="status")
        if not subject.strip():
            raise ValidationFailedError("subject is required.", fieldErrors={"subject": "empty"})
        self.tenantId = tenantId
        self.kind = kind
        self.subject = subject.strip()
        self.body = body
        self.authorId = authorId
        self.status = status
        self.recipientIds = tuple(recipientIds)
        self.acknowledgedBy = tuple(acknowledgedBy)
        self.publishedAt = publishedAt
        self.createdAt = createdAt
        self.updatedAt = updatedAt

    @staticmethod
    def draft(
        tenantId: uuid.UUID,
        authorId: uuid.UUID,
        kind: str,
        subject: str,
        body: str,
        now: datetime,
        recipientIds: tuple[uuid.UUID, ...] = (),
    ) -> OfficialMessage:
        msg = OfficialMessage(
            id=newId(),
            tenantId=tenantId,
            kind=kind,
            subject=subject,
            body=body,
            authorId=authorId,
            recipientIds=tuple(recipientIds),
            createdAt=now,
        )
        msg.recordEvent(
            DomainEvent(
                name="officialMessageCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=authorId,
                payload={"kind": kind, "subject": subject},
            )
        )
        return msg

    def _transition(self, target: str, now: datetime, *, actorId: uuid.UUID | None = None) -> None:
        if target not in t.OFFICIAL_TRANSITIONS.get(self.status, ()):
            raise ConflictError(f"Cannot move official message {self.status} -> {target}.")
        self.status = target
        self.updatedAt = now
        if target == t.OFFICIAL_PUBLISHED:
            self.publishedAt = now
        self.recordEvent(
            DomainEvent(
                name=f"officialMessage{target.title()}",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=actorId or self.authorId,
                payload={"officialId": str(self.id), "status": target},
            )
        )

    def submitForReview(self, now: datetime) -> None:
        self._transition(t.OFFICIAL_REVIEW, now)

    def approve(self, reviewerId: uuid.UUID, now: datetime) -> None:
        self._transition(t.OFFICIAL_APPROVED, now, actorId=reviewerId)

    def returnToDraft(self, reviewerId: uuid.UUID, now: datetime) -> None:
        self._transition(t.OFFICIAL_DRAFT, now, actorId=reviewerId)

    def publish(self, now: datetime) -> None:
        self._transition(t.OFFICIAL_PUBLISHED, now)

    def markDelivered(self, now: datetime) -> None:
        self._transition(t.OFFICIAL_DELIVERED, now)

    def acknowledge(self, userId: uuid.UUID, now: datetime) -> None:
        if self.status != t.OFFICIAL_DELIVERED:
            raise ConflictError("Only a DELIVERED message can be acknowledged.")
        if userId not in self.acknowledgedBy:
            self.acknowledgedBy = (*self.acknowledgedBy, userId)
        self.status = t.OFFICIAL_ACKNOWLEDGED
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="officialMessageAcknowledged",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=userId,
                payload={"officialId": str(self.id)},
            )
        )


# ---------------------------------------------------------------------------
# §43/§44 MessageReport — moderation report with a review workflow.
# ---------------------------------------------------------------------------


class MessageReport(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        reportedById: uuid.UUID,
        reason: str,
        *,
        description: str = "",
        status: str = t.REPORT_OPEN,
        reviewedById: uuid.UUID | None = None,
        reviewedAt: datetime | None = None,
        resolutionNote: str = "",
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if reason not in t.REPORT_REASONS:
            raise ValidationFailedError("Unknown report reason.", fieldErrors={"reason": reason})
        t.validateOneOf(status, t.REPORT_STATES, field="reportStatus")
        self.tenantId = tenantId
        self.messageId = messageId
        self.reportedById = reportedById
        self.reason = reason
        self.description = description
        self.status = status
        self.reviewedById = reviewedById
        self.reviewedAt = reviewedAt
        self.resolutionNote = resolutionNote
        self.createdAt = createdAt

    @staticmethod
    def open(
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        reportedById: uuid.UUID,
        reason: str,
        now: datetime,
        description: str = "",
    ) -> MessageReport:
        report = MessageReport(
            id=newId(),
            tenantId=tenantId,
            messageId=messageId,
            reportedById=reportedById,
            reason=reason,
            description=description,
            createdAt=now,
        )
        report.recordEvent(
            DomainEvent(
                name="messageReported",
                occurredAt=now,
                tenantId=tenantId,
                actorId=reportedById,
                payload={"messageId": str(messageId), "reason": reason},
            )
        )
        return report

    def _setReview(self, target: str, reviewerId: uuid.UUID, now: datetime, note: str) -> None:
        self.status = target
        self.reviewedById = reviewerId
        self.reviewedAt = now
        if note:
            self.resolutionNote = note

    def startReview(self, reviewerId: uuid.UUID, now: datetime) -> None:
        if t.REPORT_UNDER_REVIEW not in t.REPORT_TRANSITIONS.get(self.status, ()):
            raise ConflictError(f"Cannot move report {self.status} -> {t.REPORT_UNDER_REVIEW}.")
        self._setReview(t.REPORT_UNDER_REVIEW, reviewerId, now, "")
        self.recordEvent(
            DomainEvent(
                name="messageReportUnderReview",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=reviewerId,
                payload={"messageId": str(self.messageId)},
            )
        )

    def resolve(self, reviewerId: uuid.UUID, now: datetime, note: str = "") -> None:
        if self.status == t.REPORT_OPEN:
            self.startReview(reviewerId, now)
        if t.REPORT_RESOLVED not in t.REPORT_TRANSITIONS.get(self.status, ()):
            raise ConflictError(f"Cannot resolve report from {self.status}.")
        self._setReview(t.REPORT_RESOLVED, reviewerId, now, note)
        self.recordEvent(
            DomainEvent(
                name="messageReportResolved",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=reviewerId,
                payload={"messageId": str(self.messageId)},
            )
        )

    def dismiss(self, reviewerId: uuid.UUID, now: datetime, note: str = "") -> None:
        if self.status not in (t.REPORT_OPEN, t.REPORT_UNDER_REVIEW):
            raise ConflictError("Report cannot be dismissed from its current state.")
        target = t.REPORT_DISMISSED
        self._setReview(target, reviewerId, now, note)
        self.recordEvent(
            DomainEvent(
                name="messageReportDismissed",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=reviewerId,
                payload={"messageId": str(self.messageId)},
            )
        )


# ---------------------------------------------------------------------------
# §69 LegalHold
# ---------------------------------------------------------------------------


class LegalHold(AggregateRoot):
    LEGAL_HOLD_SCOPES = ("CONVERSATION", "MEETING", "RECORDING", "TRANSCRIPT", "USER")

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        scope: str,
        targetId: uuid.UUID,
        *,
        reason: str = "",
        status: str = t.LEGAL_HOLD_ACTIVE,
        createdById: uuid.UUID | None = None,
        createdAt: datetime | None = None,
        releasedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(status, t.LEGAL_HOLD_STATES, field="legalHoldStatus")
        t.validateOneOf(scope, self.LEGAL_HOLD_SCOPES, field="scope")
        self.tenantId = tenantId
        self.scope = scope
        self.targetId = targetId
        self.reason = reason
        self.status = status
        self.createdById = createdById
        self.createdAt = createdAt
        self.releasedAt = releasedAt

    @staticmethod
    def place(
        tenantId: uuid.UUID,
        scope: str,
        targetId: uuid.UUID,
        now: datetime,
        *,
        reason: str = "",
        createdById: uuid.UUID | None = None,
    ) -> LegalHold:
        hold = LegalHold(
            id=newId(),
            tenantId=tenantId,
            scope=scope,
            targetId=targetId,
            reason=reason,
            createdById=createdById,
            createdAt=now,
        )
        hold.recordEvent(
            DomainEvent(
                name="legalHoldPlaced",
                occurredAt=now,
                tenantId=tenantId,
                actorId=createdById,
                payload={"scope": scope, "targetId": str(targetId)},
            )
        )
        return hold

    def release(self, now: datetime) -> None:
        if self.status != t.LEGAL_HOLD_ACTIVE:
            raise ConflictError("Legal hold is not active.")
        self.status = t.LEGAL_HOLD_RELEASED
        self.releasedAt = now
