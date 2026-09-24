"""Device use cases (Phase 21) — register, update, status, PM, list, get."""

from __future__ import annotations

import uuid

from apps.maintenance.application.commands.maintenanceCommands import (
    ChangeDeviceStatusCommand,
    RecordDevicePmCommand,
    RegisterDeviceCommand,
    UpdateDeviceCommand,
)
from apps.maintenance.application.dto.maintenanceDtos import (
    DeviceDto,
    DeviceListDto,
    DeviceTimelineDto,
    DeviceTimelineItemDto,
    deviceDtoFromDomain,
    deviceHistoryTimelineItem,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    GetDeviceQuery,
    GetDeviceTimelineQuery,
    ListDevicesQuery,
    ListDuePmQuery,
)
from apps.maintenance.application.services.tenantResolver import (
    parseDateOrToday,
    resolveTenantId,
)
from apps.maintenance.application.services.deviceHistory import (
    DEVICE_HISTORY_PM_COMPLETED,
    DEVICE_HISTORY_REGISTERED,
    DEVICE_HISTORY_STATUS_CHANGED,
    DEVICE_HISTORY_UPDATED,
    recordDeviceHistory,
)
from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceFilters,
    DeviceHistoryRepository,
    DeviceRepository,
    WorkOrderFilters,
    WorkOrderRepository,
)
from apps.maintenance.domain.valueObjects.maintenanceState import (
    DEPARTMENT_GENERAL,
    DeviceStatus,
    MaintenanceDepartment,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError, EntityNotFoundError


class DeviceUseCaseBase(UseCase):
    """Common wiring for device use cases."""

    def __init__(
        self,
        repository: DeviceRepository,
        historyRepository: DeviceHistoryRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.historyRepository = historyRepository


class RegisterDeviceUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.manage"

    def validateCommand(self, command: RegisterDeviceCommand) -> None:
        pass

    def perform(self, command: RegisterDeviceCommand) -> DeviceDto:
        tenantId = resolveTenantId(command.tenantId)
        existing = self.repository.getByCode(tenantId, command.code.strip())
        if existing is not None:
            raise DuplicateBusinessCodeError(f"A device with code '{command.code}' already exists.")
        device = Device.create(
            tenantId=tenantId,
            code=command.code,
            name=command.name,
            location=command.location,
            department=MaintenanceDepartment(command.department or DEPARTMENT_GENERAL),
            pmIntervalDays=int(command.pmIntervalDays),
            now=self.clock.nowUtc(),
        )
        self.repository.create(device)
        recordDeviceHistory(
            self.historyRepository,
            device,
            DEVICE_HISTORY_REGISTERED,
            self.clock.nowUtc(),
            toStatus=str(device.status),
        )
        self.collectEventsFrom(device)
        self.audit(
            AUDIT_CREATE,
            resourceType="Device",
            resourceId=str(device.id),
            tenantId=tenantId,
            after=device.snapshot(),
        )
        return deviceDtoFromDomain(device, self.clock.nowUtc().date())


class UpdateDeviceUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.manage"

    def perform(self, command: UpdateDeviceCommand) -> DeviceDto:
        tenantId = resolveTenantId("")
        device = self.repository.getById(tenantId, uuid.UUID(command.deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        now = self.clock.nowUtc()
        device.updateDetails(
            name=command.name,
            location=command.location,
            department=MaintenanceDepartment(command.department or DEPARTMENT_GENERAL),
            pmIntervalDays=int(command.pmIntervalDays),
            now=now,
        )
        self.repository.update(device)
        recordDeviceHistory(
            self.historyRepository,
            device,
            DEVICE_HISTORY_UPDATED,
            now,
        )
        self.collectEventsFrom(device)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Device",
            resourceId=str(device.id),
            tenantId=tenantId,
            after=device.snapshot(),
        )
        return deviceDtoFromDomain(device, now.date())


class ChangeDeviceStatusUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.manage"

    def validateCommand(self, command: ChangeDeviceStatusCommand) -> None:
        DeviceStatus(command.target)

    def perform(self, command: ChangeDeviceStatusCommand) -> DeviceDto:
        tenantId = resolveTenantId("")
        device = self.repository.getById(tenantId, uuid.UUID(command.deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        now = self.clock.nowUtc()
        previousStatus = str(device.status)
        device.changeStatus(command.target, now)
        self.repository.update(device)
        recordDeviceHistory(
            self.historyRepository,
            device,
            DEVICE_HISTORY_STATUS_CHANGED,
            now,
            fromStatus=previousStatus,
            toStatus=str(device.status),
        )
        self.collectEventsFrom(device)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Device",
            resourceId=str(device.id),
            tenantId=tenantId,
            after=device.snapshot(),
        )
        return deviceDtoFromDomain(device, self.clock.nowUtc().date())


class RecordDevicePmUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.manage"

    def perform(self, command: RecordDevicePmCommand) -> DeviceDto:
        tenantId = resolveTenantId("")
        device = self.repository.getById(tenantId, uuid.UUID(command.deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        now = self.clock.nowUtc()
        performedOn = parseDateOrToday(command.performedOn, now.date())
        device.recordPreventiveMaintenance(performedOn, now)
        self.repository.update(device)
        recordDeviceHistory(
            self.historyRepository,
            device,
            DEVICE_HISTORY_PM_COMPLETED,
            now,
            note=performedOn.isoformat(),
        )
        self.collectEventsFrom(device)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Device",
            resourceId=str(device.id),
            tenantId=tenantId,
            after=device.snapshot(),
        )
        return deviceDtoFromDomain(device, now.date())


class ListDevicesUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.list"

    def perform(self, query: ListDevicesQuery) -> DeviceListDto:
        tenantId = resolveTenantId("")
        asOf = self.clock.nowUtc().date()
        page = self.repository.list(
            DeviceFilters(
                tenantId=tenantId,
                status=query.status,
                department=query.department,
                search=query.search,
                ordering=query.ordering,
                page=query.page,
                pageSize=query.pageSize,
            )
        )
        return DeviceListDto(
            items=[deviceDtoFromDomain(item, asOf) for item in page.items],
            totalCount=page.totalCount,
        )


class ListDuePmUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.list"

    def perform(self, query: ListDuePmQuery) -> DeviceListDto:
        tenantId = resolveTenantId("")
        asOf = self.clock.nowUtc().date()
        devices = self.repository.listDueForPm(tenantId)
        due = [d for d in devices if d.isPmDue(asOf)]
        return DeviceListDto(
            items=[deviceDtoFromDomain(item, asOf) for item in due],
            totalCount=len(due),
        )


class GetDeviceUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.view"

    def perform(self, query: GetDeviceQuery) -> DeviceDto:
        tenantId = resolveTenantId("")
        device = self.repository.getById(tenantId, uuid.UUID(query.deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        return deviceDtoFromDomain(device, self.clock.nowUtc().date())


class GetDeviceTimelineUseCase(DeviceUseCaseBase):
    """Merge device history with related work-order milestones into one timeline.

    Device-history rows (registration, updates, status changes, PM completions)
    are combined with the work orders raised against the device — each order
    contributing a "raised" milestone and, when closed, a "closed" milestone.
    The merged list is sorted chronologically (newest first) so the frontend
    renders a single, unified device timeline.
    """

    requiredAction = "maintenance.device.view"

    def __init__(
        self,
        *args: object,
        workOrderRepository: WorkOrderRepository,
        **kwargs: object,
    ) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.workOrderRepository = workOrderRepository

    def perform(self, query: GetDeviceTimelineQuery) -> DeviceTimelineDto:
        tenantId = resolveTenantId("")
        deviceId = uuid.UUID(query.deviceId)
        device = self.repository.getById(tenantId, deviceId)
        if device is None:
            raise EntityNotFoundError("Device not found.")

        now = self.clock.nowUtc()
        items: list[DeviceTimelineItemDto] = [
            deviceHistoryTimelineItem(entry)
            for entry in self.historyRepository.listForDevice(tenantId, deviceId)
        ]

        for order in self._collectWorkOrders(tenantId, str(deviceId)):
            items.append(
                DeviceTimelineItemDto(
                    id=f"wo-raised-{order.id}",
                    source="workOrder",
                    action="workOrderRaised",
                    at=order.createdAt.isoformat(),
                    toStatus=str(order.status),
                    note=order.title,
                    actorName=order.requestedByName,
                    workOrderId=str(order.id),
                    workOrderTitle=order.title,
                    orderType=str(order.orderType),
                    priority=str(order.priority),
                )
            )
            if order.closedAt is not None:
                items.append(
                    DeviceTimelineItemDto(
                        id=f"wo-closed-{order.id}",
                        source="workOrder",
                        action="workOrderClosed",
                        at=order.closedAt.isoformat(),
                        toStatus=str(order.status),
                        note=order.resolutionNote,
                        actorName=order.assignedToName,
                        workOrderId=str(order.id),
                        workOrderTitle=order.title,
                        orderType=str(order.orderType),
                        priority=str(order.priority),
                    )
                )

        items.sort(key=lambda item: item.at, reverse=True)
        return DeviceTimelineDto(
            device=deviceDtoFromDomain(device, now.date()),
            items=items,
            generatedAt=now.isoformat(),
        )

    def _collectWorkOrders(self, tenantId, deviceId: str):
        collected = []
        page = 1
        while True:
            result = self.workOrderRepository.list(
                WorkOrderFilters(
                    tenantId=tenantId,
                    deviceId=deviceId,
                    ordering="-createdAt",
                    page=page,
                    pageSize=100,
                )
            )
            collected.extend(result.items)
            if len(collected) >= result.totalCount or not result.items:
                break
            page += 1
        return collected
