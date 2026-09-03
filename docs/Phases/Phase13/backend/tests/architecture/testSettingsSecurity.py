"""Architecture tests — settings security policy (Phase 01 §14, §22).

These tests keep the configuration fail-closed: production can never start
with DEBUG, with a missing/known-development secret, with an empty host
allow-list, or with a non-SQL-Server database engine.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
from pathlib import Path
from types import ModuleType

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

SETTINGS_DIR = Path(__file__).resolve().parents[2] / "config" / "settings"


def importProductionSettingsWith(overrides: dict[str, str]) -> ModuleType:
    """(Re)import config.settings.production under patched environment values."""
    savedValues = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        sys.modules.pop("config.settings.production", None)
        module = importlib.import_module("config.settings.production")
        return module
    finally:
        sys.modules.pop("config.settings.production", None)
        for key, original in savedValues.items():
            if original is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original


VALID_PRODUCTION_ENV = {
    "SECRET_KEY": "x" * 60,
    "ALLOWED_HOSTS": "ops.tekarai.example.com",
    "csrfTrustedOrigins": "https://ops.tekarai.example.com",
    "corsAllowedOrigins": "https://ops.tekarai.example.com",
    "dbEngine": "mssql",
    "dbName": "TekaraiCore",
    "dbUser": "tekarai",
    "dbPassword": "prod-secret",
    "dbHost": "sql.internal",
    "dbPort": "1433",
}


class ProductionSettingsPolicyTests(SimpleTestCase):
    def testValidProductionConfigurationImports(self) -> None:
        module = importProductionSettingsWith(dict(VALID_PRODUCTION_ENV))
        self.assertEqual(module.environment, "production")

    def testDebugIsForcedFalseEvenWhenEnvironmentSaysTrue(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, DEBUG="true")
        module = importProductionSettingsWith(overrides)
        self.assertIs(module.DEBUG, False)

    def testMissingSecretKeyIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, SECRET_KEY="")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testKnownTestingKeyIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, SECRET_KEY="tekarai-insecure-testing-key")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testKnownPlaceholderKeyIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, SECRET_KEY="change-me")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testEmptyAllowedHostsIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, ALLOWED_HOSTS="")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testSqliteEngineIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, dbEngine="sqlite")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testEmptyCorsAllowListIsRejected(self) -> None:
        overrides = dict(VALID_PRODUCTION_ENV, corsAllowedOrigins="")
        with self.assertRaises(ImproperlyConfigured):
            importProductionSettingsWith(overrides)

    def testProductionEnablesTransportSecurity(self) -> None:
        module = importProductionSettingsWith(dict(VALID_PRODUCTION_ENV))
        self.assertIs(module.SECURE_SSL_REDIRECT, True)
        self.assertGreater(module.SECURE_HSTS_SECONDS, 0)
        self.assertIs(module.SESSION_COOKIE_SECURE, True)
        self.assertIs(module.CSRF_COOKIE_SECURE, True)


class NoHardcodedSecretsTests(SimpleTestCase):
    def testSettingsSourcesContainNoLiteralSecretKeyAssignment(self) -> None:
        pattern = re.compile(r"SECRET_KEY\s*=\s*['\"]")
        for settingsFile in SETTINGS_DIR.glob("*.py"):
            with self.subTest(file=settingsFile.name):
                content = settingsFile.read_text(encoding="utf-8")
                matches = [line.strip() for line in content.splitlines() if pattern.search(line)]
                self.assertEqual(
                    matches,
                    [],
                    f"{settingsFile.name} assigns a string literal to SECRET_KEY.",
                )

    def testSettingsSourcesContainNoLiteralPasswordAssignment(self) -> None:
        pattern = re.compile(r"(?i)(PASSWORD|SECRET)\s*=\s*['\"][^'\"]{6,}")
        for settingsFile in SETTINGS_DIR.glob("*.py"):
            with self.subTest(file=settingsFile.name):
                content = settingsFile.read_text(encoding="utf-8")
                for line in content.splitlines():
                    if line.strip().startswith("#"):
                        continue
                    self.assertIsNone(
                        pattern.search(line),
                        f"{settingsFile.name} contains a literal credential: {line}",
                    )

    def testEnvTemplateExistsAndCoversRequiredCategories(self) -> None:
        envTemplate = SETTINGS_DIR.parents[1] / ".env.example"
        self.assertTrue(envTemplate.exists(), "backend/.env.example is required.")
        content = envTemplate.read_text(encoding="utf-8")
        requiredCategories = [
            "APPLICATION",
            "DATABASE",
            "SECURITY",
            "DJANGO",
            "LOGGING",
            "CACHE",
            "EMAIL",
            "STORAGE",
            "CORS",
            "JWT",
            "EXTERNAL SERVICES",
        ]
        for category in requiredCategories:
            self.assertIn(category, content, f".env.example misses {category}.")

    def testEnvTemplateCarriesNoRealSecretValues(self) -> None:
        envTemplate = SETTINGS_DIR.parents[1] / ".env.example"
        for line in envTemplate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            if "dbPassword" in stripped or "SECRET_KEY=" in stripped:
                value = stripped.split("=", 1)[1].strip()
                acceptable = (
                    value == ""  # empty allowed: dev ephemeral key / unset
                    or "CHANGE-ME" in value
                    or "RESERVED" in value
                )
                self.assertTrue(
                    acceptable,
                    f"Unexpected credential-like value in .env.example: {stripped}",
                )
