# FieldCatalog.md — Phase 05 field rows (§65)

**Status:** DESIGN (Phase 05) · generated (see DatabaseDictionary.md header).
Columns per §65: Entity · Name · Type · Required · Nullable · Default ·
Unique · Index · FK · Description. Standard blocks (BASE/APPEND/VOCAB)
are documented once in `DatabaseDictionary.md` and apply to every entity
of that kind — they are NOT repeated per entity here.

---

## Platform Core · Tenancy · Configuration

### Tenant

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(160) | YES | no | — | — | — | — | Display name (unique per scope, BR-TEN-004) |
| code | varchar(64) | YES | no | — | YES | YES | — | Global-unique platform code |
| description | nvarchar(1000) | no | YES | — | — | — | — |  |
| status | enum(tenantStatus) | YES | no | — | — | — | — | active · suspended · closed |

### SystemSetting

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scope | enum(settingScope) | YES | no | — | — | — | — | system |
| key | varchar(190) | YES | no | — | YES | YES | — | UNIQUE(scope, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |
| valueType | varchar(32) | YES | no | — | — | — | — | string · int · bool · json · decimal |
| isSecret | boolean | YES | no | false | — | — | — | value never returned raw |

### Feature

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| category | varchar(64) | YES | no | — | — | YES | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### FeatureFlag

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| featureId | uuid | YES | no | — | — | — | Feature | UNIQUE(featureId, scopeType, tenantId) |
| scopeType | enum(flagScope) | YES | no | — | — | — | — | system · tenant |
| enabled | boolean | YES | no | false | — | — | — | flag default off (BR-DAT-006) |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### Configuration

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scope | enum(configScope) | YES | no | — | — | — | — | system · tenant |
| key | varchar(190) | YES | no | — | — | — | — | UNIQUE(tenantId, scope, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |
| schemaRef | varchar(190) | no | YES | — | — | — | — | validation schema reference |

### Lookup

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### LookupValue

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| lookupId | uuid | YES | no | — | — | — | Lookup | UNIQUE(tenantId, lookupId, code) |
| code | varchar(64) | YES | no | — | — | YES | — |  |
| label | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — |  |

### Tag

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(120) | YES | no | — | — | — | — | UNIQUE(tenantId, name) |
| color | varchar(16) | no | YES | — | — | — | — |  |

### TagAssignment

_kind: append_ · _fields incl. standard block: 6_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| tagId | uuid | YES | no | — | — | YES | Tag | UNIQUE(tagId, ownerType, ownerId) |
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |

### CustomFieldDefinition

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| fieldType | enum(customFieldType) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: field config |
| validation | json | no | YES | — | — | — | — | documented JSON use: validation rules |

### CustomFieldValue

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| definitionId | uuid | YES | no | — | — | — | CustomFieldDefinition |  |
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — | UNIQUE(definitionId, ownerType, ownerId) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |

### Attachment

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 18_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| ownerType | varchar(64) | YES | no | — | — | YES | — |  |
| ownerId | uuid | YES | no | — | — | YES | — |  |
| contactType | enum(contactType) | YES | no | — | — | — | — |  |
| value | nvarchar(250) | YES | no | — | — | — | — |  |
| isPrimary | boolean | YES | no | false | — | — | — |  |


## Identity

### User

_kind: base_ · _fields incl. standard block: 18_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(160) | YES | no | — | — | — | — |  |
| isSystem | boolean | YES | no | false | — | — | — | system roles undeletable |

### Permission

_kind: vocab_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| resource | varchar(64) | YES | no | — | — | YES | — | e.g. project |
| action | varchar(64) | YES | no | — | — | — | — | e.g. view · create · approve |
| scope | enum(permissionScope) | no | YES | — | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### RolePermission

_kind: link_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| roleId | uuid | YES | no | — | — | — | Role |  |
| permissionId | uuid | YES | no | — | — | — | Permission | UNIQUE(roleId, permissionId) |

### UserRole

_kind: link_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| roleId | uuid | YES | no | — | — | YES | Role |  |
| scopeType | enum(roleScope) | YES | no | — | — | — | — | GLOBAL·TENANT·ORG·DEPT·PROJECT (§43) |
| scopeId | uuid | no | YES | — | — | — | — |  |
| grantedBy | uuid | YES | no | — | — | — | User |  |
| grantedAt | datetime (UTC) | YES | no | — | — | — | — | UNIQUE(userId, roleId, scopeType, scopeId) |

### UserPermission

_kind: link_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| permissionId | uuid | YES | no | — | — | — | Permission |  |
| effect | enum(permissionEffect) | YES | no | — | — | — | — | allow · deny |
| scopeType | enum(roleScope) | no | YES | — | — | — | — |  |
| scopeId | uuid | no | YES | — | — | — | — |  |

### Session

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| tokenHash | varchar(255) | YES | no | — | — | — | — | hash only; UNIQUE(userId, tokenHash) |
| issuedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| expiresAt | datetime (UTC) | YES | no | — | — | YES | — | expiry sweep index |
| revokedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| ipAddress | varchar(45) | no | YES | — | — | — | — |  |
| userAgent | nvarchar(500) | no | YES | — | — | — | — |  |

### AuthenticationMethod

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | — | User |  |
| methodType | enum(authMethodType) | YES | no | — | — | — | — |  |
| secretRef | varchar(255) | YES | no | — | — | — | — | secret-manager reference |
| verifiedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### AccessPolicy

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| subjectType | varchar(64) | YES | no | — | — | YES | — |  |
| subjectId | uuid | no | YES | — | — | YES | — |  |
| resource | varchar(64) | YES | no | — | — | YES | — |  |
| effect | enum(permissionEffect) | YES | no | — | — | — | — |  |
| condition | json | no | YES | — | — | — | — | documented JSON use: policy condition |
| priority | integer | YES | no | 0 | — | — | — |  |

### SecurityEvent

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | no | YES | — | — | YES | User |  |
| eventType | enum(securityEventType) | YES | no | — | — | YES | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| ipAddress | varchar(45) | no | YES | — | — | — | — |  |
| userAgent | nvarchar(500) | no | YES | — | — | — | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: event detail |


## Organization

### Organization

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| legalId | varchar(64) | no | YES | — | — | — | — | registration number |
| orgType | enum(organizationType) | YES | no | — | — | — | — |  |
| parentId | uuid | no | YES | — | — | — | Organization |  |

### OrganizationUnit

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | YES | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, organizationId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| unitType | enum(orgUnitType) | YES | no | — | — | — | — | root · division · department · team |
| parentId | uuid | no | YES | — | — | YES | OrganizationUnit | acyclic (BR-ORG-001) |

### Department

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| headUserId | uuid | no | YES | — | — | — | User |  |
| costCenterId | uuid | no | YES | — | — | — | CostCenter |  |

### Division

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| leadUserId | uuid | no | YES | — | — | — | User |  |

### Team

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationUnitId | uuid | YES | no | — | — | — | OrganizationUnit | 1:1 |
| leadUserId | uuid | no | YES | — | — | — | User |  |

### Position

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | YES | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| title | nvarchar(200) | YES | no | — | — | — | — |  |
| jobTitleId | uuid | no | YES | — | — | — | JobTitle |  |
| grade | varchar(32) | no | YES | — | — | — | — |  |

### JobTitle

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| level | integer | no | YES | — | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### Location

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| addressId | uuid | no | YES | — | — | — | Address |  |
| latitude | decimal(9,6) | no | YES | — | — | — | — |  |
| longitude | decimal(9,6) | no | YES | — | — | — | — |  |

### CostCenter

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| responsibleUserId | uuid | no | YES | — | — | — | User |  |

### OrganizationHierarchy

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| unitId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| parentId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |


## Workforce / HR

### Employee

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeNumber | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, employeeNumber) |
| firstName | nvarchar(120) | YES | no | — | — | — | — |  |
| lastName | nvarchar(120) | YES | no | — | — | — | — |  |
| nationalIdRef | varchar(255) | no | YES | — | — | — | — | secret reference (privacy) |
| birthDate | date | no | YES | — | — | — | — |  |
| userId | uuid | no | YES | — | YES | YES | User | optional 1:1 link |
| status | enum(employeeStatus) | YES | no | — | — | — | — | see StateMachine: Employee |

### Employment

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| organizationId | uuid | YES | no | — | — | — | Organization |  |
| positionId | uuid | YES | no | — | — | — | Position |  |
| employmentType | enum(employmentType) | YES | no | — | — | — | — |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — | null = ongoing (one active per employee) |
| status | enum(employmentStatus) | YES | no | — | — | — | — |  |

### EmploymentHistory

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employmentId | uuid | YES | no | — | — | YES | Employment |  |
| changeType | enum(employmentChangeType) | YES | no | — | — | — | — |  |
| snapshot | json | no | YES | — | — | — | — | documented JSON use: point-in-time snapshot |
| changedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### EmployeeAssignment

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| organizationUnitId | uuid | YES | no | — | — | YES | OrganizationUnit |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |
| allocationPercentage | decimal(5,2) | YES | no | 100.00 | — | — | — | 0–100 |

### EmployeeManager

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| managerId | uuid | YES | no | — | — | YES | Employee | not self (BR-WF-002) |
| reportingType | enum(reportingType) | YES | no | — | — | — | — |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### EmployeeContact

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| contactType | enum(contactType) | YES | no | — | — | — | — |  |
| value | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(employeeId, contactType, value) |
| isPrimary | boolean | YES | no | false | — | — | — |  |

### EmployeeAddress

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| addressId | uuid | YES | no | — | — | — | Address | UNIQUE(employeeId, addressId) |
| addressType | enum(addressType) | YES | no | — | — | — | — |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### EmployeeDocument

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(employeeId, documentId, documentRole) |
| documentRole | enum(employeeDocumentRole) | YES | no | — | — | — | — |  |

### EmployeeSkill

_kind: link_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| skillId | uuid | YES | no | — | — | YES | Skill | UNIQUE(employeeId, skillId) |
| skillLevel | enum(skillLevel) | YES | no | — | — | — | — |  |
| verifiedBy | uuid | no | YES | — | — | — | User |  |

### Skill

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| category | varchar(64) | no | YES | — | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### EmployeeCertification

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee |  |
| certificationId | uuid | YES | no | — | — | YES | Certification | UNIQUE(employeeId, certificationId, issuedAt) |
| issuedAt | date | YES | no | — | — | — | — |  |
| expiresAt | date | no | YES | — | — | — | — |  |
| certificateRef | varchar(255) | no | YES | — | — | — | — | storage reference |

### Certification

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| issuer | nvarchar(200) | no | YES | — | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |


## Performance

### EvaluationCycle

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| periodType | enum(periodType) | YES | no | — | — | — | — | daily·weekly·monthly·quarterly·annual |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | YES | no | — | — | — | — | ≥ startDate (BR-DAT-002) |
| status | enum(cycleStatus) | YES | no | — | — | — | — | see StateMachine: EvaluationCycle |

### EmployeeEvaluation

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationCycleId | uuid | YES | no | — | — | YES | EvaluationCycle | UNIQUE(evaluationCycleId, employeeId) |
| employeeId | uuid | YES | no | — | — | YES | Employee |  |
| status | enum(evaluationStatus) | YES | no | — | — | — | — |  |
| submittedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| resultSummary | nvarchar(max) | no | YES | — | — | — | — |  |

### EvaluationCriteria

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationCycleId | uuid | YES | no | — | — | — | EvaluationCycle |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(evaluationCycleId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| weight | decimal(5,2) | YES | no | — | — | — | — | Σ weight = 100 per cycle (BR-DAT-004) |
| maxScore | decimal(6,2) | YES | no | — | — | — | — |  |

### EvaluationScore

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| evaluationId | uuid | YES | no | — | — | YES | EmployeeEvaluation | UNIQUE(evaluationId, criteriaId, reviewerId) |
| criteriaId | uuid | YES | no | — | — | — | EvaluationCriteria |  |
| reviewerId | uuid | YES | no | — | — | YES | User |  |
| weight | decimal(5,2) | YES | no | — | — | — | — | reviewer weight |
| score | decimal(6,2) | YES | no | — | — | — | — | within criteria bounds (BR-DAT-005) |
| changedAt | datetime (UTC) | YES | no | — | — | — | — | every change audited (BR-AUD-004) |


## Project

### Project

_kind: base_ · _fields incl. standard block: 21_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: link_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| memberType | enum(memberType) | YES | no | — | — | — | — | user · employee |
| memberId | uuid | YES | no | — | — | YES | — | ONE ACTIVE membership per person per project (BR-PRJ-002) |
| projectRoleId | uuid | YES | no | — | — | — | ProjectRole |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — | null = active |
| allocationPercentage | decimal(5,2) | no | YES | — | — | — | — |  |

### ProjectRole

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### ProjectPhase

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — | UNIQUE(projectId, sortOrder) |
| startDate | date | no | YES | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |
| status | enum(phaseStatus) | YES | no | — | — | — | — |  |

### ProjectMilestone

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| projectPhaseId | uuid | no | YES | — | — | — | ProjectPhase |  |
| name | nvarchar(200) | YES | no | — | — | — | — | UNIQUE(projectId, name) |
| dueDate | date | no | YES | — | — | YES | — |  |
| achievedDate | date | no | YES | — | — | — | — |  |
| status | enum(milestoneStatus) | YES | no | — | — | — | — |  |

### ProjectDependency

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| dependsOnProjectId | uuid | YES | no | — | — | YES | Project | not self; acyclic (BR-DAT-008) |
| dependencyType | enum(projectDependencyType) | YES | no | — | — | — | — |  |

### ProjectBudget

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | ≥ 0 (CHECK, §55) |
| currency | varchar(3) | YES | no | — | — | — | — | ISO 4217 |
| fiscalPeriod | varchar(20) | YES | no | — | — | — | — | UNIQUE(projectId, fiscalPeriod) |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### ProjectRisk

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(projectId, title) |
| probability | enum(riskLevel) | YES | no | — | — | — | — |  |
| impact | enum(riskLevel) | YES | no | — | — | — | — |  |
| mitigation | nvarchar(max) | no | YES | — | — | — | — |  |
| status | enum(riskStatus) | YES | no | — | — | YES | — |  |

### ProjectIssue

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | YES | Project |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(projectId, title) |
| severity | enum(issueSeverity) | YES | no | — | — | — | — |  |
| resolvedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(issueStatus) | YES | no | — | — | YES | — |  |

### ProjectDocument

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| projectId | uuid | YES | no | — | — | — | Project |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(projectId, documentId, documentRole) |
| documentRole | enum(projectDocumentRole) | YES | no | — | — | — | — |  |


## Task

### Task

_kind: base_ · _fields incl. standard block: 21_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: vocab_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |
| isTerminal | boolean | YES | no | false | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### TaskPriority

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| level | integer | YES | no | — | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### TaskType

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### TaskAssignment

_kind: link_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(taskId, userId, assignedAt) |
| assignmentRole | enum(taskAssignmentRole) | YES | no | — | — | — | — |  |
| assignedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| removedAt | datetime (UTC) | no | YES | — | — | — | — | null = active |

### TaskDependency

_kind: link_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| dependsOnTaskId | uuid | YES | no | — | — | YES | Task | not self; acyclic (BR-TSK-002) |
| dependencyType | enum(taskDependencyType) | YES | no | — | — | — | — |  |
| lagMinutes | integer | no | YES | 0 | — | — | — |  |

### TaskComment

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | — | User |  |
| body | nvarchar(max) | YES | no | — | — | — | — |  |
| parentId | uuid | no | YES | — | — | — | TaskComment |  |
| editedAt | datetime (UTC) | no | YES | — | — | — | — | edit appends revision (BR-TSK-003) |

### TaskAttachment

_kind: link_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | — | Task |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(taskId, attachmentId) |

### TaskChecklist

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| title | nvarchar(200) | YES | no | — | — | — | — |  |
| sortOrder | integer | YES | no | 0 | — | — | — |  |

### TaskChecklistItem

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| checklistId | uuid | YES | no | — | — | — | TaskChecklist |  |
| label | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(checklistId, label) |
| isDone | boolean | YES | no | false | — | — | — |  |
| doneAt | datetime (UTC) | no | YES | — | — | — | — |  |
| doneBy | uuid | no | YES | — | — | — | User |  |

### TaskTimeEntry

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| userId | uuid | YES | no | — | — | YES | User |  |
| minutes | integer | YES | no | — | — | — | — | > 0 |
| startedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### TaskHistory

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| taskId | uuid | YES | no | — | — | YES | Task |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| changeType | enum(taskChangeType) | YES | no | — | — | — | — |  |
| beforeState | json | no | YES | — | — | — | — | documented JSON use: snapshot |
| afterState | json | no | YES | — | — | — | — | documented JSON use: snapshot |
| changedAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## Asset

### Asset

_kind: base_ · _fields incl. standard block: 18_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| parentId | uuid | no | YES | — | — | — | AssetCategory |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### AssetType

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetCategoryId | uuid | YES | no | — | — | — | AssetCategory |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(tenantId, assetCategoryId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### AssetStatus

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### AssetAssignment

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| holderType | enum(holderType) | YES | no | — | — | — | — |  |
| holderId | uuid | YES | no | — | — | YES | — |  |
| startDate | date | YES | no | — | — | — | — |  |
| endDate | date | no | YES | — | — | — | — |  |

### AssetLocation

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| locationId | uuid | YES | no | — | — | — | Location |  |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### AssetOwnership

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| ownerType | enum(holderType) | YES | no | — | — | — | — |  |
| ownerId | uuid | YES | no | — | — | — | — |  |
| sharePercentage | decimal(5,2) | YES | no | — | — | — | — | Σ ≤ 100 per asset (BR-DAT-006) |
| validFrom | date | YES | no | — | — | — | — |  |
| validTo | date | no | YES | — | — | — | — |  |

### AssetLifecycle

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| eventType | enum(assetEventType) | YES | no | — | — | — | — |  |
| eventDate | date | YES | no | — | — | YES | — |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |

### AssetDocument

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | — | Asset |  |
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(assetId, documentId, documentRole) |
| documentRole | enum(assetDocumentRole) | YES | no | — | — | — | — |  |

### AssetValueHistory

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| assetId | uuid | YES | no | — | — | YES | Asset |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | money: decimal |
| currency | varchar(3) | YES | no | — | — | — | — |  |
| valuedAt | date | YES | no | — | — | YES | — |  |
| source | varchar(120) | no | YES | — | — | — | — |  |


## Device / OT

### Device

_kind: base_ · _fields incl. standard block: 19_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### DeviceManufacturer

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### DeviceModel

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| manufacturerId | uuid | YES | no | — | — | — | DeviceManufacturer |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(tenantId, manufacturerId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### DeviceStatus

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sortOrder | integer | YES | no | 0 | — | — | — |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### DeviceCredential

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | — | Device |  |
| credentialType | enum(deviceCredentialType) | YES | no | — | — | — | — | UNIQUE(deviceId, credentialType) |
| secretRef | varchar(255) | YES | no | — | — | — | — | secret-manager reference; never plain |
| rotatedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceRegistration

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | — | Device | UNIQUE(deviceId) |
| registeredBy | uuid | YES | no | — | — | — | User |  |
| approvedBy | uuid | no | YES | — | — | — | User |  |
| approvedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceHeartbeat

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| status | enum(heartbeatStatus) | YES | no | — | — | — | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: diagnostics |

### DeviceTelemetry

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| metric | varchar(120) | YES | no | — | — | YES | — |  |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |
| quality | enum(telemetryQuality) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### DeviceConfiguration

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| versionNumber | integer | YES | no | — | — | — | — | UNIQUE(deviceId, versionNumber); immutable rows |
| config | json | YES | no | — | — | — | — | documented JSON use: device configuration |
| appliedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DeviceEvent

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| deviceId | uuid | YES | no | — | — | YES | Device |  |
| eventType | enum(deviceEventType) | YES | no | — | — | YES | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| payload | json | no | YES | — | — | — | — | documented JSON use: event payload |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### Agent

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| planId | uuid | YES | no | — | — | YES | MaintenancePlan | UNIQUE(planId, dueAt) |
| dueAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| status | enum(scheduleStatus) | YES | no | — | — | — | — |  |

### MaintenanceWorkOrder

_kind: base_ · _fields incl. standard block: 23_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| title | nvarchar(250) | YES | no | — | — | — | — | UNIQUE(workOrderId, title) |
| technicianId | uuid | no | YES | — | — | YES | User |  |
| status | enum(workOrderStatus) | YES | no | — | — | — | — |  |
| estimatedMinutes | integer | no | YES | — | — | — | — |  |

### MaintenanceEvent

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| eventType | enum(maintenanceEventType) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| note | nvarchar(500) | no | YES | — | — | — | — |  |

### MaintenanceTechnician

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| employeeId | uuid | YES | no | — | — | — | Employee | UNIQUE(employeeId) |
| specializations | json | no | YES | — | — | — | — | documented JSON use: skill list |

### MaintenancePart

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| partRef | varchar(120) | YES | no | — | — | — | — | UNIQUE(workOrderId, partRef) |
| quantity | integer | YES | no | 1 | — | — | — | > 0 |
| unitCost | decimal(19,4) | no | YES | — | — | — | — |  |
| currency | varchar(3) | no | YES | — | — | — | — |  |

### MaintenanceCost

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workOrderId | uuid | YES | no | — | — | YES | MaintenanceWorkOrder |  |
| costType | enum(maintenanceCostType) | YES | no | — | — | — | — |  |
| amount | decimal(19,4) | YES | no | — | — | — | — | ≥ 0 |
| currency | varchar(3) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | — | — |  |

### MaintenanceHistory

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | enum(maintenanceTargetType) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| summary | nvarchar(500) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |


## Document

### Document

_kind: base_ · _fields incl. standard block: 19_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### DocumentCategory

_kind: vocab_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| parentId | uuid | no | YES | — | — | — | DocumentCategory |  |
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### DocumentFolder

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| name | nvarchar(200) | YES | no | — | — | — | — | UNIQUE(tenantId, parentId, name) |
| parentId | uuid | no | YES | — | — | — | DocumentFolder |  |

### DocumentPermission

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| subjectType | enum(subjectType) | YES | no | — | — | — | — |  |
| subjectId | uuid | YES | no | — | — | YES | — | UNIQUE(documentId, subjectType, subjectId, permissionLevel) |
| permissionLevel | enum(documentPermissionLevel) | YES | no | — | — | — | — |  |
| grantedBy | uuid | YES | no | — | — | — | User |  |
| grantedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| expiresAt | datetime (UTC) | no | YES | — | — | — | — |  |

### DocumentShare

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| sharedWithType | enum(subjectType) | YES | no | — | — | — | — |  |
| sharedWithId | uuid | YES | no | — | — | — | — |  |
| sharedBy | uuid | YES | no | — | — | — | User |  |
| expiresAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### DocumentMetadata

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document |  |
| key | varchar(120) | YES | no | — | — | — | — | UNIQUE(documentId, key) |
| value | nvarchar(max) | no | YES | — | — | — | — |  |

### DocumentAttachment

_kind: link_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | — | Document |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(documentId, attachmentId) |

### DocumentWorkflow

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| documentId | uuid | YES | no | — | — | YES | Document | UNIQUE(documentId, workflowInstanceId) |
| workflowInstanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| triggeredAt | datetime (UTC) | YES | no | — | — | — | — |  |


## Workflow

### Workflow

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |

### WorkflowVersion

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowId | uuid | YES | no | — | — | YES | Workflow |  |
| versionNumber | integer | YES | no | — | — | — | — | UNIQUE(workflowId, versionNumber) |
| status | enum(workflowVersionStatus) | YES | no | — | — | — | — |  |

### WorkflowDefinition

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowVersionId | uuid | YES | no | — | — | — | WorkflowVersion | UNIQUE(workflowVersionId) |
| definition | json | YES | no | — | — | — | — | documented JSON use: graph definition |

### WorkflowNode

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| nodeKey | varchar(64) | YES | no | — | — | — | — | UNIQUE(workflowDefinitionId, nodeKey) |
| nodeType | enum(workflowNodeType) | YES | no | — | — | — | — |  |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: node config |

### WorkflowTransition

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| fromNodeKey | varchar(64) | YES | no | — | — | — | — | UNIQUE(definitionId, fromNodeKey, toNodeKey) |
| toNodeKey | varchar(64) | YES | no | — | — | — | — |  |
| condition | json | no | YES | — | — | — | — | documented JSON use: transition condition |

### WorkflowInstance

_kind: base_ · _fields incl. standard block: 17_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowDefinitionId | uuid | YES | no | — | — | YES | WorkflowDefinition |  |
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| status | enum(workflowInstanceStatus) | YES | no | — | — | YES | — | see StateMachine: Workflow |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| completedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| context | json | no | YES | — | — | — | — | documented JSON use: instance context |

### WorkflowInstanceState

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | — | WorkflowInstance | UNIQUE(instanceId) |
| currentNodeKey | varchar(64) | YES | no | — | — | — | — |  |
| enteredAt | datetime (UTC) | YES | no | — | — | — | — |  |
| waitingFor | json | no | YES | — | — | — | — | documented JSON use: pending approvals |

### WorkflowTask

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance | UNIQUE(instanceId, nodeKey) |
| nodeKey | varchar(64) | YES | no | — | — | — | — |  |
| assigneeId | uuid | no | YES | — | — | YES | User |  |
| status | enum(workflowTaskStatus) | YES | no | — | — | YES | — |  |
| dueAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### WorkflowAction

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| actorId | uuid | YES | no | — | — | — | User |  |
| actionType | enum(workflowActionType) | YES | no | — | — | — | — |  |
| comment | nvarchar(500) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WorkflowApproval

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| workflowTaskId | uuid | YES | no | — | — | YES | WorkflowTask | UNIQUE(workflowTaskId, approverId) |
| approverId | uuid | YES | no | — | — | YES | User |  |
| decision | enum(approvalDecision) | YES | no | — | — | — | — | approved · rejected · pending · cancelled |
| decidedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| comment | nvarchar(500) | no | YES | — | — | — | — | required when REJECTED (BR-WF-003) |
| delegatedFromId | uuid | no | YES | — | — | — | WorkflowApproval |  |

### WorkflowHistory

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| instanceId | uuid | YES | no | — | — | YES | WorkflowInstance |  |
| fromNode | varchar(64) | no | YES | — | — | — | — |  |
| toNode | varchar(64) | no | YES | — | — | — | — |  |
| actorId | uuid | no | YES | — | — | — | User |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| metadata | json | no | YES | — | — | — | — | documented JSON use: transition detail |


## Communication

### Conversation

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationType | enum(conversationType) | YES | no | — | — | YES | — | direct · group · channel · meeting · system |
| title | nvarchar(200) | no | YES | — | — | — | — | null = direct chat (no title) |
| createdBy | uuid | YES | no | — | — | — | User | creator mandatory (BR-COM-001) |
| lastMessageAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| retentionDays | integer | no | YES | — | — | — | — | per-tenant policy; null = platform default |

### ConversationMember

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | YES | Conversation | UNIQUE(conversationId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| memberRole | enum(conversationRole) | YES | no | — | — | — | — | owner·admin·moderator·member·guest·readOnly |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |
| mutedUntil | datetime (UTC) | no | YES | — | — | — | — |  |

### ConversationType

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### Message

_kind: base_ · _fields incl. standard block: 19_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: link_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| attachmentId | uuid | YES | no | — | — | — | Attachment | UNIQUE(messageId, attachmentId) |

### MessageReaction

_kind: link_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| userId | uuid | YES | no | — | — | — | User | UNIQUE(messageId, userId, emoji) |
| emoji | varchar(32) | YES | no | — | — | — | — |  |

### MessageReadReceipt

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| messageId | uuid | YES | no | — | — | — | Message |  |
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(messageId, userId) |
| readAt | datetime (UTC) | YES | no | — | — | — | — |  |

### Channel

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | — | Conversation | UNIQUE(conversationId) |
| visibility | enum(channelVisibility) | YES | no | — | — | YES | — | public · private · announcement |
| description | nvarchar(500) | no | YES | — | — | — | — |  |

### ChannelMember

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| channelId | uuid | YES | no | — | — | YES | Channel | UNIQUE(channelId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| memberRole | enum(conversationRole) | YES | no | — | — | — | — |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### VoiceCall

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| initiatorId | uuid | YES | no | — | — | — | User |  |
| callType | enum(callType) | YES | no | — | — | — | — | direct · group |
| status | enum(callStatus) | YES | no | — | — | — | — | see StateMachine: Call |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### VoiceCallParticipant

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| callId | uuid | YES | no | — | — | YES | VoiceCall | UNIQUE(callId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| joinedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |
| state | enum(participantState) | YES | no | — | — | — | — |  |

### GroupCall

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| hostId | uuid | YES | no | — | — | — | User |  |
| status | enum(callStatus) | YES | no | — | — | — | — |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### VideoMeeting

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | no | YES | — | — | — | Conversation |  |
| hostId | uuid | YES | no | — | — | — | User |  |
| scheduledAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| startedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(meetingStatus) | YES | no | — | — | — | — | see StateMachine: Meeting |
| isRecurring | boolean | YES | no | false | — | — | — |  |

### MeetingParticipant

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingId | uuid | YES | no | — | — | YES | VideoMeeting | UNIQUE(meetingId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| participantRole | enum(meetingRole) | YES | no | — | — | — | — |  |
| invitedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| joinedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| leftAt | datetime (UTC) | no | YES | — | — | — | — |  |

### MeetingSession

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingId | uuid | YES | no | — | — | YES | VideoMeeting | UNIQUE(meetingId, sessionKey) |
| sessionKey | varchar(64) | YES | no | — | — | — | — |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### ScreenShareSession

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingSessionId | uuid | YES | no | — | — | YES | MeetingSession |  |
| sharerId | uuid | YES | no | — | — | — | User |  |
| startedAt | datetime (UTC) | YES | no | — | — | — | — |  |
| endedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### MeetingRecording

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| meetingSessionId | uuid | YES | no | — | — | YES | MeetingSession |  |
| storageProvider | varchar(32) | YES | no | — | — | — | — | binary in object storage — never DB |
| storageKey | varchar(512) | YES | no | — | — | — | — |  |
| durationSeconds | integer | YES | no | — | — | — | — |  |
| status | enum(recordingStatus) | YES | no | — | — | — | — |  |
| consentCaptured | boolean | YES | no | false | — | — | — | BR-COM-006 |

### Presence

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(userId, deviceId) |
| deviceId | uuid | no | YES | — | — | — | — |  |
| presenceStatus | enum(presenceStatus) | YES | no | — | — | YES | — | online·away·busy·doNotDisturb·offline (§30) |
| lastSeenAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### PresenceStatus

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |


## Notification

### Notification

_kind: base_ · _fields incl. standard block: 18_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(120) | YES | no | — | — | — | — | UNIQUE(tenantId, code, versionNumber) |
| versionNumber | integer | YES | no | — | — | — | — |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| subjectTemplate | nvarchar(500) | no | YES | — | — | — | — |  |
| bodyTemplate | nvarchar(max) | YES | no | — | — | — | — |  |
| variables | json | no | YES | — | — | — | — | documented JSON use: variable schema |

### NotificationPreference

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User | UNIQUE(userId, notificationType, channel) |
| notificationType | varchar(120) | YES | no | — | — | — | — |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| enabled | boolean | YES | no | true | — | — | — |  |
| quietStart | time | no | YES | — | — | — | — |  |
| quietEnd | time | no | YES | — | — | — | — |  |

### NotificationChannel

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### NotificationDelivery

_kind: append_ · _fields incl. standard block: 10_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| notificationId | uuid | YES | no | — | — | YES | Notification |  |
| recipientId | uuid | YES | no | — | — | YES | NotificationRecipient |  |
| channel | enum(notificationChannelType) | YES | no | — | — | — | — |  |
| status | enum(deliveryStatus) | YES | no | — | — | YES | — | pending · sent · delivered · failed · read (§31) |
| attemptedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| providerRef | varchar(255) | no | YES | — | — | — | — |  |
| error | nvarchar(500) | no | YES | — | — | — | — | retryable (BR-NOT-002) |

### NotificationRecipient

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| notificationId | uuid | YES | no | — | — | YES | Notification | UNIQUE(notificationId, userId) |
| userId | uuid | YES | no | — | — | YES | User |  |
| readAt | datetime (UTC) | no | YES | — | — | YES | — | read state lives HERE |


## Audit

### AuditEvent

_kind: append_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| dataSource | varchar(120) | YES | no | — | — | — | — |  |
| parameterSchema | json | no | YES | — | — | — | — | documented JSON use: parameter schema |

### ReportParameter

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition | UNIQUE(reportDefinitionId, key) |
| key | varchar(64) | YES | no | — | — | — | — |  |
| parameterType | enum(parameterType) | YES | no | — | — | — | — |  |
| isRequired | boolean | YES | no | false | — | — | — |  |
| defaultValue | nvarchar(500) | no | YES | — | — | — | — |  |

### ReportExecution

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition |  |
| requestedBy | uuid | YES | no | — | — | — | User |  |
| startedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| finishedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(executionStatus) | YES | no | — | — | YES | — |  |

### ReportSchedule

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition |  |
| cronExpression | varchar(64) | YES | no | — | — | — | — | UNIQUE(reportDefinitionId, cronExpression) |
| nextRunAt | datetime (UTC) | no | YES | — | — | YES | — |  |

### ReportOutput

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| executionId | uuid | YES | no | — | — | YES | ReportExecution |  |
| storageProvider | varchar(32) | YES | no | — | — | — | — |  |
| storageKey | varchar(512) | YES | no | — | — | — | — |  |
| format | enum(reportFormat) | YES | no | — | — | — | — |  |
| generatedAt | datetime (UTC) | YES | no | — | — | — | — |  |

### ReportAccess

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| reportDefinitionId | uuid | YES | no | — | — | YES | ReportDefinition | UNIQUE(reportDefinitionId, subjectType, subjectId) |
| subjectType | enum(subjectType) | YES | no | — | — | — | — |  |
| subjectId | uuid | YES | no | — | — | — | — |  |
| accessLevel | enum(reportAccessLevel) | YES | no | — | — | — | — |  |


## Analytics

### MetricDefinition

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| formula | nvarchar(500) | no | YES | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### MetricValue

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| metricId | uuid | YES | no | — | — | YES | MetricDefinition |  |
| dimensions | json | no | YES | — | — | — | — | documented JSON use: dimension filter |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| periodStart | datetime (UTC) | YES | no | — | — | — | — |  |
| periodEnd | datetime (UTC) | YES | no | — | — | — | — |  |

### KpiDefinition

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| targetValue | decimal(18,6) | no | YES | — | — | — | — |  |
| direction | enum(kpiDirection) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### KpiValue

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| kpiId | uuid | YES | no | — | — | YES | KpiDefinition |  |
| dimensions | json | no | YES | — | — | — | — | documented JSON use: dimension filter |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| periodType | enum(periodType) | YES | no | — | — | — | — |  |
| periodStart | datetime (UTC) | YES | no | — | — | — | — |  |
| periodEnd | datetime (UTC) | YES | no | — | — | — | — |  |

### Dashboard

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| ownerId | uuid | YES | no | — | — | YES | User |  |
| layout | json | no | YES | — | — | — | — | documented JSON use: layout |

### DashboardWidget

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| dashboardId | uuid | YES | no | — | — | YES | Dashboard |  |
| widgetType | varchar(64) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: widget config |
| position | integer | YES | no | 0 | — | — | — | UNIQUE(dashboardId, position) |

### AnalyticsSnapshot

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scopeType | varchar(64) | YES | no | — | — | YES | — |  |
| scopeId | uuid | YES | no | — | — | YES | — |  |
| periodType | enum(periodType) | YES | no | — | — | — | — |  |
| data | json | YES | no | — | — | — | — | documented JSON use: projection payload |
| builtAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## AI

### AiProvider

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | YES | — | — | global unique |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| adapterType | enum(aiAdapterType) | YES | no | — | — | — | — |  |
| config | json | no | YES | — | — | — | — | documented JSON use: provider config (no secrets) |

### AiModel

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| providerId | uuid | YES | no | — | — | YES | AiProvider |  |
| code | varchar(64) | YES | no | — | — | — | — | UNIQUE(providerId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| modality | enum(aiModality) | YES | no | — | — | — | — |  |

### AiModelVersion

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| modelId | uuid | YES | no | — | — | YES | AiModel |  |
| versionNumber | varchar(64) | YES | no | — | — | — | — | UNIQUE(modelId, versionNumber) |
| status | enum(aiModelStatus) | YES | no | — | — | — | — |  |
| contextLimit | integer | no | YES | — | — | — | — |  |
| releasedAt | date | no | YES | — | — | — | — |  |

### AiAgent

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| modelVersionId | uuid | YES | no | — | — | — | AiModelVersion |  |
| instructions | nvarchar(max) | no | YES | — | — | — | — |  |
| status | enum(aiAgentStatus) | YES | no | — | — | — | — |  |

### AiAgentExecution

_kind: append_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| capability | varchar(120) | YES | no | — | — | YES | — |  |
| inputRef | uuid | no | YES | — | — | — | — | input reference (§37) |
| promptVersionRef | uuid | no | YES | — | — | — | — | prompt/context reference (§37) |
| requestedBy | uuid | YES | no | — | — | — | User |  |
| status | enum(executionStatus) | YES | no | — | — | — | — |  |

### AiResponse

_kind: base_ · _fields incl. standard block: 19_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
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

_kind: base_ · _fields incl. standard block: 11_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| userId | uuid | YES | no | — | — | YES | User |  |
| title | nvarchar(250) | no | YES | — | — | — | — |  |

### AiMessage

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| conversationId | uuid | YES | no | — | — | YES | AiConversation |  |
| role | enum(aiMessageRole) | YES | no | — | — | — | — |  |
| content | nvarchar(max) | YES | no | — | — | — | — |  |
| promptTokens | integer | no | YES | — | — | — | — |  |
| completionTokens | integer | no | YES | — | — | — | — |  |

### AiKnowledgeSource

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| sourceType | enum(knowledgeSourceType) | YES | no | — | — | — | — |  |
| ingestionConfig | json | no | YES | — | — | — | — | documented JSON use: ingestion config |

### AiKnowledgeDocument

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| sourceId | uuid | YES | no | — | — | YES | AiKnowledgeSource | UNIQUE(sourceId, documentRef) |
| documentRef | uuid | no | YES | — | — | — | Document |  |
| chunkCount | integer | YES | no | 0 | — | — | — |  |
| status | enum(executionStatus) | YES | no | — | — | — | — |  |

### AiEmbedding

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| knowledgeDocumentId | uuid | YES | no | — | — | YES | AiKnowledgeDocument |  |
| chunkRef | varchar(120) | YES | no | — | — | — | — |  |
| vectorRef | varchar(255) | YES | no | — | — | — | — | vector store reference |
| metadata | json | no | YES | — | — | — | — | documented JSON use: chunk metadata |

### AiRecommendation

_kind: base_ · _fields incl. standard block: 16_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| content | nvarchar(max) | YES | no | — | — | — | — |  |
| classification | enum(resultClassification) | YES | no | — | — | — | — |  |
| status | enum(recommendationStatus) | YES | no | — | — | YES | — |  |
| reviewedBy | uuid | no | YES | — | — | — | User |  |
| reviewedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### AiPrediction

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| targetType | varchar(64) | YES | no | — | — | YES | — |  |
| targetId | uuid | YES | no | — | — | YES | — |  |
| horizon | varchar(64) | YES | no | — | — | — | — |  |
| predictedValue | decimal(18,6) | YES | no | — | — | — | — |  |
| confidence | decimal(5,4) | no | YES | — | — | — | — |  |
| evaluatedAt | datetime (UTC) | YES | no | — | — | — | — | compared to actual when available |

### AiInsight

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| scopeType | varchar(64) | YES | no | — | — | YES | — |  |
| scopeId | uuid | YES | no | — | — | YES | — |  |
| summary | nvarchar(500) | YES | no | — | — | — | — |  |
| evidence | json | no | YES | — | — | — | — | documented JSON use: evidence refs |
| generatedAt | datetime (UTC) | YES | no | — | — | — | — |  |


## Integration

### Integration

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| integrationTypeId | uuid | YES | no | — | — | YES | IntegrationType |  |
| status | enum(integrationStatus) | YES | no | — | — | — | — |  |

### IntegrationType

_kind: vocab_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| (VOCAB) code · name · description | — | — | — | — | code scoped-unique | — | — | standard VOCAB block (§74) |

### IntegrationCredential

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, credentialType) |
| credentialType | enum(credentialType) | YES | no | — | — | — | — |  |
| secretRef | varchar(255) | YES | no | — | — | — | — | never plain text (BR-INT-001) |
| rotatedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### IntegrationEndpoint

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| url | nvarchar(500) | no | YES | — | — | — | — |  |
| authType | enum(endpointAuthType) | YES | no | — | — | — | — |  |

### IntegrationConnection

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | — | Integration | UNIQUE(integrationId) |
| status | enum(connectionStatus) | YES | no | — | — | — | — |  |
| lastConnectedAt | datetime (UTC) | no | YES | — | — | YES | — |  |
| latencyMs | integer | no | YES | — | — | — | — |  |

### IntegrationMapping

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, direction) |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| mapping | json | YES | no | — | — | — | — | documented JSON use: field mapping |

### IntegrationJob

_kind: base_ · _fields incl. standard block: 14_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration | UNIQUE(integrationId, name) |
| name | nvarchar(200) | YES | no | — | — | — | — |  |
| cronExpression | varchar(64) | no | YES | — | — | — | — |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| status | enum(jobStatus) | YES | no | — | — | — | — |  |

### IntegrationExecution

_kind: append_ · _fields incl. standard block: 9_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| jobId | uuid | YES | no | — | — | YES | IntegrationJob |  |
| status | enum(integrationExecutionStatus) | YES | no | — | — | YES | — | started · success · failed · retrying (§39) |
| startedAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| finishedAt | datetime (UTC) | no | YES | — | — | — | — |  |
| statistics | json | no | YES | — | — | — | — | documented JSON use: run stats |
| error | nvarchar(500) | no | YES | — | — | — | — | traceable (BR-INT-002) |

### IntegrationEvent

_kind: base_ · _fields incl. standard block: 15_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| direction | enum(integrationDirection) | YES | no | — | — | — | — |  |
| idempotencyKey | varchar(190) | YES | no | — | — | — | — | UNIQUE(integrationId, idempotencyKey) |
| payload | json | no | YES | — | — | — | — | documented JSON use: external payload |
| status | enum(integrationEventStatus) | YES | no | — | — | YES | — |  |
| processedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### IntegrationError

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| integrationId | uuid | YES | no | — | — | YES | Integration |  |
| executionId | uuid | no | YES | — | — | YES | IntegrationExecution |  |
| errorCode | varchar(64) | YES | no | — | — | — | — |  |
| message | nvarchar(1000) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |


## Industry Extension (pack — NOT Core)

### WinCcServer

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| code | varchar(64) | YES | no | — | — | YES | — | UNIQUE(tenantId, code) |
| host | nvarchar(250) | YES | no | — | — | — | — |  |
| connectionProfile | json | no | YES | — | — | — | — | documented JSON use: connection config |

### WinCcConnection

_kind: base_ · _fields incl. standard block: 12_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | — | WinCcServer | UNIQUE(serverId) |
| status | enum(connectionStatus) | YES | no | — | — | — | — |  |
| lastSyncAt | datetime (UTC) | no | YES | — | — | — | — |  |

### WinCcTag

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| tagPath | varchar(250) | YES | no | — | — | — | — | UNIQUE(tenantId, serverId, tagPath) |
| dataType | enum(tagDataType) | YES | no | — | — | — | — |  |
| unit | varchar(32) | no | YES | — | — | — | — |  |

### WinCcTagValue

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| tagId | uuid | YES | no | — | — | YES | WinCcTag |  |
| value | decimal(18,6) | YES | no | — | — | — | — |  |
| quality | enum(telemetryQuality) | no | YES | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WinCcAlarm

_kind: append_ · _fields incl. standard block: 8_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| alarmCode | varchar(120) | YES | no | — | — | — | — |  |
| severity | enum(severityLevel) | YES | no | — | — | — | — |  |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |
| acknowledgedAt | datetime (UTC) | no | YES | — | — | — | — |  |

### WinCcEvent

_kind: append_ · _fields incl. standard block: 7_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | YES | WinCcServer |  |
| eventType | varchar(120) | YES | no | — | — | — | — |  |
| payload | json | no | YES | — | — | — | — | documented JSON use: event payload |
| occurredAt | datetime (UTC) | YES | no | — | — | YES | — |  |

### WinCcSyncJob

_kind: base_ · _fields incl. standard block: 13_

| Name | Type | Required | Nullable | Default | Unique | Index | FK | Description |
|---|---|---|---|---|---|---|---|---|
| serverId | uuid | YES | no | — | — | — | WinCcServer | UNIQUE(serverId) |
| config | json | no | YES | — | — | — | — | documented JSON use: sync config |
| lastRunAt | datetime (UTC) | no | YES | — | — | — | — |  |
| status | enum(jobStatus) | YES | no | — | — | — | — |  |

