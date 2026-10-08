# Changelog

This file did not exist before. The repository had a single `main` branch, no
tags and commit messages such as `calender`, `color`, `tem` and `update`, which
made it impossible to tell what any given commit changed or to roll back to a
known-good state. Entries follow [Keep a Changelog](https://keepachangelog.com)
and the project aims at [Semantic Versioning](https://semver.org).

## [0.9.0] — Scope is now enforced, not just recorded

Written after walking the four factory scenarios the client proposed. The
first three held. The fourth — «مریم، QA، رئیس باید Work Orderهای QA را
ببیند، نه فنی و تولید» — **did not**, and the way it failed is worth
recording: every grant resolved correctly, the profile said
`WorkOrder.View = department`, and the list endpoint returned every unit's
work anyway. Scope was computed and then ignored. That is the worst
possible state for a permission system, because it reads as a control
while behaving as a wildcard.

Sixteen scenario tests were written from the brief's wording before any
fix; eleven failed. They now pass, as do sixteen more that drive the same
scenarios over real HTTP.

### Added

- **Attribution on work orders**: `orgDepartmentId`, `requestedByUserId`,
  `assignedToUserId`, stamped at creation from the requester's primary
  posting. The existing `requestedByName` / `assignedToName` fields cannot
  carry an access decision — two «رضا»s are not the same person, and
  renaming a user would silently change who can see a record.
  `orgDepartmentId` is deliberately separate from the existing
  `department` field, which is maintenance's own routing crew.
- **Scope applied to the work-order query**, before any caller filter, so
  no query parameter can widen it. The actor comes from the session, never
  from a parameter.
- **Record-level checks on `GET` and `PATCH`** of a single work order,
  reading the same resolution as the list — a user can never be shown a
  row they are then refused on open.
- `own` scope now also covers work **assigned** to the person, not only
  work they raised; otherwise «کار خودش» excluded the job they were told
  to do.
- 32 new tests: `testFactoryScenarios.py` (the four scenarios at the
  resolution level) and `testScenarioEnforcementApi.py` (the same over
  HTTP, including a test that a query parameter cannot escape the unit and
  that list and detail never disagree).

### Changed

- **«مدیر» now defaults to `department` scope, not `all`.** A unit manager
  runs his unit. Plant-wide sight is a different job — «مدیر کارخانه» —
  which an administrator creates and grants `all` deliberately. Defaulting
  every manager to `all` meant the first person given the title could read
  every unit in the factory, which is the collapse of «واحد» this design
  exists to prevent. The eight verbs are unchanged; only their reach is.

### Compatibility

A tenant with no units defined is unaffected: no filter is applied and
every list behaves exactly as before. Once units exist, a user with no
posting gets an empty list rather than a full one. The asymmetry is
deliberate — **absence of configuration is permissive, absence of
permission is not.**

### Tests

Backend 3332 → **3364**; frontend **380**. mypy clean across 1077 files,
ruff clean, `tsc -b` clean, 164 architecture tests green.

## [0.8.0] — Organisation chart and unit/position access control

Gap #4 from the CMMS gap analysis. Until now access came from a flat Role,
which cannot tell «مدیر فنی و مهندسی» from «مدیر تولید», cannot say "only
his own work orders", and could not be extended without a programmer. The
unit of access is now the posting — **کاربر + واحد + سمت** — and every
grant carries a scope.

### Added

- **New bounded context `apps.organization`** (the register's long-planned
  `organization` context, opened by this release). Five tables: units,
  positions, postings, matrix cells and an append-only audit log. Users are
  referenced by id only — no foreign key into identity.
- **Units («واحدها») and positions («سمت‌ها») are data, not code.** Seeded
  with فنی و مهندسی / QC / QA / HSE / تولید and مدیر / رئیس / سرپرست /
  کارشناس / تکنسین / اپراتور, all of which the plant may rename, nest,
  deactivate or extend from inside the CMMS. Adding «انبار» or «سرپرست برق»
  tomorrow requires no deployment.
- **A position alone grants nothing.** Authority comes from the posting, so
  «علی، فنی و مهندسی، مدیر» and «رضا، همان واحد، تکنسین» are different
  principals. A user may hold several postings; their grants union, and the
  widest scope wins on collision.
- **A per-unit permission matrix** of capability × verb → scope, editable at
  runtime. Eight verbs (View, Create, Edit, Delete, Approve, Assign, Close,
  Export) rather than a single show/hide flag.
- **Scope on every grant** — `own` / `team` / `department` / `all`. The
  brief's worked case holds end to end: a technician sees and edits only his
  own work orders, a supervisor his team's, a رئیس the unit, a factory
  manager everything.
- **`scopeFilterForUser` and `userCanActOnRecord`**, derived from the same
  resolution, so a user is never shown a row they cannot open.
- **Screen «ساختار سازمانی»** with three tabs and a scrollable matrix grid
  whose rows are drawn from the catalogue the server sends.
- **`manage.py seedOrganization --tenant <uuid>`** — idempotent.
- `docs/OrganizationAccessControl.md`.

### Changed

- **`AccessRepositoryDjango.grantsOfUser` now also assembles grants from the
  organisation chart**, through the organization context's public
  application contract. Org grants are inserted *before* direct user grants
  so an explicit `deny` still overrides them: there remains exactly one
  place to look when locking someone out.
- **New public contract
  `apps.identity.application.services.authorizationInvalidation`.** Other
  contexts can now say "this user's access changed" without importing
  identity's cache. Every structural or matrix change bumps the affected
  users' version, so a revoked posting stops working on the next request
  rather than when a TTL expires.
- Twelve new permission codes registered in the catalogue, including the
  `maintenance.workorder.delete/.close/.export` verbs the matrix can grant
  and which had no code before.

### Fixed

- **The matrix view merged every unit's overrides when no unit was
  selected**, showing an organisation-wide grid of scopes that applied in no
  unit at all. Caught by its own API test.

### Design notes

- **Capabilities and verbs are code; everything else is data.** Each matrix
  cell maps to real enforced action codes, and a cell that resolves to none
  is refused rather than stored — a tick that grants nothing is worse than
  no tick. `testEveryMatrixActionCodeExistsInThePermissionCatalogue` breaks
  the build if anyone adds one.
- **The matrix is additive; it has no deny.** Subtraction stays with
  identity's `UserPermission` deny rows.
- **A unit-specific rule replaces the organisation-wide default outright,
  including when it is narrower** — "in QC the supervisor sees only his own"
  has to be expressible.
- **Seniority grants nothing.** `level` orders the grid's columns; a higher
  number does not inherit a lower one's permissions.
- **An unknown scope string resolves to no access**, so a seed typo cannot
  become a wildcard, and a user with no grant yields `denied`, never an
  unfiltered query.

### Tests

Backend 3216 → **3332**; frontend 353 → **380**. mypy clean across 1075
files, ruff clean, `tsc -b` clean, all 164 architecture tests green.

## [0.7.0] — Permit to Work (مجوز کار)

Gap #1 from the CMMS gap analysis, built because the system is going into a
real factory. A permit system that records who clicked what is paperwork;
this one is built around what it **refuses**.

### Added

- **New bounded context `apps.safety`.** Permit to work is a safety-management
  domain, not a corner of maintenance (which already carries 31 models). It
  references work orders and devices **by id only**, with no cross-context
  foreign key — the same pattern procurement uses for spare parts.
- **Ten enforced safety invariants**, each with a stable error code and a
  Persian message: self-approval refused; no issue against an unconfirmed
  mandatory precaution; no issue of an isolation-class permit unless every
  point is applied *and* independently verified; no activation outside the
  validity window; no closure while a lock is still on; no lock removal while
  work is running; illegal transitions refused; terminal states terminal;
  cross-tenant access refused; and a two-person rule above high risk where the
  verifier may not be the applier.
- **Expiry is computed from the clock, never stored.** A persisted `isExpired`
  flag is wrong for every moment between one scheduled scan and the next.
- **`scanPermitExpiry` management command**, dry-run by default. It
  auto-expires only **approved-but-never-started** permits, and merely alarms
  on overdue **active** ones — silently expiring a live permit while people are
  inside a vessel does not get them out, it only deletes the record that they
  are there. Intended cadence is every 15 minutes, not daily.
- **Four tables**: the permit, the checklist as rows (not JSON — an
  investigator asks *who* confirmed the gas test and *when*), the
  lock-and-tag register with three independent signature pairs, and an
  append-only event trail. Nothing is ever hard-deleted.
- **Eight permit types** with per-type Persian checklists, validity caps
  (hot work 12h … excavation 72h) and an isolation requirement; four risk
  levels; eight energy types.
- **API** `/api/v1/safety/permits` — list/create, detail, nine lifecycle
  actions, precaution confirmation, isolation apply/verify/remove, and a
  read-only expiry preview.
- **Five permissions** `safety.permit.view/.request/.approve/.isolate/.close`,
  wired so a technician may raise and isolate but never authorise or close.
- **Frontend `SafetyPermitsPage`** at `/app/maintenance/permits`, fixture-free
  (zero `demoMode` branches).
- `docs/PermitToWork.md` — the rules, the asymmetry of the expiry scan, and
  what was deliberately left out.

### Design decisions

- **Safety refusals return 422, not 400.** The request was well-formed; the
  *plant* was not ready, and the client has to tell those apart.
- **All blockers are reported at once**, never one at a time. A permit office
  told one missing item per attempt makes one trip per item.
- **`workAtHeight` and `radiography` deliberately do not require isolation.**
  Their controls are barriers and dosimetry; demanding a fake isolation
  register there teaches people to fill in fake ones, and that habit spreads
  to the permits where the register is real.
- **The two-person rule starts at high risk, not everywhere.** Requiring a
  second body for every low-risk isolation in a small plant produces
  signatures nobody witnessed — worse than an honest single signature.
- **Re-applying an isolation invalidates its previous verification**: what was
  checked is not necessarily what is now in place.
- **Concurrent permits on one asset are announced, not blocked** — two trades
  in one shutdown is legitimate, but it must be a conscious decision.
- **The checklist locks once the permit is authorised**: it *is* the assessment
  the signature was given against.
- The UI's disabled approve button is a courtesy; the guard lives in the
  domain, because a UI check alone is bypassed by the first person who learns
  the URL.

### Tests

- **129 new tests** (backend 3087 → 3216, frontend 335 → 353): 55 pure-rule
  tests with an injected clock, 47 against the database, 27 over authenticated
  HTTP, 18 on the page.
- The happy path is tested as deliberately as the refusals — a suite that only
  proves things are blocked can hide a rule that blocks everything, which in a
  real plant means the system is bypassed on paper within a week.
- Live smoke test on a seeded database confirmed all four headline refusals
  fire over HTTP and that a fully prepared permit completes the whole
  draft→closed cycle.

### Known limitations

- No digital or biometric signature; no permit extension (extensions become a
  way around the validity cap); `workOrderId` is stored but not yet populated
  from the work-order screen; no safety reporting or KPIs yet.
- The one-user test fixture means segregation of duties correctly fires before
  every other check; tests that need to exercise the rules underneath it seed
  a second requester directly.

## [0.6.0]

### Added

- **The stock→purchase loop.** Low stock now becomes a purchase request
  instead of only a notification somebody had to act on by hand. All three
  pieces already existed and none were connected: the warehouse knew a part
  was below minimum, `SupplierPart` knew who sells it at what price with
  what lead time and minimum order quantity, and the requisition → order →
  receipt chain knew how to buy things.
  - New domain service `procurement/domain/services/reorderPolicy.py` —
    pure rules, no ORM. Decides *whether* and *how much*.
  - New application service `replenishmentScan` + infrastructure query
    module `replenishmentRepository` (the application layer may not import
    the ORM).
  - `GET/POST /api/v1/procurement/replenishment` — preview and apply.
  - New «تأمین انبار» tab on the procurement page showing the arithmetic:
    on hand, already on order, net, suggested, supplier, estimated cost.
  - `python manage.py runReplenishment [--apply] [--tenant <uuid>]` for
    cron. **Dry run is the default** — a cron line meant to report must not
    start spending because of a typo.
- `SparePart.reorderQuantity` and `SparePart.autoReorder`
  (migration `maintenance/0021_sparePartReorderPolicy`). Both additive with
  defaults that preserve today's behaviour; the loop works with zero
  configuration by topping up to twice the minimum.
- Public contract `inventoryContract.listStockPositions()` /
  `tenantIdsWithStock()`, so procurement reads warehouse stock through
  maintenance's `.application` facade rather than its tables (RULE E/F).
- Notification route `replenishmentRequisitionRaised` (NORMAL — these are
  drafts to review, not an escalation).

### Design decisions

- **Counting goods already on order is what makes the loop idempotent.**
  The trigger is net available stock — on hand *plus* open requisition
  lines *plus* the undelivered purchase-order balance. Because a draft this
  scan creates immediately counts as incoming, a second run proposes
  nothing, with no deduplication key to keep in sync. A scan that ignored
  goods in transit would raise a fresh request every night until delivery.
  Verified on a real seeded database: run 1 created one requisition, runs 2
  and 3 created zero.
- **Drafts, not submitted requests.** A machine may notice the need; a
  person still decides to spend the money. It also keeps generated requests
  out of the buyer's overdue list, since the staleness clock starts at
  `submittedAt`.
- **One requisition per supplier, not per part.** Parts with no supplier on
  file are grouped into a single unassigned requisition rather than dropped.
- Urgency reuses the requisition priority vocabulary, so a stockout is also
  chased up sooner; a multi-line requisition inherits the most urgent line's
  priority.
- No new permission: `POST` is gated on `procurement.requisition.create`,
  the permission that already governs the object it creates.

### Tests

- Backend **3024 → 3087** (19 reorder-policy unit tests, 44 integration).
- Frontend **325 → 335**.
- Gates: `tsc --noEmit` ✔, `ruff` ✔, `mypy` ✔ (1025 files), architecture
  suite ✔.

### Known limitations

- Safety stock from lead-time demand, ABC classification and consumption
  forecasting are **not** implemented — all three need consumption
  statistics the part ledger does not yet aggregate, and a fabricated
  number would be worse than none. See `docs/StockPurchaseLoop.md`.
- The replenishment panel is live-data only: the demo-boundary rule forbids
  new files branching on the demo flag, so under demo fixtures it shows its
  error state rather than a fabricated shortage list.

## [0.5.0]

### Security

- **Any authenticated user could write into any tenant.**
  `maintenance/tenantResolver.resolveTenantId` returned whatever `tenantId`
  the caller supplied, and seven views feed it `request.data.get("tenantId")`.
  Tenant ids are returned in every API payload, so this was reachable by
  anyone with a login. Confirmed three ways, each returning `201`: a device
  planted in another tenant, a work order submitted against another tenant's
  device, and a device created in a tenant id that did not exist. The
  resolver now compares the requested tenant against the authenticated
  context and raises `TenantAccessDeniedError` on a mismatch; a request
  naming the caller's own tenant still works, and background jobs that
  iterate tenants without a request context are unaffected.

### Fixed

- **`manage.py dumpdata` produced an empty backup.** Django skips apps whose
  `models_module` is `None`, which is every app here because models live in
  `infrastructure/models.py` by architectural rule. A dump of a populated
  database returned 20 records — `contenttypes` and `auth.permission` — and
  said nothing about the omission. New `manage.py backupData` collects models
  through the app registry and writes a `loaddata`-compatible fixture; the
  same database yields 380 records across 9 models. `--tenant` limits the
  dump to one tenant.

### Added

Sixty-nine tests across the twelve gaps raised. Backend 2983 → 3024,
frontend 313 → 325. See `docs/TestCoverageGaps.md` for what each suite
covers and what remains uncovered.

- `tests/integration/testMultiTenantIsolation.py` (6) — a genuine second
  tenant, created through the real use cases, with reads and writes attempted
  across the boundary.
- `tests/resilience/testDependencyOutages.py` (7) — database and broker
  failures: `readyz` 503 while `healthz` stays 200, failed queries returning
  the project envelope with a correlation id and no leaked driver message,
  failed writes never reporting success.
- `tests/resilience/testFileSecurity.py` (13) — path traversal in filenames,
  cross-tenant download and delete, unauthenticated access, the 25 MB
  ceiling, uploaded HTML served as an attachment, byte-exact round trips and
  Persian filenames.
- `tests/resilience/testScaleAndLoad.py` (8) — 500 devices and 500 work
  orders: paging, clamped limits, and N+1 detection by comparing query counts
  across page sizes; two tenants on eight threads checking that the
  request-scoped tenant does not leak under concurrency.
- `tests/resilience/testBackupRestore.py` (7) — dump/delete/reload round
  trips, foreign keys, Persian text, idempotent re-restore, and two tenants
  that must not merge.
- `frontend-web/src/tests/permissionMatrix.test.tsx` (12) — five shipped
  roles against the real provider and a real session, including that a
  permission list is an AND, that `"*"` is exact, and that a maintenance
  manager may raise a requisition but not approve it.
- `tests/support/multiTenantHelpers.py` — builds a second tenant with its own
  administrator through the application's own use cases.

### Known issues

- **Every authenticated request writes to the database.**
  `principals.verifyToken` updates `Session.lastActivityAt` on each call, so
  every read is also a write. Under concurrency on SQLite this produces
  `database is locked`; on any database it is write amplification
  proportional to traffic. Throttling the update to once per session per
  minute would remove it.
- Browser-level E2E, sustained load testing, offline sync conflict
  resolution, and disaster recovery remain uncovered. Each is blocked on
  something other than test code — missing browser libraries, load
  infrastructure, an undecided merge rule, and a second region respectively.
  `docs/TestCoverageGaps.md` says so per item.

## [0.4.0]

### Security

- Demo fixtures are no longer linked into builds that are not demo builds.
  `vite/demoFixtureFirewall.ts` replaces each fixture module at build time
  with a same-named, empty stub. A runtime flag could not fix this: static
  imports had already put roughly 45 KB of fabricated Persian equipment,
  people and suppliers into every production bundle regardless of what
  `demoMode` said. A `VITE_DEMO_MODE=false` build now contains **zero**
  fabricated records across 66 artefacts.
- Fabricated records that sat inline inside page components — a supplier in
  `ProcurementPage`, an administrator in `AccountPage`, a role in
  `AdministrationPage`, six parts in `SparePartsPage` — moved to
  `src/features/demo/pageDemoFixtures.ts`, where the firewall covers them.
  Inline fixtures were invisible to any module-level rule.

### Added

- `ErrorState` component. A failed request is now reported on screen with a
  retry, replacing `.catch(() => setRows([]))`, which made an unreachable
  server look identical to an empty warehouse, and replacing the demo
  fallback, which answered a failure with fiction. Wired into
  `SparePartsPage`, `ProcurementPage` and `AdministrationPage`.
- `src/tests/demoFixtureIsolation.test.tsx` — renders 20 pages with
  `demoMode: false` and every request rejecting, and asserts no fixture
  string reaches the DOM. Verified by mutation: restoring one demo fallback
  makes it fail.
- `src/tests/demoFixtureFirewall.test.ts` — 14 specs over the firewall's
  rules and the stubs it generates.
- `npm run verify:demo-boundary` — builds with demo mode off and greps the
  artefacts, checking what ships rather than only the rules meant to produce
  it. Added to `npm run quality`.

### Changed

- Demo service factories in a non-demo build now throw instead of returning
  an empty object. Reaching one is a routing bug, and a loud failure in
  staging beats a blank page in front of a customer. Data exports keep their
  shape (`[]`, `{}`) so a leaked consumer renders empty rather than crashing.

### Known issues

- The 151 inline `demoMode` branches still exist and are still frozen by the
  ratchet. Production can no longer serve fixtures, but the pages are not yet
  on the service seam. See `docs/DemoModeBoundary.md`.
- The spare-parts CSV import template still ships one sample row
  (`بلبرینگ 6204`). It is a template, not data presented as the tenant's own;
  the exception is listed explicitly in `scripts/verifyDemoBoundary.mjs`.

## [0.3.0]

### Security

- A production build no longer honours `VITE_DEMO_MODE`. Demo mode includes
  `demoLogin`, which ignores the submitted credentials and returns
  `role: "Platform Administrator"` with `permissions: ["*"]`; a single
  environment variable was therefore the whole distance between a real
  deployment and one that admits anybody as administrator. Enabling demo mode
  in a production build now additionally requires
  `VITE_ALLOW_DEMO_IN_PRODUCTION=true`, a flag with no other purpose. A refusal
  is reported on the console rather than applied silently.

### Added

- `DemoModeBanner` in the application shell. Demo and real builds used to look
  identical; an active demo mode is now stated on screen, collapsing to an icon
  below 900px.
- `src/tests/demoModeProductionGuard.test.ts` — 6 specs pinning the refusal,
  the escape hatch and unchanged development behaviour.
- `src/tests/demoModeBoundary.test.ts` — a ratchet over the 151 `demoMode`
  references in 35 files. It fails when a clean file gains a branch, when a
  branching file gains more, and when branches are removed without lowering the
  baseline, so the count can only shrink.
- `docs/DemoModeBoundary.md` — the evidence, what is enforced, and the
  file-by-file plan for removing the remaining branches.
- `VITE_ALLOW_DEMO_IN_PRODUCTION` documented in `frontend-web/.env.example`,
  with the credential bypass spelled out next to `VITE_DEMO_MODE`.

### Known issues

- Demo mode is still implemented as 151 inline branches rather than a service
  seam, so roughly 45 KB of fabricated fixtures still ship in the production
  bundle. The boundary is enforced and frozen; the branches are not yet gone.
  See `docs/DemoModeBoundary.md`.

## [0.2.7]

### Fixed

- `RUNNING-WINDOWS.md` told the reader to type `run_dev.cmd`, which PowerShell
  rejects with `CommandNotFoundException` — it does not run commands from the
  current directory without an explicit `.\`. Every invocation in the document
  now reads `.\run_dev.cmd`, with a note that the prefix is required and that
  it has nothing to do with the signing restriction that applies to `.ps1`.

## [0.2.6]

### Added — `run_dev.cmd`, a launcher Windows will actually run

`run_dev.ps1` was the only way to start the stack, and a default Windows
install refuses to run an unsigned `.ps1`:

```
.\run_dev.ps1 : File ...\run_dev.ps1 is not digitally signed.
    + FullyQualifiedErrorId : UnauthorizedAccess
```

The usual advice — `Unblock-File`, or changing the execution policy — either
fails under `AllSigned` or asks someone to weaken a machine-wide security
setting in order to start a development server. `.cmd` files are not subject
to the execution policy at all, so `run_dev.cmd` hands the script to
PowerShell with `-ExecutionPolicy Bypass` scoped to that single process.
Nothing on the machine is changed, and it works by double-click.

Every switch is forwarded unchanged: `run_dev.cmd -UseSqlite`,
`run_dev.cmd -DemoMode`, and so on. The exit code is propagated, and a failure
pauses so a double-clicked window does not vanish before the error is read.

### Changed

- `RUNNING-WINDOWS.md` leads with `run_dev.cmd`, explains the signing error and
  what to do about it, and now uses real paths instead of `C:\path\to\…`
  placeholders (7 occurrences).

## [0.2.5]

### Added — a note on each requested part

A requisition had one «دلیل درخواست» covering the whole document, so there was
nowhere to say why *this* bearing is wanted while the next line is routine.
The line table in the database has carried a `note` column all along, the
serializer declares it and the create view already persists it — only the form
never sent one and no screen ever showed one.

- The compose row gained **«توضیحات این قطعه»**, which travels with the line it
  was typed for. It is cleared after the line is added, so an explanation
  cannot silently follow the next part.
- The basket table shows a توضیحات column while the request is being built.
- A new **اقلام** column in the درخواست‌ها and خریدشده lists shows every line
  with its quantity and its note, so the note is readable after filing rather
  than write-only.
- Adding the same part twice keeps both notes, joined with an em dash, instead
  of dropping one when the quantities merge.

Verified against the running API: a two-line request round-tripped
`"برای پمپ خط ۳ — جنس استیل"` and `"فوری"` to the right lines.

### Tests

- Four more specs: the note reaches the API on its own line, the box clears
  after adding, both notes survive a merge, and the list renders line and note.
- Frontend 269 tests pass; ruff and mypy clean.

## [0.2.4]

### Changed — "add a new part" now lives in the part dropdown

Creating a part that is not in the warehouse yet was an action *beside* the
picker: first a second dialog (0.2.2), then a link underneath it (0.2.3).
Someone looking for a missing part looks in the list, so that is where the
entry belongs now — «➕ افزودن قطعه جدید…» is the last option of the قطعه انبار
dropdown, mirroring the `CreatableSelect` pattern the registry pages already
use. Choosing it expands code, name, unit and unit-cost fields inside the
request; saving registers the part in the warehouse and selects it for the
line being composed, without ever opening a second window.

### Tests

- Two more specs in `procurementRequisitionLines.test.tsx`: the entry exists
  inside the dropdown and opens the fields in place with a single dialog on
  screen, and the full manual path — type a part, register it, submit the
  request with it — reaches the API with the typed code.
- Frontend 265 tests pass.

## [0.2.3]

### Changed — the procurement screen asks less of the reader

The page carried eight equally weighted tabs, eight dialogs and seven forms,
which put a receipt correction at the same visual weight as the daily job of
raising a request and checking what was bought.

- **Three tabs up front** — نمای کلی، درخواست‌ها، خریدشده — with سفارش خرید،
  رسید انبار، فاکتورها، برگشت کالا and تأمین‌کنندگان one click away under
  «بیشتر». Nothing was removed.
- **Stalled requests are shown on the tab**, as a count badge, instead of
  being visible only after navigating into the list. The number comes from
  the dashboard so it is correct whichever tab is open.
- **The requisition form is three numbered steps** — add parts, review the
  lines, then the request details — in a wide dialog, with the running
  total in the footer.
- **Defining a new part no longer opens a second dialog.** The fields expand
  inside the requisition form, so the nested-window problem does not arise on
  the common path at all. The standalone dialog remains for the returns form,
  where it is not nested.
- **The priority options state their own alert threshold** («بالا — هشدار پس
  از ۴ روز»), so the staleness rule is visible at the moment it is chosen
  rather than documented elsewhere.

### Note

Multi-part purchase requests shipped in 0.2.2; this release makes them easy to
find. Both are only visible after extracting the current archive — the
reported symptoms matched the 0.2.1 code.

## [0.2.2]

### Fixed — a purchase request can hold more than one part

- **The requisition form could only ever order a single part.** The API has
  always declared `lines = LineSerializer(many=True, min_length=1)` and totals
  across every line, but the form held one `partId` and posted
  `lines: [oneLine]`, so ordering three parts meant raising three separate
  requests — each with its own number, approval and staleness clock. The form
  now composes a line at a time into a basket, shows the lines with a running
  total, lets a line be removed, and posts all of them. Choosing the same part
  twice adds the quantities instead of writing a duplicate row. A single-part
  request can still be submitted without pressing "add" first.
  Verified against the running API: one POST created `PR-AC7C8613` with three
  lines and `totalEstimated` 4,980,000.
- **The "افزودن قطعه" button did not add a part to the request.** It opened the
  warehouse part-registration dialog — a useful shortcut for a part that is not
  in the catalogue yet, but the label read as "add a part to this request",
  which is exactly how it was reported. Renamed to «تعریف قطعه جدید در انبار»,
  and the real action is now «➕ افزودن این قطعه به درخواست».
- **The مبلغ column was blank on every purchase request.** The shared document
  table read `row.total`, which purchase orders and invoices expose but a
  requisition does not — a requisition reports `totalEstimated`, because its
  price is a forecast until a supplier quotes it. The column now falls back to
  it and formats the amount in Persian digits.
- **A modal opened from inside another modal could render behind it.** Both
  used the same `--z-overlay`, so paint order came down to JSX position, and
  both hard-coded `id="modal-title"`, which made `aria-labelledby` ambiguous
  for screen readers. `Modal` now stacks each nesting level one step higher,
  gives every instance a unique title id, and leaves the body scroll lock to
  the outermost dialog.

### Tests

- `src/tests/procurementRequisitionLines.test.tsx` — nine specs covering the
  multi-line basket, the payload actually sent, duplicate merging, removal,
  the single-part shortcut, the empty-request guard, state not leaking into the
  next requisition, the renamed button, and the amount column.
- Backend 2983 tests pass; frontend 263 tests pass with and without
  `VITE_DEMO_MODE=false`.

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
