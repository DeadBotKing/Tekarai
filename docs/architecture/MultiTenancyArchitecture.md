# Tekarai — Multi-Tenancy Architecture

**Status:** Authoritative (Phase 02 — Architecture & ADRs)
**Related ADRs:** ADR-012 (decisive), ADR-010
**Enforced from:** the first business-data phase (Platform Core/Identity).

---

## 1. Tenant Isolation Diagram (Phase 02 §20–21)

```mermaid
flowchart TB
    subgraph REQUEST["Authenticated Request"]
        PRINCIPAL["Principal (Identity)"]
    end
    RESOLVER["Tenant / Membership Resolution\n(identity → membership → tenant)"]
    CTX["Tenant Context\n(tenant · user · org context · roles · permissions)\nexplicit object — not a global variable"]
    GATE["Use Case Guard\n('no tenant context → refuse')"]
    REPO["Tenant-Scoped Repository\n(every query filtered by tenantId)"]
    subgraph DB[("SQL Server — shared schema")]
        ROWS["rows WHERE tenantId = context.tenant"]
    end
    PRINCIPAL --> RESOLVER --> CTX --> GATE --> REPO --> ROWS
    CROSS["Cross-tenant request"] -.->|"denied by default\n(explicit audited admin paths only)"| GATE
```

## 2. Model

- **Single database, shared schema, row-level tenancy** (ADR-012): every
  tenant-owned aggregate carries `tenantId`; repositories scope every read
  and write.
- Tenant is the top-level isolation boundary; organizations, units and
  departments live **inside** a tenant.
- A user may belong to multiple tenants (membership model — Identity/
  Organization phases), but every request executes in exactly **one** tenant
  context.

## 3. Isolation Across Layers

| Layer | Obligation |
|---|---|
| API | Tenant derived from authenticated principal; client-supplied tenant IDs are never the sole basis |
| Application | Tenant context required before any tenant-scoped use case |
| Domain | Aggregates tenant-aware where applicable |
| Persistence | Repositories filter by `tenantId`; uniqueness is tenant-scoped (`UNIQUE(tenantId, code)`) |
| Authorization | Cross-tenant operations denied by default; explicit platform-admin capabilities must be audited |
| Events | Events carry tenant context; consumers stay tenant-scoped |

## 4. Rules

1. Tenant filtering must never depend on the frontend.
2. `Tenant Context` is passed explicitly (request-scoped object); it is not a
   module-level global (Phase 02 §21).
3. Any new tenant-owned entity must state tenancy in its design (Phase 4/5
   catalogues enforce per entity).
4. Administrative cross-tenant operations are explicit, permissioned and
   audited.
5. Caches and read models key by tenant; cache invalidation respects tenant
   boundaries.

## 5. Test Strategy (from the first business phase)

- Isolation test per repository: tenant A write → tenant B read must miss.
- Uniqueness tests prove tenant-scoped constraints.
- API-level tests prove client-supplied tenant IDs cannot switch scope.
- These become mandatory DoD items for every tenant-owned aggregate.
