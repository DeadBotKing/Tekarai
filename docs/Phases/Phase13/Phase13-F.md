# Phase 13-F — Capability Registry

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** F از A تا Z  
**وضعیت:** COMPLETED — Capability Registry Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-E.md`](Phase13-E.md)  
**گزارش اجرا:** [`Phase13-F-ExecutionReport.md`](Phase13-F-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز F، Capability را به‌عنوان یک مفهوم مستقل از Provider و Model در یک
Registry tenant-aware قرار می‌دهد. `AICapability` از B تعریف business-level
Capability است؛ F آن را برای lifecycle، request-type policy، inspection و اتصال
کنترل‌شده به Model Routing قابل مصرف می‌کند.

F به این سؤال پاسخ می‌دهد:

> آیا Capability مشخص در Tenant فعال است، چه نوع Requestهایی را می‌پذیرد، و
> کدام Model فعال و tenant-owned آن Capability را اعلام می‌کند؟

F Provider جدیدی تعریف نمی‌کند و Adapter را نمی‌شناسد. برای انتخاب Model، فقط
از Contract عمومی `ModelRegistry` در E استفاده می‌کند و نتیجه را به شکل
`RoutingDecision` برمی‌گرداند.

قواعد اصلی:

- Capability Code در scope `(tenantId, capabilityCode)` یکتا است؛
- Capability یک Tenant به Tenant دیگر نشت نمی‌کند؛
- Capability inactive قابل Resolve عملیاتی، مدل‌یابی یا Routing نیست؛
- Request Type باید از Vocabulary B باشد؛
- Policy اختیاری `allowedRequestTypes` یک allowlist صریح است؛
- Capability از Provider مستقل است؛
- Model پشتیبان Capability باید Model فعال و Provider فعال داشته باشد؛
- Descriptor و Registration هیچ Policy metadata حساس یا Secret را expose نمی‌کنند؛
- F عملیات Provider، Persistence، API، Queue، Retry یا Failover انجام نمی‌دهد.

---

## 2. Scope و Non-Scope

### داخل Scope

- `CapabilityRegistry` در `apps/ai/domain/registries/capabilityRegistry.py`؛
- اتصال به Entity `AICapability` از B؛
- Register، Lookup، Resolve، Describe، List و Unregister؛
- Duplicate protection و Replace صریح؛
- Tenant Isolation؛
- Activation و Deactivation؛
- پشتیبانی از Capabilityهای استاندارد و `CUSTOM_*`؛
- Request Type allowlist برای Capability؛
- Capability Descriptor غیرحساس و Immutable؛
- بررسی اینکه Model، Capability را اعلام کرده است؛
- Listing Modelهای مناسب یک Capability از Model Registry E؛
- Capability-first Routing با `CapabilityRoutingRequest`؛
- استفاده از Preferred/Default/Fallback Policy موجود در E، بدون اجرای Failover؛
- خطاهای Domain-specific برای Capability؛
- Pure Unit Test و Purity Scan؛
- ثبت تصمیم‌ها، تست‌ها و محدودیت‌ها در Documentation.

### خارج از Scope

- Capability Persistence، ORM، Migration و Database Constraint؛
- API، Serializer، Admin و Permission Endpoint؛
- Provider Adapter و Network؛
- Vendor SDK یا Vendor-specific Capability؛
- اجرای Generate، Embedding، Tool یا هر عملیات مدل؛
- Retry، Timeout، Circuit Breaker، Queue و Failover واقعی؛
- محاسبه Cost، Latency و Quality؛
- Authorization واقعی User/Role؛ این مورد به K و Application Layer واگذار است؛
- Capability Registry جهانی خارج از Tenant؛
- تغییر Schema یا تغییر ساختار `AICapability` و `AIModel` در Database.

---

## 3. جایگاه معماری

```text
AICapability (B)
       │ tenantId + capabilityCode + policy
       ▼
┌──────────────────────────────────────────────┐
│ CapabilityRegistry (F)                       │
│ key = (tenantId, capabilityCode)             │
│ lifecycle + request-type policy              │
└──────────────────────┬───────────────────────┘
                       │ capabilityCode
                       ▼
             ModelRegistry (E)
                       │ active model/provider
                       ▼
                RoutingDecision
