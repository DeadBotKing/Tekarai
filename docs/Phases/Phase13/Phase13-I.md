# Phase 13-I — Prompt Platform و Versioning

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** I از A تا Z  
**وضعیت:** COMPLETED — Prompt Platform/Versioning Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-H.md`](Phase13-H.md)  
**گزارش اجرا:** [`Phase13-I-ExecutionReport.md`](Phase13-I-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز I، Prompt را به‌عنوان یک Entity مستقل و Versioned در AI Platform
قرار می‌دهد. `AIPrompt` و `AIPromptVersion` موجود در B از طریق
`PromptPlatformService` مدیریت می‌شوند؛ هر تغییر مهم Prompt یک Version جدید
می‌سازد و Versionهای قبلی overwrite نمی‌شوند.

I به این سؤال پاسخ می‌دهد:

> چگونه Prompt Template، System Instruction، Variable Contract، Output Schema
> و Model Constraints را به‌صورت Tenant-aware و قابل audit مدیریت کنیم، بدون آنکه
> Prompt قدیمی از بین برود یا Template بتواند به Object traversal ناامن تبدیل شود؟

I Provider-agnostic است و هیچ Promptی را به Model یا Provider خاص hard-code
نمی‌کند. Render فقط یک pure string transformation در Domain است؛ اجرای Prompt
و ارسال آن به Provider در زیر‌فازهای بعدی انجام می‌شود.

---

## 2. Scope و Non-Scope

### داخل Scope

- استفاده از Entityهای واقعی `AIPrompt` و `AIPromptVersion` از B؛
- Prompt registration با کلید `(tenantId, promptCode)`؛
- Duplicate protection و Replace محدود Prompt Definition؛
- ایجاد و ثبت Version با شمارهٔ صریح یا auto-increment؛
- Monotonic versioning؛
- جلوگیری از overwrite یا replace کردن Version قبلی؛
- Active Version pointer برای هر Prompt؛
- تضمین اینکه در هر Prompt حداکثر یک Version active باشد؛
- Prompt activation/deactivation؛
- Version activation/deactivation؛
- Tenant isolation برای Prompt، Version، Lookup، Render و Association؛
- Template validation و declared variable contract؛
- جلوگیری از undeclared variable، attribute access، indexing، conversion و
  format specification؛
- Render با mapping دقیق و بدون variable اضافه یا missing؛
- Output Schema اختیاری با integration به `StructuredOutputSchema` فاز H؛
- Schema fingerprint در Safe Descriptor؛
- Model Constraints غیرحساس و JSON-compatible؛
- جلوگیری از Secret-like metadata key؛
- Snapshot/copy isolation برای جلوگیری از mutation بیرونی؛
- Safe immutable `PromptDescriptor` و `PromptVersionDescriptor`؛
- `RenderedPrompt` با متن برای caller و `repr` امن؛
- Pure Unit Test و regression کامل B تا I؛
- Documentation، Verification، Gate و ZIP مستقل.

### خارج از Scope

- ORM، Database، Migration و Repository دائمی؛
- API، Serializer، Admin، View یا Permission endpoint؛
- Prompt approval workflow و Governance کامل؛
- Prompt injection detection و safety classifier؛
- Provider SDK، Network، Model execution و Token counting؛
- Context Builder، Retrieval و Permission Filtering؛
- Retry، Timeout، Failover و Async execution؛
- Response generation و output validation runtime؛ H Contract در I فقط برای
  معتبر بودن Output Schema definition مصرف می‌شود؛
- Secret resolution، API Key، Password، Connection String یا credential store؛
- Full JSON Schema standard؛ I از subset immutable و validateشدهٔ H استفاده می‌کند؛
- Translation، A/B testing، prompt analytics و rollout percentage؛
- Distributed locking، concurrency و durable uniqueness.

---

## 3. جایگاه معماری

```text
Prompt Definition (AIPrompt - B)
              │
              ▼
    PromptPlatformService (I)
      ┌───────┴────────┐
      ▼                ▼
 AIPromptVersion   Active Pointer
      │                │
      ├─ Template      │
      ├─ Variables     │
      ├─ Output Schema └─ one active version
      └─ Model Rules
              │
              ▼
       RenderedPrompt
              │
              ▼
   Future AI Application / Provider Adapter
