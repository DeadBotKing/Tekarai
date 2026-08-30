"""Permission catalogue — action-based codes (BR-PER-001), stable codes
(§74 reference data). Seeded by ``bootstrapPlatform``; extended per phase.
"""

from __future__ import annotations

ACTIONS: list[tuple[str, str]] = [
    ("tenant.create", "Create tenants (platform scope)"),
    ("tenant.list", "List all tenants (platform scope)"),
    ("tenant.view", "View tenant details"),
    ("tenant.suspend", "Suspend a tenant"),
    ("tenant.activate", "Reactivate a tenant"),
    ("tenant.close", "Close a tenant"),
    ("user.create", "Create users inside the tenant"),
    ("user.view", "View user details"),
    ("user.list", "List users of the tenant"),
    ("user.update", "Update users of the tenant"),
    ("user.assignTenant", "Assign a user to a tenant"),
    ("user.suspend", "Suspend / reactivate a user"),
    ("user.disable", "Disable a user account (terminal state)"),
    ("user.assignRole", "Assign / remove roles on users"),
    ("role.create", "Create roles"),
    ("role.update", "Update role actions"),
    ("role.delete", "Delete unassigned roles"),
    ("role.list", "List roles"),
    ("apikey.create", "Issue API keys"),
    ("apikey.revoke", "Revoke API keys"),
    ("apikey.view", "View tenant API key metadata"),
    ("serviceaccount.create", "Create service accounts"),
    ("serviceaccount.disable", "Disable / enable service accounts"),
    ("serviceaccount.list", "List service accounts"),
    ("session.revoke", "Revoke sessions of other users"),
    ("audit.view", "Read the audit trail"),
]

PLATFORM_ADMIN_ROLE = "platformAdmin"
TENANT_ADMIN_ROLE = "tenantAdmin"
MEMBER_ROLE = "member"

ROLE_PRESETS: dict[str, list[str]] = {
    PLATFORM_ADMIN_ROLE: [action for action, _ in ACTIONS],
    TENANT_ADMIN_ROLE: [
        "user.create",
        "user.view",
        "user.list",
        "user.update",
        "user.assignTenant",
        "user.suspend",
        "user.disable",
        "user.assignRole",
        "role.create",
        "role.update",
        "role.list",
        "apikey.create",
        "apikey.revoke",
        "apikey.view",
        "serviceaccount.create",
        "serviceaccount.disable",
        "serviceaccount.list",
        "session.revoke",
        "audit.view",
        "tenant.view",
    ],
    MEMBER_ROLE: ["user.view", "tenant.view"],
}
