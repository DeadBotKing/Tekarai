"""Architecture tests — Phase 04 database architecture documentation set.

Phase 04 is a DESIGN phase (docs/Phases/Phase4.md §52: no Django models yet).
These tests keep the §50 deliverable set verifiable and the §53 completion
criteria mechanically checked.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DATABASE_DIR = REPOSITORY_ROOT / "docs" / "database"


def readDoc(fileName: str) -> str:
    return (DATABASE_DIR / fileName).read_text(encoding="utf-8")


class Phase4DeliverableSetTests(SimpleTestCase):
    """Spec §50: the ten numbered deliverables exist and are substantial."""

    REQUIRED_DOCS = (
        "01EnterpriseERD.md",
        "02DomainERD.md",
        "03DatabaseDictionary.md",
        "04EntityCatalog.md",
        "05RelationshipCatalog.md",
        "06IndexStrategy.md",
        "07ConstraintCatalog.md",
        "08TenancyModel.md",
        "09AuditModel.md",
        "10DataRetentionPolicy.md",
    )

    def testAllDeliverablesExist(self) -> None:
        for docName in self.REQUIRED_DOCS:
            path = DATABASE_DIR / docName
            self.assertTrue(
                path.is_file() and path.stat().st_size > 1500,
                f"docs/database/{docName} is required by Phase 04 §50.",
            )

    def testEnterpriseErdContainsCrossCuttingRules(self) -> None:
        content = readDoc("01EnterpriseERD.md")
        for requiredStatement in (
            "UUID",  # §3 primary key strategy
            "deletedAt",  # §4/§5 base entity + soft delete
            "Decimal",  # §38 money
            "UTC",  # §39 time
            "SET_NULL",  # §31/§35 delete behaviors
            "CASCADE",  # §31 forbidden-by-default rule
            "normalized",  # §45
            "optimistic",  # §47 concurrency
        ):
            self.assertIn(requiredStatement, content)

    def testDomainErdCoversAllSpecGroups(self) -> None:
        content = readDoc("02DomainERD.md")
        for group in (
            "Platform Core",
            "Identity",
            "Organization",
            "Workforce",
            "Performance",
            "Project",
            "Task",
            "Asset",
            "Device",
            "Maintenance",
            "Document",
            "Workflow",
            "Communication",
            "Notification",
            "Audit",
            "Reporting",
            "Analytics",
            "AI",
            "Integration",
            "WinCC",
        ):
            self.assertIn(group, content, f"ERD group '{group}' missing.")
        self.assertGreaterEqual(content.count("```mermaid"), 19)


class EntityCatalogCompletenessTests(SimpleTestCase):
    """Spec §9–28 entity lists + §51 catalog attributes."""

    SPEC_ENTITIES: tuple[str, ...] = (
        # Platform Core / Tenancy / Configuration (§9)
        "Tenant",
        "SystemSetting",
        "Feature",
        "FeatureFlag",
        "Configuration",
        "Lookup",
        "LookupValue",
        "Tag",
        "TagAssignment",
        "CustomFieldDefinition",
        "CustomFieldValue",
        "Attachment",
        "Address",
        "ContactInformation",
        # Identity (§10)
        "User",
        "Role",
        "Permission",
        "RolePermission",
        "UserRole",
        "UserPermission",
        "Session",
        "AuthenticationMethod",
        "AccessPolicy",
        "SecurityEvent",
        # Organization (§11)
        "Organization",
        "OrganizationUnit",
        "Department",
        "Division",
        "Team",
        "Position",
        "JobTitle",
        "Location",
        "CostCenter",
        "OrganizationHierarchy",
        # Workforce (§12)
        "Employee",
        "Employment",
        "EmploymentHistory",
        "EmployeeAssignment",
        "EmployeeManager",
        "EmployeeContact",
        "EmployeeAddress",
        "EmployeeDocument",
        "EmployeeSkill",
        "Skill",
        "EmployeeCertification",
        "Certification",
        # Performance (evaluation entities of §12)
        "EmployeeEvaluation",
        "EvaluationCycle",
        "EvaluationCriteria",
        "EvaluationScore",
        # Project (§13)
        "Project",
        "ProjectMember",
        "ProjectRole",
        "ProjectPhase",
        "ProjectMilestone",
        "ProjectDependency",
        "ProjectBudget",
        "ProjectRisk",
        "ProjectIssue",
        "ProjectDocument",
        # Task (§14)
        "Task",
        "TaskStatus",
        "TaskPriority",
        "TaskType",
        "TaskAssignment",
        "TaskDependency",
        "TaskComment",
        "TaskAttachment",
        "TaskChecklist",
        "TaskChecklistItem",
        "TaskTimeEntry",
        "TaskHistory",
        # Asset (§15)
        "Asset",
        "AssetCategory",
        "AssetType",
        "AssetStatus",
        "AssetAssignment",
        "AssetLocation",
        "AssetOwnership",
        "AssetLifecycle",
        "AssetDocument",
        "AssetValueHistory",
        # Device / OT (§16)
        "Device",
        "DeviceType",
        "DeviceModel",
        "DeviceManufacturer",
        "DeviceStatus",
        "DeviceCredential",
        "DeviceRegistration",
        "DeviceHeartbeat",
        "DeviceTelemetry",
        "DeviceConfiguration",
        "DeviceEvent",
        "Agent",
        # Maintenance (§17)
        "MaintenancePlan",
        "MaintenanceSchedule",
        "MaintenanceWorkOrder",
        "MaintenanceTask",
        "MaintenanceEvent",
        "MaintenanceTechnician",
        "MaintenancePart",
        "MaintenanceCost",
        "MaintenanceHistory",
        # Document (§18)
        "Document",
        "DocumentVersion",
        "DocumentType",
        "DocumentCategory",
        "DocumentFolder",
        "DocumentPermission",
        "DocumentShare",
        "DocumentMetadata",
        "DocumentAttachment",
        "DocumentWorkflow",
        # Workflow (§19)
        "Workflow",
        "WorkflowVersion",
        "WorkflowDefinition",
        "WorkflowNode",
        "WorkflowTransition",
        "WorkflowInstance",
        "WorkflowInstanceState",
        "WorkflowTask",
        "WorkflowAction",
        "WorkflowApproval",
        "WorkflowHistory",
        # Communication (§20)
        "Conversation",
        "ConversationMember",
        "ConversationType",
        "Message",
        "MessageAttachment",
        "MessageReaction",
        "MessageReadReceipt",
        "Channel",
        "ChannelMember",
        "VoiceCall",
        "VoiceCallParticipant",
        "GroupCall",
        "VideoMeeting",
        "MeetingParticipant",
        "MeetingSession",
        "ScreenShareSession",
        "MeetingRecording",
        "Presence",
        "PresenceStatus",
        # Notification (§21)
        "Notification",
        "NotificationTemplate",
        "NotificationPreference",
        "NotificationChannel",
        "NotificationDelivery",
        "NotificationRecipient",
        # Audit (§22)
        "AuditEvent",
        # Reporting (§23)
        "ReportDefinition",
        "ReportParameter",
        "ReportExecution",
        "ReportSchedule",
        "ReportOutput",
        "ReportAccess",
        # Analytics (§24)
        "MetricDefinition",
        "MetricValue",
        "KpiDefinition",
        "KpiValue",
        "Dashboard",
        "DashboardWidget",
        "AnalyticsSnapshot",
        # AI (§25)
        "AiProvider",
        "AiModel",
        "AiModelVersion",
        "AiAgent",
        "AiAgentExecution",
        "AiRequest",
        "AiResponse",
        "AiConversation",
        "AiMessage",
        "AiKnowledgeSource",
        "AiKnowledgeDocument",
        "AiEmbedding",
        "AiRecommendation",
        "AiPrediction",
        "AiInsight",
        # Integration (§26)
        "Integration",
        "IntegrationType",
        "IntegrationCredential",
        "IntegrationEndpoint",
        "IntegrationConnection",
        "IntegrationMapping",
        "IntegrationJob",
        "IntegrationExecution",
        "IntegrationEvent",
        "IntegrationError",
        # WinCC extension (§28)
        "WinCcServer",
        "WinCcConnection",
        "WinCcTag",
        "WinCcTagValue",
        "WinCcAlarm",
        "WinCcEvent",
        "WinCcSyncJob",
    )

    def testCatalogCoversEverySpecEntity(self) -> None:
        content = readDoc("04EntityCatalog.md")
        missing = [entity for entity in self.SPEC_ENTITIES if f"| {entity} |" not in content]
        self.assertEqual(
            missing,
            [],
            f"Entities missing from the catalog: {missing}",
        )
        self.assertEqual(len(self.SPEC_ENTITIES), 195)

    def testCatalogStatesTotalAndAttributeMapping(self) -> None:
        content = readDoc("04EntityCatalog.md")
        self.assertIn("Total entities: 195", content)
        for attribute in (
            "Entity Name",
            "Domain",
            "Purpose",
            "Owner",
            "Primary Key",
            "Tenant Owned?",
            "Base Entity?",
            "Fields",
            "Foreign Keys",
            "Relationships",
            "Indexes",
            "Unique Constraints",
            "Delete Policy",
            "Audit Required?",
            "Soft Delete?",
            "Retention Policy",
            "Notes",
        ):
            self.assertIn(attribute, content, f"§51 attribute '{attribute}' not documented.")

    def testDictionaryMatchesCatalogEntities(self) -> None:
        dictionary = readDoc("03DatabaseDictionary.md")
        # Dictionary rows carry annotations after the name
        # (e.g. "| Tenant «base» T |"), so match name + delimiter.
        missing = [
            entity
            for entity in self.SPEC_ENTITIES
            if f"| {entity} " not in dictionary and f"| {entity} «" not in dictionary
        ]
        self.assertEqual(
            missing,
            [],
            f"Entities missing from the database dictionary: {missing}",
        )


class RelationshipCatalogTests(SimpleTestCase):
    """Spec §29–31, §35."""

    def testDeleteBehaviorsAndCascadeRegister(self) -> None:
        content = readDoc("05RelationshipCatalog.md")
        for behavior in ("PROTECT", "SET_NULL", "CASCADE", "APPEND", "SD"):
            self.assertIn(behavior, content)
        self.assertIn("CASCADE Justification Register", content)
        self.assertIn("Many-to-Many Resolutions", content)

    def testAuditColumnsUseSetNull(self) -> None:
        content = readDoc("05RelationshipCatalog.md")
        self.assertIn("createdBy/updatedBy/deletedBy", content)
        self.assertIn("SET_NULL", content)

    def testProjectTaskReferenceIsLoose(self) -> None:
        """Tasks stay independent of Project internals (spec §13/§14)."""
        content = readDoc("05RelationshipCatalog.md")
        self.assertIn("Project → Task", content)
        self.assertIn("SET_NULL", content)


class StrategyCatalogTests(SimpleTestCase):
    """Spec §32–34, §22, §48."""

    def testIndexStrategyHasStandardCompositesAndGates(self) -> None:
        content = readDoc("06IndexStrategy.md")
        for pattern in ("(tenantId", "(tenantId, status)", "(tenantId, createdAt)"):
            self.assertIn(pattern, content)
        self.assertIn("query pattern", content.lower())

    def testConstraintCatalogIsTenantAware(self) -> None:
        content = readDoc("07ConstraintCatalog.md")
        self.assertIn("(tenantId, code)", content)
        self.assertIn("Controlled Vocabulary", content)

    def testTenancyModelDefinesIsolationLayers(self) -> None:
        content = readDoc("08TenancyModel.md")
        for layer in ("Application", "Repository", "Database", "Authorization"):
            self.assertIn(layer, content)
        self.assertIn("code", content)  # spec §7 tenant fields

    def testAuditModelContainsSpecFields(self) -> None:
        content = readDoc("09AuditModel.md")
        for field in (
            "actorId",
            "action",
            "entityType",
            "entityId",
            "timestamp",
            "ipAddress",
            "userAgent",
            "beforeState",
            "afterState",
            "metadata",
            "correlationId",
            "tenantId",
        ):
            self.assertIn(field, content, f"AuditEvent field '{field}' (spec §22) missing.")
        self.assertIn("append", content.lower())

    def testRetentionPolicyCoversSpecClasses(self) -> None:
        content = readDoc("10DataRetentionPolicy.md")
        for domain in ("Audit", "Documents", "Telemetry", "Notifications"):
            self.assertIn(domain, content)
        self.assertIn("configurable", content.lower())


class Phase4StillDesignOnlyTests(SimpleTestCase):
    """Spec §52: no Django models/migrations may exist after Phase 04."""

    def testNoModelFilesOrMigrationsExist(self) -> None:
        appsDir = Path(__file__).resolve().parents[2] / "apps"
        modelFiles = [path for path in appsDir.rglob("models.py") if "venv" not in path.parts]
        self.assertEqual(modelFiles, [])
        migrationDirs = [path for path in appsDir.rglob("migrations") if path.is_dir()]
        self.assertEqual(migrationDirs, [])
