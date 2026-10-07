"""Reorder policy fields on the spare part — the stock→purchase loop.

Both columns are additive with defaults that preserve today's behaviour:
``reorderQuantity=0`` means "not configured" (the policy falls back to
topping up to twice the minimum) and ``autoReorder=True`` opts every
existing part into the loop, which is the behaviour a warehouse expects
after asking for automatic replenishment.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("maintenance", "0020_performanceReview"),
    ]

    operations = [
        migrations.AddField(
            model_name="sparepartmodel",
            name="reorderQuantity",
            field=models.DecimalField(decimal_places=3, default=0, max_digits=14),
        ),
        migrations.AddField(
            model_name="sparepartmodel",
            name="autoReorder",
            field=models.BooleanField(default=True),
        ),
        migrations.AddConstraint(
            model_name="sparepartmodel",
            constraint=models.CheckConstraint(
                condition=models.Q(reorderQuantity__gte=0),
                name="ck_spare_part_reorder_quantity_nonnegative",
            ),
        ),
    ]
