"""Architecture tests — no premature business domains (Phase 01 §23).

Phase 01 explicitly forbids building business domains (Employee, HR, Project,
Task, Asset, Communication, AI, Workflow, ...). These tests make the
prohibition executable, so nothing business-shaped can slip in unnoticed.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

#: Bounded contexts from the approved domain map — none may exist in Phase 01.
FORBIDDEN_APP_DIRECTORIES = {
    "identity",
    "tenancy",
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
    "communication",
    "notifications",
    "notification",
    "audit",
    "reporting",
    "analytics",
    "ai",
    "integration",
    "configuration",
    "platformcore",
}

#: EVOLUTION NOTE (Phase 03): the 20 bounded contexts and their module names
#: are now formally designed in docs/architecture/BoundedContexts.md §1.
#: This Phase-01 prohibition remains active because no implementing phase
#: has opened yet. When Phase 04+ implements a context (starting with
#: Platform Core → Identity → Organization), that phase's report and commit
#: must remove the corresponding names here — deliberately, with evidence —
#: never silently.


class NoPrematureBusinessDomainsTests(SimpleTestCase):
    def testNoForbiddenAppDirectoriesExist(self) -> None:
        appsDir = BACKEND_DIR / "apps"
        existingDirs = {
            entry.name.lower()
            for entry in appsDir.iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
        }
        offenders = sorted(existingDirs & FORBIDDEN_APP_DIRECTORIES)
        self.assertEqual(
            offenders,
            [],
            f"Business domains are forbidden in Phase 01. Found: {offenders}",
        )

    def testNoModelFilesExistAnywhereInBackend(self) -> None:
        modelFiles = [
            str(path.relative_to(BACKEND_DIR))
            for path in BACKEND_DIR.rglob("models.py")
            if "venv" not in path.parts
        ]
        self.assertEqual(
            modelFiles,
            [],
            "No Django models may exist in Phase 01 (docs/Phases/Phase1.md §15).",
        )

    def testNoMigrationPackagesExist(self) -> None:
        migrationDirs = [
            str(path.relative_to(BACKEND_DIR))
            for path in BACKEND_DIR.rglob("migrations")
            if path.is_dir() and "venv" not in path.parts
        ]
        self.assertEqual(
            migrationDirs,
            [],
            "Business migrations arrive with their phases, not in Phase 01.",
        )

    def testNoBusinessEntityNamesAppearInSourceCode(self) -> None:
        """A cheap early-warning scan for business vocabulary in backend code."""
        businessWords = (
            "Employee",
            "Department",
            "Project",
            "Task",
            "Asset",
            "Workflow",
            "Meeting",
            "Conversation",
            "Notification",
        )
        allowedFiles = {Path(__file__).name}
        sourceFiles = [
            path
            for path in BACKEND_DIR.rglob("*.py")
            if "venv" not in path.parts
            and "tests" not in path.parts
            and path.name not in allowedFiles
        ]
        for sourceFile in sourceFiles:
            content = sourceFile.read_text(encoding="utf-8")
            for word in businessWords:
                self.assertNotIn(
                    word,
                    content,
                    f"Business vocabulary '{word}' appeared early in "
                    f"{sourceFile.relative_to(BACKEND_DIR)}.",
                )

    def testInstalledAppsContainsOnlyFrameworkFoundation(self) -> None:
        from django.conf import settings

        allowedApps = {
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "rest_framework",
            "corsheaders",
        }
        unexpectedApps = sorted(set(settings.INSTALLED_APPS) - allowedApps)
        self.assertEqual(
            unexpectedApps,
            [],
            f"INSTALLED_APPS exceeds the Phase 01 foundation set: {unexpectedApps}",
        )
