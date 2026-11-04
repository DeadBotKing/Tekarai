"""Django-ORM implementation of the document repository (Phase 31)."""

from __future__ import annotations

import uuid

from django.db.models import Q
from django.utils import timezone

from apps.documents.domain.entities.document import Document
from apps.documents.infrastructure.models import DocumentModel
from apps.maintenance.infrastructure.models import DeviceModel
from apps.sharedKernel.domain.errors import ValidationFailedError


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
        legacyDeviceDocument=model.legacyDeviceDocument,
        relatedDevices=tuple({"id": str(d.id), "code": d.code, "name": d.name} for d in model.relatedDevices.all() if d.tenantId == model.tenantId),
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
        deviceId: str = "",
        includeLegacy: bool = True,
        includeGeneral: bool = True,
    ) -> tuple[list[Document], int]:
        queryset = DocumentModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if deviceId:
            queryset = queryset.filter(relatedDevices__id=deviceId)
        if not includeLegacy:
            queryset = queryset.filter(legacyDeviceDocument=False)
        if not includeGeneral:
            queryset = queryset.filter(legacyDeviceDocument=True)
        queryset = queryset.prefetch_related("relatedDevices")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))
        if category:
            queryset = queryset.filter(category__iexact=category)
        total = queryset.count()
        rows = queryset.order_by("-uploadedAt", "id")[offset : offset + limit]
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
        deviceIds: tuple[str, ...] = (),
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
        model.relatedDevices.set(deviceIds)
        return _toDomain(model)

    def softDelete(self, tenantId: uuid.UUID, documentId: uuid.UUID) -> None:
        DocumentModel.objects.filter(tenantId=tenantId, id=documentId).update(
            deletedAt=timezone.now()
        )


    def validateDevices(self, tenantId: uuid.UUID, deviceIds: tuple[str, ...]) -> None:
        ids = set(str(value) for value in deviceIds)
        if len(ids) > 500 or DeviceModel.objects.filter(tenantId=tenantId, id__in=ids, deletedAt__isnull=True).count() != len(ids):
            raise ValidationFailedError("دستگاه انتخاب‌شده معتبر نیست یا در دسترس نیست.", fieldErrors={"deviceIds": "invalid"})

    def update(self, tenantId: uuid.UUID, documentId: uuid.UUID, *, category: str | None, description: str | None, deviceIds: tuple[str, ...] | None) -> Document:
        model = DocumentModel.objects.select_for_update().get(tenantId=tenantId, id=documentId, deletedAt__isnull=True)
        if category is not None:
            model.category = category.strip()
        if description is not None:
            model.description = description.strip()
        model.save(update_fields=["category", "description"])
        if deviceIds is not None:
            model.relatedDevices.set(deviceIds)
        return _toDomain(model)
