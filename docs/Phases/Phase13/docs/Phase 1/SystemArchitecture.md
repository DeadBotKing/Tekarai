# Tekarai Architecture Skeleton

Based on Phase 2 documentation and ADR-001.

## Layers
- Client (Web / Mobile / Desktop)
- API Layer (REST / WebSocket) — Phase 6
- Application Layer (Commands / Queries / Use Cases) — Phase 6
- Domain Layer (Entities / Rules / Value Objects / Domain Services / Events) — Phase 3 / Phase 6
- Infrastructure Layer (Repositories / ORM / External APIs) — Phase 6
- SQL Server / Redis — Phase 4 / Phase 19 / Phase 15

## Key Principles
- Clean Architecture (dependencies point inward)
- Domain-Driven Design (bounded contexts from Phase 3 — 20 contexts)
- Multi-Tenant Isolation (Tenant entity from Phase 4)
- Security First (Phase 8 / Phase 7 / Phase 1 rules)
- AI Native (ADR-009 — Phase 13 / Phase 16 / Phase 17)
- Extension / Plugin Strategy (ADR-010)
- API First (ADR-005)
- Event Driven (ADR-006)
- Offline Ready (ADR-016)
