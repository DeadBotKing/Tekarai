# Phase 13-F — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** F — Capability Registry  
**Gate:** `GREEN` برای Scope F  
**قرارداد قبلی:** [`Phase13-E.md`](Phase13-E.md)  
**قرارداد F:** [`Phase13-F.md`](Phase13-F.md)

---

## 1. خلاصهٔ تحویل

Capability Registry زیر‌فاز F در ساختار واقعی Tekarai ساخته شد. این Registry
Entity `AICapability` از B را Tenant-aware مدیریت می‌کند و برای Request Type
Policy و Model Integration به Contractهای E متصل می‌شود.

خروجی‌های اصلی:

- `CapabilityRegistry` با کلید `(tenantId, capabilityCode)`؛
- Register/Resolve/Describe/List/Activation/Unregister؛
- Duplicate protection و Replace صریح؛
- پشتیبانی از Capabilityهای استاندارد و `CUSTOM_*`؛
- Request Type allowlist از مسیر `AICapability.policy`؛
- Descriptor غیرحساس و Immutable؛
- Model Declaration check بر اساس `AIModel.inputCapability` و
  `AIModel.outputCapability`؛
- Listing مدل‌های سازگار یک Capability از `ModelRegistry` E؛
- Capability-first Routing با حفظ Routing Policy E؛
- خطای مستقل برای Routing بدون Model مناسب؛
- تست Pure، Offline و Framework/Vendor-free؛
- Documentation و Verification مستقل.

F هیچ Provider را اجرا نمی‌کند و Persistence، API، Queue، Retry، Failover،
Secret Resolution، Vendor SDK یا Permission واقعی User/Role اضافه نمی‌کند.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/registries/capabilityRegistry.py
backend/apps/ai/domain/registries/__init__.py
```

Contractهای اضافه‌شده:

```text
CapabilityRegistration
CapabilityDescriptor
CapabilityRoutingRequest
CapabilityRegistry
```

Compatibility aliasها:

```text
AICapabilityRegistry
InMemoryCapabilityRegistry
RegisteredCapability
CapabilitySelectionRequest
CapabilityRouting
```

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای F:

```text
AICapabilityAlreadyRegistered
AICapabilityNotRegistered
AICapabilityInactive
AICapabilityRegistrationInvalid
AICapabilityPolicyInvalid
AICapabilityRequestTypeUnsupported
AICapabilityModelNotSupported
AICapabilityRoutingNoMatch
```

### Tests

```text
backend/tests/unit/testPhase13CapabilityRegistry.py
```

### Documentation و Index

```text
docs/Phases/Phase13/Phase13-F.md
docs/Phases/Phase13/Phase13-F-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

---

## 3. رفتارهای Verification‌شده

### Capability Registry

- Capability با Tenant و Code ثبت می‌شود؛
- Code استاندارد و `CUSTOM_*` پشتیبانی می‌شود؛
- Duplicate در یک Tenant رد می‌شود؛
- Replace فقط با `replace=True` مجاز است؛
- همان Code در Tenantهای مختلف مستقل است؛
- Lookup Tenant دیگر Capability را expose نمی‌کند؛
- Resolve Capability inactive با `AICapabilityInactive` رد می‌شود؛
- Active-only Listing Capabilityهای inactive را حذف می‌کند؛
- Management Listing وضعیت inactive را نگه می‌دارد؛
- Unregister و `clear()` فقط روی Registry in-memory اثر دارند.

### Request Type Policy

- Capability بدون `allowedRequestTypes` با B backward-compatible است و تمام
  Request Typeهای شناخته‌شده را می‌پذیرد؛
- allowlist صریح Request Typeها validate و normalize می‌شود؛
- allowlist خالی هیچ Request Typeی را مجاز نمی‌کند؛
- Request Type ناشناخته، String منفرد یا Policy نامعتبر رد می‌شود؛
- تغییر Policy درون Entity بعد از Register به‌صورت live دیده می‌شود و policy
  stale موجب bypass نمی‌شود؛
- Capability inactive پیش از بررسی Request Type متوقف می‌شود.

### Model Integration

- F فقط Model Registry E را compose می‌کند و Model را کپی نمی‌کند؛
- Model باید در همان Tenant باشد و active باشد؛
- Capability باید در Input یا Output capability مدل وجود داشته باشد؛
- Model/Provider فعال از مسیر E در Listing و Routing لحاظ می‌شوند؛
- نبود Model Registry برای Integration یک خطای صریح می‌دهد؛
- Object غیرقابل تشخیص به‌عنوان Model با `AICapabilityModelNotSupported` رد می‌شود.

