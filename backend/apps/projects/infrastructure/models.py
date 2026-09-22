"""Project persistence model (Phase 18b)."""

from __future__ import annotations

import uuid

from django.db import models


class ProjectModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, default="active")
    health = models.IntegerField(default=100)
    progress = models.IntegerField(default=0)
    ownerName = models.CharField(max_length=160, blank=True, default="")
    dueDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Project"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                name="UQG_Project_tenant_code",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.name}"
