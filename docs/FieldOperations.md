# کار میدانی تکنسین — Field Operations

> اسکن کد، تایمر کار، کار بدون اینترنت و همگام‌سازی تأخیری
> (code scanning, work timers, offline operation, deferred sync)

This document covers the four technician capabilities added to
`apps/maintenance` and `frontend-web`: why each exists, the rules it enforces,
the API it exposes, and how to verify it.

---

## ۱) چرا این قابلیت‌ها (Why)

The audit of the technician mobile flow found four gaps. Three capabilities
already worked (work orders, device status, parts consumption); these four did
not:

| # | Gap | Symptom in the field |
| --- | --- | --- |
| ۲ | QR scanning was device-only and used `BarcodeDetector` | Nothing scanned on iOS Safari or Firefox; printed asset tags with Code 39/128 barcodes were unreadable; the work-order sheet in the technician's hand had no code at all. |
| ۶ | Labour was `hours` + `workedAt` only | The number was typed from memory at the end of a shift. «۲ ساعت» meant "about two". |
| ۷ | No offline operation | In a basement or a pump house the app showed a blank screen. |
| ۸ | No deferred sync | Work done without a signal was simply lost, or re-typed later from a paper note. |

---

## ۲) اسکن کد (Code scanning)

### Decoder

```
BarcodeDetector supports every format we print?  ──yes──► native decoder (battery-cheap)
                              └──no / absent─────────────► ZXing, bundled with the app
```

`chooseEngine()` (pure, unit-tested) makes that call. The native path is kept
because a JavaScript decode loop is expensive on a phone that must last a
shift; the ZXing path is what makes the feature *exist* on Firefox and older
iOS. A partially-capable native decoder is treated as absent — a scanner that
reads QR but not ITF is a trap, not an optimisation.

ZXing is loaded through a dynamic `import()` (≈416 kB chunk, out of the first
paint) and pre-warmed on idle by `prefetchDecoder()`, so the first scan in a
signal-free basement does not need the network.

**Symbologies read:** `qr_code`, `data_matrix`, `code_128`, `code_39`,
`ean_13`, `ean_8`, `upc_a`, `upc_e`, `itf`.

### What a code may contain

`parseScan()` on the client and `scanCodeRules.py` on the server implement the
same four shapes:

| Shape | Example | Result |
| --- | --- | --- |
| Deep link | `https://…/app/maintenance/work-orders/<uuid>` | kind + id |
| Legacy scheme | `tekarai://device/<uuid>` | kind + id |
| Bare UUID | `3F2504E0-4F89-…` (braces and dashes optional) | id only — server probes every register |
| Business code | `PUMP-204`, `LINE1/PMP.204` | upper-cased code, server resolves |

Anything else — Persian prose, another system's URL, an empty frame, >512
characters — produces an **empty intent**. The UI says «کد ناشناس» rather than
navigating somewhere plausible-looking.

Resolution order on the server is `device → workOrder → sparePart → location`,
and a device's `code` beats its `serialNumber`.

### Offline scanning

A QR deep link carries its target inside the code, so it resolves **with no
server**. A business code cannot — the modal says so explicitly instead of
spinning.

### Labels

`QrLabelModal` prints a label for any kind. Work orders now have one
(`qr.workOrder` on the detail panel), which is what makes "scan the sheet in
your hand" possible. Error correction `M`, large modules: these labels end up
oily and photographed at an angle.

---

## ۳) تایمر کار (Work timer)

### Model

`WorkTimerModel` (`db_table="WorkTimer"`):

| Constraint | Why |
| --- | --- |
| `uq_work_timer_one_running_per_tech` — unique `(tenantId, technicianName, workOrderId)` filtered on `endedAt IS NULL` | One running timer per technician per order. Filtered, because SQL Server treats NULLs as **equal** in a plain unique index and would allow only one finished timer ever. |
| `ck_work_timer_end_after_start` | A negative span is a clock bug, not work. |
| `ck_work_timer_paused_nonnegative` | Paused time cannot be invented. |

### Rules

| Rule | Reason |
| --- | --- |
| Hours are quantised to hundredths, `ROUND_HALF_UP`. | 36 s → `0.01`. |
| A span always bills at least `MINIMUM_BILLABLE_HOURS` (0.01). | The labour table has a `hours > 0` check; a 5-second timer must still produce a row rather than a 500. |
| A span over `MAX_SPAN_HOURS` (24, inclusive) is refused. | It is a timer somebody forgot to stop, and it would corrupt the cost report. |
| `pausedSeconds` subtracts and clamps at zero. | Tea break, waiting for a crane. |
| Small forward clock skew (≤2 min) is tolerated; an hour is not. | Phone clocks drift; phone clocks are not an hour wrong. |
| A timer cannot start on a `submitted`/`routed` order. | There is no lifecycle edge to `inProgress` from there — the error says «assign this order first». |
| Stopping when nothing runs raises `MAINT_TIMER_NOT_RUNNING` (409), not 404. | «Already stopped» is the replay case; the sync engine reads it as `duplicate` and drops the item instead of retrying forever. |

