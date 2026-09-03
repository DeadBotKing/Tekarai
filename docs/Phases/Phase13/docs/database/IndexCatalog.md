# IndexCatalog.md — Phase 05 index catalogue

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §56.
**Entry format (§56):** Index Name · Table · Columns · Unique · Purpose ·
Expected Query · Tenant-Scoped · Importance.
Deepens Phase 04 `06IndexStrategy.md` (strategy + standard patterns) to the
per-entry catalogue. **BR-PERF-001:** an index without a documented entry
here is an architecture violation.

**Standard tenant composite (Phase 04 §28):** every tenant-scoped table gets
`IX_<Table>_tenant_<leading>` starting with tenantId — one per table,
choosing the strongest secondary column (usually the scoped code or
parent+code). Below, domain-specific entries are listed explicitly; the
standard composite is implied per table and not repeated row by row.

Importance scale: **P1** hot path every request · **P2** list screens /
common filters · **P3** reports / admin / sweep jobs.

---

## Platform Core & Identity

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `UQG_Tenant_code` | Tenant | code | ✓ | tenant resolution by code | login/tenant pick | ✗ | P1 |
| `IX_User_email` | User | tenantId, email | ✓ | login lookup | authentication | ✓ | P1 |
| `IX_User_username` | User | tenantId, username | ✓ | login lookup | authentication | ✓ | P1 |
| `IX_Session_user_active` | Session | userId, expiresAt | ✗ | session validation + sweep | middleware token check | ✓ | P1 |
| `IX_UserRole_user` | UserRole | tenantId, userId | ✗ | permission load | authorization (6 layers) | ✓ | P1 |
| `IX_RolePermission_role` | RolePermission | tenantId, roleId | ✗ | permission expansion | authorization | ✓ | P1 |
| `IX_UserPermission_user` | UserPermission | tenantId, userId | ✗ | exception grants | authorization | ✓ | P1 |
| `IX_AuditEvent_correlation` | AuditEvent | tenantId, correlationId | ✗ | trace by correlation | incident tracing | ✓ | P2 |
| `IX_AuditEvent_entity` | AuditEvent | tenantId, entityType, entityId | ✗ | entity history view | audit screens | ✓ | P2 |
| `IX_AuditEvent_time` | AuditEvent | tenantId, occurredAt | ✗ | cursor-paginated stream (BR-PERF-002) | audit feed | ✓ | P2 |
| `IX_AuditEvent_actor_action` | AuditEvent | tenantId, actorUserId, action | ✗ | who-did-what queries | security review | ✓ | P3 |
| `IX_SystemSetting_scope_key` | SystemSetting | scope, key | ✓ | setting fetch | runtime config | ✗ | P1 |
| `IX_LookupValue_family` | LookupValue | tenantId, typeId, sortOrder | ✗ | vocab load | dropdowns | ✓ | P2 |

## Organization & Workforce

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_OrganizationUnit_parent` | OrganizationUnit | tenantId, parentId | ✗ | tree walk | org tree screen | ✓ | P2 |
| `IX_Employee_dept_active` | Employee | tenantId, departmentId, status | ✗ | dept roster | department view | ✓ | P2 |
| `IX_EmployeeManager_employee` | EmployeeManager | tenantId, employeeId | ✗ | reporting line | manager chain | ✓ | P2 |
| `IX_EmployeeAssignment_emp_dates` | EmployeeAssignment | tenantId, employeeId, startDate | ✗ | temporal history | assignment timeline | ✓ | P2 |
| `IX_Employment_emp_dates` | Employment | tenantId, employeeId, startDate | ✗ | employment history | HR view | ✓ | P2 |
| `IX_EmployeeSkill_skill` | EmployeeSkill | tenantId, skillId, level | ✗ | skill search | resource finder | ✓ | P2 |
| `IX_EmployeeCertification_cert` | EmployeeCertification | tenantId, certificationId, expiresAt | ✗ | expiring certs report | compliance report | ✓ | P3 |
| `IX_Position_dept` | Position | tenantId, departmentId | ✗ | dept positions | org charts | ✓ | P3 |

## Projects & Tasks

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_Project_status_dates` | Project | tenantId, status, startDate | ✗ | portfolio by state | project list | ✓ | P2 |
| `IX_Project_manager` | Project | tenantId, ownerId | ✗ | my projects | dashboard | ✓ | P1 |
| `IXF_ProjectMember_user_active` | ProjectMember | tenantId, userId, projectId WHERE leftAt IS NULL | ✗ | my active projects | dashboard, authz | ✓ | P1 |
| `IX_ProjectMember_project` | ProjectMember | tenantId, projectId | ✗ | team of project | project team tab | ✓ | P2 |
| `IX_Task_board` | Task | tenantId, projectId, statusId, sortOrder | ✗ | kanban board query | board load | ✓ | P1 |
| `IX_Task_assignee_open` | Task | tenantId, assigneeId, statusId | ✗ | my open tasks | my-work screen | ✓ | P1 |
| `IX_Task_parent` | Task | tenantId, parentTaskId | ✗ | subtask expansion | task detail | ✓ | P2 |
| `IX_Task_deadline` | Task | tenantId, deadlineAt | ✗ | due-soon queries | reminders sweep | ✓ | P2 |
| `IX_TaskDependency_blocked` | TaskDependency | tenantId, blockedById | ✗ | what blocks X | dependency graph | ✓ | P2 |
| `IX_ProjectPhase_project_order` | ProjectPhase | tenantId, projectId, sortOrder | ✗ | phase strip | project timeline | ✓ | P2 |
| `IX_Milestone_due` | Milestone | tenantId, projectId, dueDate | ✗ | upcoming milestones | reports | ✓ | P3 |
| `IX_ProjectDependency_pred` | ProjectDependency | tenantId, predecessorId | ✗ | dependency graph | PMO analysis | ✓ | P3 |
| `IX_Risk_open` | Risk | tenantId, status, impact, probability | ✗ | risk register | risk screen | ✓ | P3 |
| `IX_Issue_status` | Issue | tenantId, status, severity | ✗ | issue triage | issue list | ✓ | P2 |

