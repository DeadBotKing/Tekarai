# Phase 05 Report — Database Dictionary & Business Rules

**Spec:** `docs/Phases/Phase5.md` (§1–§83) · **Status:** COMPLETE
**Previous:** `phase04Report.md` · **Gate:** 143 tests OK · ruff/mypy clean ·
`makemigrations --check` no drift · **§82 respected** (no models/migrations).

---

## §80 completion criteria — 23/23

| # | Criterion | Where |
|---|---|---|
| 1 | Database Dictionary کامل | `docs/database/DatabaseDictionary.md` (195 entities, 3146 lines) |
| 2 | تمام Entityها Dictionary دارند | 195/195 headings, test-verified == FieldCatalog == EntityCatalog |
| 3 | تمام Fieldها تعریف شده | `FieldCatalog.md` (2330 lines; standard blocks documented once per kind) |
| 4 | Data Typeها | type column (uuid, varchar(n), nvarchar, datetime UTC, decimal(19,4), boolean, integer, json, enum(...)) |
| 5 | Nullable/Required | Required + Nullable columns per field |
| 6 | Defaultها | Default column (domain-logical only — BR-DAT-006) |
| 7 | Unique Rules | Unique column + `ConstraintCatalog.md` §4 (tenant-scoped) |
| 8 | FKها | FK column + `ConstraintCatalog.md` §3 |
| 9 | Indexها | Index column + `IndexCatalog.md` (§56 format, importance P1–P3) |
| 10 | Delete Policyها | `ConstraintCatalog.md` §3 register (soft delete default, 4 CASCADEs, SET_NULL audit, RESTRICT) |
| 11 | Tenant Rules | dictionary headers (GLOBAL/TENANT_SCOPED/HYBRID §9) + BR-TEN-001..005 |
| 12 | Audit Rules | BR-AUD-001..005 + Phase 04 `09AuditModel.md` |
| 13 | Soft Delete Rules | per-entity Soft deletable flag + RET-002 (90-day recycle purge) |
| 14 | State Machineها | `StateMachineCatalog.md` — 10 machines + secondary lifecycles |
| 15 | Business Ruleها با ID | `BusinessRuleCatalog.md` — 71 rules, BR-⟨CAT⟩-NNN |
| 16 | Security Rules | BR-SEC-001..004 (all CRITICAL) |
| 17 | Permission Rules | BR-PER-001..004 (action-based §42, scopes §43, 6 layers §44) |
| 18 | Error Codeها | `ErrorCodeCatalog.md` — 45+ stable codes incl. all 6 spec codes (§61 mapping noted) |
| 19 | Data Retention | `DataRetentionPolicy.md` — RET-001..020 + tenant knobs |
| 20 | Migration Strategy | `DatabaseMigrationStrategy.md` — versioned/reproducible/reviewable + expand→migrate→contract |
| 21 | Backup Strategy | `DatabaseBackupStrategy.md` — full/differential/log + RPO/RTO tiers |
| 22 | Recovery Strategy | restore drills (monthly PITR, quarterly, annual game-day) + rollback contracts |
| 23 | Traceability | §62 in every rule (Entity · Use case · Service · API · Test) + `README.md` §83 answerability map |

## §81 outputs — 12/12 files

DatabaseDictionary.md · EntityCatalog.md · FieldCatalog.md ·
BusinessRuleCatalog.md · ConstraintCatalog.md · IndexCatalog.md ·
StateMachineCatalog.md · ErrorCodeCatalog.md · DataRetentionPolicy.md ·
DatabaseMigrationStrategy.md · DatabaseBackupStrategy.md · DataGovernance.md
— all unnumbered per spec; Phase-04 numbered set (01–10) untouched and
test-protected.

## §83 final gate — answerability

