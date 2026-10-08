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
    # -- Phase 08 (Communication Platform §17/§35) ---------------------------
    ("conversation.create", "Create direct/group conversations and channels"),
    ("conversation.moderate", "Moderate conversations (pins, archive, participants)"),
    ("meeting.manage", "Schedule and control meetings"),
    ("recording.manage", "Start/stop and publish meeting recordings"),
    ("letter.create", "Draft official letters"),
    ("letter.approve", "Approve official letters"),
    ("letter.sign", "Sign official letters"),
    ("letter.dispatch", "Dispatch official letters"),
    # -- Phase 09 notification surface (§40) ----------------------------------
    ("notification.send", "Send and schedule notifications"),
    ("notification.manage", "Manage templates, policies, channels and tenant rules"),
    ("audit.view", "Read the audit trail"),
    # -- Phase 13-Z AI Platform public boundary ------------------------------
    ("ai.agent.read", "Read AI agent definitions, runs, approvals and jobs"),
    ("ai.agent.manage", "Register and manage versioned AI agent definitions"),
    ("ai.agent.run", "Run approved AI agents synchronously or asynchronously"),
    ("ai.agent.approve", "Approve agent definitions and governed executions"),
    ("ai.tool.invoke", "Invoke an approved AI tool through the governed chain"),
    # -- Phase 16 Self-Learning Platform ------------------------------------
    ("learning.view", "Read tenant learning datasets, experiments and artifacts"),
    ("learning.observe", "Record immutable operational learning experiences"),
    ("learning.manage", "Build datasets, experiments, evaluations and validations"),
    ("learning.run", "Queue governed asynchronous learning runs"),
    ("learning.approve", "Approve or reject validated learning artifacts"),
    ("learning.deploy", "Deploy, advance canaries and roll back artifacts"),
    ("learning.feedback", "Record sourced human/system/business feedback"),
    ("learning.monitor", "Record metrics and detect production drift"),
    # -- Reporting/Analytics MetricReading platform -------------------------
    ("analytics.metricDefinition.view", "View tenant metric definitions"),
    ("analytics.metricDefinition.manage", "Create and govern metric definitions"),
    ("analytics.metricReading.view", "Query tenant metric readings and summaries"),
    ("analytics.metricReading.record", "Ingest immutable metric readings"),
    # -- Phase 18b workspace delivery (projects & tasks) --------------------
    ("project.create", "Create projects inside the tenant"),
    ("project.view", "View project details"),
    ("project.list", "List projects of the tenant"),
    ("project.update", "Update projects and their status"),
    ("task.create", "Create tasks inside the tenant"),
    ("task.view", "View task details"),
    ("task.list", "List tasks of the tenant"),
    ("task.update", "Update tasks and their status"),
    # -- Phase 21 CMMS (maintenance context) --------------------------------
    ("maintenance.device.manage", "Register and update devices, status and PM records"),
    ("maintenance.device.list", "List devices and due preventive maintenance"),
    ("maintenance.device.view", "View device details and PM schedule"),
    ("maintenance.workorder.create", "Submit maintenance work orders (requests)"),
    ("maintenance.workorder.update", "Update work orders and transition their status"),
    ("maintenance.workorder.route", "Route work orders to a maintenance department"),
    ("maintenance.workorder.assign", "Assign work orders to technicians"),
    ("maintenance.workorder.approve", "Approve or reject completed work orders"),
    ("maintenance.workorder.list", "List maintenance work orders"),
    ("maintenance.workorder.view", "View work order details"),
    ("maintenance.workorder.logTime", "Log and remove technician labour time on work orders"),
    ("maintenance.costs.view", "View work-order cost summaries and the maintenance cost report"),
    ("maintenance.inventory.view", "View spare-parts inventory and consumption"),
    ("maintenance.inventory.manage", "Create parts and adjust warehouse stock"),
    ("maintenance.inventory.consume", "Consume spare parts on maintenance work orders"),
    # -- Meter readings (ثبت قرائت دستی و سنسوری) ---------------------------
    ("maintenance.meter.view", "View meter points, readings and meter-driven PM status"),
    ("maintenance.meter.manage", "Define and retire meter points and their sensor bindings"),
    ("maintenance.meter.record", "Record manual meter readings and append corrections"),
    ("maintenance.meter.ingest", "Push sensor readings through the gateway ingest API"),
    ("maintenance.attachment.view", "View and download maintenance attachments"),
    ("maintenance.attachment.manage", "Upload and remove maintenance attachments"),
    ("maintenance.document.view", "Browse and download the tenant document library"),
    ("maintenance.document.upload", "Upload files into the tenant document library"),
    ("maintenance.document.manage", "Delete files from the tenant document library"),
    ("procurement.supplier.view", "View suppliers and supplier part prices"),
    ("procurement.supplier.manage", "Create and manage suppliers and quotes"),
    ("procurement.requisition.create", "Create purchase requisitions"),
    ("procurement.requisition.approve", "Approve or reject purchase requisitions"),
    ("procurement.purchaseOrder.create", "Create purchase orders"),
    ("procurement.purchaseOrder.approve", "Approve or cancel purchase orders"),
    ("procurement.receipt.post", "Post goods receipts into inventory"),
    ("procurement.return.post", "Post supplier returns"),
    ("procurement.invoice.manage", "Record and manage supplier invoices"),
    # Phase 27 — permit to work. The split follows who may do what on a real
    # plant, not CRUD shape: requesting a permit and applying an isolation are
    # the crew's job, authorising one is the supervisor's, and the two must
    # never collapse into a single permission.
    ("safety.permit.view", "View permits to work and their isolation registers"),
    ("safety.permit.request", "Raise a permit to work and submit it for approval"),
    ("safety.permit.approve", "Authorise, reject, suspend or cancel a permit to work"),
    ("safety.permit.isolate", "Apply, verify and remove isolation points"),
    ("safety.permit.close", "Close a permit and hand equipment back to operations"),
    # Phase 28 — organisation chart. Managing the structure is separated
    # from managing the matrix on purpose: moving a person between units is
    # routine administration, while editing who may approve work is the act
    # that changes what the system refuses, and the two should not be the
    # same permission.
    ("organization.department.view", "View organisation units"),
    ("organization.department.manage", "Create, edit and deactivate organisation units"),
    ("organization.position.view", "View organisation positions"),
    ("organization.position.manage", "Create, edit and deactivate positions"),
    ("organization.assignment.view", "View who is posted where"),
    ("organization.assignment.manage", "Assign users to units and positions"),
    ("organization.accessRule.view", "View the department/position permission matrix"),
    ("organization.accessRule.manage", "Grant and revoke permissions in the matrix"),
    # Verbs the matrix can grant that had no action code before it existed.
    ("maintenance.workorder.delete", "Delete a work order"),
    ("maintenance.workorder.close", "Close a completed work order"),
    ("maintenance.workorder.export", "Export work orders"),
    ("maintenance.device.export", "Export the equipment register"),
    ("maintenance.inventory.export", "Export the spare-parts register"),
    ("analytics.metric.export", "Export analytics and reports"),
]


