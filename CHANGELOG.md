# Changelog

This file did not exist before. The repository had a single `main` branch, no
tags and commit messages such as `calender`, `color`, `tem` and `update`, which
made it impossible to tell what any given commit changed or to roll back to a
known-good state. Entries follow [Keep a Changelog](https://keepachangelog.com)
and the project aims at [Semantic Versioning](https://semver.org).

## [0.2.1]

### Fixed — alarms that were connected to nobody

- **Every scheduled alert was being delivered to zero people.** The notification
  routes for overdue work orders, low stock, PM due/overdue and stalled purchase
  requests all target the `maintenanceManager` role. `bootstrapPlatform` created
  that role but granted it to no one, so `resolveRecipients` returned an empty
  list, the engine created no rows and reported success. The scans printed
  confident summaries — `{'overdueWorkOrders': 1, 'lowStockParts': 1}` — while
  nothing reached a single inbox. Fixed on three levels:
  - `bootstrapPlatform` now grants `maintenanceManager` to the platform
    administrator, and `seedWorkspace` grants it to the demo tenant's admin, so
    a fresh install has a real holder. The command is idempotent, so existing
    installs are repaired by re-running it.
  - `CreateNotificationCommand` gained `fallbackRecipientSpec`. When the primary
    audience resolves empty, the engine re-resolves against the fallback and
    logs a warning. Six operational routes fall back to `TENANT_ADMIN`; routes
    that are meaningless without their specific audience (chat, meeting
    invites) deliberately declare no fallback.
  - A notification that still ends up with no recipients now logs
    `Notification created for zero recipients` instead of passing silently.
  - Verified against the development database: a maintenance + procurement scan
    that previously produced nothing now produces four notifications addressed
    to real users.
- **The frontend unit suite was not hermetic.** Six specs (`registry pages`,
  `chat page`, `locations page dropdown`) read the developer's `.env`, and with
  `VITE_DEMO_MODE=false` they issued real HTTP requests, so `npm test` passed or
  failed depending on whether a backend happened to be running. `vitest.config.ts`
  now pins the suite's environment, and `src/tests/setup.ts` installs a `fetch`
  guard that rejects any unmocked request naming the URL, instead of letting it
  surface as an opaque `SYS_NETWORK_ERROR`.
- **The live-API rendering path had no test coverage at all** — every page spec
  ran in demo mode, so a wrong endpoint or a changed response shape could only
  be caught in a browser. `src/tests/liveApiPages.test.tsx` renders the registry
  and locations pages with `demoMode` off against stubbed API-shaped responses,
  asserting that fetched data (not demo fixtures) reaches the screen and that
  the auth header is sent.

### Tests

- `tests/integration/testAlertsReachSomebody.py` — pins that somebody holds the
  role alerts are routed to, that a low-stock scan actually creates a
  notification record, that the fallback fires only when the primary audience is
  empty, and that no operational route can be added without a fallback.
- Backend 2983 tests pass; frontend 254 tests pass both with and without
  `VITE_DEMO_MODE=false`.

### Known issues

- The `de` catalogue holds 134 of 1542 keys and falls back to English for the
  rest.
- `ReportsPage` and `SettingsPage` are not wired to live data.

## [0.2.0]

### Added — purchase request follow-up

- **Stale purchase-request alerts.** A request that has been waiting past the
  limit for its priority (critical 2 days, high 4, normal 7, low 14, counted
  from submission) now raises a `purchaseRequisitionStale` notification to the
  requester and the buyers. Run `manage.py checkProcurementAlerts` daily; the
  event id is scoped to the ISO week, so a daily cron raises each late request
  once a week instead of every morning.
- **A terminal `purchased` status.** Fully receiving the purchase order that
  fulfils a request moves the request to `purchased` and stamps `purchasedAt`.
  The procurement screen gained a «خریدشده» tab backed by
  `GET /procurement/requisitions?status=purchased`.
- Requisition responses now carry `isStale`, `daysWaiting`,
  `staleThresholdDays` and `daysOverdue`; the list accepts `?status=` and
  `?stale=true`; the dashboard reports `staleRequisitions` and
  `purchasedRequisitions`.
- `PROCUREMENT` notification category and the §30 route for the new event.

### Fixed

- **The requisition lifecycle had no end.** Raising a purchase order moved a
  request to `ordered` and nothing ever moved it on, so a request whose goods
  had arrived months ago was indistinguishable from one still at the supplier.
- **`requesterId` was never written.** The column existed on every requisition
  and nothing ever filled it, so every purchase request was anonymous — which
  is why the new alert initially had nobody to notify. It is now stamped from
  the authenticated actor.
- **The alert scanners visited each tenant once per document.** Both
  `checkMaintenanceAlerts` and the new procurement scan used
  `.values_list("tenantId").distinct()` on a model whose `Meta.ordering` is
  `["-createdAt"]`; Django appends ordering columns to a `DISTINCT` SELECT, so
  the query de-duplicated on `(tenantId, createdAt)` and returned one row per
  work order. A tenant with 500 work orders was scanned 500 times per run.
  Both now clear the ordering with `.order_by()`.
- Procurement tables printed the raw English status enum
  («partiallyReceived», «ordered») into an otherwise Persian page.

### Known limitation

- Buyer-role targeting resolves to nobody on a fresh install, because no user
  holds `maintenanceManager`. The alert falls back to the tenant/platform
  admins so it is never silently dropped, but assigning the role gives the
  intended routing. **Resolved in 0.2.1**, which also showed the same gap had
  been silencing the pre-existing maintenance alerts.

## [Unreleased]

### Fixed

#### Correctness

- **Export downloads with non-ASCII filenames were unusable.** Five export
  endpoints built `Content-Disposition` by hand. The device maintenance report
  embeds the user-supplied device code in the filename, so a Persian code made
  Django RFC 2047-encode the *entire* header — including the word
  `attachment` — leaving the browser a header it cannot parse. All export
  endpoints now use Django's `content_disposition_header()` (RFC 6266/5987).
  Covered by `tests/integration/testExportFilenameEncoding.py`, which fails
  against the previous implementation.
- **Lost update on spare-part stock.** The procurement goods-receipt and
  supplier-return paths read, mutated and wrote `SparePartModel.quantityOnHand`
  without a lock, so two concurrent receipts for one part silently discarded
  one of them. Both paths now go through the maintenance repository, which
  already wraps the movement in `transaction.atomic` + `select_for_update`.
- **Single-brace placeholders were never interpolated.** 23 catalogue strings
  used `{count}` while the translator only understood `{{count}}`, so the
  maintenance dashboard printed `{critical} مورد بحرانی باز` verbatim.
- **`median()` and `clampScore()` could not accept the input they were given.**
  Signatures now match the defensive behaviour the bodies already implement.

#### Internationalisation

- **622 of 1542 `en` entries (41%) contained Persian text.** Because `fa` is
  composed as `{ ...en, ...fa }`, the Persian UI resolved them through the
  English fallback, so the defect was invisible unless you selected English.
  Those values moved to `fa` — which they belonged to, and which was missing
  exactly those 624 keys — and `en` received real English.
- **24 `cmms.wave1.*` entries had the key segment lowercased as their value**,
  so the English inspections screen rendered literal words like `coltitle`,
  `failnotice` and `slabanner`. All 24 translated.
- Four new catalogue guards in `localization.test.ts` keep `en` free of
  Persian, keep `fa` free of English fallbacks, reject a value that is merely
  its own key, and require placeholder names to match across locales.

#### Types and architecture

- **`mypy` was failing with 101 errors and the CI gate had never passed.** Now
  zero errors across 996 files. The dominant cause was repository classes
  defining a `list()` method, which shadows the builtin inside the class body
  and silently invalidated 33 annotations in 11 files.
- **Cross-context dependency violation.** `apps.procurement` imported
  `apps.maintenance.infrastructure.models` directly. Stock movement is now
  exposed through `apps.maintenance.application.services.inventoryContract`.
- **`apps.procurement` had no `domain/` layer.** Rather than create an empty
  package, the pure receipt arithmetic misplaced in `application/services/`
  moved to `domain/services/receiptRules.py`.
- **`apps.documents` declared no outbound ports.** `DocumentRepository` and
  `DocumentFileStorage` protocols now make the container's attribute injection
  type-checked.
- **`GetDeviceProfileUseCase` subclassed `GetDeviceAnalyticsUseCase`** purely to
  reuse `_compute`, while accepting a different query and returning a different
  DTO. The shared computation moved to a `DeviceAnalyticsComputation` base.
- Naming conventions enforced: 4 file, 94 test-method, 7 class and 3 view
  renames, with `validate_<field>` exempted because DRF resolves validators by
  that name.

#### Security and hygiene

- `xlsx` moved to a patched build (the fixed versions are not published to npm);
  `npm audit` reports 0 vulnerabilities.
- **14 uploaded tenant documents were committed to the repository.** Removed
  from version control. `.gitignore` listed `media_root/` and `staticroot/` but
  the settings default to `mediaRoot/` and `staticRoot/`, and git is
  case-sensitive on Linux — both spellings are now ignored.
- Deleted a dead duplicate `/apps` and `/config` tree at the repository root,
  frozen since "phase 12" and shadowed by `backend/`.

### Added

- `.github/workflows/frontendCi.yml` — the frontend had no CI at all. Mirrors
  the backend gate: typecheck, tests (pinned to demo mode so specs cannot make
  live network calls), build and an advisory dependency audit.
- Route-level code splitting with `Suspense`; the entry bundle fell from 995 kB
  to 479 kB (146 kB gzipped), with `xlsx` and the QR stack as lazy chunks.
- `src/core/localization/format.ts` — one locale-aware source of truth for
  number, date, percent and time formatting.
- `apps/sharedKernel/domain/coercion.py` — explicit `asInt` / `asDecimal` /
  `asStringList` for loosely-typed inbound payloads.

### Known issues at the time of 0.1.0

Resolved in 0.2.1 (frontend specs) — see above. Still open: the `de` catalogue
holds 134 of 1542 keys; `ReportsPage` and `SettingsPage` are not wired to live
data.

### Fixed (found by running the stack, not just its tests)

- **`backend/.env` was never read.** `BASE_DIR` resolved to the repository root
  instead of `backend/`, despite its own comment saying "Backend root
  (backend/)". README.md tells every developer to copy `backend/.env.example`
  to `backend/.env`, and that file was silently ignored — configuration fell
  back to defaults and `db.sqlite3`, `staticRoot/` and `mediaRoot/` were
  scattered across the repository root.
- **The demo seed produced data the application could not read back.**
  `seedDemo` wrote one work order with `type="coordinating"` and another with
  `status="scheduled"`; neither value exists in `WORK_ORDER_TYPES` or
  `WORK_ORDER_STATUSES`. The ORM accepted both, but listing work orders raised
  `SYS_VALIDATION_FAILED`, so the work orders page was broken for anyone who
  followed the documented setup. `tests/integration/testSeedDemoProducesValidData.py`
  now validates the seed tables against the domain enums and reads the list
  back over HTTP.
