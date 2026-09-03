# 02 — Domain ER Diagrams

**Status:** DESIGN (Phase 04) · Mermaid `erDiagram` (version-control friendly)
**Spec:** `docs/Phases/Phase4.md` §9–28
Ownership = Phase 03 contexts (mapping in `README.md`). Base fields
(id/createdAt/updatedAt/createdBy/updatedBy/deletedAt/deletedBy/isActive)
are implicit on `«base»` entities and omitted below for readability —
full lists: `03DatabaseDictionary.md` · `04EntityCatalog.md`.

---

## 1. Platform Core · Tenancy · Configuration (spec §9)

```mermaid
erDiagram
    TENANT ||--o{ SYSTEM_SETTING : ""
    TENANT ||--o{ FEATURE : ""
    FEATURE ||--o{ FEATURE_FLAG : ""
    TENANT ||--o{ LOOKUP : ""
    LOOKUP ||--o{ LOOKUP_VALUE : ""
    TENANT ||--o{ TAG : ""
    TAG ||--o{ TAG_ASSIGNMENT : ""
    TENANT ||--o{ CUSTOM_FIELD_DEFINITION : ""
    CUSTOM_FIELD_DEFINITION ||--o{ CUSTOM_FIELD_VALUE : ""
    TENANT ||--o{ ATTACHMENT : ""
    TENANT ||--o{ ADDRESS : ""
    TENANT ||--o{ CONTACT_INFORMATION : ""
```

Notes: Tenant/Configuration settings are scoped (system/tenant). Address and
ContactInformation are shared re-usable records referenced by other domains
(polymorphic owner id + owner type).

## 2. Identity (spec §10)

```mermaid
erDiagram
    USER ||--o{ USER_ROLE : ""
    ROLE ||--o{ USER_ROLE : ""
    ROLE ||--o{ ROLE_PERMISSION : ""
    PERMISSION ||--o{ ROLE_PERMISSION : ""
    USER ||--o{ USER_PERMISSION : ""
    USER ||--o{ SESSION : ""
    USER ||--o{ AUTHENTICATION_METHOD : ""
    USER ||--o{ ACCESS_POLICY : ""
    USER ||--o{ SECURITY_EVENT : ""
```

User ≠ Employee (spec §10): Employee lives in Workforce. Credentials are
hashed/protected (never stored raw).

## 3. Organization (spec §11)

```mermaid
erDiagram
    TENANT ||--o{ ORGANIZATION : ""
    ORGANIZATION ||--o{ ORGANIZATION_UNIT : ""
    ORGANIZATION_UNIT ||--o{ ORGANIZATION_HIERARCHY : "parent-child"
    ORGANIZATION_UNIT ||--o{ DEPARTMENT : ""
    ORGANIZATION_UNIT ||--o{ DIVISION : ""
    ORGANIZATION_UNIT ||--o{ TEAM : ""
    ORGANIZATION ||--o{ POSITION : ""
    POSITION ||--o{ JOB_TITLE : ""
    ORGANIZATION ||--o{ LOCATION : ""
    ORGANIZATION ||--o{ COST_CENTER : ""
```

Hierarchy is generic (OrganizationUnit tree with typed nodes) — supports
complex enterprise structures, not only Company→Department (spec §11).

## 4. Workforce / HR + Performance (spec §12)

```mermaid
erDiagram
    USER |o--o| EMPLOYEE : "userId (optional link)"
    TENANT ||--o{ EMPLOYEE : ""
    EMPLOYEE ||--o{ EMPLOYMENT : ""
    EMPLOYMENT ||--o{ EMPLOYMENT_HISTORY : ""
    EMPLOYEE ||--o{ EMPLOYEE_ASSIGNMENT : "temporal (startDate/endDate)"
    EMPLOYEE ||--o{ EMPLOYEE_MANAGER : "reporting"
    EMPLOYEE ||--o{ EMPLOYEE_CONTACT : ""
    EMPLOYEE ||--o{ EMPLOYEE_ADDRESS : ""
    EMPLOYEE ||--o{ EMPLOYEE_DOCUMENT : ""
    EMPLOYEE ||--o{ EMPLOYEE_SKILL : ""
    SKILL ||--o{ EMPLOYEE_SKILL : ""
    CERTIFICATION ||--o{ EMPLOYEE_CERTIFICATION : ""
    EVALUATION_CYCLE ||--o{ EMPLOYEE_EVALUATION : ""
    EMPLOYEE ||--o{ EMPLOYEE_EVALUATION : ""
    EVALUATION_CYCLE ||--o{ EVALUATION_CRITERIA : ""
    EMPLOYEE_EVALUATION ||--o{ EVALUATION_SCORE : ""
```

