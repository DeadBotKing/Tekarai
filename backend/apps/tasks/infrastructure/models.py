"""Task persistence model (Phase 18b)."""

from __future__ import annotations

import uuid

from django.db import models


class TaskModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    projectId = models.UUIDField(null=True, blank=True, db_index=True)
    title = models.CharField(max_length=300)
    status = models.CharField(max_length=20, default="todo")
    priority = models.CharField(max_length=20, default="normal")
    assigneeName = models.CharField(max_length=160, blank=True, default="")
    dueDate = models.DateField(null=True, blank=True)
    estimate = models.CharField(max_length=40, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Task"
        ordering = ["-createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.status}:{self.title}"
