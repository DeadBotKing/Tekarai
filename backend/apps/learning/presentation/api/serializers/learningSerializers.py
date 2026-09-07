"""Strict Phase 16 REST input serializers."""

from rest_framework import serializers


class ExperienceSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=120)
    context = serializers.DictField(default=dict)
    input = serializers.DictField(default=dict)
    action = serializers.CharField(max_length=160)
    expectedOutcome = serializers.DictField(default=dict)
    actualOutcome = serializers.DictField(default=dict)
    reward = serializers.FloatField(required=False, allow_null=True, default=None)
    success = serializers.BooleanField(required=False, allow_null=True, default=None)
    traceId = serializers.CharField(max_length=160)
    metadata = serializers.DictField(default=dict)


class DatasetSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    version = serializers.CharField(max_length=48)
    source = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    metadata = serializers.DictField(default=dict)


class SampleSerializer(serializers.Serializer):
    input = serializers.DictField(default=dict)
    target = serializers.DictField(default=dict)
    context = serializers.DictField(default=dict)
    sourceExperienceId = serializers.UUIDField()
    weight = serializers.FloatField(default=1.0)
    metadata = serializers.DictField(default=dict)


class BuildDatasetSerializer(serializers.Serializer):
    samples = SampleSerializer(many=True, allow_empty=False)


class ValidateDatasetSerializer(serializers.Serializer):
    minimumSamples = serializers.IntegerField(min_value=1, max_value=100_000, default=1)


class ExperimentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    datasetId = serializers.UUIDField()
    algorithm = serializers.CharField(max_length=120)
    configuration = serializers.DictField(default=dict)
    baselineArtifactId = serializers.UUIDField(required=False, allow_null=True, default=None)


class RunExperimentSerializer(serializers.Serializer):
    idempotencyKey = serializers.CharField(min_length=8, max_length=160)
    priority = serializers.ChoiceField(choices=("LOW", "NORMAL", "HIGH"), default="NORMAL")


class ArtifactActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    environment = serializers.CharField(required=False, default="PRODUCTION", max_length=80)
    trafficPercentage = serializers.IntegerField(required=False, default=0)
    policy = serializers.DictField(default=dict)


class FeedbackSerializer(serializers.Serializer):
    source = serializers.CharField(max_length=120)
    feedbackType = serializers.CharField(max_length=16)
    experienceId = serializers.UUIDField(required=False, allow_null=True, default=None)
    deploymentId = serializers.UUIDField(required=False, allow_null=True, default=None)
    artifactId = serializers.UUIDField(required=False, allow_null=True, default=None)
    humanAction = serializers.CharField(required=False, allow_blank=True, default="", max_length=16)
    score = serializers.FloatField(required=False, allow_null=True, default=None)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    metadata = serializers.DictField(default=dict)


class MetricsSerializer(serializers.Serializer):
    artifactId = serializers.UUIDField()
    deploymentId = serializers.UUIDField(required=False, allow_null=True, default=None)
    metrics = serializers.DictField(child=serializers.FloatField(), allow_empty=False)


class DriftSerializer(serializers.Serializer):
    artifactId = serializers.UUIDField()
    driftType = serializers.CharField(default="PERFORMANCE", max_length=24)
    baselineMetrics = serializers.DictField(child=serializers.FloatField(), allow_empty=False)
    thresholds = serializers.DictField(child=serializers.FloatField(), allow_empty=False)
