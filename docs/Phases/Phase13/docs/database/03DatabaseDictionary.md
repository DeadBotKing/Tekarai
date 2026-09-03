# 03 — Database Dictionary (architecture level)

**Status:** DESIGN (Phase 04) · **Spec:** `docs/Phases/Phase4.md` §9–28
Field-level types, lengths, nullability and per-field business rules are
**Phase 05** scope (`docs/Phases/Phase5.md` §82: final Django models only
after Phase 05 approval). This dictionary fixes, per entity: purpose and key
field groups. Notation: `«base»` = full base-entity fields (id, createdAt,
updatedAt, createdBy, updatedBy, deletedAt, deletedBy, isActive);
`«append»` = append-only reduced base (id, createdAt, actor/correlation);
T = tenant-owned. Status enums are controlled vocabularies (§37).

---

## Platform Core · Tenancy · Configuration (spec §9)

| Entity | Purpose | Key field groups |
|---|---|---|
| Tenant «base» T | top isolation boundary | name, code(U), description, status, tenantSettings ref |
| SystemSetting «base» | system-scoped runtime settings | scope, key(U-scoped), value, valueType, isSecret |
| Feature «base» | registered product feature | code(U), name, description, category |
| FeatureFlag «base» T | flag state per scope | featureId, scope(system/tenant), enabled, note |
| Configuration «base» T | configuration entries | scope, key(U-scoped), value, schemaRef |
| Lookup «base» T | controlled list group | code(U-scoped), name |
| LookupValue «base» T | list entries | lookupId, code(U-scoped), label, sortOrder, isActive |
| Tag «base» T | free taxonomy tags | name(U-scoped), color |
| TagAssignment «append» T | polymorphic tag link | tagId, ownerType, ownerId |
| CustomFieldDefinition «base» T | extension field schema | code(U-scoped), targetType, fieldType, config, validation |
| CustomFieldValue «base» T | extension field data | definitionId, ownerType, ownerId, value |
| Attachment «base» T | generic file metadata + storageRef | ownerType, ownerId, fileName, storageRef, mimeType, fileSize |
| Address «base» T | reusable postal address | ownerType, ownerId, lines, city, country, postalCode, geo |
| ContactInformation «base» T | reusable contact record | ownerType, ownerId, type, value, isPrimary |

## Identity (spec §10)

| Entity | Purpose | Key field groups |
|---|---|---|
| User «base» T | authentication principal | username(U-scoped), email(U-scoped), displayName, status, passwordHash, lastLoginAt, userType(person/service/agent) |
| Role «base» T | role definition | code(U-scoped), name, description, isSystem |
| Permission «base» | permission catalogue | code(U), resource, action, scope |
| RolePermission «base» | role↔permission | roleId, permissionId |
| UserRole «base» T | user↔role with scope | userId, roleId, scopeType, scopeId, grantedBy, grantedAt |
| UserPermission «base» T | direct user permission (allow/deny) | userId, permissionId, effect, scope |
| Session «base» T | session/token record | userId, tokenHash, issuedAt, expiresAt, revokedAt, ip, userAgent |
| AuthenticationMethod «base» T | MFA/factors | userId, methodType, secret(ref), verifiedAt, isActive |
| AccessPolicy «base» T | policy rules | subjectType/Id, resource, effect, condition, priority |
| SecurityEvent «append» T | security log | userId, eventType, severity, ip, userAgent, metadata |

## Organization (spec §11)

| Entity | Purpose | Key field groups |
|---|---|---|
| Organization «base» T | legal entity root | tenantId, code(U-scoped), name, legalId, type, parentId(org) |
| OrganizationUnit «base» T | generic hierarchy node | organizationId, code(U-scoped), name, unitType, parentId |
| Department «base» T | typed unit | organizationUnitId, headUserId, costCenterId |
| Division «base» T | typed unit | organizationUnitId, leadUserId |
| Team «base» T | typed unit | organizationUnitId, leadUserId |
| Position «base» T | org position definition | organizationId, code(U-scoped), title, jobTitleId, grade |
| JobTitle «base» T | title catalogue | code(U-scoped), name, level |
| Location «base» T | site | organizationId, code(U-scoped), name, addressId, geo |
| CostCenter «base» T | cost accounting | organizationId, code(U-scoped), name, responsibleUserId |
| OrganizationHierarchy «append» T | temporal hierarchy facts | unitId, parentId, validFrom, validTo |

## Workforce / HR (spec §12 — person/employment)

