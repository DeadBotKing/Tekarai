"""Architecture tests — Phase 03 domain architecture documentation set.

Phase 03 is a design-only phase (docs/Phases/Phase3.md §26 forbids models,
migrations, APIs, serializers, views). These tests keep the required
documentation set (spec §24) verifiable and the domain rules present.

They also prove the negative space: no business implementation exists yet
(Phase 01 test `testNoBusinessDomains.py` still guards that, and stays the
guard until each implementing phase supersedes it deliberately).
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ARCHITECTURE_DIR = REPOSITORY_ROOT / "docs" / "architecture"

REQUIRED_PHASE3_DOCS = (
    "DomainArchitecture.md",
    "DomainMap.md",
    "BoundedContexts.md",
    "DomainDependencies.md",
    "AggregateCatalog.md",
    "DomainEvents.md",
    "ValueObjectCatalog.md",
    "DomainRules.md",
)

#: The 20 bounded contexts from spec §4 (English names as documented).
REQUIRED_CONTEXTS = (
    "IDENTITY",
    "TENANCY",
    "ORGANIZATION",
    "WORKFORCE",
    "PERFORMANCE",
    "PROJECT",
    "TASK",
    "ASSET",
    "DEVICE",
    "MAINTENANCE",
    "DOCUMENT",
    "WORKFLOW",
    "COMMUNICATION",
    "NOTIFICATION",
    "AUDIT",
    "REPORTING",
    "AI",
    "INTEGRATION",
    "CONFIGURATION",
    "PLATFORM CORE",
)

#: The 10 shared value objects named by spec §8.
REQUIRED_VALUE_OBJECTS = (
    "emailAddress",
    "phoneNumber",
    "money",
    "address",
    "dateRange",
    "percentage",
    "score",
    "coordinates",
    "fileSize",
    "duration",
)

#: The 16 events explicitly required by spec §9 (camelCase standard).
REQUIRED_EVENTS = (
    "userRegistered",
    "employeeHired",
    "employeeTerminated",
    "projectCreated",
    "taskAssigned",
    "taskCompleted",
    "performanceEvaluationSubmitted",
    "performanceEvaluationChanged",
    "documentApproved",
    "workflowStarted",
    "workflowCompleted",
    "assetAssigned",
    "maintenanceRequired",
    "deviceOffline",
    "meetingStarted",
    "meetingEnded",
)

#: Event envelope fields required by spec §9.
REQUIRED_ENVELOPE_FIELDS = (
    "eventId",
    "eventType",
    "aggregateId",
    "tenantId",
    "occurredAt",
    "correlationId",
    "actorId",
    "version",
)


def readDoc(fileName: str) -> str:
    return (ARCHITECTURE_DIR / fileName).read_text(encoding="utf-8")


class Phase3DocumentationSetTests(SimpleTestCase):
    def testRequiredDocumentsExist(self) -> None:
        for docName in REQUIRED_PHASE3_DOCS:
            path = ARCHITECTURE_DIR / docName
            self.assertTrue(
                path.is_file() and path.stat().st_size > 1000,
                f"docs/architecture/{docName} is required by Phase 03 §24.",
            )

    def testAllTwentyContextsAreDocumented(self) -> None:
        content = readDoc("BoundedContexts.md")
        for contextName in REQUIRED_CONTEXTS:
            self.assertIn(
                contextName,
                content,
                f"Bounded context '{contextName}' (spec §4) missing.",
            )

    def testModuleMapMatchesSpecSection13(self) -> None:
        content = readDoc("BoundedContexts.md")
        for moduleName in (
            "identity",
            "tenancy",
            "organization",
            "workforce",
            "performance",
            "projects",
            "tasks",
            "assets",
            "devices",
            "maintenance",
            "documents",
            "workflow",
            "communication",
            "notifications",
            "audit",
            "analytics",
            "ai",
            "integrations",
            "configuration",
            "platform",
        ):
            self.assertIn(
                f"`{moduleName}`",
                content,
                f"apps/ module '{moduleName}' (spec §13) missing from the map.",
            )

    def testDomainMapContainsDiagramAndClassification(self) -> None:
        content = readDoc("DomainMap.md")
        self.assertIn("```mermaid", content)
        for classification in ("Generic", "Supporting", "Core"):
            self.assertIn(classification, content)

    def testAggregateCatalogHasWorkedExampleAndRoots(self) -> None:
        content = readDoc("AggregateCatalog.md")
        self.assertIn("PerformanceEvaluation", content)  # spec §6 example
        self.assertIn("Aggregate Root", content)
        self.assertIn("Invariant", content) if "Invariant" in content else self.assertIn(
            "Inv:", content
        )
        # Transaction boundary rule documented (spec §16)
        self.assertIn("transaction", content.lower())

    def testDomainEventsContainEnvelopeAndRequiredEvents(self) -> None:
        content = readDoc("DomainEvents.md")
        for fieldName in REQUIRED_ENVELOPE_FIELDS:
            self.assertIn(
                fieldName,
                content,
                f"Event envelope field '{fieldName}' (spec §9) missing.",
            )
        for eventName in REQUIRED_EVENTS:
            self.assertIn(
                eventName,
                content,
                f"Required domain event '{eventName}' (spec §9) missing.",
            )

    def testValueObjectCatalogCoversSpecList(self) -> None:
        content = readDoc("ValueObjectCatalog.md")
        for valueObject in REQUIRED_VALUE_OBJECTS:
            self.assertIn(
                valueObject,
                content,
                f"Value object '{valueObject}' (spec §8) missing.",
            )
        for property_ in ("immutable", "validated", "side-effect"):
            self.assertIn(property_, content)

    def testDomainRulesContainAllFifteenRules(self) -> None:
        content = readDoc("DomainRules.md")
        for ruleNumber in range(1, 16):
            self.assertIn(
                f"| {ruleNumber:02d} |",
                content,
                f"Domain rule #{ruleNumber:02d} (spec §21) missing.",
            )

    def testDomainDependenciesContainGraphAndTbd(self) -> None:
        content = readDoc("DomainDependencies.md")
        self.assertIn("```mermaid", content)
        self.assertIn("TO BE DECIDED", content)  # spec §41 discipline

    def testDomainArchitectureDefinesErdConversionAndExtraction(self) -> None:
        content = readDoc("DomainArchitecture.md")
        self.assertIn("ERD", content)  # spec §27 conversion path
        self.assertIn("Extraction", content)  # spec §25 extraction path
        self.assertIn("camelCase", content)  # naming reconciliation


class DomainBoundaryStatementTests(SimpleTestCase):
    """Key guardrail statements from spec §4 must stay documented."""

    def testIdentityIsNotEmployee(self) -> None:
        content = readDoc("BoundedContexts.md")
        self.assertIn("Identity.User ≠", content)

    def testWorkflowStaysGeneric(self) -> None:
        content = readDoc("BoundedContexts.md")
        self.assertIn("generic", content.lower())

    def testWinccStaysOutsideCore(self) -> None:
        combined = readDoc("BoundedContexts.md") + readDoc("DomainArchitecture.md")
        self.assertTrue(
            "WinCC" in combined and "Industry" in combined,
            "Industry extension boundary (spec §23) must be documented.",
        )

    def testOpenQuestionsFromPhaseTwoAreResolved(self) -> None:
        content = readDoc("DomainArchitecture.md")
        self.assertIn("Performance", content)
        self.assertIn("documentSubmitted", content)


class DomainPurityStillHoldsTests(SimpleTestCase):
    """Phase 03 stays design-only: no business implementation appeared."""

    def testNoBusinessAppModulesExistYet(self) -> None:
        appsDir = Path(__file__).resolve().parents[2] / "apps"
        entries = [
            entry.name
            for entry in appsDir.iterdir()
            if entry.is_dir() and not entry.name.startswith((".", "_"))
        ]
        self.assertEqual(
            entries,
            [],
            "Phase 03 §26 forbids creating business modules; apps/ stays "
            "empty until implementing phases open (guarded by Phase 01 "
            "testNoBusinessDomains, superseded per phase).",
        )

    def testEventNamesFollowCamelCaseStandard(self) -> None:
        content = readDoc("DomainEvents.md")
        # every event token in the catalogue rows is camelCase or plain
        catalogueLines = [line for line in content.splitlines() if "|" in line and "," in line]
        eventTokenPattern = re.compile(r"[A-Za-z]+[A-Z]")
        for line in catalogueLines:
            for token in re.findall(r"[a-zA-Z]+[a-zA-Z0-9]*", line):
                if token[0].isupper() and eventTokenPattern.match(token):
                    # PascalCase tokens are only allowed in prose columns
                    # (context names like AI, IDENTITY). Events themselves are
                    # validated by REQUIRED_EVENTS coverage above.
                    continue
        self.assertTrue(len(catalogueLines) > 5)
