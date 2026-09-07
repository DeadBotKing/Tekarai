import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="EvaluationResultModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("datasetId", models.UUIDField()),
                ("datasetVersion", models.CharField(max_length=48)),
                ("metrics", models.JSONField(default=dict)),
                ("businessMetrics", models.JSONField(default=dict)),
                ("baselineArtifactId", models.UUIDField(blank=True, null=True)),
                ("baselineComparison", models.JSONField(default=dict)),
                ("durationMs", models.PositiveIntegerField(default=0)),
                ("evaluatorVersion", models.CharField(max_length=80)),
            ],
            options={
                "db_table": "evaluationResults",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "artifactId", "createdAt"], name="IX_LearnEval_t_art"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningApprovalModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("reviewerId", models.UUIDField()),
                ("decision", models.CharField(max_length=12)),
                ("reason", models.TextField()),
                ("decidedAt", models.DateTimeField()),
            ],
            options={
                "db_table": "learningApprovals",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "artifactId", "reviewerId"),
                        name="UQ_LearnApproval_t_art_user",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningArtifactModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactType", models.CharField(max_length=24)),
                ("name", models.CharField(max_length=160)),
                ("version", models.CharField(max_length=48)),
                ("storageUri", models.CharField(max_length=1000)),
                ("checksum", models.CharField(db_index=True, max_length=64)),
                ("createdByRunId", models.UUIDField(db_index=True)),
                ("status", models.CharField(db_index=True, max_length=24)),
                ("metadata", models.JSONField(default=dict)),
                ("updatedAt", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "learningArtifacts",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "status", "createdAt"], name="IX_LearnArtifact_t_status"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "name", "version"), name="UQ_LearnArtifact_t_name_ver"
                    ),
                    models.UniqueConstraint(
                        fields=("tenantId", "checksum"), name="UQ_LearnArtifact_t_checksum"
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningAuditModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("actorId", models.UUIDField(blank=True, null=True)),
                ("action", models.CharField(db_index=True, max_length=64)),
                ("targetType", models.CharField(max_length=48)),
                ("targetId", models.CharField(max_length=120)),
                ("previousState", models.JSONField(default=dict)),
                ("newState", models.JSONField(default=dict)),
                ("metadata", models.JSONField(default=dict)),
                ("auditHash", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "learningAudits",
                "indexes": [
                    models.Index(fields=["tenantId", "createdAt"], name="IX_LearnAudit_t_time")
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningDatasetModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("name", models.CharField(max_length=160)),
                ("version", models.CharField(max_length=48)),
                ("description", models.TextField(blank=True)),
                ("source", models.CharField(max_length=120)),
                ("status", models.CharField(db_index=True, max_length=20)),
                ("sampleCount", models.PositiveIntegerField(default=0)),
                ("datasetHash", models.CharField(blank=True, max_length=64)),
                ("createdById", models.UUIDField()),
                ("metadata", models.JSONField(default=dict)),
                ("updatedAt", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "learningDatasets",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "status", "createdAt"], name="IX_LearnData_t_status"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "name", "version"), name="UQ_LearnData_t_name_ver"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningDeploymentModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("artifactVersion", models.CharField(max_length=48)),
                ("artifactName", models.CharField(max_length=160)),
                ("environment", models.CharField(max_length=80)),
                ("status", models.CharField(db_index=True, max_length=24)),
                ("trafficPercentage", models.PositiveSmallIntegerField(default=0)),
                ("previousDeploymentId", models.UUIDField(blank=True, null=True)),
                ("startedAt", models.DateTimeField()),
                ("completedAt", models.DateTimeField(blank=True, null=True)),
                ("deployedById", models.UUIDField()),
                ("rollbackReason", models.TextField(blank=True)),
            ],
            options={
                "db_table": "learningDeployments",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "environment", "status"], name="IX_LearnDeploy_t_env"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningEventModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("eventType", models.CharField(db_index=True, max_length=80)),
                ("targetType", models.CharField(max_length=48)),
                ("targetId", models.CharField(max_length=120)),
                ("data", models.JSONField(default=dict)),
                ("occurredAt", models.DateTimeField(db_index=True)),
                ("eventHash", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "learningEvents",
                "indexes": [
                    models.Index(fields=["tenantId", "occurredAt"], name="IX_LearnEvent_t_time")
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningExperienceModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("source", models.CharField(max_length=120)),
                ("context", models.JSONField(default=dict)),
                ("inputData", models.JSONField(default=dict)),
                ("action", models.CharField(max_length=160)),
                ("expectedOutcome", models.JSONField(default=dict)),
                ("actualOutcome", models.JSONField(default=dict)),
                ("reward", models.FloatField(blank=True, null=True)),
                ("success", models.BooleanField(blank=True, null=True)),
                ("occurredAt", models.DateTimeField(db_index=True)),
                ("metadata", models.JSONField(default=dict)),
                ("traceId", models.CharField(db_index=True, max_length=160)),
                ("integrityHash", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "learningExperiences",
                "indexes": [
                    models.Index(fields=["tenantId", "occurredAt"], name="IX_LearnExp_t_time")
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "traceId"), name="UQ_LearnExp_t_trace"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningExperimentModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("name", models.CharField(max_length=160)),
                ("description", models.TextField(blank=True)),
                ("datasetId", models.UUIDField(db_index=True)),
                ("datasetVersion", models.CharField(max_length=48)),
                ("algorithm", models.CharField(max_length=120)),
                ("configuration", models.JSONField(default=dict)),
                ("baselineArtifactId", models.UUIDField(blank=True, null=True)),
                ("status", models.CharField(db_index=True, max_length=20)),
                ("completedAt", models.DateTimeField(blank=True, null=True)),
                ("createdById", models.UUIDField()),
            ],
            options={
                "db_table": "learningExperiments",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "status", "createdAt"],
                        name="IX_LearnExperiment_t_status",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "name"), name="UQ_LearnExperiment_t_name"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningFeedbackModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("experienceId", models.UUIDField(blank=True, db_index=True, null=True)),
                ("deploymentId", models.UUIDField(blank=True, db_index=True, null=True)),
                ("artifactId", models.UUIDField(blank=True, db_index=True, null=True)),
                ("feedbackType", models.CharField(max_length=16)),
                ("humanAction", models.CharField(blank=True, max_length=16)),
                ("score", models.FloatField(blank=True, null=True)),
                ("source", models.CharField(max_length=120)),
                ("comment", models.TextField(blank=True)),
                ("createdById", models.UUIDField(blank=True, null=True)),
                ("metadata", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "learningFeedback",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "artifactId", "createdAt"],
                        name="IX_LearnFeedback_t_art",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningJobModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("jobType", models.CharField(default="EXPERIMENT_RUN", max_length=48)),
                ("experimentId", models.UUIDField(db_index=True)),
                ("status", models.CharField(db_index=True, max_length=20)),
                ("priority", models.CharField(max_length=16)),
                ("requestedById", models.UUIDField()),
                ("idempotencyKey", models.CharField(max_length=160)),
                ("startedAt", models.DateTimeField(blank=True, null=True)),
                ("completedAt", models.DateTimeField(blank=True, null=True)),
                ("retryCount", models.PositiveIntegerField(default=0)),
                ("errorCode", models.CharField(blank=True, max_length=80)),
                ("errorMessage", models.CharField(blank=True, max_length=500)),
                ("metadata", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "learningJobs",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "status", "createdAt"], name="IX_LearnJob_t_status"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "idempotencyKey"), name="UQ_LearnJob_t_idem"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningMetricModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("deploymentId", models.UUIDField(blank=True, null=True)),
                ("metricName", models.CharField(max_length=120)),
                ("metricValue", models.FloatField()),
                ("observedAt", models.DateTimeField(db_index=True)),
                ("dimensions", models.JSONField(default=dict)),
            ],
            options={
                "db_table": "learningMetrics",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "artifactId", "metricName", "observedAt"],
                        name="IX_LearnMetric_t_art_name",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningRunModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("experimentId", models.UUIDField(db_index=True)),
                ("startedAt", models.DateTimeField(blank=True, null=True)),
                ("finishedAt", models.DateTimeField(blank=True, null=True)),
                ("parameters", models.JSONField(default=dict)),
                ("environment", models.JSONField(default=dict)),
                ("dependencyVersions", models.JSONField(default=dict)),
                ("datasetHash", models.CharField(max_length=64)),
                ("codeVersion", models.CharField(max_length=80)),
                ("artifactId", models.UUIDField(blank=True, null=True)),
                ("metrics", models.JSONField(default=dict)),
                ("logs", models.JSONField(default=list)),
                ("randomSeed", models.BigIntegerField()),
                ("status", models.CharField(db_index=True, max_length=20)),
                ("errorCode", models.CharField(blank=True, max_length=80)),
                ("errorMessage", models.CharField(blank=True, max_length=500)),
            ],
            options={
                "db_table": "learningRuns",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "experimentId", "createdAt"], name="IX_LearnRun_t_exp"
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningSampleModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("datasetId", models.UUIDField(db_index=True)),
                ("inputData", models.JSONField(default=dict)),
                ("target", models.JSONField(default=dict)),
                ("context", models.JSONField(default=dict)),
                ("sourceExperienceId", models.UUIDField(db_index=True)),
                ("weight", models.FloatField(default=1.0)),
                ("metadata", models.JSONField(default=dict)),
                ("sampleHash", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "learningSamples",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "datasetId", "createdAt"], name="IX_LearnSample_t_data"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "datasetId", "sampleHash"),
                        name="UQ_LearnSample_t_data_hash",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="LearningSnapshotModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("deploymentId", models.UUIDField(db_index=True)),
                ("state", models.JSONField(default=dict)),
                ("checksum", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "learningSnapshots",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "deploymentId", "checksum"),
                        name="UQ_LearnSnap_t_dep_hash",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ModelVersionModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("modelName", models.CharField(max_length=160)),
                ("version", models.CharField(max_length=48)),
                ("checksum", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "modelVersions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "modelName", "version"),
                        name="UQ_ModelVersion_t_name_ver",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PolicyVersionModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("policyName", models.CharField(max_length=160)),
                ("version", models.CharField(max_length=48)),
                ("policy", models.JSONField(default=dict)),
                ("checksum", models.CharField(max_length=64)),
            ],
            options={
                "db_table": "policyVersions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("tenantId", "policyName", "version"),
                        name="UQ_PolicyVersion_t_name_ver",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="ValidationResultModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("createdAt", models.DateTimeField(auto_now_add=True)),
                ("artifactId", models.UUIDField(db_index=True)),
                ("evaluationId", models.UUIDField()),
                ("decision", models.CharField(db_index=True, max_length=12)),
                ("checks", models.JSONField(default=list)),
                ("failures", models.JSONField(default=list)),
                ("policySnapshot", models.JSONField(default=dict)),
                ("reproducibilityHash", models.CharField(max_length=64)),
                ("validatorVersion", models.CharField(max_length=80)),
            ],
            options={
                "db_table": "validationResults",
                "indexes": [
                    models.Index(
                        fields=["tenantId", "artifactId", "createdAt"], name="IX_LearnValid_t_art"
                    )
                ],
            },
        ),
    ]