## Documents

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_Document_folder` | Document | tenantId, folderId | ✗ | folder browse | document tree | ✓ | P1 |
| `IX_Document_status_type` | Document | tenantId, statusId, typeId | ✗ | filtered lists | library screens | ✓ | P2 |
| `IXF_DocumentVersion_current` | DocumentVersion | tenantId, documentId, versionNumber | ✓ | current version resolve | document open | ✓ | P1 |
| `IX_DocumentFolder_parent` | DocumentFolder | tenantId, parentId | ✗ | folder tree | tree navigation | ✓ | P2 |
| `IX_DocumentShare_doc` | DocumentShare | tenantId, documentId | ✗ | shares of doc | sharing tab | ✓ | P3 |
| `IX_Attachment_target` | Attachment | tenantId, targetType, targetId | ✗ | attachments of entity | detail tabs | ✓ | P2 |

## Assets & Maintenance

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_Asset_category_status` | Asset | tenantId, categoryId, status | ✗ | asset register | asset list | ✓ | P2 |
| `IX_AssetAssignment_emp_active` | AssetAssignment | tenantId, employeeId WHERE returnedAt IS NULL | ✗ | my assets | profile assets | ✓ | P2 |
| `IX_MaintenanceWorkOrder_status_due` | MaintenanceWorkOrder | tenantId, status, scheduledAt | ✗ | open work orders | maintenance board | ✓ | P1 |
| `IX_MaintenanceWorkOrder_target` | MaintenanceWorkOrder | tenantId, targetType, targetId | ✗ | service history of asset/loc | asset history | ✓ | P2 |
| `IX_Device_status` | Device | tenantId, status, lastSeenAt | ✗ | offline sweep (BR-DEV-001) | device monitor | ✓ | P2 |
| `IX_DeviceTelemetry_device_time` | DeviceTelemetry | tenantId, deviceId, recordedAt | ✗ | telemetry stream (cursor §BR-PERF-002) | telemetry charts | ✓ | P2 |
| `IX_DeviceHeartbeat_device_time` | DeviceHeartbeat | tenantId, deviceId, occurredAt | ✗ | lastSeen derivation | online policy job | ✓ | P2 |

## Workflow Engine

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_WorkflowDefinition_key` | WorkflowDefinition | tenantId, definitionKey | ✓ | definition resolve | start instance | ✓ | P1 |
| `IXF_WorkflowVersion_active` | WorkflowVersion | tenantId, workflowId, versionNumber | ✓ | version pinning (BR-WF2-002) | instance start | ✓ | P1 |
| `IX_WorkflowInstance_target` | WorkflowInstance | tenantId, targetType, targetId | ✗ | open workflows of entity | entity workflow tab | ✓ | P1 |
| `IX_WorkflowInstance_status` | WorkflowInstance | tenantId, status | ✗ | running instances | admin monitor | ✓ | P2 |
| `IX_WorkflowTask_assignee_state` | WorkflowTask | tenantId, assigneeId, status | ✗ | my approvals | approval inbox | ✓ | P1 |
| `IX_WorkflowApproval_instance_time` | WorkflowApproval | tenantId, instanceId, decidedAt | ✗ | approval trail | audit view | ✓ | P2 |

## Communication & Collaboration

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_Conversation_member_recent` | Conversation | tenantId, lastMessageAt | ✗ | chat list ordering | inbox | ✓ | P1 |
| `IXF_ConversationMember_user_active` | ConversationMember | tenantId, userId, conversationId WHERE leftAt IS NULL | ✗ | my conversations | inbox, authz | ✓ | P1 |
| `IX_Message_stream` | Message | tenantId, conversationId, createdAt | ✗ | message stream cursor-paginated (BR-PERF-002) | chat history | ✓ | P1 |
| `IXF_MessageEdit_history` | MessageEdit | tenantId, messageId, editedAt | ✗ | edit history | message audit | ✓ | P3 |
| `IX_VoiceCall_participant` | VoiceCallParticipant | tenantId, callId | ✗ | participants of call | call detail | ✓ | P3 |
| `IX_GroupCall_conversation` | GroupCall | tenantId, conversationId, startedAt | ✗ | call history of chat | history tab | ✓ | P3 |
| `IX_Meeting_time_range` | Meeting | tenantId, scheduledAt | ✗ | calendar range queries | calendar view | ✓ | P1 |
| `IX_MeetingParticipant_user` | MeetingParticipant | tenantId, userId, meetingId | ✗ | my meetings | calendar | ✓ | P1 |
| `IX_Notification_recipient_unread` | NotificationRecipient | tenantId, userId, isRead | ✗ | unread badge | header bell | ✓ | P1 |
| `IX_NotificationDelivery_status` | NotificationDelivery | tenantId, status, channel | ✗ | dispatch queue | delivery worker | ✓ | P1 |
| `IX_Presence_user_status` | Presence | tenantId, userId | ✗ | presence read model | roster sidebar | ✓ | P2 |

