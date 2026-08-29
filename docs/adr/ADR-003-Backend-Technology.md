# ADR-003 — Backend Technology

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 01 — Foundation & Repository

## Context

The platform needs a mature, long-supported, security-maintained web
framework with an ORM, migrations, admin tooling, a REST ecosystem and
first-class Windows deployment support (the reference environment runs
Windows). The approved master specification fixes the baseline.

## Decision

1. Backend baseline: **Python 3.12+ · Django 6 · Django REST Framework**.
2. Supporting libraries (Phase 01 set, all pinned in `backend/requirements/`):
   `django-environ` (configuration), `django-cors-headers` (CORS allow-lists),
   `djangorestframework` (API layer foundation).
3. Production serving baseline on Windows: **Waitress** (`production.txt`).
   ASGI/Channels arrive with the Communication phase.
4. Quality tooling: `ruff` (lint + format), `mypy` (types), `coverage`
   (test measurement) — installed from `requirements/development.txt`.

## Alternatives

- **FastAPI / litestar** — rejected: weaker migration story for enterprise
  data models; the approved specification fixes Django.
- **Django 5 LTS** — rejected: the baseline targets Django 6.
- **gunicorn on Windows** — rejected: does not run natively on Windows;
  Waitress is the approved Windows baseline.

## Consequences

- Positive: batteries-included ORM/migrations/admin, huge ecosystem, long
  support horizon.
- Negative: Django's sync model constrains real-time features — mitigated by
  Channels/ASGI when the Communication phase begins.
- Any new dependency requires a documented reason (architectural, framework,
  security, infrastructure, business or operational — Phase 01 §7).
