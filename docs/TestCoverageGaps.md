# The twelve gaps: what is now covered, what is not, and why

Twelve categories of missing testing were raised. This records what was
built, what each one found, and — for the ones that are not done — what is
actually blocking them, rather than leaving the impression they were covered.

## Summary

| # | Gap | Status | Found |
| --- | --- | --- | --- |
| 1 | Real E2E with a real backend and database | **Partly** — API-level, real DB, real HTTP | — |
| 2 | Concurrent multi-tenant | **Done** | **Cross-tenant write hole (critical)** |
| 3 | Load testing | **Partly** — concurrency, not sustained load | Session write on every request |
| 4 | Many devices and work orders | **Done** | — |
| 5 | Offline sync | **Not done** | — |
| 6 | Large file upload | **Done** | — |
| 7 | Redis/Celery outage | **Done** | — |
| 8 | Database outage | **Done** | — |
| 9 | Permission matrix in the UI | **Done** | — |
| 10 | File security | **Done** | — |
| 11 | Backup and restore | **Done** | **`dumpdata` backs up nothing (critical)** |
| 12 | Disaster recovery | **Not done** | — |

69 new tests. Backend 2983 → 3024, frontend 313 → 325.

## The two real defects this found

### 1. Any authenticated user could write into any tenant

`apps/maintenance/application/services/tenantResolver.py` began:

```python
def resolveTenantId(requestedTenantId: str) -> uuid.UUID:
    if requestedTenantId:
        return uuid.UUID(requestedTenantId)   # whatever the caller said
```

Seven views feed it `request.data.get("tenantId")`. Tenant ids are not
secrets — the API returns them in every payload — so an authenticated user of
tenant A could post `tenantId: <B>` and plant rows in tenant B. Confirmed
three ways, each returning `201`:

- a device written into another tenant,
- a work order submitted against another tenant's device,
- a device written into a tenant id that did not exist at all.

Reads were already scoped correctly, which is why no existing test caught it:
every suite runs with one tenant, and a missing filter has nothing to leak
when there is nothing else in the table.

The fix compares the requested tenant against the authenticated context and
raises `TenantAccessDeniedError` on a mismatch, matching what the analytics
module already did. A request naming the caller's own tenant still works,
because clients legitimately send it.

One wrinkle worth recording: the first version of the fix also refused when
there was *no* context, which broke nine tests — the alert scanner, the PM
generator and the reminder command iterate tenants explicitly and have no
request to be compared against. Background callers are now allowed through,
and every network path has a context because authentication sets it.

### 2. `manage.py dumpdata` produces an empty backup

Django only dumps apps whose `models_module` is set, which means apps with a
`models.py` at their root. This codebase keeps models in
`infrastructure/models.py`, and `testPhase4DatabaseArchitecture` enforces
that. So every business app has `models_module = None` and `dumpdata` skips
all of them **without an error**.

Measured on a database holding three devices:

```
manage.py dumpdata   →   20 records: auth.permission, contenttypes.contenttype
manage.py backupData →  380 records across 9 models, devices included
```

An operator following the obvious Django backup procedure would have been
holding an empty file and would not have found out until a restore.

`apps/sharedKernel/management/commands/backupData.py` collects models through
the app registry instead, and writes a fixture `loaddata` reads back.
`--tenant` limits the dump to one tenant. Adding `models.py` shims would have
been the smaller change and was rejected: the architecture rule forbidding
them is correct and worth more than the convenience.

## What was built

**`tests/integration/testMultiTenantIsolation.py`** (6) — reads and writes
across a genuine second tenant, created through the real use cases and
authenticated through the real login endpoint.

**`tests/resilience/testDependencyOutages.py`** (7) — database and broker
failures. `readyz` must go 503 while `healthz` stays 200; a failed query must
return the project envelope with a correlation id and must not leak the
database message; a failed write must not report success. The application
already behaved correctly on all seven — worth knowing deliberately rather
than by assumption.

**`tests/resilience/testFileSecurity.py`** (13) — `../../../etc/passwd` and
its backslash variant reduced to a bare filename; cross-tenant download and
delete refused; unauthenticated access refused; 26 MB refused and 5 MB
accepted; uploaded HTML served as an attachment rather than inline; bytes and
Persian filenames surviving the round trip.

**`tests/resilience/testScaleAndLoad.py`** (8) — 500 devices and 500 work
orders. The N+1 assertions compare query counts between two page sizes rather
than hard-coding a number, so they survive migrations and still fail on a
per-row query. Plus two tenants on eight threads, checking that concurrency
does not leak the request-scoped tenant.

**`tests/resilience/testBackupRestore.py`** (7) — dump, delete, reload,
compare; the device-to-work-order link; Persian text byte-for-byte; a second
restore that must not duplicate; and two tenants that must not merge.

**`frontend-web/src/tests/permissionMatrix.test.tsx`** (12) — five shipped
roles against the real `PermissionProvider`, driven through a real session.
Covers that a list of permissions is an AND, that `"*"` is exact and
`"procurement.*"` does not work, and the separation-of-duties rule that a
maintenance manager may raise a requisition but not approve it.

## What is not done, and why

### Full browser E2E (gap 1, partly)

What exists now is end-to-end at the API boundary: real HTTP, real Django,
real database, real authentication, real file storage. What is missing is a
browser driving the actual UI.

Playwright cannot run in this environment — `chrome-headless-shell` is
missing `libnspr4.so`. `playwright.config.ts` and `npm run test:e2e` are
already in the repository; they need a machine with the browser dependencies
installed, not more code.

### Sustained load testing (gap 3, partly)

Covered: concurrent correctness — does the system stay correct with eight
threads interleaving. Not covered: throughput and latency under sustained
load, which needs a load generator (locust, k6), a database that is not
SQLite, and a machine whose numbers mean something. Wall-clock assertions
from a shared CI container are noise, and a test that fails randomly gets
disabled within a month.

One finding from the concurrency work is worth acting on regardless: **every
authenticated request writes to the database**. `principals.verifyToken`
updates `Session.lastActivityAt` on each call, so every read is also a write.
On SQLite under eight threads this produced `database is locked` for most
requests; on a real database it is write amplification proportional to total
traffic. Throttling that update to once a minute per session would remove it.

### Offline sync (gap 5)

`src/tests/fieldOpsOffline.test.ts` exists and covers the queue. What is not
tested is the hard part: a conflict where the same work order was edited
offline and on the server, and what the merge does. That needs a decision
about merge semantics before a test can assert anything — currently there is
no stated rule, and a test would be inventing one.

### Disaster recovery (gap 12)

Gap 11 covers the mechanism a recovery depends on, and it found that the
mechanism was broken. Disaster recovery proper — a second region, a measured
RTO and RPO, a rehearsed failover — is an infrastructure exercise, not a test
suite. The honest next step is a runbook with numbers in it, exercised on
real infrastructure.

## Caveats that apply to all of the above

- **SQLite is not the production database.** Concurrent writers serialise, so
  the concurrency tests retry on lock and assert on the requests that
  succeeded. On SQL Server or Postgres these would be stronger.
- **Outages are simulated at the seam**, not by stopping a service. The
  assertions are about our status codes and envelopes, which are identical
  either way.
- **The scale tests use 500 rows**, enough to expose an N+1 and an unbounded
  page, not enough to say anything about index behaviour at a million.
