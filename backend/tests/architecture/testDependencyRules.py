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

#: Phase 06 §27 layer set for the structure guard.
CONTEXT_LAYERS = ("domain", "application", "infrastructure", "presentation")

#: Directories that must never be scanned as project source (virtual
#: environments, dependency trees, caches). Without this, a local
#: `backend/venv/` makes site-packages files (django's own models.py,
#: views.py, ...) look like premature project files.
EXCLUDED_DIR_PARTS = frozenset(
    {
        "venv",
        ".venv",
        "env",
        "site-packages",
        "node_modules",
        "__pycache__",
        ".ruff_cache",
        ".mypy_cache",
        ".pytest_cache",
        "staticRoot",
        "mediaRoot",
    }
)

FORBIDDEN_DOMAIN_IMPORT_PATTERN = re.compile(
    r"^\s*(from|import)\s+(django|rest_framework|mssql_django|pyodbc|redis|channels)",
    re.MULTILINE,
)


def collectPythonFiles(*rootRelativeParts: str) -> list[Path]:
    root = BACKEND_DIR.joinpath(*rootRelativeParts)
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*.py") if not (EXCLUDED_DIR_PARTS & set(path.parts)))


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
        """EVOLUTION NOTE (Phase 06): apps/ now hosts the layered contexts
        (docs/Phases/Phase6.md §27). The Phase-01 emptiness guard becomes a
        structure guard: every context must expose exactly the four layers,
        and top-level app files are limited to ``__init__.py``/``apps.py``."""
        appsDir = Path(__file__).resolve().parents[2] / "apps"
        contextDirs = [
            entry
            for entry in appsDir.iterdir()
            if entry.is_dir() and not entry.name.startswith((".", "_"))
        ]
        self.assertTrue(contextDirs, "Expected at least one context after Phase 06.")
        for contextDir in contextDirs:
            topFiles = sorted(
                path.name
                for path in contextDir.iterdir()
                if path.is_file() and path.suffix == ".py"
            )
            self.assertEqual(
                topFiles,
                ["__init__.py", "apps.py"],
                f"{contextDir.name}: unexpected top-level modules",
            )
            for layer in CONTEXT_LAYERS:
                self.assertTrue(
                    (contextDir / layer).is_dir(),
                    f"{contextDir.name}: missing §27 layer {layer}/",
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
        """EVOLUTION NOTE (Phase 06): views/serializers/models exist now —
        but only inside the §27 placement: models under infrastructure/,
        views+serializers under presentation/api/. Anything else is still a
        layering violation."""
        offenders = [
            path
            for path in collectPythonFiles()
            if path.name in {"views.py", "serializers.py", "models.py"}
            and "tests" not in path.parts
            and "migrations" not in path.parts
            and "infrastructure" not in path.parts
            and "presentation" not in path.parts
        ]
        self.assertEqual(offenders, [], f"Layer placement violations: {offenders}")


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
