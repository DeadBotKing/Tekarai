"""Maintenance composition root (Phase 21)."""

from __future__ import annotations

from collections.abc import Mapping

from apps.maintenance.application.useCases.alertScanUseCases import (
    RunMaintenanceAlertScanUseCase,
)
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
from apps.maintenance.application.useCases.meterReadingUseCases import (
    CorrectMeterReadingUseCase,
    DeleteMeterPointUseCase,
    GetMeterPmStatusUseCase,
    GetMeterPointSummaryUseCase,
    IngestSensorReadingsUseCase,
    ListMeterPointsUseCase,
    ListMeterReadingsUseCase,
    RecordManualMeterReadingUseCase,
    SaveMeterPointUseCase,
)
from apps.maintenance.application.useCases.sparePartUseCases import (
    ConsumeSparePartUseCase,
    CreateSparePartUseCase,
    ListPartTransactionsUseCase,
    ListSparePartsUseCase,
    ListWorkOrderPartUsageUseCase,
    RecordPartTransactionUseCase,
    UpdateSparePartUseCase,
)
from apps.maintenance.application.useCases.timeCostUseCases import (
    DeleteLabourEntryUseCase,
    GetMaintenanceCostReportUseCase,
    GetWorkOrderCostSummaryUseCase,
    ListLabourEntriesUseCase,
    LogLabourEntryUseCase,
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
from apps.maintenance.infrastructure.repositories.costReportRepositoryImpl import (
    MaintenanceCostRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.deviceHistoryRepositoryImpl import (
    DeviceHistoryRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.deviceRepositoryImpl import (
    DeviceRepositoryDjango,
)
from apps.maintenance.application.commands.maintenanceCommands import (
    ChangeDeviceStatusCommand,
    ChangeWorkOrderStatusCommand,
)
from apps.maintenance.application.commands.sparePartCommands import (
    ConsumeSparePartCommand,
)
from apps.maintenance.application.commands.timeCostCommands import (
    LogLabourEntryCommand,
)
from apps.maintenance.application.useCases.meterReadingUseCases import (
    RecordManualReadingCommand,
)
from apps.maintenance.application.useCases.offlineSyncUseCases import (
    ApplySyncBatchUseCase,
    ListSyncHistoryUseCase,
)
from apps.maintenance.application.useCases.scanUseCases import ResolveScanUseCase
from apps.maintenance.application.useCases.workTimerUseCases import (
    CancelWorkTimerUseCase,
    GetMyRunningTimersUseCase,
    ListWorkTimersUseCase,
    StartWorkTimerCommand,
    StartWorkTimerUseCase,
    StopWorkTimerCommand,
    StopWorkTimerUseCase,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    GetDeviceQuery,
    GetWorkOrderQuery,
)
from apps.maintenance.domain.exceptions.fieldOpsErrors import SyncConflictError
from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    SYNC_BASELINE_KEY,
    SYNC_DEVICE_STATUS,
    SYNC_METER_READING,
    SYNC_TIMER_START,
    SYNC_TIMER_STOP,
    SYNC_WORK_ORDER_LABOUR,
    SYNC_WORK_ORDER_PART,
    SYNC_WORK_ORDER_STATUS,
)
from apps.maintenance.infrastructure.repositories.fieldOpsRepositoryImpl import (
    OfflineSyncLedgerDjango,
    ScanResolutionRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.workTimerRepositoryImpl import (
    WorkTimerRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.labourEntryRepositoryImpl import (
    LabourEntryRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.maintenanceAttachmentRepositoryImpl import (
    MaintenanceAttachmentRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.meterReadingRepositoryImpl import (
    MeterPointRepositoryDjango,
    MeterReadingRepositoryDjango,
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


def labourEntryRepository() -> LabourEntryRepositoryDjango:
    return LabourEntryRepositoryDjango()


def maintenanceCostRepository() -> MaintenanceCostRepositoryDjango:
    return MaintenanceCostRepositoryDjango()


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


def runMaintenanceAlertScanUseCase() -> RunMaintenanceAlertScanUseCase:
    return RunMaintenanceAlertScanUseCase(
        workOrderRepository=workOrderRepository(),
        sparePartRepository=sparePartRepository(),
        **_kernelPorts(),
    )


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


def recordPartTransactionUseCase() -> RecordPartTransactionUseCase:
    return RecordPartTransactionUseCase(repository=sparePartRepository(), **_kernelPorts())


def listPartTransactionsUseCase() -> ListPartTransactionsUseCase:
    return ListPartTransactionsUseCase(repository=sparePartRepository(), **_kernelPorts())


def consumeSparePartUseCase() -> ConsumeSparePartUseCase:
    return ConsumeSparePartUseCase(repository=sparePartRepository(), **_kernelPorts())


def listWorkOrderPartUsageUseCase() -> ListWorkOrderPartUsageUseCase:
    return ListWorkOrderPartUsageUseCase(repository=sparePartRepository(), **_kernelPorts())


# -- Time & cost tracking (ثبت زمان و هزینه) --------------------------------------
def logLabourEntryUseCase() -> LogLabourEntryUseCase:
    return LogLabourEntryUseCase(
        labourEntryRepository=labourEntryRepository(), **_kernelPorts()
    )


def listLabourEntriesUseCase() -> ListLabourEntriesUseCase:
    return ListLabourEntriesUseCase(
        labourEntryRepository=labourEntryRepository(), **_kernelPorts()
    )


def deleteLabourEntryUseCase() -> DeleteLabourEntryUseCase:
    return DeleteLabourEntryUseCase(
        labourEntryRepository=labourEntryRepository(), **_kernelPorts()
    )


def getWorkOrderCostSummaryUseCase() -> GetWorkOrderCostSummaryUseCase:
    return GetWorkOrderCostSummaryUseCase(
        labourEntryRepository=labourEntryRepository(),
        workOrderRepository=workOrderRepository(),
        sparePartRepository=sparePartRepository(),
        **_kernelPorts(),
    )


def getMaintenanceCostReportUseCase() -> GetMaintenanceCostReportUseCase:
    return GetMaintenanceCostReportUseCase(
        costRepository=maintenanceCostRepository(), **_kernelPorts()
    )


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
from apps.maintenance.application.useCases.pmScheduleUseCases import (  # noqa: E402
    GetPmScheduleUseCase,
)
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
from apps.maintenance.application.useCases.assetHierarchyUseCases import (  # noqa: E402
    GetAssetAncestryUseCase,
    GetAssetTreeUseCase,
    ListAssetMovementsUseCase,
    MoveAssetUseCase,
    ReinstateAssetUseCase,
    RetireAssetUseCase,
)
from apps.maintenance.application.useCases.performanceReviewUseCases import (  # noqa: E402
    ComputeReviewCycleUseCase,
    DeleteRaterScoreUseCase,
    DeleteReviewCycleUseCase,
    GetReviewResultsUseCase,
    ListRaterScoresUseCase,
    ListReviewCyclesUseCase,
    SaveRaterScoreUseCase,
    SaveReviewCycleUseCase,
)
from apps.maintenance.infrastructure.repositories.performanceReviewRepositoryImpl import (  # noqa: E402
    PerformanceReviewRepositoryDjango,
)
from apps.maintenance.application.useCases.workCalendarUseCases import (  # noqa: E402
    DeleteCalendarEntryUseCase,
    GetCapacityPlanUseCase,
    GetWorkingDayUseCase,
    ListHolidaysUseCase,
    ListWorkCalendarsUseCase,
    SaveHolidayUseCase,
    SaveShiftAssignmentUseCase,
    SaveShiftUseCase,
    SaveWorkCalendarUseCase,
)
from apps.maintenance.infrastructure.repositories.workCalendarRepositoryImpl import (  # noqa: E402
    WorkCalendarRepositoryDjango,
)
from apps.maintenance.infrastructure.repositories.assetRegistryRepositoryImpl import (  # noqa: E402
    AssetMovementRepositoryDjango,
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


def assetMovementRepository() -> AssetMovementRepositoryDjango:
    return AssetMovementRepositoryDjango()


def _assetHierarchyDeps() -> dict:
    return {
        "deviceRepository": deviceRepository(),
        "locationRepository": locationRepository(),
        "movementRepository": assetMovementRepository(),
        "historyRepository": deviceHistoryRepository(),
        **_kernelPorts(),
    }


def getAssetTreeUseCase() -> GetAssetTreeUseCase:
    return GetAssetTreeUseCase(**_assetHierarchyDeps())


def getAssetAncestryUseCase() -> GetAssetAncestryUseCase:
    return GetAssetAncestryUseCase(**_assetHierarchyDeps())


def listAssetMovementsUseCase() -> ListAssetMovementsUseCase:
    return ListAssetMovementsUseCase(**_assetHierarchyDeps())


def moveAssetUseCase() -> MoveAssetUseCase:
    return MoveAssetUseCase(**_assetHierarchyDeps())


def retireAssetUseCase() -> RetireAssetUseCase:
    return RetireAssetUseCase(**_assetHierarchyDeps())


def reinstateAssetUseCase() -> ReinstateAssetUseCase:
    return ReinstateAssetUseCase(**_assetHierarchyDeps())


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


def getPmScheduleUseCase() -> GetPmScheduleUseCase:
    return GetPmScheduleUseCase(**_registryDeps())


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


# -- Team sync (رزرو قطعات + چک‌لیست‌های تیمی) -------------------------------------
def partReservationRepository() -> PartReservationRepositoryImpl:
    from apps.maintenance.infrastructure.repositories.teamSyncRepositoryImpl import (
        PartReservationRepositoryImpl,
    )

    return PartReservationRepositoryImpl()


def inspectionSyncRepository() -> InspectionSyncRepositoryImpl:
    from apps.maintenance.infrastructure.repositories.teamSyncRepositoryImpl import (
        InspectionSyncRepositoryImpl,
    )

    return InspectionSyncRepositoryImpl()


def listReservationsUseCase() -> ListReservationsUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import ListReservationsUseCase

    return ListReservationsUseCase(repository=partReservationRepository(), **_kernelPorts())


def saveReservationUseCase() -> SaveReservationUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import SaveReservationUseCase

    return SaveReservationUseCase(repository=partReservationRepository(), **_kernelPorts())


def closeReservationUseCase() -> CloseReservationUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import CloseReservationUseCase

    return CloseReservationUseCase(repository=partReservationRepository(), **_kernelPorts())


def listInspectionTemplatesUseCase() -> ListInspectionTemplatesUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import (
        ListInspectionTemplatesUseCase,
    )

    return ListInspectionTemplatesUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


def saveInspectionTemplateUseCase() -> SaveInspectionTemplateUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import SaveInspectionTemplateUseCase

    return SaveInspectionTemplateUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


def commitInspectionTemplateUseCase() -> CommitInspectionTemplateUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import (
        CommitInspectionTemplateUseCase,
    )

    return CommitInspectionTemplateUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


def listInspectionRecordsUseCase() -> ListInspectionRecordsUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import ListInspectionRecordsUseCase

    return ListInspectionRecordsUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


def saveInspectionRecordUseCase() -> SaveInspectionRecordUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import SaveInspectionRecordUseCase

    return SaveInspectionRecordUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


def deleteInspectionTemplateUseCase() -> DeleteInspectionTemplateUseCase:
    from apps.maintenance.application.useCases.teamSyncUseCases import (
        DeleteInspectionTemplateUseCase,
    )

    return DeleteInspectionTemplateUseCase(repository=inspectionSyncRepository(), **_kernelPorts())


# -- Meter readings (ثبت قرائت دستی و سنسوری) -------------------------------------
def meterPointRepository() -> MeterPointRepositoryDjango:
    return MeterPointRepositoryDjango()


def meterReadingRepository() -> MeterReadingRepositoryDjango:
    return MeterReadingRepositoryDjango()


def _meterDeps() -> dict:
    return {
        "pointRepository": meterPointRepository(),
        "readingRepository": meterReadingRepository(),
        "deviceRepository": deviceRepository(),
        **_kernelPorts(),
    }


def saveMeterPointUseCase() -> SaveMeterPointUseCase:
    return SaveMeterPointUseCase(**_meterDeps())


def listMeterPointsUseCase() -> ListMeterPointsUseCase:
    return ListMeterPointsUseCase(**_meterDeps())


def deleteMeterPointUseCase() -> DeleteMeterPointUseCase:
    return DeleteMeterPointUseCase(**_meterDeps())


def recordManualMeterReadingUseCase() -> RecordManualMeterReadingUseCase:
    return RecordManualMeterReadingUseCase(**_meterDeps())


def ingestSensorReadingsUseCase() -> IngestSensorReadingsUseCase:
    return IngestSensorReadingsUseCase(**_meterDeps())


def correctMeterReadingUseCase() -> CorrectMeterReadingUseCase:
    return CorrectMeterReadingUseCase(**_meterDeps())


def listMeterReadingsUseCase() -> ListMeterReadingsUseCase:
    return ListMeterReadingsUseCase(**_meterDeps())


def getMeterPointSummaryUseCase() -> GetMeterPointSummaryUseCase:
    return GetMeterPointSummaryUseCase(**_meterDeps())


def getMeterPmStatusUseCase() -> GetMeterPmStatusUseCase:
    return GetMeterPmStatusUseCase(
        registryRepository=deviceRegistryRepository(), **_meterDeps()
    )


# =====================================================================================
# Field operations — timers, scanning, offline sync (کار میدانی)
# =====================================================================================
def workTimerRepository() -> WorkTimerRepositoryDjango:
    return WorkTimerRepositoryDjango()


def scanResolutionRepository() -> ScanResolutionRepositoryDjango:
    return ScanResolutionRepositoryDjango()


def offlineSyncLedger() -> OfflineSyncLedgerDjango:
    return OfflineSyncLedgerDjango()


def _timerDeps() -> dict:
    return {
        "timerRepository": workTimerRepository(),
        "workOrderRepository": workOrderRepository(),
        "labourEntryRepository": labourEntryRepository(),
        **_kernelPorts(),
    }


def startWorkTimerUseCase() -> StartWorkTimerUseCase:
    return StartWorkTimerUseCase(**_timerDeps())


def stopWorkTimerUseCase() -> StopWorkTimerUseCase:
    return StopWorkTimerUseCase(**_timerDeps())


def cancelWorkTimerUseCase() -> CancelWorkTimerUseCase:
    return CancelWorkTimerUseCase(**_timerDeps())


def listWorkTimersUseCase() -> ListWorkTimersUseCase:
    return ListWorkTimersUseCase(**_timerDeps())


def getMyRunningTimersUseCase() -> GetMyRunningTimersUseCase:
    return GetMyRunningTimersUseCase(**_timerDeps())


def resolveScanUseCase() -> ResolveScanUseCase:
    return ResolveScanUseCase(scanRepository=scanResolutionRepository(), **_kernelPorts())


# -- Sync handlers ------------------------------------------------------------------
# Each handler turns one queued payload into a call on the *same* use case the
# online endpoint uses — permissions, validation and events included. The
# handler returns ``(resultId, resultPayload)``; everything else (idempotency,
# verdicts, the ledger) is the sync use case's business.
def _text(payload: Mapping[str, object], key: str, default: str = "") -> str:
    value = payload.get(key, default)
    return "" if value is None else str(value)


def _occurred(payload: Mapping[str, object], *keys: str) -> str:
    """First populated timestamp among *keys*, else the queue's occurredAt."""
    for key in keys:
        value = _text(payload, key)
        if value:
            return value
    return _text(payload, "occurredAt")


def _guardBaseline(payload: Mapping[str, object], current: str) -> None:
    """Refuse a queued change whose premise no longer holds.

    The phone sends the status it was looking at when the technician tapped.
    If the server has moved on since — a supervisor closed the order, someone
    else put the device back in service — applying the queued change would
    quietly undo their work. We stop and let a human look instead.

    No baseline in the payload means an older client: keep the previous
    last-write-wins behaviour rather than breaking their queue.
    """
    expected = _text(payload, SYNC_BASELINE_KEY)
    if not expected or expected == current:
        return
    raise SyncConflictError(
        f"Changed to «{current}» while offline (you saw «{expected}»).",
        expected=expected,
        current=current,
        fieldErrors={"currentStatus": current},
    )


def _syncChangeWorkOrderStatus(payload: Mapping[str, object]) -> tuple[str, dict]:
    workOrderId = _text(payload, "workOrderId")
    if _text(payload, SYNC_BASELINE_KEY):
        _guardBaseline(
            payload,
            getWorkOrderUseCase().execute(GetWorkOrderQuery(workOrderId=workOrderId)).status,
        )
    dto = changeWorkOrderStatusUseCase().execute(
        ChangeWorkOrderStatusCommand(
            workOrderId=workOrderId,
            target=_text(payload, "target") or _text(payload, "status"),
            resolutionNote=_text(payload, "resolutionNote") or _text(payload, "note"),
        )
    )
    return str(dto.id), {"status": dto.status}


def _syncLogLabour(payload: Mapping[str, object]) -> tuple[str, dict]:
    dto = logLabourEntryUseCase().execute(
        LogLabourEntryCommand(
            workOrderId=_text(payload, "workOrderId"),
            technicianName=_text(payload, "technicianName"),
            hours=_text(payload, "hours", "0"),
            hourlyRate=_text(payload, "hourlyRate", "0"),
            workedAt=_occurred(payload, "workedAt"),
            note=_text(payload, "note"),
        )
    )
    return dto.id, {"hours": dto.hours, "totalCost": dto.totalCost}


def _syncConsumePart(payload: Mapping[str, object]) -> tuple[str, dict]:
    dto = consumeSparePartUseCase().execute(
        ConsumeSparePartCommand(
            workOrderId=_text(payload, "workOrderId"),
            partId=_text(payload, "partId"),
            quantity=_text(payload, "quantity", "0"),
            note=_text(payload, "note"),
        )
    )
    return dto.id, {"quantity": dto.quantity, "partCode": dto.partCode}


def _syncStartTimer(payload: Mapping[str, object]) -> tuple[str, dict]:
    dto = startWorkTimerUseCase().execute(
        StartWorkTimerCommand(
            workOrderId=_text(payload, "workOrderId"),
            technicianName=_text(payload, "technicianName"),
            startedAt=_occurred(payload, "startedAt"),
            hourlyRate=_text(payload, "hourlyRate", "0"),
            note=_text(payload, "note"),
            capturedOffline=True,
        )
    )
    return dto.id, {"startedAt": dto.startedAt, "running": dto.running}


def _syncStopTimer(payload: Mapping[str, object]) -> tuple[str, dict]:
    dto = stopWorkTimerUseCase().execute(
        StopWorkTimerCommand(
            workOrderId=_text(payload, "workOrderId"),
            timerId=_text(payload, "timerId"),
            technicianName=_text(payload, "technicianName"),
            endedAt=_occurred(payload, "endedAt"),
            note=_text(payload, "note"),
            pausedSeconds=int(_text(payload, "pausedSeconds", "0") or 0),
            capturedOffline=True,
        )
    )
    return dto.timer.id, {"hours": dto.hours, "labourEntryId": dto.labourEntryId}


def _syncChangeDeviceStatus(payload: Mapping[str, object]) -> tuple[str, dict]:
    deviceId = _text(payload, "deviceId")
    if _text(payload, SYNC_BASELINE_KEY):
        _guardBaseline(
            payload,
            getDeviceUseCase().execute(GetDeviceQuery(deviceId=deviceId)).status,
        )
    dto = changeDeviceStatusUseCase().execute(
        ChangeDeviceStatusCommand(
            deviceId=deviceId,
            target=_text(payload, "target") or _text(payload, "status"),
        )
    )
    return str(dto.id), {"status": dto.status}


def _syncRecordMeterReading(payload: Mapping[str, object]) -> tuple[str, dict]:
    dto = recordManualMeterReadingUseCase().execute(
        RecordManualReadingCommand(
            deviceId=_text(payload, "deviceId"),
            meterPointId=_text(payload, "meterPointId"),
            meterCode=_text(payload, "meterCode"),
            value=_text(payload, "value"),
            capturedAt=_occurred(payload, "capturedAt"),
            note=_text(payload, "note"),
        )
    )
    return dto.id, {"value": dto.value, "delta": dto.delta}


def syncHandlers() -> dict[str, object]:
    return {
        SYNC_WORK_ORDER_STATUS: _syncChangeWorkOrderStatus,
        SYNC_WORK_ORDER_LABOUR: _syncLogLabour,
        SYNC_WORK_ORDER_PART: _syncConsumePart,
        SYNC_TIMER_START: _syncStartTimer,
        SYNC_TIMER_STOP: _syncStopTimer,
        SYNC_DEVICE_STATUS: _syncChangeDeviceStatus,
        SYNC_METER_READING: _syncRecordMeterReading,
    }


def applySyncBatchUseCase() -> ApplySyncBatchUseCase:
    return ApplySyncBatchUseCase(
        ledger=offlineSyncLedger(), handlers=syncHandlers(), **_kernelPorts()
    )


def listSyncHistoryUseCase() -> ListSyncHistoryUseCase:
    return ListSyncHistoryUseCase(ledger=offlineSyncLedger(), **_kernelPorts())


def performanceReviewRepository() -> PerformanceReviewRepositoryDjango:
    return PerformanceReviewRepositoryDjango()


def _performanceReviewDeps() -> dict:
    return {
        "reviewRepository": performanceReviewRepository(),
        **_kernelPorts(),
    }


def listReviewCyclesUseCase() -> ListReviewCyclesUseCase:
    return ListReviewCyclesUseCase(**_performanceReviewDeps())


def saveReviewCycleUseCase() -> SaveReviewCycleUseCase:
    return SaveReviewCycleUseCase(**_performanceReviewDeps())


def deleteReviewCycleUseCase() -> DeleteReviewCycleUseCase:
    return DeleteReviewCycleUseCase(**_performanceReviewDeps())


def listRaterScoresUseCase() -> ListRaterScoresUseCase:
    return ListRaterScoresUseCase(**_performanceReviewDeps())


def saveRaterScoreUseCase() -> SaveRaterScoreUseCase:
    return SaveRaterScoreUseCase(**_performanceReviewDeps())


def deleteRaterScoreUseCase() -> DeleteRaterScoreUseCase:
    return DeleteRaterScoreUseCase(**_performanceReviewDeps())


def computeReviewCycleUseCase() -> ComputeReviewCycleUseCase:
    return ComputeReviewCycleUseCase(**_performanceReviewDeps())


def getReviewResultsUseCase() -> GetReviewResultsUseCase:
    return GetReviewResultsUseCase(**_performanceReviewDeps())


def workCalendarRepository() -> WorkCalendarRepositoryDjango:
    return WorkCalendarRepositoryDjango()


def _workCalendarDeps() -> dict:
    return {
        "calendarRepository": workCalendarRepository(),
        "deviceRepository": deviceRepository(),
        "locationRepository": locationRepository(),
        **_kernelPorts(),
    }


def listWorkCalendarsUseCase() -> ListWorkCalendarsUseCase:
    return ListWorkCalendarsUseCase(**_workCalendarDeps())


def listHolidaysUseCase() -> ListHolidaysUseCase:
    return ListHolidaysUseCase(**_workCalendarDeps())


def getCapacityPlanUseCase() -> GetCapacityPlanUseCase:
    return GetCapacityPlanUseCase(**_workCalendarDeps())


def getWorkingDayUseCase() -> GetWorkingDayUseCase:
    return GetWorkingDayUseCase(**_workCalendarDeps())


def saveWorkCalendarUseCase() -> SaveWorkCalendarUseCase:
    return SaveWorkCalendarUseCase(**_workCalendarDeps())


def saveHolidayUseCase() -> SaveHolidayUseCase:
    return SaveHolidayUseCase(**_workCalendarDeps())


def saveShiftUseCase() -> SaveShiftUseCase:
    return SaveShiftUseCase(**_workCalendarDeps())


def saveShiftAssignmentUseCase() -> SaveShiftAssignmentUseCase:
    return SaveShiftAssignmentUseCase(**_workCalendarDeps())


def deleteCalendarEntryUseCase() -> DeleteCalendarEntryUseCase:
    return DeleteCalendarEntryUseCase(**_workCalendarDeps())