PLATFORM_ADMIN_ROLE = "platformAdmin"
TENANT_ADMIN_ROLE = "tenantAdmin"
MEMBER_ROLE = "member"

# Phase 21 CMMS role codes (three-role model: requester / technician / manager).
MAINTENANCE_REQUESTER_ROLE = "maintenanceRequester"
MAINTENANCE_TECHNICIAN_ROLE = "maintenanceTechnician"
MAINTENANCE_MANAGER_ROLE = "maintenanceManager"

# Reusable Analytics permission bundles. Definitions are governed by admins;
# operations clients can ingest and all authenticated business roles may read.
_ANALYTICS_READER_ACTIONS = [
    "analytics.metricDefinition.view",
    "analytics.metricReading.view",
]
_ANALYTICS_WRITER_ACTIONS = [
    *_ANALYTICS_READER_ACTIONS,
    "analytics.metricReading.record",
]
_ANALYTICS_MANAGER_ACTIONS = [
    *_ANALYTICS_WRITER_ACTIONS,
    "analytics.metricDefinition.manage",
]

# Reusable maintenance permission bundles.
_MAINTENANCE_REQUESTER_ACTIONS = [
    "maintenance.device.list",
    "maintenance.device.view",
    "maintenance.meter.view",
    "maintenance.workorder.create",
    "maintenance.workorder.list",
    "maintenance.workorder.view",
    "maintenance.attachment.view",
    "maintenance.attachment.manage",
    "maintenance.document.view",
    "maintenance.document.upload",
    "safety.permit.view",
    "organization.department.view",
]
_MAINTENANCE_TECHNICIAN_ACTIONS = [
    "maintenance.device.list",
    "maintenance.device.view",
    "maintenance.device.manage",
    "maintenance.meter.view",
    "maintenance.meter.record",
    "maintenance.workorder.create",
    "maintenance.workorder.update",
    "maintenance.workorder.list",
    "maintenance.workorder.view",
    "maintenance.workorder.logTime",
    "maintenance.costs.view",
    "maintenance.inventory.view",
    "maintenance.inventory.consume",
    "maintenance.attachment.view",
    "maintenance.attachment.manage",
    "maintenance.document.view",
    "maintenance.document.upload",
    # A technician raises permits for their own work and performs the
    # lock-and-tag, but cannot authorise — that is the whole point of
    # segregation of duties.
    "safety.permit.view",
    "safety.permit.request",
    "safety.permit.isolate",
    "organization.department.view",
]
_PROCUREMENT_MANAGER_ACTIONS = [
    "procurement.supplier.view",
    "procurement.supplier.manage",
    "procurement.requisition.create",
    "procurement.requisition.approve",
    "procurement.purchaseOrder.create",
    "procurement.purchaseOrder.approve",
    "procurement.receipt.post",
    "procurement.return.post",
    "procurement.invoice.manage",
]

