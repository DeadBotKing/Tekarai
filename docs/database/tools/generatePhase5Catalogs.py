#!/usr/bin/env python3
"""Generate the Phase-05 catalog documents from a single entity dataset.

Outputs (into docs/database/):
  - DatabaseDictionary.md   (spec §2/§63 format, every entity)
  - EntityCatalog.md        (spec §64 attributes, every entity)
  - FieldCatalog.md         (spec §65 field rows, every entity)

Rationale: one dataset -> three consistent catalogs. Regenerate with:
  python docs/database/tools/generatePhase5Catalogs.py
"""

from __future__ import annotations

from dataclasses import dataclass, field as dcField
from pathlib import Path
from typing import Optional

DATABASE_DIR = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Field primitives
# ---------------------------------------------------------------------------

UUID = "uuid"
BOOL = "boolean"
DT = "datetime (UTC)"
DATE = "date"
TIME = "time"
INT = "integer"
BIGINT = "bigint"
JSON = "json"


def vc(n: int) -> str:
    return f"varchar({n})"


def nvc(n) -> str:
    return f"nvarchar({n})"


def dec(p: int, s: int) -> str:
    return f"decimal({p},{s})"


def en(name: str) -> str:
    return f"enum({name})"


@dataclass
class FieldSpec:
    name: str
    type: str
    required: bool
    default: str = "—"
    unique: bool = False
    indexed: bool = False
    fk: str = "—"
    description: str = ""

    def row(self) -> list[str]:
        return [
            self.name,
            self.type,
            "YES" if self.required else "no",
            "no" if self.required else "YES",
            self.default,
            "YES" if self.unique else "—",
            "YES" if self.indexed else "—",
            self.fk,
            self.description,
        ]


def f(
    name: str,
    type: str,
    req: bool = True,
    default: str = "—",
    unique: bool = False,
    indexed: bool = False,
    fk: str = "—",
    desc: str = "",
) -> FieldSpec:
    return FieldSpec(name, type, req, default, unique, indexed, fk, desc)


# ---------------------------------------------------------------------------
# Entity model
# ---------------------------------------------------------------------------

KIND_BASE = "base"      # full base-entity field block
KIND_APPEND = "append"  # append-only reduced block
KIND_LINK = "link"      # association entity (base block + link fields)
KIND_VOCAB = "vocab"    # reference data (base block + code/name/description)

GLOBAL = "GLOBAL"
TENANT = "TENANT_SCOPED"
HYBRID = "HYBRID"


@dataclass
class Entity:
    name: str
    group: str
    owner: str
    purpose: str
    tenantMode: str
    kind: str
    fields: list[FieldSpec] = dcField(default_factory=list)
    identity: str = "—"            # business identity field (§12)
    statusEnum: str = "—"          # state machine binding (§69)
    auditable: str = "✓"
    retention: str = "L"
    versioned: bool = False        # optimistic concurrency (§50)
    hardDelete: str = "—"          # explicit hard-delete policy note

    @property
    def softDeletable(self) -> str:
        return "✗ (append-only)" if self.kind == KIND_APPEND else "✓"


ENTITIES: list[Entity] = []

V = KIND_VOCAB
B = KIND_BASE
A = KIND_APPEND
L = KIND_LINK


def add(e: Entity) -> None:
    ENTITIES.append(e)


# =============================== PLATFORM ==================================
add(Entity("Tenant", "Platform Core · Tenancy · Configuration", "Tenancy",
    "Top isolation boundary of the platform.", GLOBAL, B, [
        f("name", nvc(160), True, desc="Display name (unique per scope, BR-TEN-004)"),
        f("code", vc(64), True, unique=True, indexed=True, desc="Global-unique platform code"),
        f("description", nvc(1000), False),
        f("status", en("tenantStatus"), True, desc="active · suspended · closed"),
    ], identity="code", statusEnum="Tenant", retention="L", hardDelete="never (lifecycle close only)"))

add(Entity("SystemSetting", "Platform Core · Tenancy · Configuration", "Configuration",
    "System-scoped runtime setting.", GLOBAL, B, [
        f("scope", en("settingScope"), True, desc="system"),
        f("key", vc(190), True, unique=True, indexed=True, desc="UNIQUE(scope, key)"),
        f("value", nvc("max"), False),
        f("valueType", vc(32), True, desc="string · int · bool · json · decimal"),
        f("isSecret", BOOL, True, default="false", desc="value never returned raw"),
    ], retention="L"))

add(Entity("Feature", "Platform Core · Tenancy · Configuration", "Configuration",
    "Registered product feature.", GLOBAL, V, [
        f("category", vc(64), True, indexed=True),
    ], identity="code", retention="L"))

add(Entity("FeatureFlag", "Platform Core · Tenancy · Configuration", "Configuration",
    "Feature-flag state per scope.", HYBRID, B, [
        f("featureId", UUID, True, fk="Feature", desc="UNIQUE(featureId, scopeType, tenantId)"),
        f("scopeType", en("flagScope"), True, desc="system · tenant"),
        f("enabled", BOOL, True, default="false", desc="flag default off (BR-DAT-006)"),
        f("note", nvc(500), False),
    ], retention="M"))

add(Entity("Configuration", "Platform Core · Tenancy · Configuration", "Configuration",
    "Scoped configuration entry.", HYBRID, B, [
        f("scope", en("configScope"), True, desc="system · tenant"),
        f("key", vc(190), True, desc="UNIQUE(tenantId, scope, key)"),
        f("value", nvc("max"), False),
        f("schemaRef", vc(190), False, desc="validation schema reference"),
    ], retention="L"))

add(Entity("Lookup", "Platform Core · Tenancy · Configuration", "Configuration",
    "Controlled list group.", TENANT, V, [], retention="M"))

add(Entity("LookupValue", "Platform Core · Tenancy · Configuration", "Configuration",
    "Controlled list entry.", TENANT, B, [
        f("lookupId", UUID, True, fk="Lookup", desc="UNIQUE(tenantId, lookupId, code)"),
        f("code", vc(64), True, indexed=True),
        f("label", nvc(200), True),
        f("sortOrder", INT, True, default="0"),
    ], identity="code", retention="M"))

add(Entity("Tag", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Free taxonomy tag.", TENANT, B, [
        f("name", nvc(120), True, desc="UNIQUE(tenantId, name)"),
        f("color", vc(16), False),
    ], retention="M"))

add(Entity("TagAssignment", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Polymorphic tag link (append-only).", TENANT, A, [
        f("tagId", UUID, True, fk="Tag", indexed=True, desc="UNIQUE(tagId, ownerType, ownerId)"),
        f("ownerType", vc(64), True, indexed=True),
        f("ownerId", UUID, True, indexed=True),
    ], retention="M", auditable="△"))

add(Entity("CustomFieldDefinition", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Extension field schema (spec §42).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("targetType", vc(64), True, indexed=True),
        f("fieldType", en("customFieldType"), True),
        f("config", JSON, False, desc="documented JSON use: field config"),
        f("validation", JSON, False, desc="documented JSON use: validation rules"),
    ], identity="code", retention="L"))

add(Entity("CustomFieldValue", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Extension field data.", TENANT, B, [
        f("definitionId", UUID, True, fk="CustomFieldDefinition"),
        f("ownerType", vc(64), True, indexed=True),
        f("ownerId", UUID, True, indexed=True, desc="UNIQUE(definitionId, ownerType, ownerId)"),
        f("value", nvc("max"), False),
    ], retention="L", auditable="△"))

add(Entity("Attachment", "Platform Core · Tenancy · Configuration", "Platform Core",
    "File metadata record (binary in object storage, §40).", TENANT, B, [
        f("ownerType", vc(64), True, indexed=True),
        f("ownerId", UUID, True, indexed=True),
        f("fileName", nvc(260), True),
        f("storageProvider", vc(32), True),
        f("storageKey", vc(512), True, desc="never a local path assumption"),
        f("mimeType", vc(127), True),
        f("fileSize", BIGINT, True, desc="bytes"),
        f("checksum", vc(128), True, desc="change/duplicate detection (§40)"),
    ], retention="M"))

add(Entity("Address", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Reusable postal address.", TENANT, B, [
        f("ownerType", vc(64), True, indexed=True),
        f("ownerId", UUID, True, indexed=True),
        f("line1", nvc(200), True),
        f("line2", nvc(200), False),
        f("city", nvc(120), True),
        f("country", vc(2), True, desc="ISO 3166-1 alpha-2"),
        f("postalCode", vc(20), True),
        f("latitude", dec(9, 6), False),
        f("longitude", dec(9, 6), False),
    ], retention="L", auditable="—"))

add(Entity("ContactInformation", "Platform Core · Tenancy · Configuration", "Platform Core",
    "Reusable contact record.", TENANT, B, [
        f("ownerType", vc(64), True, indexed=True),
        f("ownerId", UUID, True, indexed=True),
        f("contactType", en("contactType"), True),
        f("value", nvc(250), True),
        f("isPrimary", BOOL, True, default="false"),
    ], retention="L", auditable="—"))

# =============================== IDENTITY ==================================
add(Entity("User", "Identity", "Identity",
    "Authentication principal (≠ Employee, §15).", TENANT, B, [
        f("username", vc(150), True, indexed=True, desc="UNIQUE(tenantId, username)"),
        f("email", nvc(254), True, indexed=True, desc="UNIQUE(tenantId, email)"),
        f("displayName", nvc(200), True),
        f("passwordHash", vc(255), True, desc="hashed only; never logged"),
        f("userType", en("userType"), True, desc="person · service · agent"),
        f("status", en("userStatus"), True, desc="see StateMachine: User"),
        f("lastLoginAt", DT, False),
        f("mustChangePassword", BOOL, True, default="false"),
    ], identity="username", statusEnum="User", retention="L", versioned=True))

add(Entity("Role", "Identity", "Identity",
    "Role definition.", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(160), True),
        f("isSystem", BOOL, True, default="false", desc="system roles undeletable"),
    ], identity="code", retention="L"))

add(Entity("Permission", "Identity", "Identity",
    "Action-based permission catalogue (§42).", GLOBAL, V, [
        f("resource", vc(64), True, indexed=True, desc="e.g. project"),
        f("action", vc(64), True, desc="e.g. view · create · approve"),
        f("scope", en("permissionScope"), False),
    ], identity="code", retention="L"))

add(Entity("RolePermission", "Identity", "Identity",
    "Role↔permission link.", TENANT, L, [
        f("roleId", UUID, True, fk="Role"),
        f("permissionId", UUID, True, fk="Permission", desc="UNIQUE(roleId, permissionId)"),
    ], retention="L", auditable="△"))

add(Entity("UserRole", "Identity", "Identity",
    "Scoped user↔role grant.", TENANT, L, [
        f("userId", UUID, True, fk="User", indexed=True),
        f("roleId", UUID, True, fk="Role", indexed=True),
        f("scopeType", en("roleScope"), True, desc="GLOBAL·TENANT·ORG·DEPT·PROJECT (§43)"),
        f("scopeId", UUID, False),
        f("grantedBy", UUID, True, fk="User"),
        f("grantedAt", DT, True, desc="UNIQUE(userId, roleId, scopeType, scopeId)"),
    ], retention="L"))

add(Entity("UserPermission", "Identity", "Identity",
    "Direct user permission (allow/deny).", TENANT, L, [
        f("userId", UUID, True, fk="User", indexed=True),
        f("permissionId", UUID, True, fk="Permission"),
        f("effect", en("permissionEffect"), True, desc="allow · deny"),
        f("scopeType", en("roleScope"), False),
        f("scopeId", UUID, False),
    ], retention="L"))