### Capability-first Routing

- ابتدا Capability resolve و active بودن آن بررسی می‌شود؛
- سپس Request Type Policy بررسی می‌شود؛
- بعد Constraintهای Model Routing E اعمال می‌شوند؛
- Routing به `RoutingDecision` provider-agnostic ختم می‌شود؛
- هیچ Provider call، Network، Retry یا Failover انجام نمی‌شود؛
- نبود Model مناسب به `AICapabilityRoutingNoMatch` تبدیل می‌شود؛
- Tenant از Capability، Model Listing و Routing حذف نمی‌شود.

### Security Boundary

- `CapabilityDescriptor` frozen است؛
- Policy کامل، Internal Metadata و Secret در Descriptor نیست؛
- `CapabilityRegistration` Entity را با `repr=False` نگه می‌دارد؛
- هیچ Framework، HTTP، Redis، Queue یا Vendor import در Domain F وجود ندارد؛
- Permission واقعی User/Role در F جعل نشده و به K/Application واگذار است.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی F از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13CapabilityRegistry -v
```

نتیجه:

```text
Ran 9 tests
OK
```

در طول توسعه، یک اجرای میانی تست به‌علت انتظار قدیمی Fixture نسبت به cache شدن
Request Type Policy شکست خورد. Implementation اصلاح شد تا Policy به‌صورت live
خوانده شود، Fixture اصلاح شد و اجرای نهایی 9/9 سبز شد. هیچ validationای حذف نشد.

### 4.2 تست ترکیبی B + C + D + E + F از ریشه — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry \
  backend.tests.unit.testPhase13CapabilityRegistry -v
```

نتیجه:

```text
Ran 48 tests
OK
```

### 4.3 Python Compile — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13CapabilityRegistry.py
```

نتیجه:

```text
compileall: PASS
```

### 4.4 Domain Purity Scan — PASS

کل `backend/apps/ai/domain` برای importهای زیر بررسی شد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic
```

نتیجه:

```text
domain purity scan: PASS
```

### 4.5 Documentation Link Scan — PASS

تمام Local Linkهای `docs/Phases/Phase13/` بعد از ایجاد این Report بررسی شدند و
Link شکسته‌ای باقی نماند.

### 4.6 Whitespace — PASS

```bash
git diff --check
```

برای فایل‌های Python جدید نیز trailing whitespace scan اجرا شد و PASS بود.
Trailing دو فاصله در Markdown فقط برای line break استاندارد Markdown است.

---

## 5. تست‌های اجرا نشده و دلیل دقیق

### 5.1 Django Test Runner — BLOCKED BY ENVIRONMENT

در Environment فعلی Django نصب نیست:

```bash
cd /home/user/Tekarai/backend
python manage.py test tests.unit.testPhase13CapabilityRegistry
```

خروجی:

```text
ModuleNotFoundError: No module named 'django'
```

Pure Unit Testهای F و Combined B+C+D+E+F بدون Django با موفقیت اجرا شدند.

### 5.2 Ruff و mypy — TOOLING NOT INSTALLED

```text
ruff: NOT INSTALLED
mypy: NOT INSTALLED
```

جایگزین‌های سبک اجراشده:

- Pure Unit Tests؛
- Compileall؛
- Domain Purity Scan؛
- Documentation Link Scan؛
- Whitespace Check.

### 5.3 Full Repository Discovery — خارج از Gate F

Full `unittest discover` پروژه نیازمند Django/Channels و سایر dependencyهای
پروژه است و برای F به‌عنوان Gate اجرا نمی‌شود. هر تستی که به Framework، Database،
Network، Queue یا Provider واقعی وابسته باشد در F خارج از Scope است.

### 5.4 Real Provider/Integration — خارج از Scope F

این موارد عمداً اجرا نشدند:

- Provider Adapter واقعی و Network؛
- Secret Store و API Key؛
- Database-backed Capability Registry؛
- API/Admin؛
- Queue/Worker/Async؛
- Retry/Timeout/Circuit Breaker/Failover؛
- Authorization واقعی User/Role؛
- Audit/Observability/Usage integration؛
- Cost/Latency/Quality based selection.

---

## 6. دستور اجرای دستی کاربر

### Linux/macOS/Git Bash

```bash
cd /path/to/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13CapabilityRegistry -v

PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry \
  backend.tests.unit.testPhase13CapabilityRegistry -v
```

### Windows PowerShell از ریشهٔ Repository

