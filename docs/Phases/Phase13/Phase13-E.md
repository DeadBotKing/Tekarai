# Phase 13-E — Model Registry و Model Routing

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** E از A تا Z  
**وضعیت:** COMPLETED — Model Registry و Routing Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-D.md`](Phase13-D.md)  
**گزارش اجرا:** [`Phase13-E-ExecutionReport.md`](Phase13-E-ExecutionReport.md)

---

## 1. هدف و مرز E

زیر‌فاز E، `AIModel` دامنهٔ B را به `ProviderRegistry` زیر‌فاز D متصل می‌کند و
دو مرز pure و tenant-aware می‌سازد:

1. **Model Registry:** ثبت، Lookup، Activation، Descriptor و Unregister مدل‌ها؛
2. **Model Routing:** انتخاب deterministic و provider-agnostic یک مدل عملیاتی بر
   اساس Constraintها و Policy صریح.

E به این سؤال پاسخ می‌دهد:

> در Tenant مشخص، کدام Model از کدام Provider مالک آن است، فعال و قابل استفاده
> است، و با توجه به Type، Capability، Feature و Policy کدام گزینه باید انتخاب شود؟

E اجرای Provider را انجام نمی‌دهد. خروجی Routing فقط یک `RoutingDecision` قابل
ردیابی است که Application Service در مراحل بعدی می‌تواند آن را به Port/Adapter
تحویل دهد.

اصول الزام‌آور:

- Tenant هرگز از Lookup حذف نمی‌شود؛
- `AIModel.providerId` باید به Provider همان Tenant تعلق داشته باشد؛
- Model Code در scope ترکیبی `(tenantId, providerId, modelCode)` یکتا است؛
- Model و Provider غیرفعال Operational Resolve یا Route نمی‌شوند؛
- هیچ نام یا SDK مربوط به Vendor خاص در Core/Domain وارد نمی‌شود؛
- Descriptor و Decision فقط Metadata غیرحساس دارند؛
- Fallback در E فقط ترتیب Policy برای انتخاب است، نه Retry، Failover یا اجرای
  مجدد درخواست.

---

## 2. Scope و Non-Scope

### داخل Scope

- `ModelRegistry` در `apps/ai/domain/registries/modelRegistry.py`؛
- اتصال مستقیم به Entity `AIModel` از B؛
- استفاده از `ProviderRegistry` و `ProviderCapabilities` از D/C؛
- Register با Provider Ownership Validation؛
- Duplicate Protection و Replace صریح؛
- Tenant-aware Lookup و Listing؛
- Resolve مدل مشخص و Resolve مدل با Code یکتا؛
- Model Active/Inactive lifecycle؛
- Provider Active/Inactive enforcement؛
- Model Descriptor غیرحساس و Immutable؛
- Model Type، Business Capability و Provider Feature Contract؛
- بررسی Streaming، Tools، Vision، Embedding و Context Window؛
- Preferred، Default و Ordered Fallback Policy؛
- Deterministic Routing و Decision Result؛
- تست‌های Pure و Offline؛
- ثبت خطا، تصمیم معماری و Verification.

### خارج از Scope

- Database، ORM، Migration و Persistence Repository؛
- API، Serializer، Admin UI و Permission Endpoint؛
- Provider Adapter واقعی یا Network؛
- Secret Resolution، Vault و API Key؛
- اجرای `generate`، `embed` یا هر عملیات Provider؛
- Retry، Timeout، Circuit Breaker، Failover و Queue؛
- Load Balancing؛
- انتخاب بر اساس Cost، Latency یا Quality؛ این موارد به Scopeهای بعدی Usage,
  Observability و Governance واگذار می‌شوند؛
- Capability Registry مستقل زیر‌فاز F؛ E فقط Capability و Feature موجود در
  Contract مدل/Provider را بررسی می‌کند.

---

## 3. جایگاه در معماری

```text
AIModel (B)
    │ tenantId + providerId + modelCode
    ▼
