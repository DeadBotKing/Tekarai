# EntityCatalog.md — Phase 05 entity attributes (§64)

**Status:** DESIGN (Phase 05) · generated (see DatabaseDictionary.md header).
Attributes per §64: Domain · Owner · Purpose · Tenant · Identity ·
Lifecycle · Audit · Soft Delete.

| Entity | Domain | Owner | Purpose | Tenant (§9) | Identity (§12) | Lifecycle (§69) | Audit | Soft Delete | Retention |
|---|---|---|---|---|---|---|---|---|---|
| Tenant | Platform Core · Tenancy · Configuration | Tenancy | Top isolation boundary of the platform. | GLOBAL | `code` | Tenant | ✓ | ✓ | L |
| SystemSetting | Platform Core · Tenancy · Configuration | Configuration | System-scoped runtime setting. | GLOBAL | `—` | — | ✓ | ✓ | L |
| Feature | Platform Core · Tenancy · Configuration | Configuration | Registered product feature. | GLOBAL | `code` | — | ✓ | ✓ | L |
| FeatureFlag | Platform Core · Tenancy · Configuration | Configuration | Feature-flag state per scope. | HYBRID | `—` | — | ✓ | ✓ | M |
| Configuration | Platform Core · Tenancy · Configuration | Configuration | Scoped configuration entry. | HYBRID | `—` | — | ✓ | ✓ | L |
| Lookup | Platform Core · Tenancy · Configuration | Configuration | Controlled list group. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| LookupValue | Platform Core · Tenancy · Configuration | Configuration | Controlled list entry. | TENANT_SCOPED | `code` | — | ✓ | ✓ | M |
| Tag | Platform Core · Tenancy · Configuration | Platform Core | Free taxonomy tag. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| TagAssignment | Platform Core · Tenancy · Configuration | Platform Core | Polymorphic tag link (append-only). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| CustomFieldDefinition | Platform Core · Tenancy · Configuration | Platform Core | Extension field schema (spec §42). | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| CustomFieldValue | Platform Core · Tenancy · Configuration | Platform Core | Extension field data. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| Attachment | Platform Core · Tenancy · Configuration | Platform Core | File metadata record (binary in object storage, §40). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| Address | Platform Core · Tenancy · Configuration | Platform Core | Reusable postal address. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| ContactInformation | Platform Core · Tenancy · Configuration | Platform Core | Reusable contact record. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| User | Identity | Identity | Authentication principal (≠ Employee, §15). | TENANT_SCOPED | `username` | User | ✓ | ✓ | L |
| Role | Identity | Identity | Role definition. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| Permission | Identity | Identity | Action-based permission catalogue (§42). | GLOBAL | `code` | — | ✓ | ✓ | L |
| RolePermission | Identity | Identity | Role↔permission link. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| UserRole | Identity | Identity | Scoped user↔role grant. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| UserPermission | Identity | Identity | Direct user permission (allow/deny). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| Session | Identity | Identity | Session/token record. | TENANT_SCOPED | `—` | Session | ✓ | ✓ | S |
| AuthenticationMethod | Identity | Identity | Authentication factor (MFA-ready). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| AccessPolicy | Identity | Identity | Access policy rule. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| SecurityEvent | Identity | Identity | Append-only security telemetry. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | L |
| Organization | Organization | Organization | Legal-entity root of tenant structure. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| OrganizationUnit | Organization | Organization | Generic hierarchy node (typed by children). | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| Department | Organization | Organization | Department typed unit. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| Division | Organization | Organization | Division typed unit. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| Team | Organization | Organization | Team typed unit. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| Position | Organization | Organization | Organizational position definition. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| JobTitle | Organization | Organization | Job-title catalogue. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| Location | Organization | Organization | Physical site. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| CostCenter | Organization | Organization | Cost center. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| OrganizationHierarchy | Organization | Organization | Temporal hierarchy facts (§36). | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| Employee | Workforce / HR | Workforce | Person/employment record (≠ User, §15/§16). | TENANT_SCOPED | `employeeNumber` | Employee | ✓ | ✓ | L |
| Employment | Workforce / HR | Workforce | Employment record. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| EmploymentHistory | Workforce / HR | Workforce | Append-only employment facts. | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| EmployeeAssignment | Workforce / HR | Workforce | Temporal unit assignment (§16: history preserved). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| EmployeeManager | Workforce / HR | Workforce | Reporting relationship (temporal). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| EmployeeContact | Workforce / HR | Workforce | Employee contacts. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| EmployeeAddress | Workforce / HR | Workforce | Employee addresses. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| EmployeeDocument | Workforce / HR | Workforce | Employee↔document link. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| EmployeeSkill | Workforce / HR | Workforce | Employee skill level. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| Skill | Workforce / HR | Workforce | Skill catalogue. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| EmployeeCertification | Workforce / HR | Workforce | Employee certification. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| Certification | Workforce / HR | Workforce | Certification catalogue. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| EvaluationCycle | Performance | Performance | Evaluation period. | TENANT_SCOPED | `code` | EvaluationCycle | ✓ | ✓ | L |
| EmployeeEvaluation | Performance | Performance | Aggregate root of one evaluation (Phase 03 §6). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| EvaluationCriteria | Performance | Performance | Criterion per cycle. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| EvaluationScore | Performance | Performance | Score per criterion/reviewer (editable + audited). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| Project | Project | Projects | Project aggregate root. | TENANT_SCOPED | `code` | Project | ✓ | ✓ | L |
| ProjectMember | Project | Projects | Project membership with data (§19). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| ProjectRole | Project | Projects | Project role catalogue. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| ProjectPhase | Project | Projects | Project phase. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| ProjectMilestone | Project | Projects | Project milestone. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| ProjectDependency | Project | Projects | Project↔project dependency. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| ProjectBudget | Project | Projects | Budget line. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| ProjectRisk | Project | Projects | Risk register entry. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| ProjectIssue | Project | Projects | Issue register entry. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| ProjectDocument | Project | Projects | Project↔document link. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| Task | Task | Tasks | Task aggregate root (project-optional, §20). | TENANT_SCOPED | `code` | Task | ✓ | ✓ | L |
| TaskStatus | Task | Tasks | Task status vocabulary. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| TaskPriority | Task | Tasks | Task priority vocabulary. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| TaskType | Task | Tasks | Task type vocabulary. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| TaskAssignment | Task | Tasks | Task↔user assignment with data. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| TaskDependency | Task | Tasks | Task→task dependency (§21). | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| TaskComment | Task | Tasks | Append-oriented comments. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| TaskAttachment | Task | Tasks | Task attachment link. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| TaskChecklist | Task | Tasks | Task checklist. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| TaskChecklistItem | Task | Tasks | Checklist item (justified CASCADE child). | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| TaskTimeEntry | Task | Tasks | Time tracking (append-only). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| TaskHistory | Task | Tasks | Append-only activity stream. | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| Asset | Asset | Assets | Enterprise asset root (§24). | TENANT_SCOPED | `code` | Asset | ✓ | ✓ | L |
| AssetCategory | Asset | Assets | Asset category tree. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| AssetType | Asset | Assets | Asset type. | TENANT_SCOPED | `code` | — | △ | ✓ | L |
| AssetStatus | Asset | Assets | Asset status vocabulary. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| AssetAssignment | Asset | Assets | Custody (temporal; history preserved §24). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| AssetLocation | Asset | Assets | Location (temporal). | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| AssetOwnership | Asset | Assets | Ownership shares (temporal). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| AssetLifecycle | Asset | Assets | Lifecycle events (append-only). | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| AssetDocument | Asset | Assets | Asset↔document link. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| AssetValueHistory | Asset | Assets | Value over time (append-only). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | L |
| Device | Device / OT | Devices | Physical/logical device (§25). | TENANT_SCOPED | `code` | Device | ✓ | ✓ | L |
| DeviceType | Device / OT | Devices | Device type vocabulary. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DeviceManufacturer | Device / OT | Devices | Manufacturer catalogue. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| DeviceModel | Device / OT | Devices | Device model. | TENANT_SCOPED | `code` | — | — | ✓ | L |
| DeviceStatus | Device / OT | Devices | Device status vocabulary. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DeviceCredential | Device / OT | Devices | Credential reference. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| DeviceRegistration | Device / OT | Devices | Registration facts (auditable §25). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| DeviceHeartbeat | Device / OT | Devices | Heartbeat stream. | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| DeviceTelemetry | Device / OT | Devices | Telemetry stream. | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| DeviceConfiguration | Device / OT | Devices | Versioned configuration. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| DeviceEvent | Device / OT | Devices | Device event stream. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | C |
| Agent | Device / OT | Devices | Software agent (≠ Device, §16). | TENANT_SCOPED | `code` | — | ✓ | ✓ | M |
| MaintenancePlan | Maintenance | Maintenance | Maintenance plan for asset/device (§26). | TENANT_SCOPED | `code` | MaintenancePlan | ✓ | ✓ | L |
| MaintenanceSchedule | Maintenance | Maintenance | Scheduled occurrence. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| MaintenanceWorkOrder | Maintenance | Maintenance | Work order (§26). | TENANT_SCOPED | `code` | Maintenance | ✓ | ✓ | L |
| MaintenanceTask | Maintenance | Maintenance | Work-order task. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| MaintenanceEvent | Maintenance | Maintenance | Work-order events. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | L |
| MaintenanceTechnician | Maintenance | Maintenance | Technician registry. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| MaintenancePart | Maintenance | Maintenance | Part usage. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| MaintenanceCost | Maintenance | Maintenance | Cost record. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| MaintenanceHistory | Maintenance | Maintenance | History stream. | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| Document | Document | Documents | Document root (§22). | TENANT_SCOPED | `code` | Document | ✓ | ✓ | L |
| DocumentVersion | Document | Documents | Immutable version (§23). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| DocumentType | Document | Documents | Document type vocabulary. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DocumentCategory | Document | Documents | Category tree. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DocumentFolder | Document | Documents | Folder tree (acyclic). | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DocumentPermission | Document | Documents | Document ACL. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| DocumentShare | Document | Documents | Share grant. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| DocumentMetadata | Document | Documents | Metadata entry. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| DocumentAttachment | Document | Documents | Document attachment link. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| DocumentWorkflow | Document | Documents | Workflow trigger link. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| Workflow | Workflow | Workflow | Named workflow (generic §34). | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| WorkflowVersion | Workflow | Workflow | Version (never overwritten §34). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| WorkflowDefinition | Workflow | Workflow | Definition per version. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| WorkflowNode | Workflow | Workflow | Graph node. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| WorkflowTransition | Workflow | Workflow | Graph edge. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| WorkflowInstance | Workflow | Workflow | Running instance (independent state §34). | TENANT_SCOPED | `—` | Workflow | ✓ | ✓ | L |
| WorkflowInstanceState | Workflow | Workflow | Current state snapshot. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| WorkflowTask | Workflow | Workflow | Human task. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| WorkflowAction | Workflow | Workflow | Actions taken (append-only). | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| WorkflowApproval | Workflow | Workflow | Approval decision (§35). | TENANT_SCOPED | `—` | Approval | ✓ | ✓ | L |
| WorkflowHistory | Workflow | Workflow | Transition history. | TENANT_SCOPED | `—` | — | ✓ | ✗ (append-only) | L |
| Conversation | Communication | Communication | Chat aggregate (§27). | TENANT_SCOPED | `—` | Conversation | ✓ | ✓ | M |
| ConversationMember | Communication | Communication | Membership with data. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| ConversationType | Communication | Communication | Type vocabulary. | GLOBAL | `—` | — | — | ✓ | L |
| Message | Communication | Communication | Message (immutable/edit-policy §27). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| MessageAttachment | Communication | Communication | Message attachment. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| MessageReaction | Communication | Communication | Reaction. | TENANT_SCOPED | `—` | — | — | ✓ | S |
| MessageReadReceipt | Communication | Communication | Read state. | TENANT_SCOPED | `—` | — | — | ✓ | S |
| Channel | Communication | Communication | Channel profile. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| ChannelMember | Communication | Communication | Channel membership. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| VoiceCall | Communication | Communication | Voice call metadata (§28). | TENANT_SCOPED | `—` | Call | △ | ✓ | M |
| VoiceCallParticipant | Communication | Communication | Call participant. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| GroupCall | Communication | Communication | Group call metadata. | TENANT_SCOPED | `—` | Call | △ | ✓ | M |
| VideoMeeting | Communication | Communication | Meeting (§29). | TENANT_SCOPED | `—` | Meeting | ✓ | ✓ | L |
| MeetingParticipant | Communication | Communication | Meeting participant. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| MeetingSession | Communication | Communication | Session (reconnect/recurring). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| ScreenShareSession | Communication | Communication | Screen-share session. | TENANT_SCOPED | `—` | — | △ | ✓ | S |
| MeetingRecording | Communication | Communication | Recording metadata (§29). | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| Presence | Communication | Communication | Presence (realtime source = Redis §30). | TENANT_SCOPED | `—` | — | — | ✓ | S |
| PresenceStatus | Communication | Communication | Presence vocabulary. | GLOBAL | `—` | — | — | ✓ | L |
| Notification | Notification | Notifications | Notification root (event-driven §36). | TENANT_SCOPED | `—` | Notification | ✓ | ✓ | S |
| NotificationTemplate | Notification | Notifications | Versioned template. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| NotificationPreference | Notification | Notifications | User preference. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| NotificationChannel | Notification | Notifications | Channel vocabulary. | GLOBAL | `—` | — | — | ✓ | L |
| NotificationDelivery | Notification | Notifications | Delivery attempt (§31). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | S |
| NotificationRecipient | Notification | Notifications | Recipient + read state. | TENANT_SCOPED | `—` | — | — | ✓ | S |
| AuditEvent | Audit | Audit | Append-only audit fact (§32/§33). | TENANT_SCOPED | `—` | — | ✓ (is the record) | ✗ (append-only) | L |
| ReportDefinition | Reporting | Reporting/Analytics | Report spec. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| ReportParameter | Reporting | Reporting/Analytics | Parameter definition. | TENANT_SCOPED | `—` | — | — | ✓ | L |
| ReportExecution | Reporting | Reporting/Analytics | Report run. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| ReportSchedule | Reporting | Reporting/Analytics | Report schedule. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| ReportOutput | Reporting | Reporting/Analytics | Report output. | TENANT_SCOPED | `—` | — | — | ✓ | M |
| ReportAccess | Reporting | Reporting/Analytics | Access grant. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| MetricDefinition | Analytics | Reporting/Analytics | Metric spec. | TENANT_SCOPED | `code` | — | — | ✓ | L |
| MetricValue | Analytics | Reporting/Analytics | Metric point (projection). | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| KpiDefinition | Analytics | Reporting/Analytics | KPI spec. | TENANT_SCOPED | `code` | — | — | ✓ | L |
| KpiValue | Analytics | Reporting/Analytics | KPI point (projection). | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| Dashboard | Analytics | Reporting/Analytics | Dashboard. | TENANT_SCOPED | `code` | — | — | ✓ | M |
| DashboardWidget | Analytics | Reporting/Analytics | Widget (justified CASCADE child). | TENANT_SCOPED | `—` | — | — | ✓ | M |
| AnalyticsSnapshot | Analytics | Reporting/Analytics | Projection snapshot. | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| AiProvider | AI | AI | Provider registry. | GLOBAL | `code` | — | ✓ | ✓ | L |
| AiModel | AI | AI | Model registry. | GLOBAL | `code` | — | ✓ | ✓ | L |
| AiModelVersion | AI | AI | Model version. | GLOBAL | `—` | — | ✓ | ✓ | L |
| AiAgent | AI | AI | Software AI agent. | TENANT_SCOPED | `code` | AiAgent | ✓ | ✓ | M |
| AiAgentExecution | AI | AI | Agent run (traceable §38). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| AiRequest | AI | AI | Inference request (§37 fields). | TENANT_SCOPED | `—` | AiRequest | ✓ | ✓ | M |
| AiResponse | AI | AI | Classified result (§37/§38). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| AiConversation | AI | AI | AI chat session. | TENANT_SCOPED | `—` | — | △ | ✓ | S |
| AiMessage | AI | AI | Chat turn (append-only). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | S |
| AiKnowledgeSource | AI | AI | RAG source. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| AiKnowledgeDocument | AI | AI | Ingested document. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| AiEmbedding | AI | AI | Embedding registry row. | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| AiRecommendation | AI | AI | Recommendation (advisory by default). | TENANT_SCOPED | `—` | AiRecommendation | ✓ | ✓ | M |
| AiPrediction | AI | AI | Prediction — NOT a fact (§37). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| AiInsight | AI | AI | Generated insight. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| Integration | Integration | Integration | Registered integration. | TENANT_SCOPED | `code` | Integration | ✓ | ✓ | L |
| IntegrationType | Integration | Integration | Type vocabulary. | GLOBAL | `—` | — | — | ✓ | L |
| IntegrationCredential | Integration | Integration | Credential reference (§39). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| IntegrationEndpoint | Integration | Integration | Endpoint. | TENANT_SCOPED | `—` | — | △ | ✓ | L |
| IntegrationConnection | Integration | Integration | Connection state. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| IntegrationMapping | Integration | Integration | Payload mapping. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| IntegrationJob | Integration | Integration | Sync job. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| IntegrationExecution | Integration | Integration | Job run (§39 statuses). | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| IntegrationEvent | Integration | Integration | Inbound/outbound record (idempotent). | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |
| IntegrationError | Integration | Integration | Error stream. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | M |
| WinCcServer | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Server registry. | TENANT_SCOPED | `code` | — | ✓ | ✓ | L |
| WinCcConnection | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Connection state. | TENANT_SCOPED | `—` | — | △ | ✓ | M |
| WinCcTag | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Tag registry. | TENANT_SCOPED | `—` | — | ✓ | ✓ | L |
| WinCcTagValue | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Time-series value. | TENANT_SCOPED | `—` | — | — | ✗ (append-only) | C |
| WinCcAlarm | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Alarm stream. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | C |
| WinCcEvent | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Event stream. | TENANT_SCOPED | `—` | — | △ | ✗ (append-only) | C |
| WinCcSyncJob | Industry Extension (pack — NOT Core) | Integration (Industry Pack) | Sync job. | TENANT_SCOPED | `—` | — | ✓ | ✓ | M |

**Total entities:** 195
