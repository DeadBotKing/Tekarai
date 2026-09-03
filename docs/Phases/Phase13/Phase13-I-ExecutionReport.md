# Phase 13-I — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** I — Prompt Platform و Versioning  
**Gate:** `GREEN` برای Scope I  
**قرارداد قبلی:** [`Phase13-H.md`](Phase13-H.md)  
**قرارداد I:** [`Phase13-I.md`](Phase13-I.md)

---

## 1. خلاصهٔ تحویل

در زیر‌فاز I، Prompt به‌عنوان یک Platform Entity مستقل و Versioned پیاده‌سازی
شد. `PromptPlatformService` از Entityهای واقعی `AIPrompt` و `AIPromptVersion`
فاز B استفاده می‌کند و registry، activation، safe rendering و Output Schema
validation را بدون وابستگی به Provider یا Framework فراهم می‌کند.

خروجی‌های اصلی:

- Prompt registry با کلید `(tenantId, promptCode)`؛
- Create/Register/Lookup/List برای Prompt؛
- duplicate protection و Replace محدود Prompt Definition؛
- Version با شمارهٔ صریح یا auto-increment؛
- Version monotonic و جلوگیری از overwrite؛
- Active Version pointer با حداکثر یک Version فعال؛
- Prompt و Version activation/deactivation؛
- immutable version snapshots و deep-copy isolation؛
- Template variable declaration و safe format subset؛
- رد undeclared variable، attribute traversal، indexing، conversion و format spec؛
- Render فقط برای Prompt و Version فعال؛
- Missing/extra variable rejection؛
- اتصال Output Schema به `StructuredOutputSchema` فاز H؛
- Model Constraints passive، Provider-agnostic و بدون secret-like keys؛
- Safe `PromptDescriptor`، `PromptVersionDescriptor` و `RenderedPrompt`؛
- 10 تست اختصاصی I و regression ترکیبی B تا I؛
- Purity، Compile، Documentation Link، ZIP integrity و Extracted Archive test.

I Prompt را اجرا یا به Provider ارسال نمی‌کند. Prompt execution در L و اتصال
به Context در J/Application انجام خواهد شد.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/services/promptPlatform.py
backend/apps/ai/domain/services/__init__.py
```

Contractهای اصلی:

```text
PromptPlatformService
PromptDescriptor
PromptVersionDescriptor
RenderedPrompt
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

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای I:

```text
AIPromptAlreadyRegistered
AIPromptNotFound
AIPromptVersionAlreadyRegistered
AIPromptVersionNotFound
AIPromptLifecycleInvalid
AIPromptTemplateInvalid
AIPromptOutputSchemaInvalid
AIPromptVersionImmutable
```

### Tests

```text
backend/tests/unit/testPhase13PromptPlatform.py
```

### Documentation و Index

