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

---

# Phase 05 deliverables (authoritative, unnumbered set)

Spec: `docs/Phases/Phase5.md` (§63–§81). The Phase-04 numbered documents
above remain as design history; the unnumbered set below is the
**authoritative dictionary + rules layer** referenced by Phase 06.

| File | Content |
|---|---|
| `DatabaseDictionary.md` | full dictionary: all 195 entities, per-entity header (domain, owner, tenancy mode, soft delete, audit, kind, business identity, state machine, retention) + business-field tables + standard field blocks |
| `EntityCatalog.md` | one-row-per-entity quick index (195 rows) |
| `FieldCatalog.md` | every business field: name · type · required · nullable · default · unique · index · FK · description |
| `BusinessRuleCatalog.md` | 71 rules with IDs (BR-TEN/SEC/PER/AUD/DAT/…), severity, enforcement, traceability (§58–§62) |
| `ConstraintCatalog.md` | PK / FK+delete behavior / tenant-scoped uniques / CHECKs (simple only §55) / vocabularies / engine notes |
| `IndexCatalog.md` | §56-format catalogue: name · table · columns · unique · purpose · expected query · tenant-scoped · importance |
| `StateMachineCatalog.md` | 10 machines (Project, Task, Document, Workflow, Maintenance, Notification, Integration, Device, Call, Meeting) + secondary lifecycles |
| `ErrorCodeCatalog.md` | stable unique error codes with HTTP mapping, cause, client action |
| `DataRetentionPolicy.md` | RET-001..020 rules, tenant-configurable knobs, GDPR/backup interplay |
| `DatabaseMigrationStrategy.md` | versioned/reproducible/reviewable changes, expand→migrate→contract (§72/§78) |
| `DatabaseBackupStrategy.md` | full/differential/log backups, RPO/RTO tiers, restore drills (§76–§77) |
| `DataGovernance.md` | reference data, seed integrity (§75), environment isolation, quality policies (§79) |

`tools/generatePhase5Catalogs.py` regenerates the first three files from the
single dataset — edit the dataset, never hand-patch generated tables.

## §83 answerability map (final gate)

For any entity, the 27 questions of §83 are answered by this chain:

| Question group | Answered in |
|---|---|
| what/why/owner/tenant/PK/business identity | `EntityCatalog.md` + `DatabaseDictionary.md` headers |
| fields/required/nullable/default/constraints/indexes/relationships | `FieldCatalog.md` + `ConstraintCatalog.md` + `IndexCatalog.md` |
| who can create/update/delete · permissions | `BusinessRuleCatalog.md` (SEC/PER) + machine tables (Actor/Perm columns) |
| statuses · transitions | `StateMachineCatalog.md` |
| business rules | `BusinessRuleCatalog.md` (rule IDs searchable per entity in Trace lines) |
| audits | `BusinessRuleCatalog.md` (AUD) + Phase 04 `09AuditModel.md` |
| possible errors | `ErrorCodeCatalog.md` |
| retention · backup · restore | `DataRetentionPolicy.md` + `DatabaseBackupStrategy.md` |
| how tested | Phase 06+ test bindings in each rule's Trace line + `tests/architecture/` |

**Implementation status:** §82 respected — no Django models/migrations were
created in Phase 05.
