# Phase 13-G — Request و Operation Lifecycle

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** G از A تا Z  
**وضعیت:** COMPLETED — Request/Operation Lifecycle Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-F.md`](Phase13-F.md)  
**گزارش اجرا:** [`Phase13-G-ExecutionReport.md`](Phase13-G-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز G قرارداد عملیاتی شفاف برای دو Entity موجود B یعنی `AIRequest` و
`AIOperation` ایجاد می‌کند. G مشخص می‌کند یک Request چگونه ایجاد، به یک
Operation متصل، فعال، تکمیل، شکست‌خورده، لغو یا به‌صورت صریح دوباره در صف قرار
می‌گیرد؛ همچنین مشخص می‌کند Operation چه زمانی می‌تواند پایان یابد و چگونه
Tenant، Parent Request، Correlation و Trace در این مسیر حفظ می‌شوند.

G به این سؤال پاسخ می‌دهد:

> چگونه می‌توان چرخهٔ عمر Request و Operation را در مرز Domain، به‌صورت
> Tenant-aware و بدون وابستگی به Persistence، Queue، Worker یا Provider اجرا و
> مشاهده کرد، درحالی‌که association و duplicate behavior قابل تشخیص باشد؟

G از Entity state machine موجود B استفاده می‌کند و آن را به یک coordinator
شفاف و pure در `RequestLifecycleService` وصل می‌کند. این Service یک Repository
دائمی یا موتور Execution نیست؛ state آن فقط in-memory است تا Application/Infrastructure
بعدی بتواند آن را داخل transaction، database یا queue خود compose کند.

---

## 2. Scope و Non-Scope

### داخل Scope

- هماهنگی pure بین `AIRequest` و `AIOperation`؛
- Creation با وضعیت اولیهٔ `PENDING`؛
- ارتباط اختیاری Request با دقیقاً یک Operation؛
- نگهداری association در هر دو جهت و نمایش آن در Descriptor؛
- انتقال Request بین `PENDING`، `QUEUED`، `RUNNING`، `COMPLETED`، `FAILED` و
  `CANCELLED` مطابق state machine B؛
- انتقال Operation بین `PENDING`، `RUNNING`، `COMPLETED`، `FAILED` و `CANCELLED`؛
- timestampهای `createdAt`، `queuedAt`، `startedAt` و `completedAt`؛
- stable `errorCode` در شکست Request؛
- retry/requeue صریح یک Request شکست‌خورده، بدون retry policy یا execution؛
- completion gate برای Operation بر اساس وضعیت child Requestها؛
- cancellation cascade شفاف از Operation به child Requestهای غیرterminal؛
- Tenant isolation برای Create، Read، Transition، List و Association؛
- Parent Request و جلوگیری از اتصال آن به Operation متفاوت؛
- Correlation و Trace identifierهای opaque؛
- Tenant-scoped idempotency replay و conflict با fingerprint hash؛
- Capability ownership/type/activity validation در صورت compose شدن با F؛
- Safe immutable Descriptor بدون `inputData` و `idempotencyKey`؛
- خطاهای Domain-specific و قابل تشخیص؛
- Pure Unit Test و regression B تا G؛
- ثبت دقیق Verification، محدودیت‌ها و Gate.

### خارج از Scope

- ORM، Migration، Database، Repository دائمی و distributed transaction؛
- HTTP، API، Serializer، View، Admin یا Permission endpoint؛
- Queue، Worker، Scheduler، Event Bus و Async execution؛
- Provider SDK، Provider Adapter، Network و Model execution؛
- Retry policy، backoff، timeout، circuit breaker، failover و provider fallback؛
- Resolution یا ذخیره‌سازی Secret/API Key؛
- تولید Response، Structured Output و Validation خروجی؛ این موارد برای H است؛
- Usage، Token، Cost، Quota، Audit persistence و Monitoring؛
- Authorization کامل User/Role و Permission Filtering؛ این موارد به K/O/W و
  Application واگذار است؛
- Commit/rollback همزمان روی چند storage؛
- تضمین concurrency توزیع‌شده یا idempotency durable.

---

## 3. جایگاه معماری

```text
AICapability (B/F) ── optional validation ──┐
                                            ▼
