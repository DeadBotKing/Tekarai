"""Architecture tests — repository hygiene (Phase 01 §3, §8, §22).

Verifies the repository-level Definition-of-Done items that can be checked
mechanically: required folders exist, ignore rules actually ignore, and the
license/readme files are present.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class RepositoryStructureTests(SimpleTestCase):
    def testRequiredRootFoldersExist(self) -> None:
        requiredFolders = [
            "backend",
            "frontend-web",
            "mobile",
            "desktop",
            "agents",
            "ai",
            "sdk",
            "docs",
            "deployment",
            "infrastructure",
        ]
        for folder in requiredFolders:
            self.assertTrue(
                (REPOSITORY_ROOT / folder).is_dir(),
                f"Required root folder missing: {folder}/",
            )

    def testRequiredRootFilesExist(self) -> None:
        requiredFiles = [
            ".gitignore",
            ".gitattributes",
            "README.md",
            "LICENSE",
        ]
        for fileName in requiredFiles:
            self.assertTrue(
                (REPOSITORY_ROOT / fileName).is_file(),
                f"Required root file missing: {fileName}",
            )

    def testRequiredDocumentationFoldersExist(self) -> None:
        requiredDocFolders = [
            "architecture",
            "adr",
            "api",
            "database",
            "domain",
            "development",
            "deployment",
            "security",
            "operations",
            "product",
        ]
        for folder in requiredDocFolders:
            self.assertTrue(
                (REPOSITORY_ROOT / "docs" / folder).is_dir(),
                f"Required docs folder missing: docs/{folder}/",
            )

    def testBackendFoundationFoldersExist(self) -> None:
        requiredBackendFolders = [
            "config",
            "config/settings",
            "apps",
            "tests/unit",
            "tests/integration",
            "tests/architecture",
            "requirements",
            "scripts",
            "docs",
        ]
        for folder in requiredBackendFolders:
            self.assertTrue(
                (REPOSITORY_ROOT / "backend" / folder).is_dir(),
                f"Required backend folder missing: backend/{folder}/",
            )

    def testMultiEnvironmentSettingsModulesExist(self) -> None:
        requiredSettings = ["base.py", "development.py", "testing.py", "production.py"]
        for settingsFile in requiredSettings:
            self.assertTrue(
                (REPOSITORY_ROOT / "backend" / "config" / "settings" / settingsFile).is_file(),
                f"Multi-environment settings missing: {settingsFile}",
            )


class GitIgnorePolicyTests(SimpleTestCase):
    def testRealEnvFileIsIgnored(self) -> None:
        exitCode = subprocess.call(
            ["git", "check-ignore", "-q", "backend/.env"],
            cwd=REPOSITORY_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertEqual(exitCode, 0, "backend/.env must be ignored by Git.")

    def testVirtualEnvironmentIsIgnored(self) -> None:
        # Trailing slash: git matches directory-only patterns on paths that
        # do not exist yet in the working tree.
        for venvPath in ("backend/venv/", "venv/", ".venv/"):
            exitCode = subprocess.call(
                ["git", "check-ignore", "-q", venvPath],
                cwd=REPOSITORY_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertEqual(exitCode, 0, f"{venvPath} must be ignored by Git.")

    def testPythonArtifactsAreIgnored(self) -> None:
        for ignoredPath in (
            "backend/config/__pycache__/",
            "backend/x.pyc",
            "backend/db.sqlite3",
        ):
            exitCode = subprocess.call(
                ["git", "check-ignore", "-q", ignoredPath],
                cwd=REPOSITORY_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.assertEqual(exitCode, 0, f"{ignoredPath} must be ignored by Git.")

    def testCoverageArtifactsAreIgnored(self) -> None:
        exitCode = subprocess.call(
            ["git", "check-ignore", "-q", "backend/.coverage"],
            cwd=REPOSITORY_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.assertEqual(exitCode, 0, "backend/.coverage must be ignored by Git.")

    def testRootGitignoreTxtRemnantIsGone(self) -> None:
        """The active ignore file is `.gitignore`; a stale `.gitignore.txt`
        must not sit next to it.

        A stale copy typically appears when a newer archive is extracted
        over an older clone/download (extraction never deletes files). The
        failure message tells the user exactly how to clean it up.
        """
        stalePath = REPOSITORY_ROOT / ".gitignore.txt"
        if stalePath.exists():
            self.fail(
                "A stale '.gitignore.txt' exists next to the active "
                "'.gitignore' (usually a leftover from extracting a newer "
                "archive over an older copy of the repository — extraction "
                "does not delete extra files). Remove it and re-run:\n"
                "  PowerShell:  Remove-Item .gitignore.txt   "
                "(from the repository root)\n"
                "  Bash:        rm .gitignore.txt"
            )
        # Tracked-state check when running inside a git work tree.
        if (REPOSITORY_ROOT / ".git").exists():
            trackedOutput = subprocess.run(
                ["git", "ls-files"],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
            )
            trackedFiles = trackedOutput.stdout.splitlines()
            self.assertIn(".gitignore", trackedFiles, ".gitignore must be tracked.")
            self.assertNotIn(
                ".gitignore.txt",
                trackedFiles,
                ".gitignore.txt must not be tracked (superseded by .gitignore).",
            )


class DocumentationSetTests(SimpleTestCase):
    def testAdrFilesExistForPhaseOneBaseline(self) -> None:
        adrDir = REPOSITORY_ROOT / "docs" / "adr"
        for adrNumber in range(1, 12):  # ADR-001 .. ADR-011
            matches = list(adrDir.glob(f"ADR-{adrNumber:03d}*.md"))
            self.assertTrue(
                matches,
                f"docs/adr/ADR-{adrNumber:03d}*.md is required by Phase 01 §10.",
            )

    def testEachAdrContainsRequiredSections(self) -> None:
        adrDir = REPOSITORY_ROOT / "docs" / "adr"
        requiredSections = ["Context", "Decision", "Alternatives", "Consequences"]
        for adrFile in sorted(adrDir.glob("ADR-*.md")):
            content = adrFile.read_text(encoding="utf-8")
            for section in requiredSections:
                self.assertIn(
                    section,
                    content,
                    f"{adrFile.name} misses section '{section}'.",
                )
