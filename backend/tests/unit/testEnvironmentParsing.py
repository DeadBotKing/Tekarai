"""Unit tests for environment parsing (config.environment).

These tests verify configuration rules in isolation — no database, no client.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.environment import (
    DEFAULT_ODBC_DRIVER,
    assertProductionDatabase,
    buildDatabaseConfig,
    resolveDbEngine,
)


class ResolveDbEngineTests(SimpleTestCase):
    def testResolvesMssqlAlias(self) -> None:
        self.assertEqual(resolveDbEngine("mssql"), "mssql_django")

    def testResolvesSqliteAlias(self) -> None:
        self.assertEqual(resolveDbEngine("sqlite"), "django.db.backends.sqlite3")

    def testIsCaseInsensitive(self) -> None:
        self.assertEqual(resolveDbEngine("MSSQL"), "mssql_django")

    def testRejectsUnknownEngine(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            resolveDbEngine("postgres")

    def testRejectsEmptyEngine(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            resolveDbEngine("")


class BuildDatabaseConfigMssqlTests(SimpleTestCase):
    def testBuildsFullSqlServerConfig(self) -> None:
        config = buildDatabaseConfig(
            dbEngine="mssql",
            dbName="TekaraiCore",
            dbUser="tekarai",
            dbPassword="secret",
            dbHost="sql.example.com",
            dbPort="1433",
        )
        self.assertEqual(config["ENGINE"], "mssql_django")
        self.assertEqual(config["NAME"], "TekaraiCore")
        self.assertEqual(config["USER"], "tekarai")
        self.assertEqual(config["HOST"], "sql.example.com")
        self.assertEqual(config["PORT"], "1433")
        self.assertEqual(config["CONN_HEALTH_CHECKS"], True)

    def testAppliesOdbcDriverOptions(self) -> None:
        config = buildDatabaseConfig(
            dbEngine="mssql",
            dbName="TekaraiCore",
            dbUser="tekarai",
            dbPassword="secret",
            dbHost="localhost",
        )
        options = config["OPTIONS"]
        self.assertEqual(options["driver"], DEFAULT_ODBC_DRIVER)
        self.assertTrue(options["encrypt"])
        self.assertEqual(options["connection_timeout"], 30)

    def testDefaultsPortToSqlServerPort(self) -> None:
        config = buildDatabaseConfig(
            dbEngine="mssql", dbName="db", dbUser="u", dbPassword="p", dbHost="h"
        )
        self.assertEqual(config["PORT"], "1433")


class BuildDatabaseConfigSqliteTests(SimpleTestCase):
    def testBuildsMinimalSqliteConfig(self) -> None:
        config = buildDatabaseConfig(dbEngine="sqlite", dbName=":memory:")
        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertEqual(config["NAME"], ":memory:")

    def testFallsBackToDefaultFileWhenNameEmpty(self) -> None:
        config = buildDatabaseConfig(dbEngine="sqlite", dbName="")
        self.assertTrue(config["NAME"].endswith("db.sqlite3"))


class BuildDatabaseConfigValidationTests(SimpleTestCase):
    def testRejectsNonIntegerTimeout(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            buildDatabaseConfig(
                dbEngine="mssql",
                dbName="db",
                dbUser="u",
                dbPassword="p",
                dbHost="h",
                dbConnTimeout="not-a-number",
            )

    def testRejectsNonBooleanEncrypt(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            buildDatabaseConfig(
                dbEngine="mssql",
                dbName="db",
                dbUser="u",
                dbPassword="p",
                dbHost="h",
                dbEncrypt="maybe",
            )


class AssertProductionDatabaseTests(SimpleTestCase):
    def testAcceptsMssql(self) -> None:
        assertProductionDatabase("mssql")  # must not raise

    def testRejectsSqlite(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            assertProductionDatabase("sqlite")

    def testRejectsUnknownEngine(self) -> None:
        with self.assertRaises(ImproperlyConfigured):
            assertProductionDatabase("mysql")


class PythonBaselineTests(SimpleTestCase):
    def testPythonMeetsBaselineVersion(self) -> None:
        import sys

        self.assertGreaterEqual(
            sys.version_info[:2],
            (3, 12),
            "Tekarai baseline is Python 3.12 (docs/Phases/Phase1.md §4).",
        )
