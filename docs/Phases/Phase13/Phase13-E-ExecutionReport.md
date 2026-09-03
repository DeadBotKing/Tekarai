# Phase 13-E — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** E — Model Registry و Model Routing  
**Gate:** `GREEN` برای Scope E  
**قرارداد قبلی:** [`Phase13-D.md`](Phase13-D.md)  
**قرارداد E:** [`Phase13-E.md`](Phase13-E.md)

---

## 1. خلاصهٔ تحویل

زیر‌فاز E در ساختار واقعی Tekarai پیاده‌سازی شد. `ModelRegistry`، Entity
`AIModel` از B را با `ProviderRegistry` از D و `ProviderCapabilities` از C
compose می‌کند، بدون اینکه Provider خاص یا زیرساخت اجرایی به Core AI وارد شود.

تحویل شامل این موارد است:

- ثبت Tenant-aware مدل با مالکیت enforce‌شدهٔ Provider؛
- Unique scope برابر `(tenantId, providerId, modelCode)`؛
- Duplicate protection و Replace صریح؛
- Resolve دقیق Provider/Model و Resolve با Code یکتا؛
- Model/Provider activation enforcement؛
- Listing عملیاتی و مدیریتی؛
- Non-sensitive immutable `ModelDescriptor`؛
- بررسی Model Type، Business Capability و Provider Feature؛
- بررسی Streaming، Tools، Vision، Embedding و Context Window؛
- `ModelRoutingRequest` و `ModelRoutingPolicy`؛
- Preferred، Default و Ordered Fallback تصمیمی؛
- `RoutingDecision` deterministic و قابل ردیابی؛
- Unit Testهای Pure، Offline و بدون Django/Database/Network/SDK؛
- مستندات Contract و گزارش مستقل E.

E هیچ Provider را اجرا نمی‌کند و Retry/Failover واقعی، Persistence، API، Queue،
Secret Resolution و Observability اضافه نمی‌کند.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/registries/modelRegistry.py
backend/apps/ai/domain/registries/__init__.py
```

`modelRegistry.py` شامل این Contractهاست:

```text
ModelRegistration
ModelDescriptor
ModelRouteTarget
ModelRoutingRequest
ModelRoutingPolicy
RoutingDecision
ModelRegistry
```

Compatibility aliasها نیز ارائه شده‌اند:

```text
AIModelRegistry
InMemoryModelRegistry
RegisteredModel
ModelSelectionRequest
RoutingRequest
RoutingPolicy
ModelFallbackPolicy
ModelRoutingDecision
```

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای E:

```text
AIModelAlreadyRegistered
AIModelNotRegistered
AIModelInactive
AIModelRegistrationInvalid
AIModelProviderOwnershipInvalid
AIModelAmbiguous
AIRoutingPolicyInvalid
AIRoutingNoMatch
```

`AIProviderInactive` از D برای Provider inactive همچنان استفاده می‌شود.

### Tests

```text
backend/tests/unit/testPhase13ModelRegistry.py
```

### Documentation

```text
docs/Phases/Phase13/Phase13-E.md
docs/Phases/Phase13/Phase13-E-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

هیچ فایل ORM، Migration، API، Queue، Provider Adapter واقعی، Secret Store یا
Vendor SDK در E اضافه نشد.

---

## 3. Verification رفتارهای E

### Registration و Ownership

- `AIModel` تنها زمانی ثبت می‌شود که Provider در همان Tenant در D ثبت شده باشد؛
- `model.providerId` باید دقیقاً با Provider ID همان Binding برابر باشد؛
- Provider Code mismatch و Cross-Tenant ownership رد می‌شود؛
- Provider Code در صورت نیاز از روی Provider ID فقط وقتی derive می‌شود که دقیقاً
  یک مالک در همان Tenant وجود داشته باشد؛
- Duplicate در `(tenant, provider, modelCode)` بدون `replace=True` رد می‌شود؛
- همان Model Code در دو Provider یا دو Tenant مجاز است و با Scope اشتباه merge
  نمی‌شود.

### Lookup و Activation

- تمام Lookupها Tenant را در کلید دارند؛
- `resolveModel(tenant, provider, model)` فقط Model فعال و Provider فعال را
  برمی‌گرداند؛
