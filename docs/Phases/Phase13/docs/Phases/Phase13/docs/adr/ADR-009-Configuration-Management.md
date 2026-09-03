# ADR-009 — Configuration Management

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

The platform must run identically across development, testing and production
with no source changes. Secrets must never live in source control. The same
configurable product serves multiple tenants and industries.

## Decision

1. **Environment-driven configuration**: all runtime values come from
   environment variables / `.env` (loaded by `django-environ`), categorized as
   APPLICATION, DATABASE, SECURITY, DJANGO, LOGGING, CACHE, EMAIL, STORAGE,
   CORS, JWT, EXTERNAL SERVICES (Phase 01 §6; template:
   `backend/.env.example`).
2. **Split settings modules**: `config/settings/{base,development,testing,
   production}.py` — never one locked file (Phase 01 §5).
3. Parsing and validation live in one tested module:
   `config/environment.py`.
4. Production is fail-closed: `SECRET_KEY`, `ALLOWED_HOSTS`,
   `csrfTrustedOrigins`, `corsAllowedOrigins` and full SQL Server database
   configuration are mandatory; missing values abort startup.
5. Naming: framework-level names stay `UPPER_SNAKE_CASE`; project-specific
   configuration names are `camelCase` (ADR-001). Example: `SECRET_KEY` is
   framework-owned, `dbHost`/`jwtSigningKey` are project-owned.

## Alternatives

- **One settings file with if/else on an env flag** — rejected: the spec
  explicitly forbids locking environments into one file.
- **YAML/TOML config files loaded from the repo** — rejected: secrets creep
  into source control; weaker 12-factor compliance.
- **ALL-CAPS env names for everything** — rejected: violates the accepted
  camelCase naming decision for project-specific identifiers.

## Consequences

- Positive: identical code across environments; startup fails loudly on
  incomplete production configuration; configuration rules are unit-tested.
- Negative: contributors must copy `.env.example` → `.env` first (automated in
  `backend/scripts/setupEnvironment.*`).
