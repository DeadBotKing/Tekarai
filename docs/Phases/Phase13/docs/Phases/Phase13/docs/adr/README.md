# docs/adr — Architecture Decision Records

One global registry, stable numbers, append-only. Superseding a decision
requires a new ADR that references the old one.

## Registry

| ADR | Title | Phase |
|---|---|---|
| [ADR-001](ADR-001-Product-Architecture.md) | Product Architecture (camelCase naming, product-not-customer) | 01 |
| [ADR-002](ADR-002-Modular-Monolith.md) | Modular Monolith | 01 |
| [ADR-003](ADR-003-Backend-Technology.md) | Backend Technology (Python/Django/DRF/Waitress) | 01 |
| [ADR-004](ADR-004-Database-Technology.md) | Database Technology (SQL Server) | 01 |
| [ADR-005](ADR-005-API-First.md) | API First | 01 |
| [ADR-006](ADR-006-Domain-Driven-Design.md) | Domain Driven Design | 01 |
| [ADR-007](ADR-007-Clean-Architecture.md) | Clean Architecture | 01 |
| [ADR-008](ADR-008-Event-Driven-Architecture.md) | Event Driven Architecture | 01 |
| [ADR-009](ADR-009-Configuration-Management.md) | Configuration Management | 01 |
| [ADR-010](ADR-010-Security-Principles.md) | Security Principles | 01 |
| [ADR-011](ADR-011-Phase01-Environment-Decisions.md) | Phase 01 Environment Decisions (SQLite boundary, driver packaging, dev key bootstrap) | 01 |
| [ADR-012](ADR-012-Multi-Tenant-Architecture.md) | Multi-Tenant Architecture | 02 |
| [ADR-013](ADR-013-AI-Native-Architecture.md) | AI Native Architecture | 02 |
| [ADR-014](ADR-014-Extension-Plugin-Strategy.md) | Extension / Plugin Strategy | 02 |
| [ADR-015](ADR-015-Integration-Strategy.md) | Integration Strategy | 02 |
| [ADR-016](ADR-016-Observability-Strategy.md) | Observability Strategy | 02 |
| [ADR-017](ADR-017-Cloud-Ready-Strategy.md) | Cloud Ready Strategy | 02 |
| [ADR-018](ADR-018-Offline-Ready-Strategy.md) | Offline Ready Strategy | 02 |

## Phase 02 §38 Mapping (numbering reconciliation)

`docs/Phases/Phase2.md` §38 lists its required ADR topics with its own local
numbers. Phase 01 §10 already occupied several of those numbers with
different topics (a spec-level numbering collision). Per §38's own rule —
"if a decision was already recorded, do not create a contradictory ADR" —
Tekarai keeps **one global registry** instead of renumbering. Mapping:

| Phase 02 requires (local #) | Satisfied by |
|---|---|
| ADR-001 Enterprise Operations Platform | ADR-001 |
| ADR-002 Modular Monolith | ADR-002 |
| ADR-003 Clean Architecture | ADR-007 |
| ADR-004 Domain Driven Design | ADR-006 |
| ADR-005 API First | ADR-005 |
| ADR-006 Event Driven | ADR-008 |
| ADR-007 Multi-Tenant Architecture | **ADR-012** |
| ADR-008 Security First | ADR-010 |
| ADR-009 AI Native | **ADR-013** |
| ADR-010 Extension / Plugin | **ADR-014** |
| ADR-011 Database Strategy | ADR-004 (+ ADR-011 boundary) |
| ADR-012 Integration Strategy | **ADR-015** |
| ADR-013 Observability Strategy | **ADR-016** |
| ADR-014 Configuration Strategy | ADR-009 |
| ADR-015 Cloud Ready Strategy | **ADR-017** |
| ADR-016 Offline Ready Strategy | **ADR-018** |

All 16 required topics are covered; none contradicts a Phase 01 decision.