| Entity | Purpose | Key field groups |
|---|---|---|
| Employee «base» T | person record (≠ User) | code/employeeNumber(U-scoped), firstName, lastName, nationalId(ref), birthDate, userId(unique optional), status |
| Employment «base» T | employment record | employeeId, organizationId, positionId, type, startDate, endDate, status |
| EmploymentHistory «append» T | employment facts | employmentId, changeType, changedAt, snapshot |
| EmployeeAssignment «base» T | temporal unit assignment | employeeId, organizationUnitId, startDate, endDate, allocationPct |
| EmployeeManager «base» T | reporting relationship | employeeId, managerId, type, validFrom, validTo |
| EmployeeContact «base» T | employee contacts | employeeId, type, value, isPrimary |
| EmployeeAddress «base» T | employee addresses | employeeId, addressId, type, validFrom/To |
| EmployeeDocument «base» T | link to documents | employeeId, documentId, documentRole |
| EmployeeSkill «base» T | employee↔skill + level | employeeId, skillId, level, verifiedBy |
| Skill «base» T | skill catalogue | code(U-scoped), name, category |
| EmployeeCertification «base» T | employee↔certification | employeeId, certificationId, issuedAt, expiresAt |
| Certification «base» T | certification catalogue | code(U-scoped), name, issuer |

## Performance (spec §12 — evaluation entities; Phase 03 ownership)

| Entity | Purpose | Key field groups |
|---|---|---|
| EvaluationCycle «base» T | evaluation period | code(U-scoped), periodType(d/w/m/q/y), startDate, endDate, status |
| EmployeeEvaluation «base» T | aggregate root of one evaluation | evaluationCycleId, employeeId, status, submittedAt, resultSummary |
| EvaluationCriteria «base» T | criteria per cycle | evaluationCycleId, code(U-scoped), name, weight, maxScore |
| EvaluationScore «base» T | score per criterion/reviewer | evaluationId, criteriaId, reviewerId, weight, score, version, changedAt |

(Weighted calculation = domain service; score changes audited — Phase 03 §6.)

## Project (spec §13)

| Entity | Purpose | Key field groups |
|---|---|---|
| Project «base» T | project root | code(U-scoped), name, description, status, startDate, plannedEnd, actualEnd, organizationUnitId, budgetSummary |
| ProjectMember «base» T | M↔N with data | projectId, userId/employeeId, projectRoleId, joinedAt, leftAt, allocationPct |
| ProjectRole «base» T | project role catalogue | code(U-scoped), name, permissions ref |
| ProjectPhase «base» T | phases | projectId, name, order, startDate, endDate, status |
| ProjectMilestone «base» T | milestones | projectId/phaseId, name, dueDate, achievedDate, status |
| ProjectDependency «base» T | project↔project deps | projectId, dependsOnProjectId, type |
| ProjectBudget «base» T | budget lines | projectId, amount(decimal), currency, fiscalPeriod, note |
| ProjectRisk «base» T | risk register | projectId, title, probability, impact, mitigation, status |
| ProjectIssue «base» T | issue register | projectId, title, severity, raisedAt, resolvedAt, status |
| ProjectDocument «base» T | project↔document link | projectId, documentId, documentRole |

## Task (spec §14)

| Entity | Purpose | Key field groups |
|---|---|---|
| Task «base» T | task root | projectId(nullable ref), code(U-scoped), title, description, statusId, priorityId, typeId, parentTaskId(subtask), deadline, startDate, estimate, version |
| TaskStatus «base» T | status vocabulary | code(U-scoped), name, order, isTerminal |
| TaskPriority «base» T | priority vocabulary | code(U-scoped), name, level |
| TaskType «base» T | type vocabulary | code(U-scoped), name, defaultWorkflowId ref |
| TaskAssignment «base» T | task↔user with data | taskId, userId, role, assignedAt, removedAt |
| TaskDependency «base» T | task deps | taskId, dependsOnTaskId, type, lag |
| TaskComment «append» T | comments | taskId, userId, body, createdAt, editedAt, parentId |
| TaskAttachment «base» T | attachments | taskId, attachmentId |
| TaskChecklist «base» T | checklists | taskId, title, order |
| TaskChecklistItem «base» T | items | checklistId, label, isDone, doneAt, doneBy |
| TaskTimeEntry «append» T | time tracking | taskId, userId, minutes, startedAt, endedAt, note |
| TaskHistory «append» T | activity stream | taskId, actorId, changeType, before, after, changedAt |

## Asset (spec §15)

