"""Environment parsing helpers for Tekarai configuration.

This module is the single place that knows how raw environment values become
Django settings. It is intentionally framework-light so unit tests can verify
configuration rules without a full Django registry.

Phase 01 scope: application + database only. Later phases extend this module
with cache, email, storage and integration parsers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.exceptions import ImproperlyConfigured

# Backend root (backend/)
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

#: Engines supported by the platform. ``mssql`` is the system of record;
#: ``sqlite`` exists only for offline development and automated testing
#: (see docs/adr/ADR-011.md).
SUPPORTED_DB_ENGINES: dict[str, str] = {
    "mssql": "mssql_django",
    "sqlite": "django.db.backends.sqlite3",
}

#: Engines that are forbidden outside development/testing.
PRODUCTION_DB_ENGINES: frozenset[str] = frozenset({"mssql"})

#: Default ODBC driver used by the mssql-django backend.
DEFAULT_ODBC_DRIVER: str = "ODBC Driver 18 for SQL Server"


def resolveDbEngine(dbEngine: str) -> str:
    """Map a platform engine alias to a Django backend path.

    Raises ``ImproperlyConfigured`` for unknown aliases so a typo fails at
    startup instead of at first query.
    """
    normalizedEngine = (dbEngine or "").strip().lower()
    if normalizedEngine not in SUPPORTED_DB_ENGINES:
        allowed = ", ".join(sorted(SUPPORTED_DB_ENGINES))
        raise ImproperlyConfigured(
            f"Unsupported dbEngine '{dbEngine}'. Supported engines: {allowed}."
        )
    return SUPPORTED_DB_ENGINES[normalizedEngine]


def buildDatabaseConfig(
    dbEngine: str,
    dbName: str,
    *,
    dbUser: str = "",
    dbPassword: str = "",
    dbHost: str = "",
    dbPort: str = "",
    dbConnTimeout: str = "30",
    dbEncrypt: str = "true",
    odbcDriver: str = DEFAULT_ODBC_DRIVER,
    connMaxAge: str = "60",
) -> dict[str, Any]:
    """Build the Django ``DATABASES["default"]`` mapping from environment values.

    SQLite keeps the configuration minimal (offline development/tests only).
    SQL Server receives driver, encryption and timeout options explicitly so
    production behaviour is deterministic and documented.
    """
    enginePath = resolveDbEngine(dbEngine)

    if enginePath == SUPPORTED_DB_ENGINES["sqlite"]:
        databaseName = dbName.strip() or str(BASE_DIR / "db.sqlite3")
        return {
            "ENGINE": enginePath,
            "NAME": databaseName,
        }

    return {
        "ENGINE": enginePath,
        "NAME": dbName,
        "USER": dbUser,
        "PASSWORD": dbPassword,
        "HOST": dbHost,
        "PORT": dbPort or "1433",
        "CONN_MAX_AGE": _parseIntOrDefault(connMaxAge, 60, "dbConnTimeout"),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {
            "driver": odbcDriver or DEFAULT_ODBC_DRIVER,
            "encrypt": _parseBoolOrDefault(dbEncrypt, True, "dbEncrypt"),
            "connection_timeout": _parseIntOrDefault(dbConnTimeout, 30, "dbConnTimeout"),
        },
    }


def assertProductionDatabase(dbEngine: str) -> None:
    """Reject non-production database engines in the production environment."""
    normalizedEngine = (dbEngine or "").strip().lower()
    if normalizedEngine not in PRODUCTION_DB_ENGINES:
        raise ImproperlyConfigured(
            "The production environment only permits dbEngine='mssql'. "
            f"Got '{dbEngine}'. SQLite is allowed in development/testing only "
            "(docs/adr/ADR-011.md)."
        )


def _parseIntOrDefault(rawValue: str, defaultValue: int, settingName: str) -> int:
    try:
        return int(rawValue)
    except (TypeError, ValueError):
        _ = defaultValue
        raise ImproperlyConfigured(
            f"Configuration value '{settingName}' must be an integer, got '{rawValue}'."
        ) from None


def _parseBoolOrDefault(rawValue: str, defaultValue: bool, settingName: str) -> bool:
    if isinstance(rawValue, bool):
        return rawValue
    normalizedValue = str(rawValue).strip().lower()
    if normalizedValue in {"1", "true", "yes", "on"}:
        return True
    if normalizedValue in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(
        f"Configuration value '{settingName}' must be a boolean, got '{rawValue}'."
    )
