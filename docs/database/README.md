# docs/database — Phase 04 Deliverables (Enterprise ERD & Database Architecture)

**Status:** DESIGN PHASE — no Django models/migrations exist (spec §52).
**Specification:** `docs/Phases/Phase4.md`
**Next phase:** Phase 05 deepens this set into the full field-level
Database Dictionary + Business Rules.

## Deliverables (spec §50)

| File | Content |
|---|---|
| `01EnterpriseERD.md` | enterprise ERD (tenant spine, cross-domain map), cross-cutting rules: PK, base entity, soft delete, money, time, JSON, file storage, custom fields, status model, temporal data, normalization, concurrency, transaction boundary, DB security |
| `02DomainERD.md` | per-domain ER diagrams (Mermaid `erDiagram`) for all 19 Phase-04 entity groups |
| `03DatabaseDictionary.md` | architecture-level dictionary: purpose + key field groups per entity (field-level detail = Phase 05) |
| `04EntityCatalog.md` | the §51 catalog — all ~195 entities × 17 required attributes |
| `05RelationshipCatalog.md` | every FK: owner, dependent, cardinality, delete behavior, tenant scope; M↔N resolution entities |
| `06IndexStrategy.md` | index rules, standard composites (`tenantId + …`), per-domain justified indexes |
| `07ConstraintCatalog.md` | unique / check / enum (controlled vocabulary) constraints, tenant-aware |
| `08TenancyModel.md` | tenant entity, tenant-owned marking, isolation layers, tenant-aware constraints & indexes |
| `09AuditModel.md` | AuditEvent structure, base-entity audit fields, append-only rules |
| `10DataRetentionPolicy.md` | retention class per domain/entity |

## Domain naming reconciliation (Phase 03 ↔ Phase 04)

Phase 04 (spec §8–28) groups entities in 19 buckets; Phase 03 refined the
platform into 20 bounded contexts. Binding ownership = **Phase 03 contexts**
(`docs/architecture/BoundedContexts.md`). Mapping used throughout this set:

| Phase 04 group | Owning context(s) |
|---|---|
| Platform Core (§9) | Platform Core (primitives) · Tenancy (Tenant) · Configuration (settings/flags/lookups) |
| Identity (§10) | Identity |
| Organization (§11) | Organization |
| HR (§12) | Workforce — except evaluation entities → **Performance** |
| Project / Task / Asset / Device / Maintenance / Document / Workflow / Communication / Notification / Audit (§13–22) | same-named contexts |
| Reporting + Analytics (§23–24) | Reporting/Analytics context |
| AI (§25) | AI |
| Integration (§26) | Integration |
| WinCC (§28) | **Industry Extension — NOT Core** (ADR-014/015) |
