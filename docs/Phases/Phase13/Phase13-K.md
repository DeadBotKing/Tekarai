# Phase 13-K — Tenant Isolation، Authorization و Permission Filtering

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** K از A تا Z  
**وضعیت:** COMPLETED — Authorization/Permission Gate GREEN  
**تاریخ قرارداد و اجرا:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-J.md`](Phase13-J.md)  
**گزارش اجرا:** [`Phase13-K-ExecutionReport.md`](Phase13-K-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز K مرز صریح authorization بین Application و AI Domain را ایجاد می‌کند.
J قبلاً source candidate را Tenant-bound می‌کرد و امکان دریافت یک
`permissionFilter` ساده داشت؛ K این boundary را به یک Permission Engine خالص،
قابل trace و fail-closed تبدیل می‌کند.

K به این سؤال پاسخ می‌دهد:

> چگونه اطمینان بدهیم که عضویت در Tenant به‌تنهایی مجوز نیست، هر AI resource
> پیش از مصرف با permission صریح بررسی می‌شود، deny بر allow تقدم دارد و فقط
> sourceهای مجاز پیش از Context assembly به J می‌رسند؟

K سه اصل ثابت دارد:

1. **Tenant isolation:** هیچ Principal یا Resource خارج از Tenant جاری ارزیابی
   نمی‌شود؛
2. **Least privilege:** نبودن grant صریح به معنی deny است؛
3. **Fail closed:** خطای ساختار، Tenant mismatch یا principal نامعتبر به جای
   fallback permissive رد می‌شود.

K authentication را انجام نمی‌دهد. Application یک snapshot از subject احراز‌شده
را به شکل `AuthorizationPrincipal` ارائه می‌کند و K فقط authorization و filtering
خالص را روی همان ورودی انجام می‌دهد.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- تعریف `AuthorizationPrincipal` با Tenant، Subject، نوع subject، Roleها و direct
  permissionهای صریح؛
- تعریف `AuthorizationResource` برای resource referenceهای بدون payload؛
- تعریف `PermissionGrant` با Subject یا Role target؛
- Allow/Deny effect با deny precedence؛
- exact و prefix wildcard permission matching؛
- resource type، resource ID، source identity، classification و external-provider
  selectors؛
- grant priority، expiry و active-at evaluation؛
- default deny و policy immutable؛
- Tenant mismatch rejection برای Principal و Resource؛
- principal و grant registry در حافظه با duplicate protection؛
- safe descriptor برای Principal و Grant؛
- immutable `AuthorizationDecision` شامل reason، matched grant و fingerprint؛
- safe `SourcePermissionDecision` و `PermissionFilterResult`؛
- Context source filtering با `ContextSourceCandidate` از J؛
- حذف source غیرمجاز بدون expose کردن content؛
- رد source متعلق به Tenant دیگر؛
- authorization لازم برای Context build؛
- authorization جداگانه برای Context read/list؛
- permission مستقل برای external Context export؛
- اتصال `AuthorizedContextEngine` به `ContextEngine` فاز J؛
- typed helper برای Request، Response، Prompt، Model، Provider و Capability؛
- deep-copy برای Principal/Grant registry و عدم نگهداری payload در decision؛
- pure Unit Test، regression B تا K، compile، purity، whitespace، link، archive
  integrity و test روی Extract؛
- ثبت Scope، تصمیم‌های معماری، محدودیت‌ها، Verification، Gate و ZIP مستقل.

### 2.2 خارج از Scope

- Authentication، login، session، JWT، OAuth یا identity provider؛
- واکشی User، Role، Membership، ACL یا Permission از Database؛
- Django ORM، API، Serializer، View، Admin یا Permission endpoint؛
- تغییر در Domainهای Project، Task، HR، Document یا Communication؛
- persistence durable، transaction، distributed lock، cache یا concurrency؛
- تولید یا resolve کردن Secret، API Key، Password، Token یا credential؛
- Provider SDK، Network، Model inference، Queue، Worker یا Redis؛
- جایگزینی Governance/Audit دائمی O؛ Decision K فقط یک read model امن و in-memory
  برای traceability است؛
- PII scanner، DLP، malware scanner یا prompt-injection detector؛
- classification policy محتوایی J؛ K permission را بررسی می‌کند و J همچنان
  `ContextPolicy` را برای classification/limits اعمال می‌کند؛
- اجرای Tool، Agent، Response delivery یا Usage/Cost accounting؛
- ادعای thread-safe یا multi-process authorization؛
- bypass عمومی برای `SYSTEM`؛ نوع Principal به‌تنهایی هیچ permissionی اعطا نمی‌کند.

---

## 3. جایگاه معماری

```text
Authentication / Application Boundary
        │
        │  immutable AuthorizationPrincipal snapshot
        ▼
