"""Link a workforce person to the platform account they sign in with."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0022_workordermodel_assignedtouserid_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="maintenancepersonnelmodel",
            name="linkedUserId",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="maintenancepersonnelmodel",
            constraint=models.UniqueConstraint(
                condition=models.Q(deletedAt__isnull=True, linkedUserId__isnull=False),
                fields=["tenantId", "linkedUserId"],
                name="uq_maintenance_personnel_linked_user",
            ),
        ),
    ]
