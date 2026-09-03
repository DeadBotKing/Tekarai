# 07 — Constraint Catalog

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §32, §37
Uniqueness is enforced in the database, tenant-aware (spec §32). Statuses
are controlled vocabularies, never free strings on sensitive entities
(spec §37).

---

## 1. Tenant-Aware Unique Constraints (spec §32: UNIQUE(tenantId, …), not UNIQUE(code))

| Entity | Unique constraint |
|---|---|
| Tenant | `(code)` — platform-global |
| Organization | `(tenantId, code)` |
| OrganizationUnit | `(tenantId, organizationId, code)` |
| Position / JobTitle / Location / CostCenter | `(tenantId, code)` |
| User | `(tenantId, username)`, `(tenantId, email)` |
| Role / Skill / Certification / Lookup / Tag | `(tenantId, code)` |
| LookupValue | `(tenantId, lookupId, code)` |
| FeatureFlag | `(tenantId, featureId, scope)` |
| SystemSetting | `(scope, key)` |
| Configuration | `(tenantId, scope, key)` |
| CustomFieldDefinition | `(tenantId, code)` |
| Employee | `(tenantId, employeeNumber)`, `(userId)` where not null |
| EvaluationCycle | `(tenantId, code)` |
| EmployeeEvaluation | `(evaluationCycleId, employeeId)` |
| EvaluationCriteria | `(evaluationCycleId, code)` |
| EvaluationScore | `(evaluationId, criteriaId, reviewerId)` |
| Project / ProjectRole | `(tenantId, code)` |
| ProjectMember | `(projectId, userId)` |
| ProjectPhase | `(projectId, order)` |
| Task | `(tenantId, code)` |
| TaskStatus/Priority/Type | `(tenantId, code)` |
| TaskAssignment | `(taskId, userId, assignedAt)` |
| TaskDependency | `(taskId, dependsOnTaskId)` |
| TaskChecklistItem | `(checklistId, label)` |
| Asset / AssetType / AssetStatus | `(tenantId, code)` |
| AssetType | `(tenantId, categoryId, code)` |
| Device / DeviceType / DeviceManufacturer | `(tenantId, code)` |
| DeviceModel | `(tenantId, manufacturerId, code)` |
| DeviceConfiguration | `(deviceId, version)` |
| Agent | `(tenantId, code)` |
| MaintenancePlan / WorkOrder | `(tenantId, code)` |
| MaintenanceSchedule | `(planId, dueAt)` |
| Document / DocumentType | `(tenantId, code)` |
| DocumentVersion | `(documentId, versionNumber)` — versions immutable (spec §18) |
| DocumentFolder | `(tenantId, parentId, name)` |
| DocumentPermission | `(documentId, subjectType, subjectId, permissionLevel)` |
| Workflow | `(tenantId, code)` |
| WorkflowVersion | `(workflowId, versionNumber)` |
| WorkflowNode | `(workflowDefinitionId, nodeKey)` |
| WorkflowTransition | `(workflowDefinitionId, fromNodeKey, toNodeKey)` |
| ConversationMember | `(conversationId, userId)` |
| MessageReaction | `(messageId, userId, emoji)` |
| MessageReadReceipt | `(messageId, userId)` |
| MeetingSession | `(meetingId, sessionKey)` |
| Presence | `(userId, deviceId)` |
| NotificationTemplate | `(tenantId, code, version)` |
| NotificationPreference | `(userId, notificationType, channel)` |
| NotificationRecipient | `(notificationId, userId)` |
| ReportDefinition / MetricDefinition / KpiDefinition / Dashboard | `(tenantId, code)` |
| AiProvider/AiModel registry | `(code)` / `(providerId, code)`; `(modelId, version)` |
| AiAgent | `(tenantId, code)` |
| AiResponse | `(requestId)` |
| Integration | `(tenantId, code)` |
| IntegrationEvent | `(integrationId, idempotencyKey)` — duplicate delivery guard |
| WinCC (extension) | `(tenantId, code)` server; `(tenantId, serverId, tagPath)` tag |

## 2. Enumerated / Controlled Vocabulary Statuses (spec §37)

Stored as controlled vocabularies via reference entities (TaskStatus,
AssetStatus, DeviceStatus, PresenceStatus, NotificationChannel,
ConversationType, IntegrationType) or enum columns on sensitive entities:

| Entity/field | Values |
|---|---|
| Tenant.status | active · suspended · closed |
| User.status | active · suspended · locked · deactivated · pending |
| Session lifecycle | active · expired · revoked |
| Employee.status | active · onLeave · terminated · archived |
| EvaluationCycle.status | draft · open · reviewing · closed |
| Project.status | draft · active · onHold · closed · cancelled |
| Task lifecycle | backlog · todo · inProgress · inReview · blocked · done · cancelled |
| Asset/Device status | registered · active · inactive · maintenance · retired |
| WorkOrder.status | draft · scheduled · inProgress · done · verified · cancelled |
| Document.status | draft · inReview · approved · published · archived · rejected |
| WorkflowVersion.status | draft · published · retired |
| WorkflowInstance.status | running · completed · cancelled · failed |
| Approval.decision | approved · rejected · delegated |
| Conversation.type | direct · group · channel · meeting · system |
| Presence status | online · away · busy · invisible · offline |
| Notification priority/status | low/normal/high/urgent · pending/sent/delivered/failed |
| AiResponse.resultClassification | advisory · draft · automated · authoritative (ADR-013) |
| IntegrationEvent direction/status | in/out · pending/processed/failed/dead |

Free-string status columns are forbidden on the above.

## 3. Check-Style Business Constraints (enforced domain-side + DB check where supported)

| Constraint | Rule |
|---|---|
| Date ordering | startDate ≤ endDate (EvaluationCycle, dateRange VOs, Project phases, Leave) |
| Task deadline | deadline ≥ startDate; subtask deadline within parent window |
| Dependency graphs (Task, Project) | acyclic (validated in domain; DB cannot express) |
| EvaluationCriteria weights | Σ weight = 100% per cycle |
| EvaluationScore | score within criteria bounds; weight percentage 0–100 |
| One active Employment per Employee | filtered unique (07-style partial unique; engine notes §5) |
| EmployeeAssignment overlap | no overlapping active assignments for same employee+unit (domain check) |
| AssetOwnership share | Σ shares per asset ≤ 100% at any point in time |
| DocumentVersion | versionNumber monotonically increasing; row immutable after insert |
| WorkflowInstance transitions | only defined WorkflowTransition edges (domain engine check) |
| Money | Decimal(19,4) + ISO currency code; amount ≥ 0 where business requires |
| Percentage/Score | 0–100 (Decimal) |
| Folder/OrgUnit hierarchy | acyclic parent chain (domain + depth guard) |

## 4. Foreign Key Rules

- All FKs declared with explicit delete behavior from
  `05RelationshipCatalog.md` (CASCADE forbidden unless registered §11 there).
- Cross-context FKs follow the Phase 03 dependency matrix; loose references
  (Task→Project) may be plain UUID + application contract validation when
  decoupling requires it (documented per relationship in 05).

## 5. Engine-Specific Notes (spec §2 — each documented)

| Feature | Status |
|---|---|
| UUID PK (uniqueidentifier) | used via Django/mssql-django |
| Filtered/partial unique indexes (e.g. one-active-employment) | SQL Server filtered index — implementation-phase decision, documented per table |
| rowversion concurrency | optional per sensitive entity (04 Notes); engine-specific |
| Partitioning for append-only streams | implementation-phase decision (06 §5) |

No other engine-specific features are used by this design.
