# Tekarai API & Application Architecture — Phase 06

**Status:** IMPLEMENTED (Phase 06) · **Spec:** `docs/Phases/Phase6.md` (§1–§35)
**Decisions:** ADR-019 (session tokens) · ADR-020 (OpenAPI builder) · ADR-021 (Shared Kernel)
**Enforcement:** `backend/tests/architecture/testPhase6ApplicationArchitecture.py` (37 tests)

---

## 1 · Layering (§1–§3)

```
Client → API (presentation) → Application (use cases) → Domain → Infrastructure → DB/External
```

| Layer | Location | May import | Never imports |
|---|---|---|---|
| Domain | `apps/<ctx>/domain` | stdlib + sharedKernel.domain | Django, DRF, HTTP, siblings (RULES A–D) |
| Application | `apps/<ctx>/application` | own domain + sharedKernel.application ports | Django, DRF, ORM (test-enforced) |
| Infrastructure | `apps/<ctx>/infrastructure` | own domain + own/other **application** facades + framework | other contexts' non-public layers |
| Presentation | `apps/<ctx>/presentation/api` | own application + own container + sharedKernel.presentation | ORM (test-enforced), own domain |

The **Shared Kernel** (`apps/sharedKernel`) is the one package every layer may
import (ADR-021): errors, entities/events/value-object primitives, ports,
request context, envelope, middleware, pagination, filtering, idempotency,
rate limiting, OpenAPI, audit stream, structured logging.

## 2 · Structure (§27)

Every context ships `domain/{entities,valueObjects,services,events,repositories,exceptions}`,
`application/{commands,queries,useCases,dto,services}`,
`infrastructure/{models,repositories,services,migrations}` (migrations via
`MIGRATION_MODULES`), `presentation/api/{serializers,views,urls,permissions}`.
Django models live ONLY in infrastructure; migrations ONLY under
`infrastructure/migrations` — mechanically enforced.

## 3 · Use cases (§4–§9)

`apps/sharedKernel/application/useCase.py` encodes the eight canonical steps:
validate → authorize (action-based, via PermissionGate) → business rules →
entity → persist → events (post-commit) → audit (in-transaction) → DTO.
The transaction boundary is the application layer (`UnitOfWork` port →
`transaction.atomic`). Failed **security** audits (e.g. failed login) are
written outside the rolled-back transaction (§19 vs §9 — implemented in
`AuthenticateUserUseCase.execute`).

Implemented exemplar use cases: CreateTenant, GetTenant, ListTenants,
ChangeTenantStatus (state machine), CreateUser, AssignUserToTenant,
AuthenticateUser, RefreshSession, Logout, GetUser, ListUsers,
GetCurrentAccount.

## 4 · Repositories (§10)

Contracts = `typing.Protocol` in `domain/repositories` (selectors carry
tenant scope: `getById(userId, tenantId)` — BR-TEN-001/§10). Implementations
in `infrastructure/repositories` map aggregates ↔ models; IntegrityError →
`DuplicateBusinessCodeError`/`DuplicateIdentifierError` for stable codes.

## 5 · Services (§11)

- Domain services (pure): `PermissionEvaluator` (deny-wins, GLOBAL/TENANT
  scopes, module wildcards, fail-closed).
- Application services: `TenantDirectory` (public cross-context facade,
  RULE F), permission catalogue.
- Infrastructure services: `PasswordHasherDjango`, `SessionVerifierDjango`,
  `PermissionGateDjango`, audit stream reader.

## 6 · API contract (§12–§15)

- Versioning: everything under `/api/v1/` (§13); RULE K forbids unversioned
  `api/` strings.
- Envelope (§14): `{success, data, meta, errors}` — success and error, one
  shape everywhere; `meta.correlationId` always present.
- Errors (§15): `apps/sharedKernel/domain/errors.py` hierarchy with stable
  codes from `docs/database/ErrorCodeCatalog.md`; mapped to HTTP by
  `tekraiExceptionHandler` — the ONLY place exceptions become HTTP.
  Serializer validation → `VALIDATION_ERROR` + `field` (Phase 06 §14).

## 7 · AuthN / AuthZ / Tenancy (§16–§18)

- AuthN (§16): opaque rotating bearer tokens (SHA-256 at rest) via
  `SessionVerifier` port — ADR-019; JWT provider can replace the port
  implementation without touching views. Service accounts/agents plug into
  the same port later.
