"""Documents context persistence model (Phase 31 — document library)."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.db import models
from django.utils import timezone


def documentStoragePath(instance: "DocumentModel", filename: str) -> str:
    """Route uploads under media/documents/<tenant>/<documentId>/<filename>."""
    return str(Path("documents") / str(instance.tenantId) / str(instance.id) / filename)


class DocumentModel(models.Model):
    """One real file owned by a tenant, retrievable as a byte stream."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    name = models.CharField(max_length=300)
    contentType = models.CharField(max_length=200, blank=True, default="")
    sizeBytes = models.BigIntegerField(default=0)
    category = models.CharField(max_length=80, blank=True, default="")
    description = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=documentStoragePath, max_length=500)
    uploadedByIdentifier = models.CharField(max_length=200, blank=True, default="")
    uploadedAt = models.DateTimeField(default=timezone.now)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "documents_document"
        ordering = ["-uploadedAt"]
