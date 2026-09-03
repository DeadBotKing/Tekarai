# ADR-010 — Security Principles

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

Security is part of the architecture, not a later feature (Master
Specification §2.9). The foundation phase must already establish the baseline
that later phases inherit.

## Decision

1. **Secret management**: no secrets in source control; `.env` is git-ignored
   (verified by `tests/architecture/test_repositoryHygiene.py`); production
   reads from environment/secret manager only.
2. **Fail-closed production**: `DEBUG=False` forced; `SECRET_KEY`,
   `ALLOWED_HOSTS`, CSRF origins and CORS allow-list mandatory; known
   development/testing key values rejected at import.
3. **Headers and cookies from day one**: `X-Frame-Options: DENY`,
   `SECURE_CONTENT_TYPE_NOSNIFF`, referrer policy, HttpOnly cookies; HSTS,
   SSL redirect and secure cookies in production.
4. **CORS as explicit allow-list** — never `*` in production.
5. **Least information**: error contracts never leak stack traces or database
   internals; health endpoints report engine labels, never credentials.
6. Authentication/authorization arrive with the Identity phase (Phase 7);
   Phase 01 implements no auth (forbidden list §23).

## Alternatives

- **Add security hardening just before release** — rejected: retrofitting
  security into a live platform is where leaks happen.
- **Permissive dev defaults in base settings** — rejected: unsafe defaults
  propagate to every environment; defaults live in the per-environment
  modules instead.

## Consequences

- Positive: every later phase inherits a hardened baseline; violations are
  caught by architecture tests, not by audits.
- Negative: cookie/CSRF details (e.g. `CSRF_COOKIE_HTTPONLY` interaction with
  the SPA) must be revisited in the GUI phase — recorded as an open point in
  ADR-011.
