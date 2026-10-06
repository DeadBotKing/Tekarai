"""Requisition ageing clock + the terminal ``purchased`` status.

The two new timestamps are nullable, so the schema change is safe on a live
table. The backfill matters though: without it every requisition that already
exists has ``submittedAt = NULL``, the staleness scan treats "never submitted"
as "not the buyer's problem", and the first run after deploying this would
report zero stale requests on a backlog that is in fact months old.

``createdAt`` is the honest stand-in for rows that predate the column — it is
the only submission-ish timestamp those rows ever recorded, and for anything
that reached ``submitted`` or beyond the two are usually minutes apart.
"""

from django.db import migrations, models


def backfillSubmittedAt(apps, schema_editor):
    """Start the clock for requisitions already in the buyer's queue."""
    Requisition = apps.get_model("procurement", "PurchaseRequisitionModel")
    Requisition.objects.filter(
        status__in=["submitted", "approved", "ordered"],
        submittedAt__isnull=True,
    ).update(submittedAt=models.F("createdAt"))


def unbackfill(apps, schema_editor):
    """Reverse leg — drop the values the forward backfill invented."""
    Requisition = apps.get_model("procurement", "PurchaseRequisitionModel")
    Requisition.objects.filter(status__in=["submitted", "approved", "ordered"]).update(
        submittedAt=None
    )


class Migration(migrations.Migration):
    dependencies = [
        ("procurement", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchaserequisitionmodel",
            name="purchasedAt",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="purchaserequisitionmodel",
            name="submittedAt",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="purchaserequisitionmodel",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "draft"),
                    ("submitted", "submitted"),
                    ("approved", "approved"),
                    ("rejected", "rejected"),
                    ("cancelled", "cancelled"),
                    ("ordered", "ordered"),
                    ("purchased", "purchased"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
        migrations.RunPython(backfillSubmittedAt, unbackfill),
    ]