- Model inactive با `AIModelInactive` رد می‌شود؛
- Provider inactive با `AIProviderInactive` رد می‌شود؛
- `listModels(activeOnly=True)` Model inactive یا Provider inactive را حذف می‌کند؛
- `activeOnly=False` برای مدیریت، Descriptor را با `providerIsActive=False` نگه
  می‌دارد؛
- Resolve با Model Code تنها، در صورت وجود همان Code در چند Provider،
  `AIModelAmbiguous` می‌دهد و حدس نمی‌زند؛
- Provider unregister/replacement رکورد مدل را برای inspection حفظ می‌کند اما
  مدل orphan operational قابل استفاده نیست.

### Routing

- Candidate فقط از همان Tenant و Binding مالک معتبر انتخاب می‌شود؛
- Model Type و Business Capability بررسی می‌شوند؛
- Provider Feature از `ProviderCapabilities` بررسی می‌شود؛
- Model flag و Provider feature برای Streaming، Tools، Vision و Embedding با هم
  بررسی می‌شوند؛
- Model و Provider Context Window با `minimumContextWindow` مقایسه می‌شوند؛
- مرتب‌سازی مستقل از Register order با `(providerCode, modelCode, modelType,
  modelId)` انجام می‌شود؛
- Preferred در صورت eligible بودن اولویت دارد؛
- Preferred نامعتبر با Fallback خاموش، انتخاب تصادفی مدل دیگر نمی‌کند؛
- Fallbackهای صریح به ترتیب Policy بررسی می‌شوند؛
- Default صریح بررسی می‌شود؛
- بدون Target صریح، انتخاب اول deterministic با reason مشخص انجام می‌شود؛
- Routing فقط `RoutingDecision` می‌سازد و هیچ Provider call یا Retry انجام نمی‌دهد.

### Security Boundary

- `ModelDescriptor` frozen است؛
- Descriptor و Decision شامل metadata مدل، configuration reference، Token Rate،
  Adapter و Secret نیستند؛
- `ModelRegistration.model` با `repr=False` از logging ناخواستهٔ Entity جلوگیری
  می‌کند؛
- Domain E هیچ import مربوط به Framework، HTTP، Cache یا Vendor ندارد.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی E از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13ModelRegistry -v
```

نتیجهٔ نهایی:

```text
Ran 12 tests
OK
```

در اجرای اول E، دو خطای تستی مشاهده شد:

1. Fixture تست برای مدل Provider محدود، `providerId` Provider غنی را نگه داشته بود؛
   بنابراین Ownership Guard درستاً آن را رد کرد؛
2. Fixture Policy از Code تک‌حرفی استفاده کرده بود، در حالی که Contract B حداقل
   طول Code را enforce می‌کند.

هر دو مورد در خود تست اصلاح شدند؛ هیچ bypassای در Ownership یا Code Validation
اضافه نشد و اجرای نهایی 12/12 سبز شد.

### 4.2 تست ترکیبی B + C + D + E از ریشه — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry -v
```

نتیجه:

```text
Ran 39 tests
OK
```

### 4.3 تست ترکیبی از داخل `backend` — PASS

```bash
cd /home/user/Tekarai/backend
PYTHONPATH=. python -m unittest \
  tests.unit.testPhase13Domain \
  tests.unit.testPhase13ProviderPort \
  tests.unit.testPhase13ProviderRegistry \
  tests.unit.testPhase13ModelRegistry -v
```

نتیجه:

```text
Ran 39 tests
OK
```

این اجرا مستقل از Current Working Directory بودن Source path تست E را نیز
تأیید کرد.

### 4.4 Python Compile — PASS

```bash
cd /home/user/Tekarai
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13ModelRegistry.py
```

نتیجه:

```text
compileall: PASS
```

### 4.5 Domain Purity Scan — PASS