```

مرز مالکیت:

| مفهوم | مالک |
|---|---|
| Capability Definition و Lifecycle | Capability Registry در F |
| Provider Definition و Adapter | Provider Registry در D |
| Model Definition و Model Routing | Model Registry در E |
| User/Role Permission | Application و K |
| Persistence و Audit واقعی | زیر‌فازهای بعدی |

F از Model Registry برای integration استفاده می‌کند، اما Model یا Provider را
دوباره در Capability Registry کپی نمی‌کند.

---

## 4. Capability Registration Contract

### 4.1 کلید یکتا

کلید Registry به شکل زیر است:

```text
(tenantId UUID, capabilityCode UPPERCASE)
```

بنابراین:

- دو Tenant می‌توانند Capability Code یکسان داشته باشند؛
- یک Tenant نمی‌تواند Code را دوباره ثبت کند مگر با `replace=True`؛
- Provider و Model در uniqueness Capability دخالت ندارند؛
- Capability با Code خارج از Tenant قابل Lookup نیست.

### 4.2 Definition

ورودی باید یک `AICapability` معتبر از B باشد. Invariantهای B همچنان برقرارند:

- Tenant و ID باید UUID باشند؛
- Code باید Grammar دامنه را رعایت کند؛
- Code باید استاندارد یا `CUSTOM_*` باشد؛
- Name غیرخالی باشد؛
- `isActive` lifecycle عملیاتی را کنترل کند.

### 4.3 Replace و Registration Atomicity

رفتار پیش‌فرض امن است:

```text
register(existing tenant/code)            → AICapabilityAlreadyRegistered
register(new definition, replace=True)    → binding جدید
```

Policy قبل از تغییر Registry validate می‌شود؛ اگر Policy نامعتبر باشد Registry
تغییر نمی‌کند. Atomicity توزیع‌شده و Database transaction در F ادعا نمی‌شود.

---

## 5. Request Type Policy

در B، `AICapability.accepts(requestType)` برای Capability فعال، Request Type
شناخته‌شده را می‌پذیرد. F یک policy اختیاری و صریح از داخل `AICapability.policy`
پشتیبانی می‌کند:

```python
AICapability(
    tenantId=tenantId,
    code="DOCUMENT_ANALYSIS",
    name="Document analysis",
    policy={"allowedRequestTypes": ("ASK", "EXTRACT")},
)
```

قواعد:

1. اگر `allowedRequestTypes` در Policy وجود نداشته باشد، تمام `REQUEST_TYPES`
   معتبر B به‌صورت سازگار با B قابل استفاده‌اند؛
2. اگر Key وجود داشته باشد، فقط اعضای همان allowlist پذیرفته می‌شوند؛
3. Tuple خالی یعنی هیچ Request Typeای مجاز نیست؛
4. مقدار String منفرد، `None` یا Request Type ناشناخته رد می‌شود؛
5. مقدارها normalize و Unique می‌شوند؛
6. Policy در Registration cache نمی‌شود و تغییرات Policy درون‌پردازشی به‌صورت
   live خوانده می‌شوند تا allowlist stale باعث bypass نشود؛
7. فعال‌بودن Capability قبل از بررسی Request Type الزامی است.

APIها:

| API | رفتار |
|---|---|
| `supportsRequestType(...)` | Boolean برای Capability موجود؛ Unknown Request Type خطا است |
| `acceptsRequestType(...)` | Alias همان Boolean |
| `resolveForRequest(...)` | Capability فعال و Request Type مجاز را برمی‌گرداند |

برای Capability inactive، `resolveForRequest` خطای `AICapabilityInactive` می‌دهد
و Predicate مقدار False برمی‌گرداند.

---

## 6. Descriptor و Security Boundary

### 6.1 `CapabilityRegistration`

Registration شامل Entity، زمان Register و Propertyهای Tenant/Code است. Entity با
`repr=False` نگهداری می‌شود تا Policy و metadata داخلی در log ناخواسته چاپ نشود.

### 6.2 `CapabilityDescriptor`

Descriptor `frozen` و غیرحساس است و شامل این موارد می‌شود:

- `tenantId`؛
- `capabilityId`؛
- `code`، `name` و `description`؛
- `isActive`؛
- `supportedRequestTypes`؛
- `registeredAt`.

این موارد عمداً expose نمی‌شوند:

- کل `AICapability.policy`؛
- Internal marker یا arbitrary metadata؛
- Secret، Token، Password، API Key یا Connection String؛
- Model Registry object؛
- Provider Adapter یا Provider configuration.

`CapabilityRoutingRequest` نیز فقط Constraint و Code دارد و محتوای Prompt یا
Secret حمل نمی‌کند.

---

## 7. Capability-to-Model Integration

### 7.1 مدل اعلام‌کنندهٔ Capability

`AIModel.inputCapability` و `outputCapability` از B مرجع Declaration هستند. F
Mapping جداگانه‌ای را در یک جدول یا Cache دوم ایجاد نمی‌کند.

مطابق Contract B/E:

- اگر `inputCapability` خالی باشد، مدل Capability را unrestricted/unspecified
  تلقی می‌کند و `supportsCapability` فعلی B حفظ می‌شود؛
- اگر Input Capability پر باشد، Code باید در Input یا Output وجود داشته باشد؛
- Model باید در همان Tenant باشد؛
- برای Listing عملیاتی، Model و Provider هر دو باید active باشند؛
- Provider ownership توسط Model Registry E کنترل می‌شود.

### 7.2 `listModelsForCapability`

این API ابتدا Capability active و Request Type اختیاری را validate می‌کند، سپس
از `ModelRegistry.listModels(tenantId, activeOnly=...)` استفاده می‌کند و فقط
Descriptorهای مدل سازگار را برمی‌گرداند.

```python
capabilityRegistry.listModelsForCapability(
    tenantId,
    "SUMMARIZATION",
    requestType="SUMMARIZE",
)
```

اگر Model Registry به‌صورت Constructor به F داده نشده باشد، می‌تواند به‌صورت
Explicit به API داده شود. نبود آن `AICapabilityRegistrationInvalid` است؛ F
خودش Model Registry جداگانه نمی‌سازد.

### 7.3 `modelSupportsCapability`

این API بعد از Resolve Capability فعال، Tenant و active بودن Model را بررسی
می‌کند و نتیجهٔ Boolean می‌دهد. ورودی Model می‌تواند `AIModel` یا
`ModelDescriptor` باشد. Object نامعتبر با `AICapabilityModelNotSupported` رد
می‌شود.

این API Permission User/Role را جعل نمی‌کند؛ Boolean آن فقط Declaration و
lifecycle Registry را پوشش می‌دهد.

---

## 8. Capability-first Routing

### 8.1 `CapabilityRoutingRequest`

Request ترکیبی F شامل این موارد است:

- `tenantId` الزامی؛
- `capabilityCode` الزامی؛
- `requestType` اختیاری؛
- Constraintهای E برای Model Type، Provider Feature، Streaming، Tools، Vision،
  Embeddings و Context Window.

F آن را به `ModelRoutingRequest` تبدیل می‌کند و Capability را قبل از Routing
Resolve می‌کند.

### 8.2 ترتیب پردازش

```text
Tenant Validation
       ↓