Evaluation entities (EmployeeEvaluation/EvaluationCycle/EvaluationCriteria/
EvaluationScore) are owned by the **Performance** context (Phase 03
resolution); shown here together because spec §12 lists them under HR.
All important HR changes audited (spec §12).

## 5. Project (spec §13)

```mermaid
erDiagram
    TENANT ||--o{ PROJECT : ""
    PROJECT ||--o{ PROJECT_MEMBER : ""
    PROJECT_ROLE ||--o{ PROJECT_MEMBER : ""
    PROJECT ||--o{ PROJECT_PHASE : ""
    PROJECT ||--o{ PROJECT_MILESTONE : ""
    PROJECT ||--o{ PROJECT_DEPENDENCY : ""
    PROJECT ||--o{ PROJECT_BUDGET : ""
    PROJECT ||--o{ PROJECT_RISK : ""
    PROJECT ||--o{ PROJECT_ISSUE : ""
    PROJECT ||--o{ PROJECT_DOCUMENT : ""
```

Project is independent of Task implementation (spec §13) — Tasks reference
projects by id.

## 6. Task (spec §14)

```mermaid
erDiagram
    PROJECT |o--o{ TASK : "projectId (loose contract ref)"
    TASK_STATUS ||--o{ TASK : ""
    TASK_PRIORITY ||--o{ TASK : ""
    TASK_TYPE ||--o{ TASK : ""
    TASK ||--o{ TASK_ASSIGNMENT : ""
    TASK ||--o{ TASK_DEPENDENCY : ""
    TASK ||--o{ TASK_COMMENT : ""
    TASK ||--o{ TASK_ATTACHMENT : ""
    TASK ||--o{ TASK_CHECKLIST : ""
    TASK_CHECKLIST ||--o{ TASK_CHECKLIST_ITEM : "CASCADE candidate"
    TASK ||--o{ TASK_TIME_ENTRY : ""
    TASK ||--o{ TASK_HISTORY : "append-only"
```

## 7. Asset (spec §15)

```mermaid
erDiagram
    TENANT ||--o{ ASSET : ""
    ASSET_CATEGORY ||--o{ ASSET_TYPE : ""
    ASSET_TYPE ||--o{ ASSET : ""
    ASSET_STATUS ||--o{ ASSET : ""
    ASSET ||--o{ ASSET_ASSIGNMENT : ""
    ASSET ||--o{ ASSET_LOCATION : ""
    ASSET ||--o{ ASSET_OWNERSHIP : ""
    ASSET ||--o{ ASSET_LIFECYCLE : ""
    ASSET ||--o{ ASSET_DOCUMENT : ""
    ASSET ||--o{ ASSET_VALUE_HISTORY : "append-only"
```

Assets may be physical/digital/financial/operational (spec §15).

## 8. Device / OT + Agent (spec §16)

```mermaid
erDiagram
    ASSET |o--o{ DEVICE : "assetId (optional)"
    DEVICE_MANUFACTURER ||--o{ DEVICE_MODEL : ""
    DEVICE_MODEL ||--o{ DEVICE : ""
    DEVICE_TYPE ||--o{ DEVICE : ""
    DEVICE_STATUS ||--o{ DEVICE : ""
    DEVICE ||--o{ DEVICE_CREDENTIAL : ""
    DEVICE ||--o{ DEVICE_REGISTRATION : ""
    DEVICE ||--o{ DEVICE_HEARTBEAT : "append-only"
    DEVICE ||--o{ DEVICE_TELEMETRY : "append-only"
    DEVICE ||--o{ DEVICE_CONFIGURATION : "versioned"
    DEVICE ||--o{ DEVICE_EVENT : "append-only"
    TENANT ||--o{ AGENT : "software agent (distinct entity)"
```

Device (physical/logical) ≠ Agent (software agent) — never merged (spec §16).

## 9. Maintenance (spec §17)

