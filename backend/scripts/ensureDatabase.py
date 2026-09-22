#!/usr/bin/env python
"""ensureDatabase — create the Tekarai SQL Server database if it is missing.

Used by run_dev.ps1 / run_dev.sh before the first ``migrate`` so that the
one-command developer flow works against a fresh SQL Express install.

Reads connection settings from environment variables (same names the Django
settings understand):
    dbServer   -> HOST  (e.g. ``localhost\\SQLEXPRESS`` or ``localhost``)
    dbPort     -> PORT  (empty for named instances)
    dbName     -> database to ensure (default ``Tekarai``)
    dbUser     -> SQL login (empty => Windows integrated auth)
    dbPassword -> SQL login password
    odbcDriver -> explicit driver name (empty => auto-detect)
    dbExtraParams -> extra ODBC connection-string fragments (e.g.
                     ``TrustServerCertificate=yes;Encrypt=no``)

On success it prints the chosen driver as ``DRIVER=<name>`` so the caller can
reuse it for the Django process. Exit codes: 0 = ok, 1 = driver missing,
2 = connection failed, 3 = database name invalid.
"""

from __future__ import annotations

import os
import re
import sys

CANDIDATE_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]


def detectDriver(preferred: str) -> str:
    if preferred:
        return preferred
    try:
        import pyodbc

        available = [d for d in pyodbc.drivers()]
        for candidate in CANDIDATE_DRIVERS:
            if candidate in available:
                return candidate
        if available:
            print(f"available drivers: {', '.join(available)}", file=sys.stderr)
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"pyodbc import failed: {exc}", file=sys.stderr)
        sys.exit(1)
    return ""


def sanitizeDatabaseName(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_\- ]{1,128}", name or ""):
        return ""
    return name


def buildConnString(driver: str, host: str, port: str, database: str) -> str:
    server = host or "localhost"
    if port and "\\" not in server:
        server = f"{server},{port}"
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}", f"DATABASE={database}"]
    user = os.environ.get("dbUser", "")
    password = os.environ.get("dbPassword", "")
    if user:
        parts.append(f"UID={user}")
        parts.append(f"PWD={password}")
    else:
        parts.append("Trusted_Connection=yes")
    extra = os.environ.get("dbExtraParams", "")
    if extra:
        parts.append(extra)
    return ";".join(parts)


def main() -> int:
    dbName = sanitizeDatabaseName(os.environ.get("dbName", "Tekarai"))
    if not dbName:
        print("dbName contains unsupported characters (allowed: A-Z a-z 0-9 _ - space).")
        return 3

    driver = detectDriver(os.environ.get("odbcDriver", ""))
    if not driver:
        print(
            "No SQL Server ODBC driver found. Install 'ODBC Driver 18 for SQL Server':\n"
            "  https://aka.ms/downloadmsodbcsql",
            file=sys.stderr,
        )
        return 1

    host = os.environ.get("dbServer", os.environ.get("dbHost", "localhost"))
    port = os.environ.get("dbPort", "")
    connString = buildConnString(driver, host, port, "master")

    try:
        import pyodbc

        conn = pyodbc.connect(connString, autocommit=True, timeout=10)
    except Exception as exc:
        print(f"Could not connect to SQL Server ({host}). {exc}", file=sys.stderr)
        print("Hint: check the server name, authentication and the ODBC driver.", file=sys.stderr)
        return 2

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DB_ID(?)", dbName)
        row = cursor.fetchone()
        if row and row[0] is not None:
            print(f"database exists: {dbName}")
        else:
            cursor.execute(f"CREATE DATABASE [{dbName}]")
            print(f"database created: {dbName}")
    except Exception as exc:
        print(f"Could not create database '{dbName}'. {exc}", file=sys.stderr)
        print(
            "Hint: the login needs CREATE DATABASE permission. You can also create "
            "the database manually in SSMS and re-run.",
            file=sys.stderr,
        )
        return 2
    finally:
        conn.close()

    # Announce the driver so run_dev.ps1 / run_dev.sh can reuse it.
    print(f"DRIVER={driver}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
