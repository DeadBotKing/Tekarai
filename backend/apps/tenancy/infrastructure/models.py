"""Tenant persistence model (Phase 05 dictionary — Tenant entity).

Column names follow the Phase 05 ``FieldCatalog.md`` (camelCase §3);
surrogate UUID PK with the business ``code`` as a separate global-unique
key (§12). Infrastructure-only: domain entities never touch this model.
"""

from __future__ import annotations

import uuid

from django.db import models


class TenantModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)  # UQG_Tenant_code (BR-TEN-004)
    name = models.CharField(max_length=160)
    status = models.CharField(max_length=20, default="active")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)  # soft delete (§71)

    class Meta:
        db_table = "Tenant"
        ordering = ["-createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.name}"


class TenantAppearanceModel(models.Model):
    """Runtime per-organization display data; no HTML, SVG or remote resources."""
    tenantId = models.UUIDField(primary_key=True)
    displayName = models.CharField(max_length=160)
    logoData = models.TextField(blank=True, default='')
    primaryColor = models.CharField(max_length=7, default='#214d3d')
    theme = models.CharField(max_length=16, default='warm')
    revision = models.PositiveIntegerField(default=1)
    updatedAt = models.DateTimeField(auto_now=True)


class TenantWorkspaceModel(models.Model):
    """Organization composition, not personal permissions and never executable content."""
    tenantId = models.UUIDField(primary_key=True)
    title = models.CharField(max_length=160)
    introduction = models.TextField(blank=True, default='')
    homeMode = models.CharField(max_length=16, default='cards')
    homeModule = models.CharField(max_length=40, blank=True, default='')
    enabledModules = models.JSONField(default=list)
    menuOrder = models.JSONField(default=list)
    revision = models.PositiveIntegerField(default=1)
    updatedAt = models.DateTimeField(auto_now=True)