```mermaid
erDiagram
    ASSET |o--o{ MAINTENANCE_PLAN : ""
    DEVICE |o--o{ MAINTENANCE_PLAN : ""
    MAINTENANCE_PLAN ||--o{ MAINTENANCE_SCHEDULE : ""
    MAINTENANCE_PLAN ||--o{ MAINTENANCE_WORK_ORDER : ""
    MAINTENANCE_WORK_ORDER ||--o{ MAINTENANCE_TASK : ""
    MAINTENANCE_WORK_ORDER ||--o{ MAINTENANCE_EVENT : ""
    MAINTENANCE_TECHNICIAN ||--o{ MAINTENANCE_TASK : ""
    MAINTENANCE_WORK_ORDER ||--o{ MAINTENANCE_PART : ""
    MAINTENANCE_WORK_ORDER ||--o{ MAINTENANCE_COST : ""
    MAINTENANCE_WORK_ORDER ||--o{ MAINTENANCE_HISTORY : "append-only"
```

Maintenance serves both Assets and Devices (spec §17).

## 10. Document (spec §18)

```mermaid
erDiagram
    TENANT ||--o{ DOCUMENT : ""
    DOCUMENT_TYPE ||--o{ DOCUMENT : ""
    DOCUMENT_CATEGORY ||--o{ DOCUMENT : ""
    DOCUMENT_FOLDER ||--o{ DOCUMENT : ""
    DOCUMENT ||--o{ DOCUMENT_VERSION : "immutable versions"
    DOCUMENT ||--o{ DOCUMENT_PERMISSION : ""
    DOCUMENT ||--o{ DOCUMENT_SHARE : ""
    DOCUMENT ||--o{ DOCUMENT_METADATA : ""
    DOCUMENT ||--o{ DOCUMENT_ATTACHMENT : ""
    DOCUMENT ||--o{ DOCUMENT_WORKFLOW : "trigger link"
```

Versions never overwrite (spec §18); binary content lives in object storage
(§40).

## 11. Workflow (spec §19)

```mermaid
erDiagram
    WORKFLOW ||--o{ WORKFLOW_VERSION : ""
    WORKFLOW_VERSION ||--o{ WORKFLOW_DEFINITION : ""
    WORKFLOW_DEFINITION ||--o{ WORKFLOW_NODE : ""
    WORKFLOW_NODE ||--o{ WORKFLOW_TRANSITION : "fromNode/toNode"
    WORKFLOW_DEFINITION ||--o{ WORKFLOW_INSTANCE : ""
    WORKFLOW_INSTANCE ||--o{ WORKFLOW_INSTANCE_STATE : ""
    WORKFLOW_INSTANCE ||--o{ WORKFLOW_TASK : ""
    WORKFLOW_INSTANCE ||--o{ WORKFLOW_ACTION : ""
    WORKFLOW_TASK ||--o{ WORKFLOW_APPROVAL : ""
    WORKFLOW_INSTANCE ||--o{ WORKFLOW_HISTORY : "append-only"
```

Generic engine — document/project/purchase/leave/maintenance approvals all
use the same entities (spec §19).

## 12. Communication (spec §20)

```mermaid
erDiagram
    TENANT ||--o{ CONVERSATION : ""
    CONVERSATION_TYPE ||--o{ CONVERSATION : ""
    CONVERSATION ||--o{ CONVERSATION_MEMBER : ""
    CONVERSATION ||--o{ MESSAGE : ""
    MESSAGE ||--o{ MESSAGE_ATTACHMENT : ""
    MESSAGE ||--o{ MESSAGE_REACTION : ""
    MESSAGE ||--o{ MESSAGE_READ_RECEIPT : ""
    CHANNEL ||--o{ CHANNEL_MEMBER : ""
    TENANT ||--o{ VOICE_CALL : ""
    VOICE_CALL ||--o{ VOICE_CALL_PARTICIPANT : ""
    TENANT ||--o{ GROUP_CALL : ""
    TENANT ||--o{ VIDEO_MEETING : ""
    VIDEO_MEETING ||--o{ MEETING_PARTICIPANT : ""
    VIDEO_MEETING ||--o{ MEETING_SESSION : ""
    MEETING_SESSION ||--o{ SCREEN_SHARE_SESSION : ""
    MEETING_SESSION ||--o{ MEETING_RECORDING : ""
    USER ||--o{ PRESENCE : ""
    PRESENCE_STATUS ||--o{ PRESENCE : ""
```

Four layers stay separate (spec §20): WebRTC media · Channels realtime ·
Redis infra · database persistent state.

## 13. Notification (spec §21)

