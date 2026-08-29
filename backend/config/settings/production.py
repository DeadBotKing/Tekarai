"""Production settings — hardened, fail-closed.

Policy (Phase 01 · docs/Phases/Phase1.md §14):
- DEBUG is always False.
- SECRET_KEY and ALLOWED_HOSTS are mandatory and must come from the environment.
- Known development/testing key values are rejected.
- Only SQL Server (dbEngine=mssql) is permitted.
- Transport security (TLS redirect, HSTS, secure cookies) is on by default.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.environment import assertProductionDatabase, buildDatabaseConfig

from .base import *  # noqa: F401,F403 — standard Django settings inheritance
from .base import env

# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------
environment = "production"

# ---------------------------------------------------------------------------
# DJANGO / SECURITY — fail-closed configuration
# ---------------------------------------------------------------------------
DEBUG = False  # hard rule: never overridable in production

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("SECRET_KEY is required in the production environment.")
_FORBIDDEN_KEY_VALUES = {
    "tekarai-insecure-testing-key",
    "change-me",
    "changeme",
}
if SECRET_KEY.strip().lower() in _FORBIDDEN_KEY_VALUES:
    raise ImproperlyConfigured(
        "SECRET_KEY carries a known development/testing value. "
        "Provide a real secret from the secret manager."
    )

ALLOWED_HOSTS = env("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty in the production environment.")

CSRF_TRUSTED_ORIGINS = env("csrfTrustedOrigins")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        "csrfTrustedOrigins must be configured in the production environment."
    )

CORS_ALLOWED_ORIGINS = env("corsAllowedOrigins")
if not CORS_ALLOWED_ORIGINS:
    raise ImproperlyConfigured("corsAllowedOrigins must be an explicit allow-list in production.")

# ---------------------------------------------------------------------------
# DATABASE — SQL Server only
# ---------------------------------------------------------------------------
_productionDbEngine = env("dbEngine", default="mssql")
assertProductionDatabase(_productionDbEngine)

DATABASES = {
    "default": buildDatabaseConfig(
        dbEngine=_productionDbEngine,
        dbName=env("dbName"),
        dbUser=env("dbUser"),
        dbPassword=env("dbPassword"),
        dbHost=env("dbHost"),
        dbPort=env("dbPort", default="1433"),
        dbConnTimeout=env("dbConnTimeout", default="30"),
        dbEncrypt=env("dbEncrypt", default="true"),
        odbcDriver=env("odbcDriver", default="ODBC Driver 18 for SQL Server"),
        connMaxAge=env("dbConnMaxAge", default="60"),
    )
}

# ---------------------------------------------------------------------------
# TRANSPORT SECURITY
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = env("secureSslRedirect", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env("secureHstsSeconds", default=31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
