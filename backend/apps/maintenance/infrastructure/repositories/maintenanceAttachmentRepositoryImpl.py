"""Django persistence for maintenance file attachments."""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.maintenance.domain.entities.maintenanceAttachment import MaintenanceAttachment
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MaintenanceAttachmentModel,
    WorkOrderModel,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError


class MaintenanceAttachmentRepositoryDjango:
    @staticmethod
    def _toDomain(model: MaintenanceAttachmentModel) -> MaintenanceAttachment:
        return MaintenanceAttachment(
            id=model.id,
            tenantId=model.tenantId,
            targetType=model.targetType,
            targetId=model.targetId,
            category=model.category,
            originalName=model.originalName,
            mimeType=model.mimeType,
            sizeBytes=model.sizeBytes,
            storageName=model.file.name,
            uploadedAt=model.uploadedAt,
        )

    def targetExists(
        self, tenantId: uuid.UUID, targetType: str, targetId: uuid.UUID
    ) -> bool:
        model = DeviceModel if targetType == "device" else WorkOrderModel
        return model.objects.filter(
            id=targetId, tenantId=tenantId, deletedAt__isnull=True
        ).exists()

    def create(
        self,
        tenantId: uuid.UUID,
        targetType: str,
        targetId: uuid.UUID,
        category: str,
        originalName: str,
        mimeType: str,
        sizeBytes: int,
        uploadedFile: object,
    ) -> MaintenanceAttachment:
        model = MaintenanceAttachmentModel.objects.create(
            tenantId=tenantId,
            targetType=targetType,
            targetId=targetId,
            category=category,
            originalName=originalName,
            mimeType=mimeType,
            sizeBytes=sizeBytes,
            file=uploadedFile,
        )
        return self._toDomain(model)

    def listForTarget(
        self, tenantId: uuid.UUID, targetType: str, targetId: uuid.UUID
    ) -> list[MaintenanceAttachment]:
        rows = MaintenanceAttachmentModel.objects.filter(
            tenantId=tenantId,
            targetType=targetType,
            targetId=targetId,
            deletedAt__isnull=True,
        ).order_by("-uploadedAt")
        return [self._toDomain(item) for item in rows]

    def getById(
        self, tenantId: uuid.UUID, attachmentId: uuid.UUID
    ) -> MaintenanceAttachment | None:
        model = MaintenanceAttachmentModel.objects.filter(
            id=attachmentId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self._toDomain(model) if model else None

    def openFile(self, tenantId: uuid.UUID, attachmentId: uuid.UUID) -> object:
        model = MaintenanceAttachmentModel.objects.filter(
            id=attachmentId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if model is None:
            raise EntityNotFoundError("MaintenanceAttachment", str(attachmentId))
        return model.file.open("rb")

    def delete(self, tenantId: uuid.UUID, attachmentId: uuid.UUID, deletedAt: datetime) -> None:
        updated = MaintenanceAttachmentModel.objects.filter(
            id=attachmentId, tenantId=tenantId, deletedAt__isnull=True
        ).update(deletedAt=deletedAt)
        if not updated:
            raise EntityNotFoundError("MaintenanceAttachment", str(attachmentId))
