# Phase 13-G — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** G — Request و Operation Lifecycle  
**Gate:** `GREEN` برای Scope G  
**قرارداد قبلی:** [`Phase13-F.md`](Phase13-F.md)  
**قرارداد G:** [`Phase13-G.md`](Phase13-G.md)

---

## 1. خلاصهٔ تحویل

در زیر‌فاز G یک lifecycle coordinator pure و Tenant-aware برای Entityهای واقعی
`AIRequest` و `AIOperation` از B ساخته شد. پیاده‌سازی به Provider، ORM، API،
Queue، Worker، Network یا Secret Store وابسته نیست و فقط مسئول هماهنگی state و
association در مرز Domain است.

تحویل‌های اصلی:

- `RequestLifecycleService` با state in-memory و Tenant-scoped indexes؛
- Operation و Request creation با status اولیهٔ `PENDING`؛
- association اختیاری Request به Operation و association Parent؛
- Request state transition برای queue/start/complete/fail/cancel؛
- explicit requeue برای Request شکست‌خورده با `retryCount`؛
- Operation start/complete/fail/cancel؛
- completion/failure gate بر اساس terminal child Requestها؛
- cancellation cascade کنترل‌شده از Operation به childهای غیرterminal؛
- timestamp و stable error code؛
- Correlation و Trace identifier با inheritance از Operation به Request متصل؛
- Tenant isolation در Create/Read/Transition/List/Association؛
- idempotency replay و conflict در scope `(tenantId, idempotencyKey)`؛
- Capability validation اختیاری با `CapabilityRegistry` فاز F؛
- `RequestDescriptor` و `OperationDescriptor` frozen و بدون input/idempotency
  secret surface؛
- خطاهای Domain-specific قابل تشخیص؛
- 11 تست اختصاصی G و regression ترکیبی B تا G؛
- Documentation، purity، compile، checksum و extracted-archive verification.

G retry policy، timeout، failover، async execution و Provider execution را
پیاده‌سازی نمی‌کند و این مرز برای زیر‌فازهای M و P حفظ شده است.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/services/requestLifecycle.py
backend/apps/ai/domain/services/__init__.py
```

Contractهای اصلی:

```text
RequestLifecycleService
RequestDescriptor
OperationDescriptor
```

Compatibility aliasها:

```text
AIRequestLifecycle
InMemoryRequestLifecycle
RequestLifecycleManager
OperationLifecycleService
```

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای G:

```text
AIRequestNotFound
AIOperationNotFound
AIRequestAlreadyRegistered
AIOperationAlreadyRegistered
AIRequestLifecycleInvalid
AIOperationLifecycleInvalid
AIRequestCapabilityInvalid
```

`AIIdempotencyConflict` موجود در B برای conflict مربوط به G استفاده شد.

### Tests

```text
backend/tests/unit/testPhase13RequestLifecycle.py
```

### Documentation و Index

```text
docs/Phases/Phase13/Phase13-G.md
docs/Phases/Phase13/Phase13-G-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

---

## 3. رفتارهای Verification‌شده

### Creation و Association

- Operation با `PENDING` ساخته می‌شود؛
- Request با `PENDING` ساخته می‌شود؛
- Request می‌تواند به Operation همان Tenant متصل شود؛
- `operation.requestIds` و index داخلی association را حفظ می‌کنند؛
- Parent در همان Tenant resolve می‌شود؛
- Parent و Child نمی‌توانند به دو Operation متفاوت متصل شوند؛
- association با Operation terminal رد می‌شود؛
- همهٔ validationهای Create پیش از mutation aggregate انجام می‌شوند.

### Request Lifecycle

- `PENDING → QUEUED → RUNNING → COMPLETED`؛
- `RUNNING → FAILED` با `errorCode` پایدار؛
- `PENDING/QUEUED/RUNNING → CANCELLED`؛
- `FAILED → QUEUED` فقط با command صریح `retryRequest`؛
- `retryCount` در requeue افزایش می‌یابد؛
- transition نامعتبر با `AIRequestLifecycleInvalid` گزارش می‌شود؛
- Request شروع‌شده، Operation pending مربوط به خود را به running می‌برد؛
- timestampهای Queue/Start/Completion با clock تزریق‌پذیر قابل تست هستند.

### Operation Lifecycle

- `PENDING → RUNNING`؛
- `RUNNING → COMPLETED/FAILED/CANCELLED`؛
- Completion فقط وقتی ممکن است که همهٔ childها terminal و هیچ childی failed
  نباشد؛
