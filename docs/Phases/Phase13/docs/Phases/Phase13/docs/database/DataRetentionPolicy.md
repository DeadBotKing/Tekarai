# DataRetentionPolicy.md — Phase 05 retention policy

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §71;
deepens Phase 04 `10DataRetentionPolicy.md` (class assignment for all 195
entities) with rule mechanics.

**Classes (Phase 04):** **L** Long-lived (business lifetime) · **M**
Medium (operational, months–years) · **S** Short (transient, days–weeks) ·
**C** Compliance/forever (legal hold, no auto-delete).

---

## 1 · Retention rules by rule-ID

| Rule | Applies to | Policy |
|---|---|---|
| RET-001 · Audit forever | AuditEvent (C) | Never auto-deleted; archive tiering allowed; legal hold flag overrides any purge |
| RET-002 · Soft-delete window | all L soft-deleted rows | Hard-purge after 90 days in recycle state unless C |
| RET-003 · Session/token hygiene | Session, refresh tokens (S) | Purge expired after 30 days |
| RET-004 · Notification pruning | Notification + children (M) | Delivered+read older than 12 months pruned; unread/failure kept 24 months |
| RET-005 · Delivery detail pruning | NotificationDelivery (S) | Sent/delivered older than 90 days purged before parent pruning |
| RET-006 · Presence ephemeral | Presence (S) | DB row refreshed continuously; stale > 7 days purged (realtime source governs, BR-COM-007) |
| RET-007 · Telemetry rollup | DeviceTelemetry (S→M) | Raw points 90 days; daily aggregates kept 24 months |
| RET-008 · Heartbeat pruning | DeviceHeartbeat (S) | 90 days |
| RET-009 · Integration logs | IntegrationExecution/IntegrationError (M) | Success 90 days; failures 12 months (traceability §39) |
| RET-010 · Inbound event log | IntegrationEvent (M) | 12 months (idempotency window + audit) |
| RET-011 · Call metadata | VoiceCall/GroupCall (M) | 24 months (no audio stored — BR-COM-004) |
| RET-012 · Meeting artifacts | Meeting, MeetingRecording (M/C) | Metadata 24 months; recording binaries per tenant policy, default 12 months in object storage |
| RET-013 · Message retention | Message (M) | Tenant-configurable 24 months default; edit/delete tombstones follow BR-COM-003 |
| RET-014 · AI traces | AiRequest/AiResponse (M) | 24 months (explainability §38) unless compliance hold |
| RET-015 · Evaluation records | EvaluationCycle + scores (C or L per tenant) | Employment-law minimum (IR: 2–5 years after cycle close); default keep-forever |
| RET-016 · Employment history | Employment, EmployeeAssignment (C) | Statutory retention (personnel files), never auto-purged |
| RET-017 · Financial records | Invoice, Payment, ProjectBudget (C) | Tax-law retention 7–10 years; never auto-purged |
| RET-018 · Temporary uploads | Attachment pending-link (S) | 30 days unattached → purge binary + row |
| RET-019 · Tenant offboarding | all tenant-owned rows | Export → archive → purge via controlled CASCADE job (Phase 04 register); AuditEvent of purge itself is C |
| RET-020 · Workflow archive | WorkflowInstance completed (M) | 24 months then archive tier |

## 2 · Mechanics

- **Enforcement:** scheduled sweeper jobs (Phase 09 scheduling), each run
  audited (`DELETE` batch events with counts); no ad-hoc manual deletes.
- **Legal hold:** `AuditEvent.legalHold` / compliance flag on tenant blocks
  RET-002/004/013/020 for flagged scope.
- **Order:** children before parents; CASCADE-registered relations purge
  atomically inside the tenant purge job only.
- **Backups are not retention:** deleted-in-DB data may persist in backups
  until backup rotation (§`DatabaseBackupStrategy.md`) — documented for
  GDPR Article 17 responses: erasure = DB purge + backup expiry notice.
- **Class per entity:** authoritative table in Phase 04
  `10DataRetentionPolicy.md` (all 195 rows); conflicts resolve to the
  stricter class.

## 3 · Tenant-configurable knobs (§74 reference-data style)

| Knob | Default | Range |
|---|---|---|
| `retention.notificationsMonths` | 12 | 3–36 |
| `retention.messagesMonths` | 24 | 1–60 |
| `retention.telemetryDays` | 90 | 30–365 |
| `retention.integrationLogsDays` | 90 | 30–400 |
| `retention.recycleBinDays` | 90 | 7–365 |

Knobs are SystemSetting/TenantSetting entries with validation ranges —
never hard-coded constants (§74).
