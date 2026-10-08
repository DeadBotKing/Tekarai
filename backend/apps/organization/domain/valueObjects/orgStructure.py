"""The vocabulary of the organisation chart: units, positions, verbs, scopes.

This module fixes the words the rest of the context argues in. Three ideas
carry the whole design:

1. **A permission is a verb, not a role.** "مدیر است پس دسترسی دارد" cannot
   be audited and cannot be changed without arguing about job titles. A
   grant here is always ``capability × action`` — «دستور کار × تأیید» —
   which can be read, granted and revoked one cell at a time.

2. **A permission without a scope is half a permission.** "Can view work
   orders" is not an answer; *whose* work orders is. Scope (own / team /
   department / all) is stored on every grant, not bolted on afterwards.

3. **Departments and positions are data, not code.** A plant that opens a
   «آزمایشگاه» unit or invents a «سرپرست شیفت» title must not need a
   developer. Nothing in this module hardcodes the five starting units; they
   are a seed, and the seed is deletable.

What is deliberately *not* data: the capability catalogue and the action
verbs. Those correspond to code paths that must actually exist and be
enforced — inventing «دستور کار × پرواز» in a form would produce a
permission nothing checks, which is worse than no permission at all.
"""

from __future__ import annotations

# --- Scope: whose records does this grant reach? ---------------------------

SCOPE_OWN = "own"
SCOPE_TEAM = "team"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"

SCOPES = (SCOPE_OWN, SCOPE_TEAM, SCOPE_DEPARTMENT, SCOPE_ALL)

SCOPE_LABELS_FA = {
    SCOPE_OWN: "فقط موارد خودش",
    SCOPE_TEAM: "تیم خودش",
    SCOPE_DEPARTMENT: "کل واحد",
    SCOPE_ALL: "همه واحدها",
}

#: Ordered weakest → strongest. The ordering is the rule: when a user picks
#: up the same permission from more than one place, the widest scope wins.
#: Narrowing by accident is the failure mode that makes people share
#: accounts, which destroys the audit trail this whole system exists for.
SCOPE_RANK = {SCOPE_OWN: 0, SCOPE_TEAM: 1, SCOPE_DEPARTMENT: 2, SCOPE_ALL: 3}


def widestScope(first: str, second: str) -> str:
    """The more permissive of two scopes."""
    return first if SCOPE_RANK.get(first, -1) >= SCOPE_RANK.get(second, -1) else second


def scopeCovers(granted: str, required: str) -> bool:
    """Does a grant at ``granted`` satisfy a need for ``required``?"""
    return SCOPE_RANK.get(granted, -1) >= SCOPE_RANK.get(required, 99)


# --- Action verbs ----------------------------------------------------------

ACTION_VIEW = "view"
ACTION_CREATE = "create"
ACTION_EDIT = "edit"
ACTION_DELETE = "delete"
ACTION_APPROVE = "approve"
ACTION_ASSIGN = "assign"
ACTION_CLOSE = "close"
ACTION_EXPORT = "export"

ACTIONS = (
    ACTION_VIEW,
    ACTION_CREATE,
    ACTION_EDIT,
    ACTION_DELETE,
    ACTION_APPROVE,
    ACTION_ASSIGN,
    ACTION_CLOSE,
    ACTION_EXPORT,
)

ACTION_LABELS_FA = {
    ACTION_VIEW: "مشاهده",
    ACTION_CREATE: "ایجاد",
    ACTION_EDIT: "ویرایش",
    ACTION_DELETE: "حذف",
    ACTION_APPROVE: "تأیید",
    ACTION_ASSIGN: "تخصیص",
    ACTION_CLOSE: "بستن",
    ACTION_EXPORT: "خروجی",
}

#: Verbs that change or release something. They are called out so the UI can
#: warn before granting them wholesale, and so «دسترسی کامل» in a seed is a
#: visible decision rather than a checkbox nobody read.
DESTRUCTIVE_ACTIONS = (ACTION_DELETE, ACTION_APPROVE, ACTION_CLOSE)


# --- Capabilities: the things a grant can be about -------------------------
#
# Each capability maps one (capability, action) cell to the *existing*
# enforced action codes. That mapping is the honest part of this design: the
# grid the administrator sees is not a parallel permission system, it is a
# readable front end onto the codes the API already checks. A cell with no
# codes would be a lie — a tick that grants nothing — so every cell listed
# here resolves to at least one real code.