add(Entity("Session", "Identity", "Identity",
    "Session/token record.", TENANT, B, [
        f("userId", UUID, True, fk="User", indexed=True),
        f("tokenHash", vc(255), True, desc="hash only; UNIQUE(userId, tokenHash)"),
        f("issuedAt", DT, True),
        f("expiresAt", DT, True, indexed=True, desc="expiry sweep index"),
        f("revokedAt", DT, False),
        f("ipAddress", vc(45), False),
        f("userAgent", nvc(500), False),
    ], statusEnum="Session", retention="S"))

add(Entity("AuthenticationMethod", "Identity", "Identity",
    "Authentication factor (MFA-ready).", TENANT, B, [
        f("userId", UUID, True, fk="User"),
        f("methodType", en("authMethodType"), True),
        f("secretRef", vc(255), True, desc="secret-manager reference"),
        f("verifiedAt", DT, False),
    ], retention="M"))

add(Entity("AccessPolicy", "Identity", "Identity",
    "Access policy rule.", TENANT, B, [
        f("subjectType", vc(64), True, indexed=True),
        f("subjectId", UUID, False, indexed=True),
        f("resource", vc(64), True, indexed=True),
        f("effect", en("permissionEffect"), True),
        f("condition", JSON, False, desc="documented JSON use: policy condition"),
        f("priority", INT, True, default="0"),
    ], retention="L"))

add(Entity("SecurityEvent", "Identity", "Identity",
    "Append-only security telemetry.", TENANT, A, [
        f("userId", UUID, False, fk="User", indexed=True),
        f("eventType", en("securityEventType"), True, indexed=True),
        f("severity", en("severityLevel"), True),
        f("ipAddress", vc(45), False),
        f("userAgent", nvc(500), False),
        f("metadata", JSON, False, desc="documented JSON use: event detail"),
    ], retention="L", auditable="△"))

# ============================= ORGANIZATION ================================
add(Entity("Organization", "Organization", "Organization",
    "Legal-entity root of tenant structure.", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(200), True),
        f("legalId", vc(64), False, desc="registration number"),
        f("orgType", en("organizationType"), True),
        f("parentId", UUID, False, fk="Organization"),
    ], identity="code", retention="L", versioned=True))

add(Entity("OrganizationUnit", "Organization", "Organization",
    "Generic hierarchy node (typed by children).", TENANT, B, [
        f("organizationId", UUID, True, fk="Organization", indexed=True),
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, organizationId, code)"),
        f("name", nvc(200), True),
        f("unitType", en("orgUnitType"), True, desc="root · division · department · team"),
        f("parentId", UUID, False, fk="OrganizationUnit", indexed=True, desc="acyclic (BR-ORG-001)"),
    ], identity="code", retention="L", versioned=True))

add(Entity("Department", "Organization", "Organization",
    "Department typed unit.", TENANT, B, [
        f("organizationUnitId", UUID, True, fk="OrganizationUnit", desc="1:1"),
        f("headUserId", UUID, False, fk="User"),
        f("costCenterId", UUID, False, fk="CostCenter"),
    ], identity="code", retention="L"))
add(Entity("Division", "Organization", "Organization", "Division typed unit.", TENANT, B, [
    f("organizationUnitId", UUID, True, fk="OrganizationUnit", desc="1:1"),
    f("leadUserId", UUID, False, fk="User"),
], identity="code", retention="L"))
add(Entity("Team", "Organization", "Organization", "Team typed unit.", TENANT, B, [
    f("organizationUnitId", UUID, True, fk="OrganizationUnit", desc="1:1"),
    f("leadUserId", UUID, False, fk="User"),
], identity="code", retention="L"))

add(Entity("Position", "Organization", "Organization",
    "Organizational position definition.", TENANT, B, [
        f("organizationId", UUID, True, fk="Organization", indexed=True),
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("title", nvc(200), True),
        f("jobTitleId", UUID, False, fk="JobTitle"),
        f("grade", vc(32), False),
    ], identity="code", retention="L"))

add(Entity("JobTitle", "Organization", "Organization", "Job-title catalogue.", TENANT, V, [
    f("level", INT, False),
], retention="L"))

add(Entity("Location", "Organization", "Organization", "Physical site.", TENANT, B, [
    f("organizationId", UUID, True, fk="Organization"),
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("addressId", UUID, False, fk="Address"),
    f("latitude", dec(9, 6), False),
    f("longitude", dec(9, 6), False),
], identity="code", retention="L"))

add(Entity("CostCenter", "Organization", "Organization", "Cost center.", TENANT, B, [
    f("organizationId", UUID, True, fk="Organization"),
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("responsibleUserId", UUID, False, fk="User"),
], identity="code", retention="L"))

add(Entity("OrganizationHierarchy", "Organization", "Organization",
    "Temporal hierarchy facts (§36).", TENANT, A, [
        f("unitId", UUID, True, fk="OrganizationUnit", indexed=True),
        f("parentId", UUID, True, fk="OrganizationUnit", indexed=True),
        f("validFrom", DATE, True),
        f("validTo", DATE, False),
    ], retention="L"))

# =============================== WORKFORCE =================================
add(Entity("Employee", "Workforce / HR", "Workforce",
    "Person/employment record (≠ User, §15/§16).", TENANT, B, [
        f("employeeNumber", vc(64), True, indexed=True, desc="UNIQUE(tenantId, employeeNumber)"),
        f("firstName", nvc(120), True),
        f("lastName", nvc(120), True),
        f("nationalIdRef", vc(255), False, desc="secret reference (privacy)"),
        f("birthDate", DATE, False),
        f("userId", UUID, False, fk="User", unique=True, indexed=True, desc="optional 1:1 link"),
        f("status", en("employeeStatus"), True, desc="see StateMachine: Employee"),
    ], identity="employeeNumber", statusEnum="Employee", retention="L", versioned=True))

add(Entity("Employment", "Workforce / HR", "Workforce",
    "Employment record.", TENANT, B, [
        f("employeeId", UUID, True, fk="Employee", indexed=True),
        f("organizationId", UUID, True, fk="Organization"),
        f("positionId", UUID, True, fk="Position"),
        f("employmentType", en("employmentType"), True),
        f("startDate", DATE, True),
        f("endDate", DATE, False, desc="null = ongoing (one active per employee)"),
        f("status", en("employmentStatus"), True),
    ], retention="L"))

add(Entity("EmploymentHistory", "Workforce / HR", "Workforce",
    "Append-only employment facts.", TENANT, A, [
        f("employmentId", UUID, True, fk="Employment", indexed=True),
        f("changeType", en("employmentChangeType"), True),
        f("snapshot", JSON, False, desc="documented JSON use: point-in-time snapshot"),
        f("changedAt", DT, True),
    ], retention="L"))

add(Entity("EmployeeAssignment", "Workforce / HR", "Workforce",
    "Temporal unit assignment (§16: history preserved).", TENANT, B, [
        f("employeeId", UUID, True, fk="Employee", indexed=True),
        f("organizationUnitId", UUID, True, fk="OrganizationUnit", indexed=True),
        f("startDate", DATE, True),
        f("endDate", DATE, False),
        f("allocationPercentage", dec(5, 2), True, default="100.00", desc="0–100"),
    ], retention="L"))

add(Entity("EmployeeManager", "Workforce / HR", "Workforce",
    "Reporting relationship (temporal).", TENANT, B, [
        f("employeeId", UUID, True, fk="Employee", indexed=True),
        f("managerId", UUID, True, fk="Employee", indexed=True, desc="not self (BR-WF-002)"),
        f("reportingType", en("reportingType"), True),
        f("validFrom", DATE, True),
        f("validTo", DATE, False),
    ], retention="L"))

add(Entity("EmployeeContact", "Workforce / HR", "Workforce", "Employee contacts.", TENANT, B, [
    f("employeeId", UUID, True, fk="Employee"),
    f("contactType", en("contactType"), True),
    f("value", nvc(250), True, desc="UNIQUE(employeeId, contactType, value)"),
    f("isPrimary", BOOL, True, default="false"),
], retention="M", auditable="—"))

add(Entity("EmployeeAddress", "Workforce / HR", "Workforce", "Employee addresses.", TENANT, B, [
    f("employeeId", UUID, True, fk="Employee"),
    f("addressId", UUID, True, fk="Address", desc="UNIQUE(employeeId, addressId)"),
    f("addressType", en("addressType"), True),
    f("validFrom", DATE, True),
    f("validTo", DATE, False),
], retention="L", auditable="—"))

add(Entity("EmployeeDocument", "Workforce / HR", "Workforce", "Employee↔document link.", TENANT, L, [
    f("employeeId", UUID, True, fk="Employee"),
    f("documentId", UUID, True, fk="Document", indexed=True,
      desc="UNIQUE(employeeId, documentId, documentRole)"),
    f("documentRole", en("employeeDocumentRole"), True),
], retention="L", auditable="△"))

add(Entity("EmployeeSkill", "Workforce / HR", "Workforce", "Employee skill level.", TENANT, L, [
    f("employeeId", UUID, True, fk="Employee"),
    f("skillId", UUID, True, fk="Skill", indexed=True, desc="UNIQUE(employeeId, skillId)"),
    f("skillLevel", en("skillLevel"), True),
    f("verifiedBy", UUID, False, fk="User"),
], retention="M", auditable="—"))

add(Entity("Skill", "Workforce / HR", "Workforce", "Skill catalogue.", TENANT, V, [
    f("category", vc(64), False),
], retention="M", auditable="—"))

add(Entity("EmployeeCertification", "Workforce / HR", "Workforce", "Employee certification.", TENANT, B, [
    f("employeeId", UUID, True, fk="Employee"),
    f("certificationId", UUID, True, fk="Certification", indexed=True,
      desc="UNIQUE(employeeId, certificationId, issuedAt)"),
    f("issuedAt", DATE, True),
    f("expiresAt", DATE, False),
    f("certificateRef", vc(255), False, desc="storage reference"),
], retention="M", auditable="—"))

add(Entity("Certification", "Workforce / HR", "Workforce", "Certification catalogue.", TENANT, V, [
    f("issuer", nvc(200), False),
], retention="M", auditable="—"))

# ============================== PERFORMANCE ================================
add(Entity("EvaluationCycle", "Performance", "Performance",
    "Evaluation period.", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("periodType", en("periodType"), True, desc="daily·weekly·monthly·quarterly·annual"),
        f("startDate", DATE, True),
        f("endDate", DATE, True, desc="≥ startDate (BR-DAT-002)"),
        f("status", en("cycleStatus"), True, desc="see StateMachine: EvaluationCycle"),
    ], identity="code", statusEnum="EvaluationCycle", retention="L", versioned=True))

add(Entity("EmployeeEvaluation", "Performance", "Performance",
    "Aggregate root of one evaluation (Phase 03 §6).", TENANT, B, [
        f("evaluationCycleId", UUID, True, fk="EvaluationCycle", indexed=True,
          desc="UNIQUE(evaluationCycleId, employeeId)"),
        f("employeeId", UUID, True, fk="Employee", indexed=True),
        f("status", en("evaluationStatus"), True),
        f("submittedAt", DT, False),
        f("resultSummary", nvc("max"), False),
    ], retention="L", versioned=True))