- Failure فقط وقتی ممکن است که همهٔ childها terminal باشند؛ child failed برای
  Failure Operation مجاز است؛
- Cancellation childهای non-terminal را cancel می‌کند؛
- command terminal یکسان مانند تکرار cancel، بدون mutation اضافی idempotent است؛
- Operation transition نامعتبر با `AIOperationLifecycleInvalid` گزارش می‌شود.

### Idempotency و Duplicate

- همان Tenant و همان key با fingerprint برابر، replay همان Request را می‌دهد؛
- همان Tenant و key با fingerprint متفاوت، `AIIdempotencyConflict` می‌دهد؛
- همان key در Tenant دیگر مستقل است؛
- duplicate Request/Operation ID در scope Tenant با error مشخص رد می‌شود؛
- fingerprint فقط hash identity است و key/payload در Descriptor یا error expose
  نمی‌شود؛
- index عمداً process-local است و ادعای durable/distributed deduplication ندارد.

### Tenant و Capability

- Read و Transition بدون Tenant صحیح، `NotFound` می‌دهند؛
- List فقط Entityهای Tenant درخواست‌شده را برمی‌گرداند؛
- Cross-tenant Parent/Operation association ممکن نیست؛
- در صورت compose شدن با F، Capability باید متعلق به همان Tenant، active و
  پذیرای Request Type باشد؛
- Capability خارجی، inactive یا request type نامجاز با
  `AIRequestCapabilityInvalid` ترجمه می‌شود؛
- Permission User/Role جعل نشده و به K/Application واگذار است.

### Security و Safe Read Model

- `RequestDescriptor` و `OperationDescriptor` immutable هستند؛
- `inputData`، idempotency key و policy کامل در Descriptor نیستند؛
- correlation/trace فقط opaque identifier هستند؛
- هیچ Secret، API Key، Password یا Connection String در G تعریف نشده است؛
- هیچ Provider خاصی در Lifecycle hard-code نشده است.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی G از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13RequestLifecycle -v
```

نتیجهٔ نهایی:

```text
Ran 11 tests
OK
```

Test coverage شامل Creation، Association، State Transition، Timestamp،
Completion Gate، Error، Retry، Cancellation Cascade، Tenant Isolation،
Idempotency، Capability Composition، Parent Association، Safe Descriptor و
Purity Boundary است.

### 4.2 Regression ترکیبی B + C + D + E + F + G — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry \
  backend.tests.unit.testPhase13CapabilityRegistry \
  backend.tests.unit.testPhase13RequestLifecycle -v
```

نتیجهٔ نهایی:

```text
Ran 59 tests
OK
```

### 4.3 Python Compile — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13RequestLifecycle.py
```

نتیجه:

```text
compileall: PASS
```

### 4.4 Domain Purity — PASS

Importهای Framework، HTTP، Redis، Queue و Vendor در Domain بررسی شدند:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic, boto3
```

نتیجه:

```text
domain purity scan: PASS
```

تست اختصاصی G همچنین نبود import/provider coupling و نبود عبارت‌های
`api_key`/`secret_key` را در implementation بررسی می‌کند.

### 4.5 Documentation Link Scan — PASS

Local Linkهای Markdown در `docs/Phases/Phase13/` بررسی شدند و broken link باقی
نماند.

### 4.6 Whitespace — PASS

```bash
git diff --check
```

Trailing whitespace در فایل‌های Python تغییرکرده نیز scan شد و PASS بود.

---

## 5. محدودیت‌ها و تست‌های اجرا نشده

### 5.1 Django Test Runner — BLOCKED BY ENVIRONMENT

Django در Environment فعلی نصب نیست:

```text
ModuleNotFoundError: No module named 'django'
```

بنابراین `python manage.py test` اجرا نشد. تست‌های Pure، regression، compile و
purity بدون Django با موفقیت اجرا شدند. این محدودیت محیط است و failure قراردادی
G نیست.

### 5.2 Ruff و mypy — TOOLING NOT INSTALLED

```text
ruff: NOT INSTALLED
mypy: NOT INSTALLED
```

جایگزین‌های اجراشده:

- Pure `unittest`؛
- `compileall`؛
- Domain Purity Scan؛
- Documentation Link Scan؛
- `git diff --check` و Python whitespace scan.

### 5.3 Persistence/Concurrency — خارج از Scope G

