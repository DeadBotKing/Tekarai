"""Phase 11 REST views (docs/Phases/Phase11.md).

Thin transport (§55/§64): authenticate → validate input → application use case
→ envelope. No business logic and no ORM here (§62/§63). Surfaces:
- tenant CommunicationPolicy (§70),
- message delivery receipts (§19),
- meeting room/session (§34), screen share (§35),
- meeting summary + action item candidates with human review (§38/§39),
- OfficialMessage governance (§40/§41),
- MessageReport moderation (§43/§44), LegalHold (§69).
"""

from __future__ import annotations

from rest_framework import serializers as drf_serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.application.commands.phase11Commands import (
    AcknowledgeOfficialMessageCommand,
    CreateOfficialMessageCommand,
    DispatchActionItemCommand,
    EndMeetingSessionCommand,
    GenerateMeetingSummaryCommand,
    OpenMeetingRoomCommand,
    PlaceLegalHoldCommand,
    RecordDeliveryCommand,
    ReleaseLegalHoldCommand,
    ReportMessageCommand,
    ReviewActionItemCommand,
    ReviewMeetingSummaryCommand,
    ReviewMessageReportCommand,
    StartMeetingSessionCommand,
    StartScreenShareCommand,
    StopScreenShareCommand,
    TransitionOfficialMessageCommand,
    UpdateCommunicationPolicyCommand,
)
from apps.communication.infrastructure import container
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def _dto(obj: object) -> dict:
    if isinstance(obj, dict):
        return obj
    out = {}
    for key, value in vars(obj).items():
        if key.startswith("_"):
            continue
        if hasattr(value, "hex") and not isinstance(value, (int, float, str, bool)):
            out[key] = str(value)
        elif isinstance(value, (list, tuple)):
            out[key] = [str(v) if hasattr(v, "hex") and not isinstance(v, (int, float, str, bool)) else v for v in value]
        else:
            out[key] = value
    return out


# -- serializers (input validation only, §63) --------------------------------


class UpdatePolicySerializer(drf_serializers.Serializer):
    messageRetentionDays = drf_serializers.IntegerField(required=False, min_value=1)
    recordingRetentionDays = drf_serializers.IntegerField(required=False, min_value=1)
    transcriptRetentionDays = drf_serializers.IntegerField(required=False, min_value=1)
    presenceRetentionDays = drf_serializers.IntegerField(required=False, min_value=1)
    auditRetentionDays = drf_serializers.IntegerField(required=False, min_value=1)
    maxAttachmentSize = drf_serializers.IntegerField(required=False, min_value=1)
    maxMessageLength = drf_serializers.IntegerField(required=False, min_value=1)
    maxGroupMembers = drf_serializers.IntegerField(required=False, min_value=1)
    maxMeetingParticipants = drf_serializers.IntegerField(required=False, min_value=1)
    allowedFileTypes = drf_serializers.ListField(
        child=drf_serializers.CharField(), required=False
    )
    allowExternalUsers = drf_serializers.BooleanField(required=False)
    allowRecording = drf_serializers.BooleanField(required=False)
    allowScreenSharing = drf_serializers.BooleanField(required=False)
    allowMessageEdit = drf_serializers.BooleanField(required=False)
    allowMessageDelete = drf_serializers.BooleanField(required=False)


class RecordDeliverySerializer(drf_serializers.Serializer):
    recipientId = drf_serializers.CharField()
    state = drf_serializers.ChoiceField(choices=["DELIVERED", "FAILED"], default="DELIVERED")
    failedReason = drf_serializers.CharField(required=False, allow_blank=True, default="")


class OpenRoomSerializer(drf_serializers.Serializer):
    capacity = drf_serializers.IntegerField(required=False, default=0, min_value=0)


class ScreenShareStartSerializer(drf_serializers.Serializer):
    shareKind = drf_serializers.ChoiceField(
        choices=["SCREEN", "WINDOW", "TAB"], default="SCREEN"
    )
    sessionId = drf_serializers.CharField(required=False, allow_blank=True, default="")


