# Tekarai — Domain Architecture

**Status:** Authoritative (Phase 03 — Domain Architecture; design only)
**Specification:** `docs/Phases/Phase3.md`
**Companion documents:** `BoundedContexts.md` (the 20 contexts) ·
`DomainMap.md` (visual map) · `DomainDependencies.md` (graph + rules) ·
`AggregateCatalog.md` (aggregates & invariants) · `DomainEvents.md`
(event envelope & catalogue) · `ValueObjectCatalog.md` (value objects) ·
`DomainRules.md` (the 15 rules).
**Phase 02 open questions resolved here:** see §12.

> Phase 03 is **planning/design only** (spec header): no models, migrations,
> APIs, serializers, views or CRUD are created in this phase (spec §26).

---

## 1. Purpose

By the end of Phase 03, one glance answers (spec §27): which domains exist,
what each owns, their aggregates, the events they produce, their
dependencies (both directions), which data may leave a boundary, which must
not — and how this architecture becomes the Phase 04 Enterprise ERD.

## 2. Architectural Principle (spec §2)

Tekarai is a **Modular Monolith** applying DDD · Clean Architecture · SOLID ·
Bounded Contexts · Aggregates · Domain Events · Application/Domain Services ·
Repository Pattern · Dependency Inversion.

The prime directive: **the business domain does not depend on Django.**
Django is infrastructure/delivery. Business rules never live in: views,
serializers, URLs, Django admin, `Model.save()`, signals or HTTP handlers.

Layer direction (spec §5): `Presentation → Application → Domain ←
Infrastructure`. Between bounded contexts, a direct dependency is allowed
**only** when it is an explicit architectural contract; the default is
`Domain A → Domain Event → Event Bus → Domain B` (see
`DomainDependencies.md`).

## 3. Domain Classification (spec §3)

| Class | Meaning | Contexts |
|---|---|---|
| **Generic Subdomain** | exists in nearly every enterprise platform; never industry-specific | Identity · Tenancy · Notification · Audit · Configuration · Platform Core · Integration (mechanism) |
| **Supporting Subdomain** | important but not the core differentiator | Documents · Reporting/Analytics · Dashboard · Communication · Device Management · Integration (connectors) · Maintenance |
| **Core Domain** | the main product value; extensible and AI-enableable | Organization Management · Workforce Management · Performance Management · Project Operations · Task Operations · Workflow · AI Intelligence · Enterprise Operations Intelligence |

(Per-context classification table with justification: `DomainMap.md` §2.)

## 4. Domain Concepts — Binding Rules

| Concept | Rule (spec) | Detail |
|---|---|---|
| **Entity** | stable identity; UUID primary identifier; identity never based on name | `AggregateCatalog.md` §2 |
| **Aggregate** | root + explicit boundary + own invariants; children never mutated from outside; transaction boundary = aggregate boundary | `AggregateCatalog.md` §3 (worked example: PerformanceEvaluation) |
| **Value Object** | immutable · validated · side-effect free; no independent identity | `ValueObjectCatalog.md` |
| **Domain Event** | explicit business facts; envelope carries eventId, eventType, aggregateId, tenantId, occurredAt, correlationId, actorId, version; versionable | `DomainEvents.md` §2 |
| **Domain Service** | only for rules that belong to no single entity/aggregate (e.g. `performanceScoreCalculationService`); never a general-purpose service dump | §7 below |
| **Repository** | contract belongs to the domain (`IProjectRepository`); infrastructure implements (`SqlServerProjectRepository`); domain never sees QuerySets | §8 below |

**Naming standard (per ADR-001):** domain identifiers, events and functions
are **camelCase** (`taskAssigned`, `performanceScoreCalculationService`).
PascalCase event names in specification examples are conceptual; the binding
project standard is camelCase.

## 5. Business Logic Placement (spec §15)

```
BAD:   View → Model.save() → business logic scattered
GOOD:  API → Application Command → Domain Aggregate → Domain Event
           → Repository (port) → Infrastructure
```

Business logic → Domain layer. Orchestration → Application layer. Database
access → Infrastructure. HTTP → Presentation.

## 6. Transaction Rule (spec §16)

Transaction boundary aligns with **aggregate boundary**. No oversized
transactions; a business operation must not lock multiple aggregates/contexts
in one database transaction without reason. Cross-domain operations use
**eventual consistency** via events wherever business rules allow.

## 7. Domain Service Rule (spec §17)

A domain service exists only when a business rule spans entities/aggregates
and belongs to neither (example: weighted score calculation across
evaluators). If the logic belongs to one aggregate, it lives inside that
aggregate/domain object. Domain services must not become general-purpose
"manager services" (DevelopmentRules §6).