Lifecycle state در یک Service in-memory است و برای process-local pure testing
طراحی شده است. Durability، locking، transaction، concurrent duplicate race و
multi-process idempotency در G ادعا نمی‌شوند و باید در Persistence/Application
adapter آینده پوشش داده شوند.

### 5.4 Provider/Async/Policy — خارج از Scope G

عمداً اجرا یا ساخته نشد:

- Provider SDK و Network؛
- Queue و Worker؛
- Retry schedule، backoff و timeout؛
- Failover و circuit breaker؛
- Response/Structured Output؛
- Usage/Cost/Audit/Monitoring persistence؛
- Authorization واقعی و Permission Filtering؛
- Secret resolution و API Key؛
- Database migration و API endpoint.

---

## 6. تصمیم‌های معماری ثبت‌شده

1. `AIRequest` و `AIOperation` موجود B منبع state model هستند و G state machine
   دومی ایجاد نمی‌کند؛
2. `RequestLifecycleService` یک coordinator pure و in-memory است، نه Repository؛
3. Tenant context در تمام public APIهای Read و Transition الزامی است؛
4. association به Operation در G immutable است و attach بعدی عمداً اضافه نشده؛
5. شروع child Request می‌تواند Operation pending را به running ارتقا دهد تا
   state aggregate سازگار بماند؛
6. Operation completion/failure پیش از transition، وضعیت همهٔ childها را gate
   می‌کند؛
7. فقط cancellation cascade دارد؛ failure/complete childها را بی‌صدا mutate
   نمی‌کنند؛
8. retry در G فقط explicit requeue است و هیچ policy، delay یا provider retry
   اجرا نمی‌شود؛
9. idempotency key در `(tenantId, key)` scoped است و fingerprint از payload را
   فقط برای مقایسهٔ hash استفاده می‌کند؛
10. safe Descriptorها input و idempotency key را expose نمی‌کنند؛
11. correlation/trace opaque باقی می‌مانند و G آن‌ها را Secret تلقی یا resolve
    نمی‌کند؛
12. در صورت وجود F Registry، Capability ownership/activity/request-type قبل از
    Create enforce می‌شود؛ در نبود آن outer adapter باید این validation را بدهد؛
13. خطای Tenant دیگر به شکل NotFound رفتار می‌کند تا existence افشا نشود؛
14. Authorization واقعی User/Role، Persistence، Audit، Async و Provider boundary
    به Phaseهای مربوطه واگذار شده‌اند؛
15. هیچ dependency اختصاصی Vendor یا Framework وارد Domain G نشده است.

---

## 7. Gate نهایی G

| معیار | وضعیت |
|---|---|
| استفاده از Entityهای واقعی `AIRequest`/`AIOperation` از B | PASS |
| Creation و initial state شفاف | PASS |
| Request state transitions | PASS |
| Operation state transitions | PASS |
| Timestamp و error code | PASS |
| Request/Operation association | PASS |
| Parent association و cross-operation guard | PASS |
| Operation completion/failure gate | PASS |
| Cancellation cascade | PASS |
| Tenant Isolation | PASS |
| Correlation و Trace propagation | PASS |
| Idempotency replay/conflict | PASS |
| Safe immutable descriptors | PASS |
| Optional Capability Registry validation با F | PASS |
| Domain-specific errors | PASS |
| Pure/Vendor/Framework boundary | PASS |
| Pure G tests | PASS — 11/11 |
| Combined B+C+D+E+F+G tests | PASS — 59/59 |
| Compile/Docs/Whitespace checks | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Persistence/Async/Provider execution | N/A — خارج از Scope G |
| Documentation | PASS |
| ZIP مستقل G و SHA-256 | PASS — مسیر در بخش 8 |

**نتیجه:** `GREEN — Phase 13-H may begin.`

---

## 8. Archive تحویل مستقل G

Archive مستقل G پس از Verification در این مسیر ساخته و بررسی شد:

```text
/home/user/Tekarai-Phase13-G.zip
```

SHA-256 نهایی فایل ZIP در فایل sidecar زیر ثبت می‌شود:

```text
/home/user/Tekarai-Phase13-G.zip.sha256
```

برای جلوگیری از self-reference، مقدار canonical checksum فقط در sidecar و
Delivery Message اعلام می‌شود و در خود Report تکرار نمی‌شود. Integrity خود ZIP
با `unzip -tq` و تست Extract‌شدهٔ regression بررسی می‌شود.

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```
