"""Maintenance value objects — closed sets for devices and work orders.

Phase 21 (Maintenance / CMMS). All codes are stable reference data; the
Persian UI labels live in the frontend localization layer, never here.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

# -- Device status ----------------------------------------------------------------
DEVICE_OPERATIONAL = "operational"
DEVICE_UNDER_MAINTENANCE = "underMaintenance"
DEVICE_OUT_OF_SERVICE = "outOfService"
DEVICE_RETIRED = "retired"

DEVICE_STATUSES = (
    DEVICE_OPERATIONAL,
    DEVICE_UNDER_MAINTENANCE,
    DEVICE_OUT_OF_SERVICE,
    DEVICE_RETIRED,
)

# -- Work order type --------------------------------------------------------------
WORK_ORDER_CORRECTIVE = "corrective"
WORK_ORDER_PREVENTIVE = "preventive"
WORK_ORDER_INSPECTION = "inspection"

WORK_ORDER_TYPES = (
    WORK_ORDER_CORRECTIVE,
    WORK_ORDER_PREVENTIVE,
    WORK_ORDER_INSPECTION,
)

# -- Work order status (lifecycle) ------------------------------------------------
WO_SUBMITTED = "submitted"
WO_ROUTED = "routed"
WO_ASSIGNED = "assigned"
WO_IN_PROGRESS = "inProgress"
WO_ON_HOLD = "onHold"
WO_PENDING_APPROVAL = "pendingApproval"
WO_COMPLETED = "completed"
WO_CANCELLED = "cancelled"

WORK_ORDER_STATUSES = (
    WO_SUBMITTED,
    WO_ROUTED,
    WO_ASSIGNED,
    WO_IN_PROGRESS,
    WO_ON_HOLD,
    WO_PENDING_APPROVAL,
    WO_COMPLETED,
    WO_CANCELLED,
)

#: Allowed lifecycle transitions (BR-WO-001). A closed set keeps the workflow
#: predictable. Two-step dispatch: a work order is first *routed* to a
#: department, then *assigned* to an individual technician. Both a completed
#: and a cancelled order are terminal.
#: A completed order requires manager approval: a technician moves work from
#: ``inProgress`` to ``pendingApproval`` (never straight to ``completed``); a
#: manager then approves (→ ``completed``) or rejects (→ ``inProgress``).
WORK_ORDER_TRANSITIONS: dict[str, tuple[str, ...]] = {
    WO_SUBMITTED: (WO_ROUTED, WO_ASSIGNED, WO_CANCELLED),
    WO_ROUTED: (WO_ASSIGNED, WO_ON_HOLD, WO_CANCELLED),
    WO_ASSIGNED: (WO_IN_PROGRESS, WO_ON_HOLD, WO_CANCELLED),
    WO_IN_PROGRESS: (WO_ON_HOLD, WO_PENDING_APPROVAL, WO_CANCELLED),
    WO_ON_HOLD: (WO_IN_PROGRESS, WO_CANCELLED),
    # From pendingApproval, completion/rework happen only through the dedicated
    # approve/reject endpoints (which enforce the approve permission); the
    # generic status endpoint may only cancel.
    WO_PENDING_APPROVAL: (WO_CANCELLED,),
    WO_COMPLETED: (),
    WO_CANCELLED: (),
}

# -- Maintenance department (closed set) ------------------------------------------
# The unit that owns a device and handles its work orders. A fixed catalogue keeps
# routing predictable; Persian labels live in the frontend localization layer.
DEPARTMENT_GENERAL = "general"
DEPARTMENT_ELECTRICAL = "electrical"
DEPARTMENT_MECHANICAL = "mechanical"
DEPARTMENT_FACILITIES = "facilities"
DEPARTMENT_INSTRUMENTATION = "instrumentation"
DEPARTMENT_HYDRAULIC = "hydraulic"
DEPARTMENT_PNEUMATIC = "pneumatic"

MAINTENANCE_DEPARTMENTS = (
    DEPARTMENT_GENERAL,
    DEPARTMENT_ELECTRICAL,
    DEPARTMENT_MECHANICAL,
    DEPARTMENT_FACILITIES,
    DEPARTMENT_INSTRUMENTATION,
    DEPARTMENT_HYDRAULIC,
    DEPARTMENT_PNEUMATIC,
)

#: The seven maintenance disciplines a PM plan can belong to (Phase 26 asset
#: registry). Identical to the department catalogue on purpose: a PM plan is
#: owned by the same unit that receives its generated work orders, so routing
#: stays consistent. Persian labels live in the frontend localization layer.
PM_DISCIPLINES = MAINTENANCE_DEPARTMENTS

# -- Equipment criticality (Phase 26) --------------------------------------------------
CRITICALITY_LOW = "low"
CRITICALITY_MEDIUM = "medium"
CRITICALITY_HIGH = "high"
CRITICALITY_VITAL = "vital"

ASSET_CRITICALITIES = (
    CRITICALITY_LOW,
    CRITICALITY_MEDIUM,
    CRITICALITY_HIGH,
    CRITICALITY_VITAL,
)

# -- Location kinds (Phase 26 hierarchical location tree) --------------------------
# A location is a node in a self-referencing tree; the kind is descriptive only,
# so depth is never capped at site → building → room.
LOCATION_SITE = "site"
LOCATION_BUILDING = "building"
LOCATION_FLOOR = "floor"
LOCATION_HALL = "hall"
LOCATION_LINE = "line"
LOCATION_ROOM = "room"
LOCATION_AREA = "area"

LOCATION_KINDS = (
    LOCATION_SITE,
    LOCATION_BUILDING,
    LOCATION_FLOOR,
    LOCATION_HALL,
    LOCATION_LINE,
    LOCATION_ROOM,
    LOCATION_AREA,
)

# -- PM plan frequency units (Phase 26) --------------------------------------------
FREQUENCY_DAY = "day"
FREQUENCY_WEEK = "week"
FREQUENCY_MONTH = "month"
FREQUENCY_RUNNING_HOUR = "runningHour"

PM_FREQUENCY_UNITS = (
    FREQUENCY_DAY,
    FREQUENCY_WEEK,
    FREQUENCY_MONTH,
    FREQUENCY_RUNNING_HOUR,
)

#: Days per frequency unit, used to normalise a PM plan's period into days.
#: ``runningHour`` has no calendar equivalent and is scheduled by meter reading.
FREQUENCY_DAYS: dict[str, int] = {
    FREQUENCY_DAY: 1,
    FREQUENCY_WEEK: 7,
    FREQUENCY_MONTH: 30,
}

# -- Device personnel assignment roles (Phase 26) ----------------------------------
ASSIGNMENT_OPERATOR = "operator"
ASSIGNMENT_RESPONSIBLE = "responsible"
ASSIGNMENT_TECHNICIAN = "technician"
ASSIGNMENT_DEPUTY = "deputy"

DEVICE_ASSIGNMENT_ROLES = (
    ASSIGNMENT_OPERATOR,
    ASSIGNMENT_RESPONSIBLE,
    ASSIGNMENT_TECHNICIAN,
    ASSIGNMENT_DEPUTY,
)

# -- Failure classification (Phase 26 reporting) -----------------------------------
FAILURE_NONE = ""
FAILURE_MECHANICAL = "mechanicalFailure"
FAILURE_ELECTRICAL = "electricalFailure"
FAILURE_WEAR = "wear"
FAILURE_LUBRICATION = "lubrication"
FAILURE_OPERATOR_ERROR = "operatorError"
FAILURE_PART_QUALITY = "partQuality"
FAILURE_MISSED_PM = "missedPm"
FAILURE_OTHER = "otherFailure"

FAILURE_TYPES = (
    FAILURE_MECHANICAL,
    FAILURE_ELECTRICAL,
    FAILURE_WEAR,
    FAILURE_LUBRICATION,
    FAILURE_OPERATOR_ERROR,
    FAILURE_PART_QUALITY,
    FAILURE_MISSED_PM,
    FAILURE_OTHER,
)

# -- Priority (shared vocabulary with tasks for consistency) -----------------------
PRIORITY_LOW = "low"
PRIORITY_NORMAL = "normal"
PRIORITY_HIGH = "high"
PRIORITY_CRITICAL = "critical"

WORK_ORDER_PRIORITIES = (
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    PRIORITY_HIGH,
    PRIORITY_CRITICAL,
)

#: SLA target — hours from submission to completion, per priority (BR-WO-SLA).
#: An open order past its target is flagged "overdue" so managers can escalate.
SLA_HOURS_BY_PRIORITY: dict[str, int] = {
    PRIORITY_CRITICAL: 4,
    PRIORITY_HIGH: 24,
    PRIORITY_NORMAL: 72,
    PRIORITY_LOW: 168,
}


@dataclass(frozen=True)
class DeviceStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in DEVICE_STATUSES:
            raise ValidationFailedError(
                "Invalid device status.", fieldErrors={"status": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class WorkOrderType(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in WORK_ORDER_TYPES:
            raise ValidationFailedError(
                "Invalid work order type.", fieldErrors={"orderType": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class WorkOrderStatus(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in WORK_ORDER_STATUSES:
            raise ValidationFailedError(
                "Invalid work order status.", fieldErrors={"status": self.value}
            )

    def __str__(self) -> str:
        return self.value

    def canTransitionTo(self, target: str) -> bool:
        return target in WORK_ORDER_TRANSITIONS.get(self.value, ())


@dataclass(frozen=True)
class WorkOrderPriority(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in WORK_ORDER_PRIORITIES:
            raise ValidationFailedError(
                "Invalid work order priority.", fieldErrors={"priority": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MaintenanceDepartment(ValueObject):
    value: str

    def __post_init__(self) -> None:
        if self.value not in MAINTENANCE_DEPARTMENTS:
            raise ValidationFailedError(
                "Invalid maintenance department.", fieldErrors={"department": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EquipmentCriticality(ValueObject):
    """How badly the plant suffers when this asset stops (Phase 26)."""

    value: str

    def __post_init__(self) -> None:
        if self.value not in ASSET_CRITICALITIES:
            raise ValidationFailedError(
                "Invalid asset criticality.", fieldErrors={"criticality": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class LocationKind(ValueObject):
    """Descriptive kind of a node in the location tree (Phase 26)."""

    value: str

    def __post_init__(self) -> None:
        if self.value not in LOCATION_KINDS:
            raise ValidationFailedError(
                "Invalid location kind.", fieldErrors={"kind": self.value}
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PmFrequency(ValueObject):
    """How often a PM plan repeats — ``every`` units of ``unit`` (Phase 26)."""

    every: int
    unit: str

    def __post_init__(self) -> None:
        if self.unit not in PM_FREQUENCY_UNITS:
            raise ValidationFailedError(
                "Invalid PM frequency unit.", fieldErrors={"frequencyUnit": self.unit}
            )
        if self.every <= 0:
            raise ValidationFailedError(
                "PM frequency must be positive.", fieldErrors={"frequencyEvery": str(self.every)}
            )

    def asDays(self) -> int | None:
        """Calendar period in days, or None for meter-based (runningHour) plans."""
        perUnit = FREQUENCY_DAYS.get(self.unit)
        return None if perUnit is None else perUnit * self.every

    def __str__(self) -> str:
        return f"{self.every}:{self.unit}"