کل `backend/apps/ai/domain` برای importهای زیر بررسی شد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic
```

نتیجه:

```text
domain purity scan: PASS
```

### 4.6 Whitespace — PASS

```bash
git diff --check
```

نتیجه:

```text
git diff --check: PASS
```

### 4.7 Documentation Link Scan — PASS

Local linkهای `docs/Phases/Phase13/` بعد از ایجاد Execution Report بررسی شدند و
Link شکسته‌ای باقی نماند.

در یک اجرای زودهنگام، پیش از ایجاد همین Execution Report، Scanner لینک گزارش را
Missing اعلام کرد؛ Report ایجاد شد و Scan نهایی PASS شد.

### 4.8 Verification خود Archive — PASS

Archive با `unzip -tq` بررسی و سپس در یک مسیر موقت Extract شد. تست ترکیبی از روی
محتوای Extract‌شده نیز سبز شد:

```text
archive integrity: PASS
Ran 39 tests
OK
```

---

## 5. تست‌های اجرا نشده و دلیل دقیق

### 5.1 Django Test Runner — BLOCKED BY ENVIRONMENT

دستور اجراشده:

```bash
cd /home/user/Tekarai/backend
python manage.py test tests.unit.testPhase13ModelRegistry
```

خروجی:

```text
ModuleNotFoundError: No module named 'django'

ImportError: Couldn't import Django. Activate the project virtual environment
and install dependencies with: python -m pip install -r requirements/development.txt
```

بنابراین Django Test Runner و Full Project Suite در محیط فعلی قابل اجرا نیستند.
Pure Unit Testهای E و تست ترکیبی B+C+D+E بدون Django با موفقیت اجرا شدند.

### 5.2 Ruff و mypy — TOOLING NOT INSTALLED

```text
ruff: NOT INSTALLED
mypy: NOT INSTALLED
```

این ابزارها در Environment فعلی وجود ندارند؛ Compile، Unit Test، Purity و
Whitespace Scan جایگزین سبک اجراشده هستند.

### 5.3 Full `unittest discover` — BLOCKED BY EXISTING PROJECT DEPENDENCIES

برای بررسی سطح کل Repository این دستور نیز اجرا شد:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests -p 'test*.py' -v
```

تست‌های Pure مربوط به B/C/D/E در همین اجرا سبز بودند، اما Discovery در مجموع با
37 خطای Import متوقف شد؛ علت همه در Environment فعلی نبودن Django/Channels و
وابستگی‌های پروژه بود، از جمله:

```text
ModuleNotFoundError: No module named 'django'
ModuleNotFoundError: No module named 'channels'
```

این Failure به کد E مربوط نیست. تست جایگزین سبک و قابل اجرای E همان تست‌های
اختصاصی 12/12 و Combined B+C+D+E با 39/39 است که بدون Framework اجرا شدند.

### 5.4 Real Provider و Integration — N/A / خارج از Scope E

موارد زیر عمداً اجرا نشدند:

- Provider Adapter واقعی؛
- Network و Secret Store؛
- هر Vendor SDK؛
- Database-backed Model Registry؛
- API و Admin؛
- Queue/Worker/Async؛
- Retry، Timeout، Circuit Breaker و Failover واقعی؛
- Cost/Latency/Quality based routing؛
- Application Permission و Audit integration.

این موارد به زیر‌فازهای مرتبط بعدی واگذار شده‌اند و نبودشان Failure E محسوب
نمی‌شود.

---

## 6. دستور اجرای دستی کاربر

### Linux/macOS/Git Bash

```bash
cd /path/to/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13ModelRegistry -v

PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry -v
```

### Windows PowerShell از ریشهٔ Repository

```powershell
Set-Location C:\path\to\Tekarai
$env:PYTHONPATH = "backend"
python -m unittest backend.tests.unit.testPhase13ModelRegistry -v
python -m unittest `
  backend.tests.unit.testPhase13Domain `
  backend.tests.unit.testPhase13ProviderPort `
  backend.tests.unit.testPhase13ProviderRegistry `
  backend.tests.unit.testPhase13ModelRegistry -v
```

### Windows PowerShell از داخل `backend`

```powershell
Set-Location C:\path\to\Tekarai\backend
$env:PYTHONPATH = "."
python -m unittest tests.unit.testPhase13ModelRegistry -v
```

### در صورت آماده‌سازی Environment کامل

```bash
python -m venv backend/.venv
# Linux/macOS: source backend/.venv/bin/activate
# Windows:     backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements/development.txt
cd backend
python manage.py test tests.unit.testPhase13ModelRegistry
```

اگر تست دستی خطا داد، کاربر باید این موارد را کامل ارسال کند:

```text
کل stdout و stderr خطا
python --version
python -m pip freeze
نام سیستم‌عامل و اینکه دستور از root یا backend اجرا شده است
```

هیچ API Key، Token، Password، Secret، Connection String یا فایل `.env` ارسال
نشود. پس از دریافت خروجی، ابتدا مشخص می‌شود خطا از dependency، path، import،
Contract، Fixture، Ownership، Activation یا Routing است؛ سپس کد/تست اصلاح،
Verification تکرار و Archive جدید با Checksum جدید ساخته خواهد شد.

---

## 7. تصمیم‌های معماری ثبت‌شده

1. Model Registry در Domain خالص و in-memory است تا Persistence زودهنگام وارد E
   نشود؛
2. کلید شامل Tenant و Provider ownership است و Model Code به‌تنهایی کافی نیست؛
3. `providerId` مرجع مالکیت Entity است و `providerCode` فقط مسیر resolve به D را
   مشخص می‌کند؛
4. Provider Registry همچنان تنها مالک Runtime Adapter است؛
5. Provider inactive و Model inactive از consumption عملیاتی جدا هستند؛
6. Descriptor/Decision کمینه و غیرحساس‌اند؛
7. Capability business از Provider feature جداست، اما Routing هر دو Contract را
   هم‌زمان بررسی می‌کند؛
8. Routing بر اساس registry state و active flags است و Health call/Network ندارد؛
9. مرتب‌سازی ثابت از Register order مستقل است؛
10. Preferred بدون Fallback، strict است و مدل دیگری را silent انتخاب نمی‌کند؛
11. Fallback Policy فقط candidate selection است و Retry/Failover واقعی نیست؛
12. انتخاب Cost، Latency و Quality به Scopeهای Usage/Observability/Governance
    واگذار شده است؛
13. Resolve با Model Code تکراری بدون Provider، Ambiguous است و از انتخاب حدسی
    جلوگیری می‌شود؛
14. Permission واقعی User/Role در Application/Governance باقی می‌ماند و E ادعای
    Authorization کامل نمی‌کند؛
15. هیچ نام Vendor یا SDK خاصی به Core AI اضافه نشد.

---

## 8. Gate نهایی E

| معیار | وضعیت |
|---|---|
| اتصال `AIModel` به `ProviderRegistry` | PASS |
| Tenant-aware Model Lookup | PASS |
| Unique `(tenantId, providerId, modelCode)` | PASS |
| Provider Ownership Validation | PASS |
| Duplicate و Explicit Replace | PASS |
| Model/Provider Activation Guard | PASS |
| Non-sensitive Immutable Descriptor | PASS |
| Model Type و Business Capability | PASS |
| Streaming/Tools/Vision/Embedding | PASS |
| Context Window Contract | PASS |
| Preferred/Default/Fallback Policy | PASS |
| Deterministic Provider-agnostic Routing | PASS |
| Vendor/Framework Domain Purity | PASS |
| Pure E Tests | PASS — 12/12 |
| Combined B+C+D+E Tests | PASS — 39/39 |
| Compile/Whitespace/Docs Scan | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Real Provider/Network/Persistence | N/A — خارج از Scope E |
| Documentation | PASS |
| ZIP تحویل E | PASS — مسیر در بخش 9 |

**نتیجه:** `GREEN — زیر‌فاز F می‌تواند آغاز شود.`

---

## 9. Archive تحویل

پس از Verification نهایی، Archive مستقل E در این مسیر ساخته و بررسی شد:

```text
/home/user/Tekarai-Phase13-E.zip
```

SHA-256 فایل ZIP تحویلی:

```text
e7f646fff7bae67322942aac8ed646ab4a1fafcd3c13ec3acb72488612f51547
```

فایل sidecar همان checksum:

```text
/home/user/Tekarai-Phase13-E.zip.sha256
```

Checksum در این Report کاری و sidecar، Delivery Metadata نهایی است؛ ZIP از
Workspace نهایی قبل از درج همین مقدار در متن Report بسته‌بندی شده است. برای
اعتبارسنجی Artifact، مقدار sidecar یا همین SHA-256 را با خروجی `sha256sum`/
`Get-FileHash` مقایسه کنید.

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```
