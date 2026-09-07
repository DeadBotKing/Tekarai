# Tekarai Web GUI — Phase 18

**Version:** 0.18.0  
**Status:** Implemented and verified

This package is the generic Tekarai Application Interface Platform. It is a
presentation client, not a domain implementation: feature code consumes
versioned API/service contracts and never imports Django, an ORM, a repository
or a database.

## Stack

- React 19 + TypeScript
- Vite
- React Router
- Vitest + Testing Library
- Playwright desktop/mobile smoke tests
- Owned CSS design tokens and inline SVG icons

The technology decision is recorded in
[`../docs/adr/ADR-025-FrontendTechnology.md`](../docs/adr/ADR-025-FrontendTechnology.md).

## Run

```bash
npm install
npm run dev
```

Vite serves on `http://localhost:4173` and binds to `0.0.0.0` for proxied
previews. `/api` and `/ws` are proxied to the local backend in development.

## Configuration

```bash
cp .env.example .env.local
```

| Variable | Default | Description |
|---|---:|---|
| `VITE_API_BASE_URL` | empty | same-origin by default; set only for another API origin |
| `VITE_API_VERSION` | `v1` | centralized API version |
| `VITE_DEMO_MODE` | `true` in dev | deterministic local UI data; **false in production** |
| `VITE_REALTIME_ENABLED` | `false` | optional WebSocket transport |
| `VITE_APP_NAME` | `Tekarai` | product label |

Vite variables are public. Do not place secrets in them. Production identity
must use the configured backend/session provider; demo session storage is not a
production auth mechanism.

## Quality gate

```bash
npm run typecheck
npm test
npm run build
npm run test:e2e
```

Available scripts:

- `npm run dev` — development server
- `npm run build` — TypeScript + production Vite build
- `npm run typecheck` — TypeScript project references
- `npm test` / `npm run test:coverage` — unit, component and contract tests
- `npm run test:e2e` — Chromium desktop/mobile smoke journeys
- `npm run quality` — typecheck, unit tests and production build

## Architecture

```text
src/
├── app/                 providers, routing, runtime configuration
├── core/                API, auth, tenant, permissions, flags, theme, i18n,
│                       notifications, errors, telemetry, realtime
├── features/            domain-neutral feature services and demo adapters
├── layouts/             application shell and protected route
├── pages/               page-level composition
├── shared/components/   design-system primitives and composites
├── shared/hooks/        reusable local-state hooks
├── shared/types/        API-independent DTO/form contracts
├── styles/              centralized tokens and responsive styles
└── tests/               unit/component/integration/accessibility contracts
```

### Data flow

```text
User
  ↓
Application Shell → Auth / Tenant / Permission / Feature Flag contexts
  ↓
Page + shared components
  ↓
Feature service
  ↓
ApiClient (version + auth + tenant + timeout + retry + envelope)
  ↓
Tekarai API v1 → Application → Domain → Infrastructure
```

### State ownership

- Local state: component controls and modal/tab state.
- Feature state: page workflows such as project editing and dashboard layout.
- Application state: auth, tenant, permissions, theme, locale, notifications and
  feature flags.
- Server state: `TenantAwareCache` and `useAsyncResource`; cache is not source
  of truth and is invalidated explicitly.

## Demo journeys

The default development demo contains no real credentials. The sign-in form is
pre-filled and any values may be submitted. It demonstrates:

- tenant switching (`Nordic Manufacturing Group`, `Atlas Engineering GmbH`,
  `Tekarai Platform`)
- dashboard widget customization
- project create/edit and generic table controls
- task list/board/timeline/calendar views
- document upload progress and capability-aware viewer
- reports, notifications, admin/audit and settings
- Project Intelligence evidence, recommendations and task context
- light/dark mode and English/Persian/German RTL/LTR switching

## API contract

See [`../docs/api/GUI_PLATFORM.md`](../docs/api/GUI_PLATFORM.md) for envelope,
headers, auth refresh, pagination, upload, intelligence and real-time contracts.
See [`../docs/operations/guiPlatform.md`](../docs/operations/guiPlatform.md)
for deployment and incident procedures.
