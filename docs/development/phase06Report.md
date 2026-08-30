# Phase 06 Report — API Architecture & Application Layer

**Spec:** `docs/Phases/Phase6.md` (§1–§35) · **Status:** COMPLETE
**Architecture doc:** `docs/api/APIArchitecture.md` · **ADRs:** 019, 020, 021
**Gate:** **235 tests OK** · ruff clean · mypy clean (161 files) ·
`makemigrations --check` no drift · **no new dependencies**.

Phase 06 is the first **implementing** phase: it builds the application/API
backbone plus two exemplar bounded contexts (Tenancy, Identity) end-to-end
through all four layers — the spine §35 demands for every later context.

---

## §32 required outputs — 27/27

| # | Output | Where |
|---|---|---|
| 1 | Application Architecture | `apps/*/application` + `useCase.py` 8-step template (§8) |
| 2 | Command Architecture | `application/commands/*` frozen dataclasses (§5) |
| 3 | Query Architecture | `application/queries/*` (§6) |
| 4 | Use Case Architecture | 12 use cases across Tenancy/Identity (§4 list covered) |
| 5 | DTO Architecture | `application/dto/*` — no logic, dataclasses (§7) |
| 6 | Repository Contracts | Protocols in `domain/repositories` (§10) |
| 7 | Repository Implementations | `infrastructure/repositories` (ORM, tenant-scoped) |
| 8 | Application Services | containers, TenantDirectory facade (§11) |
| 9 | Domain Services Boundary | `PermissionEvaluator` pure domain; hashers/verifiers behind ports |
| 10 | API Architecture | `presentation/api` per context + shared kernel |
| 11 | API Versioning | `/api/v1/` only; RULE K enforced |
| 12 | Standard Response Contract | envelope `{success,data,meta,errors}` everywhere (§14) |
| 13 | Exception Architecture | `domain/errors.py` + `tekraiExceptionHandler` (§15) |
| 14 | Authentication Architecture | opaque rotating tokens + SessionVerifier port (ADR-019, §16) |
| 15 | Authorization Architecture | action codes + scopes + evaluator (RBAC, §17) |
| 16 | Multi-Tenant Enforcement | 4 layers: context, use case, repository, schema (§18) |
| 17 | Audit Integration | `AuditEventModel` §19 fields + use-case audit step |
| 18 | Correlation ID | middleware → context → audit/logs/envelope (§25) |
| 19 | Idempotency Strategy | `Idempotency-Key` mixin, cache store (§20) |
| 20 | Pagination | page/pageSize + keyset cursor (§21) |
| 21 | Filtering | whitelist filters (§22) |
| 22 | Searching | `search` on declared fields (§22) |
| 23 | Sorting | whitelist ordering, unknown → 422 (§22) |
| 24 | Rate Limiting Architecture | settings policies + cache limiter (§23) |
| 25 | OpenAPI Architecture | registry → `/api/v1/openapi.json` + `/docs` (ADR-020, §24) |
| 26 | Testing Architecture | unit/application/integration/architecture suites (§29) |
| 27 | Logging Architecture | `TekaraiJsonFormatter` §30 fields (§30) |

## §33 Definition of Done — 15/15

1. **API runs no business logic** — views orchestrate serializer→command→use
   case→envelope; ORM in presentation is test-forbidden
   (`testPresentationContainsNoOrmCalls`).
2. **Use cases HTTP-independent** — application layer imports zero Django/DRF
   (`testApplicationLayerIsFrameworkFree`).
3. **Domain Django-free** — Phase-02 RULES A–D scans, now active on real
   contexts.
4. **Repository contracts exist** — Protocols in domain.
5. **Infrastructure implements them** — 4 Django repositories.
6. **AuthN ≠ AuthZ** — `SessionVerifier` vs `PermissionGate` ports, separate
   modules; login requires no permission.
7. **Tenant isolation enforced** — 4 layers; integration tests prove
   403 `TENANT_ACCESS_DENIED`, 404 no-leak, GLOBAL crossing.