```

ارتباط با زیر‌فازهای قبلی:

```text
Request (G) ── future caller context ──► Prompt Render (I)
StructuredOutputSchema (H) ────────────► AIPromptVersion.outputSchema
AIResponse.promptVersionId (B) ◄─────── future execution reference
ModelRegistry (E/F) ◄────────────────── modelConstraints as passive data
```

مرز مالکیت:

| مفهوم | مالک |
|---|---|
| Prompt Entity و Version Entity | B |
| Prompt code registry و version lifecycle | I |
| Safe template render | I |
| Structured Output Schema Contract | H |
| Prompt Schema ownership/version persistence | future adapter / I extension |
| Provider execution | L |
| Prompt selection and Model Routing | Application/E/F |
| Context construction | J |
| Prompt injection/safety governance | K/O |
| Usage/Cost/Latency | N/W |
| Async execution | P |

---

## 4. Prompt Registration Contract

### 4.1 کلید Tenant-aware

```text
(tenantId UUID, promptCode UPPERCASE)
```

دو Tenant می‌توانند Code یکسان داشته باشند؛ Prompt یک Tenant در Tenant دیگر
قابل lookup یا render نیست.

```python
prompt = platform.createPrompt(
    tenantId,
    "PROJECT_SUMMARY",
    "Project summary",
    description="Summarize an authorized project",
)
```

قواعد:

- `tenantId` و `promptId` UUID معتبر هستند؛
- Code با Grammar B normalize و uppercase می‌شود؛
- Name از Entity B اعتبارسنجی می‌شود؛
- duplicate در همان Tenant با `AIPromptAlreadyRegistered` رد می‌شود؛
- Code یکسان در Tenant دیگر مستقل است؛
- `registerPrompt(..., replace=True)` فقط همان Prompt ID را replace می‌کند؛
- replacement، Versionها را حذف نمی‌کند و Prompt ID را تغییر نمی‌دهد؛
- returned Entity snapshot است و mutation آن Registry داخلی را تغییر نمی‌دهد.

### 4.2 Prompt Active State

Prompt `isActive` و Version `isActive` دو مفهوم مستقل‌اند:

```text
Prompt inactive + Version active  → resolve/render عملیاتی ممنوع
Prompt active + no active Version → resolve فعال وجود ندارد
Prompt active + one active Version → render مجاز
```

`activatePrompt` و `deactivatePrompt` فقط Prompt lifecycle را تغییر می‌دهند.
غیرفعال کردن Prompt، Version تاریخی را حذف یا overwrite نمی‌کند.

---

## 5. Versioning Contract

### 5.1 شماره‌گذاری

```python
version1 = platform.createVersion(
    tenantId,
    prompt.id,
    "Summarize {subject}",
    variables=("subject",),
)
version2 = platform.createVersion(
    tenantId,
    prompt.id,
    "Summarize {subject} for {audience}",
    variables=("subject", "audience"),
    version=2,
    activate=True,
)
```

اگر `version` داده نشود، عدد `max(existing)+1` ساخته می‌شود. Version باید
positive integer باشد. کلید یکتا:

```text
(tenantId, promptId, versionNumber)
```

### 5.2 Immutability

پس از ثبت Version:

- Template overwrite نمی‌شود؛
- Variables overwrite نمی‌شوند؛
- Output Schema overwrite نمی‌شود؛
- Model Constraints overwrite نمی‌شوند؛
- `replace=True` برای Version مجاز نیست و
  `AIPromptVersionImmutable` می‌دهد؛
- تغییر محتوای Prompt باید Version جدید بسازد؛
- `getVersion` و `getPrompt` snapshot عمیق برمی‌گردانند تا caller نتواند state
  داخلی را mutate کند؛
- Activation فقط `isActive` و Prompt active pointer را تغییر می‌دهد و محتوای
  Version را تغییر نمی‌دهد.

### 5.3 Active Version Pointer

`activateVersion(tenantId, promptId, versionId)`:

1. Prompt و Version را در همان Tenant resolve می‌کند؛
2. تعلق Version به Prompt را بررسی می‌کند؛
3. همهٔ sibling Versionهای همان Prompt را inactive می‌کند؛
4. Version هدف را active می‌کند؛
5. `prompt.activeVersionId` را به Version هدف متصل می‌کند.

`deactivateVersion` اگر Version active باشد، pointer را `None` می‌کند. هیچ
Version تاریخی delete نمی‌شود.

ثبت مستقیم Version با `isActive=True` عمداً رد می‌شود تا activation همیشه یک
command صریح و قابل audit باشد.

---

## 6. Template Contract و Safe Rendering

### 6.1 Declared Variables

هر field استفاده‌شده در Template باید در `variables` اعلام شده باشد:

```python
"Analyze {project_name} for {audience}"
variables=("project_name", "audience")
```

این موارد ممنوع‌اند:

```text
{name}                 بدون declaration
{user.name}            attribute traversal
{items[0]}             indexing
{value!r}              conversion
{value:>10}            format specification
```

Variable باید Simple Identifier باشد:

```text
[A-Za-z_][A-Za-z0-9_]*
```

Variable تکراری یا Template دارای syntax نامعتبر رد می‌شود. Declared variable
unused می‌تواند برای compatibility باقی بماند، اما در Render تمام declared
values باید صریحاً داده شوند.

### 6.2 Render Rules

```python
rendered = platform.render(
    tenantId,
    "PROJECT_SUMMARY",
    {"project_name": "Apollo", "audience": "leadership"},
)
```

قواعد:

- فقط Active Prompt و Active Version از Tenant صحیح قابل Render هستند؛
- mapping ورودی الزامی است؛
- missing variable و extra variable رد می‌شوند؛
- escaped braces مانند `{{literal}}` پشتیبانی می‌شوند؛
- Render فقط `str.format` محدودشده به Simple Identifier است؛
- هیچ Object traversal یا method invocation از Template ممکن نیست؛
- متن Render شده برای caller در `RenderedPrompt.asText()` قابل دسترسی است؛
- متن در `repr(RenderedPrompt)` چاپ نمی‌شود؛
- Prompt متن را HTML، SQL، Command، Tool call یا Provider instruction امن فرض
  نمی‌کند؛ downstream safety باید در K/Application/O انجام شود.

### 6.3 RenderedPrompt

`RenderedPrompt` شامل این metadata است:

- Tenant ID؛
- Prompt ID؛
- Version ID و شمارهٔ Version؛
- variable names؛
- متن Render شده، با `repr=False`؛
- Output Schema fingerprint.

`RenderedPrompt` یک immutable result است؛ آن را می‌توان به Application Service
تحویل داد تا بعداً به Provider Port متصل شود.

---

## 7. Output Schema و Model Constraints

### 7.1 Output Schema

`AIPromptVersion.outputSchema` از Entity B یک dictionary است. I در زمان Create
و Register آن را به `StructuredOutputSchema` فاز H می‌دهد تا definition معتبر
باشد.

```text
invalid schema → AIPromptOutputSchemaInvalid
valid schema   → canonical JSON-compatible dictionary
```

I Schema کامل را در Descriptor expose نمی‌کند؛ فقط این موارد را نشان می‌دهد:

- `hasOutputSchema`؛
- `outputSchemaFingerprint`؛
- Version و Schema identity.

Schema مالکیت runtime response را به‌تنهایی تعیین نمی‌کند؛ Response H هنگام
دریافت خروجی باید validation را دوباره انجام دهد. I فقط contract را به Prompt
Version متصل می‌کند.

### 7.2 Model Constraints

`modelConstraints` passive و Provider-agnostic است؛ مثال:

```python
{
    "modelType": "LLM",
    "minimumContextWindow": 1000,
}
```

I آن را اجرا یا routing نمی‌کند. `ModelRegistry` و Application در زمان انتخاب
Model آن را consume می‌کنند.

قواعد:

- فقط Mapping JSON-compatible پذیرفته می‌شود؛
- keyها باید String باشند؛
- Secret-like keyهای `api_key`، `password`، `token`، `secret` و
  `connection_string` رد می‌شوند؛
- Model Constraint کامل در Descriptor و log safe نمایش داده نمی‌شود؛
- هیچ Provider code یا SDK object در Prompt Version ذخیره نمی‌شود.

---

## 8. Safe Read Models و Security Boundary

### 8.1 PromptDescriptor

شامل:

- Tenant/Prompt ID؛
- Code، Name و Description؛
- Active state؛
- Active Version ID و شماره؛
- Version count؛
- CreatedAt.

شامل نمی‌شود:

- Template؛
- System Instruction؛
- Output Schema کامل؛
- Model Constraint کامل؛
- Secret یا credential؛
- Rendered text.

### 8.2 PromptVersionDescriptor

شامل:

- Tenant، Prompt و Version ID؛
- Version number؛
- active state؛
- declared variable names؛
- وجود Schema و fingerprint آن؛
- وجود Model Constraints؛
- createdBy و createdAt.

شامل نمی‌شود:

- Template و System Instruction؛
- Schema کامل؛
- Constraint values؛
- Rendered values؛
- Secret و API Key.

### 8.3 Copy Isolation

Registry Entityها را deep-copy نگه می‌دارد و Read Entity snapshot برمی‌گرداند.
این تضمین می‌کند caller با تغییر object برگشتی، version content یا active
pointer داخلی را دور نزند. تغییر مجاز فقط از طریق commandهای Platform انجام
می‌شود.

---

## 9. Tenant Isolation و Error Contract

- تمام Prompt lookupها `tenantId` دارند؛
- Prompt code به‌تنهایی برای resolve کافی نیست؛
- Version lookup در `(tenantId, versionId)` است؛
- Version متعلق به Tenant یا Prompt دیگر activate/render نمی‌شود؛
- duplicate code در Tenant دیگر مستقل است؛
- خطای Tenant دیگر با NotFound boundary گزارش می‌شود؛
- هیچ Prompt یا Version از Tenant دیگر در List وارد نمی‌شود؛
- `createdBy` فقط UUID reference است و Authorization واقعی را جعل نمی‌کند؛
- Permission/Approval واقعی به K/Application/O واگذار است.

خطاهای I:

| Exception | Code | کاربرد |
|---|---|---|
| `AIPromptAlreadyRegistered` | `AI_PROMPT_ALREADY_REGISTERED` | duplicate Prompt code در Tenant |
| `AIPromptNotFound` | `AI_PROMPT_NOT_FOUND` | Prompt خارج از Tenant scope |
| `AIPromptVersionAlreadyRegistered` | `AI_PROMPT_VERSION_ALREADY_REGISTERED` | duplicate Version number/ID |
| `AIPromptVersionNotFound` | `AI_PROMPT_VERSION_NOT_FOUND` | Version خارج از Tenant scope |
| `AIPromptLifecycleInvalid` | `AI_PROMPT_LIFECYCLE_INVALID` | active pointer یا command نامعتبر |
| `AIPromptTemplateInvalid` | `AI_PROMPT_TEMPLATE_INVALID` | syntax/variable/render نامعتبر |
| `AIPromptOutputSchemaInvalid` | `AI_PROMPT_OUTPUT_SCHEMA_INVALID` | Schema definition نامعتبر |
| `AIPromptVersionImmutable` | `AI_PROMPT_VERSION_IMMUTABLE` | تلاش برای overwrite Version |

---

## 10. Persistence و آینده

پیاده‌سازی I in-memory است. Adapter دائمی آینده باید حداقل این invariantها را
حفظ کند:

- unique `(tenantId, promptCode)`؛
- unique `(tenantId, promptId, version)`؛
- stable Version ID؛
- transaction برای active pointer؛
- حداکثر یک Version active برای Prompt؛
- عدم overwrite محتوای Version؛
- optimistic locking یا concurrency control؛
- Audit برای Create/Activate/Deactivate؛
- Retention policy برای Prompt، Version و Render metadata؛
- Encryption/secret policy خارج از Prompt Domain؛
- cache invalidation پس از Activation؛
- authorization و approval قبل از activation در Application/O.

I عمداً Migration یا Database Constraint ناقص اضافه نمی‌کند.

---

## 11. Purity و Dependency Rules

`promptPlatform.py` فقط از Python standard library، Entityهای B، Exceptionهای
Domain، `StructuredOutputSchema` فاز H و value validation دامنه استفاده می‌کند.

ممنوع و استفاده‌نشده:

```text
Django / ORM / REST / HTTP / Redis / Queue / Worker
OpenAI / Ollama / Azure / Anthropic / Vendor SDK
Network / File I/O / Secret Store / Database / Persistence
```

Template Rendering pure است و Provider execution ندارد.

---

## 12. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/services/promptPlatform.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13PromptPlatform.py

docs/Phases/Phase13/Phase13-I.md
docs/Phases/Phase13/Phase13-I-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
PromptPlatformService
createPrompt / registerPrompt
createVersion / registerVersion
getPrompt / getPromptById / getVersion
getActiveVersion
activatePrompt / deactivatePrompt
activateVersion / deactivateVersion
render / renderVersion
describePrompt / describeVersion
listPrompts / listVersions
```

