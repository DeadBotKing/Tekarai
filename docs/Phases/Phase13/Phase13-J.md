# Phase 13-J — Context Engine و Context Builder

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** J از A تا Z  
**وضعیت:** COMPLETED — Context Engine/Builder Gate GREEN  
**تاریخ قرارداد و اجرا:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-I.md`](Phase13-I.md)  
**گزارش اجرا:** [`Phase13-J-ExecutionReport.md`](Phase13-J-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز J مرز امن و deterministic بین منابع مجاز Tekarai و Context قابل مصرف
توسط AI را ایجاد می‌کند. هدف، ساخت یک Context کامل از همهٔ داده‌های در دسترس
نیست؛ هدف، ساخت **Least-Privilege Context** از منابعی است که caller قبلاً با
Tenant scope معتبر ارائه کرده و Builder قبل از assembly آن‌ها را authorization،
classification، external-provider و budget filter می‌کند.

J به این سؤال پاسخ می‌دهد:

> چگونه بدون ORM، Network، Provider SDK یا Secret Resolution، مجموعه‌ای از
> `ContextSource`های واقعی B را از source candidateهای Tenant-bound بسازیم،
> محتوای غیرمجاز را هرگز وارد Context نکنیم، محدودیت‌های policy را enforce کنیم
> و read model امنی برای lookup و traceability بدهیم؟

`ContextBuilder` pure و provider-agnostic است. `ContextEngine` یک registry
in-memory و Tenant-aware روی آن قرار می‌دهد. هیچ‌کدام منبع داده را fetch نمی‌کنند
و هیچ Providerی را اجرا نمی‌کنند.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- استفاده از Entity واقعی `AIContext` از B؛
- استفاده از Value Object واقعی `ContextSource` از B؛
- استفاده از `ContextPolicy` موجود B بدون شکستن قرارداد قبلی؛
- استفاده از `estimateTokens` موجود B برای token estimation؛
- تعریف `ContextSourceCandidate` به‌عنوان source wrapper دارای `tenantId` صریح؛
- ساخت pure و deterministic Context بر اساس ترتیب ورودی؛
- assemble کردن source content با separator ثابت؛
- Tenant isolation برای request، source، Context registration، lookup و listing؛
- رد sourceهای بدون Tenant scope معتبر یا sourceهای متعلق به Tenant دیگر؛
- authorization اولیهٔ source و permission predicate اختیاری؛
- classification filtering بر اساس `ContextPolicy.allowedClassifications`؛
- external-provider boundary بر اساس `allowExternalProvider`؛
- redaction محتوای `RESTRICTED` وقتی classification مجاز و `redactRestricted`
  فعال است؛
- حذف sourceهای empty، duplicate و خارج از source/character/token budget؛
- enforce کردن `maxSources`، `maxCharacters` و `maxTokens`؛
- ثبت exclusion reason بدون expose کردن متن source حذف‌شده؛
- حذف keyهای secret-like از source metadata قبل از ساخت `ContextSource`؛
- content fingerprint با SHA-256 بدون نگهداری fingerprint از متن در descriptor؛
- safe immutable `ContextSourceDescriptor` و `ContextDescriptor`؛
- `ContextBuildResult` شامل Context، source references، counts، classifications،
  redaction state و dropped-source reasons؛
- in-memory Context registration با duplicate protection؛
- Tenant-aware lookup با `getContext`، `getResult`، `describeContext`؛
- request-aware lookup با `latestForRequest` و `listContexts`؛
- deep-copy/snapshot isolation برای Context، source metadata و read model؛
- exception boundary اختصاصی J؛
- Pure Unit Test، regression، compile، purity، whitespace، documentation link،
  archive integrity و test روی Extract؛
- ثبت Scope، تصمیم‌های معماری، محدودیت‌ها، Verification، Gate و ZIP مستقل.

### 2.2 خارج از Scope

- ORM، Django Model، Repository یا Database persistence؛
- API، Serializer، View، Admin یا Permission endpoint؛
- واکشی داده از Project، Task، Document، HR، Knowledge یا Domain دیگر؛
- اتصال Network، HTTP، filesystem، queue، worker یا Redis؛
- Provider SDK، Model execution، prompt execution یا inference؛
- انتخاب Provider یا Model و routing نهایی؛
- persistence durable، transaction، distributed lock و unique database constraint؛
- ادعای thread-safety، multi-process safety یا concurrency control؛
- Secret Resolution، credential lookup یا ذخیرهٔ API Key؛
- تشخیص کامل PII، prompt injection، malware یا content safety؛
- جایگزینی authorization واقعی Application/K/O؛
- tokenization اختصاصی Provider؛ J فقط estimator سازگار با `aiRules.estimateTokens`
  را مصرف می‌کند؛
- truncation بخشی از source؛ source یا کامل وارد می‌شود یا به دلیل budget حذف
  می‌شود؛
- audit event، Usage، Cost و Latency record؛ این‌ها به N/O/W واگذار شده‌اند.

---

## 3. جایگاه معماری

```text
Domain/Application Adapter
        │
        │  Tenant-bound ContextSourceCandidate
        ▼
   ContextBuilder (J)
   ├─ tenant/source validation
   ├─ authorization / permission predicate
   ├─ classification policy
   ├─ external-provider boundary
   ├─ restricted redaction
   ├─ deduplication
   ├─ source/character/token budgets
   └─ safe descriptors + AIContext (B)
        │
        ▼
   ContextBuildResult
        │
        ▼
   ContextEngine (J)
   ├─ in-memory registration
   ├─ Tenant-aware lookup
   ├─ request-aware listing
   └─ deep-copy snapshots
        │
        ▼
