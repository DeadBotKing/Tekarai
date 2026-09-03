# ErrorCodeCatalog.md — Phase 05 error codes

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §61
**Laws (§61):** every error has a unique, stable, documented code; messages
are user-presentable and localizable; codes never renumbered or reused;
HTTP status is advisory mapping, the code is the contract.
**Format:** Code · HTTP · Message (en) · Cause · Client action.
Prefixes: `TENANT_` `AUTH_` `PERM_` `VAL_` `DUP_` `STATE_` `WF_` `DOC_`
`PRJ_` `MAINT_` `COM_` `INT_` `SYS_`.

---

## Core platform errors

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `TENANT_ACCESS_DENIED` | 403 | You do not have access to this tenant's data. | No active membership / missing tenant context (BR-TEN-001) | Switch tenant or contact admin |
| `AUTH_AUTHENTICATION_REQUIRED` | 401 | Authentication required. | Missing/expired credentials (BR-SEC-001) | Log in again |
| `AUTH_TOKEN_EXPIRED` | 401 | Session expired. | Token TTL passed | Refresh or re-login |
| `AUTH_TOKEN_INVALID` | 401 | Invalid session. | Bad signature/revoked session (BR-SEC-004) | Re-login |
| `AUTH_MFA_REQUIRED` | 401 | Multi-factor verification required. | MFA policy enforced | Complete MFA |
| `PERM_PERMISSION_DENIED` | 403 | You do not have permission to perform this action. | Authorization failed at any of the six layers (BR-SEC-002, BR-PER-004) | Request role/permission from admin |
| `PERM_SCOPE_DENIED` | 403 | This action is outside your assigned scope. | Role scope mismatch (BR-PER-002) | Request scope assignment |
| `TENANT_SUSPENDED` | 403 | This tenant is suspended. | Tenant.status = suspended | Contact platform admin |
| `SYS_RECORD_NOT_FOUND` | 404 | Record not found. | Id absent, soft-deleted, or other tenant's (silent, no existence leak) | Refresh list |
| `SYS_VALIDATION_FAILED` | 422 | Validation failed. | API/application/domain validation (BR-DAT-014); details carry field errors | Fix reported fields |
| `SYS_CONCURRENCY_CONFLICT` | 409 | The record was changed by someone else. | Stale version (BR-DAT-013) | Reload and reapply |
| `SYS_RATE_LIMITED` | 429 | Too many requests. | Throttle policy | Retry after window |
| `SYS_INTERNAL_ERROR` | 500 | Unexpected server error. | Unhandled fault (audited, correlationId returned) | Retry / report correlationId |

## Uniqueness & duplication (§11, §12)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `DUP_BUSINESS_CODE` | 409 | This code is already in use. | UNIQUE(tenantId, code) violated (BR-TEN-005) | Choose another code |
| `DUP_TENANT_CODE` | 409 | Tenant code already exists globally. | Tenant.code global unique (BR-TEN-004) | Choose another code |
| `DUP_ACTIVE_MEMBERSHIP` | 409 | User already has an active membership in this project. | One active membership rule (BR-PRJ-002) | Reuse existing membership |
| `DUP_INTEGRATION_EVENT` | 409 | Duplicate external event. | idempotencyKey seen (BR-INT-003) | Ignore (idempotent success) |
| `DUP_IDENTIFIER` | 409 | Identifier already registered. | serial/employeeNumber/email per-scope unique | Correct identifier |

## State machines (§13, §61)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `STATE_INVALID_TRANSITION` | 409 | This state change is not allowed. | Transition outside machine (BR-DAT-012) | Check StateMachineCatalog |
| `STATE_PROJECT_ALREADY_COMPLETED` | 409 | Project is completed and locked. | Project COMPLETED guard (BR-PRJ-001) | Request `project.reopen` permission |
| `STATE_PROJECT_NOT_ACTIVE` | 409 | Project is not active. | Start/hold guard | Resume project first |
| `STATE_WORK_ORDER_COMPLETED` | 409 | Work order is completed. | Maintenance terminal guard (BR-MNT-001) | Request `maintenance.reopen` |
| `STATE_DOCUMENT_VERSION_IMMUTABLE` | 409 | Document versions cannot be changed. | BR-DOC-001 | Create a new version |
| `STATE_DOCUMENT_LOCKED` | 423 | Document is locked by review. | IN_REVIEW guard | Wait for review outcome |
| `STATE_REJECTION_REASON_REQUIRED` | 422 | A reason is required for rejection. | BR-WF2-004 | Provide reason |
| `STATE_TASK_TERMINAL` | 409 | Task is closed. | DONE/CANCELLED guard | Reopen via permission or new task |
| `STATE_CALL_ENDED` | 409 | Call already ended. | Call terminal state | Start a new call |
| `STATE_MEETING_TERMINAL` | 409 | Meeting already ended/cancelled. | Meeting terminal guard | Schedule follow-up meeting |
| `STATE_DEVICE_RETIRED` | 409 | Device is retired/lost. | Device lifecycle guard | Register a new device |

