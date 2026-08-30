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
