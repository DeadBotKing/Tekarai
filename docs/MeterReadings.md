# ثبت قرائت دستی و سنسوری — Meter Readings

> Manual and sensor capture of meter values (running hours, energy, condition),
> plus the meter-driven PM scheduling it unlocks.

This document describes the slice added to `apps/maintenance`: what it does, the
rules it enforces, the API it exposes, and the three production bugs it fixes.

---

## ۱) چرا این قابلیت (Why)

The platform already had three features that **could not work** because nothing
ever fed them a measured number:

| Existing capability | What was missing |
| --- | --- |
| PM plans with `frequencyUnit = "runningHour"` | No running-hour input, and `asDays()` returned `None`, so the plan was never due. |
| `analytics.MetricReading` condition alerts | No device-bound capture path for plant meters. |
| Cost / availability reporting on `Device.runningHours` | The column was hand-typed on the nameplate form and nobody trusted it. |

This slice is the input layer. A reading now has a time, a source, a quality and
an owner — and everything downstream derives from it instead of guessing.

---

## ۲) مدل دامنه (Domain model)

```
Device ──1:N── MeterPoint ──1:N── MeterReading   (append-only)
                   │
                   └─ drivesRunningHours ──► Device.runningHours  (derived)
                                        └──► PmPlan.lastMetricValue ──► due?
```

**MeterPoint** — what is measured on one device.

| Field | Meaning |
| --- | --- |
| `code` | Uppercase identifier, unique per device (`RUNNING_HOURS`, `PUMP.KWH`). |
| `kind` | `cumulative` (a counter) or `gauge` (a spot value). Immutable after creation. |
| `sensorKey` | Gateway tag. Unique per tenant; retiring a point frees it. |
| `drivesRunningHours` | At most one per device, counters only. |
| `rolloverMaximum` | Counter capacity, so a wrap can be told apart from a typo. |
| `maximumStepPerHour` | Plausibility guard: a pump cannot gain 90 hours in one hour. |
| `minimumValue` / `maximumValue` | Hard accept/reject bounds. |

**MeterReading** — one observation. **Immutable.** No `PATCH`, no `DELETE`, at
any layer: the model, the queryset and the routes all refuse. A mistake is fixed
by appending a correction that supersedes the original.

---

## ۳) قواعد دامنه (The rules, and why)

| Rule | Reason |
| --- | --- |
| First reading of a series has `delta = null`, not `0`. | Zero would claim the machine ran for no hours before we started watching. |
| A counter that drops by ≥50 % of `rolloverMaximum` wrapped; a smaller drop is `suspect` with `delta = null`. | `8400 → 840` is a dropped digit, not a wrap of a 999999 counter. |
| Quality can only be downgraded, never upgraded by the caller. | A client cannot launder a suspect value into a good one. |
| Only `good` / `estimated` readings feed derived state. | Untrusted numbers must not move running hours or trip a PM plan. |
| A back-dated reading never overwrites the cached `lastValue`. | Entering yesterday's sheet today must not rewind the meter. |
| Timestamps more than 5 minutes in the future are rejected; naive values are read as UTC. | Clock skew is tolerated; "next week's reading" is not. |
| Every append happens inside `lockPoint()` within a transaction. | Two concurrent appends would otherwise compute the same delta twice. |
| Readings survive point deletion (FK `PROTECT`, soft delete). | Deleting history to tidy a dropdown is how plants lose their record. |

### Corrections

A correction is a **new row** that keeps the **original `capturedAt`**, requires
a non-empty reason, and marks the original superseded. An already-superseded
reading cannot be corrected again. Superseded rows stop driving later deltas.

### Decimals

Every decimal crosses the wire as a **string**, in both directions. A JSON
number is an IEEE-754 double in every browser, and an hour meter at
`124578901.2345` would silently lose its last digits. Values are stored with
4 decimal places (`VALUE_DECIMAL_PLACES`) and 18 significant digits.

---

## ۴) ثبت سنسوری (Sensor ingestion)

`POST /api/v1/maintenance/meter-readings/ingest` accepts both
`X-API-Key` (gateway) **and** a bearer session; every other meter endpoint is
session-only, so a key leaking off a PLC cabinet can push samples but can never
read the plant's history, redefine a meter, or author a human-attributed manual
reading.

* Samples resolve to a point by `sensorKey`.
* `ingestionKey` is the idempotency token: a replay returns `status="duplicate"`;
  the *same* key with a *different* value raises `MAINT_METER_INGESTION_CONFLICT`.
* Batches are ≤ 500 samples and **partially succeed** by default — a gateway
  flushing a minute of telemetry must not lose 499 good points because one
  arrived malformed. Send `atomic: true` for all-or-nothing.
* Duplicate keys *within* one batch are rejected up front.

Response is `200` with a per-item result list and `meta` counts
(`accepted` / `duplicates` / `rejected` / `received`).

---

## ۵) نگهداری مبتنی بر کنتور (Meter-driven PM)

