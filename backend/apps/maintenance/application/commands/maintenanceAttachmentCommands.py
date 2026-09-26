from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Command, Query


@dataclass(frozen=True)
class UploadMaintenanceAttachmentCommand(Command):
    targetType: str
    targetId: str
    category: str
    uploadedFile: object


@dataclass(frozen=True)
class DeleteMaintenanceAttachmentCommand(Command):
    attachmentId: str


@dataclass(frozen=True)
class ListMaintenanceAttachmentsQuery(Query):
    targetType: str
    targetId: str


@dataclass(frozen=True)
class DownloadMaintenanceAttachmentQuery(Query):
    attachmentId: str
