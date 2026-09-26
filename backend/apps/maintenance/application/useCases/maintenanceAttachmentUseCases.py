"""Secure attachment intake, listing, download, and removal for maintenance."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from apps.maintenance.application.commands.maintenanceAttachmentCommands import (
    DeleteMaintenanceAttachmentCommand,
    DownloadMaintenanceAttachmentQuery,
    ListMaintenanceAttachmentsQuery,
    UploadMaintenanceAttachmentCommand,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.maintenanceAttachment import MaintenanceAttachment
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    MaintenanceAttachmentRepository,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError

TARGET_TYPES = {"device", "workOrder"}
CATEGORIES = {"failurePhoto", "manual", "invoice", "other"}
MAX_ATTACHMENT_BYTES = 15 * 1024 * 1024
ALLOWED_FILES: dict[str, set[str]] = {
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".webp": {"image/webp"},
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
    ".txt": {"text/plain"},
}


@dataclass(frozen=True)
class MaintenanceAttachmentDto:
    id: str
    targetType: str
    targetId: str
    category: str
    originalName: str
    mimeType: str
    sizeBytes: int
    uploadedAt: str
    downloadUrl: str


@dataclass(frozen=True)
class MaintenanceAttachmentListDto:
    items: list[MaintenanceAttachmentDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class MaintenanceAttachmentDownload:
    metadata: MaintenanceAttachmentDto
    stream: object


def attachmentDto(item: MaintenanceAttachment) -> MaintenanceAttachmentDto:
    return MaintenanceAttachmentDto(
        id=str(item.id),
        targetType=item.targetType,
        targetId=str(item.targetId),
        category=item.category,
        originalName=item.originalName,
        mimeType=item.mimeType,
        sizeBytes=item.sizeBytes,
        uploadedAt=item.uploadedAt.isoformat(),
        downloadUrl=f"maintenance/attachments/{item.id}/download",
    )


def _safeFileName(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r"[^\w.()\- ]+", "_", name, flags=re.UNICODE).strip(" .")
    return name[:255] or "attachment"


def _hasValidSignature(uploaded: object, extension: str) -> bool:
    """Reject obvious extension/content mismatches without external scanning services."""
    read = getattr(uploaded, "read", None)
    seek = getattr(uploaded, "seek", None)
    if not callable(read) or not callable(seek):
        return False
    header = read(512)
    seek(0)
    if not isinstance(header, bytes):
        return False
    signatures: dict[str, tuple[bytes, ...]] = {
        ".jpg": (b"\xff\xd8\xff",),
        ".jpeg": (b"\xff\xd8\xff",),
        ".png": (b"\x89PNG\r\n\x1a\n",),
        ".pdf": (b"%PDF-",),
        ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
        ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
        ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
        ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    }
    if extension == ".webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if extension == ".txt":
        return b"\x00" not in header
    return any(header.startswith(signature) for signature in signatures.get(extension, ()))


class MaintenanceAttachmentUseCaseBase(UseCase):
    def __init__(self, repository: MaintenanceAttachmentRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repository = repository

    @staticmethod
    def validateTarget(targetType: str) -> None:
        if targetType not in TARGET_TYPES:
            raise ValidationFailedError(
                "Invalid attachment target.", fieldErrors={"targetType": "invalid"}
            )


class UploadMaintenanceAttachmentUseCase(MaintenanceAttachmentUseCaseBase):
    requiredAction = "maintenance.attachment.manage"

    def perform(self, command: UploadMaintenanceAttachmentCommand) -> MaintenanceAttachmentDto:
        self.validateTarget(command.targetType)
        if command.category not in CATEGORIES:
            raise ValidationFailedError(
                "Invalid attachment category.", fieldErrors={"category": "invalid"}
            )
        tenantId = resolveTenantId("")
        targetId = uuid.UUID(command.targetId)
        if not self.repository.targetExists(tenantId, command.targetType, targetId):
            raise EntityNotFoundError(command.targetType, command.targetId)

        uploaded = command.uploadedFile
        originalName = _safeFileName(str(getattr(uploaded, "name", "")))
        sizeBytes = int(getattr(uploaded, "size", 0) or 0)
        mimeType = str(getattr(uploaded, "content_type", "") or "").lower()
        extension = Path(originalName).suffix.lower()
        if sizeBytes <= 0:
            raise ValidationFailedError("The attachment is empty.", fieldErrors={"file": "empty"})
        if sizeBytes > MAX_ATTACHMENT_BYTES:
            raise ValidationFailedError(
                "The attachment exceeds the 15 MB limit.", fieldErrors={"file": "tooLarge"}
            )
        if (
            extension not in ALLOWED_FILES
            or mimeType not in ALLOWED_FILES[extension]
            or not _hasValidSignature(uploaded, extension)
        ):
            raise ValidationFailedError(
                "This attachment type is not allowed or its content does not match its extension.",
                fieldErrors={"file": "unsupportedType"},
            )

        item = self.repository.create(
            tenantId,
            command.targetType,
            targetId,
            command.category,
            originalName,
            mimeType,
            sizeBytes,
            uploaded,
        )
        dto = attachmentDto(item)
        self.audit(
            AUDIT_CREATE,
            "MaintenanceAttachment",
            str(item.id),
            tenantId,
            after={
                "targetType": item.targetType,
                "targetId": str(item.targetId),
                "category": item.category,
                "originalName": item.originalName,
                "mimeType": item.mimeType,
                "sizeBytes": item.sizeBytes,
            },
        )
        return dto


class ListMaintenanceAttachmentsUseCase(MaintenanceAttachmentUseCaseBase):
    requiredAction = "maintenance.attachment.view"

    def perform(self, query: ListMaintenanceAttachmentsQuery) -> MaintenanceAttachmentListDto:
        self.validateTarget(query.targetType)
        tenantId = resolveTenantId("")
        targetId = uuid.UUID(query.targetId)
        if not self.repository.targetExists(tenantId, query.targetType, targetId):
            raise EntityNotFoundError(query.targetType, query.targetId)
        items = [
            attachmentDto(item)
            for item in self.repository.listForTarget(tenantId, query.targetType, targetId)
        ]
        return MaintenanceAttachmentListDto(items=items, totalCount=len(items))


class DownloadMaintenanceAttachmentUseCase(MaintenanceAttachmentUseCaseBase):
    requiredAction = "maintenance.attachment.view"

    def perform(
        self, query: DownloadMaintenanceAttachmentQuery
    ) -> MaintenanceAttachmentDownload:
        tenantId = resolveTenantId("")
        attachmentId = uuid.UUID(query.attachmentId)
        item = self.repository.getById(tenantId, attachmentId)
        if item is None:
            raise EntityNotFoundError("MaintenanceAttachment", query.attachmentId)
        return MaintenanceAttachmentDownload(
            metadata=attachmentDto(item),
            stream=self.repository.openFile(tenantId, attachmentId),
        )


class DeleteMaintenanceAttachmentUseCase(MaintenanceAttachmentUseCaseBase):
    requiredAction = "maintenance.attachment.manage"

    def perform(self, command: DeleteMaintenanceAttachmentCommand) -> None:
        tenantId = resolveTenantId("")
        attachmentId = uuid.UUID(command.attachmentId)
        item = self.repository.getById(tenantId, attachmentId)
        if item is None:
            raise EntityNotFoundError("MaintenanceAttachment", command.attachmentId)
        self.repository.delete(tenantId, attachmentId, self.clock.nowUtc())
        self.audit(
            AUDIT_DELETE,
            "MaintenanceAttachment",
            str(attachmentId),
            tenantId,
            before={
                "targetType": item.targetType,
                "targetId": str(item.targetId),
                "originalName": item.originalName,
            },
        )
        return None
