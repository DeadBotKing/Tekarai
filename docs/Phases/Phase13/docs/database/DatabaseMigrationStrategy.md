# DatabaseMigrationStrategy.md — Phase 05 migration strategy

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §72, §78;
migration execution begins in Phase 06 (§82 — no migrations before Phase 5
approval).
**Laws (§72):** every schema change is (1) versioned, (2) reproducible,
(3) reviewable, (4) deployable without data loss. Pattern for live changes:
**expand → migrate → contract** (§78).

---

## 1 · Tooling & conventions (Phase 06 readiness)

- Django migration framework (`manage.py makemigrations` per app =
  bounded context); one migration per logical change set, reviewed in PR
  alongside the `BusinessRuleCatalog`/`ConstraintCatalog` rows it implements.
- Migration naming: `NNNN_short_purpose` auto-numbered per app; **never
  edit an applied migration** — corrections are new migrations.
- Every migration references: the constraint/index rows it creates
  (`ConstraintCatalog.md` / `IndexCatalog.md`) and the rules it enforces
  (traceability §62).
- Baseline: `0001_initial` of each domain app is generated **from this
  Phase 05 dictionary** and reviewed against `FieldCatalog.md` row by row.

## 2 · Expand → Migrate → Contract (§78)

| Stage | Rule | Example |
|---|---|---|
| 1 · Expand | Additive change only: new nullable column / new table / new index (CONCURRENTLY); old code keeps running | add `Task.estimateMinutes integer NULL` |
| 2 · Migrate | Backfill in batched jobs (never one giant UPDATE); dual-write/read window; validate counts + checksums | backfill from legacy field |
| 3 · Contract | Only after all app versions read the new shape: drop old column/index/constraint in a separate later deploy | drop legacy column |

**Forbidden without expand-migrate-contract:** renaming in place, type
narrowing, NOT NULL on populated column, dropping a column still read by any
deployed version. `NOT NULL` arrives as: expand nullable → backfill →
add CHECK-ish validation → contract to NOT NULL.

## 3 · Zero-downtime rules

1. Deploy schema (expand) **before** application code that uses it.
2. Application code must tolerate both shapes during the window
   (nullable reads, default writes).
3. Long backfills run as management commands with resumable batches
   (`--batch-size`, checkpoint table), not inside request paths.
4. Index creation on hot tables: `CREATE INDEX CONCURRENTLY` (PostgreSQL) /
  `ONLINE=ON` (SQL Server); never blocking builds on P1 tables
  (IndexCatalog importance).
5. FK additions: create NOT VALID → VALIDATE separately (PostgreSQL), or
  equivalent staged check.

## 4 · Data migrations vs schema migrations

- Schema migrations: structure only; reversible where possible
  (`reversibility` documented per operation; irreversible ops — drops,
  type narrowing — require explicit `RunPython.noop` reverse + sign-off).
- Data migrations: separate `RunPython` steps, idempotent (safe on re-run),
  tested with fixtures; reference-data seeds follow §73–§74 rules (stable
  codes, versioned fixture files, no secrets §75).

## 5 · Environments & pipeline

| Environment | Source of migrations | Gate |
|---|---|---|
| CI | applied on throwaway DB from scratch + on copy of prod snapshot | all tests + makemigrations --check (no drift) |
| Staging | rehearse the exact release train incl. backfills | timing measured, rollback rehearsed |
| Production | same artifact as staging | change ticket + review checklist |

- **Drift check in gate:** `makemigrations --check` must report no pending
  changes (already enforced in Phases 2–4 CI gate).
- **Rollback plan:** every release train documents forward-only contract;
  rollbacks restore previous app version against the **expanded** schema
  (contract never runs in the same train) — this is why contract is a
  separate deploy.

## 6 · Review checklist (per migration PR)

- [ ] Expands before contracts; contract in later deploy
- [ ] Reversible or irreversible-signoff attached
- [ ] Backfill batched + resumable + idempotent
- [ ] Index/Constraint catalog rows updated (BR-PERF-001, §62 trace)
- [ ] No data loss path (§72-3) — deletes only via explicit, reviewed
      RunPython with audit
- [ ] Tested: fresh install + upgraded copy + empty-table edge
- [ ] Performance note for hot tables (lock risk assessed)
