"""Documents context use cases: list / upload / download / soft-delete (Phase 31)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from apps.documents.application.commands import (
    DeleteDocumentCommand,
    DownloadDocumentQuery,
    ListDocumentsQuery,
    UploadDocumentCommand,
)
from apps.documents.domain.entities.document import Document
from apps.documents.domain.repositories.documentRepositories import (
    DocumentFileStorage,
    DocumentRepository,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_CREATE,
    AUDIT_DELETE,
    UseCase,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB guard rail (§trusted-server policy)


@dataclass(frozen=True)
class DocumentDto:
    id: str
    name: str
    contentType: str
    sizeBytes: int
    category: str
    description: str
    uploadedByIdentifier: str
    uploadedAt: str


@dataclass(frozen=True)
class DocumentListDto:
    items: list[DocumentDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass
class DocumentFileResult:
    """Byte-stream result for the download endpoint."""

    name: str = ""
    contentType: str = ""
    stream: object | None = None


def _dto(document: Document) -> DocumentDto:
    return DocumentDto(
        id=str(document.id),
        name=document.name,
        contentType=document.contentType,
        sizeBytes=document.sizeBytes,
        category=document.category,
        description=document.description,
        uploadedByIdentifier=document.uploadedByIdentifier,
        uploadedAt=document.uploadedAt.isoformat(),
    )


class DocumentUseCaseBase(UseCase):
    # Injected by apps.documents.infrastructure.container at construction time.
    repository: DocumentRepository
    storage: DocumentFileStorage

    def _getOrRaise(self, tenantId: uuid.UUID, rawId: str) -> Document:
        try:
            documentId = rawId if isinstance(rawId, uuid.UUID) else uuid.UUID(str(rawId))
        except (ValueError, AttributeError, TypeError) as error:
            raise EntityNotFoundError("Document not found.") from error
        document = self.repository.byId(tenantId, documentId)
        if document is None:
            raise EntityNotFoundError("Document not found.")
        return document

    def _dto(self, document: Document) -> DocumentDto:
        return _dto(document)


class ListDocumentsUseCase(DocumentUseCaseBase):
    requiredAction = "maintenance.document.view"

    def perform(self, query: ListDocumentsQuery) -> DocumentListDto:
        tenantId = resolveTenantId("")
        documents, total = self.repository.listForTenant(
            tenantId,
            search=query.search.strip(),
            category=query.category.strip(),
            limit=max(1, min(query.limit, 200)),
            offset=max(0, query.offset),
        )
        return DocumentListDto(items=[_dto(d) for d in documents], totalCount=total)


class GetDocumentStreamUseCase(DocumentUseCaseBase):
    requiredAction = "maintenance.document.view"

    def perform(self, query: DownloadDocumentQuery) -> DocumentFileResult:
        tenantId = resolveTenantId("")
        document = self._getOrRaise(tenantId, query.documentId)
        return DocumentFileResult(
            name=document.name,
            contentType=document.contentType or "application/octet-stream",
            stream=self.storage.open(document.storagePath),
        )


class UploadDocumentUseCase(DocumentUseCaseBase):
    requiredAction = "maintenance.document.upload"

    def perform(self, command: UploadDocumentCommand) -> DocumentDto:
        uploaded = command.uploadedFile
        fileName = Path(getattr(uploaded, "name", "") or "").name.strip()
        if not fileName:
            raise ValidationFailedError("A file is required.", fieldErrors={"file": "required"})
        sizeBytes = int(getattr(uploaded, "size", 0) or 0)
        if sizeBytes <= 0 or sizeBytes > MAX_UPLOAD_BYTES:
            raise ValidationFailedError(
                "File size must be between 1 byte and 25 MB.",
                fieldErrors={"file": "invalid_size"},
            )
        tenantId = resolveTenantId("")
        context = currentContext()
        uploader = context.actorName or context.actorId or ""
        storedPath = self.storage.save(tenantId=tenantId, fileName=fileName, stream=uploaded)
        try:
            document = self.repository.create(
                tenantId=tenantId,
                name=fileName,
                contentType=(getattr(uploaded, "content_type", "") or "")[:200],
                sizeBytes=sizeBytes,
                category=command.category.strip()[:80],
                description=command.description.strip(),
                uploadedByIdentifier=uploader,
                storagePath=storedPath,
            )
        except Exception:
            self.storage.delete(storedPath)
            raise
        self.audit(
            AUDIT_CREATE, "Document", str(document.id), tenantId, after=_dto(document).__dict__
        )
        return _dto(document)


class DeleteDocumentUseCase(DocumentUseCaseBase):
    requiredAction = "maintenance.document.manage"

    def perform(self, command: DeleteDocumentCommand) -> DocumentDto:
        tenantId = resolveTenantId("")
        document = self._getOrRaise(tenantId, command.documentId)
        self.repository.softDelete(tenantId, document.id)
        self.storage.delete(document.storagePath)
        dto = _dto(document)
        self.audit(AUDIT_DELETE, "Document", str(document.id), tenantId, before=dto.__dict__)
        return dto
