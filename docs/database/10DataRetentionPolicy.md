# 10 — Data Retention Policy

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §5, §48
Classes: **L** long-term (years, compliance-grade) · **M** medium (months) ·
**S** short (days/weeks, transient) · **C** configurable per tenant (spec:
Telemetry configurable). Retention is enforced by scheduled purge/archive
jobs (implementation phase); **audit and compliance holds override purge**
(Legal-Hold concept arrives with the Communication/Notification phases).

---

## 1. Per-Domain Retention (matches `04EntityCatalog.md` Ret column)

| Domain | Class | Notes |
|---|---|---|
| Audit | **L** | append-only; legal/compliance hold; never casually deletable (spec §48) |
| Documents (metadata/versions) | **L** | versions immutable; retention per tenant policy; legal hold override |
| Tenancy / Identity core records | **L** | soft delete preserves; closed tenants retained per policy |
| Workforce / Employment history | **L** | labour-law compliance horizon |
| Performance evaluations | **L** | every score change audited + retained |
| Projects / Tasks (roots) | **L** (soft-deleted: M→archive) | operational history |
| Task comments / time entries / activity | **M** | archive then purge |
| Communication messages | **M/L per tenant policy** | retention policy entity arrives with Communication phase (Phase 11 concept `messageRetentionDays`); recording retention flagged |
| Presence / typing / receipts | **S** | transient by nature (presence cache-first) |
| Notifications (root + recipients) | **S/M** | spec §48: temporary notifications short-term |
| Notification deliveries (attempts) | **S/M** | delivery troubleshooting window |
| Sessions / security events | sessions **S/M** (purge expired) · security events **L** | security telemetry retained |
| Device telemetry / heartbeats / WinCC tag values | **C** | spec §48: configurable; partition/purge design (06 §5) |
| Analytics values / snapshots | **C** | rebuildable; keep per reporting window |
| AI conversations/messages | **S/M** | privacy-sensitive; classification records **M** |
| AI requests/responses | **M** | governance/cost analysis window |
| Integration events/executions/errors | **M** | duplicate-delivery window + troubleshooting |
| Report outputs | **M** | re-generatable |
| Attachments (binary) | follows owner class | object-storage lifecycle mirrors owner retention |

## 2. Rules

1. Nothing is hard-deleted before its class horizon; soft delete is the
   default end state (spec §5).
2. Purge jobs are tenant-aware, audited, and idempotent.
3. Legal/compliance hold suspends purge for held scopes (documented
   extension point; Communication phase formalizes).
4. Personal-data horizons (employee privacy) follow the most restrictive
   applicable law — Workforce phase defines per-field rules.
5. Retention changes are configuration (tenant policy) where class = C;
   L-class horizons are platform policy, not tenant-erasable.

## 3. Before Production (spec §48)

Per-domain retention values must be confirmed with compliance before the
deployment phase; this document fixes the classes and the mechanism.
