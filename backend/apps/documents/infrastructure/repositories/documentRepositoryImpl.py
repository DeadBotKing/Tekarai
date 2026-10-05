"""Django-ORM implementation of the document repository (Phase 31)."""

from __future__ import annotations

import uuid

from django.db.models import Q
from django.utils import timezone

from apps.documents.domain.entities.document import Document
from apps.documents.infrastructure.models import DocumentModel


def _toDomain(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        tenantId=model.tenantId,
        name=model.name,
        contentType=model.contentType,
        sizeBytes=model.sizeBytes,
        category=model.category,
        description=model.description,
        uploadedByIdentifier=model.uploadedByIdentifier,
        uploadedAt=model.uploadedAt,
        storagePath=model.file.name,
    )


class DocumentRepositoryImpl:
    """Tenant-scoped document persistence; soft-deleted rows stay hidden."""

    def listForTenant(
        self,
        tenantId: uuid.UUID,
        *,
        search: str = "",
        category: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        queryset = DocumentModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category:
            queryset = queryset.filter(category__iexact=category)
        total = queryset.count()
        rows = queryset.order_by("-uploadedAt")[offset : offset + limit]
        return [_toDomain(row) for row in rows], total

    def byId(self, tenantId: uuid.UUID, documentId: uuid.UUID) -> Document | None:
        model = DocumentModel.objects.filter(
            tenantId=tenantId, id=documentId, deletedAt__isnull=True
        ).first()
        return _toDomain(model) if model else None

    def create(
        self,
        *,
        tenantId: uuid.UUID,
        name: str,
        contentType: str,
        sizeBytes: int,
        category: str,
        description: str,
        uploadedByIdentifier: str,
        storagePath: str,
    ) -> Document:
        model = DocumentModel(
            tenantId=tenantId,
            name=name,
            contentType=contentType,
            sizeBytes=sizeBytes,
            category=category,
            description=description,
            uploadedByIdentifier=uploadedByIdentifier,
        )
        model.file.name = storagePath
        model.save()
        return _toDomain(model)

    def softDelete(self, tenantId: uuid.UUID, documentId: uuid.UUID) -> None:
        DocumentModel.objects.filter(tenantId=tenantId, id=documentId).update(
            deletedAt=timezone.now()
        )