┌──────────────────────────────────────────────────┐
│ ModelRegistry (E)                                │
│ key = (tenantId, providerId, modelCode)          │
│ ownership + activation + deterministic routing  │
└──────────────────┬───────────────────────────────┘
                   │ providerCode
                   ▼
┌──────────────────────────────────────────────────┐
│ ProviderRegistry (D)                             │
│ key = (tenantId, providerCode)                   │
│ Provider definition + Port adapter + capabilities│
└──────────────────┬───────────────────────────────┘
                   │ فقط برای capability handshake
                   ▼
          ProviderCapabilities (C)

ModelRoutingRequest + ModelRoutingPolicy
                   │
                   ▼
         RoutingDecision (non-sensitive)
```

`ModelRegistry` مالک Provider نیست و Adapter را در Registration مدل نگه‌داری
نمی‌کند. `ProviderRegistry` مرجع مالکیت Provider و Adapter Runtime باقی می‌ماند.

---

## 4. Model Registration Contract

### 4.1 کلید یکتا

کلید داخلی Registry به شکل زیر است:

```text
(tenantId UUID, providerId UUID, modelCode UPPERCASE)
```

این انتخاب هم‌زمان سه قاعده را enforce می‌کند:

- Tenantها از یکدیگر جدا هستند؛
- یک Provider می‌تواند چند Model داشته باشد؛
- یک Model Code می‌تواند در دو Provider متفاوتِ یک Tenant وجود داشته باشد.

چون `AIModel.code` در B با `validateCode` normalize می‌شود، Code در Registry
uppercase و محدود به الگوی Code دامنه است.

### 4.2 Provider Ownership

`registerModel(model, providerCode)` این موارد را بررسی می‌کند:

1. ورودی از نوع `AIModel` باشد؛
2. `model.tenantId` UUID معتبر باشد؛
3. Provider با `providerCode` در همان Tenant در D ثبت شده باشد؛
4. `model.providerId == providerRegistration.provider.id` باشد؛
5. Model Code معتبر باشد؛
6. Duplicate فقط با `replace=True` جایگزین شود؛
7. هیچ metadata یا configuration به Descriptor منتقل نشود.

`providerCode` اختیاری است فقط برای Composition Rootای که بتواند از روی
`model.providerId` دقیقاً یک Provider متعلق به همان Tenant پیدا کند. اگر مالکیت
صریحاً قابل اثبات نباشد، ثبت رد می‌شود. Registry Provider غیرفعال را برای
مدیریت می‌تواند بپذیرد، اما چنین Modelی Operational قابل Resolve/Route نیست.

### 4.3 Replace

رفتار پیش‌فرض امن است:

```text
register(existing key)              → AIModelAlreadyRegistered
register(new model, replace=True)   → binding جدید
```

Replace silent وجود ندارد. Replace، Persistence یا Audit ایجاد نمی‌کند؛ این‌ها در
لایه‌های بعدی تعریف خواهند شد.

---

## 5. Registration و Descriptor

### 5.1 `ModelRegistration`

Registration شامل این موارد است:

- `AIModel` دامنه؛
- `providerCode` نرمال‌شده؛
- `registeredAt`؛
- Propertyهای tenant/model/provider؛
- متد `descriptor(providerIsActive=...)`.

Adapter Provider در آن ذخیره یا expose نمی‌شود. خود `model` با `repr=False` نگه
داشته می‌شود تا logging ناخواسته metadata مدل را چاپ نکند.

### 5.2 `ModelDescriptor`

Descriptor خروجی غیرحساس و `frozen` است و فقط شامل موارد زیر می‌شود:

- `tenantId`؛
- `modelId`؛
- `providerId` و `providerCode`؛
- `code`، `name`، `modelType` و `version`؛
- `contextWindow`؛
- Input/Output Capability codeها؛
- flagهای Streaming، Tools، Embeddings و Vision؛
- `isActive` و `providerIsActive`؛
- `registeredAt`.

این موارد عمداً در Descriptor نیستند:

- `AIProvider` یا Adapter object؛
- `configurationReference`؛
- `AIModel.metadata`؛
- Token Rate و Cost metadata؛
- Secret، API Key، Password، Token، Connection String یا Payload Provider.

### 5.3 APIهای Registry

| API | رفتار |
|---|---|
| `registerModel(model, providerCode, replace=False)` | اعتبارسنجی مالکیت و ثبت Binding |
| `register(...)` | Alias Composition Root |
| `getRegistration(tenantId, providerCode, modelCode)` | Lookup مدیریتی؛ Inactive را به‌صورت پیش‌فرض هم می‌بیند |
| `resolveModel(tenantId, providerCode, modelCode)` | فقط Model فعال با Provider فعال و مالکیت معتبر |
| `resolveRegistration(...)` | Registration عملیاتی همان Resolve |
| `resolveModelByCode(tenantId, modelCode, providerCode=None)` | بدون Provider فقط اگر Code در Tenant مبهم نباشد |
| `describeModel(...)` | Descriptor غیرحساس و Immutable |
| `listModels(tenantId, activeOnly=True)` | فقط همان Tenant؛ Active بودن Model و Provider در حالت پیش‌فرض الزامی است |
| `activateModel` / `deactivateModel` | تغییر lifecycle درون‌پردازشی؛ Provider را تغییر نمی‌دهد |
| `unregisterModel` / `unregister` | حذف Binding از Registry in-memory |
| `clear()` | فقط Test/Composition Root؛ بدون ادعای حذف Database |

`resolveModel(tenant, model, provider)` نیز به‌صورت تحمل‌پذیر برای ترتیب معادل
پارامترهای positional پشتیبانی می‌شود، اما قرارداد مستند و اصلی Provider-first
است: `resolveModel(tenantId, providerCode, modelCode)`.

---

## 6. Operational Activation Rules

| وضعیت Model | وضعیت Provider | `getRegistration` | `resolveModel` | `listModels(activeOnly=True)` | Routing |
|---|---|---|---|---|---|
| active | active | مجاز | مجاز | شامل | Candidate |
| inactive | active | برای مدیریت مجاز | `AIModelInactive` | حذف | حذف |
| active | inactive | برای مدیریت مجاز | `AIProviderInactive` | حذف | حذف |
| inactive | inactive | برای مدیریت مجاز | Model inactive | حذف | حذف |
| active | unregistered/replaced | رکورد مدیریتی حفظ می‌شود | Ownership error | حذف | حذف |

این تفکیک از این جلوگیری می‌کند که یک رکورد مدیریتی inactive یا orphan به‌صورت
تصادفی برای اجرای AI مصرف شود.

---

## 7. Routing Contract

### 7.1 `ModelRoutingRequest`

درخواست Routing فقط Constraint دارد و به Vendor یا Adapter وابسته نیست:

- `tenantId` الزامی؛
- `modelType` اختیاری و Extensible؛
- `capabilityCode` اختیاری و از Capabilityهای کنترل‌شده یا `CUSTOM_`؛
- `requiredFeatures` از `MODEL_FEATURES` در Port C؛
- `requiresStreaming`؛
- `requiresTools`؛
- `requiresVision`؛
- `requiresEmbeddings`؛
- `minimumContextWindow`.

### 7.2 Eligibility

برای هر Candidate به ترتیب قواعد زیر بررسی می‌شود:

1. مدل و Provider متعلق به Tenant درخواست باشند؛
2. هر دو active باشند؛
3. Provider binding هنوز با `model.providerId` منطبق باشد؛
4. `modelType` منطبق باشد؛
5. `capabilityCode` با Capabilityهای Model سازگار باشد؛
6. Model Context Window از سقف اعلام‌شدهٔ Provider بزرگ‌تر نباشد؛
7. Model Context Window حداقل درخواست را پوشش دهد و اگر Provider سقف Context
   اعلام کرده، آن سقف نیز برای درخواست کافی باشد؛
8. Streaming/Tools/Vision/Embedding هم در flag مدل و هم در Feature handshake
   Provider، هرجا Contract آن را تعریف کرده، پشتیبانی شوند؛
9. Featureهای درخواستی Provider در `ProviderCapabilities` موجود باشند؛
10. برای Model Type `EMBEDDING`، Model باید Embedding را پشتیبانی کند و Provider
    باید `EMBEDDING` را advertise کند؛
11. برای Model Typeهای تولیدی مانند `LLM`، Provider باید `GENERATION` را
    advertise کند.

E از Cost، Latency، Health call یا Provider execution برای Eligibility استفاده
نمی‌کند. Health/Availability Runtime در D و مراحل بعدی جداست؛ در E وضعیت
صریح `isActive` معیار است.

### 7.3 مرتب‌سازی Deterministic

Candidateهای eligible همیشه با این کلید مرتب می‌شوند:

```text
(providerCode, modelCode, modelType, modelId)
```

`registeredAt` یا iteration order Dictionary در انتخاب دخالت ندارد. بنابراین
برای Registry state یکسان، نتیجه مستقل از ترتیب Register است.

---

## 8. Preferred، Default و Fallback Policy

`ModelRoutingPolicy` شامل موارد زیر است:

- `preferredProviderCode` و/یا `preferredModelCode`؛
- `defaultProviderCode` و/یا `defaultModelCode`؛
- `fallbackTargets` به شکل ordered `ModelRouteTarget`؛
- شکل فشردهٔ `fallbackModelCodes` و `fallbackProviderCodes`؛
- `allowFallback` یا Alias آن `fallbackEnabled`.

### ترتیب انتخاب

1. اگر Preferred تعریف شده و eligible باشد، همان انتخاب می‌شود؛
2. اگر Preferred تعریف شده ولی eligible نباشد و Fallback خاموش باشد، تصمیم رد
   می‌شود؛ سیستم سراغ مدل دلخواه دیگر نمی‌رود؛
3. اگر Fallback روشن باشد، `fallbackTargets` و سپس لیست‌های فشرده دقیقاً به‌ترتیب
   تعریف‌شده بررسی می‌شوند؛
4. پس از Fallbackهای صریح، Default بررسی می‌شود؛
5. اگر Target صریحی وجود نداشته باشد، اولین Candidate بر اساس مرتب‌سازی ثابت
   به‌عنوان `deterministic-default` انتخاب می‌شود؛
6. در Fallback روشن، اگر Targetهای صریح match نشوند، اولین Candidate ثابت با
   دلیل `fallback-deterministic` انتخاب می‌شود.

`RoutingDecision` حداقل این داده‌های غیرحساس را برمی‌گرداند:

- Tenant؛
- Provider ID و Code؛
- Model ID، Code و Type؛
- `reason`؛
- `usedFallback`؛
- `rank`؛
- Descriptor.

Reasonهای فعلی:

```text
preferred
fallback
default
deterministic-default
fallback-deterministic
```

این Decision فقط تصمیم است. E هیچ `generate`، `embed`، Retry، Failover، Queue،
Network یا Side Effect انجام نمی‌دهد.

---

## 9. Error Contract

| خطا | Code | HTTP advisory | کاربرد |
|---|---|---:|---|
| `AIModelAlreadyRegistered` | `AI_MODEL_ALREADY_REGISTERED` | 409 | Duplicate در Tenant/Provider/Code |
| `AIModelNotRegistered` | `AI_MODEL_NOT_REGISTERED` | 404 | Model خارج از Lookup scope |
| `AIModelInactive` | `AI_MODEL_INACTIVE` | 503 | Model برای مصرف عملیاتی فعال نیست |
| `AIModelRegistrationInvalid` | `AI_MODEL_REGISTRATION_INVALID` | 422 | Definition/Policy/Code نامعتبر |
| `AIModelProviderOwnershipInvalid` | `AI_MODEL_PROVIDER_OWNERSHIP_INVALID` | 422 | `providerId` به Provider صحیح Tenant تعلق ندارد |
| `AIModelAmbiguous` | `AI_MODEL_AMBIGUOUS` | 409 | Resolve با Code تنها، در چند Provider تکراری است |
| `AIProviderInactive` | `AI_PROVIDER_INACTIVE` | 503 | Provider مالک inactive است |
| `AIRoutingPolicyInvalid` | `AI_ROUTING_POLICY_INVALID` | 422 | Request/Policy/Feature نامعتبر است |
| `AIRoutingNoMatch` | `AI_ROUTING_NO_MATCH` | 422 | Candidate فعال و واجد شرایطی وجود ندارد |

تمام خطاها در Domain با Exceptionهای پایدار Tekarai تعریف شده‌اند. Exception
خام Adapter یا SDK در E وجود ندارد.

---

## 10. Tenant Isolation و Security Boundary

- تمام Registry APIهای Lookup یک `tenantId` می‌گیرند؛
- Model Code به‌تنهایی برای Registry key کافی نیست؛
- Listing فقط Descriptorهای همان Tenant را می‌دهد؛
- Resolve Tenant دیگر به `AIModelNotRegistered` یا Route بدون Candidate ختم می‌شود؛
- Model ثبت‌شده برای Provider Tenant دیگر با Ownership error رد می‌شود؛
- `resolveModelByCode` در یک Tenantِ دارای چند Provider، Ambiguous است و حدس
  نمی‌زند؛
- Model Descriptor `frozen` است و caller آن را mutate نمی‌کند؛
- Metadata، Configuration Reference، Secret و Adapter در Descriptor/Decision نیست؛
- Permission واقعی User/Role، Audit و authorization context به Application و
  زیر‌فازهای Governance واگذار شده و در E جعل نشده است؛
- E هیچ Secret را resolve، ذخیره، log یا به Provider ارسال نمی‌کند.

---

## 11. فایل‌های ایجادشده/تغییریافته

```text
backend/apps/ai/domain/registries/modelRegistry.py       # ایجاد
backend/apps/ai/domain/registries/__init__.py            # export E
backend/apps/ai/domain/exceptions/aiExceptions.py        # خطاهای E
backend/apps/ai/domain/exceptions/__init__.py            # export خطاهای E
backend/tests/unit/testPhase13ModelRegistry.py           # تست Pure E

