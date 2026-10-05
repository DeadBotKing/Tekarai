# Changelog

This file did not exist before. The repository had a single `main` branch, no
tags and commit messages such as `calender`, `color`, `tem` and `update`, which
made it impossible to tell what any given commit changed or to roll back to a
known-good state. Entries follow [Keep a Changelog](https://keepachangelog.com)
and the project aims at [Semantic Versioning](https://semver.org).

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

### Known issues

- Six frontend specs fail when `VITE_DEMO_MODE=false` because they reach for a
  live API instead of a mock (`registry pages`, `chat page`,
  `locations page dropdown`). CI pins demo mode; the specs still need fixing.
- The `de` catalogue holds 134 of 1542 keys and falls back to English for the
  rest.
- `ReportsPage` and `SettingsPage` are not wired to live data.

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
