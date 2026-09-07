# Tekarai GUI Platform Contract — Phase 18

**Version:** `tekarai-gui-0.18.0`  
**API base:** `/api/v1/`  
**Envelope:** `{ success, data, meta, errors }`

The frontend is a presentation client. It does not connect to a database,
Django ORM, repository or domain entity. All data travels through
`src/core/api/apiClient.ts` and feature services.

## Request contract

Every API request created by `ApiClient` includes:

| Header | Purpose |
|---|---|
| `Accept: application/json` | JSON response negotiation |
| `X-Client-Version: tekarai-gui-0.18.0` | client observability |
| `Authorization: Bearer <access>` | authenticated calls when a session exists |
| `X-Tenant-ID: <tenant>` | selected tenant context; backend validates it |

The client adds the configured API version once. Feature code passes paths such
as `auth/login` or `projects/{id}/intelligence/`; it never repeats `api/v1`.

## Response contract

### Success

```json
{
  "success": true,
  "data": {},
  "meta": { "correlationId": "..." },
  "errors": []
}
```

### Error

```json
{
  "success": false,
  "data": null,
  "meta": { "correlationId": "..." },
  "errors": [
    { "code": "PERM_PERMISSION_DENIED", "message": "...", "field": "" }
  ]
}
```

The client maps this to `ApiClientError` with `status`, stable `code`,
optional `field`, sanitized `details` and `correlationId`. UI states classify
errors as validation, authentication, authorization, not found, conflict,
server, network or timeout; an error is never console-only.

## Authentication

| Method | Path | Client operation |
|---|---|---|
| POST | `/api/v1/auth/login` | `api.post("auth/login", credentials)` |
| POST | `/api/v1/auth/refresh` | centralized automatic one-time refresh |
| POST | `/api/v1/auth/logout` | shell logout |
| GET | `/api/v1/me` | current user and permissions |

A 401 causes one serialized refresh attempt for concurrent requests. A failed
refresh clears the central session and redirects to `/login`. GET calls retry
transient network/5xx/408/429 failures with bounded exponential backoff;
mutations are not retried by default.

## Tenant and permission contract

- Tenant selection is held by `TenantProvider` and passed to the API boundary.
- `PermissionProvider` performs deny-by-default rendering checks and supports
  wildcard permissions for platform administrators.
- `PermissionGuard` can hide or display a permission-denied state.
- Route and button visibility are usability controls only. Backend permission
  classes and object-level checks must still enforce access.

Representative actions: `project.view`, `project.create`, `project.update`,
`task.view`, `document.upload`, `report.view`,
`projectIntelligence.view`, `projectIntelligence.analyze`, `audit.view`,
`user.manage`, `role.manage`, `settings.manage`.

## Pagination, filtering and sorting

Generic table clients use explicit `page`, `pageSize` (bounded by the backend),
`search`, filter fields and whitelisted sort fields. UI tables always support a
loading state, empty state, error state, sorting, column visibility, selection,
bulk action slot, export request slot and pagination. Export is a request to an
application/API service; the UI does not query a database or construct a SQL
filter.

## Feature path map

| Feature | API path family |
|---|---|
| Users / roles / tenants | `/api/v1/users`, `/roles`, `/tenants` |
| Notifications | `/api/v1/notifications/*` |
| Audit | `/api/v1/platform/audit-events` (cursor pagination) |
| Project intelligence | `/api/v1/projects/{projectId}/intelligence/*` |
| Projects / tasks / documents / reports | feature service contracts under `src/features/`; exact backend resources are versioned independently |

The Phase 17 intelligence surface is consumed by
`src/features/intelligence/intelligenceService.ts`:

- `GET .../intelligence/` overview
- `POST .../intelligence/analyze/`
- `POST .../intelligence/reanalyze/`
- `POST .../intelligence/context/build/`
- state, architecture, dependencies, insights, recommendations, context,
  changes and resume read models

## Upload contract

`ApiClient.upload` is the only file transport. It uses `XMLHttpRequest` behind
the transport boundary to expose progress and cancellation, adds the same
central auth and tenant headers and parses the standard envelope. File type,
size, progress, success, error and retry/cancel affordances belong to the
component/application workflow; storage keys are never accepted from the user.

## Real-time contract

The optional `RealtimeClient` accepts a configured WebSocket URL and emits a
versioned event envelope:

```json
{
  "eventId": "...",
  "eventType": "NotificationCreated",
  "timestamp": "2026-09-06T12:00:00Z",
  "payload": {}
}
```

The adapter handles reconnect backoff and status only. Notification, task,
job and AI business decisions remain in application/feature services.

## Background job state

Long operations are rendered as `queued`, `running`, `completed` or `failed`
with progress where the backend supplies it. The GUI never performs heavy
analysis in the browser or blocks an HTTP request for project intelligence,
report generation or AI processing.