_MAINTENANCE_MANAGER_ACTIONS = [
    "maintenance.device.manage",
    "maintenance.device.list",
    "maintenance.device.view",
    "maintenance.meter.view",
    "maintenance.meter.manage",
    "maintenance.meter.record",
    "maintenance.meter.ingest",
    "maintenance.workorder.create",
    "maintenance.workorder.update",
    "maintenance.workorder.route",
    "maintenance.workorder.assign",
    "maintenance.workorder.approve",
    "maintenance.workorder.list",
    "maintenance.workorder.view",
    "maintenance.workorder.logTime",
    "maintenance.costs.view",
    "maintenance.inventory.view",
    "maintenance.inventory.manage",
    "maintenance.inventory.consume",
    "maintenance.attachment.view",
    "maintenance.attachment.manage",
    "maintenance.document.view",
    "maintenance.document.upload",
    "maintenance.document.manage",
    # The supervisor authorises and closes. They can also raise and isolate,
    # because in a small plant they often do — but the self-approval guard
    # in the domain still refuses when they try to sign off their own.
    "safety.permit.view",
    "safety.permit.request",
    "safety.permit.approve",
    "safety.permit.isolate",
    "safety.permit.close",
    # The manager runs their own unit: who is in it, and (for their unit)
    # what each title may do. Creating units and positions stays with the
    # tenant administrator, who holds every action.
    "organization.department.view",
    "organization.position.view",
    "organization.assignment.view",
    "organization.assignment.manage",
    "organization.accessRule.view",
    "maintenance.workorder.export",
    "maintenance.device.export",
    "maintenance.inventory.export",
    "analytics.metric.export",
]

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
        "notification.send",
        "notification.manage",
        "ai.agent.read",
        "ai.agent.manage",
        "ai.agent.run",
        "ai.agent.approve",
        "ai.tool.invoke",
        "learning.view",
        "learning.observe",
        "learning.manage",
        "learning.run",
        "learning.approve",
        "learning.deploy",
        "learning.feedback",
        "learning.monitor",
        *_ANALYTICS_MANAGER_ACTIONS,
        "project.create",
        "project.view",
        "project.list",
        "project.update",
        "task.create",
        "task.view",
        "task.list",
        "task.update",
        *_MAINTENANCE_MANAGER_ACTIONS,
        *_PROCUREMENT_MANAGER_ACTIONS,
    ],
    MEMBER_ROLE: [
        "user.view",
        "tenant.view",
        "ai.agent.read",
        "ai.agent.run",
        "learning.view",
        "learning.observe",
        "learning.feedback",
        *_ANALYTICS_READER_ACTIONS,
        "project.view",
        "project.list",
        "task.view",
        "task.list",
        "task.create",
        "task.update",
        *_MAINTENANCE_REQUESTER_ACTIONS,
        "procurement.supplier.view",
        "procurement.requisition.create",
    ],
    MAINTENANCE_REQUESTER_ROLE: list(_MAINTENANCE_REQUESTER_ACTIONS)
    + list(_ANALYTICS_READER_ACTIONS),
    MAINTENANCE_TECHNICIAN_ROLE: list(_MAINTENANCE_TECHNICIAN_ACTIONS)
    + list(_ANALYTICS_WRITER_ACTIONS),
    MAINTENANCE_MANAGER_ROLE: list(_MAINTENANCE_MANAGER_ACTIONS)
    + list(_PROCUREMENT_MANAGER_ACTIONS)
    + list(_ANALYTICS_MANAGER_ACTIONS),
}
