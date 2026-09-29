"""MetricDefinition and MetricReading application orchestration."""

from __future__ import annotations

import uuid
from datetime import timedelta

from apps.analytics.application.commands.metricCommands import (
    CreateMetricDefinitionCommand,
    MetricReadingInput,
    RecordMetricReadingCommand,
    RecordMetricReadingsBatchCommand,
    UpdateMetricDefinitionCommand,
)
from apps.analytics.application.dto.metricDtos import (
    MetricDefinitionDto,
    MetricDefinitionListDto,
    MetricReadingBatchDto,
    MetricReadingDto,
    MetricReadingListDto,
    MetricReadingSummaryDto,
    definitionDtoFromDomain,
    readingDtoFromDomain,
    summaryDtoFromDomain,
)
from apps.analytics.application.queries.metricQueries import (
    GetMetricDefinitionQuery,
    GetMetricReadingQuery,
    ListMetricDefinitionsQuery,
    ListMetricReadingsQuery,
    SummarizeMetricReadingsQuery,
)
from apps.analytics.domain.entities.metricDefinition import MetricDefinition
from apps.analytics.domain.entities.metricReading import MetricReading
from apps.analytics.domain.exceptions.metricErrors import MetricIngestionConflictError
from apps.analytics.domain.repositories.metricRepository import (
    MetricDefinitionFilters,
    MetricDefinitionRepository,
    MetricReadingFilters,
    MetricReadingRepository,
)
from apps.analytics.domain.valueObjects.metricTypes import (
    MetricCode,
    normalizeMetricValue,
    normalizeQuality,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import (
    DuplicateBusinessCodeError,
    EntityNotFoundError,
    TenantAccessDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

MAX_BATCH_SIZE = 500
MAX_FUTURE_SKEW = timedelta(minutes=5)


def resolveTenantId(requestedTenantId: str = "") -> uuid.UUID:
    """Resolve tenant from authenticated context and block cross-tenant input."""

    context = currentContext()
    contextValue = context.tenantId or context.actorTenantId
    if requestedTenantId:
        requested = asUuid(requestedTenantId, "tenantId")
        if contextValue and str(requested) != str(contextValue):
            raise TenantAccessDeniedError("Cross-tenant analytics access is forbidden.")
        return requested
    if contextValue:
        return asUuid(contextValue, "tenantId")
    raise TenantAccessDeniedError("Tenant scope could not be resolved.")


class AnalyticsUseCase(UseCase):
    """Common constructor for use cases that need both repositories."""

    def __init__(
        self,
        definitionRepository: MetricDefinitionRepository,
        readingRepository: MetricReadingRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.definitionRepository = definitionRepository
        self.readingRepository = readingRepository

    def definitionFor(
        self, tenantId: uuid.UUID, metricId: str = "", metricCode: str = ""
    ) -> MetricDefinition:
        if bool(metricId) == bool(metricCode):
            raise ValidationFailedError(
                "Supply exactly one of metricId or metricCode.",
                fieldErrors={"metricId": "exclusive with metricCode"},
            )
        definition = (
            self.definitionRepository.getById(tenantId, asUuid(metricId, "metricId"))
            if metricId
            else self.definitionRepository.getByCode(tenantId, str(MetricCode(metricCode)))
        )
        if definition is None:
            raise EntityNotFoundError("MetricDefinition", metricId or metricCode)
        return definition


class CreateMetricDefinitionUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricDefinition.manage"

    def validateCommand(self, command: CreateMetricDefinitionCommand) -> None:
        MetricCode(command.code)

    def businessRules(self, command: CreateMetricDefinitionCommand) -> None:
        tenantId = resolveTenantId(command.tenantId)
        if self.definitionRepository.existsByCode(tenantId, str(MetricCode(command.code))):
            raise DuplicateBusinessCodeError("Metric code already exists in this tenant.")

    def perform(self, command: CreateMetricDefinitionCommand) -> MetricDefinitionDto:
        tenantId = resolveTenantId(command.tenantId)
        definition = MetricDefinition.create(
            tenantId=tenantId,
            code=MetricCode(command.code),
            name=command.name,
            description=command.description,
            formula=command.formula,
            unit=command.unit,
            aggregation=command.aggregation,
            minimumValue=command.minimumValue,
            maximumValue=command.maximumValue,
            now=self.clock.nowUtc(),
        )
        self.definitionRepository.create(definition)
        self.collectEventsFrom(definition)
        self.audit(
            AUDIT_CREATE,
            "MetricDefinition",
            str(definition.id),
            tenantId,
            after=definition.snapshot(),
        )
        return definitionDtoFromDomain(definition)


class UpdateMetricDefinitionUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricDefinition.manage"

    def perform(self, command: UpdateMetricDefinitionCommand) -> MetricDefinitionDto:
        tenantId = resolveTenantId()
        definition = self.definitionRepository.getById(
            tenantId, asUuid(command.definitionId, "definitionId")
        )
        if definition is None:
            raise EntityNotFoundError("MetricDefinition", command.definitionId)
        before = definition.snapshot()
        definition.update(
            name=command.name,
            description=command.description,
            formula=command.formula,
            unit=command.unit,
            aggregation=command.aggregation,
            minimumValue=command.minimumValue,
            maximumValue=command.maximumValue,
            isActive=command.isActive,
            now=self.clock.nowUtc(),
        )
        self.definitionRepository.update(definition)
        self.collectEventsFrom(definition)
        self.audit(
            AUDIT_UPDATE,
            "MetricDefinition",
            str(definition.id),
            tenantId,
            before=before,
            after=definition.snapshot(),
        )
        return definitionDtoFromDomain(definition)


class GetMetricDefinitionUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricDefinition.view"

    def perform(self, query: GetMetricDefinitionQuery) -> MetricDefinitionDto:
        tenantId = resolveTenantId()
        definition = self.definitionRepository.getById(
            tenantId, asUuid(query.definitionId, "definitionId")
        )
        if definition is None:
            raise EntityNotFoundError("MetricDefinition", query.definitionId)
        return definitionDtoFromDomain(definition)


class ListMetricDefinitionsUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricDefinition.view"

    def perform(self, query: ListMetricDefinitionsQuery) -> MetricDefinitionListDto:
        tenantId = resolveTenantId()
        pageSize = min(200, max(1, query.pageSize))
        pageNumber = max(1, query.page)
        page = self.definitionRepository.list(
            MetricDefinitionFilters(
                tenantId=tenantId,
                search=query.search.strip(),
                isActive=query.isActive,
                page=pageNumber,
                pageSize=pageSize,
            )
        )
        return MetricDefinitionListDto(
            items=[definitionDtoFromDomain(item) for item in page.items],
            totalCount=page.totalCount,
            page=pageNumber,
            pageSize=pageSize,
        )


def buildMetricReading(
    useCase: AnalyticsUseCase,
    tenantId: uuid.UUID,
    value: MetricReadingInput,
) -> tuple[MetricReading, MetricDefinition]:
    """Apply shared single/batch ingestion rules without nested use cases."""

    definition = useCase.definitionFor(tenantId, value.metricId, value.metricCode)
    normalizedValue = normalizeMetricValue(value.value)
    definition.validateReadingValue(normalizedValue)
    if value.periodStart is None:
        raise ValidationFailedError(
            "Metric period start is required.", fieldErrors={"periodStart": "required"}
        )
    periodEnd = value.periodEnd or value.periodStart
    now = useCase.clock.nowUtc()
    context = currentContext()
    reading = MetricReading.record(
        tenantId=tenantId,
        metricId=definition.id,
        value=normalizedValue,
        periodStart=value.periodStart,
        periodEnd=periodEnd,
        dimensions=value.dimensions,
        quality=value.quality,
        sourceType=value.sourceType,
        sourceId=value.sourceId,
        ingestionKey=value.ingestionKey,
        recordedAt=now,
        recordedById=asUuid(context.actorId, "actorId") if context.actorId else None,
        correlationId=context.correlationId,
    )
    if (
        reading.periodStart > reading.recordedAt + MAX_FUTURE_SKEW
        or reading.periodEnd > reading.recordedAt + MAX_FUTURE_SKEW
    ):
        raise ValidationFailedError(
            "Metric period cannot be more than five minutes in the future.",
            fieldErrors={"periodStart": "future timestamp"},
        )
    return reading, definition


class RecordMetricReadingUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricReading.record"

    def validateCommand(self, command: RecordMetricReadingCommand) -> None:
        if command.reading.periodStart is None:
            raise ValidationFailedError(
                "Metric period start is required.", fieldErrors={"periodStart": "required"}
            )

    def perform(self, command: RecordMetricReadingCommand) -> MetricReadingDto:
        tenantId = resolveTenantId()
        reading, definition = buildMetricReading(self, tenantId, command.reading)
        stored, created = self.readingRepository.create(reading)
        if not created and not stored.sameObservationAs(reading):
            raise MetricIngestionConflictError(
                "The ingestion key already belongs to a different metric observation."
            )
        if created:
            self._pendingEvents.append(stored.recordedEvent())
        return readingDtoFromDomain(stored, definition, replayed=not created)


class RecordMetricReadingsBatchUseCase(AnalyticsUseCase):
    """Atomic all-or-nothing ingestion of at most 500 readings."""

    def validateCommand(self, command: RecordMetricReadingsBatchCommand) -> None:
        if not command.readings:
            raise ValidationFailedError(
                "Batch must contain at least one reading.", fieldErrors={"readings": "required"}
            )
        if len(command.readings) > MAX_BATCH_SIZE:
            raise ValidationFailedError(
                "Metric reading batch is too large.",
                fieldErrors={"readings": f"maximum {MAX_BATCH_SIZE}"},
            )
        for index, reading in enumerate(command.readings):
            if reading.periodStart is None:
                raise ValidationFailedError(
                    "Metric period start is required.",
                    fieldErrors={f"readings.{index}.periodStart": "required"},
                )

    def perform(self, command: RecordMetricReadingsBatchCommand) -> MetricReadingBatchDto:
        tenantId = resolveTenantId()
        items: list[MetricReadingDto] = []
        createdCount = 0
        replayedCount = 0
        for inputValue in command.readings:
            reading, definition = buildMetricReading(self, tenantId, inputValue)
            stored, created = self.readingRepository.create(reading)
            if not created and not stored.sameObservationAs(reading):
                raise MetricIngestionConflictError(
                    "The ingestion key already belongs to a different metric observation."
                )
            if created:
                createdCount += 1
                self._pendingEvents.append(stored.recordedEvent())
            else:
                replayedCount += 1
            items.append(readingDtoFromDomain(stored, definition, replayed=not created))
        return MetricReadingBatchDto(
            items=items,
            createdCount=createdCount,
            replayedCount=replayedCount,
        )


class GetMetricReadingUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricReading.view"

    def perform(self, query: GetMetricReadingQuery) -> MetricReadingDto:
        tenantId = resolveTenantId()
        reading = self.readingRepository.getById(tenantId, asUuid(query.readingId, "readingId"))
        if reading is None:
            raise EntityNotFoundError("MetricReading", query.readingId)
        definition = self.definitionRepository.getById(tenantId, reading.metricId)
        if definition is None:  # protected FK makes this an integrity alarm.
            raise EntityNotFoundError("MetricDefinition", str(reading.metricId))
        return readingDtoFromDomain(reading, definition)


class ListMetricReadingsUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricReading.view"

    def perform(self, query: ListMetricReadingsQuery) -> MetricReadingListDto:
        tenantId = resolveTenantId()
        metricId: uuid.UUID | None = None
        if query.metricId or query.metricCode:
            metricId = self.definitionFor(tenantId, query.metricId, query.metricCode).id
        filters = self.filtersFromQuery(tenantId, query, metricId)
        page = self.readingRepository.list(filters)
        definitions: dict[uuid.UUID, MetricDefinition] = {}
        items: list[MetricReadingDto] = []
        for reading in page.items:
            definition = definitions.get(reading.metricId)
            if definition is None:
                definition = self.definitionRepository.getById(tenantId, reading.metricId)
                if definition is None:
                    raise EntityNotFoundError("MetricDefinition", str(reading.metricId))
                definitions[reading.metricId] = definition
            items.append(readingDtoFromDomain(reading, definition))
        return MetricReadingListDto(
            items=items,
            totalCount=page.totalCount,
            page=filters.page,
            pageSize=filters.pageSize,
        )

    @staticmethod
    def filtersFromQuery(
        tenantId: uuid.UUID,
        query: ListMetricReadingsQuery | SummarizeMetricReadingsQuery,
        metricId: uuid.UUID | None,
    ) -> MetricReadingFilters:
        fromTime = query.fromTime
        toTime = query.toTime
        if fromTime and toTime and toTime < fromTime:
            raise ValidationFailedError(
                "The end of the query window cannot precede its start.",
                fieldErrors={"to": "must be >= from"},
            )
        quality = normalizeQuality(query.quality) if query.quality else ""
        return MetricReadingFilters(
            tenantId=tenantId,
            metricId=metricId,
            quality=quality,
            sourceType=query.sourceType.strip(),
            sourceId=query.sourceId.strip(),
            fromTime=fromTime,
            toTime=toTime,
            ordering=getattr(query, "ordering", "-periodStart"),
            page=max(1, getattr(query, "page", 1)),
            pageSize=min(500, max(1, getattr(query, "pageSize", 100))),
        )


class SummarizeMetricReadingsUseCase(AnalyticsUseCase):
    requiredAction = "analytics.metricReading.view"

    def perform(self, query: SummarizeMetricReadingsQuery) -> MetricReadingSummaryDto:
        tenantId = resolveTenantId()
        definition = self.definitionFor(tenantId, query.metricId, query.metricCode)
        filters = ListMetricReadingsUseCase.filtersFromQuery(tenantId, query, definition.id)
        return summaryDtoFromDomain(self.readingRepository.summarize(filters), definition)


__all__ = [
    "CreateMetricDefinitionUseCase",
    "GetMetricDefinitionUseCase",
    "GetMetricReadingUseCase",
    "ListMetricDefinitionsUseCase",
    "ListMetricReadingsUseCase",
    "RecordMetricReadingUseCase",
    "RecordMetricReadingsBatchUseCase",
    "SummarizeMetricReadingsUseCase",
    "UpdateMetricDefinitionUseCase",
]
