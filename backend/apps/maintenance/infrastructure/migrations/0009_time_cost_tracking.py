from __future__ import annotations

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """Time & cost tracking — technician labour entries + part prices.

    - ``WorkOrderLabourEntryModel``: per-technician hours with the hourly rate
      captured at logging time.
    - ``SparePartModel.unitCost``: current price per unit.
    - ``WorkOrderPartUsageModel.unitCost``: price snapshot per consumption so
      historical maintenance costs survive later price changes.
    """

    dependencies = [("maintenance", "0008_openTaxonomies")]

    operations = [
        migrations.AddField(
            model_name="sparepartmodel",
            name="unitCost",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=16),
        ),
        migrations.AddField(
            model_name="workorderpartusagemodel",
            name="unitCost",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=16),
        ),
        migrations.CreateModel(
            name="WorkOrderLabourEntryModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("workOrderId", models.UUIDField(db_index=True)),
                ("technicianName", models.CharField(max_length=160)),
                ("hours", models.DecimalField(decimal_places=2, max_digits=10)),
                ("hourlyRate", models.DecimalField(decimal_places=2, default=0, max_digits=16)),
                ("workedAt", models.DateTimeField(db_index=True)),
                ("note", models.CharField(blank=True, default="", max_length=500)),
                ("createdAt", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={"db_table": "WorkOrderLabourEntry", "ordering": ["-workedAt"]},
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(unitCost__gte=0),
                name="ck_spare_part_unit_cost_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="workorderlabourentrymodel",
            constraint=models.CheckConstraint(
                condition=models.Q(hours__gt=0),
                name="ck_labour_entry_hours_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="workorderlabourentrymodel",
            constraint=models.CheckConstraint(
                condition=models.Q(hourlyRate__gte=0),
                name="ck_labour_entry_rate_nonnegative",
            ),
        ),
    ]
