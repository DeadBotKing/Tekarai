"""AuditEvent persistence (Phase 06 §19; Phase 04/05 audit model).

Append-only: no view, use case or job ever UPDATEs or DELETEs audit rows
(BR-AUD-002); writes happen only through ``AuditRecorderDjango``. Fields
cover the full §19 list: actor, tenant, action, resource, resourceId,
timestamp, ip, userAgent, before, after, correlationId (+requestId).
Column naming follows the Phase 05 dictionary (camelCase §3).
"""

from __future__ import annotations

import uuid

from django.db import models


class AuditEventModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurredAt = models.DateTimeField(auto_now_add=True, db_index=True)
    actorUserId = models.UUIDField(null=True, blank=True)
    tenantId = models.UUIDField(null=True, blank=True, db_index=True)
    action = models.CharField(max_length=40)
    resourceType = models.CharField(max_length=80)
    resourceId = models.CharField(max_length=64, blank=True, default="")
    ipAddress = models.CharField(max_length=64, blank=True, default="")
    userAgent = models.CharField(max_length=300, blank=True, default="")
    beforeState = models.JSONField(null=True, blank=True)
    afterState = models.JSONField(null=True, blank=True)
    correlationId = models.CharField(max_length=64, blank=True, default="", db_index=True)
    requestId = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "AuditEvent"
        ordering = ["-occurredAt"]
        indexes = [
            models.Index(fields=["tenantId", "occurredAt"], name="IX_AuditEvent_t_occ"),
            models.Index(fields=["tenantId", "correlationId"], name="IX_AuditEvent_t_corr"),
            models.Index(fields=["tenantId", "actorUserId", "action"], name="IX_AuditEvent_t_act"),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.action}:{self.resourceType}/{self.resourceId}"