AuthorizationService (K)
   ├─ Tenant boundary
   ├─ Subject / Role grant matching
   ├─ Explicit Allow/Deny evaluation
   ├─ Resource selector matching
   ├─ Safe AuthorizationDecision
   └─ Context source filtering
        │
        ├──────────────► AI Request/Prompt/Model/etc. authorization helpers
        │
        ▼
AuthorizedContextEngine (K facade)
        │
        ▼
ContextEngine / ContextBuilder (J)
        │
        ▼
AIContext (B) → future Application/Provider orchestration
```

مرز مالکیت:

| مفهوم | مالک |
|---|---|
| Entityهای AI و `ContextSource` | B |
| Context budgets و classification policy | B/J |
| Tenant-bound `ContextSourceCandidate` | J |
| Principal snapshot و grant evaluation | K |
| Permission filtering و context authorization facade | K |
| Authentication و load کردن membership/grants | Application/Identity |
| Permission audit persistence و governance | O/Application |
| Provider transmission policy و adapter | L |
| Usage/Cost/Latency | N/W |

---

## 4. Principal Contract

### 4.1 `AuthorizationPrincipal`

```python
principal = AuthorizationPrincipal(
    tenantId=tenantId,
    subjectId=userId,
    subjectType="USER",
    roles=("ANALYST",),
    directPermissions=("AI_CONTEXT_READ",),
    isActive=True,
)
```

قواعد:

- `tenantId` و `subjectId` UUID معتبر هستند؛
- `subjectType` فقط `USER`، `SERVICE` یا `SYSTEM` است؛
- Roleها normalize و deduplicate می‌شوند؛
- direct permissionها normalize و deduplicate می‌شوند؛
- permissionهای wildcard مانند `AI_CONTEXT_*` قابل استفاده‌اند؛
- Principal inactive هیچ permissionی—even direct permission—اعمال نمی‌کند؛
- `SYSTEM` نیز بدون grant/direct permission مجاز نیست؛
- Principal فقط یک snapshot از Application است و K هویت آن را authenticate نمی‌کند؛
- Principal با Tenant A هرگز برای resource Tenant B evaluate نمی‌شود.

ثبت Principal در registry برای composition root، inspection و snapshot isolation
است. `AuthorizationService` به‌صورت عمدی authentication یا lookup خارجی را به
ثبت Principal تبدیل نمی‌کند.

### 4.2 `AuthorizationResource`

Resource فقط reference و policy attributes دارد و payload یا content ندارد:

```python
resource = AuthorizationResource(
    tenantId=tenantId,
    resourceType="CONTEXT_SOURCE",
    resourceId="document-123",
    sourceDomain="projects",
    sourceEntityType="document",
    sourceEntityId="document-123",
    classification="INTERNAL",
    externalProvider=False,
)
```

Resource type باید concrete باشد. `*` فقط برای selectorهای Grant مجاز است، نه
Resource واقعی. Source identity در Resource، اگر استفاده شود، باید سه جزء کامل
`sourceDomain`، `sourceEntityType` و `sourceEntityId` را داشته باشد.

Factoryهای مهم:

```text
AuthorizationResource.entity(...)
AuthorizationResource.context(...)
AuthorizationResource.source(candidate)
AuthorizationResource.tenant(...)
```

هیچ factoryای content، metadata یا secret را به Decision منتقل نمی‌کند.

---

## 5. Permission Grant Contract

### 5.1 ساختار Grant

```python
grant = PermissionGrant(
    tenantId=tenantId,
    permissionCode="AI_CONTEXT_SOURCE_READ",
    effect="ALLOW",
    roleCode="ANALYST",
    resourceType="CONTEXT_SOURCE",
    sourceDomain="projects",
    allowedClassifications=("PUBLIC", "INTERNAL"),
)
```

هر Grant دقیقاً یکی از این targetها را دارد:

- `subjectId` برای direct subject grant؛ یا
- `roleCode` برای role grant.

Grant بدون target یا با Subject و Role همزمان رد می‌شود. Grantها Tenant-bound
هستند و در registry با `(tenantId, grantId)` نگه‌داری می‌شوند.

### 5.2 Permission code و wildcard

Permission codeها normalize و validate می‌شوند. نمونه‌های استاندارد K:

```text
AI_CONTEXT_BUILD
AI_CONTEXT_READ
AI_CONTEXT_SOURCE_READ
AI_CONTEXT_EXPORT
AI_REQUEST_CREATE
AI_REQUEST_READ
AI_REQUEST_TRANSITION
AI_RESPONSE_CREATE
AI_RESPONSE_READ
AI_PROMPT_READ
AI_PROMPT_RENDER
AI_PROVIDER_USE
AI_MODEL_USE
AI_CAPABILITY_USE
AI_MEMORY_READ / AI_MEMORY_WRITE
AI_KNOWLEDGE_READ / AI_KNOWLEDGE_WRITE
AI_TOOL_USE
AI_AGENT_USE
AI_OUTPUT_AUTHORITATIVE
```

پشتیبانی wildcard محدود به `*` و prefix wildcard مانند `AI_CONTEXT_*` است. Prefix
wildcard فقط ابتدای یک permission را match می‌کند و permissionهای unrelated را
باز نمی‌کند.

### 5.3 Resource selectorها

Grant می‌تواند به این موارد محدود شود:

- `resourceType`؛
- `resourceId`؛
- `sourceDomain`؛
- `sourceEntityType`؛
- `sourceEntityId`؛
- `allowedClassifications`؛
- `externalProvider`؛
- `priority`؛
- `expiresAt`.

Selectorهای خالی wildcard آن dimension هستند. Selectorهای غیرخالی باید با
Resource جاری match شوند. Grant با `externalProvider=True` فقط برای Resource
external match می‌شود و به‌صورت implicit مجوز external برای Resource داخلی یا
برعکس تولید نمی‌کند.

### 5.4 Effect و precedence

ارزیابی به شکل زیر است:

```text
Foreign Tenant                    → AIAuthorizationTenantMismatch
Inactive Principal                → deny / INACTIVE_PRINCIPAL
Matching DENY + deny precedence  → deny / EXPLICIT_DENY
Matching ALLOW                   → allow / EXPLICIT_ALLOW
Direct permission بدون deny      → allow / DIRECT_PERMISSION
No matching rule                 → deny / DEFAULT_DENY
```

`AuthorizationPolicy.defaultDeny` باید true باشد. `denyOverridesAllow` به‌صورت
پیش‌فرض true است. حتی اگر یک Role allow عمومی بدهد، deny اختصاصی همان subject یا
Role آن permission/resource را مسدود می‌کند.

---

## 6. Authorization Decision و Safe Read Model

### 6.1 `AuthorizationDecision`

Decision immutable و بدون payload است و شامل این موارد است:

- `decisionId`؛
- Tenant و Subject ID؛
- action؛
- resource type و reference؛
- allowed؛
- reason؛
- matched grant ID در صورت وجود؛
- evaluatedAt؛
- deterministic decision fingerprint.

Fingerprint برای traceability است و content، metadata یا credential را encode
نمی‌کند. `requirePermission()` در صورت deny فقط یک exception با action امن صادر
می‌کند و متن Resource را در پیام خطا قرار نمی‌دهد.

### 6.2 Grant و Principal Descriptor

`PrincipalDescriptor` فقط subject type، roleها، active state و تعداد direct
permissionها را expose می‌کند. `GrantDescriptor` فقط selectorهای policy را
expose می‌کند و payload یا secret field ندارد.

### 6.3 Source Permission Result

`PermissionFilterResult` شامل این موارد است:

- Tenant و Subject؛
- action؛
- requested/allowed/denied counts؛
- safe `SourcePermissionDecision` برای هر source؛
- زمان ارزیابی؛
- `authorizedSources` برای downstream assembly که در `repr` عمداً مخفی است.

`SourcePermissionDecision` فقط source reference، classification، allowed/reason
و `authorizationDecisionId` دارد. محتوای source حذف‌شده هیچ‌گاه در result یا
reason قرار نمی‌گیرد.

---

## 7. Context Permission Filtering و اتصال به J

### 7.1 Filtering

```python
filtered = authorization.filterContextSources(
    principal,
    candidates,
    action="AI_CONTEXT_SOURCE_READ",
)
```

برای هر candidate:

1. type و Tenant آن بررسی می‌شود؛
2. source دارای `authorized=False` با `SOURCE_NOT_AUTHORIZED` حذف می‌شود؛
3. Resource بدون content از candidate ساخته می‌شود؛
4. Permission grantهای Subject/Role evaluate می‌شوند؛
5. source مجاز وارد `authorizedSources` می‌شود؛
6. source غیرمجاز فقط یک safe decision می‌گیرد.

Source متعلق به Tenant دیگر exception است، نه drop عادی؛ این کار مانع پنهان شدن
Cross-Tenant bug در لیست ورودی می‌شود. Source فاقد Tenant scope نیز به دلیل نیاز
به `ContextSourceCandidate` رد می‌شود.

### 7.2 Context build

`buildAuthorizedContext()` دو permission مستقل می‌خواهد:

1. `AI_CONTEXT_BUILD` روی Request reference؛
2. `AI_CONTEXT_SOURCE_READ` برای هر source.

پس از آن فقط `authorizedSources` به `ContextEngine` J تحویل می‌شود. J دوباره
classification، external policy، redaction و budget را enforce می‌کند؛ K آن
invariantها را حذف یا جایگزین نمی‌کند.

### 7.3 External Provider

External Context یک permission مستقل به نام `AI_CONTEXT_EXPORT` دارد. داشتن
`AI_CONTEXT_BUILD` یا `AI_CONTEXT_SOURCE_READ` به‌تنهایی ارسال external را مجاز
نمی‌کند:

```text
build permission + source permission + export permission + J external policy
```

همهٔ این چهار boundary باید برای build external موفق باشند. K هیچ Providerی را
صدا نمی‌زند و فقط authorization decision می‌سازد.

### 7.4 Context read facade

`AuthorizedContextEngine` روی `ContextEngine` J قرار می‌گیرد و برای این عملیات
permission می‌خواهد:

- `getContext` → `AI_CONTEXT_READ` روی Context reference؛
- `getResult` → `AI_CONTEXT_READ`؛
- `describeContext` → `AI_CONTEXT_READ`؛
- `listContexts` → `AI_CONTEXT_READ` روی Context collection.

Tenant از Principal استخراج می‌شود و caller نمی‌تواند Tenant دیگری را به lookup
تزریق کند.

---

## 8. Typed Authorization Helpers

برای جلوگیری از ساخت Resourceهای نامتجانس در Application، این helperها وجود
دارند:

```text
authorizeContext(principal, contextId)
authorizeRequest(principal, requestId)
authorizeResponse(principal, responseId)
authorizePrompt(principal, promptId)
authorizeModel(principal, modelId)
authorizeProvider(principal, providerId)
authorizeCapability(principal, capabilityId)
authorizeEntity(principal, action, resourceType, resourceId)
authorizeTenant(principal, tenantId)
```

این helperها lookup واقعی یا mutation موجودیت انجام نمی‌دهند؛ فقط Decision تولید
می‌کنند. Default actionها از permission vocabulary K می‌آیند و caller می‌تواند
برای use case مشخص action صریح بدهد.

---

## 9. Exception Contract

| Exception | Code | کاربرد |
|---|---|---|
| `AIAuthorizationDenied` | `AI_AUTHORIZATION_DENIED` | permission صریح وجود ندارد یا deny فعال است |
| `AIAuthorizationPrincipalInvalid` | `AI_AUTHORIZATION_PRINCIPAL_INVALID` | Principal نامعتبر یا subject type/permission نادرست |
| `AIAuthorizationGrantInvalid` | `AI_AUTHORIZATION_GRANT_INVALID` | Grant/Resource selector نامعتبر |
| `AIAuthorizationPolicyInvalid` | `AI_AUTHORIZATION_POLICY_INVALID` | Policy، service یا integration contract نامعتبر |
| `AIAuthorizationTenantMismatch` | `AI_AUTHORIZATION_TENANT_MISMATCH` | Principal، Resource یا source متعلق به Tenant دیگر |
| `AIAuthorizationAlreadyRegistered` | `AI_AUTHORIZATION_ALREADY_REGISTERED` | duplicate Principal یا Grant |
| `AIAuthorizationNotFound` | `AI_AUTHORIZATION_NOT_FOUND` | Principal یا Grant در scope جاری پیدا نشد |

`AIAuthorizationDenied` از `AIPermissionDenied` ارث می‌برد تا Adapterهای قبلی
بتوانند همان permission boundary عمومی را consume کنند.

---

## 10. Persistence، Authentication و Concurrency

K یک policy evaluator خالص و registry in-memory است. این موارد عمداً ادعا نشده‌اند:

- احراز هویت و اثبات هویت Subject؛
- load کردن Role یا Membership از DB؛
- persistence grants؛
- audit event durable؛
- transaction برای grant mutation؛
- distributed consistency؛
- revoke propagation بین processها؛
- lock یا thread/process safety؛
- cache invalidation؛
- retention و privacy erasure.

Application/Identity در آینده باید Principal و Grant snapshot را از منبع مورداعتماد
بسازد. Infrastructure باید حداقل uniqueness، versioning، revoke، audit،
concurrency، cache invalidation و Tenant scoping را حفظ کند. K نباید با یک
in-memory allowlist به‌عنوان سیستم production authorization معرفی شود.

---

## 11. Purity و Dependency Rules

`authorizationService.py` فقط از Python standard library، Entity/Policy/Service
خالص J و exception/value objectهای Domain استفاده می‌کند. موارد زیر وارد K نشده‌اند:

```text
Django / ORM / DRF / HTTP / Network
Redis / Queue / Worker / Filesystem
OpenAI / Ollama / Azure / Anthropic / Vendor SDK
JWT / OAuth / Identity Provider / Secret Store
```

هیچ payload source، metadata حساس، API Key، Password، Token یا credential در
Decision، Descriptor، exception message یا registry key ذخیره نمی‌شود.

---

## 12. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/services/authorizationService.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13Authorization.py

docs/Phases/Phase13/Phase13-K.md
docs/Phases/Phase13/Phase13-K-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
AuthorizationPrincipal
AuthorizationResource
PermissionGrant
AuthorizationPolicy
AuthorizationDecision
PermissionFilterResult
AuthorizationService
AuthorizedContextEngine
```