add(Entity("EvaluationCriteria", "Performance", "Performance",
    "Criterion per cycle.", TENANT, B, [
        f("evaluationCycleId", UUID, True, fk="EvaluationCycle"),
        f("code", vc(64), True, desc="UNIQUE(evaluationCycleId, code)"),
        f("name", nvc(200), True),
        f("weight", dec(5, 2), True, desc="Σ weight = 100 per cycle (BR-DAT-004)"),
        f("maxScore", dec(6, 2), True),
    ], retention="L"))

add(Entity("EvaluationScore", "Performance", "Performance",
    "Score per criterion/reviewer (editable + audited).", TENANT, B, [
        f("evaluationId", UUID, True, fk="EmployeeEvaluation", indexed=True,
          desc="UNIQUE(evaluationId, criteriaId, reviewerId)"),
        f("criteriaId", UUID, True, fk="EvaluationCriteria"),
        f("reviewerId", UUID, True, fk="User", indexed=True),
        f("weight", dec(5, 2), True, desc="reviewer weight"),
        f("score", dec(6, 2), True, desc="within criteria bounds (BR-DAT-005)"),
        f("changedAt", DT, True, desc="every change audited (BR-AUD-004)"),
    ], retention="L", versioned=True))

# ================================ PROJECTS =================================
add(Entity("Project", "Project", "Projects",
    "Project aggregate root.", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code); e.g. PRJ-2026-001"),
        f("name", nvc(200), True),
        f("description", nvc("max"), False),
        f("status", en("projectStatus"), True, desc="see StateMachine: Project"),
        f("ownerId", UUID, False, fk="User", desc="required unless status=DRAFT (BR-PRJ-001)"),
        f("startDate", DATE, False),
        f("plannedEndDate", DATE, False),
        f("actualEndDate", DATE, False),
        f("organizationUnitId", UUID, False, fk="OrganizationUnit"),
        f("budgetAmount", dec(19, 4), False, desc="money: decimal, never float (§52)"),
        f("budgetCurrency", vc(3), False, desc="ISO 4217"),
    ], identity="code", statusEnum="Project", retention="L", versioned=True))

add(Entity("ProjectMember", "Project", "Projects",
    "Project membership with data (§19).", TENANT, L, [
        f("projectId", UUID, True, fk="Project", indexed=True),
        f("memberType", en("memberType"), True, desc="user · employee"),
        f("memberId", UUID, True, indexed=True, desc="ONE ACTIVE membership per person per project (BR-PRJ-002)"),
        f("projectRoleId", UUID, True, fk="ProjectRole"),
        f("joinedAt", DT, True),
        f("leftAt", DT, False, desc="null = active"),
        f("allocationPercentage", dec(5, 2), False),
    ], retention="M"))

add(Entity("ProjectRole", "Project", "Projects", "Project role catalogue.", TENANT, V, [],
    retention="L", auditable="△"))

add(Entity("ProjectPhase", "Project", "Projects", "Project phase.", TENANT, B, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("name", nvc(200), True),
    f("sortOrder", INT, True, default="0", desc="UNIQUE(projectId, sortOrder)"),
    f("startDate", DATE, False),
    f("endDate", DATE, False),
    f("status", en("phaseStatus"), True),
], retention="L"))

add(Entity("ProjectMilestone", "Project", "Projects", "Project milestone.", TENANT, B, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("projectPhaseId", UUID, False, fk="ProjectPhase"),
    f("name", nvc(200), True, desc="UNIQUE(projectId, name)"),
    f("dueDate", DATE, False, indexed=True),
    f("achievedDate", DATE, False),
    f("status", en("milestoneStatus"), True),
], retention="L"))

add(Entity("ProjectDependency", "Project", "Projects", "Project↔project dependency.", TENANT, L, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("dependsOnProjectId", UUID, True, fk="Project", indexed=True,
      desc="not self; acyclic (BR-DAT-008)"),
    f("dependencyType", en("projectDependencyType"), True),
], retention="M", auditable="△"))

add(Entity("ProjectBudget", "Project", "Projects", "Budget line.", TENANT, B, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("amount", dec(19, 4), True, desc="≥ 0 (CHECK, §55)"),
    f("currency", vc(3), True, desc="ISO 4217"),
    f("fiscalPeriod", vc(20), True, desc="UNIQUE(projectId, fiscalPeriod)"),
    f("note", nvc(500), False),
], retention="L"))

add(Entity("ProjectRisk", "Project", "Projects", "Risk register entry.", TENANT, B, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("title", nvc(250), True, desc="UNIQUE(projectId, title)"),
    f("probability", en("riskLevel"), True),
    f("impact", en("riskLevel"), True),
    f("mitigation", nvc("max"), False),
    f("status", en("riskStatus"), True, indexed=True),
], retention="M"))

add(Entity("ProjectIssue", "Project", "Projects", "Issue register entry.", TENANT, B, [
    f("projectId", UUID, True, fk="Project", indexed=True),
    f("title", nvc(250), True, desc="UNIQUE(projectId, title)"),
    f("severity", en("issueSeverity"), True),
    f("resolvedAt", DT, False),
    f("status", en("issueStatus"), True, indexed=True),
], retention="M"))

add(Entity("ProjectDocument", "Project", "Projects", "Project↔document link.", TENANT, L, [
    f("projectId", UUID, True, fk="Project"),
    f("documentId", UUID, True, fk="Document", indexed=True,
      desc="UNIQUE(projectId, documentId, documentRole)"),
    f("documentRole", en("projectDocumentRole"), True),
], retention="L", auditable="△"))

# ================================= TASKS ===================================
add(Entity("Task", "Task", "Tasks",
    "Task aggregate root (project-optional, §20).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("title", nvc(250), True),
        f("description", nvc("max"), False),
        f("projectId", UUID, False, fk="Project", indexed=True,
          desc="nullable — task usable standalone (BR-TSK-001)"),
        f("statusId", UUID, True, fk="TaskStatus", indexed=True, desc="(projectId,statusId) board index"),
        f("priorityId", UUID, True, fk="TaskPriority"),
        f("typeId", UUID, True, fk="TaskType"),
        f("parentTaskId", UUID, False, fk="Task", desc="subtask reference"),
        f("startDate", DT, False),
        f("deadlineAt", DT, False, indexed=True, desc="≥ startDate (BR-DAT-003)"),
        f("estimateMinutes", INT, False),
    ], identity="code", statusEnum="Task", retention="L", versioned=True))

add(Entity("TaskStatus", "Task", "Tasks", "Task status vocabulary.", TENANT, V, [
    f("sortOrder", INT, True, default="0"),
    f("isTerminal", BOOL, True, default="false"),
], retention="L", auditable="△"))
add(Entity("TaskPriority", "Task", "Tasks", "Task priority vocabulary.", TENANT, V, [
    f("level", INT, True),
], retention="L", auditable="—"))
add(Entity("TaskType", "Task", "Tasks", "Task type vocabulary.", TENANT, V, [], retention="L", auditable="—"))

add(Entity("TaskAssignment", "Task", "Tasks", "Task↔user assignment with data.", TENANT, L, [
    f("taskId", UUID, True, fk="Task", indexed=True),
    f("userId", UUID, True, fk="User", indexed=True,
      desc="UNIQUE(taskId, userId, assignedAt)"),
    f("assignmentRole", en("taskAssignmentRole"), True),
    f("assignedAt", DT, True),
    f("removedAt", DT, False, desc="null = active"),
], retention="M"))

add(Entity("TaskDependency", "Task", "Tasks",
    "Task→task dependency (§21).", TENANT, L, [
        f("taskId", UUID, True, fk="Task", indexed=True),
        f("dependsOnTaskId", UUID, True, fk="Task", indexed=True,
          desc="not self; acyclic (BR-TSK-002)"),
        f("dependencyType", en("taskDependencyType"), True),
        f("lagMinutes", INT, False, default="0"),
    ], retention="M", auditable="△"))

add(Entity("TaskComment", "Task", "Tasks", "Append-oriented comments.", TENANT, A, [
    f("taskId", UUID, True, fk="Task", indexed=True),
    f("userId", UUID, True, fk="User"),
    f("body", nvc("max"), True),
    f("parentId", UUID, False, fk="TaskComment"),
    f("editedAt", DT, False, desc="edit appends revision (BR-TSK-003)"),
], retention="M", auditable="△"))

add(Entity("TaskAttachment", "Task", "Tasks", "Task attachment link.", TENANT, L, [
    f("taskId", UUID, True, fk="Task"),
    f("attachmentId", UUID, True, fk="Attachment", desc="UNIQUE(taskId, attachmentId)"),
], retention="M", auditable="△"))

add(Entity("TaskChecklist", "Task", "Tasks", "Task checklist.", TENANT, B, [
    f("taskId", UUID, True, fk="Task", indexed=True),
    f("title", nvc(200), True),
    f("sortOrder", INT, True, default="0"),
], retention="M", auditable="△"))

add(Entity("TaskChecklistItem", "Task", "Tasks",
    "Checklist item (justified CASCADE child).", TENANT, B, [
        f("checklistId", UUID, True, fk="TaskChecklist"),
        f("label", nvc(250), True, desc="UNIQUE(checklistId, label)"),
        f("isDone", BOOL, True, default="false"),
        f("doneAt", DT, False),
        f("doneBy", UUID, False, fk="User"),
    ], retention="M", auditable="△"))

add(Entity("TaskTimeEntry", "Task", "Tasks", "Time tracking (append-only).", TENANT, A, [
    f("taskId", UUID, True, fk="Task", indexed=True),
    f("userId", UUID, True, fk="User", indexed=True),
    f("minutes", INT, True, desc="> 0"),
    f("startedAt", DT, False),
    f("endedAt", DT, False),
    f("note", nvc(500), False),
], retention="M", auditable="△"))

add(Entity("TaskHistory", "Task", "Tasks", "Append-only activity stream.", TENANT, A, [
    f("taskId", UUID, True, fk="Task", indexed=True),
    f("actorId", UUID, False, fk="User"),
    f("changeType", en("taskChangeType"), True),
    f("beforeState", JSON, False, desc="documented JSON use: snapshot"),
    f("afterState", JSON, False, desc="documented JSON use: snapshot"),
    f("changedAt", DT, True, indexed=True),
], retention="L"))

# ================================= ASSETS ==================================
add(Entity("Asset", "Asset", "Assets",
    "Enterprise asset root (§24).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(200), True),
        f("assetCategoryId", UUID, True, fk="AssetCategory"),
        f("assetTypeId", UUID, True, fk="AssetType", indexed=True),
        f("statusId", UUID, True, fk="AssetStatus", indexed=True),
        f("serialNumber", vc(120), False),
        f("acquisitionDate", DATE, False),
        f("ownershipType", en("assetOwnershipType"), True, desc="physical·digital·financial·operational"),
    ], identity="code", statusEnum="Asset", retention="L", versioned=True))

add(Entity("AssetCategory", "Asset", "Assets", "Asset category tree.", TENANT, V, [
    f("parentId", UUID, False, fk="AssetCategory"),
], retention="L", auditable="△"))
add(Entity("AssetType", "Asset", "Assets", "Asset type.", TENANT, B, [
    f("assetCategoryId", UUID, True, fk="AssetCategory"),
    f("code", vc(64), True, desc="UNIQUE(tenantId, assetCategoryId, code)"),
    f("name", nvc(200), True),
], identity="code", retention="L", auditable="△"))
add(Entity("AssetStatus", "Asset", "Assets", "Asset status vocabulary.", TENANT, V, [
    f("sortOrder", INT, True, default="0"),
], retention="L", auditable="△"))