```powershell
Set-Location C:\path\to\Tekarai
$env:PYTHONPATH = "backend"
python -m unittest backend.tests.unit.testPhase13CapabilityRegistry -v
python -m unittest `
  backend.tests.unit.testPhase13Domain `
  backend.tests.unit.testPhase13ProviderPort `
  backend.tests.unit.testPhase13ProviderRegistry `
  backend.tests.unit.testPhase13ModelRegistry `
  backend.tests.unit.testPhase13CapabilityRegistry -v
```

### Windows PowerShell از داخل `backend`

```powershell
Set-Location C:\path\to\Tekarai\backend
$env:PYTHONPATH = "."
python -m unittest tests.unit.testPhase13CapabilityRegistry -v
```

### Environment کامل Django

```bash
python -m venv backend/.venv
# Linux/macOS: source backend/.venv/bin/activate
# Windows:     backend\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend/requirements/development.txt
cd backend
python manage.py test tests.unit.testPhase13CapabilityRegistry
```

اگر خروجی شما خطا داشت، لطفاً این موارد را ارسال کنید:

```text
کل stdout و stderr
python --version
python -m pip freeze
نام سیستم‌عامل
مسیر اجرای دستور: root یا backend
```

هیچ API Key، Token، Password، Secret، Connection String یا فایل `.env` ارسال
نشود. پس از دریافت خطا، مشخص می‌کنم مشکل از Environment، Path، Contract، Policy،
Tenant، Model Integration یا Routing است؛ سپس اصلاح و Verification مجدد انجام
می‌دهم و در صورت تغییر Artifact، ZIP جدید با Checksum جدید می‌سازم.

---

## 7. تصمیم‌های معماری

1. Capability Registry مثل Provider و Model در این مرحله in-memory است؛
2. Capability Key فقط `(tenantId, capabilityCode)` است؛
3. Capability مستقل از Provider است؛
4. Model Capability mapping از Declaration موجود در B استفاده می‌کند و Registry
   دوم ایجاد نمی‌شود؛
5. F Model/Provider ownership را دوباره پیاده نمی‌کند و به E واگذار می‌کند؛
6. Request Type Policy در `AICapability.policy` با کلید صریح
   `allowedRequestTypes` تعریف شده است؛
7. نبود Policy به‌منظور backward compatibility به معنی پذیرش تمام Request Typeهای
   شناخته‌شده است؛ وجود allowlist به معنی enforcement صریح است؛
8. Capability inactive قبل از Model Routing متوقف می‌شود؛
9. Model/Provider inactive از Listing عملیاتی و Routing حذف می‌شوند؛
10. Capability Routing همان Policy و Deterministic Ordering E را مصرف می‌کند؛
11. Fallback فقط انتخاب Candidate است و Failover واقعی نیست؛
12. Descriptorها Policy کامل، Metadata داخلی و Secret را expose نمی‌کنند؛
13. Permission واقعی User/Role، Audit و Persistence به زیر‌فازهای مرتبط واگذار
    شده‌اند؛
14. هیچ Vendor/Framework/Network import وارد Domain F نشده است.

---

## 8. Gate نهایی F

| معیار | وضعیت |
|---|---|
| Capability Registry در ساختار واقعی Tekarai | PASS |
| اتصال به `AICapability` از B | PASS |
| Unique `(tenantId, capabilityCode)` | PASS |
| Duplicate و Explicit Replace | PASS |
| Tenant Isolation | PASS |
| Activation/Deactivation | PASS |
| Request Type Policy | PASS |
| Standard و `CUSTOM_*` Capability | PASS |
| Non-sensitive Immutable Descriptor | PASS |
| Model Capability Integration با E | PASS |
| Capability-first Routing | PASS |
| Routing No Match Error Boundary | PASS |
| Provider/Framework Purity | PASS |
| Pure F Tests | PASS — 9/9 |
| Combined B+C+D+E+F Tests | PASS — 48/48 |
| Compile/Docs/Whitespace Checks | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Real Provider/Persistence/API | N/A — خارج از Scope F |
| Documentation | PASS |
| ZIP تحویل F | PASS — مسیر در بخش 9 |

**نتیجه:** `GREEN — زیر‌فاز G می‌تواند آغاز شود.`

---

## 9. Archive تحویل

پس از Verification نهایی، Archive مستقل F در این مسیر ساخته می‌شود:

```text
/home/user/Tekarai-Phase13-F.zip
```

SHA-256 و فایل sidecar پس از Packaging در همین Report و مسیر زیر ثبت می‌شوند:

```text
/home/user/Tekarai-Phase13-F.zip.sha256
```

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```
