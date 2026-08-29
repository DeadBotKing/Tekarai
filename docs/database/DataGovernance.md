# DataGovernance.md — Phase 05 data governance

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §73–§75,
§79 (quality), plus cross-cutting §62 traceability.
**Definition (§79):** governance = reference data management, seed data
integrity, production data isolation, and data quality policies.

---

## 1 · Reference data management (§73)

- Reference data = controlled vocabularies and platform catalogues
  (SystemSetting defaults, Permission catalogue, LookupType/LookupValue
  families, vocabulary entities: TaskStatus, TaskPriority, DocumentType,
  AssetCategory, SkillCategory, Certification, Location, AiProvider, …).
- **Separated from transactional data:** vocab tables are never mixed into
  business tables; business rows FK to vocab (BR-DAT-012 closure).
- **Stable codes (§74):** every reference row has an immutable `code`
  (never reassigned, never renamed meaning); display names are localizable;
  migrations may add rows, never silently change codes.
- Change process: add proposal (row + purpose) → review → fixture update →
  release note. Deprecation uses `isActive=false` + successor code, not
  deletion.

## 2 · Seed data integrity (§75)

- Seeds ship as **versioned fixture files** per domain (checked into repo,
  reviewed like code); applied idempotently (upsert by stable code).
- **No real secrets, no real personal data in seeds (§75):** credentials are
  placeholder secret *references* (resolved from the environment in real
  deployments); demo persons are synthetic (clearly synthetic names).
- Seed application is a deploy step with audit (CREATE batch events).
- Test fixtures may use synthetic personal data only; production snapshots
  never used as fixtures.

## 3 · Production data isolation

- Environments (dev / staging / prod) are separate databases + separate
  object-storage buckets; no shared credentials; staging may receive
  **anonymized** copies only, via audited export job with approval.
- Copy prod → non-prod requires: ticket, approval, anonymization pass
  (names, emails, phones, tokens, secrets scrubbed), audit trail
  (`EXPORT` event §32).
- Developers never access production data directly; break-glass access is
  role-scoped (GLOBAL ops), time-boxed, audited, two-person rule (aligns
  with `DatabaseBackupStrategy.md` §4).

## 4 · Data quality policies (§79)

| Policy | Rule | Enforcement |
|---|---|---|
| QUAl-1 Completeness | Required fields non-null at rest (FieldCatalog Req=YES ↔ NOT NULL in Phase 06 models) | schema + makemigrations review |
| QUAL-2 Consistency | FK targets exist; tenant columns equal across FK chains (BR-TEN-003) | FK + isolation tests |
| QUAL-3 Uniqueness | scoped uniques enforced (ConstraintCatalog §4) | DB + `DUP_*` errors |
| QUAL-4 Validity | closed vocabularies + CHECK ranges (§55) | enums/FK/CHECK |
| QUAL-5 Accuracy | temporal invariants (dates ordered, weights 100%) | domain validation (§54) |
| QUAL-6 Timeliness | UTC everywhere; sync/async jobs SLA'd (Phase 09) | BR-DAT-010 + monitoring |
| QUAL-7 Traceability | every change attributable (audit) | BR-AUD-001..005 |
| QUAL-8 Currency | stale-flag policy data derived, not stored (device online) | BR-DEV-001 |

Quality dashboard (Phase 09+): per-domain counts of constraint violations
blocked, audit gaps, retention sweep status — KPI reviewed monthly.

## 5 · Ownership & stewardship

| Data domain | Steward (role) | Duties |
|---|---|---|
| Identity & Access | Security officer | permission catalogue, role scopes |
| Workforce | HR lead | employment vocabularies, evaluation retention |
| Projects | PMO lead | project/task vocabularies, portfolio quality |
| Documents | DMS owner | document types, retention classes |
| Assets & Maintenance | Maintenance lead | asset categories, work-order policies |
| Communication | Collaboration owner | retention knobs, consent policy |
| AI | AI governance owner | model catalogue, classification policy (§37) |
| Integrations | Integration owner | provider catalogue, credential rotation |
| Platform | Platform owner | tenants, settings, reference data process |

Stewards approve reference-data changes in their domain (§1 process) and
own retention knob defaults (DataRetentionPolicy §3).

## 6 · Compliance alignment

- Audit trail satisfies who/what/when/where/why (§32–§33, BR-AUD-003) for
  ISO 27001-style evidence and works-council requirements.
- Personal data: employee/user records carry retention classes (RET-015/
  016) and erasure flows (retention §2 GDPR note).
- AI records provide decision explainability (BR-AI-002) for audit review.
- Integration logs provide external-system evidence trail (BR-INT-002).
