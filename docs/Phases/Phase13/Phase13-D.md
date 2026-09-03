# Phase 13-D — Provider Registry

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** D از A تا Z  
**وضعیت:** COMPLETED — Provider Registry Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد C:** [`Phase13-C.md`](Phase13-C.md)  
**گزارش اجرا:** [`Phase13-D-ExecutionReport.md`](Phase13-D-ExecutionReport.md)

---

## 1. هدف

D یک Registry مستقل و Tenant-aware برای ثبت و Resolve کردن Provider Definition و
Provider Adapter می‌سازد. Registry نقطهٔ ترکیب Runtime برای Providerهاست و از
Application/Infrastructure می‌خواهد که فقط Adapterای را ثبت کند که Contract C را
پیاده‌سازی کرده باشد.

D این سؤال را پاسخ می‌دهد:

> برای Tenant مشخص، Provider با Code مشخص ثبت شده است؟ فعال است؟ Adapter آن کدام
> است؟ چه Capabilityهایی اعلام می‌کند؟

D هنوز تصمیم نمی‌گیرد کدام Model یا Provider برای یک Request انتخاب شود؛ انتخاب و
Routing به زیر‌فاز E واگذار است.

---

## 2. Scope و Non-Scope

### داخل Scope

- In-memory `ProviderRegistry` خالص Python؛
- ثبت Definition به همراه `AIProviderPort` Adapter؛
- کلید یکتا `(tenantId, providerCode)`؛
- جلوگیری از Duplicate Registration؛
- `replace=True` فقط با دستور صریح؛
- Resolve Tenant-scoped؛
- Active/Inactive lifecycle؛
- Active-only Listing و Full Listing برای inspection؛
- Capability lookup؛
- Health delegation کنترل‌شده؛
- Non-sensitive `ProviderDescriptor`؛
- Runtime validation برای Port، Provider Code و Capability Code؛
- Unregister و Test reset؛
- تست Unit بدون Django، ORM، Network و SDK.

### خارج از Scope

- Model Registry و Model Routing؛
- Default/Fallback Provider؛
- Load Balancing و Cost/Latency selection؛
- Persistence، ORM و Migration؛
- Distributed Registry یا shared cache؛
- Provider Adapter واقعی؛
- Secret Resolution و Secret Vault؛
- Queue، Retry، Timeout و Circuit Breaker؛
- API، Permission endpoint و Admin UI.

---

## 3. معماری Registry

```text
Application Composition Root
          │
          │ registerProvider(AIProvider, AIProviderPort)
          ▼
┌────────────────────────────────────┐
│        ProviderRegistry             │
│ key = (tenantId, providerCode)     │
│ Definition + Runtime Adapter       │
└──────────────┬─────────────────────┘
               │ resolve(tenant, code)
               ▼
        AIProviderPort Adapter
               │
               ▼
   Generation / Embedding / Health
```

Registry در D یک Object درون‌پردازشی است. این تصمیم عمدی است: Persistence و
Distributed Consistency نباید پیش از تعریف Repository، Database Constraints و
Application Transaction در D پنهان شوند.

---

## 4. مدل‌های Registry

### 4.1 `ProviderRegistration`

Binding Runtime بین:

- `AIProvider` از B؛
- یک Object سازگار با `AIProviderPort` از C؛
- زمان ثبت.

Properties قابل استفاده:

- `tenantId`؛
- `providerCode`؛
- `capabilities`؛
- `descriptor()`.

Adapter عمداً در `repr` Registration نشان داده نمی‌شود تا object داخلی، Metadata
یا Configuration ناخواسته در Log ظاهر نشود.

### 4.2 `ProviderDescriptor`

Read Model غیرحساس برای Listing/Inspection:

- Tenant ID؛
- Provider ID؛
- Code؛
- Name؛
- Provider Type؛
- Active flag؛
- Capabilities؛
- Registered At.

`configurationReference`، metadata داخلی، Adapter object، Secret و API Key در
Descriptor وجود ندارند. Descriptor نیز `frozen` است.

### 4.3 کلید Registration

کلید دقیق Registry:

```text
(tenantId UUID, providerCode UPPERCASE)
```

در نتیجه دو Tenant می‌توانند Provider Code یکسان داشته باشند، اما یک Tenant
نمی‌تواند یک Code را دوباره ثبت کند مگر با `replace=True`.

---

## 5. Registration Contract

برای ثبت معتبر، همهٔ قواعد زیر باید برقرار باشد:

1. Definition از نوع `AIProvider` باشد؛
2. `tenantId` Definition یک UUID معتبر باشد؛
3. Provider Code Definition توسط Domain B normalize شده باشد؛
4. Adapter با `AIProviderPort` سازگار باشد؛
5. Adapter `providerCode` داشته باشد؛
6. `adapter.providerCode == provider.code` باشد؛
7. Adapter `capabilities` از نوع `ProviderCapabilities` باشد؛
8. `capabilities.providerCode == provider.code` باشد؛
9. Registration قبلی برای همان `(tenantId, code)` وجود نداشته باشد، مگر
   `replace=True`؛