Application / future Prompt and Provider orchestration
```

مالکیت مفاهیم:

| مفهوم | مالک |
|---|---|
| `AIContext` و `ContextSource` | B |
| `ContextPolicy` | B |
| Token estimation | `aiRules.py` از B |
| Tenant-bound source candidate | J |
| Context filtering و assembly | J |
| Context in-memory registry | J |
| Authorization واقعی و role/permission lookup | Application/K |
| Provider policy و actual transmission | L/K |
| Usage، Cost، Latency | N/W |
| Audit و Governance | O |
| Persistence و retention | زیر‌فازهای Application/Infrastructure آینده |

---

## 4. قرارداد ورودی و Tenant Scope

### 4.1 مشکل Entity موجود B

`ContextSource` در B شامل source identity، content، classification، allowed و
metadata است، اما `tenantId` ندارد. بنابراین J از روی یک `ContextSource` خام
نمی‌تواند مالکیت Tenant را حدس بزند. این رفتار عمداً ناامن است و Builder آن را
قبول نمی‌کند.

J wrapper زیر را فراهم می‌کند:

```python
candidate = ContextSourceCandidate(
    tenantId=tenantId,
    sourceDomain="projects",
    sourceEntityType="document",
    sourceEntityId="doc-123",
    content="authorized content",
    classification="INTERNAL",
    authorized=True,
    metadata={"title": "Project brief"},
)
```

`ContextSourceCandidate`:

- `tenantId` را به UUID normalize می‌کند؛
- source identity و content را validate می‌کند؛
- classification را با `DataClassification` normalize می‌کند؛
- metadata را deep-copy می‌کند؛
- `toEntity()` را فقط پس از filtering برای ساخت `ContextSource` استفاده می‌کند.

ورودی معتبر Builder باید `ContextSourceCandidate` باشد. موارد زیر رد می‌شوند:

- `ContextSource` خام؛
- object فاقد source identity؛
- classification ناشناخته؛
- candidate متعلق به Tenant دیگر؛
- tenantId یا requestId نامعتبر.

### 4.2 Permission Contract

J دو سطح pure دارد:

1. `authorized=False` روی candidate، که همیشه با reason برابر
   `NOT_AUTHORIZED` حذف می‌شود؛
2. `permissionFilter(candidate) -> bool` که caller می‌تواند برای نتیجهٔ
   authorization از K/Application فراهم کند.

اگر predicate مقدار false بدهد، source با reason `PERMISSION_FILTERED` حذف می‌شود.
اگر predicate exception بدهد، کل build با `AIContextPolicyInvalid` متوقف می‌شود؛
متن source یا exception provider به read model نشت نمی‌کند.

J ادعا نمی‌کند که خودش User، Role، ACL یا Policy Store را resolve می‌کند. وجود
predicate فقط یک boundary صریح و fail-closed برای ورودی مجاز است.

---

## 5. ContextPolicy و ترتیب فیلترها

`ContextPolicy` موجود B حفظ شده و فیلدهای آن contract J را تشکیل می‌دهند:

```python
ContextPolicy(
    allowedClassifications=("PUBLIC", "INTERNAL"),
    maxSources=50,
    maxCharacters=120_000,
    maxTokens=32_000,
    allowExternalProvider=False,
    redactRestricted=True,
)
```

برای هر source، Builder به ترتیب زیر عمل می‌کند:

1. type و Tenant scope را validate می‌کند؛
2. duplicate identity را حذف می‌کند؛
3. `authorized` را بررسی می‌کند؛
4. `permissionFilter` را اجرا می‌کند؛
5. classification و external-provider policy را می‌سنجد؛
6. empty content را حذف می‌کند؛
7. `maxSources` را enforce می‌کند؛
8. در صورت نیاز Restricted content را با marker ثابت redaction می‌کند؛
9. candidate content را با content قبلی assemble می‌کند؛
10. `maxCharacters` را روی متن assembled بررسی می‌کند؛
11. `estimateTokens` را روی همان متن assembled اجرا می‌کند؛
12. فقط در صورت عبور همهٔ مراحل، `ContextSource` واقعی و Context piece ساخته
    می‌شود.

بنابراین متن source غیرمجاز، duplicate، empty یا خارج از limit وارد `AIContext`
نمی‌شود. ترتیب ورودی deterministic است و source خارج از limit truncate نمی‌شود؛
کل source حذف می‌شود تا محتوای ناقص به‌صورت ناخواسته مصرف نشود.

---

## 6. Classification، External Provider و Restricted Redaction

### 6.1 Classification

`allowedClassifications` از `ContextPolicy` خوانده می‌شود. اگر classification
source در policy نباشد، source حذف و reason برابر `CLASSIFICATION_NOT_PERMITTED`
است.

### 6.2 External Provider

پارامتر `externalProvider` فقط یک policy boundary را فعال می‌کند؛ Builder به
هیچ Providerی متصل نیست:

```text
externalProvider=False → policy external boundary فعال نیست
externalProvider=True  + allowExternalProvider=False → همهٔ candidateها حذف
externalProvider=True  + allowExternalProvider=True  → classification policy ادامه دارد
```

در حالت blocked، reason برابر `EXTERNAL_PROVIDER_NOT_PERMITTED` است. این تصمیم
به معنی ارسال داده به Provider نیست و فقط به caller اعلام می‌کند که این Context
برای مرز external قابل استفاده نیست.

### 6.3 Restricted Redaction

اگر `RESTRICTED` در `allowedClassifications` باشد و `redactRestricted=True`،
متن source پیش از assembly با marker زیر جایگزین می‌شود:

```text
[REDACTED:RESTRICTED]
```

در این حالت:

- متن اصلی Restricted وارد Context نمی‌شود؛
- `AIContext.redacted=True` می‌شود؛
- descriptor فقط `wasRedacted=True` را برای source نشان می‌دهد؛
- budget روی متن redacted محاسبه می‌شود؛
- اگر Restricted در allowed classifications نباشد، source حذف می‌شود و redaction
  اتفاق نمی‌افتد.

J یک PII/Secret scanner عمومی نیست. محتوای source باید از boundary مجاز caller
آمده باشد و Secret Resolution خارج از Domain J است.

---

## 7. Deduplication و Budget Contract

### 7.1 Source identity

کلید deduplication این است:

```text
(sourceDomain, sourceEntityType, sourceEntityId)
```

اولین source در ترتیب ورودی winner است. duplicateهای بعدی حذف می‌شوند و فقط
reference امن و reason `DUPLICATE_SOURCE` در result می‌گیرند. متن duplicate در
descriptor یا exclusion reason قرار نمی‌گیرد.

### 7.2 Source limit

پس از عبور source از authorization و policy، تعداد sourceهای پذیرفته‌شده با
`maxSources` کنترل می‌شود. sourceهای بعدی با reason `MAX_SOURCES` حذف می‌شوند.

### 7.3 Character limit

متن assembled به شکل زیر ساخته می‌شود:

```text
source_1

