"""ORM-backed repositories for team-synced reservations & inspections."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.utils import timezone

from apps.maintenance.domain.entities.teamSync import (
    InspectionRecord,
    InspectionTemplate,
    PartReservation,
)
from apps.maintenance.infrastructure.models import (
    InspectionRecordModel,
    InspectionTemplateModel,
    PartReservationModel,
)


def _reservationEntity(model: PartReservationModel) -> PartReservation:
    return PartReservation(
        id=str(model.id),
        tenantId=uuid.UUID(str(model.tenantId)),
        workOrderId=uuid.UUID(str(model.workOrderId)),
        partCode=model.partCode,
        quantity=model.quantity,
        status=model.status,
        reservedByName=model.reservedByName,
        createdAt=model.createdAt.isoformat() if model.createdAt else "",
        closedAt=model.closedAt.isoformat() if model.closedAt else "",
    )


def _templateEntity(model: InspectionTemplateModel) -> InspectionTemplate:
    return InspectionTemplate(
        id=str(model.id),
        tenantId=uuid.UUID(str(model.tenantId)),
        name=model.name,
        description=model.description,
        deviceCode=model.deviceCode,
        checks=tuple(model.checks or []),
        isCommitted=model.isCommitted,
    )


def _recordEntity(model: InspectionRecordModel) -> InspectionRecord:
    return InspectionRecord(
        id=str(model.id),
        tenantId=uuid.UUID(str(model.tenantId)),
        templateId=str(model.templateId),
        workOrderId=(uuid.UUID(str(model.workOrderId)) if model.workOrderId else None),
        deviceId=uuid.UUID(str(model.deviceId)),
        passedChecks=tuple(model.passedChecks or []),
        failedChecks=tuple(model.failedChecks or []),
        performedByName=model.performedByName,
        createdAt=model.createdAt.isoformat() if model.createdAt else "",
    )


class PartReservationRepositoryImpl:
    """PartReservationRepository (domain protocol)."""

    def listForTenant(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID | None = None
    ) -> list[PartReservation]:
        query = PartReservationModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if workOrderId:
            query = query.filter(workOrderId=workOrderId)
        return [_reservationEntity(model) for model in query]

    def upsert(self, reservation: PartReservation) -> PartReservation:
        model, _ = PartReservationModel.objects.update_or_create(
            id=reservation.id,
            tenantId=reservation.tenantId,
            defaults={
                "workOrderId": reservation.workOrderId,
                "partCode": reservation.partCode,
                "quantity": reservation.quantity,
                "status": reservation.status,
                "reservedByName": reservation.reservedByName,
                "updatedAt": timezone.now(),
            },
        )
        return _reservationEntity(model)

    def close(
        self, tenantId: uuid.UUID, reservationId: str, status: str, closedAt: datetime
    ) -> PartReservation | None:
        try:
            model = PartReservationModel.objects.get(
                id=reservationId, tenantId=tenantId, deletedAt__isnull=True
            )
        except PartReservationModel.DoesNotExist:
            return None
        if model.status != "active":
            return _reservationEntity(model)
        model.status = status
        model.closedAt = closedAt
        model.updatedAt = closedAt
        model.save(update_fields=["status", "closedAt", "updatedAt"])
        return _reservationEntity(model)


class InspectionSyncRepositoryImpl:
    """InspectionSyncRepository (domain protocol)."""

    def listTemplates(self, tenantId: uuid.UUID) -> list[InspectionTemplate]:
        query = InspectionTemplateModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        return [_templateEntity(model) for model in query]

    def upsertTemplate(self, template: InspectionTemplate) -> InspectionTemplate:
        model, _ = InspectionTemplateModel.objects.update_or_create(
            id=template.id,
            tenantId=template.tenantId,
            defaults={
                "name": template.name,
                "description": template.description,
                "deviceCode": template.deviceCode,
                "checks": list(template.checks),
                "isCommitted": template.isCommitted,
                "updatedAt": timezone.now(),
            },
        )
        return _templateEntity(model)

    def getTemplate(self, tenantId: uuid.UUID, templateId: str) -> InspectionTemplate | None:
        model = InspectionTemplateModel.objects.filter(
            id=templateId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return _templateEntity(model) if model else None

    def commitTemplate(self, tenantId: uuid.UUID, templateId: str) -> InspectionTemplate | None:
        model = InspectionTemplateModel.objects.filter(
            id=templateId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        if not model:
            return None
        if not model.isCommitted:
            model.isCommitted = True
            model.updatedAt = timezone.now()
            model.save(update_fields=["isCommitted", "updatedAt"])
        return _templateEntity(model)

    def createRecord(self, record: InspectionRecord) -> InspectionRecord:
        model, _ = InspectionRecordModel.objects.update_or_create(
            id=record.id,
            tenantId=record.tenantId,
            defaults={
                "templateId": record.templateId,
                "workOrderId": record.workOrderId,
                "deviceId": record.deviceId,
                "passedChecks": list(record.passedChecks),
                "failedChecks": list(record.failedChecks),
                "performedByName": record.performedByName,
            },
        )
        return _recordEntity(model)

    def listRecords(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID | None = None
    ) -> list[InspectionRecord]:
        query = InspectionRecordModel.objects.filter(tenantId=tenantId)
        if workOrderId:
            query = query.filter(workOrderId=workOrderId)
        return [_recordEntity(model) for model in query]

    def deleteTemplate(self, tenantId: uuid.UUID, templateId: str) -> bool:
        updated = InspectionTemplateModel.objects.filter(
            id=templateId, tenantId=tenantId, deletedAt__isnull=True
        ).update(deletedAt=timezone.now())
        return bool(updated)