Stopping writes the labour entry **through the existing
`LogLabourEntryUseCase`**, so cost, reporting and permissions behave exactly as
they do for a hand-typed entry. `elapsedSeconds` in the UI is computed from
`startedAt`, never accumulated by an interval — an interval drifts and stops
dead when the phone sleeps in a pocket, which is precisely when a timer runs.

---

## ۴) کار بدون اینترنت (Offline / PWA)

| Piece | File |
| --- | --- |
| Manifest (fa, RTL, maskable icons, shortcuts) | `frontend-web/public/manifest.webmanifest` |
| Service worker | `frontend-web/public/serviceWorker.js` |
| Offline fallback page | `frontend-web/public/offline.html` |
| Registration (production only) | `src/core/offline/registerServiceWorker.ts` |

Strategies:

| Request | Strategy |
| --- | --- |
| navigation | network-first → cached shell → `offline.html` |
| `/assets/*` (content-hashed) | cache-first |
| icons, fonts, manifest | stale-while-revalidate |
| allow-listed maintenance `GET` | network-first → cached copy |
| every mutation | **not handled** — see below |

Two deliberate decisions:

* **The worker never queues mutations.** Background Sync does not exist on iOS
  and gives no per-item verdict. Our queue lives in IndexedDB and replays
  through `/maintenance/sync`, which answers applied/duplicate/rejected/failed
  per operation. Two queues would fight over the same work.
* **API responses live in a separate cache** that is dropped on logout
  (`clearCachedApiResponses()`), so a shared phone cannot show the next user
  the previous user's work orders.

The work-orders page additionally keeps its three lists (orders, devices,
parts) in IndexedDB and serves them when a load fails for connectivity
reasons — with a visible «نسخه‌ی آفلاین از …» note. A stale list that looks
live is worse than no list.

**Not registered in dev.** A service worker caching a Vite dev bundle makes
code changes invisible.

---

## ۵) همگام‌سازی تأخیری (Deferred sync)

### Client

```
tap ──► OfflineQueue.enqueue()  ──► IndexedDB  (clientRequestId minted here, once)
                                        │
            online / reconnect / 30 s ──┴──► SyncEngine.flush() ──► POST /maintenance/sync
```

Invariants:

1. The operation is written to storage **before** the UI claims success.
2. Replay is FIFO by capture time — a `workTimer.stop` must not precede its
   `workTimer.start`.
3. `clientRequestId` is minted at capture and **never regenerated**. Re-minting
   on retry is how an idempotent replay becomes a double entry.
4. Rejected items are kept and shown, never silently dropped.

Verdict handling:

| Verdict | Queue action |
| --- | --- |
| `applied` | delete |
| `duplicate` | delete (the first attempt landed) |
| `rejected` | park as rejected, show the server's reason, offer retry/discard |
| `failed` | keep as pending, retry later |
| *missing from the response* | keep as pending — never assume success |

A flush is single-flight: concurrent callers share one batch. Batches are
capped at 50 client-side (the server refuses >200).

### Server

`POST /maintenance/sync` is **always 200 on a well-formed batch** — the
per-item verdicts are the payload. An HTTP error would make the queue retry
items that can never succeed.

| Kind | Underlying use case |
| --- | --- |
| `workOrder.status` | `ChangeWorkOrderStatusUseCase` |
| `workOrder.labour` | `LogLabourEntryUseCase` |
| `workOrder.partUsage` | `ConsumeSparePartUseCase` |
| `workTimer.start` / `workTimer.stop` | timer use cases (`capturedOffline=True`) |
| `device.status` | `ChangeDeviceStatusUseCase` |
| `meter.reading` | `RecordManualReadingUseCase` |

**Authorisation is not bypassed.** `ApplySyncBatchUseCase.requiredAction` is
intentionally empty; each inner use case runs its own check, so a requester-
level session cannot launder a device-status change through the sync endpoint.
There is an integration test for exactly that.

Deduplication is a unique index on `(tenantId, clientRequestId)` in
`OfflineSyncOperationModel`, **not** the cache-backed idempotency store: that
one is LocMem/Redis with a 24-hour TTL and is lost on restart, which is useless
for a phone that was offline over a weekend. A previously `failed` ledger entry
is forgotten and re-executed; `applied` and `rejected` are replayed from the
ledger. A duplicate `clientRequestId` *within one batch* rejects the whole
batch (400) — the client is confused and guessing would be worse.