| Entity | Purpose | Key field groups |
|---|---|---|
| Asset «base» T | asset root | code(U-scoped), name, categoryId, typeId, statusId, acquisitionDate, serial, ownershipType |
| AssetCategory «base» T | categories | code(U-scoped), name, parentId |
| AssetType «base» T | types | categoryId, code(U-scoped), name |
| AssetStatus «base» T | status vocabulary | code(U-scoped), name, order |
| AssetAssignment «base» T | custody (temporal) | assetId, holderType/Id, startDate, endDate |
| AssetLocation «base» T | location (temporal) | assetId, locationId, validFrom/To |
| AssetOwnership «base» T | ownership (temporal) | assetId, ownerType/Id, share, validFrom/To |
| AssetLifecycle «base» T | lifecycle events | assetId, eventType, eventDate, note, actorId |
| AssetDocument «base» T | asset↔document | assetId, documentId, role |
| AssetValueHistory «append» T | value over time | assetId, amount, currency, valuedAt, source |

## Device / OT + Agent (spec §16)

| Entity | Purpose | Key field groups |
|---|---|---|
| Device «base» T | physical/logical device | code(U-scoped), name, typeId, modelId, statusId, assetId(nullable), registeredAt, lastSeenAt |
| DeviceType «base» T | type vocabulary | code(U-scoped), name |
| DeviceModel «base» T | models | manufacturerId, code(U-scoped), name |
| DeviceManufacturer «base» T | makers | code(U-scoped), name |
| DeviceStatus «base» T | status vocabulary | code(U-scoped), name, order |
| DeviceCredential «base» T | device credentials (refs) | deviceId, credentialType, secretRef, rotatedAt |
| DeviceRegistration «base» T | registration facts | deviceId, registeredBy, registeredAt, approvedAt |
| DeviceHeartbeat «append» T | heartbeats | deviceId, occurredAt, status, metadata |
| DeviceTelemetry «append» T | telemetry stream | deviceId, metric, value, unit, occurredAt |
| DeviceConfiguration «base» T | versioned config | deviceId, version, config(json), appliedAt |
| DeviceEvent «append» T | device event stream | deviceId, eventType, severity, payload, occurredAt |
| Agent «base» T | software agent (≠ Device) | code(U-scoped), name, agentType, ownerId, credentialRef, lastSeenAt |

## Maintenance (spec §17)

| Entity | Purpose | Key field groups |
|---|---|---|
| MaintenancePlan «base» T | plan | code(U-scoped), name, targetType(asset/device), targetId, cadence, startsAt, endsAt, status |
| MaintenanceSchedule «base» T | scheduled occurrences | planId, dueAt, status |
| MaintenanceWorkOrder «base» T | work order | code(U-scoped), planId(nullable), targetType/Id, title, priority, status, assignedTechnicianId, openedAt, closedAt |
| MaintenanceTask «base» T | WO tasks | workOrderId, title, technicianId, status, estimatedMinutes |
| MaintenanceEvent «append» T | WO events | workOrderId, eventType, occurredAt, actorId, note |
| MaintenanceTechnician «base» T | technician registry | employeeId, specializations, isActive |
| MaintenancePart «base» T | parts used | workOrderId, partRef, quantity, unitCost(decimal), currency |
| MaintenanceCost «base» T | costs | workOrderId, amount, currency, costType, occurredAt |
| MaintenanceHistory «append» T | history | targetType/Id, summary, occurredAt, actorId |

## Document (spec §18)

| Entity | Purpose | Key field groups |
|---|---|---|
| Document «base» T | document root | code(U-scoped), title, typeId, categoryId, folderId, ownerId, status, currentVersionNumber |
| DocumentVersion «base» T | immutable versions | documentId, versionNumber(U-scoped with doc), storageRef, checksum, uploadedBy, uploadedAt, changeNote |
| DocumentType «base» T | type vocabulary | code(U-scoped), name |
| DocumentCategory «base» T | categories | code(U-scoped), parentId |
| DocumentFolder «base» T | folder tree | tenantId, name, parentId |
| DocumentPermission «base» T | ACL | documentId, subjectType/Id, permissionLevel, grantedBy/At |
| DocumentShare «base» T | shares | documentId, sharedWithType/Id, sharedBy/At, expiresAt |
| DocumentMetadata «base» T | metadata (structured+json) | documentId, key, value |
| DocumentAttachment «base» T | attachments | documentId, attachmentId |
| DocumentWorkflow «base» T | workflow trigger link | documentId, workflowInstanceId, triggeredAt |

## Workflow (spec §19)

