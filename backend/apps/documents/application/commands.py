"""Documents context commands & queries (Phase 31)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.sharedKernel.application.messaging import Command, Query


@dataclass(frozen=True)
class ListDocumentsQuery(Query):
    search: str = ""
    category: str = ""
    limit: int = 50
    offset: int = 0
    deviceId: str = ""


@dataclass(frozen=True)
class UploadDocumentCommand(Command):
    uploadedFile: Any = None
    category: str = ""
    description: str = ""
    deviceIds: tuple[str, ...] = ()


@dataclass(frozen=True)
class DownloadDocumentQuery(Query):
    documentId: str = ""


@dataclass(frozen=True)
class DeleteDocumentCommand(Command):
    documentId: str = ""


@dataclass(frozen=True)
class UpdateDocumentCommand(Command):
    documentId: str = ""
    category: str | None = None
    description: str | None = None
    deviceIds: tuple[str, ...] | None = None
