"""Work order use cases (Phase 21 + Phase 22 workflow).

Phase 22 adds a full workflow layer on top of the original lifecycle:
* every transition appends a ``WorkOrderHistory`` entry (timeline),
* completion passes through a manager approval gate,
* SLA due dates / overdue flags ride on every DTO,
* an auto-assign use case routes to the device's department and picks the
  least-loaded technician.
"""

from __future__ import annotations

import uuid

from apps.maintenance.application.commands.maintenanceCommands import (
    ApproveWorkOrderCommand,
    AssignWorkOrderCommand,
    ChangeWorkOrderStatusCommand,
    GeneratePmWorkOrdersCommand,
    RejectWorkOrderCommand,
    RouteWorkOrderCommand,
    SubmitWorkOrderCommand,
    UpdateWorkOrderCommand,
)
from apps.maintenance.application.dto.maintenanceDtos import (
    DeviceMaintenanceReportDto,
    DeviceReportSummaryDto,
    WorkOrderDto,
    WorkOrderHistoryListDto,
    WorkOrderListDto,
    deviceDtoFromDomain,
    historyDtoFromDomain,
    workOrderDtoFromDomain,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    DeviceMaintenanceReportQuery,
    GetWorkOrderQuery,
    ListWorkOrderHistoryQuery,
    ListWorkOrdersQuery,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.application.services.workflowHistory import (
    HISTORY_APPROVED,
    HISTORY_ASSIGNED,
    HISTORY_REJECTED,
    HISTORY_ROUTED,
    HISTORY_STATUS_CHANGED,
    HISTORY_SUBMITTED,
    HISTORY_SUBMITTED_FOR_APPROVAL,
    recordHistory,
)
from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceRepository,
    WorkOrderFilters,
    WorkOrderHistoryRepository,
    WorkOrderRepository,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    PRIORITY_NORMAL,
    WO_PENDING_APPROVAL,
    WORK_ORDER_PREVENTIVE,
    MaintenanceDepartment,
    WorkOrderPriority,
    WorkOrderStatus,
    WorkOrderType,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import (
    AUDIT_APPROVAL,
    AUDIT_CREATE,
    AUDIT_REJECTION,
    AUDIT_UPDATE,
    UseCase,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError


class WorkOrderUseCaseBase(UseCase):
    def __init__(
        self,
        repository: WorkOrderRepository,
        historyRepository: WorkOrderHistoryRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.historyRepository = historyRepository


class SubmitWorkOrderUseCase(UseCase):
    """Anyone with request permission can raise a work order against a device."""

    requiredAction = "maintenance.workorder.create"

    def __init__(
        self,
        repository: WorkOrderRepository,
        deviceRepository: DeviceRepository,
        historyRepository: WorkOrderHistoryRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.deviceRepository = deviceRepository
        self.historyRepository = historyRepository

    def validateCommand(self, command: SubmitWorkOrderCommand) -> None:
        WorkOrderType(command.orderType)
        WorkOrderPriority(command.priority)
        if command.department:
            MaintenanceDepartment(command.department)

    def perform(self, command: SubmitWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId(command.tenantId)
        deviceId = uuid.UUID(command.deviceId)
        device = self.deviceRepository.getById(tenantId, deviceId)
        if device is None:
            raise EntityNotFoundError("Device not found.")
        # A submitted order inherits the device's owning department unless the
        # requester explicitly overrides it.
        department = (
            MaintenanceDepartment(command.department)
            if command.department
            else device.department
        )
        now = self.clock.nowUtc()
        order = WorkOrder.submit(
            tenantId=tenantId,
            deviceId=deviceId,
            title=command.title,
            description=command.description,
            orderType=WorkOrderType(command.orderType),
            priority=WorkOrderPriority(command.priority),
            department=department,
            requestedByName=command.requestedByName,
            now=now,
        )
        self.repository.create(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_SUBMITTED,
            now,
            toStatus=str(order.status),
            toDepartment=str(order.department),
            actor=command.requestedByName or "",
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_CREATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class UpdateWorkOrderUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def validateCommand(self, command: UpdateWorkOrderCommand) -> None:
        WorkOrderPriority(command.priority)

    def perform(self, command: UpdateWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        order.updateDetails(
            title=command.title,
            description=command.description,
            priority=WorkOrderPriority(command.priority),
            now=self.clock.nowUtc(),
        )
        self.repository.update(order)
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, self.clock.nowUtc())


class RouteWorkOrderUseCase(WorkOrderUseCaseBase):
    """Step 1 of dispatch — a manager routes the order to a department."""

    requiredAction = "maintenance.workorder.route"

    def validateCommand(self, command: RouteWorkOrderCommand) -> None:
        MaintenanceDepartment(command.department)

    def perform(self, command: RouteWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        previousStatus = str(order.status)
        previousDepartment = str(order.department)
        order.routeToDepartment(MaintenanceDepartment(command.department), now)
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_ROUTED,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            fromDepartment=previousDepartment,
            toDepartment=str(order.department),
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class AssignWorkOrderUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.assign"

    def perform(self, command: AssignWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        previousStatus = str(order.status)
        order.assign(command.assignedToName, now)
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_ASSIGNED,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            note=order.assignedToName,
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class AutoAssignWorkOrderUseCase(WorkOrderUseCaseBase):
    """Route to the device's department (if needed) then assign the least-loaded
    technician already working that department's open orders.

    A pragmatic rule that needs no separate technician roster: it balances load
    across the technicians the department is already using.
    """

    requiredAction = "maintenance.workorder.assign"

    def __init__(
        self,
        repository: WorkOrderRepository,
        historyRepository: WorkOrderHistoryRepository,
        deviceRepository: DeviceRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(
            repository,
            historyRepository,
            unitOfWork,
            auditRecorder,
            eventDispatcher,
            permissionGate,
            clock,
        )
        self.deviceRepository = deviceRepository

    def perform(self, command: AssignWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        # Choose the least-loaded technician among the department's current pool.
        loads = self.repository.countOpenByAssignee(tenantId, str(order.department))
        # Exclude this order's own assignee count noise by picking the min load.
        candidate = command.assignedToName.strip()
        if not candidate and loads:
            candidate = min(loads.items(), key=lambda item: item[1])[0]
        if not candidate:
            # No pool yet — surface a validation error the API maps to 400.
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "No technician available for auto-assignment; assign manually.",
                fieldErrors={"assignedToName": "noCandidate"},
            )
        previousStatus = str(order.status)
        order.assign(candidate, now)
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_ASSIGNED,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            note=f"{candidate} (خودکار)",
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class ChangeWorkOrderStatusUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def validateCommand(self, command: ChangeWorkOrderStatusCommand) -> None:
        WorkOrderStatus(command.target)

    def perform(self, command: ChangeWorkOrderStatusCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        previousStatus = str(order.status)
        # Completion is gated: a technician sends work for approval instead of
        # closing it directly.
        if command.target == WO_PENDING_APPROVAL:
            order.submitForApproval(command.resolutionNote, now)
            action = HISTORY_SUBMITTED_FOR_APPROVAL
        else:
            order.changeStatus(command.target, command.resolutionNote, now)
            action = HISTORY_STATUS_CHANGED
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            action,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            note=command.resolutionNote.strip(),
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class ApproveWorkOrderUseCase(WorkOrderUseCaseBase):
    """Manager approves a pending order → completed."""

    requiredAction = "maintenance.workorder.approve"

    def perform(self, command: ApproveWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        previousStatus = str(order.status)
        order.approve(command.note, now)
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_APPROVED,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            note=command.note.strip(),
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_APPROVAL,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class RejectWorkOrderUseCase(WorkOrderUseCaseBase):
    """Manager rejects a pending order → back to inProgress for rework."""

    requiredAction = "maintenance.workorder.approve"

    def perform(self, command: RejectWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        now = self.clock.nowUtc()
        previousStatus = str(order.status)
        order.reject(command.note, now)
        self.repository.update(order)
        recordHistory(
            self.historyRepository,
            order,
            HISTORY_REJECTED,
            now,
            fromStatus=previousStatus,
            toStatus=str(order.status),
            note=command.note.strip(),
        )
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_REJECTION,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order, now)


class ListWorkOrdersUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.list"

    def perform(self, query: ListWorkOrdersQuery) -> WorkOrderListDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        page = self.repository.list(
            WorkOrderFilters(
                tenantId=tenantId,
                deviceId=query.deviceId,
                status=query.status,
                orderType=query.orderType,
                priority=query.priority,
                department=query.department,
                search=query.search,
                ordering=query.ordering,
                page=query.page,
                pageSize=query.pageSize,
            )
        )
        return WorkOrderListDto(
            items=[workOrderDtoFromDomain(item, now) for item in page.items],
            totalCount=page.totalCount,
        )


class GetWorkOrderUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: GetWorkOrderQuery) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(query.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        return workOrderDtoFromDomain(order, self.clock.nowUtc())


class ListWorkOrderHistoryUseCase(WorkOrderUseCaseBase):
    """The ordered transition timeline for a single work order."""

    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListWorkOrderHistoryQuery) -> WorkOrderHistoryListDto:
        tenantId = resolveTenantId("")
        orderId = uuid.UUID(query.workOrderId)
        order = self.repository.getById(tenantId, orderId)
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        entries = self.historyRepository.listForOrder(tenantId, orderId)
        return WorkOrderHistoryListDto(
            items=[historyDtoFromDomain(entry) for entry in entries],
            totalCount=len(entries),
        )


class DeviceMaintenanceReportUseCase(WorkOrderUseCaseBase):
    """Assemble the full maintenance history + stats for one device (Phase 23).

    Pulls the device card and every work order raised against it within an
    optional creation-date window, then computes a statistical summary
    (counts by status/type/priority, open/completed/overdue tallies, MTTR).
    The result feeds the JSON API, the Excel/CSV exporters and the printable
    report page from a single shape.
    """

    requiredAction = "maintenance.workorder.view"

    def __init__(self, *args: object, deviceRepository: DeviceRepository, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.deviceRepository = deviceRepository

    def perform(self, query: "DeviceMaintenanceReportQuery") -> "DeviceMaintenanceReportDto":
        from datetime import datetime, time, timezone

        from django.utils.dateparse import parse_date

        tenantId = resolveTenantId("")
        deviceId = uuid.UUID(query.deviceId)
        device = self.deviceRepository.getById(tenantId, deviceId)
        if device is None:
            raise EntityNotFoundError("Device not found.")

        now = self.clock.nowUtc()

        createdFrom = None
        createdTo = None
        if query.fromDate:
            parsed = parse_date(query.fromDate)
            if parsed is not None:
                createdFrom = datetime.combine(parsed, time.min, tzinfo=timezone.utc)
        if query.toDate:
            parsed = parse_date(query.toDate)
            if parsed is not None:
                createdTo = datetime.combine(parsed, time.max, tzinfo=timezone.utc)

        # Pull every matching order (report, not a paginated list): walk pages.
        collected: list[WorkOrder] = []
        page = 1
        while True:
            result = self.repository.list(
                WorkOrderFilters(
                    tenantId=tenantId,
                    deviceId=str(deviceId),
                    ordering="-createdAt",
                    page=page,
                    pageSize=100,
                    createdFrom=createdFrom,
                    createdTo=createdTo,
                )
            )
            collected.extend(result.items)
            if len(collected) >= result.totalCount or not result.items:
                break
            page += 1

        orders = [workOrderDtoFromDomain(order, now) for order in collected]
        summary = _buildReportSummary(collected, now)

        return DeviceMaintenanceReportDto(
            device=deviceDtoFromDomain(device, now.date()),
            workOrders=orders,
            summary=summary,
            generatedAt=now.isoformat(),
            fromDate=query.fromDate,
            toDate=query.toDate,
        )


def _buildReportSummary(
    orders: "list[WorkOrder]", now: "datetime"
) -> "DeviceReportSummaryDto":
    from apps.maintenance.domain.valueObjects.maintenanceState import (
        WO_CANCELLED,
        WO_COMPLETED,
    )

    byStatus: dict[str, int] = {}
    byType: dict[str, int] = {}
    byPriority: dict[str, int] = {}
    openCount = 0
    completedCount = 0
    overdueCount = 0
    repairHoursTotal = 0.0
    repairSamples = 0

    for order in orders:
        status = str(order.status)
        byStatus[status] = byStatus.get(status, 0) + 1
        byType[str(order.orderType)] = byType.get(str(order.orderType), 0) + 1
        byPriority[str(order.priority)] = byPriority.get(str(order.priority), 0) + 1

        if status not in (WO_COMPLETED, WO_CANCELLED):
            openCount += 1
        if status == WO_COMPLETED:
            completedCount += 1
            if order.closedAt is not None:
                repairHoursTotal += (order.closedAt - order.createdAt).total_seconds() / 3600.0
                repairSamples += 1
        if order.isOverdue(now):
            overdueCount += 1

    mttr = round(repairHoursTotal / repairSamples, 1) if repairSamples else None

    return DeviceReportSummaryDto(
        totalOrders=len(orders),
        openOrders=openCount,
        completedOrders=completedCount,
        overdueOrders=overdueCount,
        byStatus=byStatus,
        byType=byType,
        byPriority=byPriority,
        mttrHours=mttr,
    )


class GeneratePmWorkOrdersUseCase(UseCase):
    """Auto-generate preventive work orders for devices whose PM is due.

    For each device whose ``isPmDue`` is true and that has no open preventive
    order yet, a ``preventive`` work order is created and routed to the device's
    owning department. Idempotent: running it repeatedly will not pile up
    duplicate orders for the same device.
    """

    requiredAction = "maintenance.workorder.create"

    def __init__(
        self,
        repository: WorkOrderRepository,
        deviceRepository: DeviceRepository,
        historyRepository: WorkOrderHistoryRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.deviceRepository = deviceRepository
        self.historyRepository = historyRepository

    def perform(self, command: GeneratePmWorkOrdersCommand) -> WorkOrderListDto:
        tenantId = resolveTenantId(command.tenantId)
        now = self.clock.nowUtc()
        asOf = now.date()
        created: list[WorkOrder] = []
        for device in self.deviceRepository.listDueForPm(tenantId):
            if not device.isPmDue(asOf):
                continue
            if self.repository.hasOpenPreventiveOrder(tenantId, device.id):
                continue
            due = device.nextDueDate()
            dueLabel = due.isoformat() if due else asOf.isoformat()
            order = WorkOrder.submit(
                tenantId=tenantId,
                deviceId=device.id,
                title=f"نگهداری پیشگیرانه دوره‌ای — {device.name}",
                description=(
                    f"این درخواست به‌صورت خودکار برای دستگاه «{device.name}» "
                    f"(کد {device.code}) ایجاد شد؛ سررسید نگهداری پیشگیرانه: {dueLabel}."
                ),
                orderType=WorkOrderType(WORK_ORDER_PREVENTIVE),
                priority=WorkOrderPriority(PRIORITY_NORMAL),
                department=device.department,
                requestedByName="سامانه (خودکار)",
                now=now,
            )
            recordHistory(
                self.historyRepository,
                order,
                HISTORY_SUBMITTED,
                now,
                toStatus=str(order.status),
                toDepartment=str(order.department),
                actor="سامانه (خودکار)",
            )
            # Immediately route the auto-order to the device's owning department.
            order.routeToDepartment(device.department, now)
            recordHistory(
                self.historyRepository,
                order,
                HISTORY_ROUTED,
                now,
                toStatus=str(order.status),
                toDepartment=str(order.department),
                actor="سامانه (خودکار)",
            )
            self.repository.create(order)
            self.collectEventsFrom(order)
            self.audit(
                AUDIT_CREATE,
                resourceType="WorkOrder",
                resourceId=str(order.id),
                tenantId=tenantId,
                after=order.snapshot(),
            )
            created.append(order)
        return WorkOrderListDto(
            items=[workOrderDtoFromDomain(item, now) for item in created],
            totalCount=len(created),
        )
