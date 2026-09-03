# DatabaseDictionary.md — Phase 05 field-level dictionary

**Status:** DESIGN (Phase 05) · **Spec:** `docs/Phases/Phase5.md` §2/§63
**Generated from:** `tools/generatePhase5Catalogs.py` (single dataset →
Dictionary + EntityCatalog + FieldCatalog; regenerate after any change).
**Conventions:**
- Field naming camelCase (§3) — snake_case/PascalCase forbidden.
- Types by concept (§4): uuid · varchar(n) · nvarchar(n|max) · boolean ·
  datetime(UTC) · date · time · integer · bigint · decimal(p,s) · json · enum(Name).
- NULL semantics documented per field (§6); defaults only when domain-logical (§7).
- Every enum references the controlled vocabulary in `07ConstraintCatalog.md` §2
  or `StateMachineCatalog.md` where it is a state machine.
- Money: decimal + ISO-4217 currency, never float (§52). Timestamps stored UTC (§51).
- Standard blocks (below) apply to entities by kind; business fields listed per entity.

### Standard field blocks

| Block | Applies to | Fields |
|---|---|---|
| BASE | kind=base/link/vocab | id, tenantId (tenant-owned), createdAt, updatedAt, createdBy, updatedBy, deletedAt, deletedBy, isActive (+version when optimistic-locked) |
| APPEND | kind=append | id, tenantId, createdAt — rows immutable, retention-purge only |
| VOCAB | kind=vocab | BASE + code, name, description (stable reference data §73/§74) |

---

## Platform Core · Tenancy · Configuration

### Tenant

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Tenancy
- **Purpose:** Top isolation boundary of the platform.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Tenant · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “Tenant” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(160) | YES | no | — | — | — | — | Display name (unique per scope, BR-TEN-004) |
| code | varchar(64) | YES | no | — | YES | YES | — | Global-unique platform code |
| description | nvarchar(1000) | no | YES | — | — | — | — |  |
| status | enum(tenantStatus) | YES | no | — | — | — | — | active · suspended · closed |

