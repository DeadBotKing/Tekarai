"""Communication ORM models (Phase 08 §26–§27).

Table names follow the spec's conceptual list exactly. Global standards:
UUID PKs, createdAt/updatedAt, createdBy where applicable, soft-delete
where appropriate, tenant scoping, indexes and constraints. Presence has NO
table — it lives in the ephemeral store (§7).
"""

from __future__ import annotations

import uuid

from django.db import models


def uuidPk() -> models.UUIDField:
    return models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class ConversationModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    conversationType = models.CharField(max_length=20, db_index=True)
    name = models.CharField(max_length=160, blank=True, default="")
    description = models.CharField(max_length=500, blank=True, default="")
    directKey = models.CharField(max_length=80, blank=True, default="", db_index=True)
    isActive = models.BooleanField(default=True, db_index=True)
    createdBy = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)
    archivedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communicationConversations"
        indexes = [
            models.Index(fields=["tenantId", "conversationType"], name="IX_Conv_t_type"),
            models.Index(fields=["tenantId", "isActive"], name="IX_Conv_t_active"),
        ]
        constraints = [
            # §5 — one direct conversation per user pair per tenant
            models.UniqueConstraint(
                fields=["tenantId", "directKey"],
                condition=models.Q(conversationType="DIRECT", directKey__gt=""),
                name="UQ_Conversation_direct_key",
            ),
        ]


class ChannelProfileModel(models.Model):
    """§4 — channel-only profile (1:1 with a CHANNEL conversation)."""

    id = uuidPk()
    conversationId = models.UUIDField(unique=True, db_index=True)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64, blank=True, default="", db_index=True)
    topic = models.CharField(max_length=300, blank=True, default="")
    visibility = models.CharField(max_length=12, default="PUBLIC")
    isArchived = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationChannels"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(code__gt=""),
                name="UQ_Channel_code",
            ),
        ]


class ChannelMembershipModel(models.Model):
    """§26 — public-channel self-join history (PRIVATE membership lives in
    the conversation participants table)."""

    id = uuidPk()
    conversationId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    requestedBy = models.UUIDField(null=True, blank=True)
    joinedAt = models.DateTimeField(auto_now_add=True)
    leftAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communicationChannelMemberships"
        indexes = [
            models.Index(fields=["conversationId", "userId"], name="IX_ChanM_c_u"),
        ]


class ConversationParticipantModel(models.Model):
    id = uuidPk()
    conversationId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    role = models.CharField(max_length=12, default="MEMBER")
    invitedBy = models.UUIDField(null=True, blank=True)
    joinedAt = models.DateTimeField(auto_now_add=True)
    leftAt = models.DateTimeField(null=True, blank=True)
    isMuted = models.BooleanField(default=False)
    # Phase 10 §5 — time-bounded mute and explicit notification toggle.
    mutedUntil = models.DateTimeField(null=True, blank=True)
    notificationsEnabled = models.BooleanField(default=True)
    notificationLevel = models.CharField(max_length=12, default="ALL")
    lastReadMessageId = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationConversationParticipants"
        indexes = [
            models.Index(fields=["conversationId", "userId"], name="IX_Part_c_u"),
        ]
        constraints = [
            # §38 — duplicate ACTIVE participant is a data corruption bug
            models.UniqueConstraint(
                fields=["conversationId", "userId"],
                condition=models.Q(leftAt__isnull=True),
                name="UQ_Participant_active",
            ),
        ]


class MessageModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(db_index=True)
    senderId = models.UUIDField(db_index=True)
    messageType = models.CharField(max_length=20, default="TEXT")
    body = models.TextField(blank=True, default="")
    replyToId = models.UUIDField(null=True, blank=True, db_index=True)
    # Phase 10 §14 — thread root for nested replies (indexed per §42).
    threadRootId = models.UUIDField(null=True, blank=True, db_index=True)
    clientRequestId = models.CharField(max_length=80, blank=True, default="")
    editedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationMessages"
        indexes = [
            models.Index(fields=["conversationId", "createdAt"], name="IX_Msg_c_created"),
            models.Index(fields=["senderId", "createdAt"], name="IX_Msg_s_created"),
        ]
        constraints = [
            # §24 — offline retries never duplicate a committed message
            models.UniqueConstraint(
                fields=["tenantId", "conversationId", "senderId", "clientRequestId"],
                condition=models.Q(clientRequestId__gt=""),
                name="UQ_Message_idempotency",
            ),
        ]