Aliasها:

```text
PromptRegistry
AIPromptRegistry
PromptPlatform
InMemoryPromptRegistry
AIPromptPlatformService
PromptVersioningService
```

Read Modelها:

```text
PromptDescriptor
PromptVersionDescriptor
RenderedPrompt
```

---

## 13. Open Questions برای زیر‌فازهای بعدی

1. Prompt approval و publish workflow در O/Application چگونه به
   `activateVersion` متصل شود؟
2. Schema پایدار I چگونه با `AIResponseService` H و Prompt Version reference
   در `AIResponse.promptVersionId` همسان شود؟
3. آیا Template باید syntax اختصاصی مستقل از Python format داشته باشد؟
4. Prompt injection detection و content safety در K/O چگونه قبل از Render یا
   قبل از delivery قرار گیرد؟
5. آیا variable value باید JSON-compatible محدود شود یا رشته‌سازی application
   برای همهٔ نوع‌ها کافی است؟
6. آیا Version numbering باید integer بماند یا semantic version هم لازم است؟
7. آیا activation همزمان در چند instance به database lock یا event version نیاز
   دارد؟
8. آیا Promptهای inactive باید قابل preview برای Admin باشند، و با چه permission؟
9. A/B rollout، canary و tenant-specific override در کدام زیر‌فاز تعریف شوند؟
10. Retention متن Render شده چگونه با Privacy و Audit policy هماهنگ شود؟

