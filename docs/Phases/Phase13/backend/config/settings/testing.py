"""Testing settings — automated tests and CI only.

Policy (Phase 01 · docs/Phases/Phase1.md §12):
- Test configuration is independent from development and production.
- DEBUG stays False so tests observe production-like behaviour.
- SQLite keeps the suite hermetic; the SQL Server baseline is exercised by the
  integration environment of later phases (docs/adr/ADR-011.md).
- Fast password hasher keeps auth-related tests quick when Identity lands.
"""

from __future__ import annotations

from .base import *  # noqa: F401,F403 — standard Django settings inheritance
from .base import env

# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------
environment = "testing"

# ---------------------------------------------------------------------------
# DJANGO / SECURITY
# ---------------------------------------------------------------------------
DEBUG = False
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "testserver"])

# Deterministic, publicly-known, non-secret key. Production rejects it.
SECRET_KEY = env("SECRET_KEY", default="tekarai-insecure-testing-key")

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# ---------------------------------------------------------------------------
# DATABASE — hermetic test database
# ---------------------------------------------------------------------------
from config.environment import buildDatabaseConfig  # noqa: E402 — after base import

DATABASES = {
    "default": buildDatabaseConfig(
        dbEngine=env("dbEngine", default="sqlite"),
        dbName=env("dbName", default=":memory:"),
        dbUser=env("dbUser", default=""),
        dbPassword=env("dbPassword", default=""),
        dbHost=env("dbHost", default=""),
        dbPort=env("dbPort", default=""),
    )
}