source_2

source_3
```

`maxCharacters` شامل separatorها نیز هست. اگر اضافه شدن یک source limit را رد
کند، همان source حذف می‌شود و sourceهای قبلی حفظ می‌شوند.

### 7.4 Token limit

تخمین token با تابع موجود `estimateTokens` انجام می‌شود و دقیقاً روی candidate
assembled content اجرا می‌گردد. J tokenizer یا الگوریتم Provider-specific جدید
تعریف نمی‌کند. اگر candidate token limit را رد کند، source با reason
`MAX_TOKENS` حذف می‌شود.

### 7.5 Empty و all-dropped Context

Context می‌تواند بدون source و با `content=""` ساخته شود؛ این نتیجه failure
نیست. در این حالت descriptor count صفر و fingerprint متن خالی ثبت می‌شود. Source
غیرمجاز هرگز برای پر کردن Context جایگزین نمی‌شود.

---

## 8. خروجی‌ها و Safe Read Models

### 8.1 `ContextBuildResult`

```text
context          → AIContext واقعی B برای مصرف downstream
 descriptor       → ContextDescriptor امن و immutable
includedSources  → tuple از source decisionهای امن
excludedSources  → tuple از dropped-source decisionهای امن
tenantScoped     → provenance داخلی برای registration امن
```

خود `ContextBuildResult` برای caller شامل Context و در نتیجه متن Context است؛ این
متن همان payload مورد نیاز orchestration است. اما descriptor و source decisionها
محتوا و metadata را expose نمی‌کنند.

### 8.2 `ContextSourceDescriptor`

فیلدها:

- `sourceDomain`؛
- `sourceEntityType`؛
- `sourceEntityId`؛
- `classification`؛
- `included`؛
- `exclusionReason`؛
- `wasRedacted`.

فیلدهای عمداً غایب:

- source content؛
- raw metadata؛
- Secret، API Key، Password، Token یا credential؛
- exception text حاوی source data.

### 8.3 `ContextDescriptor`

فیلدها:

- Tenant، Request و Context UUID؛
- source count؛
- included source references؛
- excluded source count؛
- character و token count؛
- SHA-256 content fingerprint؛
- redaction state؛
- external-provider flag؛
- createdAt.

Descriptor متن Context، raw source content و metadata را expose نمی‌کند و با
`@dataclass(frozen=True)` immutable است. Fingerprint برای traceability است، نه
برای بازیابی متن.

### 8.4 Sensitive metadata

Candidate metadata پیش از ساخت Entity نهایی sanitize می‌شود. keyهای secret-like
از جمله موارد زیر حذف می‌شوند:

```text
api_key, apikey, password, secret, secret_key, token,
access_token, refresh_token, connection_string
```

mappingهای nested نیز recursively sanitize می‌شوند. این کار به معنی Secret
Resolution یا Secret storage نیست؛ هیچ credentialی تولید یا resolve نمی‌شود.

---

## 9. ContextEngine Contract

`ContextEngine` فقط حافظهٔ process جاری را مدیریت می‌کند:

```python
engine = ContextEngine(builder=builder)
result = engine.buildContext(tenantId, requestId, candidates, policy)
context = engine.getContext(tenantId, result.context.id)
descriptor = engine.describeContext(tenantId, result.context.id)
latest = engine.latestForRequest(tenantId, requestId)
items = engine.listContexts(tenantId, requestId=requestId)
```

رفتارها:

- registry با کلید `(tenantId, contextId)` کار می‌کند؛
- duplicate registration با `AIContextAlreadyRegistered` رد می‌شود؛
- lookup با Tenant اشتباه همانند not found رفتار می‌کند؛
- `getContext`، `getResult` و `describeContext` deep-copy برمی‌گردانند؛
- list فقط descriptorهای Tenant جاری را برمی‌گرداند؛
- `latestForRequest` فقط در همان Tenant جست‌وجو می‌کند؛
- `clear()` فقط helper مربوط به process/test in-memory است.

### 9.1 Registration موجود

چون `ContextSource` B فاقد `tenantId` است، `registerContext` فقط Contextی را که
source payload ندارد به‌صورت مستقیم می‌پذیرد. Context دارای source باید از
`buildContext` یا `registerResult` بیاید تا source candidate دارای Tenant scope
صریح باشد. این تصمیم از register شدن Contextی با source مالکیت‌ناشناخته جلوگیری
می‌کند.

`registerResult` فقط `ContextBuildResult`ای را می‌پذیرد که Builder J آن را با
`tenantScoped=True` تولید کرده باشد. این flag یک provenance داخلی Domain است و
به معنی persistence یا authorization جدید نیست.

---

## 10. Exception Contract

| Exception | Code | کاربرد |
|---|---|---|
| `AIContextSourceInvalid` | `AI_CONTEXT_SOURCE_INVALID` | source خام، identity/content/classification نامعتبر یا registration بدون source scope |
| `AIContextTenantMismatch` | `AI_CONTEXT_TENANT_MISMATCH` | candidate یا descriptor متعلق به Tenant دیگر |
| `AIContextPolicyInvalid` | `AI_CONTEXT_POLICY_INVALID` | policy، permission predicate یا assembly contract نامعتبر |
| `AIContextAlreadyRegistered` | `AI_CONTEXT_ALREADY_REGISTERED` | duplicate Context در registry جاری |
| `AIContextNotFound` | `AI_CONTEXT_NOT_FOUND` | lookup خارج از Tenant scope یا Context موجود نبود |
| `AIContextTooLarge` | `AI_CONTEXT_TOO_LARGE` | invariant نهایی Context از budget عبور کرده است |

رد source با reasonهای descriptor failure نیست و exception ایجاد نمی‌کند؛ مواردی
مثل authorization، classification، duplicate و budget به‌صورت safe drop ثبت
می‌شوند. خطای structural یا Tenant boundary exception است.

---

## 11. Persistence، Concurrency و Future Adapter

J عمداً in-memory و single-process است. این implementation موارد زیر را ادعا
نمی‌کند:

- durability پس از restart؛
- transaction؛
- unique constraint در Database؛
- lock یا distributed locking؛
- thread/process safety؛
- cross-instance latest ordering؛
- retention یا deletion policy.

Adapter آینده باید حداقل این invariantها را نگه دارد:

- Tenant همیشه بخشی از lookup و uniqueness باشد؛
- source قبل از persistence یا transmission Tenant-bound باشد؛
- permission/classification/external checks پیش از Context assembly باقی بمانند؛
- content fingerprint canonical و reproducible باشد؛
- source metadata secret-like حذف یا با policy امن مدیریت شود؛
- Context payload و safe descriptor از هم جدا بمانند؛
- registration idempotent و duplicate-aware باشد؛
- serialization و database schema متن را ناخواسته وارد audit/log descriptor نکند؛
- transaction و concurrency control در infrastructure واقعی اضافه شود؛
- retention، encryption، audit و provider policy در boundary مناسب اضافه شوند.

---

## 12. Purity و Dependency Rules

`contextEngine.py` فقط از Python standard library، Entity/Value Object/Policy و
exceptionهای Domain استفاده می‌کند. این موارد وارد J نشده‌اند:

```text
Django / ORM / REST / HTTP / Network
Redis / Queue / Worker / Filesystem
OpenAI / Ollama / Azure / Anthropic / boto3 / Vendor SDK
Secret Store / Credential Resolver / Database
```

Builder Provider-agnostic است و `externalProvider` فقط یک boolean policy input
است. هیچ Provider code یا API key در Context candidate، Context descriptor یا
registry تولید نمی‌شود.

---

## 13. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/services/contextEngine.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13ContextEngine.py

docs/Phases/Phase13/Phase13-J.md
docs/Phases/Phase13/Phase13-J-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
ContextSourceCandidate
AIContextSourceCandidate
TenantBoundContextSource
ContextSourceDescriptor
ContextDescriptor
ContextBuildResult
ContextBuilder
ContextEngine
```

