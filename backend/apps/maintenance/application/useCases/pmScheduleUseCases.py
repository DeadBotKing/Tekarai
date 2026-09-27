"""PM calendar schedule (برنامه‌ی زمان‌بندی PM تقویمی) — Phase 27.

A single cross-device read model for the maintenance calendar: the UI draws
one Jalali month grid and asks the API for every upcoming PM in that window.
Two event sources are merged — never double-counted:

1. **PM plans** (the recurring rules on each device): active plans whose
   derived ``nextDueOn`` falls inside the requested window, *plus* every
   overdue plan regardless of date, *plus* never-executed plans so they show
   up in the sidebar as undated.
2. **Device-level legacy PM** (``pmIntervalDays``): only for devices that
   carry no active plan at all, so a device covered by a named plan does not
   appear twice.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from apps.maintenance.application.dto.registryDtos import PmScheduleItemDto
from apps.maintenance.application.services.tenantResolver import (
    parseDateOrNone,
    resolveTenantId,
)
from apps.maintenance.application.useCases.registryUseCases import (
    PERMISSION_REGISTRY_VIEW,
    RegistryUseCaseBase,
)
from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.repositories.maintenanceRepositories import DeviceFilters

# Window shape: the calendar page always passes fromDate/toDate explicitly;
# these defaults only guard direct API callers.
DEFAULT_WINDOW_DAYS = 60
DEVICE_PAGE_SIZE = 500


@dataclass(frozen=True)
class GetPmScheduleQuery:
    fromDate: str = ""
    toDate: str = ""
    discipline: str = ""


class GetPmScheduleUseCase(RegistryUseCaseBase):
    """Aggregated upcoming-PM feed for the maintenance calendar."""

    requiredAction = PERMISSION_REGISTRY_VIEW

    def perform(self, query: GetPmScheduleQuery) -> list[PmScheduleItemDto]:
        tenantId = resolveTenantId("")
        asOf = self.clock.nowUtc().date()
        startDay = parseDateOrNone(query.fromDate) or asOf
        endDay = parseDateOrNone(query.toDate) or asOf + timedelta(days=DEFAULT_WINDOW_DAYS)
        discipline = query.discipline.strip()

        plans = [
            plan
            for plan in self.registryRepository.listPlans(tenantId, discipline=discipline)
            if plan.active
        ]

        # Join device code/name onto each plan row (Device is the display
        # context of a PM), paged so large plants are not clipped.
        deviceById: dict[uuid.UUID, Device] = {}
        page = 1
        while True:
            devicePage = self.deviceRepository.list(
                DeviceFilters(tenantId=tenantId, page=page, pageSize=DEVICE_PAGE_SIZE)
            )
            for device in devicePage.items:
                deviceById[device.id] = device
            if not devicePage.items or len(deviceById) >= devicePage.totalCount:
                break
            page += 1

        items: list[PmScheduleItemDto] = []
        plannedDeviceIds: set[uuid.UUID] = set()
        for plan in plans:
            plannedDeviceIds.add(plan.deviceId)
            device = deviceById.get(plan.deviceId)
            due = plan.nextDueOn()
            overdue = plan.isOverdue(asOf)
            # In-window, overdue-anytime, or undated (due=None) — else omit.
            if due is not None and not overdue and not (startDay <= due <= endDay):
                continue
            items.append(
                PmScheduleItemDto(
                    id=str(plan.id),
                    source="plan",
                    planId=str(plan.id),
                    deviceId=str(plan.deviceId),
                    deviceCode=device.code if device is not None else "",
                    deviceName=device.name if device is not None else "",
                    title=plan.title,
                    discipline=plan.discipline,
                    responsibleName=plan.responsibleName,
                    estimatedMinutes=plan.estimatedMinutes,
                    periodDays=plan.periodDays() or 0,
                    dueOn=due.isoformat() if due else "",
                    overdue=overdue,
                )
            )

        # Legacy device-level PM — only for devices with no active plan.
        for device in deviceById.values():
            deviceId = device.id
            if deviceId in plannedDeviceIds:
                continue
            department = str(device.department)
            if discipline and department != discipline:
                continue
            due = device.nextDueDate()
            if due is None:
                continue
            overdue = asOf > due
            if not overdue and not (startDay <= due <= endDay):
                continue
            interval = device.pmIntervalDays
            items.append(
                PmScheduleItemDto(
                    id=f"device-{deviceId}",
                    source="device",
                    deviceId=str(deviceId),
                    deviceCode=device.code,
                    deviceName=device.name,
                    title=f"PM بازه‌ای هر {interval} روز",
                    discipline=department,
                    periodDays=interval,
                    dueOn=due.isoformat() if isinstance(due, date) else "",
                    overdue=overdue,
                )
            )

        items.sort(key=lambda item: (0 if item.overdue else 1, item.dueOn or "9999-99-99"))
        return items
