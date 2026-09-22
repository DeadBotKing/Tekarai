"""Work order use cases (Phase 21) — submit, update, assign, status, list, get."""

from __future__ import annotations

import uuid

from apps.maintenance.application.commands.maintenanceCommands import (
    AssignWorkOrderCommand,
    ChangeWorkOrderStatusCommand,
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

    def perform(self, command: SubmitWorkOrderCommand) -> WorkOrderDto:
        tenantId = resolveTenantId(command.tenantId)
        deviceId = uuid.UUID(command.deviceId)
        device = self.deviceRepository.getById(tenantId, deviceId)
        if device is None:
            raise EntityNotFoundError("Device not found.")
        order = WorkOrder.submit(
            tenantId=tenantId,
            deviceId=deviceId,
            title=command.title,
            description=command.description,
            orderType=WorkOrderType(command.orderType),
            priority=WorkOrderPriority(command.priority),
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