APIهای Service:

```text
registerPrincipal / getPrincipal / describePrincipal / listPrincipals
registerGrant / getGrant / describeGrant / listGrants / revokeGrant
authorize / requirePermission / require / can / authorizeTenant
filterContextSources / filterSources
buildAuthorizedContext / buildContext
authorizeEntity / authorizeContext / authorizeRequest
```

Aliasها:

```text
PermissionService
PermissionEngine
AuthorizationEngine
AIAuthorizationService
TenantAuthorizationService
InMemoryAuthorizationService
PermissionFilteringService
Permission / PermissionRule
Principal / ResourceReference
AccessDecision / PermissionDecision
AuthorizationContext
PermissionAwareContextEngine
AIContextAuthorizationEngine
AuthorizedContextBuilder
```

---

## 13. Open Questions برای زیر‌فازهای بعدی

1. Application/Identity چگونه membership snapshot را version و به K تحویل دهد؟
2. Grant revocation و cache invalidation در معماری چند instance چگونه منتشر شود؟
3. آیا Role inheritance و deny policy باید در K اضافه شود یا در Identity boundary
   resolve و flatten شود؟
4. Permission audit در O چه correlation/trace identityای از Decision K مصرف کند؟
5. آیا هر resource type باید action vocabulary محدودتری از `PERMISSION_ACTIONS`
   داشته باشد؟