class MessageAttachmentModel(models.Model):
    """§3.4 — metadata reference into the (future) Documents subsystem."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    fileName = models.CharField(max_length=255)
    mimeType = models.CharField(max_length=120, default="application/octet-stream")
    sizeBytes = models.BigIntegerField(default=0)
    documentRef = models.CharField(max_length=255, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationMessageAttachments"
        indexes = [models.Index(fields=["messageId"], name="IX_Att_m")]


class MessageReactionModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    reaction = models.CharField(max_length=16)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationMessageReactions"
        constraints = [
            # §3.5 — no duplicate identical reactions
            models.UniqueConstraint(
                fields=["messageId", "userId", "reaction"], name="UQ_Reaction_unique"
            ),
        ]


class MessageMentionModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    mentionedUserId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationMessageMentions"
        indexes = [models.Index(fields=["messageId"], name="IX_Men_m")]


class MessageReadStateModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    state = models.CharField(max_length=10, default="SENT")
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationMessageReadStates"
        indexes = [
            models.Index(fields=["messageId", "userId"], name="IX_Read_m_u"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["messageId", "userId"], name="UQ_ReadState_m_u"
            ),
        ]


class MeetingModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(db_index=True)
    organizerId = models.UUIDField(db_index=True)
    title = models.CharField(max_length=200)
    description = models.CharField(max_length=1000, blank=True, default="")
    scheduledStart = models.DateTimeField(null=True, blank=True)
    scheduledEnd = models.DateTimeField(null=True, blank=True)
    actualStart = models.DateTimeField(null=True, blank=True)
    actualEnd = models.DateTimeField(null=True, blank=True)
    meetingStatus = models.CharField(max_length=12, default="SCHEDULED", db_index=True)
    # Phase 10 §27 — meeting configuration.
    meetingType = models.CharField(max_length=16, blank=True, default="SCHEDULED")
    joinPolicy = models.CharField(max_length=16, blank=True, default="INVITE_ONLY")
    recordingPolicy = models.CharField(max_length=16, blank=True, default="ORGANIZER")
    clientRequestId = models.CharField(max_length=80, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationMeetings"
        indexes = [
            models.Index(fields=["tenantId", "scheduledStart"], name="IX_Meet_t_start"),
            models.Index(fields=["tenantId", "meetingStatus"], name="IX_Meet_t_status"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "organizerId", "clientRequestId"],
                condition=models.Q(clientRequestId__gt=""),
                name="UQ_Meeting_idempotency",
            ),
        ]


class MeetingParticipantModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    meetingId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    status = models.CharField(max_length=10, default="INVITED")
    # Phase 10 §29 — host/co-host/participant/guest role + attendance seconds.
    role = models.CharField(max_length=12, blank=True, default="PARTICIPANT")
    attendanceDuration = models.IntegerField(default=0)
    respondedAt = models.DateTimeField(null=True, blank=True)
    joinedAt = models.DateTimeField(null=True, blank=True)
    leftAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationMeetingParticipants"
        constraints = [
            models.UniqueConstraint(
                fields=["meetingId", "userId"], name="UQ_MeetingParticipant"
            ),
        ]


class CallModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    initiatorId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(null=True, blank=True, db_index=True)
    meetingId = models.UUIDField(null=True, blank=True, db_index=True)
    mediaType = models.CharField(max_length=12, default="AUDIO")
    callStatus = models.CharField(max_length=10, default="RINGING", db_index=True)
    mediaSessionRef = models.CharField(max_length=120, blank=True, default="")
    clientRequestId = models.CharField(max_length=80, blank=True, default="")
    startedAt = models.DateTimeField(null=True, blank=True)
    endedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationCalls"
        indexes = [
            models.Index(fields=["meetingId", "callStatus"], name="IX_Call_m_status"),
            models.Index(fields=["callStatus", "startedAt"], name="IX_Call_status_start"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "initiatorId", "clientRequestId"],
                condition=models.Q(clientRequestId__gt=""),
                name="UQ_Call_idempotency",
            ),
        ]


class CallParticipantModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    callId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    joinedAt = models.DateTimeField(auto_now_add=True)
    leftAt = models.DateTimeField(null=True, blank=True)
    mediaState = models.CharField(max_length=32, default="connected")

    class Meta:
        db_table = "communicationCallParticipants"
        constraints = [
            models.UniqueConstraint(fields=["callId", "userId"], name="UQ_CallParticipant"),
        ]


class RecordingModel(models.Model):
    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    meetingId = models.UUIDField(db_index=True)
    requestedBy = models.UUIDField(db_index=True)
    recordingStatus = models.CharField(max_length=12, default="REQUESTED")
    startedAt = models.DateTimeField(null=True, blank=True)
    stoppedAt = models.DateTimeField(null=True, blank=True)
    storageRef = models.CharField(max_length=255, blank=True, default="")
    durationSeconds = models.IntegerField(default=0)
    failureReason = models.CharField(max_length=300, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationRecordings"
        indexes = [
            models.Index(fields=["tenantId", "meetingId"], name="IX_Rec_t_m"),
        ]


class PinnedMessageModel(models.Model):
    """§4/§26 — pinned messages."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    pinnedBy = models.UUIDField()
    pinnedAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationPins"
        constraints = [
            models.UniqueConstraint(
                fields=["conversationId", "messageId"], name="UQ_Pin_unique"
            ),
        ]


