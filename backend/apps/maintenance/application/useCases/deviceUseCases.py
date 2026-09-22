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
    deviceDtoFromDomain,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    GetDeviceQuery,
    ListDevicesQuery,
    ListDuePmQuery,
)
from apps.maintenance.application.services.tenantResolver import (
    parseDateOrToday,
    resolveTenantId,
)
from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    DeviceFilters,
    DeviceRepository,
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
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository


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
        device.updateDetails(
            name=command.name,
            location=command.location,
            department=MaintenanceDepartment(command.department or DEPARTMENT_GENERAL),
            pmIntervalDays=int(command.pmIntervalDays),
            now=self.clock.nowUtc(),
        )
        self.repository.update(device)
        self.collectEventsFrom(device)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Device",
            resourceId=str(device.id),
            tenantId=tenantId,
            after=device.snapshot(),
        )
        return deviceDtoFromDomain(device, self.clock.nowUtc().date())


class ChangeDeviceStatusUseCase(DeviceUseCaseBase):
    requiredAction = "maintenance.device.manage"

    def validateCommand(self, command: ChangeDeviceStatusCommand) -> None:
        DeviceStatus(command.target)

    def perform(self, command: ChangeDeviceStatusCommand) -> DeviceDto:
        tenantId = resolveTenantId("")
        device = self.repository.getById(tenantId, uuid.UUID(command.deviceId))
        if device is None:
            raise EntityNotFoundError("Device not found.")
        device.changeStatus(command.target, self.clock.nowUtc())
        self.repository.update(device)
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
