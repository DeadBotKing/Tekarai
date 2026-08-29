"""Development settings — local machines only.

Policy (Phase 01):
- DEBUG defaults to True for local ergonomics, overridable via environment.
- SECRET_KEY: taken from the environment when provided; otherwise a random
  ephemeral key is generated per process. An ephemeral key is acceptable ONLY
  here — production rejects it (see production.py).
- SQLite is the offline default; set dbEngine=mssql to develop against a real
  SQL Server instance.
"""

from __future__ import annotations

import secrets

from .base import *  # noqa: F401,F403 — standard Django settings inheritance
from .base import env

# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------
environment = "development"

# ---------------------------------------------------------------------------
# DJANGO / SECURITY
# ---------------------------------------------------------------------------
DEBUG = env("DEBUG", default=True)
ALLOWED_HOSTS = env("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

providedSecretKey = env("SECRET_KEY", default="")
if providedSecretKey:
    SECRET_KEY = providedSecretKey
else:
    # Ephemeral, process-local development key. Never a production value.
    SECRET_KEY = secrets.token_urlsafe(64)

# ---------------------------------------------------------------------------
# CORS — local development origins
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env(
    "corsAllowedOrigins",
    default=["http://localhost:3000", "http://127.0.0.1:3000"],
)

# ---------------------------------------------------------------------------
# DATABASE — offline default; switch with dbEngine=mssql + credentials
# ---------------------------------------------------------------------------
from config.environment import buildDatabaseConfig  # noqa: E402 — after base import

DATABASES = {
    "default": buildDatabaseConfig(
        dbEngine=env("dbEngine", default="sqlite"),
        dbName=env("dbName", default=""),
        dbUser=env("dbUser", default=""),
        dbPassword=env("dbPassword", default=""),
        dbHost=env("dbHost", default="localhost"),
        dbPort=env("dbPort", default="1433"),
        dbConnTimeout=env("dbConnTimeout", default="30"),
        dbEncrypt=env("dbEncrypt", default="true"),
        odbcDriver=env("odbcDriver", default="ODBC Driver 18 for SQL Server"),
        connMaxAge=env("dbConnMaxAge", default="0"),
    )
}