class OfficialLetterModel(models.Model):
    """§16 — dedicated formal-communication model (never a message type)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    referenceNumber = models.CharField(max_length=20, db_index=True)
    senderId = models.UUIDField(db_index=True)
    recipientId = models.UUIDField(db_index=True)
    subject = models.CharField(max_length=300)
    body = models.TextField(blank=True, default="")
    recipientOrganization = models.CharField(max_length=160, blank=True, default="")
    recipientUnit = models.CharField(max_length=160, blank=True, default="")
    letterStatus = models.CharField(max_length=12, default="DRAFT", db_index=True)
    approvedBy = models.UUIDField(null=True, blank=True)
    signedBy = models.UUIDField(null=True, blank=True)
    dispatchedAt = models.DateTimeField(null=True, blank=True)
    receivedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationOfficialLetters"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "referenceNumber"], name="UQ_Letter_reference"
            ),
        ]


class OutboxModel(models.Model):
    """§29 — integration events written in the SAME transaction, published
    only after commit; a crash never loses a committed event."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    eventType = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict)
    occurredAt = models.DateTimeField()
    publishedAt = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.IntegerField(default=0)

    class Meta:
        db_table = "communicationOutbox"
        indexes = [
            models.Index(fields=["publishedAt", "occurredAt"], name="IX_Outbox_pending"),
        ]


# ---------------------------------------------------------------------------
# Phase 10 additions (docs/Phases/Phase10.md) — appended without touching the
# Phase 08 table set, so 0001 stays reproducible and every Phase 08 test keeps
# passing. New tables live in migration 0002_phase10_communication.
# ---------------------------------------------------------------------------


class MessageRevisionModel(models.Model):
    """§11 — append-only edit history (previous body + who/when)."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    messageId = models.UUIDField(db_index=True)
    conversationId = models.UUIDField(db_index=True)
    revisionNumber = models.IntegerField()
    previousBody = models.TextField(blank=True, default="")
    newBody = models.TextField(blank=True, default="")
    editedBy = models.UUIDField(db_index=True)
    editedAt = models.DateTimeField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationMessageRevisions"
        indexes = [
            models.Index(fields=["messageId", "revisionNumber"], name="IX_Rev_msg_seq"),
            models.Index(fields=["tenantId", "messageId"], name="IX_Rev_t_msg"),
        ]
        constraints = [
            # §43 — one ordinal revision number per message
            models.UniqueConstraint(
                fields=["messageId", "revisionNumber"],
                name="UQ_Revision_message_number",
            ),
        ]


class MeetingTranscriptModel(models.Model):
    """§34 — transcript aggregate, independent of the recording."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    meetingId = models.UUIDField(db_index=True)
    language = models.CharField(max_length=10, default="en-US")
    transcriptStatus = models.CharField(max_length=12, default="PENDING", db_index=True)
    contentReference = models.CharField(max_length=300, blank=True, default="")
    segmentCount = models.IntegerField(default=0)
    requestedBy = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "communicationMeetingTranscripts"
        indexes = [
            models.Index(fields=["tenantId", "meetingId"], name="IX_Tran_t_meeting"),
            models.Index(fields=["meetingId", "transcriptStatus"], name="IX_Tran_m_status"),
        ]


class TranscriptSegmentModel(models.Model):
    """§35 — timed, attributed transcript slice."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    transcriptId = models.UUIDField(db_index=True)
    sequence = models.IntegerField()
    speakerId = models.UUIDField(null=True, blank=True, db_index=True)
    startTimeSeconds = models.FloatField()
    endTimeSeconds = models.FloatField()
    text = models.TextField()
    confidence = models.FloatField(default=0.0)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationTranscriptSegments"
        indexes = [
            models.Index(
                fields=["transcriptId", "sequence"], name="IX_Seg_tran_seq"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["transcriptId", "sequence"],
                name="UQ_Segment_transcript_seq",
            ),
        ]


class UserBlockModel(models.Model):
    """§70 — directional user block across communication scopes."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    blockerId = models.UUIDField(db_index=True)
    blockedUserId = models.UUIDField(db_index=True)
    scopes = models.JSONField(default=list)
    reason = models.CharField(max_length=300, blank=True, default="")
    blockStatus = models.CharField(max_length=10, default="ACTIVE", db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True)
    removedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "communicationUserBlocks"
        indexes = [
            models.Index(fields=["tenantId", "blockerId"], name="IX_Block_t_blocker"),
            models.Index(
                fields=["blockerId", "blockedUserId", "blockStatus"],
                name="IX_Block_pair_status",
            ),
        ]
        constraints = [
            # one active block per ordered pair
            models.UniqueConstraint(
                fields=["tenantId", "blockerId", "blockedUserId"],
                condition=models.Q(blockStatus="ACTIVE"),
                name="UQ_Block_active_pair",
            ),
        ]


class MeetingCapabilityOverrideModel(models.Model):
    """§30 — per-meeting capability grant/deny overriding the role default."""

    id = uuidPk()
    tenantId = models.UUIDField(db_index=True)
    meetingId = models.UUIDField(db_index=True)
    userId = models.UUIDField(db_index=True)
    capability = models.CharField(max_length=32)
    granted = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communicationMeetingCapabilityOverrides"
        indexes = [
            models.Index(fields=["meetingId", "userId"], name="IX_Cap_m_user"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["meetingId", "userId", "capability"],
                name="UQ_Cap_meeting_user_cap",
            ),
        ]