```mermaid
erDiagram
    TENANT ||--o{ NOTIFICATION : ""
    NOTIFICATION ||--o{ NOTIFICATION_RECIPIENT : "read state lives here"
    NOTIFICATION ||--o{ NOTIFICATION_DELIVERY : "attempts"
    NOTIFICATION_TEMPLATE ||--o{ NOTIFICATION : ""
    NOTIFICATION_CHANNEL ||--o{ NOTIFICATION_DELIVERY : ""
    USER ||--o{ NOTIFICATION_PREFERENCE : ""
```

Event-driven creation; channels: in-app/email/SMS/push/realtime (spec §21).
Read-state on recipient (multi-recipient rule).

## 14. Audit (spec §22)

```mermaid
erDiagram
    TENANT ||--o{ AUDIT_EVENT : "append-only"
```

Single append-only table with actor/action/entity/before/after/correlation
detail — `09AuditModel.md`.

## 15. Reporting (spec §23)

```mermaid
erDiagram
    TENANT ||--o{ REPORT_DEFINITION : ""
    REPORT_DEFINITION ||--o{ REPORT_PARAMETER : ""
    REPORT_DEFINITION ||--o{ REPORT_EXECUTION : ""
    REPORT_DEFINITION ||--o{ REPORT_SCHEDULE : ""
    REPORT_EXECUTION ||--o{ REPORT_OUTPUT : ""
    REPORT_DEFINITION ||--o{ REPORT_ACCESS : ""
```

Reporting consumes domain data; domains never depend on reporting (spec §23).

## 16. Analytics (spec §24)

```mermaid
erDiagram
    TENANT ||--o{ METRIC_DEFINITION : ""
    METRIC_DEFINITION ||--o{ METRIC_VALUE : ""
    TENANT ||--o{ KPI_DEFINITION : ""
    KPI_DEFINITION ||--o{ KPI_VALUE : ""
    TENANT ||--o{ DASHBOARD : ""
    DASHBOARD ||--o{ DASHBOARD_WIDGET : ""
    TENANT ||--o{ ANALYTICS_SNAPSHOT : "daily/weekly/monthly/quarterly/yearly"
```

## 17. AI (spec §25)

```mermaid
erDiagram
    AI_PROVIDER ||--o{ AI_MODEL : ""
    AI_MODEL ||--o{ AI_MODEL_VERSION : ""
    TENANT ||--o{ AI_AGENT : ""
    AI_AGENT ||--o{ AI_AGENT_EXECUTION : ""
    TENANT ||--o{ AI_REQUEST : ""
    AI_REQUEST ||--o| AI_RESPONSE : ""
    AI_CONVERSATION ||--o{ AI_MESSAGE : ""
    AI_KNOWLEDGE_SOURCE ||--o{ AI_KNOWLEDGE_DOCUMENT : ""
    AI_KNOWLEDGE_DOCUMENT ||--o{ AI_EMBEDDING : ""
    TENANT ||--o{ AI_RECOMMENDATION : "advisory/draft/automated/authoritative"
    TENANT ||--o{ AI_PREDICTION : ""
    TENANT ||--o{ AI_INSIGHT : ""
```

AI never mutates other domains' tables directly (spec §25; ADR-013).

## 18. Integration (spec §26)

```mermaid
erDiagram
    INTEGRATION_TYPE ||--o{ INTEGRATION : ""
    INTEGRATION ||--o{ INTEGRATION_CREDENTIAL : "secret reference"
    INTEGRATION ||--o{ INTEGRATION_ENDPOINT : ""
    INTEGRATION ||--o{ INTEGRATION_CONNECTION : ""
    INTEGRATION ||--o{ INTEGRATION_MAPPING : ""
    INTEGRATION ||--o{ INTEGRATION_JOB : ""
    INTEGRATION_JOB ||--o{ INTEGRATION_EXECUTION : ""
    INTEGRATION ||--o{ INTEGRATION_EVENT : "in/out + idempotencyKey"
    INTEGRATION ||--o{ INTEGRATION_ERROR : ""
```

## 19. WinCC / Industrial (spec §28 — INDUSTRY EXTENSION, not Core)

```mermaid
erDiagram
    WINCC_SERVER ||--o{ WINCC_CONNECTION : ""
    WINCC_SERVER ||--o{ WINCC_TAG : ""
    WINCC_TAG ||--o{ WINCC_TAG_VALUE : "time-series"
    WINCC_SERVER ||--o{ WINCC_ALARM : ""
    WINCC_SERVER ||--o{ WINCC_EVENT : ""
    WINCC_SERVER ||--o{ WINCC_SYNC_JOB : ""
```

**Marked EXTENSION** — these tables live in an Industry Pack schema
(ADR-014), never in Core.