CAPABILITIES: tuple[dict, ...] = (
    {
        "key": "workOrder",
        "labelFa": "دستور کار",
        "group": "نگهداری و تعمیرات",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("maintenance.workorder.list", "maintenance.workorder.view"),
            ACTION_CREATE: ("maintenance.workorder.create",),
            ACTION_EDIT: ("maintenance.workorder.update",),
            ACTION_DELETE: ("maintenance.workorder.delete",),
            ACTION_APPROVE: ("maintenance.workorder.approve",),
            ACTION_ASSIGN: ("maintenance.workorder.assign",),
            ACTION_CLOSE: ("maintenance.workorder.close",),
            ACTION_EXPORT: ("maintenance.workorder.export",),
        },
    },
    {
        "key": "device",
        "labelFa": "تجهیزات",
        "group": "نگهداری و تعمیرات",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("maintenance.device.list", "maintenance.device.view"),
            ACTION_CREATE: ("maintenance.device.manage",),
            ACTION_EDIT: ("maintenance.device.manage",),
            ACTION_EXPORT: ("maintenance.device.export",),
        },
    },
    {
        "key": "preventiveMaintenance",
        "labelFa": "نگهداری پیشگیرانه",
        "group": "نگهداری و تعمیرات",
        "scoped": False,
        "actions": {
            # PM schedules are part of the equipment record in this
            # codebase, so the PM row reuses the device codes rather than
            # inventing `maintenance.pm.*` codes nothing would check.
            ACTION_VIEW: ("maintenance.device.view",),
            ACTION_CREATE: ("maintenance.device.manage",),
            ACTION_EDIT: ("maintenance.device.manage",),
        },
    },
    {
        "key": "inventory",
        "labelFa": "انبار قطعات",
        "group": "انبار و خرید",
        "scoped": False,
        "actions": {
            ACTION_VIEW: ("maintenance.inventory.view",),
            ACTION_CREATE: ("maintenance.inventory.manage",),
            ACTION_EDIT: ("maintenance.inventory.manage",),
            ACTION_EXPORT: ("maintenance.inventory.export",),
        },
    },
    {
        "key": "purchaseRequisition",
        "labelFa": "درخواست خرید",
        "group": "انبار و خرید",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("procurement.supplier.view",),
            ACTION_CREATE: ("procurement.requisition.create",),
            ACTION_APPROVE: ("procurement.requisition.approve",),
        },
    },
    {
        "key": "purchaseOrder",
        "labelFa": "سفارش خرید",
        "group": "انبار و خرید",
        "scoped": False,
        "actions": {
            ACTION_VIEW: ("procurement.supplier.view",),
            ACTION_CREATE: ("procurement.purchaseOrder.create",),
            ACTION_APPROVE: ("procurement.purchaseOrder.approve",),
        },
    },
    {
        "key": "permitToWork",
        "labelFa": "مجوز کار",
        "group": "ایمنی",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("safety.permit.view",),
            ACTION_CREATE: ("safety.permit.request",),
            ACTION_APPROVE: ("safety.permit.approve",),
            ACTION_ASSIGN: ("safety.permit.isolate",),
            ACTION_CLOSE: ("safety.permit.close",),
        },
    },
    {
        "key": "report",
        "labelFa": "گزارش‌ها",
        "group": "گزارش و تحلیل",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("analytics.metricReading.view", "analytics.metricDefinition.view"),
            ACTION_EXPORT: ("analytics.metric.export",),
        },
    },
    {
        "key": "organizationUnit",
        "labelFa": "تنظیمات واحد",
        "group": "مدیریت سازمان",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("organization.department.view",),
            ACTION_EDIT: ("organization.department.manage",),
        },
    },
    {
        "key": "unitMembers",
        "labelFa": "کاربران واحد",
        "group": "مدیریت سازمان",
        "scoped": True,
        "actions": {
            ACTION_VIEW: ("organization.assignment.view",),
            ACTION_CREATE: ("organization.assignment.manage",),
            ACTION_EDIT: ("organization.assignment.manage",),
            ACTION_DELETE: ("organization.assignment.manage",),
        },
    },
    {
        "key": "accessMatrix",
        "labelFa": "ماتریس دسترسی",
        "group": "مدیریت سازمان",
        "scoped": False,
        "actions": {
            ACTION_VIEW: ("organization.accessRule.view",),
            ACTION_EDIT: ("organization.accessRule.manage",),
        },
    },
)