| Entity | Purpose | Key field groups |
|---|---|---|
| Workflow «base» T | named engine entity | code(U-scoped), name, description |
| WorkflowVersion «base» T | versions | workflowId, versionNumber(U-scoped), status(draft/published/retired) |
| WorkflowDefinition «base» T | definition per version | workflowVersionId, definition(json graph) |
| WorkflowNode «base» T | nodes | workflowDefinitionId, nodeKey, nodeType(approval/task/condition), config |
| WorkflowTransition «base» T | edges | workflowDefinitionId, fromNodeKey, toNodeKey, condition |
| WorkflowInstance «base» T | running instance | workflowDefinitionId, targetType/Id, status, contextRef, startedAt, completedAt |
| WorkflowInstanceState «base» T | state snapshot | instanceId, currentNodeKey, enteredAt, waitingFor |
| WorkflowTask «base» T | human tasks | instanceId, nodeKey, assigneeId, status, dueAt |
| WorkflowAction «base» T | actions taken | instanceId, actorId, actionType, comment, occurredAt |
| WorkflowApproval «base» T | approval decisions | workflowTaskId, approverId, decision, decidedAt, comment, delegatedFromId |
| WorkflowHistory «append» T | transition history | instanceId, fromNode, toNode, actorId, occurredAt, metadata |

## Communication (spec §20)

| Entity | Purpose | Key field groups |
|---|---|---|
| Conversation «base» T | chat aggregate | type(direct/group/channel/meeting/system), title, createdBy, createdAt, lastMessageAt, policyRef |
| ConversationMember «base» T | membership with data | conversationId, userId, role(owner/admin/moderator/member/guest|readOnly), joinedAt, leftAt, mutedUntil |
| ConversationType «base» | type vocabulary | code(U), name |
| Message «base» T | message | conversationId, senderId, contentType, body, replyToId, threadId, editedAt, deletedAt, generatedByAi |
| MessageAttachment «base» T | attachments | messageId, attachmentId |
| MessageReaction «base» T | reactions | messageId, userId, emoji |
| MessageReadReceipt «base» T | read state | messageId, userId, readAt |
| Channel «base» T | channel profile | conversationId, visibility(public/private/announcement), description |
| ChannelMember «base» T | channel membership | channelId, userId, role, joinedAt |
| VoiceCall «base» T | 1:1 call | conversationId, initiatorId, startedAt, endedAt, status |
| VoiceCallParticipant «base» T | call participants | callId, userId, joinedAt, leftAt, state |
| GroupCall «base» T | group voice | conversationId, hostId, startedAt, endedAt, status |
| VideoMeeting «base» T | meeting | conversationId, hostId, scheduledAt, startedAt, endedAt, status |
| MeetingParticipant «base» T | meeting participants | meetingId, userId, role, invitedAt, joinedAt, leftAt |
| MeetingSession «base» T | session (reconnect/recurring) | meetingId, sessionKey, startedAt, endedAt |
| ScreenShareSession «base» T | sharing sessions | meetingSessionId, sharerId, startedAt, endedAt |
| MeetingRecording «base» T | recordings | meetingSessionId, storageRef, duration, status, consent |
| Presence «base» T | presence (cache-first) | userId, deviceId, status, lastSeenAt |
| PresenceStatus «base» | status vocabulary | code(U), name (online/away/busy/invisible/offline) |

## Notification (spec §21)

| Entity | Purpose | Key field groups |
|---|---|---|
| Notification «base» T | notification root | type, title, body, payload(json), priority, status, sourceEventId, expiresAt |
| NotificationTemplate «base» T | versioned templates | code(U-scoped), version, channel, subject/body, variables |
| NotificationPreference «base» T | user preferences | userId, notificationType, channel, enabled, quietHours |
| NotificationChannel «base» | channel vocabulary | code(U) (inApp/email/sms/push/realtime) |
| NotificationDelivery «base» T | delivery attempts | notificationId, recipientId, channel, status, attemptedAt, providerRef, error |
| NotificationRecipient «base» T | recipient + read state | notificationId, userId, readAt, delistedAt |

## Audit (spec §22)

| Entity | Purpose | Key field groups |
|---|---|---|
| AuditEvent «append» T | append-only audit fact | tenantId, actorId, action, entityType, entityId, timestamp, ipAddress, userAgent, beforeState, afterState, metadata, correlationId |

## Reporting (spec §23)

