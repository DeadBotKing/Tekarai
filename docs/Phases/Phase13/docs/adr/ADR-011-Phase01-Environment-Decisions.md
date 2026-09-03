# ADR-011 — Phase 01 Environment & Boundary Decisions

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Executing Phase 01 against the specification required four concrete decisions
the documents leave open: (a) where health-check code lives, (b) how tests run
without a SQL Server instance, (c) how the SQL Server driver dependency is
packaged, and (d) how the development SECRET_KEY bootstrap works without
hard-coding a secret.

## Decision

1. **Health check placement**: health endpoints are framework-level
   infrastructure and live in `config/healthCheck.py` (not a Django app —
   creating an app for two read-only endpoints would add structure without
   need; apps/ stays empty per §23). They contain no business logic (§17).
2. **SQLite boundary**: `dbEngine=sqlite` is allowed **only** in development
   and testing. Production rejects it at import (`assertProductionDatabase`).
   SQLite exists so the foundation is runnable offline and the test suite is
   hermetic; SQL Server remains the only system of record (ADR-004). CI runs
   the gate on sqlite; the integration environment for SQL Server arrives with
   the database phases.
3. **Driver packaging**: `mssql-django`/`pyodbc`/`waitress` live in
   `requirements/production.txt`, not base — machines that never touch SQL
   Server (frontend contributors, lint-only CI jobs) stay installable, and
   the production install stays explicit.
4. **Development SECRET_KEY bootstrap**: `development.py` generates a random
   ephemeral key per process when the environment provides none. This is not
   a secret in the security sense — production rejects empty and known
   placeholder keys outright.
5. **Revisit points**: CSRF_COOKIE_HTTPONLY vs SPA token flows (GUI phase);
   JSON log format (operations phase); SQL Server CI service container
   (database phases).

## Alternatives

- **Run Phase 01 tests against a real SQL Server in CI** — deferred: no
  business schema exists yet to exercise; adds heavy infrastructure to a phase
  whose gate is structural.
- **Put mssql drivers in base requirements** — rejected: unnecessary install
  weight and ODBC system dependencies for non-database contributors.
- **A hard-coded development SECRET_KEY** — rejected: violates "no hard-coded
  secrets" and would risk leaking into production configurations.

## Consequences

- Positive: out-of-the-box runnable foundation (`manage.py check` works with
  zero configuration), hermetic tests, explicit production install.
- Negative: two-engine configuration must stay contained in
  `buildDatabaseConfig` — enforced by unit tests for both engines.
- Any change to the sqlite boundary requires superseding this ADR.