APIهای Builder:

```text
build
```

APIهای Engine:

```text
buildContext
registerContext
registerResult
getContext
getResult
describeContext
latestForRequest
listContexts
clear
```

Aliasها:

```text
AIContextBuilder
AIContextEngine
ContextService
InMemoryContextEngine
ContextBuilderService
```

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. Application/K چگونه `permissionFilter` را با permission snapshot و audit
   correlation به Builder متصل می‌کند؟
2. آیا sourceهای `CONFIDENTIAL` و `RESTRICTED` برای هر Provider policy نیاز به
   redaction strategy متفاوت دارند؟
3. آیا marker redaction باید به policy version یا localization قابل تنظیم متصل
   شود؟
4. Token estimator سادهٔ B در L/N با tokenizer واقعی Provider چگونه جایگزین یا
   کالیبره می‌شود؟
5. آیا source limit باید بر اساس source type وزن‌دار یا priority-aware شود؟
6. آیا Context assembled باید immutable serialized snapshot در persistence آینده
   داشته باشد یا فقط reference و fingerprint ذخیره شود؟
7. retention متن Context و privacy erasure در O/W چگونه اعمال می‌شود؟
8. آیا `ContextBuildResult` باید correlation/trace identity اختصاصی برای Audit
   داشته باشد یا از `AIRequest` G استفاده کند؟