Capability Lookup
       ↓
Capability Active Check
       ↓
Request Type Policy Check
       ↓
ModelRegistry Eligibility
       ↓
E Routing Policy
       ↓
RoutingDecision
```

اگر Capability فعال باشد اما هیچ Model فعال و سازگاری وجود نداشته باشد،
`AICapabilityRoutingNoMatch` تولید می‌شود. این خطا زیرمجموعهٔ معنایی خطای Routing
است و شکست انتخاب را از اجرای Provider جدا نگه می‌دارد.

### 8.3 Fallback

F از همان `ModelRoutingPolicy` در E استفاده می‌کند. `allowFallback` فقط اجازهٔ
بررسی Candidateهای بعدی را می‌دهد. F هیچ call، Retry، Failover یا Network
execution انجام نمی‌دهد.

---

## 9. Error Contract

| خطا | Code | HTTP advisory | کاربرد |
|---|---|---:|---|
| `AICapabilityAlreadyRegistered` | `AI_CAPABILITY_ALREADY_REGISTERED` | 409 | Duplicate Tenant/Code |
| `AICapabilityNotRegistered` | `AI_CAPABILITY_NOT_REGISTERED` | 404 | Capability خارج از Scope |
| `AICapabilityInactive` | `AI_CAPABILITY_INACTIVE` | 503 | Capability Operational نیست |
| `AICapabilityRegistrationInvalid` | `AI_CAPABILITY_REGISTRATION_INVALID` | 422 | Definition/Dependency نامعتبر |
| `AICapabilityPolicyInvalid` | `AI_CAPABILITY_POLICY_INVALID` | 422 | Policy یا Request Type نامعتبر |
| `AICapabilityRequestTypeUnsupported` | `AI_CAPABILITY_REQUEST_TYPE_UNSUPPORTED` | 422 | Request Type در allowlist نیست |
| `AICapabilityModelNotSupported` | `AI_CAPABILITY_MODEL_NOT_SUPPORTED` | 422 | Model از نوع/Scope درست نیست |
| `AICapabilityRoutingNoMatch` | `AI_CAPABILITY_ROUTING_NO_MATCH` | 422 | Model فعال و سازگار وجود ندارد |

همهٔ خطاها Domain-level هستند و Exception Provider یا Framework از مرز F عبور
نمی‌کند.

---

## 10. Tenant Isolation

- همهٔ Capability Lookupها `tenantId` دارند؛
- Key فقط `(tenantId, code)` است؛
- List برای Tenant دیگر tuple خالی می‌دهد؛
- Resolve Tenant دیگر `AICapabilityNotRegistered` می‌دهد؛
- Model Listing از Model Registry همان Tenant انجام می‌شود؛
- Model متعلق به Tenant دیگر در `modelSupportsCapability` False است؛
- Routing بدون Capability/Model همان Tenant هیچ Candidateای ندارد؛
- Capability Code به‌تنهایی در Registry معتبر نیست.

Permission واقعی کاربر در F انجام نشده و به زیر‌فاز K/Application واگذار است؛
Tenant Isolation با Authorization کامل یکی نیست.

---

## 11. Persistence و آینده

پیاده‌سازی F in-memory است. Repository آینده باید حداقل این Contractها را حفظ
کند:

- Unique `(tenantId, capabilityCode)`؛
- Transaction برای Replace/Activation؛
- Policy validation پیش از write؛
- عدم خروج Policy و metadata حساس از Read Model؛
- Audit تغییرات در O؛
- Authorization در K/Application؛
- Cache invalidation و concurrency control در مراحل زیرساختی.

F هیچ Database، Migration یا Persistence abstraction ناقصی اضافه نمی‌کند.

---

## 12. فایل‌های پیاده‌سازی

```text
backend/apps/ai/domain/registries/capabilityRegistry.py
backend/apps/ai/domain/registries/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13CapabilityRegistry.py