class SummarySerializer(drf_serializers.Serializer):
    transcriptId = drf_serializers.CharField(required=False, allow_blank=True, default="")
    summary = drf_serializers.CharField(required=False, allow_blank=True, default="")
    keyPoints = drf_serializers.ListField(child=drf_serializers.CharField(), required=False, default=list)
    decisions = drf_serializers.ListField(child=drf_serializers.CharField(), required=False, default=list)
    actionItems = drf_serializers.ListField(child=drf_serializers.CharField(), required=False, default=list)
    risks = drf_serializers.ListField(child=drf_serializers.CharField(), required=False, default=list)
    topics = drf_serializers.ListField(child=drf_serializers.CharField(), required=False, default=list)
    confidence = drf_serializers.FloatField(min_value=0.0, max_value=1.0, default=0.0)
    modelReference = drf_serializers.CharField(required=False, default="tekarai.ai.summary.v1")


class ReviewDecisionSerializer(drf_serializers.Serializer):
    decision = drf_serializers.ChoiceField(choices=["APPROVE", "REJECT", "RESOLVE", "DISMISS"])
    note = drf_serializers.CharField(required=False, allow_blank=True, default="")


class DispatchActionItemSerializer(drf_serializers.Serializer):
    taskRef = drf_serializers.CharField(max_length=120)


class CreateOfficialSerializer(drf_serializers.Serializer):
    kind = drf_serializers.ChoiceField(
        choices=["ANNOUNCEMENT", "DIRECTIVE", "CIRCULAR", "NOTICE"]
    )
    subject = drf_serializers.CharField(max_length=300)
    body = drf_serializers.CharField(required=False, allow_blank=True, default="")
    recipientIds = drf_serializers.ListField(
        child=drf_serializers.CharField(), required=False, default=list
    )


class TransitionOfficialSerializer(drf_serializers.Serializer):
    action = drf_serializers.ChoiceField(
        choices=["review", "approve", "return", "publish", "deliver"]
    )


class ReportMessageSerializer(drf_serializers.Serializer):
    reason = drf_serializers.ChoiceField(
        choices=[
            "SPAM", "ABUSE", "HARASSMENT", "INAPPROPRIATE",
            "MISINFORMATION", "OTHER",
        ]
    )
    description = drf_serializers.CharField(required=False, allow_blank=True, default="")


class LegalHoldSerializer(drf_serializers.Serializer):
    scope = drf_serializers.ChoiceField(
        choices=["CONVERSATION", "MEETING", "RECORDING", "TRANSCRIPT", "USER"]
    )
    targetId = drf_serializers.CharField()
    reason = drf_serializers.CharField(required=False, allow_blank=True, default="")


# -- CommunicationPolicy (§70) ------------------------------------------------


class CommunicationPolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        policy = container.getCommunicationPolicyUseCase().execute(object())
        return Response(successEnvelope(policy.snapshot()))

    def put(self, request: Request) -> Response:
        serializer = UpdatePolicySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        policy = container.updateCommunicationPolicyUseCase().execute(
            UpdateCommunicationPolicyCommand(changes=serializer.validated_data)
        )
        return Response(successEnvelope(policy.snapshot()))


# -- MessageDelivery (§19) ----------------------------------------------------


class MessageDeliveryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, messageId: str) -> Response:
        serializer = RecordDeliverySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.recordDeliveryUseCase().execute(
            RecordDeliveryCommand(
                messageId=messageId,
                recipientId=data["recipientId"],
                state=data["state"],
                failedReason=data.get("failedReason", ""),
            )
        )
        return Response(successEnvelope(result), status=201)


# -- MeetingRoom / MeetingSession (§34) ---------------------------------------


class MeetingRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = OpenRoomSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room = container.openMeetingRoomUseCase().execute(
            OpenMeetingRoomCommand(
                meetingId=meetingId, capacity=serializer.validated_data.get("capacity", 0)
            )
        )
        return Response(successEnvelope(_dto(room)), status=201)


class MeetingSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        session = container.startMeetingSessionUseCase().execute(
            StartMeetingSessionCommand(meetingId=meetingId)
        )
        return Response(successEnvelope(_dto(session)), status=201)


class MeetingSessionEndView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, sessionId: str) -> Response:
        session = container.endMeetingSessionUseCase().execute(
            EndMeetingSessionCommand(sessionId=sessionId)
        )
        return Response(successEnvelope(_dto(session)))


# -- Screen share (§35) -------------------------------------------------------