9. Prompt injection detection و PII scanner در K/O در کدام نقطهٔ قبل از Provider
   قرار می‌گیرند؟
10. در معماری multi-instance، latest Context برای Request با چه ordering و
    transaction guarantee ذخیره می‌شود؟

---

## 15. Acceptance Criteria

- [x] Context Builder pure و deterministic در ساختار واقعی Tekarai ایجاد شد؛
- [x] Entity واقعی `AIContext` و Value Object واقعی `ContextSource` از B مصرف شدند؛
- [x] `ContextPolicy` و `estimateTokens` موجود B حفظ و مصرف شدند؛
- [x] Tenant-bound `ContextSourceCandidate` ایجاد شد؛
- [x] source خام فاقد Tenant scope رد می‌شود؛
- [x] source متعلق به Tenant دیگر رد می‌شود؛
- [x] authorization و permission filtering پیش از assembly انجام می‌شود؛
- [x] classification policy enforce می‌شود؛
- [x] external-provider boundary enforce می‌شود؛
- [x] Restricted redaction با policy انجام می‌شود؛
- [x] duplicate، empty و sourceهای خارج از budget حذف می‌شوند؛
- [x] maxSources، maxCharacters و maxTokens enforce می‌شوند؛
- [x] token estimation با `aiRules.estimateTokens` سازگار است؛
- [x] dropped-source reasons بدون expose محتوای source ارائه می‌شوند؛
- [x] safe fingerprint و safe immutable descriptors ایجاد شدند؛
- [x] sensitive metadata keyها از Context source metadata حذف می‌شوند؛
- [x] in-memory Context registration و duplicate protection وجود دارد؛
- [x] lookup و listing Tenant-aware هستند؛
- [x] Context و source metadata snapshot isolation دارند؛
- [x] persistence، locking، concurrency و provider execution ادعا نشده‌اند؛
- [x] Pure tests، regression و verification اجرا شدند؛
- [x] محدودیت Django و نبود Ruff/mypy ثبت شد؛
- [x] Documentation، Gate و ZIP مستقل J آماده شد.

**نتیجه:** `GREEN — Phase 13-K may begin.`