add(Entity("AssetAssignment", "Asset", "Assets",
    "Custody (temporal; history preserved §24).", TENANT, B, [
        f("assetId", UUID, True, fk="Asset", indexed=True),
        f("holderType", en("holderType"), True),
        f("holderId", UUID, True, indexed=True),
        f("startDate", DATE, True),
        f("endDate", DATE, False),
    ], retention="L"))

add(Entity("AssetLocation", "Asset", "Assets", "Location (temporal).", TENANT, B, [
    f("assetId", UUID, True, fk="Asset", indexed=True),
    f("locationId", UUID, True, fk="Location"),
    f("validFrom", DATE, True),
    f("validTo", DATE, False),
], retention="L", auditable="△"))

add(Entity("AssetOwnership", "Asset", "Assets",
    "Ownership shares (temporal).", TENANT, B, [
        f("assetId", UUID, True, fk="Asset", indexed=True),
        f("ownerType", en("holderType"), True),
        f("ownerId", UUID, True),
        f("sharePercentage", dec(5, 2), True, desc="Σ ≤ 100 per asset (BR-DAT-006)"),
        f("validFrom", DATE, True),
        f("validTo", DATE, False),
    ], retention="L"))

add(Entity("AssetLifecycle", "Asset", "Assets", "Lifecycle events (append-only).", TENANT, A, [
    f("assetId", UUID, True, fk="Asset", indexed=True),
    f("eventType", en("assetEventType"), True),
    f("eventDate", DATE, True, indexed=True),
    f("note", nvc(500), False),
    f("actorId", UUID, False, fk="User"),
], retention="L"))

add(Entity("AssetDocument", "Asset", "Assets", "Asset↔document link.", TENANT, L, [
    f("assetId", UUID, True, fk="Asset"),
    f("documentId", UUID, True, fk="Document", indexed=True, desc="UNIQUE(assetId, documentId, documentRole)"),
    f("documentRole", en("assetDocumentRole"), True),
], retention="L", auditable="△"))

add(Entity("AssetValueHistory", "Asset", "Assets", "Value over time (append-only).", TENANT, A, [
    f("assetId", UUID, True, fk="Asset", indexed=True),
    f("amount", dec(19, 4), True, desc="money: decimal"),
    f("currency", vc(3), True),
    f("valuedAt", DATE, True, indexed=True),
    f("source", vc(120), False),
], retention="L", auditable="△"))

# ================================ DEVICES ==================================
add(Entity("Device", "Device / OT", "Devices",
    "Physical/logical device (§25).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(200), True),
        f("deviceTypeId", UUID, True, fk="DeviceType"),
        f("deviceModelId", UUID, False, fk="DeviceModel"),
        f("statusId", UUID, True, fk="DeviceStatus", indexed=True),
        f("assetId", UUID, False, fk="Asset", indexed=True, desc="optional link; SET_NULL"),
        f("registeredAt", DT, False),
        f("lastSeenAt", DT, False, indexed=True),
        f("offlineAfterSeconds", INT, True, default="300",
          desc="offline policy threshold (BR-DEV-001), not bare isOnline"),
    ], identity="code", statusEnum="Device", retention="L", versioned=True))

add(Entity("DeviceType", "Device / OT", "Devices", "Device type vocabulary.", TENANT, V, [],
    retention="L", auditable="△"))
add(Entity("DeviceManufacturer", "Device / OT", "Devices", "Manufacturer catalogue.", TENANT, V, [],
    retention="L", auditable="—"))
add(Entity("DeviceModel", "Device / OT", "Devices", "Device model.", TENANT, B, [
    f("manufacturerId", UUID, True, fk="DeviceManufacturer"),
    f("code", vc(64), True, desc="UNIQUE(tenantId, manufacturerId, code)"),
    f("name", nvc(200), True),
], identity="code", retention="L", auditable="—"))
add(Entity("DeviceStatus", "Device / OT", "Devices", "Device status vocabulary.", TENANT, V, [
    f("sortOrder", INT, True, default="0"),
], retention="L", auditable="△"))

add(Entity("DeviceCredential", "Device / OT", "Devices", "Credential reference.", TENANT, B, [
    f("deviceId", UUID, True, fk="Device"),
    f("credentialType", en("deviceCredentialType"), True, desc="UNIQUE(deviceId, credentialType)"),
    f("secretRef", vc(255), True, desc="secret-manager reference; never plain"),
    f("rotatedAt", DT, False),
], retention="M"))

add(Entity("DeviceRegistration", "Device / OT", "Devices",
    "Registration facts (auditable §25).", TENANT, B, [
        f("deviceId", UUID, True, fk="Device", desc="UNIQUE(deviceId)"),
        f("registeredBy", UUID, True, fk="User"),
        f("approvedBy", UUID, False, fk="User"),
        f("approvedAt", DT, False),
    ], retention="L"))

add(Entity("DeviceHeartbeat", "Device / OT", "Devices", "Heartbeat stream.", TENANT, A, [
    f("deviceId", UUID, True, fk="Device", indexed=True),
    f("occurredAt", DT, True, indexed=True),
    f("status", en("heartbeatStatus"), True),
    f("metadata", JSON, False, desc="documented JSON use: diagnostics"),
], retention="C", auditable="—"))

add(Entity("DeviceTelemetry", "Device / OT", "Devices", "Telemetry stream.", TENANT, A, [
    f("deviceId", UUID, True, fk="Device", indexed=True),
    f("metric", vc(120), True, indexed=True),
    f("value", dec(18, 6), True),
    f("unit", vc(32), False),
    f("quality", en("telemetryQuality"), False),
    f("occurredAt", DT, True, indexed=True),
], retention="C", auditable="—"))

add(Entity("DeviceConfiguration", "Device / OT", "Devices", "Versioned configuration.", TENANT, B, [
    f("deviceId", UUID, True, fk="Device", indexed=True),
    f("versionNumber", INT, True, desc="UNIQUE(deviceId, versionNumber); immutable rows"),
    f("config", JSON, True, desc="documented JSON use: device configuration"),
    f("appliedAt", DT, False),
], retention="L"))

add(Entity("DeviceEvent", "Device / OT", "Devices", "Device event stream.", TENANT, A, [
    f("deviceId", UUID, True, fk="Device", indexed=True),
    f("eventType", en("deviceEventType"), True, indexed=True),
    f("severity", en("severityLevel"), True),
    f("payload", JSON, False, desc="documented JSON use: event payload"),
    f("occurredAt", DT, True, indexed=True),
], retention="C", auditable="△"))

add(Entity("Agent", "Device / OT", "Devices",
    "Software agent (≠ Device, §16).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(200), True),
        f("agentType", en("agentType"), True),
        f("ownerType", en("holderType"), False),
        f("ownerId", UUID, False),
        f("credentialRef", vc(255), True, desc="secret reference"),
        f("lastSeenAt", DT, False, indexed=True),
    ], identity="code", retention="M", versioned=True))

# ============================== MAINTENANCE ================================
add(Entity("MaintenancePlan", "Maintenance", "Maintenance",
    "Maintenance plan for asset/device (§26).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("name", nvc(200), True),
        f("targetType", en("maintenanceTargetType"), True, indexed=True, desc="asset · device"),
        f("targetId", UUID, True, indexed=True),
        f("cadenceType", en("cadenceType"), True),
        f("startsOn", DATE, True),
        f("endsOn", DATE, False),
        f("status", en("planStatus"), True),
    ], identity="code", statusEnum="MaintenancePlan", retention="L"))

add(Entity("MaintenanceSchedule", "Maintenance", "Maintenance", "Scheduled occurrence.", TENANT, B, [
    f("planId", UUID, True, fk="MaintenancePlan", indexed=True, desc="UNIQUE(planId, dueAt)"),
    f("dueAt", DT, True, indexed=True),
    f("status", en("scheduleStatus"), True),
], retention="M"))

add(Entity("MaintenanceWorkOrder", "Maintenance", "Maintenance",
    "Work order (§26).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("planId", UUID, False, fk="MaintenancePlan"),
        f("targetType", en("maintenanceTargetType"), True, indexed=True),
        f("targetId", UUID, True),
        f("title", nvc(250), True),
        f("priority", en("workOrderPriority"), True),
        f("status", en("workOrderStatus"), True, indexed=True, desc="see StateMachine: Maintenance"),
        f("requesterId", UUID, True, fk="User"),
        f("assigneeId", UUID, False, fk="User", indexed=True),
        f("dueAt", DT, False, indexed=True),
        f("openedAt", DT, True),
        f("closedAt", DT, False),
        f("outcomeNote", nvc("max"), False, desc="required to complete (BR-MNT-001)"),
    ], identity="code", statusEnum="Maintenance", retention="L", versioned=True))

add(Entity("MaintenanceTask", "Maintenance", "Maintenance", "Work-order task.", TENANT, B, [
    f("workOrderId", UUID, True, fk="MaintenanceWorkOrder", indexed=True),
    f("title", nvc(250), True, desc="UNIQUE(workOrderId, title)"),
    f("technicianId", UUID, False, fk="User", indexed=True),
    f("status", en("workOrderStatus"), True),
    f("estimatedMinutes", INT, False),
], retention="M"))

add(Entity("MaintenanceEvent", "Maintenance", "Maintenance", "Work-order events.", TENANT, A, [
    f("workOrderId", UUID, True, fk="MaintenanceWorkOrder", indexed=True),
    f("eventType", en("maintenanceEventType"), True),
    f("occurredAt", DT, True, indexed=True),
    f("actorId", UUID, False, fk="User"),
    f("note", nvc(500), False),
], retention="L", auditable="△"))

add(Entity("MaintenanceTechnician", "Maintenance", "Maintenance", "Technician registry.", TENANT, B, [
    f("employeeId", UUID, True, fk="Employee", desc="UNIQUE(employeeId)"),
    f("specializations", JSON, False, desc="documented JSON use: skill list"),
], retention="M", auditable="△"))

add(Entity("MaintenancePart", "Maintenance", "Maintenance", "Part usage.", TENANT, B, [
    f("workOrderId", UUID, True, fk="MaintenanceWorkOrder", indexed=True),
    f("partRef", vc(120), True, desc="UNIQUE(workOrderId, partRef)"),
    f("quantity", INT, True, default="1", desc="> 0"),
    f("unitCost", dec(19, 4), False),
    f("currency", vc(3), False),
], retention="M", auditable="△"))

add(Entity("MaintenanceCost", "Maintenance", "Maintenance", "Cost record.", TENANT, B, [
    f("workOrderId", UUID, True, fk="MaintenanceWorkOrder", indexed=True),
    f("costType", en("maintenanceCostType"), True),
    f("amount", dec(19, 4), True, desc="≥ 0"),
    f("currency", vc(3), True),
    f("occurredAt", DT, True),
], retention="L"))

add(Entity("MaintenanceHistory", "Maintenance", "Maintenance", "History stream.", TENANT, A, [
    f("targetType", en("maintenanceTargetType"), True, indexed=True),
    f("targetId", UUID, True, indexed=True),
    f("summary", nvc(500), True),
    f("occurredAt", DT, True, indexed=True),
    f("actorId", UUID, False, fk="User"),
], retention="L"))

# =============================== DOCUMENTS =================================
add(Entity("Document", "Document", "Documents",
    "Document root (§22).", TENANT, B, [
        f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
        f("title", nvc(250), True),
        f("documentTypeId", UUID, True, fk="DocumentType"),
        f("documentCategoryId", UUID, False, fk="DocumentCategory"),
        f("folderId", UUID, False, fk="DocumentFolder", indexed=True),
        f("ownerId", UUID, True, fk="User"),
        f("status", en("documentStatus"), True, indexed=True, desc="see StateMachine: Document"),
        f("currentVersionNumber", INT, True, default="1"),
        f("classificationLevel", en("classificationLevel"), True),
    ], identity="code", statusEnum="Document", retention="L", versioned=True))

