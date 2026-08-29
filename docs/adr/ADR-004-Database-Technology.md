# ADR-004 — Database Technology

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

The reference enterprise environment standardizes on Microsoft SQL Server
(Windows infrastructure). The approved master specification names SQL Server
as the initial system of record.

## Decision

1. System of record: **Microsoft SQL Server** via `mssql-django` + `pyodbc`
   (ODBC Driver 18, encryption on by default).
2. Database credentials come exclusively from environment variables
   (`dbHost`, `dbPort`, `dbName`, `dbUser`, `dbPassword`, ...).
3. The production settings module **rejects any engine other than mssql**
   (enforced by `config.environment.assertProductionDatabase` and covered by
   architecture tests).
4. SQLite is permitted **only** for offline development and hermetic test
   execution (see ADR-011 for the exact boundary).
5. UUID primary keys, soft delete and tenant-aware uniqueness arrive with the
   ERD/database phases (Phase 4/5/19) — nothing is pre-implemented in Phase 01.

## Alternatives

- **PostgreSQL** — strong technical fit, but rejected: does not match the
  approved enterprise baseline.
- **SQL Server everywhere including developer laptops** — rejected for Phase 01:
  forces every contributor to run a database server; SQLite keeps the
  foundation runnable offline (ADR-011 records the trade-off).

## Consequences

- Positive: enterprise-compatible system of record with deterministic
  production configuration.
- Negative: engine duality (mssql/sqlite) must stay contained in
  `config.environment.buildDatabaseConfig` — one function, tested.
- Risk watch: mssql-django/Django 6 compatibility on ASGI paths is an open
  question for the Communication phase (tracked in docs/ANALYSIS.md).