10. هیچ Secret خام در Registration یا Descriptor وارد نشود.

Registry Provider Code را از روی Adapter حدس نمی‌زند و Code mismatch را silent
fix نمی‌کند؛ mismatch یک Configuration Error است.

---

## 6. API رفتارهای Registry

### `registerProvider(provider, adapter, replace=False)`

Provider را پس از validation ثبت می‌کند.

- Duplicate پیش‌فرض رد می‌شود؛
- `replace=True` binding قبلی را صریحاً جایگزین می‌کند؛
- Tenant و Code از Definition گرفته می‌شوند؛
- زمان Registration ثبت می‌شود؛
- Runtime Adapter همان object ثبت‌شده است.

### `register(...)`

Alias کوتاه برای Composition Root است و همان قواعد `registerProvider` را دارد.

### `getRegistration(tenantId, providerCode)`

Registration کامل را برای inspection داخلی برمی‌گرداند. `includeInactive=True`
به‌صورت پیش‌فرض اجازه می‌دهد Registration غیرفعال برای مدیریت دیده شود.

### `resolveProvider(tenantId, providerCode)`

Adapter قابل استفاده را Resolve می‌کند:

- Tenant نامعتبر رد می‌شود؛
- Provider ثبت‌نشده `AIProviderNotRegistered` می‌دهد؛
- Provider غیرفعال `AIProviderInactive` می‌دهد؛
- Provider Tenant دیگر از طریق همان Not Registered path قابل enumerate نیست.

### `describeProvider(...)`

فقط `ProviderDescriptor` غیرحساس برمی‌گرداند و Adapter یا Configuration داخلی را
expose نمی‌کند.

### `listProviders(tenantId, activeOnly=True)`

- فقط Registrationهای همان Tenant را می‌بیند؛
- در حالت پیش‌فرض فقط Activeها را می‌دهد؛
- با `activeOnly=False` برای عملیات مدیریتی Inactiveها را هم می‌دهد؛
- خروجی بر اساس Code مرتب می‌شود؛
- خروجی tuple است و caller نمی‌تواند Registry داخلی را mutate کند.

### `activateProvider` / `deactivateProvider`

Lifecycle فعال‌بودن Definition را تغییر می‌دهند. Deactivate، Registration را حذف
نمی‌کند؛ Resolve عملیاتی آن را متوقف می‌کند و Listing مدیریتی آن را نگه می‌دارد.

### `supports(tenantId, providerCode, feature)`

ابتدا Resolve فعال انجام می‌شود و سپس Capability Handshake C بررسی می‌شود. این
متد Model Routing یا Business Capability Resolution انجام نمی‌دهد.

### `healthCheck(...)`

Health را فقط از Adapter ثبت‌شده می‌گیرد. Exception ناشناختهٔ Adapter در مرز
Registry به `AIProviderUnavailable` تبدیل می‌شود و Exception داخلی به Consumer
نشت نمی‌کند.

Health Check:

- فقط برای Tenant و Provider ثبت‌شده؛
- برای Provider inactive مجاز نیست؛
- Model اختیاری است؛
- نباید Secret یا Prompt را ثبت/برگرداند.

### `unregisterProvider` / `unregister`

Registration را از Registry in-memory حذف می‌کند. حذف Persistence یا Audit در D
وجود ندارد و به مراحل بعد موکول است.

### `clear()`

تنها برای Test و Composition Root در Registry in-memory است و هیچ ادعای حذف
Database ندارد.

---

## 7. Tenant Isolation

Registry هر عملیات Lookup را با Tenant در کلید انجام می‌دهد:

```text
Tenant A + DETERMINISTIC → Adapter A
Tenant B + DETERMINISTIC → Adapter B یا Not Registered
```

قواعد:

1. Lookup بدون Tenant مجاز نیست؛
2. Provider Code به‌تنهایی کلید محسوب نمی‌شود؛
3. List هر Tenant فقط Descriptorهای خودش را برمی‌گرداند؛
4. Provider Tenant دیگر با Resolve قابل مشاهده نیست؛
5. یک Adapter عمومی می‌تواند برای Definitionهای چند Tenant ثبت شود، اما Binding
   Registry و Definition همچنان Tenant-scoped باقی می‌ماند؛
6. Tenant authorization واقعی User/Role در K و Application Layer انجام می‌شود؛
7. D Permission system یا Database Query جدید اضافه نمی‌کند.

---

## 8. Activation و Duplicate Policy

### Duplicate

رفتار پیش‌فرض امن است:

```text
Existing registration + register(new) → AIProviderAlreadyRegistered
```

جایگزینی باید صریح باشد:

```text
register(new, replace=True) → binding جدید
```

این جلوگیری می‌کند از اینکه Composition Root یا Reload ناخواسته Adapter فعال را
تغییر دهد.

### Inactive

`deactivateProvider` Definition را حفظ می‌کند، اما:

```text
resolveProvider(...) → AIProviderInactive
supports(...)        → AIProviderInactive
healthCheck(...)     → AIProviderInactive
list(activeOnly=True) → حذف از خروجی
```