---

## 14. Acceptance Criteria

- [x] Prompt Platform در ساختار واقعی Tekarai ساخته شد؛
- [x] Entityهای `AIPrompt` و `AIPromptVersion` از B استفاده شدند؛
- [x] Prompt registry به‌صورت Tenant-aware پیاده شد؛
- [x] Duplicate Prompt code و Version number قابل تشخیص است؛
- [x] Version جدید بدون overwrite Version قبلی ایجاد می‌شود؛
- [x] Versionهای قبلی immutable باقی می‌مانند؛
- [x] Active Version pointer و حداکثر یک active version enforce شد؛
- [x] Prompt و Version activation/deactivation وجود دارد؛
- [x] Declared variable contract و safe rendering وجود دارد؛
- [x] undeclared variable و traversal/format expression رد می‌شود؛
- [x] Missing/extra render variables رد می‌شوند؛
- [x] Output Schema فاز H در Prompt Version validate می‌شود؛
- [x] Model Constraints passive، provider-agnostic و safe هستند؛
- [x] Secret-like metadata keys رد می‌شوند؛
- [x] Safe immutable descriptors ایجاد شدند؛
- [x] Tenant isolation در Prompt/Version/Render برقرار است؛
- [x] هیچ ORM/API/Queue/Worker/Network/Vendor/Secret وارد Domain I نشده است؛
- [x] Pure Test و regression B تا I اجرا شد؛
- [x] محدودیت‌های محیط و Scope دقیق ثبت شدند؛
- [x] Documentation، Verification، Gate و ZIP مستقل آماده شد.

**نتیجه:** `GREEN — Phase 13-J may begin.`
