"""Django repositories for meter points and the append-only reading stream.

Concurrency note
----------------
Appending a cumulative reading is read-modify-write: find the previous
reading, compute the delta, insert, refresh the point's cached last value.
Two sensors pushing at once would otherwise both read the same "previous" row
and produce two deltas that each ignore the other, double-counting
consumption. Every append therefore takes a row lock on the meter point first
(``select_for_update``), which serialises writers per point while leaving
different points fully parallel.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, Max, Min, Q, QuerySet, Sum

from apps.maintenance.domain.entities.meterReading import (
    MeterPoint,
    MeterPointSummary,
    MeterReading,
)
from apps.maintenance.domain.valueObjects.meterTypes import (
    CAPTURE_MANUAL,
    CAPTURE_SENSOR,
    METER_CUMULATIVE,
    QUALITY_SUSPECT,
    TRUSTED_QUALITIES,
    quantiseValue,
)
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MeterPointModel,
    MeterReadingModel,
)
from apps.sharedKernel.domain.errors import (
    DuplicateBusinessCodeError,
    EntityNotFoundError,
)


def _decimalOrNone(value: object) -> Decimal | None:
    return value if isinstance(value, Decimal) else None


def _quantisedOrNone(value: object) -> Decimal | None:
    """Give every aggregate the same scale the stored readings have."""
    if value is None:
        return None
    return quantiseValue(value if isinstance(value, Decimal) else Decimal(str(value)))


class MeterPointRepositoryDjango:
    """CRUD for meter-point definitions, tenant-scoped on every query."""

    @staticmethod
    def toPoint(model: MeterPointModel) -> MeterPoint:
        return MeterPoint(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            code=model.code,
            name=model.name,
            unit=model.unit,
            kind=model.kind,
            sensorKey=model.sensorKey,
            minimumValue=model.minimumValue,
            maximumValue=model.maximumValue,
            rolloverMaximum=model.rolloverMaximum,
            maximumStepPerHour=model.maximumStepPerHour,
            drivesRunningHours=model.drivesRunningHours,
            active=model.active,
            lastValue=model.lastValue,
            lastReadingAt=model.lastReadingAt,
            lastCaptureMode=model.lastCaptureMode,
            readingCount=model.readingCount,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )

    def _live(self, tenantId: uuid.UUID) -> QuerySet[MeterPointModel]:
        return MeterPointModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)

    def getById(self, tenantId: uuid.UUID, pointId: uuid.UUID) -> MeterPoint | None:
        model = self._live(tenantId).filter(id=pointId).first()
        return self.toPoint(model) if model else None

    def getByCode(self, tenantId: uuid.UUID, deviceId: uuid.UUID, code: str) -> MeterPoint | None:
        model = self._live(tenantId).filter(deviceId=deviceId, code=code).first()
        return self.toPoint(model) if model else None

    def getBySensorKey(self, tenantId: uuid.UUID, sensorKey: str) -> MeterPoint | None:
        """Resolve the gateway binding. Inactive points are deliberately
        returned so the caller can reject with a precise reason instead of a
        generic 'unknown key'."""
        if not sensorKey:
            return None
        model = self._live(tenantId).filter(sensorKey=sensorKey).first()
        return self.toPoint(model) if model else None

    def listForDevice(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, *, includeInactive: bool = True
    ) -> list[MeterPoint]:
        query = self._live(tenantId).filter(deviceId=deviceId)
        if not includeInactive:
            query = query.filter(active=True)
        return [self.toPoint(model) for model in query]

    def listForTenant(
        self,
        tenantId: uuid.UUID,
        *,
        search: str = "",
        kind: str = "",
        activeOnly: bool = False,
        limit: int = 500,
    ) -> list[MeterPoint]:
        query = self._live(tenantId)
        if kind:
            query = query.filter(kind=kind)
        if activeOnly:
            query = query.filter(active=True)
        if search:
            query = query.filter(
                Q(code__icontains=search)
                | Q(name__icontains=search)
                | Q(sensorKey__icontains=search)
            )
        return [self.toPoint(model) for model in query[:limit]]

    def runningHoursPoint(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> MeterPoint | None:
        model = (
            self._live(tenantId)
            .filter(deviceId=deviceId, drivesRunningHours=True, active=True)
            .first()
        )
        return self.toPoint(model) if model else None

    def create(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, payload: dict[str, object], now: datetime
    ) -> MeterPoint:
        code = str(payload["code"])
        if self._live(tenantId).filter(deviceId=deviceId, code=code).exists():
            raise DuplicateBusinessCodeError(f"Meter point '{code}' already exists on this device.")
        sensorKey = str(payload.get("sensorKey", "") or "")
        if sensorKey and self._live(tenantId).filter(sensorKey=sensorKey).exists():
            raise DuplicateBusinessCodeError(
                f"Sensor key '{sensorKey}' is already bound to another meter point."
            )
        drivesHours = bool(payload.get("drivesRunningHours", False))
        if drivesHours:
            self._clearRunningHoursFlag(tenantId, deviceId, now)
        model = MeterPointModel.objects.create(
            tenantId=tenantId,
            deviceId=deviceId,
            code=code,
            name=str(payload.get("name", "") or code),
            unit=str(payload.get("unit", "") or ""),
            kind=str(payload.get("kind", "gauge")),
            sensorKey=sensorKey,
            minimumValue=_decimalOrNone(payload.get("minimumValue")),
            maximumValue=_decimalOrNone(payload.get("maximumValue")),
            rolloverMaximum=_decimalOrNone(payload.get("rolloverMaximum")),
            maximumStepPerHour=_decimalOrNone(payload.get("maximumStepPerHour")),
            drivesRunningHours=drivesHours,
            active=bool(payload.get("active", True)),
            createdAt=now,
        )
        return self.toPoint(model)

    def update(
        self, tenantId: uuid.UUID, pointId: uuid.UUID, payload: dict[str, object], now: datetime
    ) -> MeterPoint:
        model = self._live(tenantId).filter(id=pointId).first()
        if model is None:
            raise EntityNotFoundError("Meter point")

        # ``kind`` is intentionally not updatable: flipping a gauge into a
        # counter would reinterpret every historical delta already stored.
        for field in ("name", "unit"):
            if field in payload:
                setattr(model, field, str(payload[field] or ""))
        if "sensorKey" in payload:
            sensorKey = str(payload["sensorKey"] or "")
            clash = (
                self._live(tenantId).filter(sensorKey=sensorKey).exclude(id=pointId).exists()
                if sensorKey
                else False
            )
            if clash:
                raise DuplicateBusinessCodeError(
                    f"Sensor key '{sensorKey}' is already bound to another meter point."
                )
            model.sensorKey = sensorKey
        for field in (
            "minimumValue",
            "maximumValue",
            "rolloverMaximum",
            "maximumStepPerHour",
        ):
            if field in payload:
                setattr(model, field, _decimalOrNone(payload[field]))
        if "active" in payload:
            model.active = bool(payload["active"])
        if "drivesRunningHours" in payload:
            drivesHours = bool(payload["drivesRunningHours"])
            if drivesHours and not model.drivesRunningHours:
                self._clearRunningHoursFlag(tenantId, model.deviceId, now, exclude=pointId)
            model.drivesRunningHours = drivesHours
        model.updatedAt = now
        model.save()
        return self.toPoint(model)

    def softDelete(self, tenantId: uuid.UUID, pointId: uuid.UUID, now: datetime) -> None:
        """Retire a point. Readings survive — the FK is PROTECT and the series
        remains queryable, because deleting history to tidy a dropdown is how
        plants lose their maintenance record."""
        model = self._live(tenantId).filter(id=pointId).first()
        if model is None:
            raise EntityNotFoundError("Meter point")
        model.deletedAt = now
        model.active = False
        # The unique sensor-key index is filtered on ``deletedAt IS NULL``, so
        # retiring a point frees its key for the replacement instrument.
        model.save(update_fields=["deletedAt", "active"])

    def _clearRunningHoursFlag(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        now: datetime,
        exclude: uuid.UUID | None = None,
    ) -> None:
        """At most one point per device may own Device.runningHours."""
        query = self._live(tenantId).filter(deviceId=deviceId, drivesRunningHours=True)
        if exclude:
            query = query.exclude(id=exclude)
        query.update(drivesRunningHours=False, updatedAt=now)


class MeterReadingRepositoryDjango:
    """Append-only reading stream plus its derived read models."""

    @staticmethod
    def toReading(model: MeterReadingModel) -> MeterReading:
        return MeterReading(
            id=model.id,
            tenantId=model.tenantId,
            deviceId=model.deviceId,
            meterPointId=model.meterPoint_id,
            value=model.value,
            capturedAt=model.capturedAt,
            captureMode=model.captureMode,
            quality=model.quality,
            delta=model.delta,
            rolloverApplied=model.rolloverApplied,
            note=model.note,
            sensorKey=model.sensorKey,
            sourceRef=model.sourceRef,
            ingestionKey=model.ingestionKey or "",
            recordedById=model.recordedById,
            recordedByName=model.recordedByName,
            correctsReadingId=model.correctsReadingId,
            supersededByReadingId=model.supersededByReadingId,
            correlationId=model.correlationId,
            createdAt=model.createdAt,
        )

    # -- reads ------------------------------------------------------------------
    def getById(self, tenantId: uuid.UUID, readingId: uuid.UUID) -> MeterReading | None:
        model = MeterReadingModel.objects.filter(tenantId=tenantId, id=readingId).first()
        return self.toReading(model) if model else None

    def findByIngestionKey(self, tenantId: uuid.UUID, ingestionKey: str) -> MeterReading | None:
        if not ingestionKey:
            return None
        model = MeterReadingModel.objects.filter(
            tenantId=tenantId, ingestionKey=ingestionKey
        ).first()
        return self.toReading(model) if model else None

    def previousReading(
        self, tenantId: uuid.UUID, pointId: uuid.UUID, capturedAt: datetime
    ) -> MeterReading | None:
        """Latest trusted, un-superseded reading strictly before ``capturedAt``.

        Superseded and untrusted rows are skipped so a corrected mistake stops
        poisoning the deltas of everything recorded after it.
        """
        model = (
            MeterReadingModel.objects.filter(
                tenantId=tenantId,
                meterPoint_id=pointId,
                capturedAt__lt=capturedAt,
                supersededByReadingId__isnull=True,
                quality__in=TRUSTED_QUALITIES,
            )
            .order_by("-capturedAt", "-createdAt")
            .first()
        )
        return self.toReading(model) if model else None

    def latestReading(self, tenantId: uuid.UUID, pointId: uuid.UUID) -> MeterReading | None:
        model = (
            MeterReadingModel.objects.filter(
                tenantId=tenantId,
                meterPoint_id=pointId,
                supersededByReadingId__isnull=True,
                quality__in=TRUSTED_QUALITIES,
            )
            .order_by("-capturedAt", "-createdAt")
            .first()
        )
        return self.toReading(model) if model else None

    def listReadings(
        self,
        tenantId: uuid.UUID,
        *,
        deviceId: uuid.UUID | None = None,
        pointId: uuid.UUID | None = None,
        captureMode: str = "",
        quality: str = "",
        fromMoment: datetime | None = None,
        toMoment: datetime | None = None,
        includeSuperseded: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[MeterReading], int]:
        query = MeterReadingModel.objects.filter(tenantId=tenantId)
        if deviceId:
            query = query.filter(deviceId=deviceId)
        if pointId:
            query = query.filter(meterPoint_id=pointId)
        if captureMode:
            query = query.filter(captureMode=captureMode)
        if quality:
            query = query.filter(quality=quality)
        if fromMoment:
            query = query.filter(capturedAt__gte=fromMoment)
        if toMoment:
            query = query.filter(capturedAt__lte=toMoment)
        if not includeSuperseded:
            query = query.filter(supersededByReadingId__isnull=True)
        total = query.count()
        rows = query.order_by("-capturedAt", "-createdAt")[offset : offset + limit]
        return [self.toReading(model) for model in rows], total

    def summarise(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        *,
        fromMoment: datetime | None = None,
        toMoment: datetime | None = None,
    ) -> MeterPointSummary:
        """Aggregate one point over a window.

        Only trusted, un-superseded rows feed min/max/avg/sum, so a single
        mistyped digit cannot distort a monthly consumption figure. The
        suspect rows are still *counted* and reported separately — hiding them
        entirely would make a failing sensor invisible.
        """
        base = MeterReadingModel.objects.filter(tenantId=tenantId, meterPoint_id=point.id)
        if fromMoment:
            base = base.filter(capturedAt__gte=fromMoment)
        if toMoment:
            base = base.filter(capturedAt__lte=toMoment)

        counts = base.aggregate(
            total=Count("id"),
            manual=Count("id", filter=Q(captureMode=CAPTURE_MANUAL)),
            sensor=Count("id", filter=Q(captureMode=CAPTURE_SENSOR)),
            suspect=Count("id", filter=Q(quality=QUALITY_SUSPECT)),
        )
        trusted = base.filter(supersededByReadingId__isnull=True, quality__in=TRUSTED_QUALITIES)
        stats = trusted.aggregate(
            minimum=Min("value"),
            maximum=Max("value"),
            average=Avg("value"),
            consumption=Sum("delta"),
        )
        firstRow = trusted.order_by("capturedAt", "createdAt").first()
        lastRow = trusted.order_by("-capturedAt", "-createdAt").first()

        average = stats["average"]
        return MeterPointSummary(
            meterPointId=point.id,
            code=point.code,
            name=point.name,
            unit=point.unit,
            kind=point.kind,
            readingCount=counts["total"] or 0,
            manualCount=counts["manual"] or 0,
            sensorCount=counts["sensor"] or 0,
            suspectCount=counts["suspect"] or 0,
            firstValue=firstRow.value if firstRow else None,
            lastValue=lastRow.value if lastRow else None,
            # Aggregates come back from the database without the stored scale,
            # so quantise them: one payload must not mix "70" with "70.0000".
            minimumValue=_quantisedOrNone(stats["minimum"]),
            maximumValue=_quantisedOrNone(stats["maximum"]),
            averageValue=_quantisedOrNone(average),
            # A consumption total only means something for a counter.
            totalConsumption=(
                _quantisedOrNone(stats["consumption"]) if point.kind == METER_CUMULATIVE else None
            ),
            firstCapturedAt=firstRow.capturedAt if firstRow else None,
            lastCapturedAt=lastRow.capturedAt if lastRow else None,
        )

    # -- append -----------------------------------------------------------------
    def append(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        payload: dict[str, object],
        now: datetime,
    ) -> MeterReading:
        """Insert one reading and refresh the derived state it feeds.

        Everything here runs under the meter point's row lock, taken by
        :meth:`lockPoint`, so the previous-reading lookup the caller made
        cannot be invalidated between the read and this write.
        """
        model = MeterReadingModel.objects.create(
            tenantId=tenantId,
            deviceId=point.deviceId,
            meterPoint_id=point.id,
            value=payload["value"],
            delta=payload.get("delta"),
            capturedAt=payload["capturedAt"],
            captureMode=str(payload.get("captureMode", CAPTURE_MANUAL)),
            quality=str(payload.get("quality", "good")),
            rolloverApplied=bool(payload.get("rolloverApplied", False)),
            note=str(payload.get("note", "") or "")[:500],
            sensorKey=str(payload.get("sensorKey", "") or ""),
            sourceRef=str(payload.get("sourceRef", "") or "")[:160],
            ingestionKey=(str(payload["ingestionKey"]) if payload.get("ingestionKey") else None),
            recordedById=payload.get("recordedById"),
            recordedByName=str(payload.get("recordedByName", "") or "")[:160],
            correctsReadingId=payload.get("correctsReadingId"),
            correlationId=str(payload.get("correlationId", "") or "")[:64],
            createdAt=now,
        )
        self._refreshPointState(tenantId, point, model, now)
        return self.toReading(model)

    def lockPoint(self, tenantId: uuid.UUID, pointId: uuid.UUID) -> MeterPoint:
        """Serialise concurrent appends to one meter point."""
        model = (
            MeterPointModel.objects.select_for_update()
            .filter(tenantId=tenantId, id=pointId, deletedAt__isnull=True)
            .first()
        )
        if model is None:
            raise EntityNotFoundError("Meter point")
        return MeterPointRepositoryDjango.toPoint(model)

    def markSuperseded(
        self, tenantId: uuid.UUID, readingId: uuid.UUID, correctionId: uuid.UUID
    ) -> bool:
        """Link a mistake to its correction. Returns False if already linked."""
        updated = MeterReadingModel.objects.filter(tenantId=tenantId).markSuperseded(
            readingId, correctionId
        )
        return bool(updated)

    def _refreshPointState(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        model: MeterReadingModel,
        now: datetime,
    ) -> None:
        """Keep the point's cached 'current value' and Device.runningHours true.

        A back-dated reading must not overwrite the cached latest value with an
        older number, so the cache is only advanced when the new row really is
        the newest one.
        """
        pointRow = MeterPointModel.objects.filter(tenantId=tenantId, id=point.id).first()
        if pointRow is None:  # pragma: no cover — locked row cannot vanish
            return
        pointRow.readingCount = (pointRow.readingCount or 0) + 1
        isNewest = pointRow.lastReadingAt is None or model.capturedAt >= pointRow.lastReadingAt
        if isNewest and model.quality in TRUSTED_QUALITIES:
            pointRow.lastValue = model.value
            pointRow.lastReadingAt = model.capturedAt
            pointRow.lastCaptureMode = model.captureMode
        pointRow.updatedAt = now
        pointRow.save(
            update_fields=[
                "readingCount",
                "lastValue",
                "lastReadingAt",
                "lastCaptureMode",
                "updatedAt",
            ]
        )

        if not (isNewest and model.quality in TRUSTED_QUALITIES):
            return

        if pointRow.drivesRunningHours:
            # Device.runningHours is now *derived*: it always traces back to a
            # dated, attributed reading instead of being typed into a form.
            DeviceModel.objects.filter(tenantId=tenantId, id=point.deviceId).update(
                runningHours=model.value, updatedAt=now
            )

        # Push the new value onto every PM plan watching this meter, so a
        # meter-driven plan becomes due the moment the reading lands rather
        # than waiting for someone to open the device page.
        from apps.maintenance.infrastructure.repositories.assetRegistryRepositoryImpl import (
            DeviceRegistryRepositoryDjango,
        )

        DeviceRegistryRepositoryDjango().refreshPlanMeterValues(
            tenantId, point.deviceId, pointRow.code, model.value
        )

    # -- PM trigger support ------------------------------------------------------
    def currentValuesByCode(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> dict[str, Decimal]:
        """Latest trusted value of every active meter point on a device."""
        return {
            row.code: row.lastValue
            for row in MeterPointModel.objects.filter(
                tenantId=tenantId,
                deviceId=deviceId,
                deletedAt__isnull=True,
                lastValue__isnull=False,
            )
        }

    @staticmethod
    def atomicBlock():  # noqa: ANN205 — thin passthrough for the use-case layer
        return transaction.atomic()


__all__ = ["MeterPointRepositoryDjango", "MeterReadingRepositoryDjango"]
