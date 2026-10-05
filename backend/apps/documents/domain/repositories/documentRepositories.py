"""Documents context outbound ports.

The use cases receive their collaborators by attribute injection from the
composition root (``apps.documents.infrastructure.container``). Before these
protocols existed the attributes were never declared, so nothing — neither a
reader nor a type checker — could tell what contract an implementation had to
satisfy, and every ``self.repository`` / ``self.storage`` access was an
unchecked guess. Declaring the ports here keeps the dependency arrow pointing
inward: the application layer depends on these domain protocols, and the
infrastructure implementations are validated against them structurally.
"""

from __future__ import annotations

import builtins
import uuid
from typing import IO, Protocol, runtime_checkable

from apps.documents.domain.entities.document import Document


@runtime_checkable
class DocumentRepository(Protocol):
    """Tenant-scoped persistence for document metadata."""

    def listForTenant(
        self,
        tenantId: uuid.UUID,
        *,
        search: str = "",
        category: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[builtins.list[Document], int]: ...

    def byId(self, tenantId: uuid.UUID, documentId: uuid.UUID) -> Document | None: ...

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
    ) -> Document: ...

    def softDelete(self, tenantId: uuid.UUID, documentId: uuid.UUID) -> None: ...


@runtime_checkable
class DocumentFileStorage(Protocol):
    """Binary payload storage, addressed by an opaque storage path."""

    def save(self, *, tenantId: uuid.UUID, fileName: str, stream: object) -> str: ...

    def open(self, storagePath: str) -> IO[bytes]: ...

    def delete(self, storagePath: str) -> None: ...