docs/Phases/Phase13/Phase13-F.md
docs/Phases/Phase13/Phase13-F-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

هیچ فایل Provider، ORM، API، Queue یا Secret Store در F ایجاد نشده است.

---

## 13. Acceptance Criteria

- [x] Capability Registry در ساختار واقعی Tekarai ساخته شد؛
- [x] `AICapability` از B به Registry متصل شد؛
- [x] Unique `(tenantId, capabilityCode)` enforce شد؛
- [x] Duplicate و Replace صریح پیاده شد؛
- [x] Tenant Isolation در Register/Lookup/List/Route برقرار است؛
- [x] Capability Activation و Deactivation وجود دارد؛
- [x] Request Type allowlist و validation پیاده شد؛
- [x] Capabilityهای استاندارد و `CUSTOM_*` پشتیبانی می‌شوند؛
- [x] Descriptor غیرحساس و Immutable است؛
- [x] Model Declaration و active Model/Provider در Integration بررسی می‌شوند؛
- [x] Capability-first Routing به E متصل شد؛
- [x] Routing No Match خطای مستقل و قابل تشخیص دارد؛
- [x] Fallback فقط Policy selection است و Failover واقعی نیست؛
- [x] هیچ Vendor/Framework/Network import در Domain F وجود ندارد؛
- [x] تست Tenant Isolation، Duplicate، Activation، Policy، Model و Routing وجود دارد؛
- [x] Documentation و Execution Report ثبت شده‌اند؛
- [x] ZIP مستقل F با Checksum ساخته می‌شود.

**نتیجه:** `GREEN — Phase 13-G may begin.`