class ScreenShareView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = ScreenShareStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        share = container.startScreenShareUseCase().execute(
            StartScreenShareCommand(
                meetingId=meetingId,
                shareKind=data["shareKind"],
                sessionId=data.get("sessionId", ""),
            )
        )
        return Response(successEnvelope(_dto(share)), status=201)


class ScreenShareStopView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, shareId: str) -> Response:
        share = container.stopScreenShareUseCase().execute(
            StopScreenShareCommand(shareId=shareId)
        )
        return Response(successEnvelope(_dto(share)))


# -- MeetingSummary + ActionItemCandidate (§38/§39) ---------------------------


class MeetingSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = SummarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        summary = container.generateMeetingSummaryUseCase().execute(
            GenerateMeetingSummaryCommand(
                meetingId=meetingId,
                transcriptId=data.get("transcriptId", ""),
                summary=data.get("summary", ""),
                keyPoints=data.get("keyPoints", []),
                decisions=data.get("decisions", []),
                actionItems=data.get("actionItems", []),
                risks=data.get("risks", []),
                topics=data.get("topics", []),
                confidence=data.get("confidence", 0.0),
                modelReference=data.get("modelReference", "tekarai.ai.summary.v1"),
            )
        )
        return Response(successEnvelope(_dto(summary)), status=201)


class MeetingSummaryReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, summaryId: str) -> Response:
        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        summary = container.reviewMeetingSummaryUseCase().execute(
            ReviewMeetingSummaryCommand(summaryId=summaryId, decision=data["decision"])
        )
        return Response(successEnvelope(_dto(summary)))


class ActionItemReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, itemId: str) -> Response:
        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = container.reviewActionItemUseCase().execute(
            ReviewActionItemCommand(
                itemId=itemId, decision=data["decision"], note=data.get("note", "")
            )
        )
        return Response(successEnvelope(_dto(item)))


class ActionItemDispatchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, itemId: str) -> Response:
        serializer = DispatchActionItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = container.dispatchActionItemUseCase().execute(
            DispatchActionItemCommand(
                itemId=itemId, taskRef=serializer.validated_data["taskRef"]
            )
        )
        return Response(successEnvelope(_dto(item)))


# -- OfficialMessage (§40/§41) ------------------------------------------------


class OfficialMessageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CreateOfficialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        message = container.createOfficialMessageUseCase().execute(
            CreateOfficialMessageCommand(
                kind=data["kind"],
                subject=data["subject"],
                body=data.get("body", ""),
                recipientIds=data.get("recipientIds", []),
            )
        )
        return Response(successEnvelope(_dto(message)), status=201)


class OfficialMessageTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, officialId: str) -> Response:
        serializer = TransitionOfficialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = container.transitionOfficialMessageUseCase().execute(
            TransitionOfficialMessageCommand(
                officialId=officialId, action=serializer.validated_data["action"]
            )
        )
        return Response(successEnvelope(_dto(message)))


class OfficialMessageAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, officialId: str) -> Response:
        message = container.acknowledgeOfficialMessageUseCase().execute(
            AcknowledgeOfficialMessageCommand(officialId=officialId)
        )
        return Response(successEnvelope(_dto(message)))


# -- MessageReport (§43/§44) --------------------------------------------------


class MessageReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, messageId: str) -> Response:
        serializer = ReportMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = container.reportMessageUseCase().execute(
            ReportMessageCommand(
                messageId=messageId,
                reason=data["reason"],
                description=data.get("description", ""),
            )
        )
        return Response(successEnvelope(_dto(report)), status=201)


class MessageReportReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, reportId: str) -> Response:
        serializer = ReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = container.reviewMessageReportUseCase().execute(
            ReviewMessageReportCommand(
                reportId=reportId, decision=data["decision"], note=data.get("note", "")
            )
        )
        return Response(successEnvelope(_dto(report)))


# -- LegalHold (§69) ----------------------------------------------------------


class LegalHoldView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = LegalHoldSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        hold = container.placeLegalHoldUseCase().execute(
            PlaceLegalHoldCommand(
                scope=data["scope"],
                targetId=data["targetId"],
                reason=data.get("reason", ""),
            )
        )
        return Response(successEnvelope(_dto(hold)), status=201)


class LegalHoldReleaseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, holdId: str) -> Response:
        hold = container.releaseLegalHoldUseCase().execute(
            ReleaseLegalHoldCommand(holdId=holdId)
        )
        return Response(successEnvelope(_dto(hold)))