8. **Responses standard** — envelope tests on success + error paths.
9. **Exception mapping standard** — single handler; stable codes from
   ErrorCodeCatalog.
10. **Audit attachable to use cases** — `UseCase.audit` (in-transaction) +
    failed-login audit outside the rolled-back transaction.
11. **Correlation ID through the flow** — middleware → audit rows → logs →
    envelope → response header (tested end-to-end).
12. **API versioning** — `/api/v1/` (+ RULE K scan).
13. **Test architecture** — 4 categories; 235 total (was 143).
14. **OpenAPI generatable** — `/api/v1/openapi.json` (3.1.0) with all v1
    endpoints, tested.
15. **Architecture documented** — `docs/api/APIArchitecture.md` + ADR-019/020/021.

## What was built

```
backend/apps/
├── sharedKernel/   domain(errors, entities, events, VOs) · application(messaging,
│                   requestContext, useCase, ports, auditStream) ·
│                   presentation/api(response, exceptionHandler, pagination,
│                   filtering, middleware, authentication, permissions,
│                   idempotency, rateLimiting, openapi, platformRoutes) ·
│                   infrastructure(models=AuditEvent, djangoPorts, auditStream,
│                   rateLimiter, loggingSetup, wiring)
├── tenancy/        Tenant aggregate + state machine + 4 use cases + API
└── identity/       User/Session/TenantMembership aggregates, PermissionEvaluator,
                    8 use cases, 8 models, authN/authz services, bootstrap command
```

API v1 surface: `auth/login|refresh|logout` · `me` · `users` (+`{id}`,
+`{id}/memberships`) · `tenants` (+`{id}`, +`{id}/status`) ·
`platform/overview` · `platform/audit-events` (cursor) · `openapi.json` ·
`docs`.

## Deliberate guard evolutions (documented, never silent)

- `testNoBusinessDomains` → opening register (tenancy/identity opened by
  Phase 06; models/migrations confined to infrastructure; INSTALLED_APPS
  allowlist extended).
- Phase 2 RULE E/F tests → Shared Kernel exception + application-facade
  composition (ADR-021).
- Phase 3/4 emptiness guards → structure/placement guards.
- Naming conventions → framework hook + Django-migration file exemptions.

## Key runtime decisions

- **Opaque rotating session tokens** (ADR-019) — hashed at rest, 8h TTL,
  rotation, revocation; JWT later behind the same port.
- **Failed-login audit survives rollback** (security beats §9 atomicity for
  LOGIN failures — implemented via post-transaction audit in
  `AuthenticateUserUseCase`).
- **Cross-tenant detail reads answer 404 without existence leak**; cross-tenant
  list override answers 403 `TENANT_ACCESS_DENIED`; GLOBAL grants cross.
- **Role scopes fixed**: platformAdmin=GLOBAL, tenantAdmin/member=TENANT
  (grants inherit the role's scope — evaluator enforces §43).
- **bootstrapPlatform** management command seeds tenant `platform`,
  permission catalogue (§73/§74 stable codes), three roles and the admin
  account from environment variables only (§75: no secrets in code).

## Gate log

```
manage.py test --settings=config.settings.testing   → 235 OK
ruff check .                                        → All checks passed
mypy .                                              → no issues in 161 files
makemigrations --check --dry-run                    → No changes detected
```

## Run locally (Windows PowerShell)

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\backend
.\venv\Scripts\Activate.ps1
$env:DJANGO_SETTINGS_MODULE="config.settings.development"
$env:PLATFORM_ADMIN_PASSWORD="Your-Strong-Pass-2026!"
python manage.py migrate
python manage.py bootstrapPlatform
python manage.py runserver
# API: http://127.0.0.1:8000/api/v1/docs
python manage.py test --settings=config.settings.testing
```

## Next — PHASE 7 (per spec ordering)

Organization context (departments/positions) on this spine, then the
remaining contexts — each arriving as `apps/<ctx>/{domain,application,
infrastructure,presentation}` without touching the kernel contracts.