## AI

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_AiRequest_trace` | AiRequest | tenantId, requestId | ✓ | provider trace (BR-AI-002) | explainability view | ✓ | P2 |
| `IX_AiResponse_request` | AiResponse | tenantId, requestId | ✗ | output of request | decision trace | ✓ | P2 |
| `IX_AiRecommendation_status` | AiRecommendation | tenantId, status, createdAt | ✗ | review queue | advisory review | ✓ | P2 |
| `IX_AiModel_provider` | AiModel | tenantId, provider | ✗ | model catalogue | model picker | ✓ | P3 |

## Integrations

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_IntegrationEndpoint_target` | IntegrationEndpoint | tenantId, targetType, targetId | ✗ | endpoints for event | dispatch router | ✓ | P1 |
| `IX_IntegrationExecution_time` | IntegrationExecution | tenantId, executedAt | ✗ | execution stream (cursor) | log viewer | ✓ | P2 |
| `IX_IntegrationExecution_status` | IntegrationExecution | tenantId, status | ✗ | failed/retrying monitor | admin monitor | ✓ | P2 |
| `IX_IntegrationEvent_status` | IntegrationEvent | tenantId, status, receivedAt | ✗ | inbound queue | event worker | ✓ | P1 |
| `UQ_IntegrationEvent_idem` | IntegrationEvent | integrationId, idempotencyKey | ✓ | idempotency (BR-INT-003) | duplicate detect | ✓ | P1 |
| `IX_IntegrationError_execution` | IntegrationError | tenantId, executionId | ✗ | error drill-down | debugging | ✓ | P2 |

## Billing & Subscriptions

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_Subscription_tenant_active` | Subscription | tenantId, status | ✗ | active plan resolve | entitlement middleware | ✓ | P1 |
| `IX_Invoice_tenant_time` | Invoice | tenantId, issuedAt | ✗ | invoice list | billing history | ✓ | P2 |
| `IX_Payment_invoice` | Payment | tenantId, invoiceId | ✗ | payments of invoice | reconciliation | ✓ | P2 |

## Evaluation (Performance)

| Index | Table | Columns | U | Purpose | Expected query | T | Imp |
|---|---|---|---|---|---|---|---|
| `IX_EvaluationCycle_status` | EvaluationCycle | tenantId, status | ✗ | active cycle resolve | evaluation entry | ✓ | P1 |
| `IX_EvaluationScore_cycle_emp` | EvaluationScore | tenantId, cycleId, employeeId | ✗ | score sheet load | scoring screen | ✓ | P1 |
| `IX_EvaluationCriteria_cycle_order` | EvaluationCriteria | tenantId, cycleId, sortOrder | ✗ | criteria list | score sheet | ✓ | P1 |
| `IX_EmployeeEvaluationReviewer_cycle` | EmployeeEvaluation | tenantId, cycleId, employeeId | ✗ | my pending reviews | reviewer queue | ✓ | P1 |

---

## Forbidden / anti-patterns (Phase 04 §31 restated)

- Index on `deletedAt` alone (low selectivity) — always composite after
  tenant.
- Single-column index on status/type columns standalone (low cardinality).
- Index per sortable column of large streams — use the composite
  (entity, time) cursor pattern instead.
- Unique index on business code without tenantId (except GLOBAL tables).

## Governance

- New index ⇒ row here (all §56 columns) + justification + review; removal ⇒
  row struck with reason and date.
- Importance drives migration ordering in Phase 06: P1 indexes ship with the
  first migration of their domain; P3 may follow.
