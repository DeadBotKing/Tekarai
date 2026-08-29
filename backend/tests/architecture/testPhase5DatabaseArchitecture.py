"""Phase 05 database architecture tests.

Verifies the Phase 05 deliverable set (docs/Phases/Phase5.md §63–§81):
database dictionary, entity/field catalogs, business rules with IDs,
constraints, indexes, state machines, error codes, retention, migration,
backup and governance documents.

Design-only phase: §82 forbids final Django models/migrations until Phase 5
is approved — that constraint is asserted too (Phase 04 test already guards
it; we re-check the core apps stay model-free).
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

from tests.architecture.testPhase4DatabaseArchitecture import (
    DATABASE_DIR,
    REPOSITORY_ROOT,
)

BACKEND_ROOT = REPOSITORY_ROOT / "backend"

PHASE5_FILES = [
    "DatabaseDictionary.md",
    "EntityCatalog.md",
    "FieldCatalog.md",
    "BusinessRuleCatalog.md",
    "ConstraintCatalog.md",
    "IndexCatalog.md",
    "StateMachineCatalog.md",
    "ErrorCodeCatalog.md",
    "DataRetentionPolicy.md",
    "DatabaseMigrationStrategy.md",
    "DatabaseBackupStrategy.md",
    "DataGovernance.md",
]

DICTIONARY = DATABASE_DIR / "DatabaseDictionary.md"
ENTITY_CATALOG = DATABASE_DIR / "EntityCatalog.md"
FIELD_CATALOG = DATABASE_DIR / "FieldCatalog.md"
RULES = DATABASE_DIR / "BusinessRuleCatalog.md"
CONSTRAINTS = DATABASE_DIR / "ConstraintCatalog.md"
INDEXES = DATABASE_DIR / "IndexCatalog.md"
MACHINES = DATABASE_DIR / "StateMachineCatalog.md"
ERRORS = DATABASE_DIR / "ErrorCodeCatalog.md"
RETENTION = DATABASE_DIR / "DataRetentionPolicy.md"
MIGRATION = DATABASE_DIR / "DatabaseMigrationStrategy.md"
BACKUP = DATABASE_DIR / "DatabaseBackupStrategy.md"
GOVERNANCE = DATABASE_DIR / "DataGovernance.md"

CORE_APPS_DIR = BACKEND_ROOT / "core_apps"

REQUIRED_MACHINES = [
    "Project",
    "Task",
    "Document",
    "Workflow",
    "Maintenance",
    "Notification",
    "Integration",
    "Device",
    "Call",
    "Meeting",
]

RULE_PREFIXES = [
    "TEN",
    "SEC",
    "PER",
    "AUD",
    "DAT",
    "WF",
    "AI",
    "COM",
    "INT",
    "PERF",
]

SPEC_ERROR_CODES = [
    "TENANT_ACCESS_DENIED",
    "PROJECT_ALREADY_COMPLETED",
    "INVALID_STATE_TRANSITION",
    "DUPLICATE_BUSINESS_CODE",
    "PERMISSION_DENIED",
    "INVALID_WORKFLOW_TRANSITION",
]

INDEX_COLUMNS = [
    "Index",
    "Table",
    "Columns",
    "Purpose",
    "Expected query",
    "Imp",
]


def headingsOf(path: Path, level: str = "###") -> set[str]:
    return {
        line[len(level) :].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(level + " ")
    }


class Phase5DeliverableSetTests(SimpleTestCase):
    def testAllTwelveDeliverablesExist(self) -> None:
        for name in PHASE5_FILES:
            assert (DATABASE_DIR / name).is_file(), f"missing {name}"
            assert (DATABASE_DIR / name).stat().st_size > 500, f"too small: {name}"

    def testPhase4NumberedSetUntouched(self) -> None:
        for i in range(1, 11):
            numbered = [
                p
                for p in DATABASE_DIR.iterdir()
                if p.name.startswith(f"{i:02d}") and p.suffix == ".md"
            ]
            assert numbered, f"phase-04 file {i:02d}*.md disappeared"

    def testGeneratorMatchesCommittedCatalogs(self) -> None:
        """EntityCatalog headings == FieldCatalog headings == dictionary set."""
        dict_headings = {
            h for h in headingsOf(DICTIONARY) if not h.startswith("Standard field blocks")
        }
        field_headings = headingsOf(FIELD_CATALOG)
        entity_rows = [
            line
            for line in ENTITY_CATALOG.read_text(encoding="utf-8").splitlines()
            if line.startswith("| ") and not line.startswith("| Entity")
        ]
        assert len(dict_headings) == len(field_headings) == len(entity_rows) == 195
        assert dict_headings == field_headings


class Phase5DictionaryTests(SimpleTestCase):
    def testDictionaryDocumentsStandardBlocks(self) -> None:
        text = DICTIONARY.read_text(encoding="utf-8")
        assert "Standard field blocks" in text
        for block in ("BASE", "APPEND", "VOCAB"):
            assert block in text, f"missing {block} standard block"

    def testDictionaryHeadersCarryRequiredAttributes(self) -> None:
        text = DICTIONARY.read_text(encoding="utf-8")
        for marker in (
            "Tenant scoped:",
            "Soft deletable:",
            "Auditable:",
            "Kind:",
            "Business identity:",
            "Retention:",
        ):
            assert marker in text, f"header attribute missing: {marker}"

    def testEveryBusinessFieldRowHasNineColumns(self) -> None:
        bad: list[str] = []
        for line in FIELD_CATALOG.read_text(encoding="utf-8").splitlines():
            if line.startswith("| ") and set(line) != {"|", "-", " "}:
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) != 9:
                    bad.append(line[:80])
        assert not bad, f"field rows without 9 columns: {bad[:5]}"

    def testNoSnakeCaseFieldNames(self) -> None:
        bad: list[str] = []
        for line in FIELD_CATALOG.read_text(encoding="utf-8").splitlines():
            if line.startswith("| ") and set(line) != {"|", "-", " "}:
                name = line.strip("|").split("|")[0].strip()
                if "_" in name and name not in {"_kind", ""}:
                    bad.append(name)
        assert not bad, f"snake_case fields violate BR-DAT-001: {sorted(set(bad))[:10]}"

    def testOptimisticLockEntitiesDeclareVersion(self) -> None:
        text = FIELD_CATALOG.read_text(encoding="utf-8")
        assert "version" in text, "version column (§50) missing from FieldCatalog"


class Phase5BusinessRuleTests(SimpleTestCase):
    def testRuleIdsPresentForEveryCategory(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        for prefix in RULE_PREFIXES:
            assert f"BR-{prefix}-" in text, f"no rules for category {prefix}"

    def testRulesCarrySeverityAndEnforcement(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        assert text.count("Severity:") >= 71
        assert text.count("Enforcement:") >= 71
        for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            assert severity in text

    def testRulesCarryTraceability(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        assert text.count("Trace:") >= 71, "§62 traceability lines missing"

    def testSpecPriorityRulesAreCritical(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        for rule_id in ("BR-TEN-001", "BR-SEC-001", "BR-SEC-002", "BR-AUD-001"):
            block = text.split(rule_id, 1)[1][:400]
            assert "CRITICAL" in block, f"{rule_id} must be CRITICAL (§60)"

    def testSpecRuleFamiliesExist(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        for fragment in (
            "TENANT_ACCESS_DENIED",
            "PERMISSION_DENIED",
            "DUPLICATE_BUSINESS_CODE",
            "offlineAfterSeconds",
            "NotificationRecipient",
            "resultClassification",
        ):
            assert fragment in text, f"rule referencing {fragment} missing"

    def testRuleInventoryTableSums(self) -> None:
        text = RULES.read_text(encoding="utf-8")
        assert "**71**" in text.split("Rule inventory summary")[1]


class Phase5StateMachineTests(SimpleTestCase):
    def testAllTenRequiredMachines(self) -> None:
        text = MACHINES.read_text(encoding="utf-8")
        for machine in REQUIRED_MACHINES:
            assert f"Machine: {machine}" in text, f"missing machine {machine}"

    def testEveryMachineDocumentsContractParts(self) -> None:
        text = MACHINES.read_text(encoding="utf-8")
        for part in ("Actor", "Perm", "Guard", "Effects"):
            assert text.count(part) >= 10, f"contract column {part} under-documented"
        for part in ("States", "Forbidden"):
            assert part in text

    def testMachinesHaveDiagrams(self) -> None:
        text = MACHINES.read_text(encoding="utf-8")
        assert text.count("stateDiagram-v2") >= 10

    def testTerminalStatesDocumented(self) -> None:
        text = MACHINES.read_text(encoding="utf-8")
        for frag in ("PROJECT_ALREADY_COMPLETED", "DOCUMENT_VERSION_IMMUTABLE"):
            assert frag in text


class Phase5ConstraintAndIndexTests(SimpleTestCase):
    def testConstraintCatalogSections(self) -> None:
        text = CONSTRAINTS.read_text(encoding="utf-8")
        for section in (
            "Primary keys",
            "Foreign keys and delete behaviors",
            "Unique constraints",
            "CHECK constraints",
            "Controlled vocabularies",
        ):
            assert section in text, f"constraint section missing: {section}"

    def testCascadeRegisterLimited(self) -> None:
        text = CONSTRAINTS.read_text(encoding="utf-8")
        cascades = [
            line for line in text.splitlines() if "CASCADE" in line and line.startswith("|")
        ]
        assert 1 <= len(cascades) <= 4, "CASCADE must stay exceptional"

    def testCheckConstraintsSimpleOnly(self) -> None:
        text = CONSTRAINTS.read_text(encoding="utf-8")
        assert "NOT CHECKs" in text or "Explicitly NOT" in text
        assert "≥ 0" in text  # amount non-negative pattern §55

    def testTenantScopedUniquesReferenceRules(self) -> None:
        text = CONSTRAINTS.read_text(encoding="utf-8")
        assert "UQ_Employee_code" in text
        assert "UQF_ProjectMember_active" in text
        assert "BR-PRJ-002" in text

    def testIndexCatalogHasRequiredColumns(self) -> None:
        text = INDEXES.read_text(encoding="utf-8")
        header = next(line for line in text.splitlines() if line.startswith("| Index |"))
        for column in INDEX_COLUMNS:
            assert column in header, f"§56 column missing: {column}"
        # Unique + Tenant-scoped documented as legend columns U / T.
        assert "| U |" in header and "| T |" in header

    def testIndexCatalogCoversAllDomains(self) -> None:
        text = INDEXES.read_text(encoding="utf-8").lower()
        for domain in (
            "platform",
            "identity",
            "workforce",
            "project",
            "task",
            "document",
            "maintenance",
            "workflow",
            "communication",
            "ai",
            "integration",
            "billing",
            "evaluation",
        ):
            assert domain in text, f"index domain missing: {domain}"

    def testIndexEntriesDocumentedNotBare(self) -> None:
        text = INDEXES.read_text(encoding="utf-8")
        rows = [
            line for line in text.splitlines() if line.startswith("| `") or line.startswith("| UQ")
        ]
        assert len(rows) >= 50, "index catalogue too thin"
        for row in rows:
            assert "P1" in row or "P2" in row or "P3" in row, f"no importance: {row[:60]}"

    def testNoRedundantUniqueCodeWithoutTenant(self) -> None:
        text = CONSTRAINTS.read_text(encoding="utf-8")
        assert "tenantId" in text
        assert "GLOBAL" in text


class Phase5ErrorAndPolicyTests(SimpleTestCase):
    def testSpecErrorCodesRegistered(self) -> None:
        text = ERRORS.read_text(encoding="utf-8")
        for code in SPEC_ERROR_CODES:
            assert (
                code in text
                or code.replace("INVALID_STATE_TRANSITION", "STATE_INVALID_TRANSITION")
                .replace("PROJECT_ALREADY_COMPLETED", "STATE_PROJECT_ALREADY_COMPLETED")
                .replace("INVALID_WORKFLOW_TRANSITION", "WF_INVALID_TRANSITION")
                .replace("PERMISSION_DENIED", "PERM_PERMISSION_DENIED")
                .replace("TENANT_ACCESS_DENIED", "TENANT_ACCESS_DENIED")
                .replace("DUPLICATE_BUSINESS_CODE", "DUP_BUSINESS_CODE")
                in text
            ), f"spec error code missing: {code}"

    def testErrorCodesUnique(self) -> None:
        codes: list[str] = []
        for line in ERRORS.read_text(encoding="utf-8").splitlines():
            if line.startswith("| `"):
                codes.append(line.split("`")[1])
        assert len(codes) == len(set(codes)), "duplicate error codes (§61)"
        assert len(codes) >= 40

    def testErrorRowsDocumentCauseAndAction(self) -> None:
        text = ERRORS.read_text(encoding="utf-8")
        assert text.count("Client action") >= 5  # headers per section
        assert "correlationId" in text

    def testRetentionRulesHaveIds(self) -> None:
        text = RETENTION.read_text(encoding="utf-8")
        for i in range(1, 21):
            assert f"RET-{i:03d}" in text, f"RET-{i:03d} missing"
        for cls in ("L", "M", "S", "C"):
            assert cls in text

    def testMigrationStrategyExpandMigrateContract(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        assert "expand" in text.lower()
        assert "contract" in text.lower()
        assert "versioned" in text.lower()
        assert "backfill" in text.lower()

    def testBackupStrategyCoversThreeTypes(self) -> None:
        text = BACKUP.read_text(encoding="utf-8")
        for kind in ("Full", "Differential", "Transaction log"):
            assert kind in text, f"backup type missing: {kind} (§76)"
        for objective in ("RPO", "RTO"):
            assert objective in text, f"{objective} missing (§77)"
        assert "restore" in text.lower()

    def testGovernanceCoversSpecAreas(self) -> None:
        text = GOVERNANCE.read_text(encoding="utf-8")
        for topic in (
            "Reference data",
            "Seed",
            "secrets",
            "anonymized",
            "quality",
            "Steward",
        ):
            assert topic.lower() in text.lower(), f"governance topic missing: {topic}"


class Phase5DesignOnlyTests(SimpleTestCase):
    def testNoDjangoModelsOrMigrationsCreated(self) -> None:
        if CORE_APPS_DIR.exists():
            for app in CORE_APPS_DIR.iterdir():
                if not app.is_dir():
                    continue
                assert not (app / "models.py").exists(), f"§82 violated: {app}/models.py"
                assert not (app / "migrations").exists(), f"§82 violated: {app}/migrations"

    def testPhase5SetIsUnnumberedPerSpec(self) -> None:
        for name in PHASE5_FILES:
            assert not name[0].isdigit(), f"{name} must be unnumbered (§81)"

    def testReadmeMapsSection83Questions(self) -> None:
        text = (DATABASE_DIR / "README.md").read_text(encoding="utf-8")
        assert "§83 answerability map" in text
        assert "Phase 05 deliverables" in text
