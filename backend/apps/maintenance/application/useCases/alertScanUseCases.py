"""Scheduled alert scan — overdue work orders and low-stock parts.

System job (weekly-idempotent) normally driven by the
``checkMaintenanceAlerts`` management command. Open work orders that have
been open longer than their priority SLA (BR-WO-SLA) emit
``workOrderOverdue``; spare parts at/below minimum stock emit
``sparePartLowStock``. Both events carry a deterministic ``eventId`` scoped
to the ISO week, so a daily cron re-run inside the same week never creates
duplicate notifications (notification engine §29 idempotency key).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.maintenance.application.commands.maintenanceCommands import (
    RunMaintenanceAlertScanCommand,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    SparePartRepository,
    WorkOrderRepository,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    SLA_HOURS_BY_PRIORITY,
    WO_CANCELLED,
    WO_COMPLETED,
)
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.events import DomainEvent

#: Open = anything that is not a terminal status (BR-WO-001).
_OPEN_STATUSES_EXCLUDED = (WO_COMPLETED, WO_CANCELLED)


@dataclass(frozen=True)
class AlertScanItemDto:
    kind: str  # "workOrder" | "sparePart"
    itemId: str
    title: str
    detail: str


@dataclass(frozen=True)
class AlertScanRunDto:
    asOf: str
    isoWeek: str
    overdueWorkOrders: int = 0
    lowStockParts: int = 0
    items: list[AlertScanItemDto] = field(default_factory=list)


class RunMaintenanceAlertScanUseCase(UseCase):
    """Scan Open-WO SLA breaches and low stock → notification events."""

    requiredAction = ""  # system scheduler job (same pattern as SendPmReminders)

    def __init__(
        self,
        workOrderRepository: WorkOrderRepository,
        sparePartRepository: SparePartRepository,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.workOrderRepository = workOrderRepository
        self.sparePartRepository = sparePartRepository

    def perform(self, command: RunMaintenanceAlertScanCommand) -> AlertScanRunDto:
        tenantId = resolveTenantId(command.tenantId)
        now = self.clock.nowUtc()
        isoYear, isoWeek, _ = now.isocalendar()
        weekKey = f"{isoYear}-W{isoWeek:02d}"
        items: list[AlertScanItemDto] = []

        overdueCount = 0
        if command.includeWorkOrders:
            # پروجکشن خام — ردیف‌های قدیمی با واژگان امروزی نامتناسب (مثل
            # وضعیت «scheduled») نباید اجرای کرون را متوقف کنند؛ هر وضعیتِ
            # ناشناخته «باز» و هر اولویتِ ناشناخته SLA پیش‌فرض ۷۲ ساعت می‌گیرد.
            for order in self.workOrderRepository.listAlertRows(tenantId):
                if order.status in _OPEN_STATUSES_EXCLUDED:
                    continue
                slaHours = SLA_HOURS_BY_PRIORITY.get(order.priority, 72)
                ageHours = (now - order.createdAt).total_seconds() / 3600
                if ageHours < slaHours:
                    continue
                overdueCount += 1
                self._pendingEvents.append(
                    DomainEvent(
                        name="workOrderOverdue",
                        occurredAt=now,
                        tenantId=tenantId,
                        payload={
                            "eventId": f"workOrderOverdue:{order.id}:{weekKey}",
                            "sourceId": str(order.id),
                            "workOrderId": str(order.id),
                            "workOrderTitle": order.title,
                            "deviceId": str(order.deviceId),
                            "priority": order.priority,
                            "department": order.department,
                            "ageHours": int(ageHours),
                            "slaHours": slaHours,
                        },
                    )
                )
                items.append(
                    AlertScanItemDto(
                        kind="workOrder",
                        itemId=str(order.id),
                        title=order.title,
                        detail=f"{int(ageHours)} ساعت (SLA: {slaHours})",
                    )
                )

        lowStockCount = 0
        if command.includeLowStock:
            for part in self.sparePartRepository.list(tenantId):
                if not part.lowStock:
                    continue
                lowStockCount += 1
                self._pendingEvents.append(
                    DomainEvent(
                        name="sparePartLowStock",
                        occurredAt=now,
                        tenantId=tenantId,
                        payload={
                            "eventId": f"sparePartLowStock:{part.id}:{weekKey}",
                            "sourceId": str(part.id),
                            "partId": str(part.id),
                            "partCode": part.code,
                            "partName": part.name,
                            "unit": part.unit,
                            "quantityOnHand": str(part.quantityOnHand),
                            "minimumStock": str(part.minimumStock),
                        },
                    )
                )
                items.append(
                    AlertScanItemDto(
                        kind="sparePart",
                        itemId=str(part.id),
                        title=f"{part.code} — {part.name}",
                        detail=f"موجودی {part.quantityOnHand} / حداقل {part.minimumStock} {part.unit}",
                    )
                )

        return AlertScanRunDto(
            asOf=now.date().isoformat(),
            isoWeek=weekKey,
            overdueWorkOrders=overdueCount,
            lowStockParts=lowStockCount,
            items=items,
        )
