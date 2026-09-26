from __future__ import annotations

import uuid

from django.db import migrations, models

import apps.maintenance.infrastructure.models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0005_spare_parts_inventory")]

    operations = [
        migrations.CreateModel(
            name="MaintenanceAttachmentModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("targetType", models.CharField(db_index=True, max_length=20)),
                ("targetId", models.UUIDField(db_index=True)),
                ("category", models.CharField(default="other", max_length=20)),
                ("originalName", models.CharField(max_length=255)),
                ("mimeType", models.CharField(max_length=120)),
                ("sizeBytes", models.PositiveBigIntegerField()),
                (
                    "file",
                    models.FileField(
                        max_length=500,
                        upload_to=apps.maintenance.infrastructure.models.maintenanceAttachmentPath,
                    ),
                ),
                ("uploadedAt", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("deletedAt", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "MaintenanceAttachment", "ordering": ["-uploadedAt"]},
        ),
        migrations.AddIndex(
            model_name="maintenanceattachmentmodel",
            index=models.Index(
                fields=["tenantId", "targetType", "targetId"],
                name="Maintenance_tenantI_d9feda_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="maintenanceattachmentmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(targetType__in=("device", "workOrder")),
                name="ck_maintenance_attachment_target",
            ),
        ),
        migrations.AddConstraint(
            model_name="maintenanceattachmentmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    category__in=("failurePhoto", "manual", "invoice", "other")
                ),
                name="ck_maintenance_attachment_category",
            ),
        ),
    ]