CAPABILITY_BY_KEY = {item["key"]: item for item in CAPABILITIES}
CAPABILITY_KEYS = tuple(item["key"] for item in CAPABILITIES)


def actionsFor(capabilityKey: str) -> tuple[str, ...]:
    """The verbs this capability actually supports, in catalogue order."""
    capability = CAPABILITY_BY_KEY.get(capabilityKey)
    if capability is None:
        return ()
    return tuple(action for action in ACTIONS if action in capability["actions"])


def actionCodesFor(capabilityKey: str, action: str) -> tuple[str, ...]:
    """The enforced action codes one grid cell stands for.

    Empty means the cell does not exist. Callers must treat that as "grant
    nothing" rather than "grant everything" — fail closed.
    """
    capability = CAPABILITY_BY_KEY.get(capabilityKey)
    if capability is None:
        return ()
    return tuple(capability["actions"].get(action, ()))


def isScoped(capabilityKey: str) -> bool:
    """Whether scope means anything for this capability.

    Some things are not owned by anybody — a spare-parts catalogue is the
    plant's, not a department's. Offering a scope selector there invites an
    administrator to set «فقط خودش» and quietly break the warehouse.
    """
    capability = CAPABILITY_BY_KEY.get(capabilityKey)
    return bool(capability and capability["scoped"])


def defaultScopeFor(capabilityKey: str) -> str:
    """Scope to assume when a rule does not state one."""
    return SCOPE_DEPARTMENT if isScoped(capabilityKey) else SCOPE_ALL


# --- Seed data -------------------------------------------------------------
#
# A starting point, not a schema. Every row below can be renamed, deactivated
# or deleted from the UI, and new ones added without touching code.

DEFAULT_DEPARTMENTS: tuple[tuple[str, str], ...] = (
    ("ENG", "فنی و مهندسی"),
    ("QC", "QC"),
    ("QA", "QA"),
    ("HSE", "ایمنی و بهداشت (HSE)"),
    ("PROD", "تولید"),
)

#: ``level`` orders seniority. It is *not* an authority ladder on its own —
#: nothing in the evaluator reads it to grant anything — it only sorts the
#: matrix columns so «مدیر» is not printed after «اپراتور», and gives the
#: team-scope rule a way to recognise who is senior inside one unit.
DEFAULT_POSITIONS: tuple[tuple[str, str, int], ...] = (
    ("MGR", "مدیر", 100),
    ("HEAD", "رئیس", 80),
    ("SUPERVISOR", "سرپرست", 60),
    ("SPECIALIST", "کارشناس", 40),
    ("TECHNICIAN", "تکنسین", 20),
    ("OPERATOR", "اپراتور", 10),
)