## Workflow engine (§61)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `WF_INVALID_TRANSITION` | 409 | Invalid workflow transition. | Engine step outside definition (BR-WF2-002) | Check workflow version |
| `WF_DEFINITION_INACTIVE` | 409 | Workflow definition is not active. | Start against retired version | Select active version |
| `WF_TASK_NOT_ASSIGNABLE` | 422 | Workflow task cannot be assigned in this state. | Step guard failed | Check task state |
| `WF_INSTANCE_NOT_RUNNING` | 409 | Workflow instance is not running. | Terminal instance command | Start a new instance |

## Documents, files, storage (§40)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `DOC_CHECKSUM_MISMATCH` | 409 | File integrity check failed. | checksum differs on upload/fetch (BR-INT-004) | Re-upload file |
| `DOC_STORAGE_UNAVAILABLE` | 503 | File storage unavailable. | Object-storage provider down | Retry later |
| `DOC_FILE_TOO_LARGE` | 413 | File exceeds size limit. | Tenant quota/policy | Split or compress |
| `DOC_MIME_FORBIDDEN` | 415 | File type not allowed. | Tenant MIME policy | Use allowed type |
| `DOC_QUOTA_EXCEEDED` | 402 | Storage quota exceeded. | Tenant plan limit | Free space / upgrade plan |

## Communication (§27–§31)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `COM_CONVERSATION_ACCESS_DENIED` | 403 | You cannot join this conversation. | Private membership guard (BR-COM-002) | Request invitation |
| `COM_MESSAGE_IMMUTABLE` | 409 | Message can no longer be edited. | Edit policy window closed (BR-COM-003) | Post a correction message |
| `COM_NOT_PARTICIPANT` | 403 | You are not a participant of this call/meeting. | Object-level check | Ask to be invited |
| `COM_RECORDING_CONSENT_REQUIRED` | 422 | Recording consent must be captured first. | BR-COM-006 | Capture consent |
| `COM_PRESENCE_STALE` | 410 | Presence data unavailable. | Realtime source unreachable (BR-COM-007) | Reconnect |

## Integrations (§39)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `INT_CONNECTION_FAILED` | 502 | Integration connection failed. | Provider unreachable | Check endpoint/credentials |
| `INT_CREDENTIAL_INVALID` | 401 | Integration credential rejected. | Secret reference resolved but rejected (BR-SEC-003) | Re-authorize integration |
| `INT_EXECUTION_FAILED` | 502 | Integration execution failed. | Terminal FAILED (BR-INT-002) | See execution log |
| `INT_RATE_LIMITED_BY_PROVIDER` | 429 | Provider rate limit hit. | Upstream 429 | Retry with backoff |
| `INT_PAYLOAD_INVALID` | 422 | External payload rejected. | Schema contract violation | Inspect event payload |

## Data integrity (§55)

| Code | HTTP | Message | Cause | Client action |
|---|---|---|---|---|
| `VAL_DATE_RANGE_INVALID` | 422 | Start date must not be after end date. | BR-DAT-002/003 | Fix dates |
| `VAL_CYCLIC_REFERENCE` | 409 | This would create a circular reference. | Graph cycle (BR-DAT-008) | Choose different parent/dependency |
| `VAL_WEIGHT_SUM_INVALID` | 422 | Criteria weights must sum to 100%. | BR-DAT-004 | Adjust weights |
| `VAL_SCORE_OUT_OF_RANGE` | 422 | Score is outside the allowed range. | BR-DAT-005 | Score within [0, maxScore] |
| `VAL_AMOUNT_NEGATIVE` | 422 | Amount cannot be negative. | CHECK amount ≥ 0 (BR-DAT-009) | Correct amount |
| `VAL_ENUM_VALUE_FORBIDDEN` | 422 | Value is not in the allowed set. | Closed set (§8) | Choose a listed value |

---

## Registration & governance

- **Adding a code:** new codes require (1) unique across this catalog,
  (2) documented cause + client action, (3) a test asserting the mapping,
  (4) entry in the localization key files (Phase 12).
- **Stability:** codes are API contract — renaming = new code + old one kept
  as alias for one release minimum.
- **Error envelope (API layer, Phase 07):**
  `{ "code": "PERM_PERMISSION_DENIED", "message": "...", "correlationId": "…", "details": {…} }`
- Codes referenced by business rules: see `BusinessRuleCatalog.md` (each
  rule's Enforcement/Trace line names its error code where applicable).
