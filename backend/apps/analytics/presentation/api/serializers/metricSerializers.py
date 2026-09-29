"""DRF input validation for the Analytics API boundary."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.analytics.domain.valueObjects.metricTypes import (
    METRIC_AGGREGATIONS,
    METRIC_QUALITIES,
)


class MetricDefinitionCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, default=""
    )
    formula = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    unit = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    aggregation = serializers.CharField(max_length=16, required=False, default="LAST")
    minimumValue = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        required=False,
        allow_null=True,
        default=None,
    )
    maximumValue = serializers.DecimalField(
        max_digits=18,
        decimal_places=6,
        required=False,
        allow_null=True,
        default=None,
    )

    def validate(self, attrs):  # noqa: ANN001, ANN201 — DRF serializer contract
        aggregation = str(attrs.get("aggregation", "LAST")).upper()
        if aggregation not in METRIC_AGGREGATIONS:
            raise serializers.ValidationError({"aggregation": "Unsupported aggregation."})
        attrs["aggregation"] = aggregation
        minimum = attrs.get("minimumValue")
        maximum = attrs.get("maximumValue")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise serializers.ValidationError(
                {"minimumValue": "Must be less than or equal to maximumValue."}
            )
        return attrs


class MetricDefinitionUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    formula = serializers.CharField(max_length=500, required=False, allow_blank=True)
    unit = serializers.CharField(max_length=32, required=False, allow_blank=True)
    aggregation = serializers.CharField(max_length=16, required=False)
    minimumValue = serializers.DecimalField(
        max_digits=18, decimal_places=6, required=False, allow_null=True
    )
    maximumValue = serializers.DecimalField(
        max_digits=18, decimal_places=6, required=False, allow_null=True
    )
    isActive = serializers.BooleanField(required=False)

    def validate(self, attrs):  # noqa: ANN001, ANN201 — DRF serializer contract
        if "aggregation" in attrs:
            aggregation = str(attrs["aggregation"]).upper()
            if aggregation not in METRIC_AGGREGATIONS:
                raise serializers.ValidationError({"aggregation": "Unsupported aggregation."})
            attrs["aggregation"] = aggregation
        return attrs


class MetricReadingInputSerializer(serializers.Serializer):
    metricId = serializers.UUIDField(required=False, allow_null=True)
    metricCode = serializers.CharField(max_length=64, required=False, allow_blank=True)
    value = serializers.DecimalField(max_digits=18, decimal_places=6)
    # ``occurredAt`` is an ergonomic alias for instantaneous measurements.
    occurredAt = serializers.DateTimeField(required=False, write_only=True)
    periodStart = serializers.DateTimeField(required=False)
    periodEnd = serializers.DateTimeField(required=False)
    dimensions = serializers.JSONField(required=False, default=dict)
    quality = serializers.CharField(max_length=12, required=False, default="GOOD")
    sourceType = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    sourceId = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    ingestionKey = serializers.CharField(
        max_length=128,
        required=False,
        allow_blank=True,
        trim_whitespace=True,
        default="",
    )

    def validate(self, attrs):  # noqa: ANN001, ANN201 — DRF serializer contract
        metricId = attrs.get("metricId")
        metricCode = str(attrs.get("metricCode", "")).strip()
        if bool(metricId) == bool(metricCode):
            raise serializers.ValidationError(
                {"metricId": "Supply exactly one of metricId or metricCode."}
            )
        occurredAt = attrs.pop("occurredAt", None)
        periodStart = attrs.get("periodStart")
        if occurredAt and periodStart and occurredAt != periodStart:
            raise serializers.ValidationError(
                {"occurredAt": "Must equal periodStart when both are supplied."}
            )
        periodStart = periodStart or occurredAt
        if periodStart is None:
            raise serializers.ValidationError({"periodStart": "This field is required."})
        attrs["periodStart"] = periodStart
        attrs["periodEnd"] = attrs.get("periodEnd") or periodStart
        quality = str(attrs.get("quality", "GOOD")).upper()
        if quality not in METRIC_QUALITIES:
            raise serializers.ValidationError({"quality": "Unsupported quality."})
        attrs["quality"] = quality
        if bool(attrs.get("sourceType")) != bool(attrs.get("sourceId")):
            raise serializers.ValidationError(
                {"sourceId": "sourceType and sourceId must be supplied together."}
            )
        return attrs


class MetricReadingBatchSerializer(serializers.Serializer):
    readings = MetricReadingInputSerializer(many=True, allow_empty=False, max_length=500)


class MetricDefinitionListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, default="")
    isActive = serializers.BooleanField(required=False, allow_null=True, default=None)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    pageSize = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)


class MetricReadingListQuerySerializer(serializers.Serializer):
    metricId = serializers.UUIDField(required=False, allow_null=True)
    metricCode = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    quality = serializers.CharField(max_length=12, required=False, allow_blank=True, default="")
    sourceType = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    sourceId = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    fromTime = serializers.DateTimeField(required=False, allow_null=True, default=None)
    toTime = serializers.DateTimeField(required=False, allow_null=True, default=None)
    ordering = serializers.ChoiceField(
        choices=(
            "periodStart",
            "-periodStart",
            "periodEnd",
            "-periodEnd",
            "recordedAt",
            "-recordedAt",
            "value",
            "-value",
            "quality",
            "-quality",
        ),
        required=False,
        default="-periodStart",
    )
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    pageSize = serializers.IntegerField(required=False, min_value=1, max_value=500, default=100)

    def validate(self, attrs):  # noqa: ANN001, ANN201 — DRF serializer contract
        if attrs.get("metricId") and attrs.get("metricCode"):
            raise serializers.ValidationError(
                {"metricId": "metricId and metricCode are mutually exclusive."}
            )
        if attrs.get("fromTime") and attrs.get("toTime"):
            if attrs["toTime"] < attrs["fromTime"]:
                raise serializers.ValidationError({"to": "Must be after or equal to from."})
        if attrs.get("quality"):
            quality = str(attrs["quality"]).upper()
            if quality not in METRIC_QUALITIES:
                raise serializers.ValidationError({"quality": "Unsupported quality."})
            attrs["quality"] = quality
        return attrs


class MetricReadingSummaryQuerySerializer(MetricReadingListQuerySerializer):
    # Pagination/ordering are harmless at validation and ignored by summary.
    pass


def optionalDecimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
