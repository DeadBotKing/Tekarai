"""Documents library REST views (Phase 31)."""

from __future__ import annotations

import dataclasses

from django.http import FileResponse
from django.utils.http import content_disposition_header
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.documents.application.commands import (
    DeleteDocumentCommand,
    DownloadDocumentQuery,
    ListDocumentsQuery,
    UploadDocumentCommand,
)
from apps.documents.infrastructure import container
from apps.documents.presentation.api.serializers.documentSerializers import (
    DocumentUploadSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class DocumentListView(IdempotencyMixin, APIView):
    """GET /api/v1/documents — list; POST /api/v1/documents — multipart upload."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request: Request) -> Response:
        query = ListDocumentsQuery(
            search=str(request.query_params.get("search", "")),
            category=str(request.query_params.get("category", "")),
            limit=int(request.query_params.get("limit", 50) or 50),
            offset=int(request.query_params.get("offset", 0) or 0),
        )
        result = container.listDocumentsUseCase().execute(query)
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in result.items], meta=result.asMeta()
            )
        )

    def post(self, request: Request) -> Response:
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.uploadDocumentUseCase().execute(
            UploadDocumentCommand(
                uploadedFile=serializer.validated_data["file"],
                category=str(serializer.validated_data.get("category") or ""),
                description=str(serializer.validated_data.get("description") or ""),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class DocumentDownloadView(APIView):
    """GET /api/v1/documents/<id>/download — stream the stored bytes."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, documentId: str) -> FileResponse:  # noqa: ARG002
        result = container.downloadDocumentUseCase().execute(
            DownloadDocumentQuery(documentId=documentId)
        )
        response = FileResponse(result.stream, content_type=result.contentType)
        response["Content-Disposition"] = content_disposition_header(
            as_attachment=True, filename=result.name
        )
        response["X-Content-Type-Options"] = "nosniff"
        return response


class DocumentDetailView(IdempotencyMixin, APIView):
    """DELETE /api/v1/documents/<id> — soft-delete the record + remove bytes."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, documentId: str) -> Response:  # noqa: ARG002
        result = container.deleteDocumentUseCase().execute(
            DeleteDocumentCommand(documentId=documentId)
        )
        return Response(successEnvelope(dataclasses.asdict(result)))