- AuthZ (§17): action-based codes (`user.create`, `tenant.list`, §42 of
  Phase 5) evaluated by the domain `PermissionEvaluator` through the
  `PermissionGate` port; roles carry GLOBAL/TENANT scopes; explicit
  allow/deny user grants (BR-PER-003). `is_staff`/`is_superuser` never used.
- Tenancy (§18): enforced at four layers — request-context binding,
  use-case boundary checks (`TENANT_ACCESS_DENIED`), repository scoping
  (cross-tenant reads answer 404 without existence leak), and scoped
  uniqueness constraints in the schema.

## 8 · Cross-cutting (§19–§25)

- Audit (§19): `AuditEventModel` with the full §19 field set
  (actor/tenant/action/resource/resourceId/timestamp/ip/userAgent/before/
  after/correlationId/requestId); append-only; cursor-paginated stream at
  `/api/v1/platform/audit-events` behind `audit.view`.
- Idempotency (§20): `Idempotency-Key` header; fingerprint =
  actor+tenant+key+path+body-hash; replay returns the stored response with
  `Idempotency-Replayed: true` (cache-backed port).
- Pagination (§21): `page`/`pageSize` (≤100) with `meta.pagination`;
  keyset cursors (`cursor`) for append-only streams — audit stream uses the
  `DjangoAuditStreamReader` keyset implementation.
- Filtering/Sorting/Searching (§22): whitelist-driven (`SafeQueryFilter`;
  repository sort whitelists; unknown sort field → `SYS_VALIDATION_FAILED`).
- Rate limiting (§23): policies in settings (`auth:login` 5/min,
  `auth:refresh` 30/min); cache-backed fixed window; 429 +
  `SYS_RATE_LIMITED` + `Retry-After`.
- OpenAPI (§24): `/api/v1/openapi.json` (3.1.0) + `/api/v1/docs` from the
  endpoint registry (ADR-020); every endpoint documents method, auth,
  permission, request/response examples, error codes, pagination/filtering.
- Correlation ID (§25): `CorrelationContextMiddleware` mints or adopts
  `X-Correlation-ID`, binds context (actor/tenant/ip/UA), echoes on every
  response, flows into use cases, audit rows, logs and the envelope.

## 9 · Request lifecycle (§26)

middleware(correlation+context) → authentication (session → principal,
context enrichment) → permission (action gate) → view → serializer (input
shape) → command/query → use case (8 steps, UoW) → domain → repository →
DB → DTO → envelope → response (+correlation headers).

## 10 · Django's role (§28)

Django = ORM/migrations/HTTP/middleware/settings only (ADR-003/007);
business architecture never imports it above infrastructure. Password
hashing uses Django hashers behind the domain `PasswordHasher` port.

## 11 · Testing (§29) & Logging (§30)

- `tests/unit` (domain, 25) · `tests/application` (use cases + repos +
  authz + isolation, 12) · `tests/integration` (API contract, 28) ·
  `tests/architecture` (all structural rules). Total gate: 235.
- `TekaraiJsonFormatter` emits the §30 field set (timestamp, level,
  service, module, operation, actor, tenant, correlationId, requestId,
  message, exception) — wired as the root console formatter.

## 12 · Security checklist (§31)

Input validation (serializers + command validation + domain VOs) ·
authentication (hashed opaque tokens, rotation, revocation) ·
authorization (server-side, six layers) · tenant isolation (4 layers) ·
CSRF/CORS (Phase 01 settings) · rate limiting · secure headers (nosniff,
DENY, referrer-policy) · secret management (env-only; nothing in code) ·
password hashing (Django hashers + policy) · token rotation (refresh) ·
audit logging · SQL-injection safety (parameterized ORM lookups only) ·
mass-assignment protection (explicit serializer fields only; commands are
allow-lists). File upload restrictions arrive with the Documents context.

## 13 · Composition (§34) & current surface (§35)

Settings + `apps.sharedKernel.infrastructure.wiring` bind ports; per-context
`infrastructure/container.py` assembles use cases; views stay dumb. The
foundation now hosts: `auth/login|refresh|logout`, `me`, `users` (+detail,
+memberships), `tenants` (+detail, +status), `platform/overview`,
`platform/audit-events`, `openapi.json`, `docs` — the spine every later
context (Organization, HR, Projects, …) plugs into without architectural
changes.
