"""رزرو قطعات و چک‌لیست‌های بازرسی تیمی (هم‌گام‌سازی موج ۲)."""

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0009_time_cost_tracking"),
    ]

    operations = [
        migrations.CreateModel(
            name="PartReservationModel",
            fields=[
                ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("tenantId", models.UUIDField(db_index=True)),
                ("workOrderId", models.UUIDField(db_index=True)),
                ("partCode", models.CharField(db_index=True, max_length=60)),
                ("quantity", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("status", models.CharField(db_index=True, default="active", max_length=16)),
                ("reservedByName", models.CharField(blank=True, default="", max_length=160)),
                ("createdAt", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updatedAt", models.DateTimeField(blank=True, null=True)),
                ("closedAt", models.DateTimeField(blank=True, null=True)),
                ("deletedAt", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "PartReservation", "ordering": ["-createdAt"]},
        ),
        migrations.CreateModel(
            name="InspectionTemplateModel",
            fields=[
                ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("tenantId", models.UUIDField(db_index=True)),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                ("deviceCode", models.CharField(blank=True, default="", max_length=60)),
                ("checks", models.JSONField(default=list)),
                ("isCommitted", models.BooleanField(default=False)),
                ("createdAt", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updatedAt", models.DateTimeField(blank=True, null=True)),
                ("deletedAt", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "InspectionTemplate", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="InspectionRecordModel",
            fields=[
                ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("tenantId", models.UUIDField(db_index=True)),
                ("templateId", models.CharField(db_index=True, max_length=64)),
                ("workOrderId", models.UUIDField(blank=True, db_index=True, null=True)),
                ("deviceId", models.UUIDField(db_index=True)),
                ("passedChecks", models.JSONField(default=list)),
                ("failedChecks", models.JSONField(default=list)),
                ("performedByName", models.CharField(blank=True, default="", max_length=160)),
                ("createdAt", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "InspectionRecord", "ordering": ["-createdAt"]},
        ),
    ]
