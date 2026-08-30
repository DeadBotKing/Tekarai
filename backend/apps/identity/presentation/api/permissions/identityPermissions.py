"""Identity API permission bindings (§17)."""

from __future__ import annotations

from apps.sharedKernel.presentation.api.permissions import actionPermission

canCreateUsers = actionPermission("user.create")
canViewUsers = actionPermission("user.view")
canListUsers = actionPermission("user.list")
canAssignMembership = actionPermission("user.assignTenant")
