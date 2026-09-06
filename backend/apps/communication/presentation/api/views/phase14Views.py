"""Thin REST transport for the Phase 14 completion endpoints."""

from __future__ import annotations

import dataclasses

from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.application.commands.phase14Commands import (
    AttachmentPreflightCommand,
    ForwardMessageCommand,
    OfflineSyncCommand,
    RunRetentionCommand,
    UnifiedSearchQuery,
)
from apps.communication.infrastructure import container
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class ForwardMessageSerializer(serializers.Serializer):
    targetConversationId = serializers.UUIDField()
    clientRequestId = serializers.CharField(max_length=80)
    comment = serializers.CharField(max_length=8000, required=False, allow_blank=True, default="")


class AttachmentPreflightSerializer(serializers.Serializer):
    fileName = serializers.CharField(max_length=255)
    mimeType = serializers.CharField(max_length=120)
    sizeBytes = serializers.IntegerField(min_value=1)
    checksum = serializers.RegexField(regex=r"^[0-9A-Fa-f]{64}$")
    scanStatus = serializers.ChoiceField(choices=["PENDING", "CLEAN", "INFECTED", "FAILED"])
    classification = serializers.ChoiceField(
        choices=["PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"], default="INTERNAL"
    )


class OfflineOperationSerializer(serializers.Serializer):
    operationId = serializers.CharField(max_length=100)
    kind = serializers.ChoiceField(choices=["SEND_MESSAGE", "EDIT_MESSAGE", "DELETE_MESSAGE"])
    payload = serializers.DictField()


class OfflineSyncSerializer(serializers.Serializer):
    clientBatchId = serializers.CharField(max_length=100)
    operations = OfflineOperationSerializer(many=True, min_length=1, max_length=100)


class RetentionSerializer(serializers.Serializer):
    retentionDays = serializers.IntegerField(min_value=1, max_value=36500, required=False)
    dryRun = serializers.BooleanField(default=True)


def _data(value: object) -> object:
    return dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value


class MessageForwardView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, messageId: str) -> Response:
        serializer = ForwardMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.forwardMessageUseCase().execute(
            ForwardMessageCommand(
                messageId=messageId,
                targetConversationId=str(data["targetConversationId"]),
                clientRequestId=data["clientRequestId"],
                comment=data["comment"],
            )
        )
        return Response(successEnvelope(_data(result)), status=201)


class AttachmentPreflightView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = AttachmentPreflightSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.attachmentPreflightUseCase().execute(AttachmentPreflightCommand(**data))
        return Response(successEnvelope(result), status=200)


class UnifiedSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        rawScopes = request.query_params.getlist("scope")
        if not rawScopes:
            rawScopes = [part for part in request.query_params.get("scopes", "").split(",") if part]
        try:
            limit = int(request.query_params.get("limit", "25"))
        except ValueError:
            limit = 0
        result = container.unifiedSearchUseCase().execute(
            UnifiedSearchQuery(
                query=request.query_params.get("q", ""), scopes=tuple(rawScopes), limit=limit
            )
        )
        return Response(successEnvelope({"items": list(result), "count": len(result)}), status=200)


class OfflineSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = OfflineSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.offlineSyncUseCase().execute(
            OfflineSyncCommand(
                clientBatchId=data["clientBatchId"], operations=list(data["operations"])
            )
        )
        return Response(successEnvelope(result), status=200)


class RetentionRunView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = RetentionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.runRetentionUseCase().execute(RunRetentionCommand(**data))
        return Response(successEnvelope(result), status=200)


__all__ = [
    "AttachmentPreflightView",
    "MessageForwardView",
    "OfflineSyncView",
    "RetentionRunView",
    "UnifiedSearchView",
]
