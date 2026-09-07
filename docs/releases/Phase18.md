# Tekarai 0.18.0 — Phase 18 Release

**Phase:** GUI Architecture & Application Interface Platform  
**Date:** 2026-09-06  
**Status:** Implemented and verified

## Release summary

Phase 18 replaces the `frontend-web/` placeholder with a generic React and
TypeScript application-interface platform. The shell is tenant-aware,
permission-aware, localized, themeable, responsive and accessible by default.
Feature screens are composed from an owned design system and consume explicit
API/service contracts rather than persistence concerns.

## Delivered capabilities

- React 19 + TypeScript + Vite technology contract and ADR-025.
- Protected application routing and an authentication flow with centralized
  session/token management and demo-mode fixtures.
- Tenant selector and request context header; permission guard with deny-by-
  default rendering and feature flag evaluation.
- Dynamic navigation configuration with routes, icons, permissions and feature
  flags.
- Design tokens, light/dark themes, inline SVG icon set, responsive layout,
  RTL/LTR direction and English/Persian/German localization.
- Primitive/composite/feature/page/application component layers.
- Generic DataTable with sorting, search filtering, pagination, column
  visibility, row selection, bulk-action slot, export and loading/empty/error
  states.
- Schema-driven form validation, field-level errors, dirty/submit affordances
  and accessible labelled controls.
- Global tenant-scoped search, notification center, unread state and mark-read
  flows.
- Widget-based dashboard with metrics, charts, activity feed and customization
  controls.
- Projects, tasks (list/board/timeline/calendar), documents/upload/viewer,
  reports, operations resources, administration, audit and settings surfaces.
- Phase 17 Project Intelligence UI: overview, health breakdown, architecture,
  dependencies, change history, evidence-based insights, recommendations and
  task-specific agent context.
- API client with standard envelope/error mapping, versioning, auth refresh,
  tenant headers, timeout, retry, GET deduplication, cancellation, caching and
  upload progress.
- Optional WebSocket transport adapter with reconnect status and no business
  logic in the transport.
- Error boundary, telemetry redaction, responsive accessibility and reduced
  motion support.
- Unit/component/contract tests and desktop/mobile Playwright smoke journeys.

## Verification

- `npm run typecheck`: PASS
- `npm test`: PASS (7 files, 15 tests)
- `npm run test:coverage`: PASS (54.03% statements, 54.61% branches,
  41.61% functions, 54.03% lines)
- `npm run build`: PASS
- `npm run test:e2e`: PASS on Chromium desktop and mobile profiles
- `npm audit`: 0 vulnerabilities at install time

## Known integration boundary

The repository's Phase 17 backend is the source of truth for authentication,
permissions, tenant isolation and intelligence data. The frontend ships with a
safe, deterministic demo mode for independent UI review. Production must set
`VITE_DEMO_MODE=false` and provide the backend endpoints described in
`docs/api/GUI_PLATFORM.md`.
