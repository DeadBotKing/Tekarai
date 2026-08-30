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