| Entity | Purpose | Key field groups |
|---|---|---|
| ReportDefinition «base» T | report spec | code(U-scoped), name, dataSource, parameters schema |
| ReportParameter «base» T | parameter defs | reportDefinitionId, key, type, required, default |
| ReportExecution «base» T | runs | reportDefinitionId, requestedBy, startedAt, finishedAt, status |
| ReportSchedule «base» T | schedules | reportDefinitionId, cron, recipients, nextRunAt |
| ReportOutput «base» T | outputs | executionId, storageRef, format, generatedAt |
| ReportAccess «base» T | access grants | reportDefinitionId, subjectType/Id, level |

## Analytics (spec §24)

| Entity | Purpose | Key field groups |
|---|---|---|
| MetricDefinition «base» T | metric spec | code(U-scoped), name, formula/ref, unit |
| MetricValue «append» T | metric points | metricId, dimension(json), value, period |
| KpiDefinition «base» T | KPI spec | code(U-scoped), name, target, direction, unit |
| KpiValue «append» T | KPI points | kpiId, dimension, value, period(d/w/m/q/y) |
| Dashboard «base» T | dashboards | code(U-scoped), name, ownerId, layout |
| DashboardWidget «base» T | widgets | dashboardId, widgetType, config, position |
| AnalyticsSnapshot «append» T | projections | scopeType/Id, period, data(json), builtAt |

## AI (spec §25)

| Entity | Purpose | Key field groups |
|---|---|---|
| AiProvider «base» | provider registry | code(U), name, adapterType, config(json) |
| AiModel «base» | model registry | providerId, code(U), name, modality |
| AiModelVersion «base» | versions | modelId, version, releasedAt, status, limits |
| AiAgent «base» T | software AI agent | code(U-scoped), name, modelVersionId, instructions, isActive |
| AiAgentExecution «append» T | agent runs | agentId, input, output, tokens, startedAt, finishedAt, status |
| AiRequest «base» T | inference request | capability, contextRef, promptVersionId, requestedBy, status |
| AiResponse «base» T | response + classification | requestId, content, resultClassification(advisory/draft/automated/authoritative), model, cost |
| AiConversation «base» T | chat sessions | userId, title, createdAt |
| AiMessage «append» T | chat turns | conversationId, role, content, tokens |
| AiKnowledgeSource «base» T | RAG source | type, ref, ingestionConfig |
| AiKnowledgeDocument «base» T | ingested doc | sourceId, documentRef, chunkCount, status |
| AiEmbedding «append» T | vectors | knowledgeDocumentId, chunkRef, vectorRef, metadata |
| AiRecommendation «base» T | recommendations | targetType/Id, content, classification, status, reviewedBy |
| AiPrediction «base» T | predictions | targetType/Id, horizon, value, confidence, evaluatedAt |
| AiInsight «base» T | insights | scope, summary, evidence(json), generatedAt |

## Integration (spec §26)

| Entity | Purpose | Key field groups |
|---|---|---|
| Integration «base» T | registered integration | code(U-scoped), name, typeId, status |
| IntegrationType «base» | type vocabulary | code(U) (rest/webhook/mqtt/opcua/wincc/sap/…) |
| IntegrationCredential «base» T | secret references | integrationId, credentialType, secretRef, rotatedAt |
| IntegrationEndpoint «base» T | endpoints | integrationId, url/queue, direction, authType |
| IntegrationConnection «base» T | connection state | integrationId, status, lastConnectedAt, latency |
| IntegrationMapping «base» T | payload mappings | integrationId, direction, mapping(json) |
| IntegrationJob «base» T | sync jobs | integrationId, schedule, direction, status |
| IntegrationExecution «append» T | job runs | jobId, startedAt, finishedAt, status, stats |
| IntegrationEvent «base» T | in/out records | integrationId, direction, idempotencyKey(U), payload, status |
| IntegrationError «append» T | errors | integrationId/executionId, code, message, occurredAt |

## WinCC — INDUSTRY EXTENSION (spec §28; pack schema, not Core)

| Entity | Purpose | Key field groups |
|---|---|---|
| WinCcServer «base» T | server registry | code(U-scoped), host, connectionProfile |
| WinCcConnection «base» T | connections | serverId, status, lastSyncAt |
| WinCcTag «base» T | tag registry | serverId, tagPath(U-scoped), dataType, unit |
| WinCcTagValue «append» T | time-series values | tagId, value, quality, occurredAt |
| WinCcAlarm «append» T | alarms | serverId, alarmCode, severity, occurredAt, acknowledgedAt |
| WinCcEvent «append» T | events | serverId, eventType, payload, occurredAt |
| WinCcSyncJob «base» T | sync jobs | serverId, config, lastRunAt, status |
