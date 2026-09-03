# Phase 13-C — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline HEAD:** `809789c`  
**زیر‌فاز:** C — Provider Port & Provider Contract  
**Gate:** `GREEN` برای Scope C  
**قرارداد قبلی:** [`Phase13-B.md`](Phase13-B.md)  
**قرارداد C:** [`Phase13-C.md`](Phase13-C.md)

---

## 1. خلاصهٔ تحویل

C مرز رسمی Provider را در ساختار واقعی Tekarai تکمیل کرد. `AIProviderPort` اکنون
یک Protocol provider-neutral است و برای عملیات اصلی Phase 13 contract دارد:

- Generate؛
- Structured Generate؛
- Streaming؛
- Embedding و Batch Embedding؛
- Token Counting؛
- Health Check؛
- Capability Handshake؛
- Tenant/Trace/Correlation/Idempotency Context.

یک Deterministic Provider کاملاً Offline نیز برای Contract Test موجود است و
Compatibility با مصرف قبلی حفظ شده است.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Provider contract

```text
backend/apps/ai/domain/ports.py
```

شامل:

```text
ProviderRequestContext
GenerationRequest
GenerationResult
GenerationChunk
EmbeddingResult
ProviderCapabilities
ProviderHealth
AIProviderPort
validateGenerationResult
validateEmbeddingVector
requireProviderFeature
DeterministicAIProvider
```

### Infrastructure test double

```text
backend/apps/ai/infrastructure/providers/deterministic.py
```

Provider deterministic را برای کشف استاندارد Infrastructure re-export می‌کند؛
این Provider هیچ Network، SDK یا Secret لازم ندارد.

### Unit Test

```text
backend/tests/unit/testPhase13ProviderPort.py
```

### Documentation

```text
docs/Phases/Phase13/README.md
docs/Phases/Phase13/Phase13-C.md
docs/Phases/Phase13/Phase13-C-ExecutionReport.md
docs/Phases/Phase13.md
```

فایل مادر `docs/Phases/Phase13.md` فقط لینک و وضعیت Sub-phase Index را به‌روز
کرده است؛ Scope کامل Phase 13 هنوز تمام نشده است.

---

## 3. رفتارها و Invariantهای پیاده‌سازی‌شده

### Request Context

- Tenant ID اجباری و UUID-normalized است؛
- Request/Operation ID در صورت وجود UUID-normalized هستند؛
- Correlation ID و Trace ID در صورت فقدان به‌صورت Domain-generated ساخته می‌شوند؛
- Idempotency Key برای عملیات حساس قابل عبور است و برای تمام Callهای ساده اجباری
  نشده است؛
- هیچ فیلد API Key، Password یا Secret در Contract وجود ندارد؛
- Context immutable است.

### Generation

- Prompt و Model خالی رد می‌شوند؛
- Temperature باید finite و غیرمنفی باشد؛
- Max Tokens باید Positive Integer باشد؛
- Response Format فقط `TEXT` یا `JSON` است؛
- JSON Schema به شکل provider-neutral عبور می‌کند؛
- Result Tokenها غیرمنفی هستند؛
- Total Tokens از Input و Output مشتق می‌شود؛
- Finish Reason کنترل‌شده است؛
- Model/Provider mismatch پیش از تحویل به Application قابل تشخیص است.

### Structured Generation

- متد `generateStructured()` دارای JSON Schema اجباری است؛
- Structured Generation و JSON Schema در Capability Handshake جداگانه قابل
  بررسی هستند؛
- Validation معنایی کامل Output با Domain Ruleهای B/H هماهنگ می‌ماند.

### Streaming

- هر Chunk Index غیرمنفی دارد؛
- Chunk آخر `isFinal=True` و Finish Reason نهایی دارد؛
- Trace fields روی Chunk قابل حمل هستند؛
- C Stream را Queue، Retry یا Persist نمی‌کند.

### Embedding

- Vector خالی رد می‌شود؛
- مقادیر non-finite رد می‌شوند؛
- Dimension از طول Vector مشتق می‌شود؛
- API قدیمی `list[float]` حفظ شده و `EmbeddingResult` برای metadata غنی موجود
  است؛