## 8. Repository Rule (spec §18)

```
Domain:          IProjectRepository (contract, pure Python)
Infrastructure:  SqlServerProjectRepository (Django ORM implementation)
```

Application depends on the contract; infrastructure binds it (dependency
inversion). The domain layer never imports the ORM.

## 9. Boundaries

- **Tenant boundary (spec §11):** every tenant-owned aggregate carries tenant
  context; no query may read another tenant's data without a valid reason;
  isolation enforced in application, repository and database layers
  (ADR-012).
- **Security boundary (spec §12):** authorization evaluates user, role,
  permission, policy, resource, tenant and organization scope —
  `if user.is_superuser` alone is forbidden.
- **AI boundary (spec §19):** AI never mutates business entities directly;
  path is always `AI recommendation → review/decision → application command
  → domain`. AI never owns business truth (ADR-013).
- **Integration boundary (spec §20):** external systems (WinCC, ERP, MES,
  email, SMS, external storage) reach the domain only through
  `Integration Adapter → Integration Application Layer → Domain
  Command/Event` (ADR-015).

## 10. Domain vs Django App (spec §13–14)

A Django app is not automatically a domain — but in the modular monolith
each bounded context maps to one module under `apps/` with the standard
internal layout:

```
apps/<context>/
├── domain/          entities/ · valueObjects/ · aggregates/ · events/
│                    services/ · repositories/ (contracts) · exceptions/
├── application/     commands/ · queries/ · services/ · dto/ · handlers/
├── infrastructure/  persistence/ · repositories/ (impl) · integrations/
└── presentation/    api/ · serializers/ · views/
```

The 20 module names are fixed in `BoundedContexts.md` §1. Creating any of
them is **not** part of Phase 03 (spec §26) — they arrive with their
implementation phases.

## 11. Industry Extension Strategy (spec §23)

Tekarai Core is industry-neutral. Pharmaceutical, manufacturing,
construction, oil & gas, retail, healthcare and technology needs are served
by Industry Packs on top of the Core (`Tekarai Core + Pharmaceutical Pack`).
**WinCC is an Integration/Industry Extension, never Core** (ADR-014/015).

## 12. Phase 02 Open Questions — Resolutions

| Open question (phase02Report) | Resolution in Phase 03 |
|---|---|
| Performance engine placement (Analytics vs own context) | **Own context:** `PERFORMANCE` (Context 05) owns cycles/evaluations/scores; `REPORTING/ANALYTICS` (Context 16) stays projection/read-model oriented |
| Documents ↔ Workflow integration shape | **Event-triggered application contract:** Documents emits `documentSubmitted`; Workflow's application layer starts a generic instance via its public contract. No domain↔domain import; final fields decided in their phases |
| Roadmap reconciliation (ExecutionGuide vs Phases) | Still open — a Phase 04 decision item (ADR candidate) |

## 13. From Domain Architecture to Enterprise ERD (spec §27)

Phase 04 converts this design mechanically:

| Domain concept | Phase 04 ERD rule |
|---|---|
| Entity / Aggregate Root | table with UUID primary key |
| Aggregate child entity | owned table with FK to root + cascade rules per Phase 04 §31 |
| Value Object | column set (e.g. `amount`+`currency`) or JSON column with validation — never an independent identity |
| Cross-context reference | FK **or** loose `uuid` reference where contract requires decoupling (per dependency matrix) |
| Tenant-owned aggregate | `tenantId` column + tenant-scoped uniqueness |
| Lifecycle | `createdAt/updatedAt/deletedAt/isActive` base fields |
| Domain event | outbox/audit table owned by producer context |

No table may exist in Phase 04 without a bounded-context owner and an
aggregate in `AggregateCatalog.md` — "database design without domain
boundary" is forbidden (spec §26).

## 14. Microservice Extraction Path (spec §25)

The monolith is intentional (ADR-002), but boundaries must stay
extraction-ready. Candidate contexts and their triggers:

| Context | Extraction trigger | Kept extractable by |
|---|---|---|
| Communication | persistent WebSocket/SFU scale | signalling contracts + events only; no shared tables |
| Notification | high-volume delivery workers | consumes events; own tables |
| Analytics/Reporting | heavy read load | projection/read models fed by events |
| AI | GPU-bound inference | port/adapter isolation (ADR-013) |
| Integration | protocol connectors & isolation | adapters behind contracts (ADR-015) |

Extraction precondition (all contexts): event-only integration, no
cross-context database access, versioned contracts — exactly the rules in
`DomainDependencies.md` and `DomainRules.md`.
