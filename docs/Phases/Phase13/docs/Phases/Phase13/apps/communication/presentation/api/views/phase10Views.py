"""Phase 10 REST views (docs/Phases/Phase10.md).

Thin transport layer (§64): authenticate → permission → application service →
envelope. No business logic, no ORM (§62/§63). New surfaces:
- message revision history (§11),
- meeting transcripts + segments (§34/§35),
- granular meeting capabilities (§30),
- user blocks (§70),
- provider-agnostic call session bootstrap (§25).
"""

from __future__ import annotations

import dataclasses

from rest_framework import serializers as drf_serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.application.commands.phase10Commands import (
    BlockUserCommand,
    CheckMeetingCapabilityQuery,
    CompleteTranscriptCommand,
    CreateCallSessionCommand,
    GetTranscriptQuery,
    ListBlocksQuery,
    ListMessageRevisionsQuery,
    RequestTranscriptCommand,
    SetMeetingCapabilityCommand,
    TranscriptSegmentInput,
    UnblockUserCommand,
)
from apps.communication.infrastructure import container
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope


def _dto(obj: object) -> dict[str, object]:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return obj
    return dict(getattr(obj, "__dict__", {}))


# -- serializers (§63 — input validation only) --------------------------------


class RequestTranscriptSerializer(drf_serializers.Serializer):
    language = drf_serializers.CharField(required=False, default="en-US", max_length=10)


class TranscriptSegmentSerializer(drf_serializers.Serializer):
    speakerId = drf_serializers.CharField(required=False, allow_blank=True, default="")
    startTimeSeconds = drf_serializers.FloatField(required=False, default=0.0)
    endTimeSeconds = drf_serializers.FloatField(required=False, default=0.0)
    text = drf_serializers.CharField()
    confidence = drf_serializers.FloatField(required=False, default=1.0, min_value=0.0, max_value=1.0)


class CompleteTranscriptSerializer(drf_serializers.Serializer):
    contentReference = drf_serializers.CharField(max_length=300)
    segments = TranscriptSegmentSerializer(many=True, required=False, default=list)


class SetCapabilitySerializer(drf_serializers.Serializer):
    userId = drf_serializers.CharField()
    capability = drf_serializers.CharField()
    granted = drf_serializers.BooleanField()


class CheckCapabilitySerializer(drf_serializers.Serializer):
    userId = drf_serializers.CharField(required=False, allow_blank=True, default="")
    capability = drf_serializers.CharField()


class BlockUserSerializer(drf_serializers.Serializer):
    blockedUserId = drf_serializers.CharField()
    scopes = drf_serializers.ListField(
        child=drf_serializers.CharField(), required=False, default=list
    )
    reason = drf_serializers.CharField(required=False, allow_blank=True, default="", max_length=300)


class CreateCallSessionSerializer(drf_serializers.Serializer):
    callId = drf_serializers.CharField()
    mediaType = drf_serializers.CharField(required=False, default="AUDIO")


# -- message revisions (§11) ---------------------------------------------------


class MessageRevisionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, messageId: str) -> Response:
        dto = container.listMessageRevisionsUseCase().execute(
            ListMessageRevisionsQuery(messageId=messageId)
        )
        return Response(successEnvelope([_dto(item) for item in dto]))


# -- transcripts (§34/§35) -----------------------------------------------------


class TranscriptRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = RequestTranscriptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.requestTranscriptUseCase().execute(
            RequestTranscriptCommand(
                meetingId=meetingId,
                language=serializer.validated_data["language"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)

    def get(self, request: Request, meetingId: str) -> Response:
        dto = container.getTranscriptUseCase().execute(
            GetTranscriptQuery(meetingId=meetingId)
        )
        return Response(successEnvelope(_dto(dto)))


class TranscriptCompleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, transcriptId: str) -> Response:
        serializer = CompleteTranscriptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        segments = [
            TranscriptSegmentInput(
                speakerId=str(seg.get("speakerId", "")),
                startTimeSeconds=float(seg.get("startTimeSeconds", 0.0)),
                endTimeSeconds=float(seg.get("endTimeSeconds", 0.0)),
                text=str(seg.get("text", "")),
                confidence=float(seg.get("confidence", 1.0)),
            )
            for seg in data["segments"]
        ]
        dto = container.completeTranscriptUseCase().execute(
            CompleteTranscriptCommand(
                transcriptId=transcriptId,
                contentReference=data["contentReference"],
                segments=segments,
            )
        )
        return Response(successEnvelope(_dto(dto)))


# -- granular meeting capabilities (§30) ---------------------------------------


class MeetingCapabilityView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, meetingId: str) -> Response:
        serializer = SetCapabilitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.setMeetingCapabilityUseCase().execute(
            SetMeetingCapabilityCommand(
                meetingId=meetingId,
                userId=data["userId"],
                capability=data["capability"],
                granted=bool(data["granted"]),
            )
        )
        return Response(successEnvelope(_dto(dto)))

    def get(self, request: Request, meetingId: str) -> Response:
        serializer = CheckCapabilitySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.checkMeetingCapabilityUseCase().execute(
            CheckMeetingCapabilityQuery(
                meetingId=meetingId,
                userId=data.get("userId", ""),
                capability=data["capability"],
            )
        )
        return Response(successEnvelope(_dto(dto)))


# -- user blocks (§70) ---------------------------------------------------------


class UserBlockView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        dto = container.listBlocksUseCase().execute(ListBlocksQuery())
        return Response(successEnvelope([_dto(item) for item in dto]))

    def post(self, request: Request) -> Response:
        serializer = BlockUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.blockUserUseCase().execute(
            BlockUserCommand(
                blockedUserId=data["blockedUserId"],
                scopes=[str(s) for s in data["scopes"]],
                reason=data["reason"],
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)


class UserBlockDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, blockedUserId: str) -> Response:
        dto = container.unblockUserUseCase().execute(
            UnblockUserCommand(blockedUserId=blockedUserId)
        )
        return Response(successEnvelope(_dto(dto)))


# -- provider-agnostic call session (§25) --------------------------------------


class CallSessionView(APIView):
    permission_classes = [IsAuthenticated]

    @enforceRateLimit("communication:callStart")
    def post(self, request: Request) -> Response:
        serializer = CreateCallSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.createCallSessionUseCase().execute(
            CreateCallSessionCommand(
                callId=data["callId"],
                mediaType=data.get("mediaType", "AUDIO"),
            )
        )
        return Response(successEnvelope(_dto(dto)), status=201)