add(Entity("DocumentVersion", "Document", "Documents",
    "Immutable version (§23).", TENANT, B, [
        f("documentId", UUID, True, fk="Document", indexed=True),
        f("versionNumber", INT, True, desc="UNIQUE(documentId, versionNumber); never overwritten"),
        f("storageProvider", vc(32), True),
        f("storageKey", vc(512), True, desc="object storage; binary never in DB (§40)"),
        f("checksum", vc(128), True),
        f("fileSize", BIGINT, True),
        f("uploadedBy", UUID, True, fk="User"),
        f("changeNote", nvc(500), False),
    ], retention="L", hardDelete="never (version chain preserved)"))

add(Entity("DocumentType", "Document", "Documents", "Document type vocabulary.", TENANT, V, [],
    retention="L", auditable="△"))
add(Entity("DocumentCategory", "Document", "Documents", "Category tree.", TENANT, V, [
    f("parentId", UUID, False, fk="DocumentCategory"),
], retention="L", auditable="△"))
add(Entity("DocumentFolder", "Document", "Documents", "Folder tree (acyclic).", TENANT, B, [
    f("name", nvc(200), True, desc="UNIQUE(tenantId, parentId, name)"),
    f("parentId", UUID, False, fk="DocumentFolder"),
], retention="L", auditable="△"))

add(Entity("DocumentPermission", "Document", "Documents", "Document ACL.", TENANT, B, [
    f("documentId", UUID, True, fk="Document", indexed=True),
    f("subjectType", en("subjectType"), True),
    f("subjectId", UUID, True, indexed=True,
      desc="UNIQUE(documentId, subjectType, subjectId, permissionLevel)"),
    f("permissionLevel", en("documentPermissionLevel"), True),
    f("grantedBy", UUID, True, fk="User"),
    f("grantedAt", DT, True),
    f("expiresAt", DT, False),
], retention="L"))

add(Entity("DocumentShare", "Document", "Documents", "Share grant.", TENANT, B, [
    f("documentId", UUID, True, fk="Document", indexed=True),
    f("sharedWithType", en("subjectType"), True),
    f("sharedWithId", UUID, True),
    f("sharedBy", UUID, True, fk="User"),
    f("expiresAt", DT, False, indexed=True),
], retention="M"))

add(Entity("DocumentMetadata", "Document", "Documents", "Metadata entry.", TENANT, B, [
    f("documentId", UUID, True, fk="Document", indexed=True),
    f("key", vc(120), True, desc="UNIQUE(documentId, key)"),
    f("value", nvc("max"), False),
], retention="L", auditable="—"))

add(Entity("DocumentAttachment", "Document", "Documents", "Document attachment link.", TENANT, L, [
    f("documentId", UUID, True, fk="Document"),
    f("attachmentId", UUID, True, fk="Attachment", desc="UNIQUE(documentId, attachmentId)"),
], retention="L", auditable="△"))

add(Entity("DocumentWorkflow", "Document", "Documents", "Workflow trigger link.", TENANT, L, [
    f("documentId", UUID, True, fk="Document", indexed=True, desc="UNIQUE(documentId, workflowInstanceId)"),
    f("workflowInstanceId", UUID, True, fk="WorkflowInstance", indexed=True),
    f("triggeredAt", DT, True),
], retention="L"))

# ================================ WORKFLOW =================================
add(Entity("Workflow", "Workflow", "Workflow", "Named workflow (generic §34).", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
], identity="code", retention="L"))

add(Entity("WorkflowVersion", "Workflow", "Workflow",
    "Version (never overwritten §34).", TENANT, B, [
        f("workflowId", UUID, True, fk="Workflow", indexed=True),
        f("versionNumber", INT, True, desc="UNIQUE(workflowId, versionNumber)"),
        f("status", en("workflowVersionStatus"), True),
    ], retention="L"))

add(Entity("WorkflowDefinition", "Workflow", "Workflow", "Definition per version.", TENANT, B, [
    f("workflowVersionId", UUID, True, fk="WorkflowVersion", desc="UNIQUE(workflowVersionId)"),
    f("definition", JSON, True, desc="documented JSON use: graph definition"),
], retention="L"))

add(Entity("WorkflowNode", "Workflow", "Workflow", "Graph node.", TENANT, B, [
    f("workflowDefinitionId", UUID, True, fk="WorkflowDefinition", indexed=True),
    f("nodeKey", vc(64), True, desc="UNIQUE(workflowDefinitionId, nodeKey)"),
    f("nodeType", en("workflowNodeType"), True),
    f("name", nvc(200), True),
    f("config", JSON, False, desc="documented JSON use: node config"),
], retention="L", auditable="△"))

add(Entity("WorkflowTransition", "Workflow", "Workflow", "Graph edge.", TENANT, B, [
    f("workflowDefinitionId", UUID, True, fk="WorkflowDefinition", indexed=True),
    f("fromNodeKey", vc(64), True, desc="UNIQUE(definitionId, fromNodeKey, toNodeKey)"),
    f("toNodeKey", vc(64), True),
    f("condition", JSON, False, desc="documented JSON use: transition condition"),
], retention="L", auditable="△"))

add(Entity("WorkflowInstance", "Workflow", "Workflow",
    "Running instance (independent state §34).", TENANT, B, [
        f("workflowDefinitionId", UUID, True, fk="WorkflowDefinition", indexed=True),
        f("targetType", vc(64), True, indexed=True),
        f("targetId", UUID, True, indexed=True),
        f("status", en("workflowInstanceStatus"), True, indexed=True,
          desc="see StateMachine: Workflow"),
        f("startedAt", DT, True),
        f("completedAt", DT, False),
        f("context", JSON, False, desc="documented JSON use: instance context"),
    ], statusEnum="Workflow", retention="L", versioned=True))

add(Entity("WorkflowInstanceState", "Workflow", "Workflow", "Current state snapshot.", TENANT, B, [
    f("instanceId", UUID, True, fk="WorkflowInstance", desc="UNIQUE(instanceId)"),
    f("currentNodeKey", vc(64), True),
    f("enteredAt", DT, True),
    f("waitingFor", JSON, False, desc="documented JSON use: pending approvals"),
], retention="M"))

add(Entity("WorkflowTask", "Workflow", "Workflow", "Human task.", TENANT, B, [
    f("instanceId", UUID, True, fk="WorkflowInstance", indexed=True, desc="UNIQUE(instanceId, nodeKey)"),
    f("nodeKey", vc(64), True),
    f("assigneeId", UUID, False, fk="User", indexed=True),
    f("status", en("workflowTaskStatus"), True, indexed=True),
    f("dueAt", DT, False, indexed=True),
], retention="M"))

add(Entity("WorkflowAction", "Workflow", "Workflow", "Actions taken (append-only).", TENANT, A, [
    f("instanceId", UUID, True, fk="WorkflowInstance", indexed=True),
    f("actorId", UUID, True, fk="User"),
    f("actionType", en("workflowActionType"), True),
    f("comment", nvc(500), False),
    f("occurredAt", DT, True, indexed=True),
], retention="L"))

add(Entity("WorkflowApproval", "Workflow", "Workflow",
    "Approval decision (§35).", TENANT, B, [
        f("workflowTaskId", UUID, True, fk="WorkflowTask", indexed=True,
          desc="UNIQUE(workflowTaskId, approverId)"),
        f("approverId", UUID, True, fk="User", indexed=True),
        f("decision", en("approvalDecision"), True, desc="approved · rejected · pending · cancelled"),
        f("decidedAt", DT, False),
        f("comment", nvc(500), False, desc="required when REJECTED (BR-WF-003)"),
        f("delegatedFromId", UUID, False, fk="WorkflowApproval"),
    ], statusEnum="Approval", retention="L"))

add(Entity("WorkflowHistory", "Workflow", "Workflow", "Transition history.", TENANT, A, [
    f("instanceId", UUID, True, fk="WorkflowInstance", indexed=True),
    f("fromNode", vc(64), False),
    f("toNode", vc(64), False),
    f("actorId", UUID, False, fk="User"),
    f("occurredAt", DT, True, indexed=True),
    f("metadata", JSON, False, desc="documented JSON use: transition detail"),
], retention="L"))

# ============================= COMMUNICATION ===============================
add(Entity("Conversation", "Communication", "Communication",
    "Chat aggregate (§27).", TENANT, B, [
        f("conversationType", en("conversationType"), True, indexed=True,
          desc="direct · group · channel · meeting · system"),
        f("title", nvc(200), False, desc="null = direct chat (no title)"),
        f("createdBy", UUID, True, fk="User", desc="creator mandatory (BR-COM-001)"),
        f("lastMessageAt", DT, False, indexed=True),
        f("retentionDays", INT, False, desc="per-tenant policy; null = platform default"),
    ], statusEnum="Conversation", retention="M"))

add(Entity("ConversationMember", "Communication", "Communication",
    "Membership with data.", TENANT, B, [
        f("conversationId", UUID, True, fk="Conversation", indexed=True,
          desc="UNIQUE(conversationId, userId)"),
        f("userId", UUID, True, fk="User", indexed=True),
        f("memberRole", en("conversationRole"), True, desc="owner·admin·moderator·member·guest·readOnly"),
        f("joinedAt", DT, True),
        f("leftAt", DT, False),
        f("mutedUntil", DT, False),
    ], retention="M"))

add(Entity("ConversationType", "Communication", "Communication", "Type vocabulary.", GLOBAL, V, [],
    retention="L", auditable="—"))

add(Entity("Message", "Communication", "Communication",
    "Message (immutable/edit-policy §27).", TENANT, B, [
        f("conversationId", UUID, True, fk="Conversation", indexed=True,
          desc="(conversationId, createdAt) cursor index"),
        f("senderId", UUID, True, fk="User"),
        f("contentType", en("messageContentType"), True),
        f("body", nvc("max"), False),
        f("replyToId", UUID, False, fk="Message"),
        f("threadId", UUID, False, fk="Message"),
        f("editedAt", DT, False, desc="edit audited (BR-COM-002)"),
        f("deletedAt", DT, False, desc="soft delete / tombstone per policy"),
        f("generatedByAi", BOOL, True, default="false", desc="AI governance flag"),
        f("aiModelRef", vc(120), False),
    ], retention="M"))

add(Entity("MessageAttachment", "Communication", "Communication", "Message attachment.", TENANT, L, [
    f("messageId", UUID, True, fk="Message"),
    f("attachmentId", UUID, True, fk="Attachment", desc="UNIQUE(messageId, attachmentId)"),
], retention="M", auditable="△"))

add(Entity("MessageReaction", "Communication", "Communication", "Reaction.", TENANT, L, [
    f("messageId", UUID, True, fk="Message"),
    f("userId", UUID, True, fk="User", desc="UNIQUE(messageId, userId, emoji)"),
    f("emoji", vc(32), True),
], retention="S", auditable="—"))

add(Entity("MessageReadReceipt", "Communication", "Communication", "Read state.", TENANT, B, [
    f("messageId", UUID, True, fk="Message"),
    f("userId", UUID, True, fk="User", indexed=True, desc="UNIQUE(messageId, userId)"),
    f("readAt", DT, True),
], retention="S", auditable="—"))

