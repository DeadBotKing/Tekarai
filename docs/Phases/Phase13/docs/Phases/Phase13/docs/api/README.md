# docs/api

**Purpose:** API contracts, versioning policy and endpoint catalogs.

**Filled in:** Phase 06 — this folder is created in Phase 01 as required
structure. Content must not be invented early; each phase delivers exactly
what its specification requires.

## Phase 06 deliverables

| File | Content |
|---|---|
| `APIArchitecture.md` | the implemented application/API architecture (§1–§35 mapping: layers, use cases, repositories, services, envelope, errors, authn/authz, tenancy, audit, idempotency, pagination/filtering/search/sort, rate limiting, OpenAPI, correlation, lifecycle, security checklist) |

Decisions: `docs/adr/ADR-019` (session tokens), `ADR-020` (OpenAPI builder),
`ADR-021` (Shared Kernel). Live contract: `/api/v1/openapi.json`, human list
at `/api/v1/docs`.

## Phase 07 deliverables

| File | Content |
|---|---|
| `APIArchitecture.md` | Phase 06 architecture — still current for the shared kernel; Phase 07 adds the identity surface below |

Phase 07 additions (spec `docs/Phases/Phase7.md` §32): `auth/login` (JWT +
refresh / MFA challenge), `auth/mfa/challenge`, `auth/refresh`,
`auth/logout`, `auth/password/change|reset/*`, `auth/verification/*`,
`auth/verify-email|verify-phone`, `roles` (CRUD + assign/remove),
`api-keys` (create/revoke/list — raw key shown once), `service-accounts`,
`me/mfa/*`, `me/sessions` (list/revoke/revoke-all). Server-to-server
authentication via `X-API-Key` (ADR-022). Decision record:
`docs/adr/022-jwt-access-tokens.md`.

## Phase 08 deliverables

| File | Content |
|---|---|
| `COMMUNICATION_API.md` | Communication surface (REST + `/ws/communication/` frame catalogue) |

## Phase 09 deliverables

| File | Content |
|---|---|
| `NOTIFICATION_API.md` | Notification surface: own notifications, preferences, devices, admin (send/schedules/templates/policies/channels/tenant-rules/metrics) and `/ws/notifications/` frames |

Phase 09 decisions: `docs/adr/ADR-024-Notification-Delivery-Architecture.md`.