#: The example matrix from the brief, as the shipped default for a technical
#: unit. It is seeded once per department and is then the plant's to edit —
#: the point of the feature is that this table lives in the database.
#:
#: Read it as: position code → capability → {action: scope}.
#: Seed matrix. Note that «مدیر» is scoped to `department`, not `all`: a
#: unit manager runs his unit. Plant-wide sight is a different job — «مدیر
#: کارخانه» — and an administrator creates that position and grants it
#: `all` deliberately. Defaulting every manager to `all` would mean the
#: first person given the title could read every unit in the factory, which
#: is precisely the collapse of «واحد» this design exists to prevent.
DEFAULT_ACCESS_MATRIX: dict[str, dict[str, dict[str, str]]] = {
    "MGR": {
        "workOrder": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_EDIT: SCOPE_DEPARTMENT,
            ACTION_DELETE: SCOPE_DEPARTMENT,
            ACTION_APPROVE: SCOPE_DEPARTMENT,
            ACTION_ASSIGN: SCOPE_DEPARTMENT,
            ACTION_CLOSE: SCOPE_DEPARTMENT,
            ACTION_EXPORT: SCOPE_DEPARTMENT,
        },
        "device": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_EDIT: SCOPE_DEPARTMENT,
            ACTION_EXPORT: SCOPE_DEPARTMENT,
        },
        "preventiveMaintenance": {
            ACTION_VIEW: SCOPE_ALL,
            ACTION_CREATE: SCOPE_ALL,
            ACTION_EDIT: SCOPE_ALL,
        },
        "inventory": {ACTION_VIEW: SCOPE_ALL, ACTION_EXPORT: SCOPE_ALL},
        "purchaseRequisition": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_APPROVE: SCOPE_DEPARTMENT,
        },
        "permitToWork": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_CREATE: SCOPE_DEPARTMENT},
        "report": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_EXPORT: SCOPE_DEPARTMENT},
        "organizationUnit": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_EDIT: SCOPE_DEPARTMENT},
        "unitMembers": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_EDIT: SCOPE_DEPARTMENT,
            ACTION_DELETE: SCOPE_DEPARTMENT,
        },
    },
    "HEAD": {
        "workOrder": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_EDIT: SCOPE_DEPARTMENT,
            ACTION_APPROVE: SCOPE_DEPARTMENT,
            ACTION_ASSIGN: SCOPE_DEPARTMENT,
            ACTION_CLOSE: SCOPE_DEPARTMENT,
            ACTION_EXPORT: SCOPE_DEPARTMENT,
        },
        "device": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_EDIT: SCOPE_DEPARTMENT},
        "preventiveMaintenance": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_DEPARTMENT,
            ACTION_EDIT: SCOPE_DEPARTMENT,
        },
        "inventory": {ACTION_VIEW: SCOPE_ALL},
        "purchaseRequisition": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_CREATE: SCOPE_DEPARTMENT},
        "permitToWork": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_CREATE: SCOPE_DEPARTMENT},
        "report": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_EXPORT: SCOPE_DEPARTMENT},
        "organizationUnit": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_EDIT: SCOPE_DEPARTMENT},
        "unitMembers": {ACTION_VIEW: SCOPE_DEPARTMENT},
    },
    "SUPERVISOR": {
        "workOrder": {
            ACTION_VIEW: SCOPE_TEAM,
            ACTION_CREATE: SCOPE_TEAM,
            ACTION_EDIT: SCOPE_TEAM,
            ACTION_ASSIGN: SCOPE_TEAM,
            ACTION_CLOSE: SCOPE_TEAM,
        },
        "device": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "preventiveMaintenance": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "inventory": {ACTION_VIEW: SCOPE_ALL},
        "purchaseRequisition": {ACTION_VIEW: SCOPE_TEAM, ACTION_CREATE: SCOPE_TEAM},
        "permitToWork": {
            ACTION_VIEW: SCOPE_TEAM,
            ACTION_CREATE: SCOPE_TEAM,
            ACTION_ASSIGN: SCOPE_TEAM,
        },
        "report": {ACTION_VIEW: SCOPE_TEAM},
    },
    "SPECIALIST": {
        "workOrder": {
            ACTION_VIEW: SCOPE_DEPARTMENT,
            ACTION_CREATE: SCOPE_OWN,
            ACTION_EDIT: SCOPE_OWN,
        },
        "device": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "preventiveMaintenance": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "inventory": {ACTION_VIEW: SCOPE_ALL},
        "permitToWork": {ACTION_VIEW: SCOPE_DEPARTMENT, ACTION_CREATE: SCOPE_OWN},
        "report": {ACTION_VIEW: SCOPE_DEPARTMENT},
    },
    # The brief's technician row: view and create, edit only their own work
    # order, and nothing else. «Edit فقط WO خودش» is exactly ``edit`` at
    # ``own`` scope — the reason scope is part of the grant and not a
    # separate feature.
    "TECHNICIAN": {
        "workOrder": {ACTION_VIEW: SCOPE_OWN, ACTION_EDIT: SCOPE_OWN},
        "device": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "inventory": {ACTION_VIEW: SCOPE_ALL},
        "permitToWork": {
            ACTION_VIEW: SCOPE_OWN,
            ACTION_CREATE: SCOPE_OWN,
            ACTION_ASSIGN: SCOPE_OWN,
        },
    },
    "OPERATOR": {
        "workOrder": {ACTION_VIEW: SCOPE_OWN, ACTION_CREATE: SCOPE_OWN},
        "device": {ACTION_VIEW: SCOPE_DEPARTMENT},
        "permitToWork": {ACTION_VIEW: SCOPE_OWN},
    },
}


DEPARTMENT_STATUS_ACTIVE = "active"
DEPARTMENT_STATUS_INACTIVE = "inactive"
DEPARTMENT_STATUSES = (DEPARTMENT_STATUS_ACTIVE, DEPARTMENT_STATUS_INACTIVE)

STATUS_LABELS_FA = {
    DEPARTMENT_STATUS_ACTIVE: "فعال",
    DEPARTMENT_STATUS_INACTIVE: "غیرفعال",
}