### SystemSetting

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** System-scoped runtime setting.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “SystemSetting” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scope | enum(settingScope) | YES | no | — | — | — | — | system |
| key | varchar(190) | YES | no | — | YES | YES | — | UNIQUE(scope, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |
| valueType | varchar(32) | YES | no | — | — | — | — | string · int · bool · json · decimal |
| isSecret | boolean | YES | no | false | — | — | — | value never returned raw |

### Feature

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** Registered product feature.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** vocab · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “Feature” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| category | varchar(64) | YES | no | — | — | YES | — |  |

_+ VOCAB block: code · name · description_

### FeatureFlag

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** Feature-flag state per scope.
- **Tenant scoped:** HYBRID (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “FeatureFlag” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| featureId | uuid | YES | no | — | — | — | Feature | UNIQUE(featureId, scopeType, tenantId) |
| scopeType | enum(flagScope) | YES | no | — | — | — | — | system · tenant |
| enabled | boolean | YES | no | false | — | — | — | flag default off (BR-DAT-006) |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### Configuration

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** Scoped configuration entry.
- **Tenant scoped:** HYBRID (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “Configuration” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scope | enum(configScope) | YES | no | — | — | — | — | system · tenant |
| key | varchar(190) | YES | no | — | — | — | — | UNIQUE(tenantId, scope, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |
| schemaRef | varchar(190) | no | YES | — | — | — | — | validation schema reference |

### Lookup

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** Controlled list group.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “Lookup” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### LookupValue

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Configuration
- **Purpose:** Controlled list entry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “LookupValue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| lookupId | uuid | YES | no | — | — | — | Lookup | UNIQUE(tenantId, lookupId, code) |
| code | varchar(64) | YES | no | — | — | YES | — |  |
| label | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — |  |

### Tag

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Free taxonomy tag.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (11):** see `FieldCatalog.md` § “Tag” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(120) | YES | no | — | — | — | — | UNIQUE(tenantId, name) |
| color | varchar(16) | no | YES | — | — | — | — |  |

### TagAssignment

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Polymorphic tag link (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (6):** see `FieldCatalog.md` § “TagAssignment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| tagId | uuid | YES | no | — | — | YES | Tag | UNIQUE(tagId, ownerType, ownerId) |
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |

### CustomFieldDefinition

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Extension field schema (spec §42).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “CustomFieldDefinition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| fieldType | enum(customFieldType) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: field config |
| validation | json | no | YES | — | — | — | — | documented JSON use: validation rules |

### CustomFieldValue

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Extension field data.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “CustomFieldValue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| definitionId | uuid | YES | no | — | — | — | CustomFieldDefinition |  |
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — | UNIQUE(definitionId, ownerType, ownerId) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |

### Attachment

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** File metadata record (binary in object storage, §40).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (17):** see `FieldCatalog.md` § “Attachment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |
| fileName | nvarchar(260) | YES | no | — | — | — | — |  |
| storageProvider | varchar(32) | YES | no | — | — | — | — |  |
| storageKey | varchar(512) | YES | no | — | — | — | — | never a local path assumption |
| mimeType | varchar(127) | YES | no | — | — | — | — |  |
| fileSize | bigint | YES | no | — | — | — | — | bytes |
| checksum | varchar(128) | YES | no | — | — | — | — | change/duplicate detection (§40) |

### Address

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Reusable postal address.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (18):** see `FieldCatalog.md` § “Address” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |
| line1 | nvarchar(200) | YES | no | — | — | — | — |  |
| line2 | nvarchar(200) | no | YES | — | — | — | — |  |
| city | nvarchar(120) | YES | no | — | — | — | — |  |
| country | varchar(2) | YES | no | — | — | — | — | ISO 3166-1 alpha-2 |
| postalCode | varchar(20) | YES | no | — | — | — | — |  |
| latitude | decimal(9,6) | no | YES | — | — | — | — |  |
| longitude | decimal(9,6) | no | YES | — | — | — | — |  |

### ContactInformation

- **Domain:** Platform Core · Tenancy · Configuration · **Owner:** Platform Core
- **Purpose:** Reusable contact record.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “ContactInformation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |
| contactType | enum(contactType) | YES | no | — | — | — | — |  |
| value | nvarchar(250) | YES | no | — | — | — | — |  |
| isPrimary | boolean | YES | no | false | — | — | — |  |


## Identity

### User

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Authentication principal (≠ Employee, §15).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `username` (§12) · **State machine:** User · **Retention:** L
- **Fields (18):** see `FieldCatalog.md` § “User” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| username | varchar(150) | YES | no | — | — | YES | — | UNIQUE(tenantId, username) |
| email | nvarchar(254) | YES | no | — | — | YES | — | UNIQUE(tenantId, email) |
| displayName | nvarchar(200) | YES | no | — | — | — | — |  |
| passwordHash | varchar(255) | YES | no | — | — | — | — | hashed only; never logged |
| userType | enum(userType) | YES | no | — | — | — | — | person · service · agent |
| status | enum(userStatus) | YES | no | — | — | — | — | see StateMachine: User |
| lastLoginAt | datetime (UTC) | no | YES | — | — | — | — |  |
| mustChangePassword | boolean | YES | no | false | — | — | — |  |

### Role

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Role definition.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “Role” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(160) | YES | no | — | — | — | — |  |
| isSystem | boolean | YES | no | false | — | — | — | system roles undeletable |

### Permission

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Action-based permission catalogue (§42).
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** vocab · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “Permission” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| resource | varchar(64) | YES | no | — | — | YES | — | e.g. project |
| action | varchar(64) | YES | no | — | — | — | — | e.g. view · create · approve |
| scope | enum(permissionScope) | no | YES | — | — | — | — |  |

_+ VOCAB block: code · name · description_

### RolePermission

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Role↔permission link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “RolePermission” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| roleId | uuid | YES | no | — | — | — | Role |  |
| permissionId | uuid | YES | no | — | — | — | Permission | UNIQUE(roleId, permissionId) |

### UserRole

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Scoped user↔role grant.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “UserRole” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| roleId | uuid | YES | no | — | — | YES | Role |  |
| scopeType | enum(roleScope) | YES | no | — | — | — | — | GLOBAL·TENANT·ORG·DEPT·PROJECT (§43) |
| scopeId | uuid | no | YES | — | — | — | — |  |
| grantedBy | uuid | YES | no | — | — | — | User |  |
| grantedAt | datetime (UTC) | YES | no | — | — | — | — | UNIQUE(userId, roleId, scopeType, scopeId) |

### UserPermission

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Direct user permission (allow/deny).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “UserPermission” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| permissionId | uuid | YES | no | — | — | — | Permission |  |
| effect | enum(permissionEffect) | YES | no | — | — | — | — | allow · deny |
| scopeType | enum(roleScope) | no | YES | — | — | — | — |  |
| scopeId | uuid | no | YES | — | — | — | — |  |

### Session

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Session/token record.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Session · **Retention:** S
- **Fields (16):** see `FieldCatalog.md` § “Session” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| tokenHash | varchar(255) | YES | no | — | — | — | — | hash only; UNIQUE(userId, tokenHash) |
| issuedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| expiresAt | datetime (UTC) | YES | no | — | — | YES | — | expiry sweep index |
| revokedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| ipAddress | varchar(45) | no | YES | — | — | — | — |  |
| userAgent | nvarchar(500) | no | YES | — | — | — | — |  |

### AuthenticationMethod

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Authentication factor (MFA-ready).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “AuthenticationMethod” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | — | User |  |
| methodType | enum(authMethodType) | YES | no | — | — | — | — |  |
| secretRef | varchar(255) | YES | no | — | — | — | — | secret-manager reference |
| verifiedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### AccessPolicy

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Access policy rule.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “AccessPolicy” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| subjectType | varchar(64) | YES | no | — | — | YES | — |  |
| subjectId | uuid | no | YES | — | — | YES | — |  |
| resource | varchar(64) | YES | no | — | — | YES | — |  |
| effect | enum(permissionEffect) | YES | no | — | — | — | — |  |
| condition | json | no | YES | — | — | — | — | documented JSON use: policy condition |
| priority | integer | YES | no | 0 | — | — | — |  |

### SecurityEvent

- **Domain:** Identity · **Owner:** Identity
- **Purpose:** Append-only security telemetry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (9):** see `FieldCatalog.md` § “SecurityEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | no | YES | — | — | YES | User |  |
| eventType | enum(securityEventType) | YES | no | — | — | YES | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| ipAddress | varchar(45) | no | YES | — | — | — | — |  |
| userAgent | nvarchar(500) | no | YES | — | — | — | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: event detail |


## Organization

### Organization

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Legal-entity root of tenant structure.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “Organization” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| legalId | varchar(64) | no | YES | — | — | — | — | registration number |
| orgType | enum(organizationType) | YES | no | — | — | — | — |  |
| parentId | uuid | no | YES | — | — | — | Organization |  |

### OrganizationUnit

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Generic hierarchy node (typed by children).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “OrganizationUnit” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | YES | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, organizationId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| unitType | enum(orgUnitType) | YES | no | — | — | — | — | root · division · department · team |
| parentId | uuid | no | YES | — | — | YES | OrganizationUnit | acyclic (BR-ORG-001) |

### Department

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Department typed unit.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “Department” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| headUserId | uuid | no | YES | — | — | — | User |  |
| costCenterId | uuid | no | YES | — | — | — | CostCenter |  |

### Division

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Division typed unit.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “Division” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| leadUserId | uuid | no | YES | — | — | — | User |  |

### Team

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Team typed unit.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “Team” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| leadUserId | uuid | no | YES | — | — | — | User |  |

### Position

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Organizational position definition.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “Position” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | YES | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| title | nvarchar(200) | YES | no | — | — | — | — |  |
| jobTitleId | uuid | no | YES | — | — | — | JobTitle |  |
| grade | varchar(32) | no | YES | — | — | — | — |  |

### JobTitle

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Job-title catalogue.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “JobTitle” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| level | integer | no | YES | — | — | — | — |  |

_+ VOCAB block: code · name · description_

### Location

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Physical site.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “Location” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| addressId | uuid | no | YES | — | — | — | Address |  |
| latitude | decimal(9,6) | no | YES | — | — | — | — |  |
| longitude | decimal(9,6) | no | YES | — | — | — | — |  |

### CostCenter

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Cost center.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “CostCenter” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| responsibleUserId | uuid | no | YES | — | — | — | User |  |

### OrganizationHierarchy

- **Domain:** Organization · **Owner:** Organization
- **Purpose:** Temporal hierarchy facts (§36).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (7):** see `FieldCatalog.md` § “OrganizationHierarchy” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| unitId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| parentId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |


## Workforce / HR

### Employee

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Person/employment record (≠ User, §15/§16).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `employeeNumber` (§12) · **State machine:** Employee · **Retention:** L
- **Fields (17):** see `FieldCatalog.md` § “Employee” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeNumber | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, employeeNumber) |
| firstName | nvarchar(120) | YES | no | — | — | — | — |  |
| lastName | nvarchar(120) | YES | no | — | — | — | — |  |
| nationalIdRef | varchar(255) | no | YES | — | — | — | — | secret reference (privacy) |
| birthDate | date | no | YES | — | — | — | — |  |
| userId | uuid | no | YES | — | YES | YES | User | optional 1:1 link |
| status | enum(employeeStatus) | YES | no | — | — | — | — | see StateMachine: Employee |

### Employment

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employment record.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (16):** see `FieldCatalog.md` § “Employment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| positionId | uuid | YES | no | — | — | — | Position |  |
| employmentType | enum(employmentType) | YES | no | — | — | — | — |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — | null = ongoing (one active per employee) |
| status | enum(employmentStatus) | YES | no | — | — | — | — |  |

### EmploymentHistory

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Append-only employment facts.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (7):** see `FieldCatalog.md` § “EmploymentHistory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employmentId | uuid | YES | no | — | — | YES | Employment |  |
| changeType | enum(employmentChangeType) | YES | no | — | — | — | — |  |
| snapshot | json | no | YES | — | — | — | — | documented JSON use: point-in-time snapshot |
| changedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### EmployeeAssignment

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Temporal unit assignment (§16: history preserved).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “EmployeeAssignment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| organizationUnitId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |
| allocationPercentage | decimal(5,2) | YES | no | 100.00 | — | — | — | 0–100 |

### EmployeeManager

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Reporting relationship (temporal).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “EmployeeManager” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| managerId | uuid | YES | no | — | — | YES | Employee | not self (BR-WF-002) |
| reportingType | enum(reportingType) | YES | no | — | — | — | — |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### EmployeeContact

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employee contacts.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “EmployeeContact” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| contactType | enum(contactType) | YES | no | — | — | — | — |  |
| value | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(employeeId, contactType, value) |
| isPrimary | boolean | YES | no | false | — | — | — |  |

### EmployeeAddress

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employee addresses.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “EmployeeAddress” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| addressId | uuid | YES | no | — | — | — | Address | UNIQUE(employeeId, addressId) |
| addressType | enum(addressType) | YES | no | — | — | — | — |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### EmployeeDocument

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employee↔document link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “EmployeeDocument” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(employeeId, documentId, documentRole) |
| documentRole | enum(employeeDocumentRole) | YES | no | — | — | — | — |  |

### EmployeeSkill

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employee skill level.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “EmployeeSkill” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| skillId | uuid | YES | no | — | — | YES | Skill | UNIQUE(employeeId, skillId) |
| skillLevel | enum(skillLevel) | YES | no | — | — | — | — |  |
| verifiedBy | uuid | no | YES | — | — | — | User |  |

### Skill

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Skill catalogue.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “Skill” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| category | varchar(64) | no | YES | — | — | — | — |  |

_+ VOCAB block: code · name · description_

### EmployeeCertification

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Employee certification.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “EmployeeCertification” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| certificationId | uuid | YES | no | — | — | YES | Certification | UNIQUE(employeeId, certificationId, issuedAt) |
| issuedAt | date | YES | no | — | — | — | — |  |
| expiresAt | date | no | YES | — | — | — | — |  |
| certificateRef | varchar(255) | no | YES | — | — | — | — | storage reference |

### Certification

- **Domain:** Workforce / HR · **Owner:** Workforce
- **Purpose:** Certification catalogue.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “Certification” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| issuer | nvarchar(200) | no | YES | — | — | — | — |  |

_+ VOCAB block: code · name · description_


## Performance

### EvaluationCycle

- **Domain:** Performance · **Owner:** Performance
- **Purpose:** Evaluation period.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** EvaluationCycle · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “EvaluationCycle” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| periodType | enum(periodType) | YES | no | — | — | — | — | daily·weekly·monthly·quarterly·annual |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | YES | no | — | — | — | — | ≥ startDate (BR-DAT-002) |
| status | enum(cycleStatus) | YES | no | — | — | — | — | see StateMachine: EvaluationCycle |

### EmployeeEvaluation

- **Domain:** Performance · **Owner:** Performance
- **Purpose:** Aggregate root of one evaluation (Phase 03 §6).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “EmployeeEvaluation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationCycleId | uuid | YES | no | — | — | YES | EvaluationCycle | UNIQUE(evaluationCycleId, employeeId) |
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| status | enum(evaluationStatus) | YES | no | — | — | — | — |  |
| submittedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| resultSummary | nvarchar(max) | no | YES | — | — | — | — |  |

### EvaluationCriteria

- **Domain:** Performance · **Owner:** Performance
- **Purpose:** Criterion per cycle.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “EvaluationCriteria” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationCycleId | uuid | YES | no | — | — | — | EvaluationCycle |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(evaluationCycleId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| weight | decimal(5,2) | YES | no | — | — | — | — | Σ weight = 100 per cycle (BR-DAT-004) |
| maxScore | decimal(6,2) | YES | no | — | — | — | — |  |

### EvaluationScore

- **Domain:** Performance · **Owner:** Performance
- **Purpose:** Score per criterion/reviewer (editable + audited).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (16):** see `FieldCatalog.md` § “EvaluationScore” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationId | uuid | YES | no | — | — | YES | EmployeeEvaluation | UNIQUE(evaluationId, criteriaId, reviewerId) |
| criteriaId | uuid | YES | no | — | — | — | EvaluationCriteria |  |
| reviewerId | uuid | YES | no | — | — | YES | User |  |
| weight | decimal(5,2) | YES | no | — | — | — | — | reviewer weight |
| score | decimal(6,2) | YES | no | — | — | — | — | within criteria bounds (BR-DAT-005) |
| changedAt | datetime (UTC) | YES | no | — | — | — | — | every change audited (BR-AUD-004) |


## Project

### Project

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project aggregate root.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Project · **Retention:** L
- **Fields (21):** see `FieldCatalog.md` § “Project” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code); e.g. PRJ-2026-001 |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| description | nvarchar(max) | no | YES | — | — | — | — |  |
| status | enum(projectStatus) | YES | no | — | — | — | — | see StateMachine: Project |
| ownerId | uuid | no | YES | — | — | — | User | required unless status=DRAFT (BR-PRJ-001) |
| startDate | date | no | YES | — | — | — | — |  |
| plannedEndDate | date | no | YES | — | — | — | — |  |
| actualEndDate | date | no | YES | — | — | — | — |  |
| organizationUnitId | uuid | no | YES | — | — | — | OrganizationUnit |  |
| budgetAmount | decimal(19,4) | no | YES | — | — | — | — | money: decimal, never float (§52) |
| budgetCurrency | varchar(3) | no | YES | — | — | — | — | ISO 4217 |

### ProjectMember

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project membership with data (§19).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (16):** see `FieldCatalog.md` § “ProjectMember” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| memberType | enum(memberType) | YES | no | — | — | — | — | user · employee |
| memberId | uuid | YES | no | — | — | YES | — | ONE ACTIVE membership per person per project (BR-PRJ-002) |
| projectRoleId | uuid | YES | no | — | — | — | ProjectRole |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — | null = active |
| allocationPercentage | decimal(5,2) | no | YES | — | — | — | — |  |

### ProjectRole

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project role catalogue.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “ProjectRole” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### ProjectPhase

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project phase.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “ProjectPhase” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — | UNIQUE(projectId, sortOrder) |
| startDate | date | no | YES | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |
| status | enum(phaseStatus) | YES | no | — | — | — | — |  |

### ProjectMilestone

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project milestone.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “ProjectMilestone” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| projectPhaseId | uuid | no | YES | — | — | — | ProjectPhase |  |
| name | nvarchar(200) | YES | no | — | — | — | — | UNIQUE(projectId, name) |
| dueDate | date | no | YES | — | — | YES | — |  |
| achievedDate | date | no | YES | — | — | — | — |  |
| status | enum(milestoneStatus) | YES | no | — | — | — | — |  |

### ProjectDependency

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project↔project dependency.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “ProjectDependency” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| dependsOnProjectId | uuid | YES | no | — | — | YES | Project | not self; acyclic (BR-DAT-008) |
| dependencyType | enum(projectDependencyType) | YES | no | — | — | — | — |  |

### ProjectBudget

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Budget line.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “ProjectBudget” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | ≥ 0 (CHECK, §55) |
| currency | varchar(3) | YES | no | — | — | — | — | ISO 4217 |
| fiscalPeriod | varchar(20) | YES | no | — | — | — | — | UNIQUE(projectId, fiscalPeriod) |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### ProjectRisk

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Risk register entry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “ProjectRisk” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(projectId, title) |
| probability | enum(riskLevel) | YES | no | — | — | — | — |  |
| impact | enum(riskLevel) | YES | no | — | — | — | — |  |
| mitigation | nvarchar(max) | no | YES | — | — | — | — |  |
| status | enum(riskStatus) | YES | no | — | — | YES | — |  |

### ProjectIssue

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Issue register entry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “ProjectIssue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(projectId, title) |
| severity | enum(issueSeverity) | YES | no | — | — | — | — |  |
| resolvedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(issueStatus) | YES | no | — | — | YES | — |  |

### ProjectDocument

- **Domain:** Project · **Owner:** Projects
- **Purpose:** Project↔document link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “ProjectDocument” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | — | Project |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(projectId, documentId, documentRole) |
| documentRole | enum(projectDocumentRole) | YES | no | — | — | — | — |  |


## Task

### Task

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task aggregate root (project-optional, §20).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Task · **Retention:** L
- **Fields (21):** see `FieldCatalog.md` § “Task” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| title | nvarchar(250) | YES | no | — | — | — | — |  |
| description | nvarchar(max) | no | YES | — | — | — | — |  |
| projectId | uuid | no | YES | — | — | YES | Project | nullable — task usable standalone (BR-TSK-001) |
| statusId | uuid | YES | no | — | — | YES | TaskStatus | (projectId,statusId) board index |
| priorityId | uuid | YES | no | — | — | — | TaskPriority |  |
| typeId | uuid | YES | no | — | — | — | TaskType |  |
| parentTaskId | uuid | no | YES | — | — | — | Task | subtask reference |
| startDate | datetime (UTC) | no | YES | — | — | — | — |  |
| deadlineAt | datetime (UTC) | no | YES | — | — | YES | — | ≥ startDate (BR-DAT-003) |
| estimateMinutes | integer | no | YES | — | — | — | — |  |

### TaskStatus

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task status vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “TaskStatus” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |
| isTerminal | boolean | YES | no | false | — | — | — |  |

_+ VOCAB block: code · name · description_

### TaskPriority

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task priority vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “TaskPriority” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| level | integer | YES | no | — | — | — | — |  |

_+ VOCAB block: code · name · description_

### TaskType

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task type vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “TaskType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### TaskAssignment

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task↔user assignment with data.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “TaskAssignment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(taskId, userId, assignedAt) |
| assignmentRole | enum(taskAssignmentRole) | YES | no | — | — | — | — |  |
| assignedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| removedAt | datetime (UTC) | no | YES | — | — | — | — | null = active |

### TaskDependency

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task→task dependency (§21).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “TaskDependency” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| dependsOnTaskId | uuid | YES | no | — | — | YES | Task | not self; acyclic (BR-TSK-002) |
| dependencyType | enum(taskDependencyType) | YES | no | — | — | — | — |  |
| lagMinutes | integer | no | YES | 0 | — | — | — |  |

### TaskComment

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Append-oriented comments.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (8):** see `FieldCatalog.md` § “TaskComment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | — | User |  |
| body | nvarchar(max) | YES | no | — | — | — | — |  |
| parentId | uuid | no | YES | — | — | — | TaskComment |  |
| editedAt | datetime (UTC) | no | YES | — | — | — | — | edit appends revision (BR-TSK-003) |

### TaskAttachment

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task attachment link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (11):** see `FieldCatalog.md` § “TaskAttachment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | — | Task |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(taskId, attachmentId) |

### TaskChecklist

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Task checklist.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “TaskChecklist” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| title | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — |  |

### TaskChecklistItem

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Checklist item (justified CASCADE child).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “TaskChecklistItem” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| checklistId | uuid | YES | no | — | — | — | TaskChecklist |  |
| label | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(checklistId, label) |
| isDone | boolean | YES | no | false | — | — | — |  |
| doneAt | datetime (UTC) | no | YES | — | — | — | — |  |
| doneBy | uuid | no | YES | — | — | — | User |  |

### TaskTimeEntry

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Time tracking (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (9):** see `FieldCatalog.md` § “TaskTimeEntry” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | YES | User |  |
| minutes | integer | YES | no | — | — | — | — | > 0 |
| startedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### TaskHistory

- **Domain:** Task · **Owner:** Tasks
- **Purpose:** Append-only activity stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (9):** see `FieldCatalog.md` § “TaskHistory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| changeType | enum(taskChangeType) | YES | no | — | — | — | — |  |
| beforeState | json | no | YES | — | — | — | — | documented JSON use: snapshot |
| afterState | json | no | YES | — | — | — | — | documented JSON use: snapshot |
| changedAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## Asset

### Asset

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Enterprise asset root (§24).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Asset · **Retention:** L
- **Fields (18):** see `FieldCatalog.md` § “Asset” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| assetCategoryId | uuid | YES | no | — | — | — | AssetCategory |  |
| assetTypeId | uuid | YES | no | — | — | YES | AssetType |  |
| statusId | uuid | YES | no | — | — | YES | AssetStatus |  |
| serialNumber | varchar(120) | no | YES | — | — | — | — |  |
| acquisitionDate | date | no | YES | — | — | — | — |  |
| ownershipType | enum(assetOwnershipType) | YES | no | — | — | — | — | physical·digital·financial·operational |

### AssetCategory

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Asset category tree.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AssetCategory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| parentId | uuid | no | YES | — | — | — | AssetCategory |  |

_+ VOCAB block: code · name · description_

### AssetType

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Asset type.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “AssetType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetCategoryId | uuid | YES | no | — | — | — | AssetCategory |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(tenantId, assetCategoryId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### AssetStatus

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Asset status vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AssetStatus” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |

_+ VOCAB block: code · name · description_

### AssetAssignment

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Custody (temporal; history preserved §24).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “AssetAssignment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| holderType | enum(holderType) | YES | no | — | — | — | — |  |
| holderId | uuid | YES | no | — | — | YES | — |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |

### AssetLocation

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Location (temporal).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AssetLocation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| locationId | uuid | YES | no | — | — | — | Location |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### AssetOwnership

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Ownership shares (temporal).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “AssetOwnership” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| ownerType | enum(holderType) | YES | no | — | — | — | — |  |
| ownerId | uuid | YES | no | — | — | — | — |  |
| sharePercentage | decimal(5,2) | YES | no | — | — | — | — | Σ ≤ 100 per asset (BR-DAT-006) |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### AssetLifecycle

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Lifecycle events (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (8):** see `FieldCatalog.md` § “AssetLifecycle” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| eventType | enum(assetEventType) | YES | no | — | — | — | — |  |
| eventDate | date | YES | no | — | — | YES | — |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |

### AssetDocument

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Asset↔document link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “AssetDocument” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | — | Asset |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(assetId, documentId, documentRole) |
| documentRole | enum(assetDocumentRole) | YES | no | — | — | — | — |  |

### AssetValueHistory

- **Domain:** Asset · **Owner:** Assets
- **Purpose:** Value over time (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (8):** see `FieldCatalog.md` § “AssetValueHistory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | money: decimal |
| currency | varchar(3) | YES | no | — | — | — | — |  |
| valuedAt | date | YES | no | — | — | YES | — |  |
| source | varchar(120) | no | YES | — | — | — | — |  |


## Device / OT

### Device

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Physical/logical device (§25).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Device · **Retention:** L
- **Fields (19):** see `FieldCatalog.md` § “Device” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| deviceTypeId | uuid | YES | no | — | — | — | DeviceType |  |
| deviceModelId | uuid | no | YES | — | — | — | DeviceModel |  |
| statusId | uuid | YES | no | — | — | YES | DeviceStatus |  |
| assetId | uuid | no | YES | — | — | YES | Asset | optional link; SET_NULL |
| registeredAt | datetime (UTC) | no | YES | — | — | — | — |  |
| lastSeenAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| offlineAfterSeconds | integer | YES | no | 300 | — | — | — | offline policy threshold (BR-DEV-001), not bare isOnline |

### DeviceType

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Device type vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DeviceType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### DeviceManufacturer

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Manufacturer catalogue.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DeviceManufacturer” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### DeviceModel

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Device model.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DeviceModel” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| manufacturerId | uuid | YES | no | — | — | — | DeviceManufacturer |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(tenantId, manufacturerId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### DeviceStatus

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Device status vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “DeviceStatus” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |

_+ VOCAB block: code · name · description_

### DeviceCredential

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Credential reference.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “DeviceCredential” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | — | Device |  |
| credentialType | enum(deviceCredentialType) | YES | no | — | — | — | — | UNIQUE(deviceId, credentialType) |
| secretRef | varchar(255) | YES | no | — | — | — | — | secret-manager reference; never plain |
| rotatedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceRegistration

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Registration facts (auditable §25).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “DeviceRegistration” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | — | Device | UNIQUE(deviceId) |
| registeredBy | uuid | YES | no | — | — | — | User |  |
| approvedBy | uuid | no | YES | — | — | — | User |  |
| approvedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceHeartbeat

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Heartbeat stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (7):** see `FieldCatalog.md` § “DeviceHeartbeat” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| status | enum(heartbeatStatus) | YES | no | — | — | — | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: diagnostics |

### DeviceTelemetry

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Telemetry stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (9):** see `FieldCatalog.md` § “DeviceTelemetry” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| metric | varchar(120) | YES | no | — | — | YES | — |  |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |
| quality | enum(telemetryQuality) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### DeviceConfiguration

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Versioned configuration.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “DeviceConfiguration” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| versionNumber | integer | YES | no | — | — | — | — | UNIQUE(deviceId, versionNumber); immutable rows |
| config | json | YES | no | — | — | — | — | documented JSON use: device configuration |
| appliedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceEvent

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Device event stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (8):** see `FieldCatalog.md` § “DeviceEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| eventType | enum(deviceEventType) | YES | no | — | — | YES | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| payload | json | no | YES | — | — | — | — | documented JSON use: event payload |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### Agent

- **Domain:** Device / OT · **Owner:** Devices
- **Purpose:** Software agent (≠ Device, §16).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** M
- **Fields (17):** see `FieldCatalog.md` § “Agent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| agentType | enum(agentType) | YES | no | — | — | — | — |  |
| ownerType | enum(holderType) | no | YES | — | — | — | — |  |
| ownerId | uuid | no | YES | — | — | — | — |  |
| credentialRef | varchar(255) | YES | no | — | — | — | — | secret reference |
| lastSeenAt | datetime (UTC) | no | YES | — | — | YES | — |  |


## Maintenance

### MaintenancePlan

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Maintenance plan for asset/device (§26).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** MaintenancePlan · **Retention:** L
- **Fields (17):** see `FieldCatalog.md` § “MaintenancePlan” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| targetType | enum(maintenanceTargetType) | YES | no | — | — | YES | — | asset · device |
| targetId | uuid | YES | no | — | — | YES | — |  |
| cadenceType | enum(cadenceType) | YES | no | — | — | — | — |  |
| startsOn | date | YES | no | — | — | — | — |  |
| endsOn | date | no | YES | — | — | — | — |  |
| status | enum(planStatus) | YES | no | — | — | — | — |  |

### MaintenanceSchedule

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Scheduled occurrence.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “MaintenanceSchedule” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| planId | uuid | YES | no | — | — | YES | MaintenancePlan | UNIQUE(planId, dueAt) |
| dueAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| status | enum(scheduleStatus) | YES | no | — | — | — | — |  |

### MaintenanceWorkOrder

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Work order (§26).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Maintenance · **Retention:** L
- **Fields (23):** see `FieldCatalog.md` § “MaintenanceWorkOrder” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| planId | uuid | no | YES | — | — | — | MaintenancePlan |  |
| targetType | enum(maintenanceTargetType) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | — | — |  |
| title | nvarchar(250) | YES | no | — | — | — | — |  |
| priority | enum(workOrderPriority) | YES | no | — | — | — | — |  |
| status | enum(workOrderStatus) | YES | no | — | — | YES | — | see StateMachine: Maintenance |
| requesterId | uuid | YES | no | — | — | — | User |  |
| assigneeId | uuid | no | YES | — | — | YES | User |  |
| dueAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| openedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| closedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| outcomeNote | nvarchar(max) | no | YES | — | — | — | — | required to complete (BR-MNT-001) |

### MaintenanceTask

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Work-order task.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “MaintenanceTask” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(workOrderId, title) |
| technicianId | uuid | no | YES | — | — | YES | User |  |
| status | enum(workOrderStatus) | YES | no | — | — | — | — |  |
| estimatedMinutes | integer | no | YES | — | — | — | — |  |

### MaintenanceEvent

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Work-order events.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (8):** see `FieldCatalog.md` § “MaintenanceEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| eventType | enum(maintenanceEventType) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### MaintenanceTechnician

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Technician registry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (11):** see `FieldCatalog.md` § “MaintenanceTechnician” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee | UNIQUE(employeeId) |
| specializations | json | no | YES | — | — | — | — | documented JSON use: skill list |

### MaintenancePart

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Part usage.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “MaintenancePart” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| partRef | varchar(120) | YES | no | — | — | — | — | UNIQUE(workOrderId, partRef) |
| quantity | integer | YES | no | 1 | — | — | — | > 0 |
| unitCost | decimal(19,4) | no | YES | — | — | — | — |  |
| currency | varchar(3) | no | YES | — | — | — | — |  |

### MaintenanceCost

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** Cost record.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “MaintenanceCost” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| costType | enum(maintenanceCostType) | YES | no | — | — | — | — |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | ≥ 0 |
| currency | varchar(3) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | — | — |  |

### MaintenanceHistory

- **Domain:** Maintenance · **Owner:** Maintenance
- **Purpose:** History stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (8):** see `FieldCatalog.md` § “MaintenanceHistory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | enum(maintenanceTargetType) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| summary | nvarchar(500) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |


## Document

### Document

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Document root (§22).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Document · **Retention:** L
- **Fields (19):** see `FieldCatalog.md` § “Document” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| title | nvarchar(250) | YES | no | — | — | — | — |  |
| documentTypeId | uuid | YES | no | — | — | — | DocumentType |  |
| documentCategoryId | uuid | no | YES | — | — | — | DocumentCategory |  |
| folderId | uuid | no | YES | — | — | YES | DocumentFolder |  |
| ownerId | uuid | YES | no | — | — | — | User |  |
| status | enum(documentStatus) | YES | no | — | — | YES | — | see StateMachine: Document |
| currentVersionNumber | integer | YES | no | 1 | — | — | — |  |
| classificationLevel | enum(classificationLevel) | YES | no | — | — | — | — |  |

### DocumentVersion

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Immutable version (§23).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (17):** see `FieldCatalog.md` § “DocumentVersion” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| versionNumber | integer | YES | no | — | — | — | — | UNIQUE(documentId, versionNumber); never overwritten |
| storageProvider | varchar(32) | YES | no | — | — | — | — |  |
| storageKey | varchar(512) | YES | no | — | — | — | — | object storage; binary never in DB (§40) |
| checksum | varchar(128) | YES | no | — | — | — | — |  |
| fileSize | bigint | YES | no | — | — | — | — |  |
| uploadedBy | uuid | YES | no | — | — | — | User |  |
| changeNote | nvarchar(500) | no | YES | — | — | — | — |  |

### DocumentType

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Document type vocabulary.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DocumentType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### DocumentCategory

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Category tree.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “DocumentCategory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| parentId | uuid | no | YES | — | — | — | DocumentCategory |  |

_+ VOCAB block: code · name · description_

### DocumentFolder

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Folder tree (acyclic).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “DocumentFolder” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(200) | YES | no | — | — | — | — | UNIQUE(tenantId, parentId, name) |
| parentId | uuid | no | YES | — | — | — | DocumentFolder |  |

### DocumentPermission

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Document ACL.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (16):** see `FieldCatalog.md` § “DocumentPermission” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| subjectType | enum(subjectType) | YES | no | — | — | — | — |  |
| subjectId | uuid | YES | no | — | — | YES | — | UNIQUE(documentId, subjectType, subjectId, permissionLevel) |
| permissionLevel | enum(documentPermissionLevel) | YES | no | — | — | — | — |  |
| grantedBy | uuid | YES | no | — | — | — | User |  |
| grantedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| expiresAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DocumentShare

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Share grant.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “DocumentShare” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| sharedWithType | enum(subjectType) | YES | no | — | — | — | — |  |
| sharedWithId | uuid | YES | no | — | — | — | — |  |
| sharedBy | uuid | YES | no | — | — | — | User |  |
| expiresAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### DocumentMetadata

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Metadata entry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DocumentMetadata” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| key | varchar(120) | YES | no | — | — | — | — | UNIQUE(documentId, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |

### DocumentAttachment

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Document attachment link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “DocumentAttachment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | — | Document |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(documentId, attachmentId) |

### DocumentWorkflow

- **Domain:** Document · **Owner:** Documents
- **Purpose:** Workflow trigger link.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “DocumentWorkflow” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(documentId, workflowInstanceId) |
| workflowInstanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| triggeredAt | datetime (UTC) | YES | no | — | — | — | — |  |


## Workflow

### Workflow

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Named workflow (generic §34).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “Workflow” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### WorkflowVersion

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Version (never overwritten §34).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “WorkflowVersion” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowId | uuid | YES | no | — | — | YES | Workflow |  |
| versionNumber | integer | YES | no | — | — | — | — | UNIQUE(workflowId, versionNumber) |
| status | enum(workflowVersionStatus) | YES | no | — | — | — | — |  |

### WorkflowDefinition

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Definition per version.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (11):** see `FieldCatalog.md` § “WorkflowDefinition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowVersionId | uuid | YES | no | — | — | — | WorkflowVersion | UNIQUE(workflowVersionId) |
| definition | json | YES | no | — | — | — | — | documented JSON use: graph definition |

### WorkflowNode

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Graph node.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “WorkflowNode” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| nodeKey | varchar(64) | YES | no | — | — | — | — | UNIQUE(workflowDefinitionId, nodeKey) |
| nodeType | enum(workflowNodeType) | YES | no | — | — | — | — |  |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: node config |

### WorkflowTransition

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Graph edge.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “WorkflowTransition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| fromNodeKey | varchar(64) | YES | no | — | — | — | — | UNIQUE(definitionId, fromNodeKey, toNodeKey) |
| toNodeKey | varchar(64) | YES | no | — | — | — | — |  |
| condition | json | no | YES | — | — | — | — | documented JSON use: transition condition |

### WorkflowInstance

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Running instance (independent state §34).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Workflow · **Retention:** L
- **Fields (17):** see `FieldCatalog.md` § “WorkflowInstance” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| status | enum(workflowInstanceStatus) | YES | no | — | — | YES | — | see StateMachine: Workflow |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| completedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| context | json | no | YES | — | — | — | — | documented JSON use: instance context |

### WorkflowInstanceState

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Current state snapshot.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “WorkflowInstanceState” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | — | WorkflowInstance | UNIQUE(instanceId) |
| currentNodeKey | varchar(64) | YES | no | — | — | — | — |  |
| enteredAt | datetime (UTC) | YES | no | — | — | — | — |  |
| waitingFor | json | no | YES | — | — | — | — | documented JSON use: pending approvals |

### WorkflowTask

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Human task.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “WorkflowTask” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance | UNIQUE(instanceId, nodeKey) |
| nodeKey | varchar(64) | YES | no | — | — | — | — |  |
| assigneeId | uuid | no | YES | — | — | YES | User |  |
| status | enum(workflowTaskStatus) | YES | no | — | — | YES | — |  |
| dueAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### WorkflowAction

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Actions taken (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (8):** see `FieldCatalog.md` § “WorkflowAction” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| actorId | uuid | YES | no | — | — | — | User |  |
| actionType | enum(workflowActionType) | YES | no | — | — | — | — |  |
| comment | nvarchar(500) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WorkflowApproval

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Approval decision (§35).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Approval · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “WorkflowApproval” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowTaskId | uuid | YES | no | — | — | YES | WorkflowTask | UNIQUE(workflowTaskId, approverId) |
| approverId | uuid | YES | no | — | — | YES | User |  |
| decision | enum(approvalDecision) | YES | no | — | — | — | — | approved · rejected · pending · cancelled |
| decidedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| comment | nvarchar(500) | no | YES | — | — | — | — | required when REJECTED (BR-WF-003) |
| delegatedFromId | uuid | no | YES | — | — | — | WorkflowApproval |  |

### WorkflowHistory

- **Domain:** Workflow · **Owner:** Workflow
- **Purpose:** Transition history.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (9):** see `FieldCatalog.md` § “WorkflowHistory” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| fromNode | varchar(64) | no | YES | — | — | — | — |  |
| toNode | varchar(64) | no | YES | — | — | — | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: transition detail |


## Communication

### Conversation

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Chat aggregate (§27).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Conversation · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “Conversation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationType | enum(conversationType) | YES | no | — | — | YES | — | direct · group · channel · meeting · system |
| title | nvarchar(200) | no | YES | — | — | — | — | null = direct chat (no title) |
| createdBy | uuid | YES | no | — | — | — | User | creator mandatory (BR-COM-001) |
| lastMessageAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| retentionDays | integer | no | YES | — | — | — | — | per-tenant policy; null = platform default |

### ConversationMember

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Membership with data.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “ConversationMember” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | YES | Conversation | UNIQUE(conversationId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| memberRole | enum(conversationRole) | YES | no | — | — | — | — | owner·admin·moderator·member·guest·readOnly |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |
| mutedUntil | datetime (UTC) | no | YES | — | — | — | — |  |

### ConversationType

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Type vocabulary.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “ConversationType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### Message

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Message (immutable/edit-policy §27).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (19):** see `FieldCatalog.md` § “Message” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | YES | Conversation | (conversationId, createdAt) cursor index |
| senderId | uuid | YES | no | — | — | — | User |  |
| contentType | enum(messageContentType) | YES | no | — | — | — | — |  |
| body | nvarchar(max) | no | YES | — | — | — | — |  |
| replyToId | uuid | no | YES | — | — | — | Message |  |
| threadId | uuid | no | YES | — | — | — | Message |  |
| editedAt | datetime (UTC) | no | YES | — | — | — | — | edit audited (BR-COM-002) |
| deletedAt | datetime (UTC) | no | YES | — | — | — | — | soft delete / tombstone per policy |
| generatedByAi | boolean | YES | no | false | — | — | — | AI governance flag |
| aiModelRef | varchar(120) | no | YES | — | — | — | — |  |

### MessageAttachment

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Message attachment.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (11):** see `FieldCatalog.md` § “MessageAttachment” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(messageId, attachmentId) |

### MessageReaction

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Reaction.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** link · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (12):** see `FieldCatalog.md` § “MessageReaction” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| userId | uuid | YES | no | — | — | — | User | UNIQUE(messageId, userId, emoji) |
| emoji | varchar(32) | YES | no | — | — | — | — |  |

### MessageReadReceipt

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Read state.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (12):** see `FieldCatalog.md` § “MessageReadReceipt” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(messageId, userId) |
| readAt | datetime (UTC) | YES | no | — | — | — | — |  |

### Channel

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Channel profile.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “Channel” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | — | Conversation | UNIQUE(conversationId) |
| visibility | enum(channelVisibility) | YES | no | — | — | YES | — | public · private · announcement |
| description | nvarchar(500) | no | YES | — | — | — | — |  |

### ChannelMember

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Channel membership.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “ChannelMember” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| channelId | uuid | YES | no | — | — | YES | Channel | UNIQUE(channelId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| memberRole | enum(conversationRole) | YES | no | — | — | — | — |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### VoiceCall

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Voice call metadata (§28).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Call · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “VoiceCall” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| initiatorId | uuid | YES | no | — | — | — | User |  |
| callType | enum(callType) | YES | no | — | — | — | — | direct · group |
| status | enum(callStatus) | YES | no | — | — | — | — | see StateMachine: Call |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### VoiceCallParticipant

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Call participant.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “VoiceCallParticipant” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| callId | uuid | YES | no | — | — | YES | VoiceCall | UNIQUE(callId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |
| state | enum(participantState) | YES | no | — | — | — | — |  |

### GroupCall

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Group call metadata.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Call · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “GroupCall” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| hostId | uuid | YES | no | — | — | — | User |  |
| status | enum(callStatus) | YES | no | — | — | — | — |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### VideoMeeting

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Meeting (§29).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Meeting · **Retention:** L
- **Fields (16):** see `FieldCatalog.md` § “VideoMeeting” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| hostId | uuid | YES | no | — | — | — | User |  |
| scheduledAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| startedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(meetingStatus) | YES | no | — | — | — | — | see StateMachine: Meeting |
| isRecurring | boolean | YES | no | false | — | — | — |  |

### MeetingParticipant

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Meeting participant.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “MeetingParticipant” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingId | uuid | YES | no | — | — | YES | VideoMeeting | UNIQUE(meetingId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| participantRole | enum(meetingRole) | YES | no | — | — | — | — |  |
| invitedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| joinedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |

### MeetingSession

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Session (reconnect/recurring).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “MeetingSession” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingId | uuid | YES | no | — | — | YES | VideoMeeting | UNIQUE(meetingId, sessionKey) |
| sessionKey | varchar(64) | YES | no | — | — | — | — |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### ScreenShareSession

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Screen-share session.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (13):** see `FieldCatalog.md` § “ScreenShareSession” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingSessionId | uuid | YES | no | — | — | YES | MeetingSession |  |
| sharerId | uuid | YES | no | — | — | — | User |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### MeetingRecording

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Recording metadata (§29).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “MeetingRecording” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingSessionId | uuid | YES | no | — | — | YES | MeetingSession |  |
| storageProvider | varchar(32) | YES | no | — | — | — | — | binary in object storage — never DB |
| storageKey | varchar(512) | YES | no | — | — | — | — |  |
| durationSeconds | integer | YES | no | — | — | — | — |  |
| status | enum(recordingStatus) | YES | no | — | — | — | — |  |
| consentCaptured | boolean | YES | no | false | — | — | — | BR-COM-006 |

### Presence

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Presence (realtime source = Redis §30).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (13):** see `FieldCatalog.md` § “Presence” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(userId, deviceId) |
| deviceId | uuid | no | YES | — | — | — | — |  |
| presenceStatus | enum(presenceStatus) | YES | no | — | — | YES | — | online·away·busy·doNotDisturb·offline (§30) |
| lastSeenAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### PresenceStatus

- **Domain:** Communication · **Owner:** Communication
- **Purpose:** Presence vocabulary.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “PresenceStatus” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_


## Notification

### Notification

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** Notification root (event-driven §36).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** Notification · **Retention:** S
- **Fields (18):** see `FieldCatalog.md` § “Notification” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| notificationType | varchar(120) | YES | no | — | — | YES | — |  |
| title | nvarchar(250) | YES | no | — | — | — | — |  |
| body | nvarchar(max) | no | YES | — | — | — | — |  |
| payload | json | no | YES | — | — | — | — | documented JSON use: event payload |
| priority | enum(notificationPriority) | YES | no | — | — | — | — |  |
| status | enum(notificationStatus) | YES | no | — | — | YES | — |  |
| sourceEventId | uuid | no | YES | — | — | — | — | originating domain event |
| templateId | uuid | no | YES | — | — | — | NotificationTemplate |  |
| expiresAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### NotificationTemplate

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** Versioned template.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (15):** see `FieldCatalog.md` § “NotificationTemplate” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(120) | YES | no | — | — | — | — | UNIQUE(tenantId, code, versionNumber) |
| versionNumber | integer | YES | no | — | — | — | — |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| subjectTemplate | nvarchar(500) | no | YES | — | — | — | — |  |
| bodyTemplate | nvarchar(max) | YES | no | — | — | — | — |  |
| variables | json | no | YES | — | — | — | — | documented JSON use: variable schema |

### NotificationPreference

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** User preference.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “NotificationPreference” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(userId, notificationType, channel) |
| notificationType | varchar(120) | YES | no | — | — | — | — |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| enabled | boolean | YES | no | true | — | — | — |  |
| quietStart | time | no | YES | — | — | — | — |  |
| quietEnd | time | no | YES | — | — | — | — |  |

### NotificationChannel

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** Channel vocabulary.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “NotificationChannel” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### NotificationDelivery

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** Delivery attempt (§31).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (10):** see `FieldCatalog.md` § “NotificationDelivery” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| notificationId | uuid | YES | no | — | — | YES | Notification |  |
| recipientId | uuid | YES | no | — | — | YES | NotificationRecipient |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| status | enum(deliveryStatus) | YES | no | — | — | YES | — | pending · sent · delivered · failed · read (§31) |
| attemptedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| providerRef | varchar(255) | no | YES | — | — | — | — |  |
| error | nvarchar(500) | no | YES | — | — | — | — | retryable (BR-NOT-002) |

### NotificationRecipient

- **Domain:** Notification · **Owner:** Notifications
- **Purpose:** Recipient + read state.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (12):** see `FieldCatalog.md` § “NotificationRecipient” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| notificationId | uuid | YES | no | — | — | YES | Notification | UNIQUE(notificationId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| readAt | datetime (UTC) | no | YES | — | — | YES | — | read state lives HERE |


## Audit

### AuditEvent

- **Domain:** Audit · **Owner:** Audit
- **Purpose:** Append-only audit fact (§32/§33).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** ✓ (is the record)
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “AuditEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| actorId | uuid | no | YES | — | — | YES | User | SET_NULL if actor purged |
| action | enum(auditAction) | YES | no | — | — | — | — | §32 controlled vocabulary |
| entityType | varchar(64) | YES | no | — | — | YES | — |  |
| entityId | uuid | YES | no | — | — | YES | — |  |
| timestamp | datetime (UTC) | YES | no | — | — | YES | — |  |
| ipAddress | varchar(45) | no | YES | — | — | — | — |  |
| userAgent | nvarchar(500) | no | YES | — | — | — | — |  |
| beforeState | json | no | YES | — | — | — | — | documented JSON use: audit snapshot |
| afterState | json | no | YES | — | — | — | — | documented JSON use: audit snapshot |
| metadata | json | no | YES | — | — | — | — | documented JSON use: change detail |
| correlationId | uuid | YES | no | — | — | YES | — | trace key |


## Reporting

### ReportDefinition

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Report spec.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “ReportDefinition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| dataSource | varchar(120) | YES | no | — | — | — | — |  |
| parameterSchema | json | no | YES | — | — | — | — | documented JSON use: parameter schema |

### ReportParameter

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Parameter definition.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “ReportParameter” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition | UNIQUE(reportDefinitionId, key) |
| key | varchar(64) | YES | no | — | — | — | — |  |
| parameterType | enum(parameterType) | YES | no | — | — | — | — |  |
| isRequired | boolean | YES | no | false | — | — | — |  |
| defaultValue | nvarchar(500) | no | YES | — | — | — | — |  |

### ReportExecution

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Report run.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “ReportExecution” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition |  |
| requestedBy | uuid | YES | no | — | — | — | User |  |
| startedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| finishedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(executionStatus) | YES | no | — | — | YES | — |  |

### ReportSchedule

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Report schedule.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “ReportSchedule” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition |  |
| cronExpression | varchar(64) | YES | no | — | — | — | — | UNIQUE(reportDefinitionId, cronExpression) |
| nextRunAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### ReportOutput

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Report output.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “ReportOutput” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| executionId | uuid | YES | no | — | — | YES | ReportExecution |  |
| storageProvider | varchar(32) | YES | no | — | — | — | — |  |
| storageKey | varchar(512) | YES | no | — | — | — | — |  |
| format | enum(reportFormat) | YES | no | — | — | — | — |  |
| generatedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### ReportAccess

- **Domain:** Reporting · **Owner:** Reporting/Analytics
- **Purpose:** Access grant.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “ReportAccess” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition | UNIQUE(reportDefinitionId, subjectType, subjectId) |
| subjectType | enum(subjectType) | YES | no | — | — | — | — |  |
| subjectId | uuid | YES | no | — | — | — | — |  |
| accessLevel | enum(reportAccessLevel) | YES | no | — | — | — | — |  |


## Analytics

### MetricDefinition

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** Metric spec.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “MetricDefinition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| formula | nvarchar(500) | no | YES | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### MetricValue

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** Metric point (projection).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (8):** see `FieldCatalog.md` § “MetricValue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| metricId | uuid | YES | no | — | — | YES | MetricDefinition |  |
| dimensions | json | no | YES | — | — | — | — | documented JSON use: dimension filter |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| periodStart | datetime (UTC) | YES | no | — | — | — | — |  |
| periodEnd | datetime (UTC) | YES | no | — | — | — | — |  |

### KpiDefinition

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** KPI spec.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “KpiDefinition” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| targetValue | decimal(18,6) | no | YES | — | — | — | — |  |
| direction | enum(kpiDirection) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### KpiValue

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** KPI point (projection).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (9):** see `FieldCatalog.md` § “KpiValue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| kpiId | uuid | YES | no | — | — | YES | KpiDefinition |  |
| dimensions | json | no | YES | — | — | — | — | documented JSON use: dimension filter |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| periodType | enum(periodType) | YES | no | — | — | — | — |  |
| periodStart | datetime (UTC) | YES | no | — | — | — | — |  |
| periodEnd | datetime (UTC) | YES | no | — | — | — | — |  |

### Dashboard

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** Dashboard.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “Dashboard” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| ownerId | uuid | YES | no | — | — | YES | User |  |
| layout | json | no | YES | — | — | — | — | documented JSON use: layout |

### DashboardWidget

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** Widget (justified CASCADE child).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “DashboardWidget” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| dashboardId | uuid | YES | no | — | — | YES | Dashboard |  |
| widgetType | varchar(64) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: widget config |
| position | integer | YES | no | 0 | — | — | — | UNIQUE(dashboardId, position) |

### AnalyticsSnapshot

- **Domain:** Analytics · **Owner:** Reporting/Analytics
- **Purpose:** Projection snapshot.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (8):** see `FieldCatalog.md` § “AnalyticsSnapshot” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scopeType | varchar(64) | YES | no | — | — | YES | — |  |
| scopeId | uuid | YES | no | — | — | YES | — |  |
| periodType | enum(periodType) | YES | no | — | — | — | — |  |
| data | json | YES | no | — | — | — | — | documented JSON use: projection payload |
| builtAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## AI

### AiProvider

- **Domain:** AI · **Owner:** AI
- **Purpose:** Provider registry.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AiProvider” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | YES | — | — | global unique |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| adapterType | enum(aiAdapterType) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: provider config (no secrets) |

### AiModel

- **Domain:** AI · **Owner:** AI
- **Purpose:** Model registry.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AiModel” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| providerId | uuid | YES | no | — | — | YES | AiProvider |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(providerId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| modality | enum(aiModality) | YES | no | — | — | — | — |  |

### AiModelVersion

- **Domain:** AI · **Owner:** AI
- **Purpose:** Model version.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “AiModelVersion” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| modelId | uuid | YES | no | — | — | YES | AiModel |  |
| versionNumber | varchar(64) | YES | no | — | — | — | — | UNIQUE(modelId, versionNumber) |
| status | enum(aiModelStatus) | YES | no | — | — | — | — |  |
| contextLimit | integer | no | YES | — | — | — | — |  |
| releasedAt | date | no | YES | — | — | — | — |  |

### AiAgent

- **Domain:** AI · **Owner:** AI
- **Purpose:** Software AI agent.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** AiAgent · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “AiAgent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| modelVersionId | uuid | YES | no | — | — | — | AiModelVersion |  |
| instructions | nvarchar(max) | no | YES | — | — | — | — |  |
| status | enum(aiAgentStatus) | YES | no | — | — | — | — |  |

### AiAgentExecution

- **Domain:** AI · **Owner:** AI
- **Purpose:** Agent run (traceable §38).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (11):** see `FieldCatalog.md` § “AiAgentExecution” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| agentId | uuid | YES | no | — | — | YES | AiAgent |  |
| input | json | no | YES | — | — | — | — | documented JSON use: run input |
| output | json | no | YES | — | — | — | — | documented JSON use: run output |
| promptTokens | integer | no | YES | — | — | — | — |  |
| completionTokens | integer | no | YES | — | — | — | — |  |
| startedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| finishedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(executionStatus) | YES | no | — | — | — | — |  |

### AiRequest

- **Domain:** AI · **Owner:** AI
- **Purpose:** Inference request (§37 fields).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** AiRequest · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “AiRequest” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| capability | varchar(120) | YES | no | — | — | YES | — |  |
| inputRef | uuid | no | YES | — | — | — | — | input reference (§37) |
| promptVersionRef | uuid | no | YES | — | — | — | — | prompt/context reference (§37) |
| requestedBy | uuid | YES | no | — | — | — | User |  |
| status | enum(executionStatus) | YES | no | — | — | — | — |  |

### AiResponse

- **Domain:** AI · **Owner:** AI
- **Purpose:** Classified result (§37/§38).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (19):** see `FieldCatalog.md` § “AiResponse” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| requestId | uuid | YES | no | — | — | — | AiRequest | UNIQUE(requestId) |
| content | nvarchar(max) | no | YES | — | — | — | — | output (§37) |
| resultClassification | enum(resultClassification) | YES | no | — | — | YES | — | advisory·draft·automated·authoritative (BR-AI-001) |
| modelId | uuid | YES | no | — | — | — | AiModel | which model (§38) |
| modelVersionId | uuid | YES | no | — | — | — | AiModelVersion | which version (§38) |
| providerId | uuid | YES | no | — | — | — | AiProvider | which provider (§38) |
| confidence | decimal(5,4) | no | YES | — | — | — | — | 0–1 (§37) |
| costAmount | decimal(12,4) | no | YES | — | — | — | — |  |
| costCurrency | varchar(3) | no | YES | — | — | — | — |  |
| producedAt | datetime (UTC) | YES | no | — | — | — | — | when (§38) |

### AiConversation

- **Domain:** AI · **Owner:** AI
- **Purpose:** AI chat session.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (11):** see `FieldCatalog.md` § “AiConversation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| title | nvarchar(250) | no | YES | — | — | — | — |  |

### AiMessage

- **Domain:** AI · **Owner:** AI
- **Purpose:** Chat turn (append-only).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** S
- **Fields (8):** see `FieldCatalog.md` § “AiMessage” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | YES | AiConversation |  |
| role | enum(aiMessageRole) | YES | no | — | — | — | — |  |
| content | nvarchar(max) | YES | no | — | — | — | — |  |
| promptTokens | integer | no | YES | — | — | — | — |  |
| completionTokens | integer | no | YES | — | — | — | — |  |

### AiKnowledgeSource

- **Domain:** AI · **Owner:** AI
- **Purpose:** RAG source.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “AiKnowledgeSource” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| sourceType | enum(knowledgeSourceType) | YES | no | — | — | — | — |  |
| ingestionConfig | json | no | YES | — | — | — | — | documented JSON use: ingestion config |

### AiKnowledgeDocument

- **Domain:** AI · **Owner:** AI
- **Purpose:** Ingested document.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “AiKnowledgeDocument” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sourceId | uuid | YES | no | — | — | YES | AiKnowledgeSource | UNIQUE(sourceId, documentRef) |
| documentRef | uuid | no | YES | — | — | — | Document |  |
| chunkCount | integer | YES | no | 0 | — | — | — |  |
| status | enum(executionStatus) | YES | no | — | — | — | — |  |

### AiEmbedding

- **Domain:** AI · **Owner:** AI
- **Purpose:** Embedding registry row.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (7):** see `FieldCatalog.md` § “AiEmbedding” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| knowledgeDocumentId | uuid | YES | no | — | — | YES | AiKnowledgeDocument |  |
| chunkRef | varchar(120) | YES | no | — | — | — | — |  |
| vectorRef | varchar(255) | YES | no | — | — | — | — | vector store reference |
| metadata | json | no | YES | — | — | — | — | documented JSON use: chunk metadata |

### AiRecommendation

- **Domain:** AI · **Owner:** AI
- **Purpose:** Recommendation (advisory by default).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** AiRecommendation · **Retention:** M
- **Fields (16):** see `FieldCatalog.md` § “AiRecommendation” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| content | nvarchar(max) | YES | no | — | — | — | — |  |
| classification | enum(resultClassification) | YES | no | — | — | — | — |  |
| status | enum(recommendationStatus) | YES | no | — | — | YES | — |  |
| reviewedBy | uuid | no | YES | — | — | — | User |  |
| reviewedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### AiPrediction

- **Domain:** AI · **Owner:** AI
- **Purpose:** Prediction — NOT a fact (§37).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “AiPrediction” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| horizon | varchar(64) | YES | no | — | — | — | — |  |
| predictedValue | decimal(18,6) | YES | no | — | — | — | — |  |
| confidence | decimal(5,4) | no | YES | — | — | — | — |  |
| evaluatedAt | datetime (UTC) | YES | no | — | — | — | — | compared to actual when available |

### AiInsight

- **Domain:** AI · **Owner:** AI
- **Purpose:** Generated insight.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (14):** see `FieldCatalog.md` § “AiInsight” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scopeType | varchar(64) | YES | no | — | — | YES | — |  |
| scopeId | uuid | YES | no | — | — | YES | — |  |
| summary | nvarchar(500) | YES | no | — | — | — | — |  |
| evidence | json | no | YES | — | — | — | — | documented JSON use: evidence refs |
| generatedAt | datetime (UTC) | YES | no | — | — | — | — |  |


## Integration

### Integration

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Registered integration.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** Integration · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “Integration” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| integrationTypeId | uuid | YES | no | — | — | YES | IntegrationType |  |
| status | enum(integrationStatus) | YES | no | — | — | — | — |  |

### IntegrationType

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Type vocabulary.
- **Tenant scoped:** GLOBAL (§9) · **Soft deletable:** ✓ · **Auditable:** —
- **Kind:** vocab · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “IntegrationType” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|

_+ VOCAB block: code · name · description_

### IntegrationCredential

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Credential reference (§39).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “IntegrationCredential” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, credentialType) |
| credentialType | enum(credentialType) | YES | no | — | — | — | — |  |
| secretRef | varchar(255) | YES | no | — | — | — | — | never plain text (BR-INT-001) |
| rotatedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### IntegrationEndpoint

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Endpoint.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “IntegrationEndpoint” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| url | nvarchar(500) | no | YES | — | — | — | — |  |
| authType | enum(endpointAuthType) | YES | no | — | — | — | — |  |

### IntegrationConnection

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Connection state.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “IntegrationConnection” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | — | Integration | UNIQUE(integrationId) |
| status | enum(connectionStatus) | YES | no | — | — | — | — |  |
| lastConnectedAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| latencyMs | integer | no | YES | — | — | — | — |  |

### IntegrationMapping

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Payload mapping.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “IntegrationMapping” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, direction) |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| mapping | json | YES | no | — | — | — | — | documented JSON use: field mapping |

### IntegrationJob

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Sync job.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (14):** see `FieldCatalog.md` § “IntegrationJob” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, name) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| cronExpression | varchar(64) | no | YES | — | — | — | — |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| status | enum(jobStatus) | YES | no | — | — | — | — |  |

### IntegrationExecution

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Job run (§39 statuses).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (9):** see `FieldCatalog.md` § “IntegrationExecution” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| jobId | uuid | YES | no | — | — | YES | IntegrationJob |  |
| status | enum(integrationExecutionStatus) | YES | no | — | — | YES | — | started · success · failed · retrying (§39) |
| startedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| finishedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| statistics | json | no | YES | — | — | — | — | documented JSON use: run stats |
| error | nvarchar(500) | no | YES | — | — | — | — | traceable (BR-INT-002) |

### IntegrationEvent

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Inbound/outbound record (idempotent).
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (15):** see `FieldCatalog.md` § “IntegrationEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| idempotencyKey | varchar(190) | YES | no | — | — | — | — | UNIQUE(integrationId, idempotencyKey) |
| payload | json | no | YES | — | — | — | — | documented JSON use: external payload |
| status | enum(integrationEventStatus) | YES | no | — | — | YES | — |  |
| processedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### IntegrationError

- **Domain:** Integration · **Owner:** Integration
- **Purpose:** Error stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (8):** see `FieldCatalog.md` § “IntegrationError” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| executionId | uuid | no | YES | — | — | YES | IntegrationExecution |  |
| errorCode | varchar(64) | YES | no | — | — | — | — |  |
| message | nvarchar(1000) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## Industry Extension (pack — NOT Core)

### WinCcServer

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Server registry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `code` (§12) · **State machine:** — · **Retention:** L
- **Fields (12):** see `FieldCatalog.md` § “WinCcServer” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| host | nvarchar(250) | YES | no | — | — | — | — |  |
| connectionProfile | json | no | YES | — | — | — | — | documented JSON use: connection config |

### WinCcConnection

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Connection state.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** △
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (12):** see `FieldCatalog.md` § “WinCcConnection” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | — | WinCcServer | UNIQUE(serverId) |
| status | enum(connectionStatus) | YES | no | — | — | — | — |  |
| lastSyncAt | datetime (UTC) | no | YES | — | — | — | — |  |

### WinCcTag

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Tag registry.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** L
- **Fields (13):** see `FieldCatalog.md` § “WinCcTag” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| tagPath | varchar(250) | YES | no | — | — | — | — | UNIQUE(tenantId, serverId, tagPath) |
| dataType | enum(tagDataType) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### WinCcTagValue

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Time-series value.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** —
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (7):** see `FieldCatalog.md` § “WinCcTagValue” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| tagId | uuid | YES | no | — | — | YES | WinCcTag |  |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| quality | enum(telemetryQuality) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WinCcAlarm

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Alarm stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (8):** see `FieldCatalog.md` § “WinCcAlarm” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| alarmCode | varchar(120) | YES | no | — | — | — | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| acknowledgedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### WinCcEvent

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Event stream.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✗ (append-only) · **Auditable:** △
- **Kind:** append · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** C
- **Fields (7):** see `FieldCatalog.md` § “WinCcEvent” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| eventType | varchar(120) | YES | no | — | — | — | — |  |
| payload | json | no | YES | — | — | — | — | documented JSON use: event payload |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WinCcSyncJob

- **Domain:** Industry Extension (pack — NOT Core) · **Owner:** Integration (Industry Pack)
- **Purpose:** Sync job.
- **Tenant scoped:** TENANT_SCOPED (§9) · **Soft deletable:** ✓ · **Auditable:** ✓
- **Kind:** base · **Business identity:** `—` (§12) · **State machine:** — · **Retention:** M
- **Fields (13):** see `FieldCatalog.md` § “WinCcSyncJob” (standard block + business fields below)

| Field | Type | Req | Null | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | — | WinCcServer | UNIQUE(serverId) |
| config | json | no | YES | — | — | — | — | documented JSON use: sync config |
| lastRunAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(jobStatus) | YES | no | — | — | — | — |  |