Application command / future adapter
                    │                       │
                    ▼                       │
        RequestLifecycleService (G)         │
          ┌─────────┴─────────┐             │
          ▼                   ▼             │
     AIRequest (B)       AIOperation (B)    │
          │                   │             │
          └──── operationId ──┘             │
                    │                       │
                    ▼                       ▼
         RequestDescriptor / OperationDescriptor
```

مرز مالکیت:

| مفهوم | مالک |
|---|---|
| Entity و state transition اولیه | `aiRecords.py` در B |
| Capability resolve و request-type policy | `CapabilityRegistry` در F |
| Lifecycle coordination و association | `RequestLifecycleService` در G |
| Persistence و transaction واقعی | Adapter/Application آینده |
| Permission واقعی User/Role | Application و K |
| Retry/Timeout/Failover | M |
| Response و structured result | H |
| Async Queue/Worker | P |
| Audit و governance | O |

G با F فقط از طریق Contract عمومی `CapabilityRegistry` compose می‌شود و هیچ
Provider یا Model-specific behavior وارد Lifecycle نمی‌کند.

---

## 4. قرارداد State Machine

### 4.1 Request

Entity B این انتقال‌ها را مجاز می‌داند و G همان قواعد را enforce می‌کند:

```text
PENDING ──► QUEUED ──► RUNNING ──► COMPLETED
   │          │           ├──────► FAILED ──► QUEUED (explicit retry)
   │          │           └──────► CANCELLED       └────► CANCELLED
   └──────────┴───────────────────────────────► CANCELLED
```

جدول دقیق:

| وضعیت فعلی | وضعیت‌های مجاز |
|---|---|
| `PENDING` | `QUEUED`, `RUNNING`, `CANCELLED` |
| `QUEUED` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `COMPLETED`, `FAILED`, `CANCELLED` |
| `COMPLETED` | هیچ انتقالی؛ تکرار همان completion بدون تغییر است |
| `FAILED` | `QUEUED` با command صریح retry، یا `CANCELLED` |
| `CANCELLED` | هیچ انتقالی |

`failRequest` یک `errorCode` غیرخالی و پایدار می‌خواهد. متن Provider Exception
به‌عنوان Contract عمومی پذیرفته نمی‌شود؛ Adapterهای آینده باید آن را به یک
Domain error code تبدیل کنند.

### 4.2 Operation

```text
PENDING ──► RUNNING ──► COMPLETED
    │          ├──────► FAILED
    │          └──────► CANCELLED
    └────────────────► CANCELLED
