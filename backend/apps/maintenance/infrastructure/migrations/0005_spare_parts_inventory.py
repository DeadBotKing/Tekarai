from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0004_devicehistorymodel")]

    operations = [
        migrations.CreateModel(
            name="SparePartModel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenantId", models.UUIDField(db_index=True)),
                ("code", models.CharField(max_length=60)),
                ("name", models.CharField(max_length=200)),
                ("unit", models.CharField(default="عدد", max_length=30)),
                ("quantityOnHand", models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ("minimumStock", models.DecimalField(decimal_places=3, default=0, max_digits=14)),
                ("createdAt", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updatedAt", models.DateTimeField(blank=True, null=True)),
                ("deletedAt", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "SparePart", "ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="WorkOrderPartUsageModel",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("tenantId", models.UUIDField(db_index=True)),
                ("workOrderId", models.UUIDField(db_index=True)),
                ("partId", models.UUIDField(db_index=True)),
                ("partCode", models.CharField(max_length=60)),
                ("partName", models.CharField(max_length=200)),
                ("unit", models.CharField(max_length=30)),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=14)),
                ("note", models.CharField(blank=True, default="", max_length=500)),
                ("consumedAt", models.DateTimeField(db_index=True)),
            ],
            options={"db_table": "WorkOrderPartUsage", "ordering": ["-consumedAt"]},
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.UniqueConstraint(
                condition=models.Q(deletedAt__isnull=True),
                fields=("tenantId", "code"),
                name="uq_spare_part_tenant_code",
            ),
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(quantityOnHand__gte=0),
                name="ck_spare_part_stock_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(minimumStock__gte=0),
                name="ck_spare_part_minimum_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="workorderpartusagemodel",
            constraint=models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="ck_work_order_part_usage_positive",
            ),
        ),
    ]