`PmPlan` gained a trigger model:

| `triggerType` | Fires when |
| --- | --- |
| `calendar` | `nextDueOn() <= today` (unchanged behaviour). |
| `meter` | `currentValue - lastExecutedMeterValue >= metricInterval`. |
| `condition` | `currentValue` crosses `thresholdValue` using `thresholdOperator`. |

* A legacy plan with `frequencyUnit == "runningHour"` is promoted to
  `triggerType="meter"` automatically, with `metricInterval` defaulted from
  `frequencyEvery`.
* A plan attached to a pump that already has 40 000 hours is **not** born 80
  cycles overdue: the first reading after the plan is created becomes its
  baseline (`status = "noBaseline"` until then).
* `warningValue` gives a lead distance so the plan warns before it trips.
* Executing a meter plan stamps `PmExecution.meterValue` and starts the next
  cycle from that value. "On time" is judged against the **meter**, never the
  calendar — a date comparison on a meter plan always reports success.

`GET /maintenance/meter-pm-status` returns the live distance to every trigger.

---

## ۶) مجوزها (Permissions)

Four deliberately separate actions:

| Action | Who |
| --- | --- |
| `maintenance.meter.view` | Everyone who can see equipment. |
| `maintenance.meter.record` | Technicians — type a reading, append a correction. |
| `maintenance.meter.manage` | Managers — define meters and sensor bindings. |
| `maintenance.meter.ingest` | Gateway credentials — push sensor batches only. |

---

## ۷) API

All paths are under `/api/v1/maintenance/`.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` `POST` | `devices/<deviceId>/meter-points` | List / define meters of a device |
| `PATCH` `DELETE` | `meter-points/<meterPointId>` | Edit / retire a meter |
| `GET` | `meter-points` | Tenant-wide meter search |
| `GET` | `meter-points/<meterPointId>/readings` | History of one meter |
| `GET` | `meter-points/<meterPointId>/summary` | Counts, range, total consumption |
| `GET` `POST` | `devices/<deviceId>/meter-readings` | History / manual capture |
| `GET` | `meter-readings` | Cross-device reading feed (filters + paging) |
| `POST` | `meter-readings/ingest` | Gateway batch |
| `POST` | `meter-readings/<readingId>/correct` | Append a correction |
| `GET` | `meter-pm-status` | Meter/condition PM plans and their distance to due |

Events emitted: `meterPointDefined`, `meterReadingRecorded`,
`meterReadingFlagged` (quality ≠ good; carries `eventId`/`sourceId` for alert
dedupe), `meterReadingCorrected`.

---

## ۸) سه باگی که رفع شد (Three bugs fixed)

1. **Meter-based PM never fired.** `FREQUENCY_DAYS` had no `runningHour` entry,
   so `asDays()` returned `None` and `isOverdue()` answered `False` forever.
   Every "every 500 running hours" plan in the database was inert.

2. **Migration `0012_pm_metric_triggers` was an orphan — a live outage.** It
   added nine `NOT NULL` columns to `PmPlan` with no model counterpart, so
   `makemigrations --check` failed on a clean checkout and **every PM-plan
   create returned HTTP 500** (`NOT NULL constraint failed: PmPlan.triggerType`).
   That single defect accounted for 13 of the 17 failing tests on `main`. The
   columns are now mirrored in the model, carried through repository, use case,
   DTO, serializer and view, and brought to life by this feature.

3. **`Device.runningHours` was untrustworthy.** It was a free-text nameplate
   field. It is now *derived* from the newest trusted reading of the meter point
   flagged `drivesRunningHours`; the nameplate form silently ignores the field
   once such a meter exists, and `readNameplate` reports `runningHoursDerived`
   so the UI can render it read-only.

---

## ۹) آزمون‌ها (Tests)

| Suite | Count | Scope |
| --- | --- | --- |
| `backend/tests/unit/testMeterReading.py` | 44 | Domain rules without a database: deltas, rollover, step guard, bounds, quality, triggers. |
| `backend/tests/integration/testMeterReadingApi.py` | 47 | REST contract end to end: capture, ingest, idempotency, corrections, immutability, tenant isolation, derived running hours, meter-driven PM becoming due. |
| `frontend-web/src/tests/meterReadings.test.tsx` | 6 | Wire mapping (precision, null vs zero) and the page render. |

Run them with:

```bash
cd backend && .venv/bin/python manage.py test tests --settings=config.settings.testing
cd frontend-web && npm run typecheck && npm run test -- --run && npm run build
```

> `manage.py test --parallel` is broken in this repository (`cannot pickle
> 'traceback' object`); run the suite serially.

---

## ۱۰) رابط کاربری (UI)

`/app/maintenance/meter-readings` (`src/pages/MeterReadingsPage.tsx`) — choose a
device, define its meters, type a reading, see the history with its quality and
consumption, correct a mistake with a reason, and watch the meter-driven PM
strip move from «طبق برنامه» to «نزدیک سررسید» to «سررسید رسیده».
