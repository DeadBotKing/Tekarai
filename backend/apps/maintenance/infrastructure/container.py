"""Maintenance composition root (Phase 21)."""

from __future__ import annotations

from apps.maintenance.application.useCases.deviceUseCases import (
    ChangeDeviceStatusUseCase,
    GetDeviceTimelineUseCase,
    GetDeviceUseCase,
    ListDevicesUseCase,
    ListDuePmUseCase,
    RecordDevicePmUseCase,
    RegisterDeviceUseCase,
    SendPmRemindersUseCase,
    UpdateDeviceUseCase,
)
from apps.maintenance.application.useCases.maintenanceAttachmentUseCases import (
    DeleteMaintenanceAttachmentUseCase,
    DownloadMaintenanceAttachmentUseCase,
    ListMaintenanceAttachmentsUseCase,
    UploadMaintenanceAttachmentUseCase,
)
from apps.maintenance.application.useCases.sparePartUseCases import (
    ConsumeSparePartUseCase,
    CreateSparePartUseCase,
    ListSparePartsUseCase,
    ListWorkOrderPartUsageUseCase,
    UpdateSparePartUseCase,
)
from apps.maintenance.application.useCases.workOrderUseCases import (
    ApproveWorkOrderUseCase,
    AssignWorkOrderUseCase,
    AutoAssignWorkOrderUseCase,
    ChangeWorkOrderStatusUseCase,
    DeviceMaintenanceReportUseCase,
    GeneratePmWorkOrdersUseCase,
    GetWorkOrderUseCase,
    ListWorkOrderHistoryUseCase,
    ListWorkOrdersUseCase,
    RejectWorkOrderUseCase,
    RouteWorkOrderUseCase,
    SubmitWorkOrderUseCase,
    UpdateWorkOrderUseCase,
)
from apps.maintenance.infrastructure.repositories.deviceHistoryRepositoryImpl import (
    DeviceHistoryRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.deviceRepositoryImpl import (
    DeviceRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.maintenanceAttachmentRepositoryImpl import (
    MaintenanceAttachmentRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.sparePartRepositoryImpl import (
    SparePartRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.workOrderHistoryRepositoryImpl import (
    WorkOrderHistoryRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.workOrderRepositoryImpl import (
    WorkOrderRepositoryDjango,
)
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def deviceRepository() -> DeviceRepositoryDjango:
    return DeviceRepositoryDjango()


def workOrderRepository() -> WorkOrderRepositoryDjango:
    return WorkOrderRepositoryDjango()


def workOrderHistoryRepository() -> WorkOrderHistoryRepositoryDjango:
    return WorkOrderHistoryRepositoryDjango()


def deviceHistoryRepository() -> DeviceHistoryRepositoryDjango:
    return DeviceHistoryRepositoryDjango()


def sparePartRepository() -> SparePartRepositoryDjango:
    return SparePartRepositoryDjango()


def maintenanceAttachmentRepository() -> MaintenanceAttachmentRepositoryDjango:
    return MaintenanceAttachmentRepositoryDjango()


def _kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def _deviceDeps() -> dict:
    return {
        "repository": deviceRepository(),
        "historyRepository": deviceHistoryRepository(),
        **_kernelPorts(),
    }


def _workOrderDeps() -> dict:
    return {
        "repository": workOrderRepository(),
        "historyRepository": workOrderHistoryRepository(),
        **_kernelPorts(),
    }


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


def sendPmRemindersUseCase() -> SendPmRemindersUseCase:
    return SendPmRemindersUseCase(**_deviceDeps())


# -- Maintenance attachments -----------------------------------------------------
def uploadMaintenanceAttachmentUseCase() -> UploadMaintenanceAttachmentUseCase:
    return UploadMaintenanceAttachmentUseCase(
        repository=maintenanceAttachmentRepository(), **_kernelPorts()
    )


def listMaintenanceAttachmentsUseCase() -> ListMaintenanceAttachmentsUseCase:
    return ListMaintenanceAttachmentsUseCase(
        repository=maintenanceAttachmentRepository(), **_kernelPorts()
    )


def downloadMaintenanceAttachmentUseCase() -> DownloadMaintenanceAttachmentUseCase:
    return DownloadMaintenanceAttachmentUseCase(
        repository=maintenanceAttachmentRepository(), **_kernelPorts()
    )


def deleteMaintenanceAttachmentUseCase() -> DeleteMaintenanceAttachmentUseCase:
    return DeleteMaintenanceAttachmentUseCase(
        repository=maintenanceAttachmentRepository(), **_kernelPorts()
    )


# -- Spare-parts inventory --------------------------------------------------------
def createSparePartUseCase() -> CreateSparePartUseCase:
    return CreateSparePartUseCase(repository=sparePartRepository(), **_kernelPorts())


def updateSparePartUseCase() -> UpdateSparePartUseCase:
    return UpdateSparePartUseCase(repository=sparePartRepository(), **_kernelPorts())


def listSparePartsUseCase() -> ListSparePartsUseCase:
    return ListSparePartsUseCase(repository=sparePartRepository(), **_kernelPorts())


def consumeSparePartUseCase() -> ConsumeSparePartUseCase:
    return ConsumeSparePartUseCase(repository=sparePartRepository(), **_kernelPorts())


def listWorkOrderPartUsageUseCase() -> ListWorkOrderPartUsageUseCase:
    return ListWorkOrderPartUsageUseCase(repository=sparePartRepository(), **_kernelPorts())


# -- Work order use cases ---------------------------------------------------------
def submitWorkOrderUseCase() -> SubmitWorkOrderUseCase:
    return SubmitWorkOrderUseCase(
        repository=workOrderRepository(),
        deviceRepository=deviceRepository(),
        historyRepository=workOrderHistoryRepository(),
        **_kernelPorts(),
    )


def updateWorkOrderUseCase() -> UpdateWorkOrderUseCase:
    return UpdateWorkOrderUseCase(**_workOrderDeps())


def routeWorkOrderUseCase() -> RouteWorkOrderUseCase:
    return RouteWorkOrderUseCase(**_workOrderDeps())


def generatePmWorkOrdersUseCase() -> GeneratePmWorkOrdersUseCase:
    return GeneratePmWorkOrdersUseCase(
        repository=workOrderRepository(),
        deviceRepository=deviceRepository(),
        historyRepository=workOrderHistoryRepository(),
        **_kernelPorts(),
    )


def assignWorkOrderUseCase() -> AssignWorkOrderUseCase:
    return AssignWorkOrderUseCase(**_workOrderDeps())


def autoAssignWorkOrderUseCase() -> AutoAssignWorkOrderUseCase:
    return AutoAssignWorkOrderUseCase(
        repository=workOrderRepository(),
        historyRepository=workOrderHistoryRepository(),
        deviceRepository=deviceRepository(),
        **_kernelPorts(),
    )


def changeWorkOrderStatusUseCase() -> ChangeWorkOrderStatusUseCase:
    return ChangeWorkOrderStatusUseCase(**_workOrderDeps())


def approveWorkOrderUseCase() -> ApproveWorkOrderUseCase:
    return ApproveWorkOrderUseCase(**_workOrderDeps())


def rejectWorkOrderUseCase() -> RejectWorkOrderUseCase:
    return RejectWorkOrderUseCase(**_workOrderDeps())


def listWorkOrdersUseCase() -> ListWorkOrdersUseCase:
    return ListWorkOrdersUseCase(**_workOrderDeps())


def getWorkOrderUseCase() -> GetWorkOrderUseCase:
    return GetWorkOrderUseCase(**_workOrderDeps())


def listWorkOrderHistoryUseCase() -> ListWorkOrderHistoryUseCase:
    return ListWorkOrderHistoryUseCase(**_workOrderDeps())


def deviceMaintenanceReportUseCase() -> DeviceMaintenanceReportUseCase:
    return DeviceMaintenanceReportUseCase(
        deviceRepository=deviceRepository(), **_workOrderDeps()
    )


def getDeviceTimelineUseCase() -> GetDeviceTimelineUseCase:
    return GetDeviceTimelineUseCase(
        workOrderRepository=workOrderRepository(), **_deviceDeps()
    )


# -- Phase 26: asset registry + analytics -----------------------------------------
from apps.maintenance.application.useCases.registryUseCases import (  # noqa: E402
    DeleteLocationUseCase,
    DeletePersonnelUseCase,
    DeletePmPlanUseCase,
    GetDeviceAnalyticsUseCase,
    GetDeviceProfileUseCase,
    GetFleetAnalyticsUseCase,
    GetPartUsageReportUseCase,
    ListLocationsUseCase,
    ListPersonnelUseCase,
    ListPmPlansUseCase,
    RecordClosureDetailsUseCase,
    RecordPmExecutionUseCase,
    RemoveBomItemUseCase,
    SaveAssignmentsUseCase,
    SaveBomItemUseCase,
    SaveLocationUseCase,
    SavePersonnelUseCase,
    SavePmPlanUseCase,
    SaveSpecificationsUseCase,
    UpdateDeviceNameplateUseCase,
)
from apps.maintenance.infrastructure.repositories.assetRegistryRepositoryImpl import (  # noqa: E402
    DeviceRegistryRepositoryDjango,
    LocationRepositoryDjango,
    MaintenanceAnalyticsRepositoryDjango,
    PersonnelRepositoryDjango,
)


def locationRepository() -> LocationRepositoryDjango:
    return LocationRepositoryDjango()


def personnelRepository() -> PersonnelRepositoryDjango:
    return PersonnelRepositoryDjango()


def deviceRegistryRepository() -> DeviceRegistryRepositoryDjango:
    return DeviceRegistryRepositoryDjango()


def maintenanceAnalyticsRepository() -> MaintenanceAnalyticsRepositoryDjango:
    return MaintenanceAnalyticsRepositoryDjango()


def _registryDeps() -> dict:
    return {
        "deviceRepository": deviceRepository(),
        "registryRepository": deviceRegistryRepository(),
        "locationRepository": locationRepository(),
        "personnelRepository": personnelRepository(),
        "analyticsRepository": maintenanceAnalyticsRepository(),
        **_kernelPorts(),
    }


def saveLocationUseCase() -> SaveLocationUseCase:
    return SaveLocationUseCase(**_registryDeps())


def deleteLocationUseCase() -> DeleteLocationUseCase:
    return DeleteLocationUseCase(**_registryDeps())


def listLocationsUseCase() -> ListLocationsUseCase:
    return ListLocationsUseCase(**_registryDeps())


def savePersonnelUseCase() -> SavePersonnelUseCase:
    return SavePersonnelUseCase(**_registryDeps())


def deletePersonnelUseCase() -> DeletePersonnelUseCase:
    return DeletePersonnelUseCase(**_registryDeps())


def listPersonnelUseCase() -> ListPersonnelUseCase:
    return ListPersonnelUseCase(**_registryDeps())


def saveSpecificationsUseCase() -> SaveSpecificationsUseCase:
    return SaveSpecificationsUseCase(**_registryDeps())


def savePmPlanUseCase() -> SavePmPlanUseCase:
    return SavePmPlanUseCase(**_registryDeps())


def deletePmPlanUseCase() -> DeletePmPlanUseCase:
    return DeletePmPlanUseCase(**_registryDeps())


def listPmPlansUseCase() -> ListPmPlansUseCase:
    return ListPmPlansUseCase(**_registryDeps())


def recordPmExecutionUseCase() -> RecordPmExecutionUseCase:
    return RecordPmExecutionUseCase(**_registryDeps())


def saveBomItemUseCase() -> SaveBomItemUseCase:
    return SaveBomItemUseCase(**_registryDeps())


def removeBomItemUseCase() -> RemoveBomItemUseCase:
    return RemoveBomItemUseCase(**_registryDeps())


def saveAssignmentsUseCase() -> SaveAssignmentsUseCase:
    return SaveAssignmentsUseCase(**_registryDeps())


def getDeviceProfileUseCase() -> GetDeviceProfileUseCase:
    return GetDeviceProfileUseCase(**_registryDeps())


def getDeviceAnalyticsUseCase() -> GetDeviceAnalyticsUseCase:
    return GetDeviceAnalyticsUseCase(**_registryDeps())


def getFleetAnalyticsUseCase() -> GetFleetAnalyticsUseCase:
    return GetFleetAnalyticsUseCase(**_registryDeps())


def getPartUsageReportUseCase() -> GetPartUsageReportUseCase:
    return GetPartUsageReportUseCase(**_registryDeps())


def updateDeviceNameplateUseCase() -> UpdateDeviceNameplateUseCase:
    return UpdateDeviceNameplateUseCase(**_registryDeps())


def recordClosureDetailsUseCase() -> RecordClosureDetailsUseCase:
    return RecordClosureDetailsUseCase(**_registryDeps())
