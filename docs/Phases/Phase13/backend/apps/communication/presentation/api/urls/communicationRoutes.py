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
from apps.communication.presentation.api.views.phase11Views import (
    ActionItemDispatchView,
    ActionItemReviewView,
    CommunicationPolicyView,
    LegalHoldReleaseView,
    LegalHoldView,
    MeetingRoomView,
    MeetingSessionEndView,
    MeetingSessionView,
    MeetingSummaryReviewView,
    MeetingSummaryView,
    MessageDeliveryView,
    MessageReportReviewView,
    MessageReportView,
    OfficialMessageAcknowledgeView,
    OfficialMessageTransitionView,
    OfficialMessageView,
    ScreenShareStopView,
    ScreenShareView,
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
    # -- Phase 11 meeting sub-resources (MUST precede the
    # meetings/<id>/<action> catch-all below so /room, /sessions,
    # /screen-share and /summary route to the governance views) -------------
    path(
        "meetings/<str:meetingId>/room",
        MeetingRoomView.as_view(),
        name="commMeetingRoom",
    ),
    path(
        "meetings/<str:meetingId>/sessions",
        MeetingSessionView.as_view(),
        name="commMeetingSessions",
    ),
    path(
        "meetings/<str:meetingId>/screen-share",
        ScreenShareView.as_view(),
        name="commScreenShare",
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
    # -- Phase 11 surface (docs/Phases/Phase11.md) --------------------------
    path("policy", CommunicationPolicyView.as_view(), name="commPolicy"),
    path(
        "messages/<str:messageId>/delivery",
        MessageDeliveryView.as_view(),
        name="commMessageDelivery",
    ),
    path(
        "messages/<str:messageId>/report",
        MessageReportView.as_view(),
        name="commMessageReport",
    ),
    path(
        "reports/<str:reportId>/review",
        MessageReportReviewView.as_view(),
        name="commMessageReportReview",
    ),
    # NOTE: meetings/<meetingId>/room|sessions|screen-share|summary are
    # registered earlier (before the meetings/<id>/<action> catch-all) below;
    # the non-meeting-prefixed Phase 11 routes stay here.
    path(
        "sessions/<str:sessionId>/end",
        MeetingSessionEndView.as_view(),
        name="commMeetingSessionEnd",
    ),
    path(
        "screen-shares/<str:shareId>/stop",
        ScreenShareStopView.as_view(),
        name="commScreenShareStop",
    ),
    path(
        "summaries/<str:summaryId>/review",
        MeetingSummaryReviewView.as_view(),
        name="commSummaryReview",
    ),
    path(
        "action-items/<str:itemId>/review",
        ActionItemReviewView.as_view(),
        name="commActionItemReview",
    ),
    path(
        "action-items/<str:itemId>/dispatch",
        ActionItemDispatchView.as_view(),
        name="commActionItemDispatch",
    ),
    path("official-messages", OfficialMessageView.as_view(), name="commOfficial"),
    path(
        "official-messages/<str:officialId>/transition",
        OfficialMessageTransitionView.as_view(),
        name="commOfficialTransition",
    ),
    path(
        "official-messages/<str:officialId>/acknowledge",
        OfficialMessageAcknowledgeView.as_view(),
        name="commOfficialAcknowledge",
    ),
    path("legal-holds", LegalHoldView.as_view(), name="commLegalHold"),
    path(
        "legal-holds/<str:holdId>/release",
        LegalHoldReleaseView.as_view(),
        name="commLegalHoldRelease",
    ),
]

registerCommunicationEndpoints()
