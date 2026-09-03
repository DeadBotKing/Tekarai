"""Tenancy API permission bindings (§17) — action-based codes (BR-PER-001)."""

from __future__ import annotations

from apps.sharedKernel.presentation.api.permissions import actionPermission

canCreateTenants = actionPermission("tenant.create")
canListTenants = actionPermission("tenant.list")
canViewTenants = actionPermission("tenant.view")
canChangeTenantStatus = actionPermission("tenant.suspend")  # view-level gate;
# the precise action (activate/close) is re-checked inside the use case.
