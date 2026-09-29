"""Django persistence for MetricDefinition and append-only MetricReading."""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from apps.analytics.domain.exceptions.metricErrors import MetricReadingImmutableError


class MetricDefinitionModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=200)
    description = models.CharField(max_length=1000, blank=True, default="")
    formula = models.CharField(max_length=500, blank=True, default="")
    unit = models.CharField(max_length=32, blank=True, default="")
    aggregation = models.CharField(max_length=16, default="LAST")
    minimumValue = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    maximumValue = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    isActive = models.BooleanField(default=True, db_index=True)
    createdAt = models.DateTimeField(default=timezone.now, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MetricDefinition"
        ordering = ["code"]
        indexes = [models.Index(fields=["tenantId", "isActive"], name="ix_mdef_tenant_active")]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_mdef_tenant_code",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    aggregation__in=("LAST", "SUM", "AVERAGE", "MIN", "MAX", "COUNT")
                ),
                name="ck_mdef_aggregation",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(minimumValue__isnull=True)
                    | models.Q(maximumValue__isnull=True)
                    | models.Q(minimumValue__lte=models.F("maximumValue"))
                ),
                name="ck_mdef_value_range",
            ),
        ]


class MetricReadingQuerySet(models.QuerySet):
    """Block accidental bulk mutation of the append-only metric stream."""

    def update(self, **kwargs) -> int:  # noqa: ANN003 — Django QuerySet contract
        raise MetricReadingImmutableError("Metric readings cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise MetricReadingImmutableError("Metric readings cannot be deleted.")


class MetricReadingModel(models.Model):
    """Immutable metric point; update/delete are not part of the public model API."""

    objects = MetricReadingQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    metric = models.ForeignKey(
        MetricDefinitionModel,
        on_delete=models.PROTECT,
        related_name="readings",
        db_column="metricId",
    )
    value = models.DecimalField(max_digits=18, decimal_places=6)
    dimensions = models.JSONField(default=dict, blank=True)
    quality = models.CharField(max_length=12, default="GOOD")
    periodStart = models.DateTimeField(db_index=True)
    periodEnd = models.DateTimeField(db_index=True)
    sourceType = models.CharField(max_length=64, blank=True, default="")
    sourceId = models.CharField(max_length=128, blank=True, default="")
    ingestionKey = models.CharField(max_length=128, null=True, blank=True)
    recordedAt = models.DateTimeField(default=timezone.now, db_index=True)
    recordedById = models.UUIDField(null=True, blank=True)
    correlationId = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "MetricReading"
        ordering = ["-periodStart", "-id"]
        indexes = [
            models.Index(
                fields=["tenantId", "metric", "periodStart"],
                name="ix_mread_tenant_metric_time",
            ),
            models.Index(
                fields=["tenantId", "sourceType", "sourceId", "periodStart"],
                name="ix_mread_tenant_source_time",
            ),
            models.Index(fields=["tenantId", "recordedAt"], name="ix_mread_tenant_recorded"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "ingestionKey"],
                condition=models.Q(ingestionKey__isnull=False),
                name="uq_mread_tenant_ingestion",
            ),
            models.CheckConstraint(
                condition=models.Q(quality__in=("GOOD", "SUSPECT", "BAD", "UNKNOWN")),
                name="ck_mread_quality",
            ),
            models.CheckConstraint(
                condition=models.Q(periodEnd__gte=models.F("periodStart")),
                name="ck_mread_period",
            ),
        ]

    def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        if not self._state.adding:
            raise MetricReadingImmutableError("Metric readings cannot be updated.")
        if (
            self.metric_id
            and not MetricDefinitionModel.objects.filter(
                id=self.metric_id,
                tenantId=self.tenantId,
                deletedAt__isnull=True,
            ).exists()
        ):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Metric definition must belong to the reading tenant.",
                fieldErrors={"metricId": "tenant mismatch or deleted reference"},
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise MetricReadingImmutableError("Metric readings cannot be deleted individually.")
