"""Architecture tests — deliberate context openings (Phase 01 §23 → Phase 06).

Phase 01 forbade business domains until an implementing phase opened them.
Phase 06 (docs/Phases/Phase6.md §32/§33) opened the implementation era
with the Shared Kernel + Tenancy + Identity. This module now guards the
OPENING REGISTER: only contexts an implementing phase has deliberately
opened may exist, with models/migrations confined to their infrastructure
layers (Phase 06 §27).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: Contexts deliberately opened, with the phase that opened them.
OPENED_CONTEXTS = {
    "sharedKernel": "Phase 06 (foundation)",
    "tenancy": "Phase 06 (exemplar context #1)",
    "identity": "Phase 06 (exemplar context #2)",
    "communication": "Phase 08 (Communication Platform)",
    "notifications": "Phase 09 (Notification Platform)",
    "ai": "Phase 13 (AI Platform & Intelligence Foundation)",
}

#: Bounded contexts from the approved domain map — still not opened.
FORBIDDEN_APP_DIRECTORIES = {
    "organization",
    "workforce",
    "hr",
    "people",
    "performance",
    "projects",
    "project",
    "tasks",
    "task",
    "assets",
    "asset",
    "devices",
    "device",
    "maintenance",
    "documents",
    "document",
    "workflow",
    "reporting",
    "analytics",
    "integration",
    "platformcore",
}


class ContextOpeningRegisterTests(SimpleTestCase):
    def testOnlyOpenedContextsExist(self) -> None:
        appsDir = BACKEND_DIR / "apps"
        existingDirs = {
            entry.name
            for entry in appsDir.iterdir()
            if entry.is_dir() and not entry.name.startswith((".", "_"))
        }
        lowered = {name.lower() for name in existingDirs}
        offenders = sorted(lowered & FORBIDDEN_APP_DIRECTORIES)
        self.assertEqual(
            offenders,
            [],
            f"Contexts exist that no phase has opened yet: {offenders}",
        )
        unexpected = sorted(existingDirs - set(OPENED_CONTEXTS))
        self.assertEqual(
            unexpected,
            [],
            f"Contexts missing from the opening register: {unexpected}",
        )

    def testModelsAndMigrationsLiveOnlyInInfrastructure(self) -> None:
        appsDir = BACKEND_DIR / "apps"
        modelFiles = [
            str(path.relative_to(BACKEND_DIR))
            for path in appsDir.rglob("models.py")
            if "infrastructure" not in path.parts
        ]
        self.assertEqual(modelFiles, [])
        migrationDirs = [
            str(path.relative_to(BACKEND_DIR))
            for path in appsDir.rglob("migrations")
            if path.is_dir() and "infrastructure" not in path.parts
        ]
        self.assertEqual(migrationDirs, [])

    def testNoBusinessEntityNamesAppearInSourceCode(self) -> None:
        """Early-warning scan for vocabulary of not-yet-opened contexts."""
        # EVOLUTION NOTE (Phase 08): Meeting/Conversation vocabulary now
        # lives in the opened communication context and is therefore allowed.
        # EVOLUTION NOTE (Phase 09): Notification vocabulary now lives in the
        # opened notifications context; it stays forbidden everywhere else.
        businessWords = (
            "Employee",
            "Department",
            "Project",
            "Task",
            "Asset",
            "Workflow",
            "Notification",
        )
        allowedFiles = {Path(__file__).name}
        def _isThirdParty(path: Path) -> bool:
            # Skip virtual environments and dependency caches (venv / .venv /
            # site-packages / node_modules) so only first-party source is scanned.
            return any(
                part in {"venv", ".venv", "site-packages", "node_modules", "__pycache__"}
                or part.endswith("venv")
                for part in path.parts
            )

        sourceFiles = [
            path
            for path in BACKEND_DIR.rglob("*.py")
            if not _isThirdParty(path)
            and "tests" not in path.parts
            and path.name not in allowedFiles
        ]
        for sourceFile in sourceFiles:
            content = sourceFile.read_text(encoding="utf-8")
            for word in businessWords:
                if word == "Notification" and "notifications" in sourceFile.parts:
                    continue
                self.assertNotIn(
                    word,
                    content,
                    f"Business vocabulary '{word}' appeared in "
                    f"{sourceFile.relative_to(BACKEND_DIR)} before its phase "
                    f"opened it.",
                )

    def testInstalledAppsMatchesOpenedContexts(self) -> None:
        allowedApps = {
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "rest_framework",
            "corsheaders",
            # Phase 08: ASGI server app so runserver speaks WebSocket.
            "daphne",
            "apps.sharedKernel",
            "apps.tenancy",
            "apps.identity",
            "apps.communication",
            "apps.notifications",
            # Phase 13: AI Platform & Intelligence Foundation context.
            "apps.ai",
        }
        unexpectedApps = sorted(set(settings.INSTALLED_APPS) - allowedApps)
        self.assertEqual(
            unexpectedApps,
            [],
            f"INSTALLED_APPS exceeds the opened-context set: {unexpectedApps}",
        )
