# ADR-025 — Web GUI Technology and Application Interface Platform

- **Status:** Accepted
- **Date:** 2026-09-06
- **Phase:** 18 — GUI Architecture & Application Interface Platform
- **Owners:** Tekarai Platform Architecture

## Context

The web surface was intentionally a placeholder through Phase 17. Phase 18
requires a generic, tenant-aware and permission-aware presentation platform for
current and future Tekarai domains, not a domain-specific collection of pages.
The backend already exposes a versioned REST contract with the standard
`{success, data, meta, errors}` envelope and may expose WebSocket transports for
selected real-time features.

## Decision

Tekarai Web uses:

- **React 19 + TypeScript** for component composition and explicit contracts.
- **Vite** for development, production bundling, source maps and code-splitting
  boundaries.
- **React Router** for version-independent protected application routes.
- A small, owned **Tekarai Design System** using CSS design tokens and inline
  SVG icons. There is no vendor component library dependency in the platform
  core.
- React Context for application state (`auth`, `tenant`, `permissions`,
  `theme`, `localization`, `notifications`, `feature flags`) and local state
  for component/feature state. Server state uses `TenantAwareCache` and the
  `useAsyncResource` lifecycle.
- A single `ApiClient` as the only HTTP boundary. It owns API versioning,
  auth headers, tenant context, timeout, retry policy, cancellation, envelope
  parsing and stable client errors.
- An optional `RealtimeClient` transport adapter. Business logic is never
  placed in a WebSocket handler.

## Security decisions

1. Feature components cannot access the database, ORM, repository or backend
   infrastructure. They consume DTO-like contracts through feature services.
2. Access and refresh tokens are centrally managed. The demo uses
   `sessionStorage` only so a refresh is available during the demo tab; a real
   deployment must prefer an httpOnly, secure, same-site cookie/session
   provider configured behind the same port.
3. The browser sends `Authorization: Bearer` and `X-Tenant-ID` through the
   client boundary. The backend remains the security source of truth for both
   authorization and tenant isolation.
4. Demo mode uses generated, non-production tokens and deterministic fixture
   data. It is enabled for local development only; production deployments set
   `VITE_DEMO_MODE=false` and configure the API.
5. Telemetry redacts token, password, secret, authorization, cookie and email
   keys before emitting diagnostics.

## Consequences

- The GUI is generic: Projects, Tasks, Documents, Reports, Intelligence and
  Administration are feature surfaces on shared primitives rather than
  industry-specific widgets.
- New domains add routes, DTOs and feature modules without changing the shell,
  token system or API transport.
- The owned design system has a smaller dependency footprint and gives Tekarai
  direct control over RTL/LTR, keyboard focus, contrast and theme behavior.
- Backend endpoint availability is environment-dependent. Demo mode makes the
  interface independently reviewable while the feature services keep the
  integration boundary explicit.
