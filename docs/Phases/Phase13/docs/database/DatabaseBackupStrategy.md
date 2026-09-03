# DatabaseBackupStrategy.md — Phase 05 backup & recovery

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §76–§77.
**Laws (§76):** backup program covers full, differential and transaction-log
backups; recovery objectives defined per tier (§77 RPO/RTO) and tested by
restore rehearsal, not by assumption.

---

## 1 · Backup scheme

| Type | What | Frequency | Retention | Notes |
|---|---|---|---|---|
| Full | complete database cluster | weekly (Sunday) | 6 weeks | base for differentials |
| Differential | changes since last full | daily | 3 weeks | restore = full + latest diff |
| Transaction log | WAL / log shipping | continuous (≤5 min) | 14 days | point-in-time recovery (PITR) |
| Snapshot (pre-release) | storage snapshot before each migration train | per release | 2 releases | expand-migrate safety net |
| Object storage (files) | versioned buckets / cross-region replication | continuous | bucket lifecycle 90 versions | attachments, recordings (§40) |

Configuration store (secret manager) backed up separately with restricted
access; **secrets never inside database backups unencrypted** (BR-SEC-003) —
backups are encrypted at rest (AES-256) with keys in KMS, rotation quarterly.

## 2 · RPO / RTO by tier (§77)

| Tier | Scope | RPO | RTO | Strategy |
|---|---|---|---|---|
| T0 Platform | Tenant, SystemSetting, Identity, Subscriptions | ≤ 5 min | ≤ 1 h | synchronous/async replica + log shipping; failover runbook |
| T1 Business-critical | Projects, Tasks, Documents (meta), Workflows, Evaluations | ≤ 15 min | ≤ 4 h | PITR from log chain |
| T2 Operational | Messages, Notifications, Maintenance, Assets, Integrations, AI traces | ≤ 1 h | ≤ 8 h | diff + log restore |
| T3 Ephemeral | Presence, DeviceTelemetry raw, heartbeats | ≤ 24 h (best effort) | ≤ 24 h | rebuildable from source/re-aggregation; raw loss acceptable (RET-006/007/008) |

Tenant-facing SLA derives from tier of the tenant plan (Subscription) —
documented per plan in Phase 10 (billing).

## 3 · Restore & rehearsal

1. **Monthly restore drill (staging):** full + latest diff + log roll-forward
   to a random timestamp; row counts + checksums compared to source
   (checksum fixture: per-table `count + max(updatedAt)` + sampled md5).
2. **Quarterly PITR drill:** point-in-time to minute precision for T0/T1.
3. **Annual game-day:** total region loss → restore from cross-region copy;
   measured RTO compared to table above; gaps become tickets.
4. Every drill produces a report (date, duration, verified tables, RPO/RTO
   measured vs target) stored under `docs/development/` ops folder.

## 4 · Operational rules

- Backups run on replicas where available (no full backup on primary during
  peak).
- Access: backup artifacts readable only by ops role (GLOBAL scope §43);
  restores are audited (`AuditEvent.action = EXPORT`-class op) and require
  two-person approval in production.
- Retention vs erasure: GDPR erasure requests mark DB purge; backup copies
  age out per §1 retention — the erasure response documents the expiry
  window (see `DataRetentionPolicy.md` §2).
- Monitoring: failed backup job = P1 incident (alerting Phase 09); success
  metrics shipped to observability stack.

## 5 · Responsibility split (deployment shapes)

| Shape | DB backups | Object storage | Drills |
|---|---|---|---|
| Self-hosted | ops runbook (pgBackRest / native tools) | rsync/restic to second site | monthly |
| Managed DB (RDS/Azure SQL/Cloud SQL) | service automated + our config (window, retention, PITR window) | provider versioning + replication | monthly (restore into scratch) |
| Single-tenant on-prem | appliance schedule + offsite copy | NAS replication | quarterly |

The strategy document is engine-agnostic; the concrete tool choice is fixed
per deployment in the environment dossier (Phase 10).
