# ADR-020 — In-house OpenAPI builder (registry-driven)

**Status:** Accepted (Phase 06) · **Context:** Phase 06 §24/DoD-14 requires
"OpenAPI قابل تولید" — an OpenAPI document must be generatable from the
architecture.

## Decision

Endpoints register an `EndpointSpec` (method, path, auth, permission,
request/response examples, error codes, pagination/filtering/sorting flags,
idempotency, rate-limit scope) in a shared-kernel registry at URL-module
import time. `buildOpenApiDocument()` renders the registry as an
OpenAPI **3.1.0** document served at `/api/v1/openapi.json`, plus a
human-readable `/api/v1/docs`. Architecture tests assert registry coverage.

## Consequences

- Zero new dependencies; the document and the §32 checklist stay in sync
  (tests compare registry against routes and error catalog codes).
- Examples are curated per endpoint (contract clarity over exhaustiveness).
- When request/response schemas must be auto-derived at scale (Phase 07+),
  `drf-spectacular` can render the same routes; the registry remains the
  documentation source of truth and the diff gate.

## Alternatives rejected

- **drf-spectacular now** — heavier contract than the current curated
  surface justifies; would also silently drift from the spec's §32 field
  list which the registry makes explicit.