برای مدیریت:

```text
listProviders(activeOnly=False) → شامل Inactive
```

---

## 9. Error Contract

خطاهای مخصوص D:

| خطا | Code | وضعیت |
|---|---|---:|
| `AIProviderAlreadyRegistered` | `AI_PROVIDER_ALREADY_REGISTERED` | 409 |
| `AIProviderNotRegistered` | `AI_PROVIDER_NOT_REGISTERED` | 404 |
| `AIProviderInactive` | `AI_PROVIDER_INACTIVE` | 503 |
| `AIProviderRegistrationInvalid` | `AI_PROVIDER_REGISTRATION_INVALID` | 422 |
| Adapter health failure | `AI_PROVIDER_UNAVAILABLE` | 503 |

هدف `AIProviderNotRegistered` این است که Tenant دیگر و Provider واقعاً موجود،
از نظر Enumeration به‌صورت متفاوت expose نشوند.

خطای خام SDK در D وجود ندارد. Mapping خطاهای Adapter واقعی در M/L تکمیل می‌شود.

---

## 10. Security و Secret Boundary

- Registry مقدار `configurationReference` را فقط در `AIProvider` می‌پذیرد؛
- Registry Secret Store را resolve نمی‌کند؛
- Descriptor Configuration Reference ندارد؛
- Adapter object در Public Listing برگردانده نمی‌شود؛
- Provider Code/Name/Type قابل نمایش‌اند، Secret نیستند؛
- Health Detail باید غیرحساس باشد؛
- هیچ API Key، Password، Token یا Connection String در Source Code C/D اضافه نشده؛
- Audit واقعی Registration به O واگذار شده است.

---

## 11. جایگاه Capability و Routing

D Capability Provider را فقط advertise و inspect می‌کند:

```python
registry.supports(tenantId, "DETERMINISTIC", "STREAMING")
```

اما موارد زیر عمداً انجام نمی‌شوند:

- انتخاب بین چند Provider؛
- انتخاب Model؛
- بررسی Cost/Latency؛
- Fallback؛
- اولویت Provider؛
- Default Provider؛
- Capability Business Domain؛
- Tenant Quota.

این مرز از مخفی‌شدن E، F، M و N داخل D جلوگیری می‌کند.

---

## 12. Persistence Boundary

پیاده‌سازی فعلی in-memory است و برای یک Process معتبر است. در مراحل بعد:

```text
ProviderRegistry Contract
          │
          ▼
Provider Repository / Persistence
          │
          ▼
Tenant unique constraint + active policy
```

پیاده‌سازی Repository-backed باید همین قواعد را حفظ کند:

- Unique `(tenantId, providerCode)`؛
- عدم بازگرداندن Secret در Read Model؛
- Transaction برای Replace/Activate؛
- optimistic/concurrency control؛
- Audit تغییرات؛
- Cache invalidation؛
- عدم نشت Registration بین Tenantها.

D عمداً Schema و Migration را تغییر نمی‌دهد.

---

## 13. فایل‌های پیاده‌سازی

```text
backend/apps/ai/domain/registries/__init__.py
backend/apps/ai/domain/registries/providerRegistry.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13ProviderRegistry.py
```

Compatibility aliasها:

```python
AIProviderRegistry = ProviderRegistry
InMemoryProviderRegistry = ProviderRegistry
RegisteredProvider = ProviderRegistration
```

این Aliasها برای Composition Root و نام‌گذاری آینده هستند و رفتار جدید جداگانه‌ای
ایجاد نمی‌کنند.

---

## 14. Acceptance Criteria

- [x] Provider Registry در ساختار واقعی Tekarai ایجاد شد؛
- [x] Registry Framework-independent است؛
- [x] Provider Definition از Adapter جدا ولی به‌صورت Binding ثبت می‌شود؛
- [x] کلید `(tenantId, providerCode)` enforce شد؛
- [x] Duplicate Registration به‌صورت امن رد می‌شود؛
- [x] Replace فقط با Flag صریح انجام می‌شود؛
- [x] Adapter باید Runtime با `AIProviderPort` سازگار باشد؛
- [x] Provider Code و Capability Code mismatch رد می‌شود؛
- [x] Resolve Tenant-scoped است؛
- [x] Inactive Provider Resolve عملیاتی نمی‌شود؛
- [x] Active-only و Full Listing وجود دارد؛
- [x] Capability و Health از Adapter ثبت‌شده قابل دریافت است؛
- [x] Descriptor غیرحساس و Immutable است؛
- [x] خطاهای مخصوص Registry تعریف شده‌اند؛
- [x] هیچ Secret یا Vendor SDK اضافه نشده است؛
- [x] Model Routing، Fallback و Persistence وارد D نشده‌اند؛
- [x] Unit Testهای Offline سبز هستند؛
- [x] گزارش اجرا و دلیل تست‌های اجرا نشده ثبت شده است؛
- [x] ZIP تحویل مستقل D ساخته می‌شود.

**نتیجه:** `GREEN — Phase 13-E may begin.`
