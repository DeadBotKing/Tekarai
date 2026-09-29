"""Analytics composition root."""

from __future__ import annotations

from apps.analytics.application.useCases.metricUseCases import (
    CreateMetricDefinitionUseCase,
    GetMetricDefinitionUseCase,
    GetMetricReadingUseCase,
    ListMetricDefinitionsUseCase,
    ListMetricReadingsUseCase,
    RecordMetricReadingsBatchUseCase,
    RecordMetricReadingUseCase,
    SummarizeMetricReadingsUseCase,
    UpdateMetricDefinitionUseCase,
)
from apps.analytics.infrastructure.repositories.metricRepositoryImpl import (
    MetricDefinitionRepositoryDjango,
    MetricReadingRepositoryDjango,
)
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def metricDefinitionRepository() -> MetricDefinitionRepositoryDjango:
    return MetricDefinitionRepositoryDjango()


def metricReadingRepository() -> MetricReadingRepositoryDjango:
    return MetricReadingRepositoryDjango()


def _dependencies() -> dict:
    return {
        "definitionRepository": metricDefinitionRepository(),
        "readingRepository": metricReadingRepository(),
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def createMetricDefinitionUseCase() -> CreateMetricDefinitionUseCase:
    return CreateMetricDefinitionUseCase(**_dependencies())


def updateMetricDefinitionUseCase() -> UpdateMetricDefinitionUseCase:
    return UpdateMetricDefinitionUseCase(**_dependencies())


def getMetricDefinitionUseCase() -> GetMetricDefinitionUseCase:
    return GetMetricDefinitionUseCase(**_dependencies())


def listMetricDefinitionsUseCase() -> ListMetricDefinitionsUseCase:
    return ListMetricDefinitionsUseCase(**_dependencies())


def recordMetricReadingUseCase() -> RecordMetricReadingUseCase:
    return RecordMetricReadingUseCase(**_dependencies())


def recordMetricReadingsBatchUseCase() -> RecordMetricReadingsBatchUseCase:
    return RecordMetricReadingsBatchUseCase(**_dependencies())


def getMetricReadingUseCase() -> GetMetricReadingUseCase:
    return GetMetricReadingUseCase(**_dependencies())


def listMetricReadingsUseCase() -> ListMetricReadingsUseCase:
    return ListMetricReadingsUseCase(**_dependencies())


def summarizeMetricReadingsUseCase() -> SummarizeMetricReadingsUseCase:
    return SummarizeMetricReadingsUseCase(**_dependencies())
