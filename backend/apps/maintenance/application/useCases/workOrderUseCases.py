"""Work order use cases (Phase 21) — submit, update, assign, status, list, get."""

from __future__ import annotations

import uuid

from apps.maintenance.application.commands.maintenanceCommands import (
    AssignWorkOrderCommand,
    ChangeWorkOrderStatusCommand,
    GeneratePmWorkOrdersCommand,
    RouteWorkOrderCommand,
    SubmitWorkOrderCommand,
    UpdateWorkOrderCommand,
)
from apps.maintenance.application.dto.maintenanceDtos import (
    WorkOrderDto,
    WorkOrderListDto,
    workOrderDtoFromDomain,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    GetWorkOrderQuery,
    ListWorkOrdersQuery,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceRepository,
    WorkOrderFilters,
    WorkOrderRepository,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    PRIORITY_NORMAL,
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
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError


class WorkOrderUseCaseBase(UseCase):
    def __init__(
        self,
        repository: WorkOrderRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository


class SubmitWorkOrderUseCase(UseCase):
    """Anyone with request permission can raise a work order against a device."""

    requiredAction = "maintenance.workorder.create"

    def __init__(
        self,
        repository: WorkOrderRepository,
        deviceRepository: DeviceRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.deviceRepository = deviceRepository

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
        order = WorkOrder.submit(
            tenantId=tenantId,
            deviceId=deviceId,
            title=command.title,
            description=command.description,
            orderType=WorkOrderType(command.orderType),
            priority=WorkOrderPriority(command.priority),
            department=department,
            requestedByName=command.requestedByName,
            now=self.clock.nowUtc(),
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
        return workOrderDtoFromDomain(order)


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
        return workOrderDtoFromDomain(order)


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
        order.routeToDepartment(
            MaintenanceDepartment(command.department), self.clock.nowUtc()
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
        return workOrderDtoFromDomain(order)


class AssignWorkOrderUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.assign"

    def perform(self, command: AssignWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        order.assign(command.assignedToName, self.clock.nowUtc())
        self.repository.update(order)
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order)


class ChangeWorkOrderStatusUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def validateCommand(self, command: ChangeWorkOrderStatusCommand) -> None:
        WorkOrderStatus(command.target)

    def perform(self, command: ChangeWorkOrderStatusCommand) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(command.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        order.changeStatus(command.target, command.resolutionNote, self.clock.nowUtc())
        self.repository.update(order)
        self.collectEventsFrom(order)
        self.audit(
            AUDIT_UPDATE,
            resourceType="WorkOrder",
            resourceId=str(order.id),
            tenantId=tenantId,
            after=order.snapshot(),
        )
        return workOrderDtoFromDomain(order)


class ListWorkOrdersUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.list"

    def perform(self, query: ListWorkOrdersQuery) -> WorkOrderListDto:
        tenantId = resolveTenantId("")
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
            items=[workOrderDtoFromDomain(item) for item in page.items],
            totalCount=page.totalCount,
        )


class GetWorkOrderUseCase(WorkOrderUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: GetWorkOrderQuery) -> WorkOrderDto:
        tenantId = resolveTenantId("")
        order = self.repository.getById(tenantId, uuid.UUID(query.workOrderId))
        if order is None:
            raise EntityNotFoundError("Work order not found.")
        return workOrderDtoFromDomain(order)


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
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.deviceRepository = deviceRepository

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
            # Immediately route the auto-order to the device's owning department.
            order.routeToDepartment(device.department, now)
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
            items=[workOrderDtoFromDomain(item) for item in created],
            totalCount=len(created),
        )
