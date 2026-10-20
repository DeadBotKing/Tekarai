"""Add human repair-scope, part-impact snapshots and performance-role metadata."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0023_personnel_user_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="workordermodel",
            name="repairScope",
            field=models.CharField(db_index=True, default="unclassified", max_length=20),
        ),
        migrations.AddConstraint(
            model_name="workordermodel",
            constraint=models.CheckConstraint(
                condition=models.Q(repairScope__in=("unclassified", "minor", "major", "overhaul")),
                name="ck_work_order_repair_scope",
            ),
        ),
        migrations.AddField(
            model_name="sparepartmodel",
            name="lifecycleImpact",
            field=models.CharField(default="unknown", max_length=12),
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(lifecycleImpact__in=("unknown", "minor", "major")),
                name="ck_spare_part_lifecycle_impact",
            ),
        ),
        migrations.AddField(
            model_name="workorderpartusagemodel",
            name="lifecycleImpact",
            field=models.CharField(default="unknown", max_length=12),
        ),
        migrations.AddConstraint(
            model_name="workorderpartusagemodel",
            constraint=models.CheckConstraint(
                condition=models.Q(lifecycleImpact__in=("unknown", "minor", "major")),
                name="ck_work_order_part_usage_impact",
            ),
        ),
        migrations.AddField(
            model_name="meterpointmodel",
            name="performanceRole",
            field=models.CharField(default="none", max_length=20),
        ),
        migrations.AddConstraint(
            model_name="meterpointmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(performanceRole__in=("none", "higherIsBetter", "lowerIsBetter")),
                name="ck_meter_point_performance_role",
            ),
        ),
        migrations.AddConstraint(
            model_name="meterpointmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(performanceRole="none") | models.Q(kind="gauge"),
                name="ck_meter_point_performance_gauge",
            ),
        ),
    ]