6. Classification clearance کاربر چگونه با `ContextPolicy` J و Provider policy L
   ترکیب شود؟
7. External export approval و dual-control برای `AI_CONTEXT_EXPORT` در O چگونه
   پیاده شود؟
8. آیا direct permission باید در production ممنوع و فقط snapshot امضاشدهٔ Identity
   پذیرفته شود؟
9. Permission check برای Request lifecycle G و Response H دقیقاً در کدام
   Application command قبل از mutation قرار گیرد؟
10. Retention و privacy deletion برای Decision fingerprintها و audit trail چگونه
    تعریف شود؟

---

## 14. Acceptance Criteria

- [x] AuthorizationService خالص و Tenant-aware در ساختار واقعی Tekarai ایجاد شد؛
- [x] Principal snapshot و Grant contract ایجاد شد؛
- [x] Resource reference بدون payload و secret طراحی شد؛
- [x] default deny enforce شد؛
- [x] explicit allow و explicit deny با deny precedence پیاده شد؛
- [x] exact و prefix wildcard permission matching پیاده شد؛
- [x] resource/source/classification/external selectors enforce شدند؛
- [x] Grant expiry و priority پشتیبانی شد؛
- [x] duplicate protection و snapshot isolation ایجاد شد؛
- [x] Tenant mismatch برای Principal/Resource/Source رد می‌شود؛
- [x] safe AuthorizationDecision و fingerprint ایجاد شد؛
- [x] Context source filtering پیش از Context assembly انجام می‌شود؛
- [x] source content در dropped decisionها expose نمی‌شود؛
- [x] Context build permission و source read permission جدا هستند؛
- [x] External Context export permission مستقل enforce می‌شود؛
- [x] AuthorizedContextEngine lookup/list را permission-aware می‌کند؛
- [x] typed authorization helperها برای AI resources وجود دارند؛
- [x] هیچ ORM/API/Network/Provider/Identity SDK/Secret dependency وارد K نشده است؛
- [x] Pure test و regression B تا K اجرا شد؛
- [x] محدودیت‌های محیط، persistence و concurrency ثبت شد؛
- [x] Documentation، Verification، Gate و ZIP مستقل آماده شد.

**نتیجه:** `GREEN — Phase 13-L may begin.`