---

## ۶) API

All paths are under `/api/v1/maintenance`.

| Method | Path | Notes |
| --- | --- | --- |
| `POST` | `work-orders/<uuid>/timer/start` | 201; `technicianName`, `startedAt`, `note`, `startedVia`, `hourlyRate` |
| `POST` | `work-orders/<uuid>/timer/stop` | 200; returns timer + `labourEntryId`, `hours`, `labourCost` |
| `GET` | `work-orders/<uuid>/timers?runningOnly=` | session history for one order |
| `GET` | `work-timers/active?technicianName=` | what is running right now |
| `DELETE` | `work-timers/<uuid>` | discard a running timer without billing it |
| `GET` | `scan?code=&symbology=` | resolve any code to a target |
| `POST` | `sync` | replay a batch; always 200 when well-formed |
| `GET` | `sync/history?limit=` | the server-side ledger |

Error codes: `MAINT_TIMER_ALREADY_RUNNING` (409), `MAINT_TIMER_NOT_RUNNING`
(409), `MAINT_TIMER_SPAN_INVALID` (422), `MAINT_SCAN_CODE_UNREADABLE` (422),
`MAINT_SCAN_TARGET_NOT_FOUND` (404), `MAINT_SYNC_KIND_UNSUPPORTED` (422),
`MAINT_SYNC_BATCH_TOO_LARGE` (400).

Permissions: timers need `maintenance.workorder.logTime`, reads
`maintenance.workorder.view`, scanning `maintenance.device.view`. **No new
permission was introduced** — the technician role already holds all three, so
nothing has to be re-bootstrapped.

Decimals (`billableHours`, `hourlyRate`, `hours`, `labourCost`) cross the wire
as **strings** and are parsed once, at the client boundary.

---

## ۷) جایی که در رابط کاربری دیده می‌شود (Where it shows up)

| Surface | Path |
| --- | --- |
| Scan button + work-order QR label + timer panel | **نگهداری ← عملیات ← سفارش‌های کار** (`/app/maintenance/work-orders`) |
| Equipment scanner (now multi-format) | **نگهداری ← دارایی‌ها ← تجهیزات** |
| Offline queue page | **نگهداری ← عملیات ← صف آفلاین** (`/app/maintenance/offline-queue`) |
| Connectivity / pending badge | app header, visible only when offline or when items are waiting |

The header badge stays hidden while everything is normal: a permanent green dot
teaches people to ignore the indicator, and then they ignore the red one too.

---

## ۸) تست‌ها (Tests)

| Suite | Count |
| --- | --- |
| `backend/tests/unit/testFieldOperations.py` | 42 |
| `backend/tests/integration/testFieldOpsApi.py` | 48 |
| `frontend-web/src/tests/fieldOpsOffline.test.ts` | 24 |
| `frontend-web/src/tests/fieldOpsUi.test.tsx` | 5 |

Full backend suite: **2647 tests, 5 failures — all pre-existing
`tests.architecture.*` naming/dependency violations on `main`, unrelated to
this work.** Frontend: 139 tests, typecheck and production build green.

### اجرا در ویندوز

```powershell
cd C:\Users\Mitra\Desktop\Tekarai
.\verify_fieldOps.cmd              # تست‌های بک‌اند همین قابلیت (۹۰ تست)
.\verify_fieldOps.cmd -Frontend    # typecheck + تست + build + دارایی‌های PWA
.\verify_fieldOps.cmd -Full        # کل مجموعه بک‌اند
.\verify_fieldOps.cmd -Smoke       # تست زنده روی سرور بالا
.\verify_fieldOps.cmd -All
```

Running the app: `.\run_dev.cmd -UseSqlite` → `http://localhost:4173`, sign in
as `platform-admin` / `Tekarai-Demo-2026!`.

### امتحان‌کردن حالت آفلاین

1. `npm run build && npm run preview` in `frontend-web` (the service worker is
   production-only).
2. Open the app, sign in, let the work-order list load once.
3. DevTools → Network → **Offline**.
4. Start a timer, change a work-order status, stop the timer. Each action is
   confirmed as queued; the header badge shows the count.
5. Go back online. The queue drains automatically; «صف آفلاین» shows the
   per-item verdicts and the server-side history.

---

## ۹) مهاجرت (Migration)

`apps/maintenance/infrastructure/migrations/0015_fieldOperations.py` creates
`WorkTimer` and `OfflineSyncOperation`. No data migration, no backfill, no
change to existing tables. `makemigrations --check` is clean.