add(Entity("Channel", "Communication", "Communication", "Channel profile.", TENANT, B, [
    f("conversationId", UUID, True, fk="Conversation", desc="UNIQUE(conversationId)"),
    f("visibility", en("channelVisibility"), True, indexed=True,
      desc="public · private · announcement"),
    f("description", nvc(500), False),
], retention="L"))

add(Entity("ChannelMember", "Communication", "Communication", "Channel membership.", TENANT, B, [
    f("channelId", UUID, True, fk="Channel", indexed=True, desc="UNIQUE(channelId, userId)"),
    f("userId", UUID, True, fk="User", indexed=True),
    f("memberRole", en("conversationRole"), True),
    f("joinedAt", DT, True),
], retention="M"))

add(Entity("VoiceCall", "Communication", "Communication",
    "Voice call metadata (§28).", TENANT, B, [
        f("conversationId", UUID, False, fk="Conversation"),
        f("initiatorId", UUID, True, fk="User"),
        f("callType", en("callType"), True, desc="direct · group"),
        f("status", en("callStatus"), True, desc="see StateMachine: Call"),
        f("startedAt", DT, True),
        f("endedAt", DT, False),
    ], statusEnum="Call", retention="M", auditable="△"))

add(Entity("VoiceCallParticipant", "Communication", "Communication", "Call participant.", TENANT, B, [
    f("callId", UUID, True, fk="VoiceCall", indexed=True, desc="UNIQUE(callId, userId)"),
    f("userId", UUID, True, fk="User", indexed=True),
    f("joinedAt", DT, True),
    f("leftAt", DT, False),
    f("state", en("participantState"), True),
], retention="M", auditable="△"))

add(Entity("GroupCall", "Communication", "Communication", "Group call metadata.", TENANT, B, [
    f("conversationId", UUID, False, fk="Conversation"),
    f("hostId", UUID, True, fk="User"),
    f("status", en("callStatus"), True),
    f("startedAt", DT, True),
    f("endedAt", DT, False),
], statusEnum="Call", retention="M", auditable="△"))

add(Entity("VideoMeeting", "Communication", "Communication",
    "Meeting (§29).", TENANT, B, [
        f("conversationId", UUID, False, fk="Conversation"),
        f("hostId", UUID, True, fk="User"),
        f("scheduledAt", DT, False, indexed=True),
        f("startedAt", DT, False),
        f("endedAt", DT, False),
        f("status", en("meetingStatus"), True, desc="see StateMachine: Meeting"),
        f("isRecurring", BOOL, True, default="false"),
    ], statusEnum="Meeting", retention="L"))

add(Entity("MeetingParticipant", "Communication", "Communication", "Meeting participant.", TENANT, B, [
    f("meetingId", UUID, True, fk="VideoMeeting", indexed=True, desc="UNIQUE(meetingId, userId)"),
    f("userId", UUID, True, fk="User", indexed=True),
    f("participantRole", en("meetingRole"), True),
    f("invitedAt", DT, True),
    f("joinedAt", DT, False),
    f("leftAt", DT, False),
], retention="M"))

add(Entity("MeetingSession", "Communication", "Communication",
    "Session (reconnect/recurring).", TENANT, B, [
        f("meetingId", UUID, True, fk="VideoMeeting", indexed=True,
          desc="UNIQUE(meetingId, sessionKey)"),
        f("sessionKey", vc(64), True),
        f("startedAt", DT, True),
        f("endedAt", DT, False),
    ], retention="M"))

add(Entity("ScreenShareSession", "Communication", "Communication", "Screen-share session.", TENANT, B, [
    f("meetingSessionId", UUID, True, fk="MeetingSession", indexed=True),
    f("sharerId", UUID, True, fk="User"),
    f("startedAt", DT, True),
    f("endedAt", DT, False),
], retention="S", auditable="△"))

add(Entity("MeetingRecording", "Communication", "Communication",
    "Recording metadata (§29).", TENANT, B, [
        f("meetingSessionId", UUID, True, fk="MeetingSession", indexed=True),
        f("storageProvider", vc(32), True, desc="binary in object storage — never DB"),
        f("storageKey", vc(512), True),
        f("durationSeconds", INT, True),
        f("status", en("recordingStatus"), True),
        f("consentCaptured", BOOL, True, default="false", desc="BR-COM-006"),
    ], retention="L"))

add(Entity("Presence", "Communication", "Communication",
    "Presence (realtime source = Redis §30).", TENANT, B, [
        f("userId", UUID, True, fk="User", indexed=True, desc="UNIQUE(userId, deviceId)"),
        f("deviceId", UUID, False),
        f("presenceStatus", en("presenceStatus"), True, indexed=True,
          desc="online·away·busy·doNotDisturb·offline (§30)"),
        f("lastSeenAt", DT, True, indexed=True),
    ], retention="S", auditable="—"))

add(Entity("PresenceStatus", "Communication", "Communication", "Presence vocabulary.", GLOBAL, V, [],
    retention="L", auditable="—"))

# ============================= NOTIFICATIONS ===============================
add(Entity("Notification", "Notification", "Notifications",
    "Notification root (event-driven §36).", TENANT, B, [
        f("notificationType", vc(120), True, indexed=True),
        f("title", nvc(250), True),
        f("body", nvc("max"), False),
        f("payload", JSON, False, desc="documented JSON use: event payload"),
        f("priority", en("notificationPriority"), True),
        f("status", en("notificationStatus"), True, indexed=True),
        f("sourceEventId", UUID, False, desc="originating domain event"),
        f("templateId", UUID, False, fk="NotificationTemplate"),
        f("expiresAt", DT, False, indexed=True),
    ], statusEnum="Notification", retention="S", hardDelete="after retention window (policy purge)"))
# NOTE (canonical rule): read state lives on NotificationRecipient — an
# isRead/readAt column on Notification is FORBIDDEN (Phase 12 §).

add(Entity("NotificationTemplate", "Notification", "Notifications", "Versioned template.", TENANT, B, [
    f("code", vc(120), True, desc="UNIQUE(tenantId, code, versionNumber)"),
    f("versionNumber", INT, True),
    f("channel", en("notificationChannelType"), True),
    f("subjectTemplate", nvc(500), False),
    f("bodyTemplate", nvc("max"), True),
    f("variables", JSON, False, desc="documented JSON use: variable schema"),
], identity="code", retention="L"))

add(Entity("NotificationPreference", "Notification", "Notifications", "User preference.", TENANT, B, [
    f("userId", UUID, True, fk="User", indexed=True,
      desc="UNIQUE(userId, notificationType, channel)"),
    f("notificationType", vc(120), True),
    f("channel", en("notificationChannelType"), True),
    f("enabled", BOOL, True, default="true"),
    f("quietStart", TIME, False),
    f("quietEnd", TIME, False),
], retention="M", auditable="—"))

add(Entity("NotificationChannel", "Notification", "Notifications", "Channel vocabulary.", GLOBAL, V, [],
    retention="L", auditable="—"))

add(Entity("NotificationDelivery", "Notification", "Notifications",
    "Delivery attempt (§31).", TENANT, A, [
        f("notificationId", UUID, True, fk="Notification", indexed=True),
        f("recipientId", UUID, True, fk="NotificationRecipient", indexed=True),
        f("channel", en("notificationChannelType"), True),
        f("status", en("deliveryStatus"), True, indexed=True,
          desc="pending · sent · delivered · failed · read (§31)"),
        f("attemptedAt", DT, True, indexed=True),
        f("providerRef", vc(255), False),
        f("error", nvc(500), False, desc="retryable (BR-NOT-002)"),
    ], retention="S", auditable="△"))

add(Entity("NotificationRecipient", "Notification", "Notifications",
    "Recipient + read state.", TENANT, B, [
        f("notificationId", UUID, True, fk="Notification", indexed=True,
          desc="UNIQUE(notificationId, userId)"),
        f("userId", UUID, True, fk="User", indexed=True),
        f("readAt", DT, False, indexed=True, desc="read state lives HERE"),
    ], retention="S", auditable="—"))

# ================================= AUDIT ===================================
add(Entity("AuditEvent", "Audit", "Audit",
    "Append-only audit fact (§32/§33).", TENANT, A, [
        f("actorId", UUID, False, fk="User", indexed=True, desc="SET_NULL if actor purged"),
        f("action", en("auditAction"), True, desc="§32 controlled vocabulary"),
        f("entityType", vc(64), True, indexed=True),
        f("entityId", UUID, True, indexed=True),
        f("timestamp", DT, True, indexed=True),
        f("ipAddress", vc(45), False),
        f("userAgent", nvc(500), False),
        f("beforeState", JSON, False, desc="documented JSON use: audit snapshot"),
        f("afterState", JSON, False, desc="documented JSON use: audit snapshot"),
        f("metadata", JSON, False, desc="documented JSON use: change detail"),
        f("correlationId", UUID, True, indexed=True, desc="trace key"),
    ], retention="L", hardDelete="never (compliance); UPDATE/DELETE forbidden (BR-AUD-002)",
    auditable="✓ (is the record)"))

# =============================== REPORTING =================================
add(Entity("ReportDefinition", "Reporting", "Reporting/Analytics", "Report spec.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("dataSource", vc(120), True),
    f("parameterSchema", JSON, False, desc="documented JSON use: parameter schema"),
], identity="code", retention="L"))

add(Entity("ReportParameter", "Reporting", "Reporting/Analytics", "Parameter definition.", TENANT, B, [
    f("reportDefinitionId", UUID, True, fk="ReportDefinition", indexed=True,
      desc="UNIQUE(reportDefinitionId, key)"),
    f("key", vc(64), True),
    f("parameterType", en("parameterType"), True),
    f("isRequired", BOOL, True, default="false"),
    f("defaultValue", nvc(500), False),
], retention="L", auditable="—"))

add(Entity("ReportExecution", "Reporting", "Reporting/Analytics", "Report run.", TENANT, B, [
    f("reportDefinitionId", UUID, True, fk="ReportDefinition", indexed=True),
    f("requestedBy", UUID, True, fk="User"),
    f("startedAt", DT, True, indexed=True),
    f("finishedAt", DT, False),
    f("status", en("executionStatus"), True, indexed=True),
], retention="M", auditable="△"))

add(Entity("ReportSchedule", "Reporting", "Reporting/Analytics", "Report schedule.", TENANT, B, [
    f("reportDefinitionId", UUID, True, fk="ReportDefinition", indexed=True),
    f("cronExpression", vc(64), True, desc="UNIQUE(reportDefinitionId, cronExpression)"),
    f("nextRunAt", DT, False, indexed=True),
], retention="M", auditable="△"))

add(Entity("ReportOutput", "Reporting", "Reporting/Analytics", "Report output.", TENANT, B, [
    f("executionId", UUID, True, fk="ReportExecution", indexed=True),
    f("storageProvider", vc(32), True),
    f("storageKey", vc(512), True),
    f("format", en("reportFormat"), True),
    f("generatedAt", DT, True),
], retention="M", auditable="—"))

add(Entity("ReportAccess", "Reporting", "Reporting/Analytics", "Access grant.", TENANT, B, [
    f("reportDefinitionId", UUID, True, fk="ReportDefinition", indexed=True,
      desc="UNIQUE(reportDefinitionId, subjectType, subjectId)"),
    f("subjectType", en("subjectType"), True),
    f("subjectId", UUID, True),
    f("accessLevel", en("reportAccessLevel"), True),
], retention="L"))

