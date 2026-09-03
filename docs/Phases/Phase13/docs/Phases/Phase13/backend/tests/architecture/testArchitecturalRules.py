"""Architecture tests — Phase 02 RULES A–N (docs/Phases/Phase2.md §42).

Mechanically enforced subset:

- RULE A  Domain cannot depend on Infrastructure.
- RULE B  Domain cannot depend on HTTP.
- RULE C  Domain cannot depend on Django views.
- RULE D  Domain cannot depend on external providers.
- RULE E  Modules cannot access another module's private implementation.
- RULE F  Cross-module communication must use explicit contracts.
- RULE K  Every public API must be versioned.
- RULE I  (kept from Phase 01: testSettingsSecurity).

RULES G, H, J, L, M, N become enforceable when the corresponding code
exists; their enforcement owners are documented in
docs/architecture/DependencyRules.md §4.

These tests are intentionally future-proof: today apps/ is empty (Phase 01
§23) and every scan passes vacuously; the rules activate automatically as
contexts appear.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

#: Bounded contexts appear as apps/<context>/{domain,application,
#: infrastructure,presentation}.
CONTEXT_LAYERS = ("domain", "application", "infrastructure", "presentation")

#: RULE B — HTTP stacks.
HTTP_MODULES = ("django.http", "requests", "httpx", "urllib", "aiohttp")
#: RULE A/C + layer isolation — framework stacks forbidden in domain.
FRAMEWORK_MODULES = (
    "django",
    "rest_framework",
    "channels",
    "celery",
    "redis",
    "pyodbc",
    "mssql_django",
)
#: RULE D — external provider SDKs forbidden in domain.
VENDOR_MODULES = (
    "openai",
    "anthropic",
    "boto3",
    "azure",
    "paho",
    "opcua",
    "snap7",
    "wincc",
)

IMPORT_LINE_PATTERN = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)")


def extractImports(source: str) -> list[str]:
    imports: list[str] = []
    for line in source.splitlines():
        if line.strip().startswith("#"):
            continue
        match = IMPORT_LINE_PATTERN.match(line)
        if match:
            imports.append(match.group(1))
    return imports


def collectContextFiles(contextName: str, layer: str) -> list[Path]:
    layerDir = BACKEND_DIR / "apps" / contextName / layer
    if not layerDir.exists():
        return []
    return sorted(layerDir.rglob("*.py"))


def collectContextNames() -> list[str]:
    appsDir = BACKEND_DIR / "apps"
    if not appsDir.exists():
        return []
    return sorted(
        entry.name
        for entry in appsDir.iterdir()
        if entry.is_dir() and not entry.name.startswith(("_", "."))
    )


class DomainPurityRulesTests(SimpleTestCase):
    """RULES A–D: the domain layer stays framework- and vendor-free."""

    def testDomainImportsNoFrameworkHttpOrVendorModules(self) -> None:
        violations: list[str] = []
        for contextName in collectContextNames():
            for domainFile in collectContextFiles(contextName, "domain"):
                for imported in extractImports(domainFile.read_text(encoding="utf-8")):
                    root = imported.split(".")[0]
                    full = imported
                    if root in FRAMEWORK_MODULES or full.startswith(FRAMEWORK_MODULES):
                        violations.append(
                            f"RULE A/C: {domainFile.relative_to(BACKEND_DIR)} "
                            f"imports framework '{imported}'"
                        )
                    if full.startswith(HTTP_MODULES) or root in HTTP_MODULES:
                        violations.append(
                            f"RULE B: {domainFile.relative_to(BACKEND_DIR)} "
                            f"imports HTTP stack '{imported}'"
                        )
                    if root in VENDOR_MODULES:
                        violations.append(
                            f"RULE D: {domainFile.relative_to(BACKEND_DIR)} "
                            f"imports vendor SDK '{imported}'"
                        )
        self.assertEqual(violations, [])

    def testDomainDoesNotImportSiblingLayers(self) -> None:
        """Domain never imports its own application/infrastructure."""
        violations: list[str] = []
        for contextName in collectContextNames():
            for domainFile in collectContextFiles(contextName, "domain"):
                for imported in extractImports(domainFile.read_text(encoding="utf-8")):
                    if imported.startswith(
                        f"apps.{contextName}.application"
                    ) or imported.startswith(f"apps.{contextName}.infrastructure"):
                        violations.append(
                            f"layer isolation: {domainFile.relative_to(BACKEND_DIR)} "
                            f"imports '{imported}'"
                        )
        self.assertEqual(violations, [])


class ExplicitContractsRulesTests(SimpleTestCase):
    """RULES E/F: cross-context imports target the public application layer only."""

    def testCrossContextImportsTargetApplicationContractsOnly(self) -> None:
        violations: list[str] = []
        contextNames = collectContextNames()
        for contextName in contextNames:
            for layer in CONTEXT_LAYERS:
                for sourceFile in collectContextFiles(contextName, layer):
                    for imported in extractImports(sourceFile.read_text(encoding="utf-8")):
                        match = re.match(r"^apps\.([a-zA-Z0-9_]+)\.(.+)$", imported)
                        if not match:
                            continue
                        targetContext, targetPath = match.groups()
                        if targetContext == contextName:
                            continue
                        # EVOLUTION NOTE (Phase 06, ADR-021): the Shared Kernel
                        # is the one context every layer may import — it is the
                        # platform's explicit public contract (errors, ports,
                        # envelope, middleware). All other cross-context
                        # imports must still target the application layer only
                        # (RULE F).
                        if targetContext == "sharedKernel":
                            continue
                        if targetPath.split(".")[0] != "application":
                            violations.append(
                                f"RULE E/F: {sourceFile.relative_to(BACKEND_DIR)} "
                                f"reaches into apps.{targetContext}.{targetPath} "
                                f"(only .application contracts are public)"
                            )
        self.assertEqual(violations, [])

    def testInfrastructureAndApplicationDoNotImportOtherContexts(self) -> None:
        """Infrastructure is protocol-local; it never imports other contexts.

        EVOLUTION NOTE (Phase 06, ADR-021): each context's composition root
        (``infrastructure/container.py``) assembles cross-context public
        contracts — so infrastructure may import other contexts'
        ``application`` facades exactly like every other layer. Reaching
        into another context's domain/infrastructure/presentation stays
        forbidden (RULE E).
        """
        violations: list[str] = []
        contextNames = collectContextNames()
        for contextName in contextNames:
            for sourceFile in collectContextFiles(contextName, "infrastructure"):
                for imported in extractImports(sourceFile.read_text(encoding="utf-8")):
                    match = re.match(r"^apps\.([a-zA-Z0-9_]+)\.(.+)$", imported)
                    if not match or match.group(1) == contextName:
                        continue
                    targetContext, targetPath = match.groups()
                    if targetContext == "sharedKernel":
                        continue  # shared kernel is public to all layers
                    if targetPath.split(".")[0] == "application":
                        continue  # public contract facade (Phase 06)
                    violations.append(
                        f"RULE E: infrastructure of '{contextName}' imports "
                        f"'{imported}' (cross-context forbidden)"
                    )
        self.assertEqual(violations, [])


class ApplicationLayerIsolationTests(SimpleTestCase):
    """Application uses ports, not the ORM/HTTP stack (DependencyRules §3)."""

    def testApplicationImportsNoOrmOrTransport(self) -> None:
        allowedDjangoPrefix = "django.core.exceptions"
        violations: list[str] = []
        for contextName in collectContextNames():
            for sourceFile in collectContextFiles(contextName, "application"):
                for imported in extractImports(sourceFile.read_text(encoding="utf-8")):
                    if imported.startswith(allowedDjangoPrefix):
                        continue
                    if imported.startswith("django.db") or imported.startswith("django.http"):
                        violations.append(
                            f"application isolation: {sourceFile.relative_to(BACKEND_DIR)} "
                            f"imports '{imported}' (use a repository/port)"
                        )
                    if imported.startswith("rest_framework"):
                        violations.append(
                            f"application isolation: {sourceFile.relative_to(BACKEND_DIR)} "
                            f"imports '{imported}' (transport stays in presentation)"
                        )
        self.assertEqual(violations, [])


class ApiVersioningRuleTests(SimpleTestCase):
    """RULE K: every public API path is versioned (/api/vN/...)."""

    UNVERSIONED_API_PATTERN = re.compile(r"['\"]api/(?!v\d+/)")

    def testNoUnversionedApiRoutes(self) -> None:
        scanTargets: list[Path] = []
        configDir = BACKEND_DIR / "config"
        scanTargets.extend(sorted(configDir.rglob("*.py")))
        presentationDirs = (BACKEND_DIR / "apps").rglob("presentation")
        for presentationDir in presentationDirs:
            scanTargets.extend(sorted(presentationDir.rglob("*.py")))

        violations: list[str] = []
        for target in scanTargets:
            for lineNumber, line in enumerate(
                target.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if self.UNVERSIONED_API_PATTERN.search(line):
                    violations.append(
                        f"RULE K: unversioned API path in "
                        f"{target.relative_to(BACKEND_DIR)}:{lineNumber}: {stripped}"
                    )
        self.assertEqual(violations, [])


class Phase02DocumentationSetTests(SimpleTestCase):
    """Documentation Review: the Phase 02 architecture set exists."""

    REQUIRED_ARCHITECTURE_DOCS = (
        "SystemArchitecture.md",
        "LayerArchitecture.md",
        "ModuleArchitecture.md",
        "DependencyRules.md",
        "SecurityArchitecture.md",
        "MultiTenancyArchitecture.md",
        "EventArchitecture.md",
        "IntegrationArchitecture.md",
        "AIArchitecture.md",
        "ExtensionArchitecture.md",
        "ObservabilityArchitecture.md",
        "StorageArchitecture.md",
    )

    def testRequiredArchitectureDocumentsExist(self) -> None:
        for docName in self.REQUIRED_ARCHITECTURE_DOCS:
            path = REPOSITORY_ROOT / "docs" / "architecture" / docName
            self.assertTrue(
                path.is_file() and path.stat().st_size > 500,
                f"docs/architecture/{docName} is required by Phase 02 §37.",
            )

    def testPhase02AdrsExist(self) -> None:
        for adrNumber in range(12, 19):  # ADR-012 .. ADR-018
            matches = list((REPOSITORY_ROOT / "docs" / "adr").glob(f"ADR-{adrNumber:03d}*.md"))
            self.assertTrue(
                matches,
                f"docs/adr/ADR-{adrNumber:03d}*.md is required by Phase 02 §38.",
            )

    def testAdrIndexContainsNumberingMapping(self) -> None:
        """The Phase 02 §38 numbering reconciliation is documented."""
        index = (REPOSITORY_ROOT / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
        self.assertIn("Phase 02 §38 Mapping", index)

    def testDependencyRulesContainRulesAToN(self) -> None:
        rulesDoc = (REPOSITORY_ROOT / "docs" / "architecture" / "DependencyRules.md").read_text(
            encoding="utf-8"
        )
        for ruleLetter in "ABCDEFGHIJKLMN":
            self.assertIn(f"| {ruleLetter} |", rulesDoc, f"RULE {ruleLetter} missing.")

    def testModuleArchitectureContainsMatrix(self) -> None:
        moduleDoc = (REPOSITORY_ROOT / "docs" / "architecture" / "ModuleArchitecture.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Architecture Matrix", moduleDoc)
        for requiredModule in (
            "Platform Core",
            "Identity",
            "Organization",
            "People",
            "Projects",
            "Tasks",
            "Assets",
            "Devices",
            "Maintenance",
            "Documents",
            "Workflow",
            "Communication",
            "Notifications",
            "Analytics",
            "AI",
            "Integration Hub",
        ):
            self.assertIn(requiredModule, moduleDoc)

    def testDependencyMatrixMarksUndecidedItems(self) -> None:
        """Spec §41: uncertain dependencies must be marked TO BE DECIDED."""
        depDoc = (REPOSITORY_ROOT / "docs" / "architecture" / "DependencyRules.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("TO BE DECIDED", depDoc)
        self.assertIn("Dependency Matrix", depDoc)

    def testArchitectureDocsContainMermaidDiagrams(self) -> None:
        """Spec §39: maintainable (Mermaid) diagrams, 12 required."""
        diagramHosts = {
            "SystemArchitecture.md": 2,  # system context + container
            "LayerArchitecture.md": 2,  # layer + API request flow
            "ModuleArchitecture.md": 2,  # module boundary + sequence
            "DependencyRules.md": 1,
            "SecurityArchitecture.md": 1,  # authentication flow
            "MultiTenancyArchitecture.md": 1,
            "EventArchitecture.md": 1,
            "IntegrationArchitecture.md": 1,
            "AIArchitecture.md": 1,
            "ExtensionArchitecture.md": 1,
        }
        totalDiagrams = 0
        for docName, minimumCount in diagramHosts.items():
            content = (REPOSITORY_ROOT / "docs" / "architecture" / docName).read_text(
                encoding="utf-8"
            )
            count = content.count("```mermaid")
            self.assertGreaterEqual(
                count,
                minimumCount,
                f"{docName} must contain at least {minimumCount} diagram(s).",
            )
            totalDiagrams += count
        self.assertGreaterEqual(totalDiagrams, 12)