For every entity the 27 questions resolve through the chain documented in
`docs/database/README.md` → "§83 answerability map" (identity/purpose →
EntityCatalog; fields/constraints/indexes → FieldCatalog+Constraint+Index
catalogs; who/permissions → BusinessRuleCatalog+machines; statuses/transitions
→ StateMachineCatalog; errors → ErrorCodeCatalog; retention/backup/restore →
retention+backup docs; testing → per-rule Trace bindings).

## Key decisions

1. **Single source dataset:** `tools/generatePhase5Catalogs.py` regenerates
   dictionary/entity/field catalogs from one dataset (195 entities × field
   specs) — no hand-patched generated tables.
2. **Rule inventory:** 71 rules / 12 categories (TEN SEC PER AUD DAT BR COM
   NOT WF AI INT PERF) / 15 CRITICAL — tenant isolation, authn, authz,
   audit are CRITICAL per §60.
3. **Machines:** Project · Task · Document · Workflow · Maintenance ·
   Notification · Integration (STARTED/SUCCESS/FAILED/RETRYING §39) · Device
   (lifecycle separated from derived ONLINE/OFFLINE — BR-DEV-001) · Call ·
   Meeting; terminal states append-only; notifications only as event-driven
   side effects (BR-NOT-001).
4. **Error naming:** spec codes mapped to prefixed stable codes
   (`TENANT_ACCESS_DENIED` as-is; `PERMISSION_DENIED`→`PERM_PERMISSION_DENIED`,
   `DUPLICATE_BUSINESS_CODE`→`DUP_BUSINESS_CODE`,
   `INVALID_STATE_TRANSITION`→`STATE_INVALID_TRANSITION`,
   `PROJECT_ALREADY_COMPLETED`→`STATE_PROJECT_ALREADY_COMPLETED`,
   `INVALID_WORKFLOW_TRANSITION`→`WF_INVALID_TRANSITION`) — documented in
   the catalog; aliasing policy defined (one release minimum).
5. **Filtered uniques** (one-active-membership etc.) with engine notes
   (PostgreSQL/SQL Server/MySQL 8 differences).
6. **§82 held:** design only — `testNoDjangoModelsOrMigrationsCreated`
   re-asserts core_apps has no models/migrations.

## Tests added (36) — `tests/architecture/testPhase5DatabaseArchitecture.py`

- Deliverable set: 12 files exist/substantial; Phase-04 numbered set intact;
  catalog ↔ dictionary ↔ field headings 195 == 195 == 195.
- Dictionary: standard blocks (BASE/APPEND/VOCAB); header attributes;
  9-column field rows; no snake_case fields (BR-DAT-001); version column.
- Rules: 12 categories present; ≥71 Severity/Enforcement/Trace lines; §60
  CRITICAL checks; inventory sums to 71.
- Machines: all 10 required; Actor/Perm/Guard/Effects columns; ≥10 diagrams;
  terminal-state error fragments.
- Constraints/indexes: sections; CASCADE ≤4; simple-only CHECKs; scoped
  uniques; §56 header incl. U/T legend; ≥50 documented entries with P1–P3;
  domain coverage.
- Errors/policies: 6 spec codes (alias-aware); code uniqueness; RET-001..020;
  expand→contract; full/differential/log + RPO/RTO; governance topics.
- Design-only: no models/migrations; unnumbered names; README §83 map.

**Result:** `Ran 143 tests … OK` (Phase 04 set: 107 → 143 total).

## Gate log

```
manage.py test --settings=config.settings.testing  → 143 OK
ruff format                                       → 1 file reformatted
ruff check .                                      → All checks passed
mypy .                                            → no issues in 28 files
makemigrations --check --dry-run                  → No changes detected
```

## Next

**PHASE 6 — DOMAIN IMPLEMENTATION ARCHITECTURE** (per §"NEXT PHASE"):
Django app boundaries, domain packages, entities, value objects, aggregates,
repositories, domain services, application services, commands, queries,
events, DTOs, DI, module boundaries — then controlled entry into real
implementation.