# =============================== ANALYTICS =================================
add(Entity("MetricDefinition", "Analytics", "Reporting/Analytics", "Metric spec.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("formula", nvc(500), False),
    f("unit", vc(32), False),
], identity="code", retention="L", auditable="—"))

add(Entity("MetricValue", "Analytics", "Reporting/Analytics", "Metric point (projection).", TENANT, A, [
    f("metricId", UUID, True, fk="MetricDefinition", indexed=True),
    f("dimensions", JSON, False, desc="documented JSON use: dimension filter"),
    f("value", dec(18, 6), True),
    f("periodStart", DT, True),
    f("periodEnd", DT, True),
], retention="C", auditable="—"))

add(Entity("KpiDefinition", "Analytics", "Reporting/Analytics", "KPI spec.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("targetValue", dec(18, 6), False),
    f("direction", en("kpiDirection"), True),
    f("unit", vc(32), False),
], identity="code", retention="L", auditable="—"))

add(Entity("KpiValue", "Analytics", "Reporting/Analytics", "KPI point (projection).", TENANT, A, [
    f("kpiId", UUID, True, fk="KpiDefinition", indexed=True),
    f("dimensions", JSON, False, desc="documented JSON use: dimension filter"),
    f("value", dec(18, 6), True),
    f("periodType", en("periodType"), True),
    f("periodStart", DT, True),
    f("periodEnd", DT, True),
], retention="C", auditable="—"))

add(Entity("Dashboard", "Analytics", "Reporting/Analytics", "Dashboard.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("ownerId", UUID, True, fk="User", indexed=True),
    f("layout", JSON, False, desc="documented JSON use: layout"),
], identity="code", retention="M", auditable="—"))

add(Entity("DashboardWidget", "Analytics", "Reporting/Analytics",
    "Widget (justified CASCADE child).", TENANT, B, [
        f("dashboardId", UUID, True, fk="Dashboard", indexed=True),
        f("widgetType", vc(64), True),
        f("config", JSON, False, desc="documented JSON use: widget config"),
        f("position", INT, True, default="0", desc="UNIQUE(dashboardId, position)"),
    ], retention="M", auditable="—"))

add(Entity("AnalyticsSnapshot", "Analytics", "Reporting/Analytics", "Projection snapshot.", TENANT, A, [
    f("scopeType", vc(64), True, indexed=True),
    f("scopeId", UUID, True, indexed=True),
    f("periodType", en("periodType"), True),
    f("data", JSON, True, desc="documented JSON use: projection payload"),
    f("builtAt", DT, True, indexed=True),
], retention="C", auditable="—"))

# ==================================== AI ===================================
add(Entity("AiProvider", "AI", "AI", "Provider registry.", GLOBAL, B, [
    f("code", vc(64), True, unique=True, desc="global unique"),
    f("name", nvc(200), True),
    f("adapterType", en("aiAdapterType"), True),
    f("config", JSON, False, desc="documented JSON use: provider config (no secrets)"),
], identity="code", retention="L"))

add(Entity("AiModel", "AI", "AI", "Model registry.", GLOBAL, B, [
    f("providerId", UUID, True, fk="AiProvider", indexed=True),
    f("code", vc(64), True, desc="UNIQUE(providerId, code)"),
    f("name", nvc(200), True),
    f("modality", en("aiModality"), True),
], identity="code", retention="L"))

add(Entity("AiModelVersion", "AI", "AI", "Model version.", GLOBAL, B, [
    f("modelId", UUID, True, fk="AiModel", indexed=True),
    f("versionNumber", vc(64), True, desc="UNIQUE(modelId, versionNumber)"),
    f("status", en("aiModelStatus"), True),
    f("contextLimit", INT, False),
    f("releasedAt", DATE, False),
], retention="L"))

add(Entity("AiAgent", "AI", "AI", "Software AI agent.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("modelVersionId", UUID, True, fk="AiModelVersion"),
    f("instructions", nvc("max"), False),
    f("status", en("aiAgentStatus"), True),
], identity="code", statusEnum="AiAgent", retention="M"))

add(Entity("AiAgentExecution", "AI", "AI", "Agent run (traceable §38).", TENANT, A, [
    f("agentId", UUID, True, fk="AiAgent", indexed=True),
    f("input", JSON, False, desc="documented JSON use: run input"),
    f("output", JSON, False, desc="documented JSON use: run output"),
    f("promptTokens", INT, False),
    f("completionTokens", INT, False),
    f("startedAt", DT, True, indexed=True),
    f("finishedAt", DT, False),
    f("status", en("executionStatus"), True),
], retention="M", auditable="△"))

add(Entity("AiRequest", "AI", "AI",
    "Inference request (§37 fields).", TENANT, B, [
        f("capability", vc(120), True, indexed=True),
        f("inputRef", UUID, False, desc="input reference (§37)"),
        f("promptVersionRef", UUID, False, desc="prompt/context reference (§37)"),
        f("requestedBy", UUID, True, fk="User"),
        f("status", en("executionStatus"), True),
    ], statusEnum="AiRequest", retention="M"))

add(Entity("AiResponse", "AI", "AI",
    "Classified result (§37/§38).", TENANT, B, [
        f("requestId", UUID, True, fk="AiRequest", desc="UNIQUE(requestId)"),
        f("content", nvc("max"), False, desc="output (§37)"),
        f("resultClassification", en("resultClassification"), True, indexed=True,
          desc="advisory·draft·automated·authoritative (BR-AI-001)"),
        f("modelId", UUID, True, fk="AiModel", desc="which model (§38)"),
        f("modelVersionId", UUID, True, fk="AiModelVersion", desc="which version (§38)"),
        f("providerId", UUID, True, fk="AiProvider", desc="which provider (§38)"),
        f("confidence", dec(5, 4), False, desc="0–1 (§37)"),
        f("costAmount", dec(12, 4), False),
        f("costCurrency", vc(3), False),
        f("producedAt", DT, True, desc="when (§38)"),
    ], retention="M"))

add(Entity("AiConversation", "AI", "AI", "AI chat session.", TENANT, B, [
    f("userId", UUID, True, fk="User", indexed=True),
    f("title", nvc(250), False),
], retention="S", auditable="△"))

add(Entity("AiMessage", "AI", "AI", "Chat turn (append-only).", TENANT, A, [
    f("conversationId", UUID, True, fk="AiConversation", indexed=True),
    f("role", en("aiMessageRole"), True),
    f("content", nvc("max"), True),
    f("promptTokens", INT, False),
    f("completionTokens", INT, False),
], retention="S", auditable="△"))

add(Entity("AiKnowledgeSource", "AI", "AI", "RAG source.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("sourceType", en("knowledgeSourceType"), True),
    f("ingestionConfig", JSON, False, desc="documented JSON use: ingestion config"),
], identity="code", retention="L"))

add(Entity("AiKnowledgeDocument", "AI", "AI", "Ingested document.", TENANT, B, [
    f("sourceId", UUID, True, fk="AiKnowledgeSource", indexed=True,
      desc="UNIQUE(sourceId, documentRef)"),
    f("documentRef", UUID, False, fk="Document"),
    f("chunkCount", INT, True, default="0"),
    f("status", en("executionStatus"), True),
], retention="L"))

add(Entity("AiEmbedding", "AI", "AI", "Embedding registry row.", TENANT, A, [
    f("knowledgeDocumentId", UUID, True, fk="AiKnowledgeDocument", indexed=True),
    f("chunkRef", vc(120), True),
    f("vectorRef", vc(255), True, desc="vector store reference"),
    f("metadata", JSON, False, desc="documented JSON use: chunk metadata"),
], retention="C", auditable="—"))

add(Entity("AiRecommendation", "AI", "AI",
    "Recommendation (advisory by default).", TENANT, B, [
        f("targetType", vc(64), True, indexed=True),
        f("targetId", UUID, True, indexed=True),
        f("content", nvc("max"), True),
        f("classification", en("resultClassification"), True),
        f("status", en("recommendationStatus"), True, indexed=True),
        f("reviewedBy", UUID, False, fk="User"),
        f("reviewedAt", DT, False),
    ], statusEnum="AiRecommendation", retention="M"))

add(Entity("AiPrediction", "AI", "AI",
    "Prediction — NOT a fact (§37).", TENANT, B, [
        f("targetType", vc(64), True, indexed=True),
        f("targetId", UUID, True, indexed=True),
        f("horizon", vc(64), True),
        f("predictedValue", dec(18, 6), True),
        f("confidence", dec(5, 4), False),
        f("evaluatedAt", DT, True, desc="compared to actual when available"),
    ], retention="M"))

add(Entity("AiInsight", "AI", "AI", "Generated insight.", TENANT, B, [
    f("scopeType", vc(64), True, indexed=True),
    f("scopeId", UUID, True, indexed=True),
    f("summary", nvc(500), True),
    f("evidence", JSON, False, desc="documented JSON use: evidence refs"),
    f("generatedAt", DT, True),
], retention="M"))

# ============================== INTEGRATION ================================
add(Entity("Integration", "Integration", "Integration", "Registered integration.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("name", nvc(200), True),
    f("integrationTypeId", UUID, True, fk="IntegrationType", indexed=True),
    f("status", en("integrationStatus"), True),
], identity="code", statusEnum="Integration", retention="L"))

add(Entity("IntegrationType", "Integration", "Integration", "Type vocabulary.", GLOBAL, V, [],
    retention="L", auditable="—"))

add(Entity("IntegrationCredential", "Integration", "Integration",
    "Credential reference (§39).", TENANT, B, [
        f("integrationId", UUID, True, fk="Integration", indexed=True,
          desc="UNIQUE(integrationId, credentialType)"),
        f("credentialType", en("credentialType"), True),
        f("secretRef", vc(255), True, desc="never plain text (BR-INT-001)"),
        f("rotatedAt", DT, False),
    ], retention="M"))

add(Entity("IntegrationEndpoint", "Integration", "Integration", "Endpoint.", TENANT, B, [
    f("integrationId", UUID, True, fk="Integration", indexed=True),
    f("direction", en("integrationDirection"), True),
    f("url", nvc(500), False),
    f("authType", en("endpointAuthType"), True),
], retention="L", auditable="△"))

add(Entity("IntegrationConnection", "Integration", "Integration", "Connection state.", TENANT, B, [
    f("integrationId", UUID, True, fk="Integration", desc="UNIQUE(integrationId)"),
    f("status", en("connectionStatus"), True),
    f("lastConnectedAt", DT, False, indexed=True),
    f("latencyMs", INT, False),
], retention="M", auditable="△"))

add(Entity("IntegrationMapping", "Integration", "Integration", "Payload mapping.", TENANT, B, [
    f("integrationId", UUID, True, fk="Integration", indexed=True,
      desc="UNIQUE(integrationId, direction)"),
    f("direction", en("integrationDirection"), True),
    f("mapping", JSON, True, desc="documented JSON use: field mapping"),
], retention="L"))

add(Entity("IntegrationJob", "Integration", "Integration", "Sync job.", TENANT, B, [
    f("integrationId", UUID, True, fk="Integration", indexed=True,
      desc="UNIQUE(integrationId, name)"),
    f("name", nvc(200), True),
    f("cronExpression", vc(64), False),
    f("direction", en("integrationDirection"), True),
    f("status", en("jobStatus"), True),
], retention="L"))

