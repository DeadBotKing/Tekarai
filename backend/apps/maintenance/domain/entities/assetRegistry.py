"""Equipment-registry entities (Phase 26).

The registry models equipment master data as *independent* records that are
linked to a device, never as text buried inside it:

* ``MaintenanceLocation`` — one node of a self-referencing location tree, so a
  device can sit at site → building → floor → hall → line → room without the
  depth being capped.
* ``MaintenancePersonnel`` — the maintenance workforce directory; the same
  person can be attached to many devices, PM plans and work orders.
* ``DeviceSpecification`` — a user-defined technical attribute, because a
  compressor and a PLC do not share one fixed nameplate form.
* ``PmPlan`` / ``PmExecution`` — the recurring *rule* and each actual *run* of
  it, kept apart so PM compliance can be measured honestly.
* ``DeviceBomItem`` — the many-to-many link between a device and a shared
  spare part, carrying the standard quantity for that fitment.
* ``DeviceAssignment`` — who is attached to a device, in which role, over which
  dates, so responsibility history survives staff changes.

All records are tenant-scoped, immutable value snapshots; mutation happens
through repositories in the application layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from apps.maintenance.domain.services.meterReadingRules import (
    TriggerEvaluation,
    evaluatePlanTrigger,
)
from apps.maintenance.domain.valueObjects.maintenanceState import FREQUENCY_DAYS
from apps.maintenance.domain.valueObjects.meterTypes import (
    TRIGGER_CALENDAR,
    TRIGGER_CONDITION,
    TRIGGER_METER,
)


@dataclass(frozen=True)
class MaintenanceLocation:
    """One node of the hierarchical location tree."""

    id: uuid.UUID
    tenantId: uuid.UUID
    code: str
    name: str
    kind: str
    parentId: uuid.UUID | None = None
    path: str = ""
    note: str = ""
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    def displayPath(self) -> str:
        return self.path or self.name


@dataclass(frozen=True)
class MaintenancePersonnel:
    """A maintenance technician / engineer in the workforce directory."""

    id: uuid.UUID
    tenantId: uuid.UUID
    personnelCode: str
    fullName: str
    specialty: str
    unit: str = ""
    phone: str = ""
    shift: str = ""
    skills: tuple[str, ...] = ()
    certifications: tuple[str, ...] = ()
    active: bool = True
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


@dataclass(frozen=True)
class DeviceSpecification:
    """One user-defined technical attribute of a device."""

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    label: str
    value: str = ""
    unit: str = ""
    sortOrder: int = 0

    def formatted(self) -> str:
        return f"{self.value} {self.unit}".strip()


@dataclass(frozen=True)
class PmPlan:
    """A recurring preventive-maintenance rule owned by one discipline.

    A plan fires on one of three triggers:

    * ``calendar``  — every N days/weeks/months since the last execution;
    * ``meter``     — every N meter units (running hours, kWh, cycles) since
      the meter value recorded at the last execution;
    * ``condition`` — when a measured value crosses a threshold.

    The meter and condition triggers are driven by a ``MeterPoint`` on the same
    device, identified by ``metricType`` (its code). Before meter readings
    existed, a ``runningHour`` plan could be saved but could never become due,
    because its period had no calendar equivalent — the plan was inert. Meter
    readings supply the missing input, and ``meterDueStatus`` is the rule that
    turns them into a due date.
    """

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    title: str
    discipline: str
    description: str = ""
    checklist: tuple[str, ...] = ()
    frequencyEvery: int = 1
    frequencyUnit: str = "month"
    estimatedMinutes: int = 0
    responsibleName: str = ""
    lastExecutedOn: date | None = None
    active: bool = True
    # -- Meter / condition trigger ------------------------------------------------
    triggerType: str = TRIGGER_CALENDAR
    #: Code of the MeterPoint that drives this plan (empty for calendar plans).
    metricType: str = ""
    #: "Every N units" for a meter trigger.
    metricInterval: Decimal = Decimal("0")
    thresholdOperator: str = ">="
    thresholdValue: Decimal = Decimal("0")
    #: Lead distance for a warning before the trigger actually trips.
    warningValue: Decimal = Decimal("0")
    metricUnit: str = ""
    #: Optional direct sensor binding, when the plan watches a raw gateway tag.
    sensorKey: str = ""
    #: Latest observed meter value, denormalised for list screens.
    lastMetricValue: Decimal | None = None
    #: Meter value at the last execution — the baseline a meter trigger counts from.
    lastExecutedMeterValue: Decimal | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    @property
    def isMeterDriven(self) -> bool:
        """True when due-ness comes from readings rather than the calendar."""
        return self.triggerType in (TRIGGER_METER, TRIGGER_CONDITION)

    def periodDays(self) -> int | None:
        """Calendar period in days; None for meter-driven plans."""
        if self.isMeterDriven:
            return None
        perUnit = FREQUENCY_DAYS.get(self.frequencyUnit)
        return None if perUnit is None else perUnit * max(1, self.frequencyEvery)

    def nextDueOn(self) -> date | None:
        """Derived next due date — None when never executed or meter-driven."""
        period = self.periodDays()
        if period is None or self.lastExecutedOn is None:
            return None
        from datetime import timedelta

        return self.lastExecutedOn + timedelta(days=period)

    def meterDueStatus(self, currentValue: Decimal | None = None) -> TriggerEvaluation:
        """Where this plan stands against the meter.

        Falls back to ``lastMetricValue`` so a caller that has not loaded the
        meter point still gets the last known answer instead of nothing.
        """
        reading = currentValue if currentValue is not None else self.lastMetricValue
        return evaluatePlanTrigger(self, reading)

    def isMeterOverdue(self, currentValue: Decimal | None = None) -> bool:
        return bool(self.active and self.meterDueStatus(currentValue).isDue)

    def isOverdue(self, asOf: date, currentValue: Decimal | None = None) -> bool:
        """Overdue by whichever rule governs this plan.

        Previously a ``runningHour`` plan always answered ``False`` here: its
        period was ``None``, so the calendar branch could never trip and no
        other branch existed. Meter-driven plans now answer from the meter.
        """
        if not self.active:
            return False
        if self.isMeterDriven:
            return self.meterDueStatus(currentValue).isDue
        due = self.nextDueOn()
        # Due today counts as overdue: the period has been fully consumed and
        # the job has not been done, which is what the schedule feed reports.
        return bool(due is not None and asOf >= due)


@dataclass(frozen=True)
class PmExecution:
    """One completed run of a PM plan — the fact behind compliance reporting."""

    id: uuid.UUID
    tenantId: uuid.UUID
    planId: uuid.UUID
    deviceId: uuid.UUID
    discipline: str
    performedOn: date
    dueOn: date | None = None
    onTime: bool = True
    performedByName: str = ""
    durationMinutes: int = 0
    findings: str = ""
    workOrderId: uuid.UUID | None = None
    #: Meter value at the moment of execution. This is what resets a
    #: meter-driven plan's clock, the way ``performedOn`` resets a calendar
    #: plan's — without it an "every 500 hours" plan could never start a new
    #: cycle and would stay permanently due after its first execution.
    meterValue: Decimal | None = None
    createdAt: datetime | None = None


@dataclass(frozen=True)
class DeviceBomItem:
    """A spare part fitted to a device, with its standard quantity."""

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    partId: uuid.UUID
    partCode: str = ""
    partName: str = ""
    unit: str = ""
    position: str = ""
    standardQuantity: Decimal = Decimal("1")
    note: str = ""
    quantityOnHand: Decimal = Decimal("0")
    minimumStock: Decimal = Decimal("0")

    @property
    def lowStock(self) -> bool:
        return self.quantityOnHand <= self.minimumStock


@dataclass(frozen=True)
class DeviceAssignment:
    """Who is attached to a device, in which role, over which period."""

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    role: str
    personnelId: uuid.UUID | None = None
    personnelName: str = ""
    unit: str = ""
    fromDate: date | None = None
    toDate: date | None = None

    def isCurrent(self, asOf: date) -> bool:
        if self.fromDate and asOf < self.fromDate:
            return False
        return not (self.toDate and asOf > self.toDate)


@dataclass(frozen=True)
class DeviceRegistryProfile:
    """Everything the registry knows about one device, assembled for reading."""

    specifications: list[DeviceSpecification] = field(default_factory=list)
    pmPlans: list[PmPlan] = field(default_factory=list)
    bom: list[DeviceBomItem] = field(default_factory=list)
    assignments: list[DeviceAssignment] = field(default_factory=list)
    location: MaintenanceLocation | None = None
    children: list[tuple[uuid.UUID, str, str]] = field(default_factory=list)
