"""Communication serializers — transport mapping only, no business rules."""

from __future__ import annotations

from rest_framework import serializers

MESSAGE_TYPE_CHOICES = [
    "TEXT",
    "FILE",
    "IMAGE",
    "AUDIO",
    "VIDEO",
    "SYSTEM",
    "MEETING",
    "LOCATION",
    "LINK",
    "AI_GENERATED",
    # Phase 10 §9
    "DOCUMENT",
    "CALL_EVENT",
    "MEETING_EVENT",
]


class CreateDirectSerializer(serializers.Serializer):
    peerUserId = serializers.UUIDField()


class CreateGroupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    memberIds = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )


class CreateChannelSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    code = serializers.RegexField(regex=r"^[a-z0-9_-]{2,64}$")
    topic = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    visibility = serializers.ChoiceField(choices=["PUBLIC", "PRIVATE", "RESTRICTED"])
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class UpdateConversationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    topic = serializers.CharField(max_length=300, required=False, allow_blank=True)
    visibility = serializers.ChoiceField(
        choices=["PUBLIC", "PRIVATE", "RESTRICTED"], required=False
    )


class AddParticipantSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    role = serializers.ChoiceField(
        choices=["OWNER", "ADMIN", "MODERATOR", "MEMBER", "GUEST"], default="MEMBER"
    )


class ChangeRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["OWNER", "ADMIN", "MODERATOR", "MEMBER", "GUEST"])


class PreferencesSerializer(serializers.Serializer):
    isMuted = serializers.BooleanField(required=False)
    notificationLevel = serializers.ChoiceField(
        choices=["ALL", "MENTIONS", "NONE"], required=False
    )


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=8000)
    messageType = serializers.ChoiceField(choices=MESSAGE_TYPE_CHOICES, default="TEXT")
    replyToId = serializers.UUIDField(required=False, allow_null=True, default=None)
    clientRequestId = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )
    attachments = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


class EditMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=8000)


class ReactSerializer(serializers.Serializer):
    reaction = serializers.CharField(max_length=16)


class MarkReadSerializer(serializers.Serializer):
    uptoMessageId = serializers.UUIDField()


class CreateMeetingSerializer(serializers.Serializer):
    conversationId = serializers.UUIDField()
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    scheduledStart = serializers.CharField(required=False, allow_blank=True, default="")
    scheduledEnd = serializers.CharField(required=False, allow_blank=True, default="")
    inviteeIds = serializers.ListField(
        child=serializers.UUIDField(), required=False, default=list
    )
    clientRequestId = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )


class RsvpSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()


class StartCallSerializer(serializers.Serializer):
    conversationId = serializers.UUIDField(required=False, allow_null=True, default=None)
    meetingId = serializers.UUIDField(required=False, allow_null=True, default=None)
    mediaType = serializers.ChoiceField(choices=["AUDIO", "VIDEO", "SCREEN"], default="AUDIO")
    clientRequestId = serializers.CharField(
        max_length=80, required=False, allow_blank=True, default=""
    )


class RelaySignalSerializer(serializers.Serializer):
    envelope = serializers.DictField()
    targetUserId = serializers.UUIDField(required=False, allow_null=True, default=None)


class UpdatePresenceSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[
            "ONLINE",
            "AWAY",
            "BUSY",
            "DO_NOT_DISTURB",
            "IN_MEETING",
            "INVISIBLE",  # Phase 10 §17 privacy state
            "OFFLINE",
        ]
    )


class CreateLetterSerializer(serializers.Serializer):
    recipientId = serializers.UUIDField()
    subject = serializers.CharField(max_length=300)
    body = serializers.CharField(required=False, allow_blank=True, default="")
    recipientOrganization = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    recipientUnit = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
