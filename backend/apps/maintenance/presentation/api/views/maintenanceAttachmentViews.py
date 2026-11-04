"""Authenticated maintenance attachment endpoints."""

from __future__ import annotations

import dataclasses

from django.http import FileResponse
from django.utils.http import content_disposition_header
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import MethodNotAllowed
from apps.documents.infrastructure import container as documentsContainer
from apps.documents.application.commands import ListDocumentsQuery, DownloadDocumentQuery
from apps.documents.infrastructure.models import DocumentModel
from apps.maintenance.infrastructure.models import MaintenanceAttachmentModel
from apps.maintenance.application.services.tenantResolver import resolveTenantId

from apps.maintenance.application.commands.maintenanceAttachmentCommands import (
    DeleteMaintenanceAttachmentCommand,
    DownloadMaintenanceAttachmentQuery,
    ListMaintenanceAttachmentsQuery,
    UploadMaintenanceAttachmentCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.maintenanceSerializers import (
    MaintenanceAttachmentUploadSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def _list(targetType: str, targetId: str) -> Response:
    result = container.listMaintenanceAttachmentsUseCase().execute(
        ListMaintenanceAttachmentsQuery(targetType=targetType, targetId=targetId)
    )
    return Response(
        successEnvelope([dataclasses.asdict(item) for item in result.items], meta=result.asMeta())
    )


def _upload(request: Request, targetType: str, targetId: str) -> Response:
    serializer = MaintenanceAttachmentUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = container.uploadMaintenanceAttachmentUseCase().execute(
        UploadMaintenanceAttachmentCommand(
            targetType=targetType,
            targetId=targetId,
            category=str(serializer.validated_data["category"]),
            uploadedFile=serializer.validated_data["file"],
        )
    )
    return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class DeviceAttachmentView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request, deviceId: str) -> Response:  # noqa: ARG002
        result = documentsContainer.listDocumentsUseCase().execute(ListDocumentsQuery(deviceId=str(deviceId), limit=200))
        items = [{"id": item.id, "targetType": "device", "targetId": str(deviceId), "category": "other", "originalName": item.name, "mimeType": item.contentType, "sizeBytes": item.sizeBytes, "uploadedAt": item.uploadedAt, "downloadUrl": f"/api/v1/documents/{item.id}/download"} for item in result.items]
        return Response(successEnvelope(items, meta=result.asMeta()))

    def post(self, request: Request, deviceId: str) -> Response:
        raise MethodNotAllowed("POST", detail="ثبت مدارک دستگاه فقط از بخش اسناد انجام می‌شود.")


class WorkOrderAttachmentView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request, workOrderId: str) -> Response:  # noqa: ARG002
        return _list("workOrder", str(workOrderId))

    def post(self, request: Request, workOrderId: str) -> Response:
        return _upload(request, "workOrder", str(workOrderId))


class MaintenanceAttachmentDownloadView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, attachmentId: str) -> FileResponse:  # noqa: ARG002
        if DocumentModel.objects.filter(id=attachmentId, tenantId=resolveTenantId(""), legacyDeviceDocument=True).exists():
            result = documentsContainer.downloadDocumentUseCase().execute(DownloadDocumentQuery(documentId=str(attachmentId)))
            response = FileResponse(result.stream, content_type=result.contentType)
            response["Content-Disposition"] = content_disposition_header(True, result.name)
            response["X-Content-Type-Options"] = "nosniff"
            return response
        result = container.downloadMaintenanceAttachmentUseCase().execute(
            DownloadMaintenanceAttachmentQuery(attachmentId=str(attachmentId))
        )
        inline = (
            result.metadata.mimeType.startswith("image/")
            or result.metadata.mimeType == "application/pdf"
        )
        response = FileResponse(result.stream, content_type=result.metadata.mimeType)
        response["Content-Disposition"] = content_disposition_header(
            not inline, result.metadata.originalName
        )
        response["Content-Length"] = str(result.metadata.sizeBytes)
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MaintenanceAttachmentDetailView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, attachmentId: str) -> Response:  # noqa: ARG002
        if MaintenanceAttachmentModel.objects.filter(id=attachmentId, tenantId=resolveTenantId(""), targetType="device").exists():
            raise MethodNotAllowed("DELETE", detail="مدیریت مدارک دستگاه فقط از بخش اسناد انجام می‌شود.")
        container.deleteMaintenanceAttachmentUseCase().execute(
            DeleteMaintenanceAttachmentCommand(attachmentId=str(attachmentId))
        )
        return Response(successEnvelope(None), status=200)