docs/Phases/Phase13/Phase13-E.md                         # همین قرارداد
docs/Phases/Phase13/Phase13-E-ExecutionReport.md         # گزارش اجرا

docs/Phases/Phase13/README.md                            # وضعیت و لینک E
```

هیچ ORM، Migration، API، Queue، Provider Adapter، Secret Store یا Vendor SDK در
E اضافه نشده است.

---

## 12. Acceptance Criteria

- [x] Model Registry در ساختار واقعی Tekarai ساخته شد؛
- [x] `AIModel` دامنه و `ProviderRegistry` زیر‌فاز D به هم متصل شدند؛
- [x] تمام Lookupها Tenant-aware هستند؛
- [x] کلید `(tenantId, providerId, modelCode)` enforce شد؛
- [x] Duplicate و Replace صریح پیاده شد؛
- [x] Provider Ownership و Provider ID mismatch رد می‌شود؛
- [x] Model inactive Operational Resolve نمی‌شود؛
- [x] Provider inactive Model را Operational Resolve/Route نمی‌کند؛
- [x] Active Listing و Management Listing جدا هستند؛
- [x] Descriptorها non-sensitive و immutable هستند؛
- [x] Model Type و Business Capability بررسی می‌شوند؛
- [x] Streaming، Tools، Vision، Embedding و Context Window بررسی می‌شوند؛
- [x] Provider Feature handshake از `ProviderCapabilities` بررسی می‌شود؛
- [x] Routing deterministic و provider-agnostic است؛
- [x] هیچ Vendor import یا Vendor hard-code در Domain E وجود ندارد؛
- [x] Preferred/Default/Fallback Policy صریح است؛
- [x] Retry/Failover واقعی در E وارد نشده است؛
- [x] Tenant Isolation، Duplicate، Activation، Routing و Purity تست شده‌اند؛
- [x] مستندات و Execution Report ثبت شده‌اند؛
- [x] ZIP مستقل E ساخته و checksum آن ثبت می‌شود.

**نتیجه:** `GREEN — Phase 13-F may begin.`
