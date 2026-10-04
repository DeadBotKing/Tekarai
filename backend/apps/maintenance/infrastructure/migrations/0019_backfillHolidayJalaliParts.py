"""Backfill `jalaliMonth`/`jalaliDay` on holidays that were saved without them.

Until Phase 28.1 the web form posted zeros for both columns and the server
stored them as sent, so every holiday created through the UI was pinned to no
Jalali date at all. `recursAnnually` could be ticked, but the projection had
nothing to project on and the holiday silently stayed a one-off.

The parts are recoverable — they are a pure function of `onDate` — so existing
rows are repaired rather than left half-written. Rows that already carry a
month and day are untouched.
"""

from __future__ import annotations

from django.db import migrations


def backfillJalaliParts(apps, schema_editor):
    from apps.maintenance.domain.services.jalaliCalendar import dateToJalali

    Holiday = apps.get_model("maintenance", "CalendarHolidayModel")
    pending = Holiday.objects.filter(jalaliMonth=0).exclude(onDate=None)
    repaired = []
    for row in pending.iterator():
        _, month, day = dateToJalali(row.onDate)
        row.jalaliMonth = month
        row.jalaliDay = day
        repaired.append(row)
    if repaired:
        Holiday.objects.bulk_update(repaired, ["jalaliMonth", "jalaliDay"], batch_size=500)


def unbackfill(apps, schema_editor):
    """Deliberately a no-op.

    Zeroing the columns again would destroy correct data to restore a bug;
    leaving them populated is harmless to the previous code, which simply
    ignored them.
    """


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0018_workCalendar")]

    operations = [migrations.RunPython(backfillJalaliParts, unbackfill)]