```text
docs/Phases/Phase13/Phase13-I.md
docs/Phases/Phase13/Phase13-I-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

---

## 3. رفتارهای Verification‌شده

### Prompt Registry

- Prompt با Tenant و Code ثبت می‌شود؛
- Code normalize و uppercase می‌شود؛
- duplicate در همان Tenant با `AIPromptAlreadyRegistered` رد می‌شود؛
- همان Code در Tenantهای مختلف مستقل است؛
- Prompt replacement فقط با همان Prompt ID مجاز است؛
- Prompt و Version readها deep-copy snapshot هستند؛
- List فقط Promptهای Tenant جاری را برمی‌گرداند؛
- Prompt inactive قابل Render عملیاتی نیست.

### Versioning

- Version صریح یا auto-increment ساخته می‌شود؛
- Version باید positive integer باشد؛
- Version number در Prompt/Tenant یکتا است؛
- duplicate Version با `AIPromptVersionAlreadyRegistered` رد می‌شود؛
- overwrite/replace Version با `AIPromptVersionImmutable` رد می‌شود؛
- Versionهای قدیمی باقی می‌مانند و حذف نمی‌شوند؛
- Active pointer به Version فعال متصل می‌شود؛
- همزمان فقط یک Version برای Prompt active است؛
- Deactivate Version pointer را در صورت نیاز پاک می‌کند؛
- ثبت مستقیم Version فعال بدون command صریح activation رد می‌شود.

### Template و Rendering

- Template variable باید declare شده باشد؛
- syntax ناقص یا variable تکراری رد می‌شود؛
- variable فقط Simple Identifier است؛
- attribute traversal مانند `{user.name}` رد می‌شود؛
- indexing مانند `{items[0]}` رد می‌شود؛
- conversion مانند `{value!r}` رد می‌شود؛
- format spec مانند `{value:>10}` رد می‌شود؛
- escaped braces پشتیبانی می‌شوند؛
- missing و extra render variable رد می‌شوند؛
- فقط active Prompt/Version قابل Render هستند؛
- `RenderedPrompt` متن را برای caller ارائه می‌کند اما در repr چاپ نمی‌کند.

### Output Schema و Model Constraints

- Prompt Version Output Schema با `StructuredOutputSchema` فاز H validate می‌شود؛
- Schema invalid به `AIPromptOutputSchemaInvalid` تبدیل می‌شود؛
- Schema fingerprint در Descriptor ثبت می‌شود؛
- Schema کامل در Descriptor expose نمی‌شود؛
- Model Constraints JSON-compatible و passive باقی می‌مانند؛
- keyهای `api_key`، `password`، `token`، `secret` و `connection_string` رد می‌شوند؛
- Prompt Platform Model Routing یا Provider selection انجام نمی‌دهد.

### Tenant و Security

- Prompt و Version در تمام lookupها Tenant-aware هستند؛
- Version Tenant دیگر NotFound می‌شود؛
- Version متعلق به Prompt دیگر قابل Activate نیست؛
- Cross-Tenant Render ممکن نیست؛
- Template و System Instruction در safe descriptor نیستند؛
- Rendered text فقط در result caller است و repr آن مخفی است؛
- هیچ Secret، API Key، Password یا Provider credential ذخیره نمی‌شود؛
- Authorization کامل User/Role و Approval workflow به K/Application/O واگذار است.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی I از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13PromptPlatform -v
```

نتیجهٔ نهایی:

```text
Ran 10 tests
OK
```

### 4.2 Regression ترکیبی B + C + D + E + F + G + H + I — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry \
  backend.tests.unit.testPhase13CapabilityRegistry \
  backend.tests.unit.testPhase13RequestLifecycle \
  backend.tests.unit.testPhase13ResponseLifecycle \
  backend.tests.unit.testPhase13PromptPlatform -v
```

نتیجهٔ نهایی:

```text
Ran 80 tests
OK
```

### 4.3 Python Compile — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13PromptPlatform.py
```

نتیجه:

```text
compileall: PASS
```

### 4.4 Domain Purity — PASS