```

| وضعیت فعلی | وضعیت‌های مجاز |
|---|---|
| `PENDING` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `COMPLETED`, `FAILED`, `CANCELLED` |
| `COMPLETED` | هیچ انتقالی |
| `FAILED` | هیچ انتقالی |
| `CANCELLED` | هیچ انتقالی |

Operation با `startRequest` در صورت نیاز از `PENDING` به `RUNNING` می‌رود؛ این
یک convenience coordination است و اجرای Provider نیست. `startOperation` نیز
به‌صورت explicit در دسترس است.

---

## 5. Creation و Association Contract

### 5.1 Operation Creation

```python
operation = lifecycle.createOperation(
    tenantId,
    "CHAT_OPERATION",
    requestedBy=userId,
    correlationId="corr-opaque",
    traceId="trace-opaque",
)
```

قواعد:

- `tenantId` و `requestedBy` در صورت وجود UUID معتبر هستند؛
- `operationType` با Grammar موجود B اعتبارسنجی می‌شود؛
- وضعیت آغازین همیشه `PENDING` است؛
- اگر correlation/trace خالی باشد، Entity B identifier opaque تولید می‌کند؛
- `operationId` اختیاری برای boundaryهای import/test است؛ duplicate همان Tenant
  با `AIOperationAlreadyRegistered` رد می‌شود؛
- Operation هیچ Provider، Model، Secret یا payload اجرایی نگهداری نمی‌کند.

### 5.2 Request Creation

```python
request = lifecycle.createRequest(
    tenantId,
    capabilityId,
    "GENERATE",
    operationId=operation.id,
    inputData={"prompt": "..."},
    idempotencyKey="tenant-scoped-key",
)
```

قواعد:

- وضعیت آغازین همیشه `PENDING` است؛
- `capabilityId` و `requestType` از B استفاده می‌شوند؛
- Operation اختیاری است، اما اگر داده شود باید در همان Tenant موجود و
  non-terminal باشد؛
- Request به Tenant دیگر یا Operation Tenant دیگر attach نمی‌شود؛
- `parentRequestId` در صورت وجود باید در همان Tenant موجود باشد؛
- اگر Parent به Operationی وابسته باشد، Child نمی‌تواند به Operation متفاوت
  وصل شود؛
- `operation.requestIds` و index داخلی G هر دو association را ثبت می‌کنند؛
- اگر F compose شده باشد، Capability باید در همان Tenant، active و پذیرای
  Request Type باشد؛
- G بدون Capability Registry نیز قابل compose است تا boundary B و adapter
  validation به‌صورت مستقل استفاده شوند.

تمام validationهای Creation قبل از mutate شدن aggregateها انجام می‌شوند؛ در
خطای Capability، Parent، Operation یا duplicate، association ناقص باقی نمی‌ماند.

---

## 6. Lifecycle API

### Request commands

| API | رفتار |
|---|---|
| `queueRequest(tenantId, requestId)` | `PENDING → QUEUED` |
| `startRequest(tenantId, requestId)` | `PENDING/QUEUED → RUNNING` و فعال‌سازی Operation pending |
| `completeRequest(tenantId, requestId)` | `RUNNING → COMPLETED` |
| `failRequest(..., errorCode=...)` | `RUNNING → FAILED` با error code |
| `cancelRequest(tenantId, requestId)` | انتقال به `CANCELLED` در صورت مجاز بودن |
| `retryRequest(tenantId, requestId)` | فقط `FAILED → QUEUED` و افزایش `retryCount` |

### Operation commands

| API | رفتار |
|---|---|
| `startOperation(tenantId, operationId)` | `PENDING → RUNNING` |
| `completeOperation(tenantId, operationId)` | فقط بعد از terminal childها و بدون child شکست‌خورده |
| `failOperation(tenantId, operationId)` | فقط بعد از terminal شدن همهٔ childها؛ child failed مجاز است |
| `cancelOperation(tenantId, operationId)` | childهای غیرterminal را cancel و سپس Operation را cancel می‌کند |

`now` اختیاری در commandها برای clock injection و test determinism است. اگر
Request به Operation متصل باشد و correlation/trace صریح برای Request ارسال نشود،
G identifierهای Operation را به‌عنوان trace context فرزند inherit می‌کند؛ مقدار
صریح Request بر مقدار inherited مقدم است. در Application واقعی، transaction و
persistence باید بیرون G مدیریت شود.

### Read API

- `getRequest` و `getOperation` برای read مدل Entity در boundary داخلی؛
- `describeRequest` و `describeOperation` برای read مدل safe و immutable؛
- `listRequests(tenantId, status=...)` و `listOperations(tenantId, status=...)`؛
- `operationForRequest` برای resolve کردن association؛
- همهٔ Readها Tenant را صریح دریافت می‌کنند.

---

## 7. Operation Completion Invariants

Operation می‌تواند `COMPLETED` شود اگر:

1. خود Operation در `PENDING` یا `RUNNING` باشد؛
2. تمام Requestهای child در یکی از وضعیت‌های terminal باشند؛
3. هیچ child در وضعیت `FAILED` نباشد؛
4. سپس state machine B انتقال را تأیید کند.

Operation می‌تواند `FAILED` شود اگر:

1. خود Operation در `PENDING` یا `RUNNING` باشد؛
2. تمام childها terminal باشند؛
3. childهای `FAILED` مجاز باشند؛
4. سپس state machine B انتقال را تأیید کند.

این طراحی اجازه نمی‌دهد Operation در حالی که Request فعال، queued یا pending
دارد ظاهراً تمام‌شده گزارش شود. اگر نیاز عملیاتی به abort فوری وجود داشته باشد،
`cancelOperation` command صریح childهای non-terminal را cancel می‌کند.

تکرار `cancelOperation`، `completeRequest` روی Request completed و commandهای
terminal یکسان، بدون تغییر اضافه idempotent هستند؛ transition متناقض همچنان با
Domain error رد می‌شود.

---

## 8. Idempotency و Duplicate Behavior

Idempotency فقط در مرز G و به‌صورت in-memory است:

```text
key = (tenantId, idempotencyKey)
value = (requestFingerprint, requestId)
```

Fingerprint شامل identity غیرsecret زیر است:

- Tenant و Capability ID؛
- Request Type، actor و source reference؛
- Priority؛
- Operation و Parent ID؛
- `inputData` به‌شکل canonical و فقط در SHA-256 داخلی؛
- Context token count.

خود `idempotencyKey` و `inputData` در `RequestDescriptor` expose نمی‌شوند و
fingerprint یا payload در Error message چاپ نمی‌شود.

رفتار:

| حالت | نتیجه |
|---|---|
| کلید برای Tenant جدید | Request جدید و ثبت index |
| همان Tenant/کلید با fingerprint برابر | replay همان Request موجود |
| همان Tenant/کلید با fingerprint متفاوت | `AIIdempotencyConflict` |
| همان کلید در Tenant دیگر | مستقل و مجاز |
| Request ID تکراری در همان Tenant | `AIRequestAlreadyRegistered` |

این index در crash، process restart یا چند instance مشترک باقی نمی‌ماند؛
Idempotency durable باید در P یا Persistence آینده با unique constraint و
transaction ساخته شود. G ادعای distributed deduplication ندارد.

---

## 9. Correlation، Trace و Error Contract

`AIRequest` و `AIOperation` correlation/trace را به‌عنوان identifierهای opaque
حمل می‌کنند. G آن‌ها را تولید/forward می‌کند اما semantic یا secret resolution
برای آن‌ها انجام نمی‌دهد. `RequestDescriptor` و `OperationDescriptor` این دو
identifier را برای observability boundary نشان می‌دهند.

خطاهای G:

| Exception | Code | کاربرد |
|---|---|---|
| `AIRequestNotFound` | `AI_REQUEST_NOT_FOUND` | Request در Tenant داده‌شده وجود ندارد |
| `AIOperationNotFound` | `AI_OPERATION_NOT_FOUND` | Operation در Tenant داده‌شده وجود ندارد |
| `AIRequestAlreadyRegistered` | `AI_REQUEST_ALREADY_REGISTERED` | duplicate Request ID |
| `AIOperationAlreadyRegistered` | `AI_OPERATION_ALREADY_REGISTERED` | duplicate Operation ID |
| `AIRequestLifecycleInvalid` | `AI_REQUEST_LIFECYCLE_INVALID` | command یا association نامعتبر |
| `AIOperationLifecycleInvalid` | `AI_OPERATION_LIFECYCLE_INVALID` | gate یا transition نامعتبر |
| `AIRequestCapabilityInvalid` | `AI_REQUEST_CAPABILITY_INVALID` | Capability خارجی، inactive یا type نامجاز |
| `AIIdempotencyConflict` | `AI_IDEMPOTENCY_CONFLICT` | یک key با fingerprint متفاوت |

Read خطای Tenant دیگر را به‌صورت NotFound برمی‌گرداند و existence آن Tenant را
لو نمی‌دهد. متن خطاهای Lifecycle وضعیت‌ها را برای debugging داخلی ارائه می‌کند؛
Application آینده باید logging و redaction را بیرون Domain policy کند.

---

## 10. Tenant Isolation و Security Boundary

- کلیدهای in-memory به‌صورت `(tenantId, entityId)` هستند؛
- هیچ Read/Transition بدون Tenant context وجود ندارد؛
- Request و Operation خارجی با همان ID در Tenant دیگر در این Scope قابل مشاهده
  نیستند؛
- Capability validation با `listCapabilities(tenantId)` و `resolveForRequest` در
  همان Tenant انجام می‌شود؛
- Parent و Operation association cross-tenant رد می‌شود؛
- Idempotency در هر Tenant جداست؛
- Descriptorها `inputData`، idempotency key، policy کامل و Secret را expose
  نمی‌کنند؛
- G Authorization واقعی User/Role را ادعا نمی‌کند؛ `requestedBy` فقط reference
  audit/trace است و K/Application باید permission را قبل از Create/Transition
  بررسی کند؛
- هیچ API Key، Password، Connection String یا Secret در Source Code، Descriptor
  یا Archive G تعریف نشده است.

---

## 11. Purity و Dependency Rules

`requestLifecycle.py` فقط به:

- Python standard library؛
- Entityهای B؛
- Exceptionهای Domain؛
- Value Objectهای B؛
- Contract اختیاری Capability Registry F

وابسته است.

ممنوع و در G استفاده‌نشده:

```text
Django / ORM / REST framework / HTTP / Redis / Queue / Worker
OpenAI / Ollama / Azure / Anthropic / vendor SDK
Network / filesystem execution / secret resolver / persistence
```

`RequestLifecycleService` به‌دلیل stateful بودن در حافظه، یک **Domain coordinator
قابل تست** است، نه Repository. خروجی commandها Entityهای B هستند تا adapter بیرونی
آن‌ها را persist یا publish کند.

---

## 12. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/services/requestLifecycle.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13RequestLifecycle.py

docs/Phases/Phase13/Phase13-G.md
docs/Phases/Phase13/Phase13-G-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

Compatibility aliasهای ارائه‌شده:

```text
RequestLifecycleService
AIRequestLifecycle
InMemoryRequestLifecycle
RequestLifecycleManager
OperationLifecycleService
```

Read modelهای immutable:

```text
RequestDescriptor
OperationDescriptor
```

---

## 13. Open Questions برای زیر‌فازهای بعدی

1. Persistence implementation برای unique `(tenantId, requestId)` و
   `(tenantId, operationId)` در کدام adapter/transaction boundary قرار گیرد؟
2. Idempotency durable با چه retention، TTL و cleanup policy اجرا شود؟
3. آیا یک idempotency key باید پس از terminal شدن Request برای همیشه replay شود
   یا با retention policy expire شود؟
4. Eventهای `AIRequestCreated/Started/Completed/Failed` در P یا O publish شوند؟
5. آیا Operation شکست‌خورده باید childهای active را `FAILED` یا `CANCELLED` کند؟
   G عمداً فقط explicit terminal gate و cancellation cascade را تثبیت کرده است.
6. Error code taxonomy برای Provider، Timeout، Quota و Permission در M/N/K چگونه
   با `AIRequest.errorCode` map شود؟
7. Authorization actor و transition permission دقیقاً در Application/K چگونه
   به G commandها inject شود؟
8. برای multi-process deployment، transaction و locking چه adapterی لازم است؟
9. آیا child Request باید در creation بدون `operationId` بتواند بعداً attach شود؟
   G association را immutable نگه داشته و چنین commandی اضافه نکرده است.

---

## 14. Acceptance Criteria

- [x] `AIRequest` و `AIOperation` واقعی B در lifecycle استفاده شدند؛
- [x] Request و Operation creation با state اولیهٔ شفاف وجود دارد؛
- [x] state transition معتبر و invalid transition قابل تشخیص است؛
- [x] زمان‌های creation، queue، start و completion نگهداری می‌شوند؛
- [x] Request error code در Failure نگهداری می‌شود؛
- [x] Request/Operation association و Parent association enforce می‌شود؛
- [x] Operation completion/failure gate بر اساس childهای terminal وجود دارد؛
- [x] Operation cancellation به‌صورت explicit childهای non-terminal را cancel می‌کند؛
- [x] Tenant isolation در Create/Read/Transition/List/Association وجود دارد؛
- [x] Correlation و Trace identifier در Entity و Descriptor حمل می‌شود؛
- [x] Idempotency replay و conflict در scope Tenant قابل تشخیص است؛
- [x] Idempotency key و payload در safe Descriptor expose نمی‌شود؛
- [x] F Capability Registry در صورت compose شدن، activity/type/tenant را validate می‌کند؛
- [x] Retry فقط command صریح requeue است و Retry Policy/Backoff اجرا نمی‌شود؛
- [x] هیچ ORM/API/Queue/Worker/Network/Vendor SDK/Secret وارد Domain G نشده است؛
- [x] Pure Test و regression B تا G آماده و اجرا شده است؛
- [x] محدودیت Django، Ruff و mypy دقیق ثبت شده است؛
- [x] Documentation، Verification، Gate و Archive مستقل ثبت شده‌اند.

**نتیجه:** `GREEN — Phase 13-H may begin.`
