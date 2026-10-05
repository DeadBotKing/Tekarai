from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0011_parttransactionmodel")]
    operations = [
        migrations.AddField(
            "PmPlanModel",
            "triggerType",
            models.CharField(default="calendar", db_index=True, max_length=20),
        ),
        migrations.AddField(
            "PmPlanModel", "metricType", models.CharField(blank=True, default="", max_length=40)
        ),
        migrations.AddField(
            "PmPlanModel",
            "metricInterval",
            models.DecimalField(decimal_places=3, default=0, max_digits=14),
        ),
        migrations.AddField(
            "PmPlanModel", "thresholdOperator", models.CharField(default=">=", max_length=4)
        ),
        migrations.AddField(
            "PmPlanModel",
            "thresholdValue",
            models.DecimalField(decimal_places=3, default=0, max_digits=18),
        ),
        migrations.AddField(
            "PmPlanModel",
            "warningValue",
            models.DecimalField(decimal_places=3, default=0, max_digits=18),
        ),
        migrations.AddField(
            "PmPlanModel", "metricUnit", models.CharField(blank=True, default="", max_length=30)
        ),
        migrations.AddField(
            "PmPlanModel", "sensorKey", models.CharField(blank=True, default="", max_length=120)
        ),
        migrations.AddField(
            "PmPlanModel",
            "lastMetricValue",
            models.DecimalField(blank=True, null=True, decimal_places=3, max_digits=18),
        ),
    ]