add(Entity("IntegrationExecution", "Integration", "Integration",
    "Job run (§39 statuses).", TENANT, A, [
        f("jobId", UUID, True, fk="IntegrationJob", indexed=True),
        f("status", en("integrationExecutionStatus"), True, indexed=True,
          desc="started · success · failed · retrying (§39)"),
        f("startedAt", DT, True, indexed=True),
        f("finishedAt", DT, False),
        f("statistics", JSON, False, desc="documented JSON use: run stats"),
        f("error", nvc(500), False, desc="traceable (BR-INT-002)"),
    ], retention="M", auditable="△"))

add(Entity("IntegrationEvent", "Integration", "Integration",
    "Inbound/outbound record (idempotent).", TENANT, B, [
        f("integrationId", UUID, True, fk="Integration", indexed=True),
        f("direction", en("integrationDirection"), True),
        f("idempotencyKey", vc(190), True, desc="UNIQUE(integrationId, idempotencyKey)"),
        f("payload", JSON, False, desc="documented JSON use: external payload"),
        f("status", en("integrationEventStatus"), True, indexed=True),
        f("processedAt", DT, False),
    ], retention="M"))

add(Entity("IntegrationError", "Integration", "Integration", "Error stream.", TENANT, A, [
    f("integrationId", UUID, True, fk="Integration", indexed=True),
    f("executionId", UUID, False, fk="IntegrationExecution", indexed=True),
    f("errorCode", vc(64), True),
    f("message", nvc(1000), True),
    f("occurredAt", DT, True, indexed=True),
], retention="M", auditable="△"))

# ============================ WINCC (EXTENSION) ============================
WINCC = "Industry Extension (pack — NOT Core)"
add(Entity("WinCcServer", WINCC, "Integration (Industry Pack)", "Server registry.", TENANT, B, [
    f("code", vc(64), True, indexed=True, desc="UNIQUE(tenantId, code)"),
    f("host", nvc(250), True),
    f("connectionProfile", JSON, False, desc="documented JSON use: connection config"),
], identity="code", retention="L"))
add(Entity("WinCcConnection", WINCC, "Integration (Industry Pack)", "Connection state.", TENANT, B, [
    f("serverId", UUID, True, fk="WinCcServer", desc="UNIQUE(serverId)"),
    f("status", en("connectionStatus"), True),
    f("lastSyncAt", DT, False),
], retention="M", auditable="△"))
add(Entity("WinCcTag", WINCC, "Integration (Industry Pack)", "Tag registry.", TENANT, B, [
    f("serverId", UUID, True, fk="WinCcServer", indexed=True),
    f("tagPath", vc(250), True, desc="UNIQUE(tenantId, serverId, tagPath)"),
    f("dataType", en("tagDataType"), True),
    f("unit", vc(32), False),
], retention="L"))
add(Entity("WinCcTagValue", WINCC, "Integration (Industry Pack)", "Time-series value.", TENANT, A, [
    f("tagId", UUID, True, fk="WinCcTag", indexed=True),
    f("value", dec(18, 6), True),
    f("quality", en("telemetryQuality"), False),
    f("occurredAt", DT, True, indexed=True),
], retention="C", auditable="—"))
add(Entity("WinCcAlarm", WINCC, "Integration (Industry Pack)", "Alarm stream.", TENANT, A, [
    f("serverId", UUID, True, fk="WinCcServer", indexed=True),
    f("alarmCode", vc(120), True),
    f("severity", en("severityLevel"), True),
    f("occurredAt", DT, True, indexed=True),
    f("acknowledgedAt", DT, False),
], retention="C", auditable="△"))
add(Entity("WinCcEvent", WINCC, "Integration (Industry Pack)", "Event stream.", TENANT, A, [
    f("serverId", UUID, True, fk="WinCcServer", indexed=True),
    f("eventType", vc(120), True),
    f("payload", JSON, False, desc="documented JSON use: event payload"),
    f("occurredAt", DT, True, indexed=True),
], retention="C", auditable="△"))
add(Entity("WinCcSyncJob", WINCC, "Integration (Industry Pack)", "Sync job.", TENANT, B, [
    f("serverId", UUID, True, fk="WinCcServer", desc="UNIQUE(serverId)"),
    f("config", JSON, False, desc="documented JSON use: sync config"),
    f("lastRunAt", DT, False),
    f("status", en("jobStatus"), True),
], retention="M"))

# ---------------------------------------------------------------------------
# Standard field blocks
# ---------------------------------------------------------------------------

BASE_BLOCK: list[FieldSpec] = [
    f("id", UUID, True, desc="primary key (UUID, §12 technical identity)"),
    f("tenantId", UUID, True, fk="Tenant", indexed=True,
      desc="tenant ownership (omitted on GLOBAL entities)"),
    f("createdAt", DT, True, desc="creation instant (UTC §51)"),
    f("updatedAt", DT, True, desc="last modification (UTC)"),
    f("createdBy", UUID, False, fk="User", desc="SET_NULL — audit survives user deletion"),
    f("updatedBy", UUID, False, fk="User", desc="SET_NULL"),
    f("deletedAt", DT, False, indexed=True, desc="null = not soft-deleted (§6)"),
    f("deletedBy", UUID, False, fk="User", desc="SET_NULL"),
    f("isActive", BOOL, True, default="true", desc="domain-logical default (§7)"),
]

APPEND_BLOCK: list[FieldSpec] = [
    f("id", UUID, True, desc="primary key (UUID)"),
    f("tenantId", UUID, True, fk="Tenant", indexed=True, desc="tenant ownership"),
    f("createdAt", DT, True, desc="row insert time (UTC); rows are immutable"),
]

VOCAB_FIELDS: list[FieldSpec] = [
    f("code", vc(64), True, indexed=True, desc="stable business code (§74)"),
    f("name", nvc(200), True),
    f("description", nvc(1000), False),
]

VERSION_FIELD = f("version", INT, True, default="1",
                  desc="optimistic concurrency (§50)")


def fieldsOf(e: Entity) -> list[FieldSpec]:
    result: list[FieldSpec]
    if e.kind == KIND_APPEND:
        result = APPEND_BLOCK + e.fields
    elif e.kind == KIND_VOCAB:
        result = BASE_BLOCK + VOCAB_FIELDS + e.fields
    else:  # base / link
        result = BASE_BLOCK + e.fields
    if e.versioned:
        result = result + [VERSION_FIELD]
    return result


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

GROUP_ORDER: list[str] = []


def titleFor(group: str) -> str:
    return f"## {group}"


def renderDictionary() -> str:
    lines = [
        "# DatabaseDictionary.md — Phase 05 field-level dictionary",
        "",
        "**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §2/§63",
        "**Generated from:** `tools/generatePhase5Catalogs.py` (single dataset →",
        "Dictionary + EntityCatalog + FieldCatalog; regenerate after any change).",
        "**Conventions:**",
        "- Field naming camelCase (§3) — snake_case/PascalCase forbidden.",
        "- Types by concept (§4): uuid · varchar(n) · nvarchar(n|max) · boolean ·",
        "  datetime(UTC) · date · time · integer · bigint · decimal(p,s) · json · enum(Name).",
        "- NULL semantics documented per field (§6); defaults only when domain-logical (§7).",
        "- Every enum references the controlled vocabulary in `07ConstraintCatalog.md` §2",
        "  or `StateMachineCatalog.md` where it is a state machine.",
        "- Money: decimal + ISO-4217 currency, never float (§52). Timestamps stored UTC (§51).",
        "- Standard blocks (below) apply to entities by kind; business fields listed per entity.",
        "",
        "### Standard field blocks",
        "",
        "| Block | Applies to | Fields |",
        "|---|---|---|",
        "| BASE | kind=base/link/vocab | id, tenantId (tenant-owned), createdAt, updatedAt, createdBy, updatedBy, deletedAt, deletedBy, isActive (+version when optimistic-locked) |",
        "| APPEND | kind=append | id, tenantId, createdAt — rows immutable, retention-purge only |",
        "| VOCAB | kind=vocab | BASE + code, name, description (stable reference data §73/§74) |",
        "",
        "---",
    ]
    currentGroup = None
    for e in ENTITIES:
        if e.group != currentGroup:
            currentGroup = e.group
            lines += ["", titleFor(currentGroup), ""]
        lines += [
            f"### {e.name}",
            "",
            f"- **Domain:** {e.group} · **Owner:** {e.owner}",
            f"- **Purpose:** {e.purpose}",
            f"- **Tenant scoped:** {e.tenantMode} (§9) · **Soft deletable:** {e.softDeletable}"
            f" · **Auditable:** {e.auditable}",
            f"- **Kind:** {e.kind} · **Business identity:** `{e.identity}` (§12)"
            f" · **State machine:** {e.statusEnum} · **Retention:** {e.retention}",
            f"- **Fields ({len(fieldsOf(e))}):** see `FieldCatalog.md` § “{e.name}”"
            " (standard block + business fields below)",
            "",
            "| Field | Type | Req | Null | Default | Unique | Index | FK | Description |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for spec in e.fields if e.kind != KIND_VOCAB else e.fields:
            lines.append("| " + " | ".join(spec.row()) + " |")
        if e.kind == KIND_VOCAB:
            lines.append("")
            lines.append("_+ VOCAB block: code · name · description_")
        lines.append("")
    return "\n".join(lines)


def renderEntityCatalog() -> str:
    lines = [
        "# EntityCatalog.md — Phase 05 entity attributes (§64)",
        "",
        "**Status:** DESIGN (Phase 05) · generated (see DatabaseDictionary.md header).",
        "Attributes per §64: Domain · Owner · Purpose · Tenant · Identity ·",
        "Lifecycle · Audit · Soft Delete.",
        "",
        "| Entity | Domain | Owner | Purpose | Tenant (§9) | Identity (§12) | Lifecycle (§69) | Audit | Soft Delete | Retention |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for e in ENTITIES:
        lines.append(
            f"| {e.name} | {e.group} | {e.owner} | {e.purpose} | {e.tenantMode} | "
            f"`{e.identity}` | {e.statusEnum} | {e.auditable} | {e.softDeletable} | {e.retention} |"
        )
    lines += [
        "",
        f"**Total entities:** {len(ENTITIES)}",
    ]
    return "\n".join(lines)


def renderFieldCatalog() -> str:
    lines = [
        "# FieldCatalog.md — Phase 05 field rows (§65)",
        "",
        "**Status:** DESIGN (Phase 05) · generated (see DatabaseDictionary.md header).",
        "Columns per §65: Entity · Name · Type · Required · Nullable · Default ·",
        "Unique · Index · FK · Description. Standard blocks (BASE/APPEND/VOCAB)",
        "are documented once in `DatabaseDictionary.md` and apply to every entity",
        "of that kind — they are NOT repeated per entity here.",
        "",
        "---",
    ]
    currentGroup = None
    for e in ENTITIES:
        if e.group != currentGroup:
            currentGroup = e.group
            lines += ["", titleFor(currentGroup), ""]
        lines += [
            f"### {e.name}",
            "",
            f"_kind: {e.kind}_ · _fields incl. standard block: {len(fieldsOf(e))}_",
            "",
            "| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for spec in e.fields:
            lines.append("| " + " | ".join(spec.row()) + " |")
        if e.kind == KIND_VOCAB:
            lines.append("| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    outputs = {
        "DatabaseDictionary.md": renderDictionary(),
        "EntityCatalog.md": renderEntityCatalog(),
        "FieldCatalog.md": renderFieldCatalog(),
    }
    for fileName, content in outputs.items():
        target = DATABASE_DIR / fileName
        target.write_text(content + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(DATABASE_DIR.parent.parent)} "
              f"({len(content.splitlines())} lines)")


if __name__ == "__main__":
    main()
