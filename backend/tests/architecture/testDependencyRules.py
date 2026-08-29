"""Architecture tests — dependency direction rules (Phase 01 §13).

Phase 01 installs the guard rails early. The rules checked here are
intentionally forward-looking: today they pass because no domain code exists
yet, and they must keep passing as later phases add code.

Rules (from the approved architecture documents):
- Domain code must not import Django or any infrastructure module.
- Infrastructure must not own business rules (guarded later by review; here we
  assert structural basics).
- The API/presentation layer must not execute complex business logic directly.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

FORBIDDEN_DOMAIN_IMPORT_PATTERN = re.compile(
    r"^\s*(from|import)\s+(django|rest_framework|mssql_django|pyodbc|redis|channels)",
    re.MULTILINE,
)


def collectPythonFiles(*rootRelativeParts: str) -> list[Path]:
    root = BACKEND_DIR.joinpath(*rootRelativeParts)
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


class DomainPurityTests(SimpleTestCase):
    """Domain packages must stay framework-independent (Clean Architecture)."""

    def testNoDomainFileImportsDjangoOrInfrastructure(self) -> None:
        domainFiles = [path for path in collectPythonFiles("apps") if "domain" in path.parts]
        for domainFile in domainFiles:
            with self.subTest(file=str(domainFile)):
                source = domainFile.read_text(encoding="utf-8")
                match = FORBIDDEN_DOMAIN_IMPORT_PATTERN.search(source)
                self.assertIsNone(
                    match,
                    f"Domain file imports a framework: {domainFile} -> "
                    f"{match.group(0).strip() if match else ''}",
                )


class LayerPlacementTests(SimpleTestCase):
    """Structural expectations for the Phase 01 codebase."""

    def testAppsContainOnlyFoundationDunderInit(self) -> None:
        appFiles = [path for path in collectPythonFiles("apps")]
        nonInitFiles = [path for path in appFiles if path.name != "__init__.py"]
        self.assertEqual(
            nonInitFiles,
            [],
            "Phase 01 forbids application modules. Business apps arrive with "
            "their phases (Platform Core → Identity → Organization → ...).",
        )

    def testConfigModuleContainsNoBusinessLogicModules(self) -> None:
        configFiles = [
            path.name
            for path in collectPythonFiles("config")
            if path.suffix == ".py" and path.name != "__init__.py"
        ]
        allowedFiles = {
            "environment.py",
            "healthCheck.py",
            "urls.py",
            "wsgi.py",
            "asgi.py",
            "base.py",
            "development.py",
            "testing.py",
            "production.py",
        }
        unexpectedFiles = sorted(set(configFiles) - allowedFiles)
        self.assertEqual(
            unexpectedFiles,
            [],
            f"Unexpected modules in config/: {unexpectedFiles}",
        )

    def testNoViewsOrSerializersExistYet(self) -> None:
        """Presentation scaffolding arrives with the API phase (Phase 06)."""
        offenders = [
            path
            for path in collectPythonFiles()
            if path.name in {"views.py", "serializers.py", "models.py"}
            and "tests" not in path.parts
        ]
        self.assertEqual(offenders, [], f"Premature presentation/domain files: {offenders}")


class ImportHygieneTests(SimpleTestCase):
    def testAllSourceFilesParseAsValidPython(self) -> None:
        sourceFiles = [
            *collectPythonFiles("config"),
            *collectPythonFiles("apps"),
            *collectPythonFiles("tests"),
        ]
        self.assertTrue(len(sourceFiles) > 5, "Expected the Phase 01 file set.")
        for sourceFile in sourceFiles:
            with self.subTest(file=str(sourceFile)):
                ast.parse(sourceFile.read_text(encoding="utf-8"))