- Batch Embedding به‌صورت provider-neutral تعریف شده است.

### Capability/Health

- Featureهای معتبر: Generation، Structured Generation، Streaming، Embedding،
  Token Counting، Tools و Vision؛
- JSON Schema بدون Structured Generation نامعتبر است؛
- Batch Embedding بدون Embedding capability نامعتبر است؛
- Health status فقط Healthy/Degraded/Unavailable/Unknown است؛
- Health latency غیرمنفی است و detail نباید دادهٔ حساس داشته باشد.

---

## 4. Backward Compatibility

Callهای موجود همچنان معتبر هستند:

```python
provider.generate(prompt="hello", model="test")
provider.embed(text="hello", model="test")
```

و Contractهای جدید:

```python
provider.generateRequest(GenerationRequest(prompt="...", model="..."))
provider.generateStructured(prompt="...", model="...", jsonSchema={...})
provider.stream(prompt="...", model="...")
provider.embedBatch(texts=("...", "..."), model="...")
provider.countTokens(text="...", model="...")
provider.healthCheck(model="...")
```

تست‌های قبلی deterministic که `provider == "deterministic"` و Embedding
هشت‌بعدی را انتظار دارند، با Contract جدید سازگار باقی مانده‌اند.

---

## 5. Verification اجراشده

### 5.1 C Pure Unit Tests — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest backend.tests.unit.testPhase13ProviderPort -v
```

نتیجه:

```text
Ran 9 tests
OK
```

### 5.2 Combined B + C Unit Tests — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort -v
```

نتیجه:

```text
Ran 19 tests
OK
```

### 5.3 Python Compile Check — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/apps/ai/infrastructure/providers \
  backend/tests/unit/testPhase13ProviderPort.py
```

نتیجه:

```text
compileall: PASS
```

### 5. Domain Dependency Scan — PASS

روی Domain و Provider test double بررسی شد که Domain import مستقیم از این گروه‌ها
نداشته باشد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, anthropic, azure, ollama
```

نتیجه:

```text
C dependency scan: PASS
```

### 5.4 Git Whitespace Check — PASS

```bash
git diff --check
```

نتیجه:

```text
git diff check: PASS
```

### 5.5 Import Surface — PASS

`AIProviderPort`، `GenerationResult` و `DeterministicAIProvider` از مسیر public
قابل import هستند و Infrastructure test double به همان Provider resolve می‌شود.

---

## 6. تست‌های اجرا نشده و دلیل دقیق

### 6.1 Django Test Runner — BLOCKED BY ENVIRONMENT

دستور اجراشده:

```bash
cd /home/user/Tekarai/backend
python manage.py test tests.unit.testPhase13ProviderPort
```

نتیجه:

```text
ModuleNotFoundError: No module named 'django'

ImportError: Couldn't import Django. Activate the project virtual environment
and install dependencies with: python -m pip install -r requirements/development.txt
```

بنابراین Django test runner و full project suite در این محیط قابل اجرا نبودند.
این خطا مربوط به نبود dependency محیط است، نه failure تست‌های pure C.

### 6.2 Ruff و mypy — TOOLING NOT INSTALLED

- `ruff check ...` اجرا نشد: `ruff: NOT INSTALLED`؛
- `mypy ...` اجرا نشد: `mypy: NOT INSTALLED`.

### 6.3 Integration/Real Provider Tests — خارج از Scope C

این موارد در C عمداً اجرا نشدند:

- OpenAI/Azure/Ollama/Anthropic یا هر Provider واقعی؛
- Network و API Key؛
- Provider Adapter Contract واقعی؛
- Database/ORM/Migration؛
- API/HTTP؛
- Queue/Worker/Async؛
- Retry/Timeout/Fallback Executor؛
- Routing و Registry.

C فقط Port و Test Double را تحویل می‌دهد؛ Adapter واقعی در L و رفتارهای Routing
و Registry در D/E و زیر‌فازهای بعدی اجرا می‌شوند.

---

## 7. دستور اجرای دستی برای کاربر

پس از آماده‌سازی محیط backend:

```bash
cd /path/to/Tekarai
python -m venv backend/.venv
source backend/.venv/bin/activate          # Windows: backend\\.venv\\Scripts\\activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements/development.txt

PYTHONPATH=backend python -m unittest backend.tests.unit.testPhase13ProviderPort -v
PYTHONPATH=backend python -m unittest backend.tests.unit.testPhase13Domain backend.tests.unit.testPhase13ProviderPort -v

cd backend
python manage.py test tests.unit.testPhase13ProviderPort
python manage.py test
```

در صورت خطا، این موارد را ارسال کنید:

```bash
python --version
python -m pip freeze
```

همراه با کل `stdout/stderr` همان دستور. هیچ API Key، Token، Password یا Secret را
ارسال نکنید.

---

## 8. تصمیم‌های معماری

1. Port در Domain باقی ماند و هیچ Adapter/SDK به Domain وارد نشد؛
2. Contract canonical با `GenerationRequest` تعریف شد، اما keyword API قبلی حفظ
   شد؛
3. `embed()` برای عدم شکستن مصرف‌کنندهٔ موجود `list[float]` می‌دهد؛
4. `EmbeddingResult` برای Adapterهای غنی‌تر تعریف شد؛
5. Stream به‌صورت sync `Iterable` تعریف شد تا C به Queue/Event Loop وابسته نشود؛
6. Provider capability از Business Capability جدا نگه داشته شد؛
7. Health Snapshot فقط metadata غیرحساس دارد؛
8. Tenant/Trace context بخشی از Contract است، اما Port خودش Permission یا
   Tenant lookup انجام نمی‌دهد؛
9. Idempotency Key اختیاری برای Callهای معمولی و الزامی از نظر Governance برای
   عملیات حساس باقی ماند؛
10. Deterministic Provider به‌عنوان Test Double نگه داشته شد و Adapter تجاری
    اضافه نشد؛
11. Provider exception mapping در L/M انجام می‌شود و Exception خام SDK به Core
    اجازهٔ عبور ندارد.

---

## 9. Open Boundary برای D و بعد

- D: Provider Registry و ثبت/فعال‌سازی Providerها؛
- E: Model Registry و Routing؛
- F: Capability Registry و Resolution؛
- L: Adapterهای OpenAI/Ollama/Azure و غیره در Infrastructure؛
- M: Provider Error Boundary، Retry، Timeout و Fallback؛
- N: Token Counter واقعی، Usage، Cost و Quota؛
- P: Async/Queue/Worker و Stream orchestration؛
- Z: API Envelope، Migration و full release gate.

---

## 10. Gate نهایی C

| معیار | وضعیت |
|---|---|
| Provider Port به‌صورت Protocol | PASS |
| Generate/Structured Generate | PASS |
| Streaming Contract | PASS |
| Embedding/Batch Embedding | PASS |
| Token Counting | PASS |
| Capability/Health Handshake | PASS |
| Tenant/Trace/Correlation Context | PASS |
| Provider-neutral Result validation | PASS |
| Offline Deterministic Test Double | PASS |
| Backward Compatibility | PASS |
| Domain purity / no Vendor SDK | PASS |
| Pure Unit Tests | PASS — 9/9 C و 19/19 B+C |
| Compile/Whitespace checks | PASS |
| Django/Ruff/mypy | BLOCKED — محیط/tooling |
| Real Adapter/Network/Integration | N/A — خارج از Scope C |
| Documentation | PASS |
| ZIP تحویل | PASS — مسیر در بخش ۱۱ |

**نتیجه:** `GREEN — زیر‌فاز D می‌تواند آغاز شود.`

---

## 11. Archive تحویل

پس از نهایی‌شدن کد، تست و Documentation، Archive مستقل C در این مسیر ساخته
شد:

```text
/home/user/Tekarai-Phase13-C.zip
```

SHA-256:

```text
62c05971b683be33ee8e7f4d966a57509788a017f442548e61f754ff21fb3bbc
```

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```

فایل checksum جانبی نیز در این مسیر ساخته شده است:

```text
/home/user/Tekarai-Phase13-C.zip.sha256
```

checksum متعلق به فایل ZIP تحویل‌شده است. ثبت آن در این نسخهٔ کاری، Delivery
Metadata است و محتوای اجرایی و مستنداتی Archive را تغییر نمی‌دهد.
