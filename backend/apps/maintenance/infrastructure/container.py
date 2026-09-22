"""Maintenance composition root (Phase 21)."""

from __future__ import annotations

from apps.maintenance.application.useCases.deviceUseCases import (
    ChangeDeviceStatusUseCase,
    GetDeviceUseCase,
    ListDevicesUseCase,
    ListDuePmUseCase,
    RecordDevicePmUseCase,
    RegisterDeviceUseCase,
    UpdateDeviceUseCase,
)
from apps.maintenance.application.useCases.workOrderUseCases import (
    AssignWorkOrderUseCase,
    ChangeWorkOrderStatusUseCase,
    GetWorkOrderUseCase,
    ListWorkOrdersUseCase,
    SubmitWorkOrderUseCase,
    UpdateWorkOrderUseCase,
)
from apps.maintenance.infrastructure.repositories.deviceRepositoryImpl import (
    DeviceRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.workOrderRepositoryImpl import (
    WorkOrderRepositoryDjango,
)
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def deviceRepository() -> DeviceRepositoryDjango:
    return DeviceRepositoryDjango()


def workOrderRepository() -> WorkOrderRepositoryDjango:
    return WorkOrderRepositoryDjango()


def _kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def _deviceDeps() -> dict:
    return {"repository": deviceRepository(), **_kernelPorts()}


def _workOrderDeps() -> dict:
    return {"repository": workOrderRepository(), **_kernelPorts()}


# -- Device use cases -------------------------------------------------------------
def registerDeviceUseCase() -> RegisterDeviceUseCase:
    return RegisterDeviceUseCase(**_deviceDeps())


def updateDeviceUseCase() -> UpdateDeviceUseCase:
    return UpdateDeviceUseCase(**_deviceDeps())


def changeDeviceStatusUseCase() -> ChangeDeviceStatusUseCase:
    return ChangeDeviceStatusUseCase(**_deviceDeps())


def recordDevicePmUseCase() -> RecordDevicePmUseCase:
    return RecordDevicePmUseCase(**_deviceDeps())


def listDevicesUseCase() -> ListDevicesUseCase:
    return ListDevicesUseCase(**_deviceDeps())


def listDuePmUseCase() -> ListDuePmUseCase:
    return ListDuePmUseCase(**_deviceDeps())


def getDeviceUseCase() -> GetDeviceUseCase:
    return GetDeviceUseCase(**_deviceDeps())


# -- Work order use cases ---------------------------------------------------------
def submitWorkOrderUseCase() -> SubmitWorkOrderUseCase:
    return SubmitWorkOrderUseCase(
        repository=workOrderRepository(),
        deviceRepository=deviceRepository(),
        **_kernelPorts(),
    )


def updateWorkOrderUseCase() -> UpdateWorkOrderUseCase:
    return UpdateWorkOrderUseCase(**_workOrderDeps())


def assignWorkOrderUseCase() -> AssignWorkOrderUseCase:
    return AssignWorkOrderUseCase(**_workOrderDeps())


def changeWorkOrderStatusUseCase() -> ChangeWorkOrderStatusUseCase:
    return ChangeWorkOrderStatusUseCase(**_workOrderDeps())


def listWorkOrdersUseCase() -> ListWorkOrdersUseCase:
    return ListWorkOrdersUseCase(**_workOrderDeps())


def getWorkOrderUseCase() -> GetWorkOrderUseCase:
    return GetWorkOrderUseCase(**_workOrderDeps())
