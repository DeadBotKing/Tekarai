"""Activate PM plans that were saved as "every N running hours".

Before meter readings existed, a plan with ``frequencyUnit='runningHour'``
could be created through the UI but could never become due: its period had no
calendar equivalent, ``nextDueOn()`` returned ``None``, and ``isOverdue()``
answered ``False`` forever. Those rows are real maintenance intent that the
system silently dropped.

This migration converts each of them into a proper meter trigger:

* ``triggerType``    → ``meter``
* ``metricInterval`` → the ``frequencyEvery`` the planner originally typed
* ``metricType``     → the conventional running-hours meter code, so the plan
  binds to the device's hour meter as soon as one is defined

The plans do not fire until a meter point with that code receives readings,
which is the correct behaviour: a trigger with no measurement is not due, it
is unknown.

Reversible: the trigger columns are reset to their calendar defaults, which
restores the previous (inert) state exactly.
"""

from __future__ import annotations

from django.db import migrations

#: Conventional code for the hour meter created by ``ensureRunningHoursPoint``.
RUNNING_HOURS_CODE = "RUNNING_HOURS"


def forwards(apps, schemaEditor) -> None:  # noqa: ANN001 — migration contract
    PmPlanModel = apps.get_model("maintenance", "PmPlanModel")
    legacy = PmPlanModel.objects.filter(frequencyUnit="runningHour", triggerType="calendar")
    for plan in legacy.iterator():
        plan.triggerType = "meter"
        plan.metricType = plan.metricType or RUNNING_HOURS_CODE
        # ``frequencyEvery`` is a positive integer by database constraint, so
        # the resulting interval always satisfies ck_pm_plan_meter_interval.
        plan.metricInterval = plan.metricInterval or plan.frequencyEvery
        plan.metricUnit = plan.metricUnit or "ساعت"
        plan.save(update_fields=["triggerType", "metricType", "metricInterval", "metricUnit"])


def backwards(apps, schemaEditor) -> None:  # noqa: ANN001 — migration contract
    PmPlanModel = apps.get_model("maintenance", "PmPlanModel")
    reverted = PmPlanModel.objects.filter(
        frequencyUnit="runningHour", triggerType="meter", metricType=RUNNING_HOURS_CODE
    )
    for plan in reverted.iterator():
        plan.triggerType = "calendar"
        plan.metricType = ""
        plan.metricInterval = 0
        plan.save(update_fields=["triggerType", "metricType", "metricInterval"])


class Migration(migrations.Migration):
    dependencies = [("maintenance", "0013_meterReadings")]

    operations = [migrations.RunPython(forwards, backwards)]
