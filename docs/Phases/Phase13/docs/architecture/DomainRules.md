# Tekarai — Domain Rules

**Status:** Authoritative (Phase 03 — Domain Architecture)
**Specification:** `docs/Phases/Phase3.md` §21 (Rules 01–15), §6–§10
**Relation to Phase 02:** RULES A–N (`DependencyRules.md`) remain binding;
this document adds domain-architecture granularity.

---

## 1. The 15 Domain Architecture Rules (spec §21)

| # | Rule (binding statement) | Enforcement |
|---|---|---|
| 01 | No domain depends on another domain's database schema | Architecture test (cross-context import scan) + review |
| 02 | No domain imports another domain's internal models | Architecture test (apps.<ctx>.domain/infrastructure import ban) |
| 03 | Cross-domain communication uses contracts or events only | Architecture test (application-only imports) + event catalogue review |
| 04 | No business rule inside views | Review + phase tests (RULE H, Phase 02) |
| 05 | No business rule inside serializers | Review + phase tests (RULE G) |
| 06 | No business rule inside signals | Review + code scan when signals appear |
| 07 | Infrastructure never enters the domain (domain stays pure) | Architecture test (RULES A–D) |
| 08 | AI never owns business truth | Design review vs ADR-013; aiJob classification invariant |
| 09 | Audit stays independent (append-only, no CRUD mixing) | Architecture test (no other context imports audit internals) + review |
| 10 | Tenant isolation designed from the start | ADR-012; tenantId invariant per tenant-owned aggregate; isolation tests from first business phase |
| 11 | External integration passes only through the Integration boundary | Architecture test (vendor import scan) + ADR-015 |
| 12 | Every aggregate enforces its own invariants | Aggregate review per implementing phase (catalog invariants) |
| 13 | Every event is versionable | Event envelope `version` field; catalogue discipline |
| 14 | Every sensitive operation is auditable | Use-case review; audit fields in envelope |
| 15 | No domain has direct database access to another domain's internals | Same mechanism as Rule 01/02 (no shared-table access) |

## 2. Concept Rules Summary

| Concept | Binding rule |
|---|---|
| Entity | stable UUID identity; never name-based identity (spec §7) |
| Aggregate | root + boundary + invariants; children not mutated externally; one aggregate per transaction (spec §6, §16) |
| Value Object | immutable · validated · side-effect free (spec §8) |
| Domain Event | explicit, camelCase, envelope with 8 mandatory fields, versionable (spec §9) |
| Domain Service | only for multi-entity rules (e.g. weighted score calculation); no general-purpose service dumps (spec §17) |
| Repository | domain owns the contract (`IProjectRepository`); infrastructure implements (`SqlServerProjectRepository`) (spec §18) |

## 3. Boundary Rules Summary

| Boundary | Rule |
|---|---|
| Tenant (spec §11) | every tenant-owned aggregate carries tenant context; no cross-tenant query without valid reason; enforced app/repo/db |
| Security (spec §12) | authorization = user + role + permission + policy + resource + tenant + org scope; `is_superuser` alone forbidden |
| AI (spec §19) | AI → review/decision → application command → domain; never AI → database update |
| Integration (spec §20) | external → integration adapter → integration application layer → domain command/event |
| Industry (spec §23) | no industry hard-coding in Core; packs/extensions carry industry behaviour |

## 4. Prohibitions Carried Forward (spec §26)

In Phase 03 (and until each implementing phase opens): no migrations, no
database tables, no APIs, no serializers, no views, no Django models, no
business logic bound to Django, no CRUD, no convenience FKs, no
database-without-domain-boundary design, no industry hard-coding, no
premature microservices.

## 5. Review Checklist (per implementing phase)

1. New entities/aggregates listed in `AggregateCatalog.md` with invariants.
2. New events in `DomainEvents.md` with envelope fields + version.
3. Dependencies still conform to `DomainDependencies.md` (no new edge
   without design note).
4. Tenant ownership marked per aggregate.
5. Domain layer imports zero frameworks (tests green).