کل `backend/apps/ai/domain` برای importهای زیر بررسی شد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic, boto3
```

نتیجه:

```text
domain purity scan: PASS
```

تست اختصاصی I نیز نبود Provider coupling و نمونهٔ actual secret مانند `sk-` یا
`Bearer` را بررسی می‌کند.

### 4.5 Documentation و Whitespace — PASS

```text
documentation link scan: PASS
git diff --check: PASS
Python whitespace scan: PASS
```

---

## 5. محدودیت‌ها و تست‌های اجرا نشده

### 5.1 Django Test Runner — BLOCKED BY ENVIRONMENT

Django در Environment فعلی نصب نیست:

```text
ModuleNotFoundError: No module named 'django'
```

بنابراین `python manage.py test` اجرا نشد. Pure Unit Test و regression B تا I
بدون Django موفق هستند.

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
- Whitespace و `git diff --check`.

### 5.3 Persistence و Concurrency — خارج از Scope I

Registry I in-memory است و durability، transaction، lock، multi-process
activation، cache invalidation و unique database constraint در این زیر‌فاز
ادعا نمی‌شوند. این موارد در adapter/Application آینده باید حفظ شوند.

### 5.4 Full JSON Schema و Provider Execution — خارج از Scope I

I فقط definition Output Schema را با Contract فاز H validate می‌کند. Full JSON
Schema، Provider Adapter، Network، Prompt execution، Context injection، Retry،
Timeout، Failover و Async در این Scope اجرا نشدند.

---

## 6. تصمیم‌های معماری ثبت‌شده

1. Entityهای `AIPrompt` و `AIPromptVersion` از B حفظ شدند؛
2. Prompt Registry با کلید `(tenantId, promptCode)` طراحی شد؛
3. Version با کلید `(tenantId, promptId, version)` یکتا است؛
4. Versionها immutable هستند و هر تغییر Version جدید می‌سازد؛
5. Activation از Registration جدا شد تا active pointer یک command صریح باشد؛
6. در هر Prompt حداکثر یک Version active است؛
7. Prompt inactive حتی با active Version قابل Render نیست؛
8. Template فقط declared simple variables را قبول می‌کند؛
9. Attribute/index/format/conversion expressions برای جلوگیری از traversal رد
   می‌شوند؛
10. Render values باید دقیقاً با variables اعلام‌شده برابر باشند؛
11. Output Schema از Contract H مصرف می‌شود اما مالکیت versioned آن در I است؛
12. Model Constraints passive هستند و I routing یا Provider selection انجام
   نمی‌دهد؛
13. Read Modelها Template، System Instruction، Schema کامل، Constraint values و
   Secret را expose نمی‌کنند؛
14. Entity snapshotها deep-copy هستند تا caller Registry state را دور نزند؛
15. Permission/Approval، Persistence، Audit، Provider و Async به زیر‌فازهای
   مربوط واگذار شده‌اند؛
16. هیچ Framework، Vendor، Network یا Secret dependency وارد Domain I نشده است.

---

## 7. Gate نهایی I

| معیار | وضعیت |
|---|---|
| Prompt Platform در ساختار واقعی Tekarai | PASS |
| استفاده از `AIPrompt` و `AIPromptVersion` فاز B | PASS |
| Tenant-aware Prompt Registry | PASS |
| Prompt duplicate/replace boundary | PASS |
| Monotonic Versioning | PASS |
| Version immutability | PASS |
| Active Version pointer | PASS |
| Prompt/Version activation و deactivation | PASS |
| Declared variable validation | PASS |
| Safe template rendering | PASS |
| Missing/extra variable rejection | PASS |
| H Output Schema integration | PASS |
| Model Constraints safe/passive | PASS |
| Safe immutable descriptors | PASS |
| Tenant Isolation | PASS |
| Domain/Vendor/Framework purity | PASS |
| Pure I tests | PASS — 10/10 |
| Combined B+C+D+E+F+G+H+I tests | PASS — 80/80 |
| Compile/Docs/Whitespace checks | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Persistence/Provider/Async execution | N/A — خارج از Scope I |
| Documentation | PASS |
| ZIP مستقل I و SHA-256 | PASS — مسیر در بخش 8 |

**نتیجه:** `GREEN — Phase 13-J may begin.`

---

## 8. Archive تحویل مستقل I

Archive مستقل I پس از Verification ساخته و بررسی شد:

```text
/home/user/Tekarai-Phase13-I.zip
```

SHA-256 canonical در sidecar زیر ثبت شده است:

```text
/home/user/Tekarai-Phase13-I.zip.sha256
```

برای جلوگیری از self-reference، checksum canonical فقط در sidecar و Delivery
Message اعلام می‌شود و در خود Report تکرار نمی‌شود. ZIP با `unzip -tq` بررسی و
پس از Extract، regression B تا I روی محتوای Archive اجرا می‌شود.

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```
