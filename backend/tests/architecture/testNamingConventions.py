"""Architecture tests — naming conventions (Phase 01 §20).

Rules:
- Python functions and variables: camelCase (a single leading underscore for
  private helpers is allowed — Python privacy convention).
- Python classes: PascalCase.
- Django apps and packages: lowercase.
- Framework constants: UPPER_SNAKE_CASE (validated by Django itself).

camelCase is enforced for our own modules via AST — this keeps the convention
executable instead of aspirational. Test functions prefixed with `test` are
camelCase-compatible by construction.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

CAMEL_CASE_PATTERN = re.compile(r"^_?[a-z][a-zA-Z0-9]*$")
PASCAL_CASE_PATTERN = re.compile(r"^[A-Z][a-zA-Z0-9]*$")

#: Names exempt from the convention (dunder hooks, standard entrypoints).
#: EVOLUTION NOTE (Phase 06): framework hook methods we override keep their
#: framework names (DRF/Django/management contracts) — camelCase still rules
#: for everything we name ourselves.
FRAMEWORK_HOOKS = {
    "main",  # console entrypoints
    "handle",  # django management commands
    "add_arguments",  # django management command argument hook
    "get_paginated_response",  # DRF pagination override
    "get_next_link",  # DRF cursor pagination helper
    "has_permission",  # DRF permission hook
    "authenticate",  # DRF authentication hook
    "authenticate_header",  # DRF authentication hook
    "dispatch",  # DRF view dispatch
    "is_authenticated",  # DRF principal property
    "_backfill_refresh_hashes",  # Phase 07 migration helper (snake per Django)
    "receive_json",  # Channels AsyncJsonWebsocketConsumer hook (Phase 08)
    "communication_event",  # Channels group_send handler name (Phase 08)
    "notification_event",  # Channels group_send handler name (Phase 09)
    "log_message",  # http.server BaseHTTPRequestHandler hook (Phase 13)
    "do_POST",  # http.server verb dispatch hook (Phase 13)
    "do_GET",  # http.server verb dispatch hook (Phase 13)
}
FUNCTION_EXEMPTIONS = FRAMEWORK_HOOKS
MODULE_EXEMPTIONS = {"manage.py", "wsgi.py", "asgi.py", "urls.py"}


def isFrameworkGenerated(sourceFile: Path) -> bool:
    """Django-generated migration files (0001_initial.py, 00XX_*.py)."""
    return "migrations" in sourceFile.parts and bool(
        __import__("re").match(r"^\d{4}_", sourceFile.name)
    )


def collectOurPythonFiles() -> list[Path]:
    files: list[Path] = []
    for folder in ("config", "apps", "tests"):
        root = BACKEND_DIR / folder
        files.extend(sorted(root.rglob("*.py")))
    return files


class FunctionNamingTests(SimpleTestCase):
    def testFunctionNamesAreCamelCase(self) -> None:
        for sourceFile in collectOurPythonFiles():
            if sourceFile.name in MODULE_EXEMPTIONS or isFrameworkGenerated(sourceFile):
                continue
            tree = ast.parse(sourceFile.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("__") and node.name.endswith("__"):
                        continue
                    if node.name in FUNCTION_EXEMPTIONS:
                        continue
                    self.assertTrue(
                        CAMEL_CASE_PATTERN.match(node.name),
                        f"{sourceFile.relative_to(BACKEND_DIR)}: function "
                        f"'{node.name}' must be camelCase.",
                    )

    def testClassNamesArePascalCase(self) -> None:
        for sourceFile in collectOurPythonFiles():
            tree = ast.parse(sourceFile.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self.assertTrue(
                        PASCAL_CASE_PATTERN.match(node.name),
                        f"{sourceFile.relative_to(BACKEND_DIR)}: class "
                        f"'{node.name}' must be PascalCase.",
                    )


class FileNamingTests(SimpleTestCase):
    def testPythonFilesUseCamelCaseOrSingleLowercaseWords(self) -> None:
        """Files are camelCase; single-word lowercase files (base.py) are fine."""
        allowedExact = MODULE_EXEMPTIONS
        for sourceFile in collectOurPythonFiles():
            name = sourceFile.name
            if name in MODULE_EXEMPTIONS or name == "__init__.py":
                continue
            if isFrameworkGenerated(sourceFile):
                continue  # Django migration file names are framework-owned
            stem = name.removesuffix(".py")
            isCamelCase = bool(CAMEL_CASE_PATTERN.match(stem))
            isSingleLowercaseWord = bool(re.match(r"^[a-z]+$", stem))
            self.assertTrue(
                isCamelCase or isSingleLowercaseWord or name in allowedExact,
                f"File name '{name}' must be camelCase (or a single lowercase "
                f"word). Path: {sourceFile.relative_to(BACKEND_DIR)}",
            )
