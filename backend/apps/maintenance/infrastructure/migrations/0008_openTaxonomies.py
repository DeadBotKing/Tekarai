"""Phase 26.1 — widen taxonomy columns for operator-defined labels.

The registry dropdowns now let an operator add a value at run time (a location
kind the plant calls «سوله», a criticality grade «خیلی بحرانی»). The canonical
ASCII codes fit easily, but a Persian label needs more room than the original
10–20 characters, so every open vocabulary column moves to 24 characters —
the limit the API enforces as well.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0007_assetRegistry"),
    ]

    operations = [
        # The closed-set CHECK constraints become "a value was given" checks:
        # the catalogue moves to the UI, the database keeps the NOT-EMPTY
        # guarantee.
        migrations.RemoveConstraint(
            model_name="maintenancelocationmodel",
            name="ck_maintenance_location_kind",
        ),
        migrations.RemoveConstraint(
            model_name="deviceassignmentmodel",
            name="ck_device_assignment_role",
        ),
        migrations.AlterField(
            model_name="devicemodel",
            name="criticality",
            field=models.CharField(db_index=True, default="medium", max_length=24),
        ),
        migrations.AlterField(
            model_name="maintenancelocationmodel",
            name="kind",
            field=models.CharField(default="site", max_length=24),
        ),
        migrations.AlterField(
            model_name="deviceassignmentmodel",
            name="role",
            field=models.CharField(default="technician", max_length=24),
        ),
        migrations.AddConstraint(
            model_name="maintenancelocationmodel",
            constraint=models.CheckConstraint(
                condition=~models.Q(kind=""), name="ck_maintenance_location_kind"
            ),
        ),
        migrations.AddConstraint(
            model_name="deviceassignmentmodel",
            constraint=models.CheckConstraint(
                condition=~models.Q(role=""), name="ck_device_assignment_role"
            ),
        ),
    ]
