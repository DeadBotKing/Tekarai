"""Communication routes — mounted under /api/v1/communication/ (§30)."""

from __future__ import annotations

from django.urls import path

from apps.communication.presentation.api.views.communicationViews import (
    CallActionView,
    CallDetailView,
    CallView,
    ChannelJoinView,
    CommunicationMetricsView,
    ConversationArchiveView,
    ConversationDetailView,
    ConversationListView,
    ConversationReadView,
    LetterDetailView,
    LetterListView,
    MeetingDetailView,
    MeetingLifecycleView,
    MeetingListView,
    MeetingRsvpView,
    MeetingSummaryView,
    MessageDetailView,
    MessageListView,
    MessageReactionsView,
    MessageSearchView,
    ParticipantDetailView,
    ParticipantLeaveView,
    ParticipantListView,
    ParticipantPreferencesView,
    PinListView,
    PresenceView,
    RecordingDetailView,
    RecordingListView,
    registerCommunicationEndpoints,
)
from apps.communication.presentation.api.views.phase10Views import (
    CallSessionView,
    MeetingCapabilityView,
    MessageRevisionListView,
    TranscriptCompleteView,
    TranscriptRequestView,
    UserBlockDetailView,
    UserBlockView,
)

urlpatterns = [
    path("conversations", ConversationListView.as_view(), name="commConversations"),
    path(
        "conversations/<str:conversationId>",
        ConversationDetailView.as_view(),
        name="commConversationDetail",
    ),
    path(
        "conversations/<str:conversationId>/archive",
        ConversationArchiveView.as_view(),
        name="commConversationArchive",
    ),
    path(
        "conversations/<str:conversationId>/join",
        ChannelJoinView.as_view(),
        name="commChannelJoin",
    ),
    path(
        "conversations/<str:conversationId>/participants",
        ParticipantListView.as_view(),
        name="commParticipants",
    ),
    path(
        "conversations/<str:conversationId>/participants/<str:userId>",
        ParticipantDetailView.as_view(),
        name="commParticipantDetail",
    ),
    path(
        "conversations/<str:conversationId>/leave",
        ParticipantLeaveView.as_view(),
        name="commConversationLeave",
    ),
    path(
        "conversations/<str:conversationId>/preferences",
        ParticipantPreferencesView.as_view(),
        name="commParticipantPreferences",
    ),
    path(
        "conversations/<str:conversationId>/messages",
        MessageListView.as_view(),
        name="commMessages",
    ),
    path(
        "conversations/<str:conversationId>/read",
        ConversationReadView.as_view(),
        name="commConversationRead",
    ),
    path(
        "conversations/<str:conversationId>/pins",
        PinListView.as_view(),
        name="commPins",
    ),
    path(
        "conversations/<str:conversationId>/pins/<str:messageId>",
        PinListView.as_view(),
        name="commPinDetail",
    ),
    path(
        "messages/search",
        MessageSearchView.as_view(),
        name="commMessageSearch",
    ),
    path(
        "messages/<str:messageId>",
        MessageDetailView.as_view(),
        name="commMessageDetail",
    ),
    path(
        "messages/<str:messageId>/reactions",
        MessageReactionsView.as_view(),
        name="commMessageReactions",
    ),
    path("meetings", MeetingListView.as_view(), name="commMeetings"),
    path(
        "meetings/<str:meetingId>",
        MeetingDetailView.as_view(),
        name="commMeetingDetail",
    ),
    # Phase 10 + specific sub-paths must be declared BEFORE the generic
    # <str:action> lifecycle route, or they would be swallowed by it.
    path(
        "meetings/<str:meetingId>/rsvp",
        MeetingRsvpView.as_view(),
        name="commMeetingRsvp",
    ),
    path(
        "meetings/<str:meetingId>/summary",
        MeetingSummaryView.as_view(),
        name="commMeetingSummary",
    ),
    path(
        "meetings/<str:meetingId>/recordings",
        RecordingListView.as_view(),
        name="commRecordings",
    ),
    path(
        "meetings/<str:meetingId>/transcript",
        TranscriptRequestView.as_view(),
        name="commMeetingTranscript",
    ),
    path(
        "meetings/<str:meetingId>/capabilities",
        MeetingCapabilityView.as_view(),
        name="commMeetingCapabilities",
    ),
    path(
        "transcripts/<str:transcriptId>/complete",
        TranscriptCompleteView.as_view(),
        name="commTranscriptComplete",
    ),
    path(
        "meetings/<str:meetingId>/<str:action>",
        MeetingLifecycleView.as_view(),
        name="commMeetingLifecycle",
    ),
    path(
        "recordings/<str:recordingId>/<str:action>",
        RecordingDetailView.as_view(),
        name="commRecordingAction",
    ),
    path("blocks", UserBlockView.as_view(), name="commBlocks"),
    path(
        "blocks/<str:blockedUserId>",
        UserBlockDetailView.as_view(),
        name="commBlockDetail",
    ),
    path("call-sessions", CallSessionView.as_view(), name="commCallSessions"),
    path("calls", CallView.as_view(), name="commCalls"),
    path("calls/<str:callId>", CallDetailView.as_view(), name="commCallDetail"),
    path(
        "calls/<str:callId>/<str:action>",
        CallActionView.as_view(),
        name="commCallAction",
    ),
    path("presence", PresenceView.as_view(), name="commPresence"),
    path("metrics", CommunicationMetricsView.as_view(), name="commMetrics"),
    path("letters", LetterListView.as_view(), name="commLetters"),
    path(
        "letters/<str:letterId>/<str:action>",
        LetterDetailView.as_view(),
        name="commLetterAction",
    ),
    # -- Phase 10 surface: message revision history (§11) -------------------
    path(
        "messages/<str:messageId>/revisions",
        MessageRevisionListView.as_view(),
        name="commMessageRevisions",
    ),
]

registerCommunicationEndpoints()
