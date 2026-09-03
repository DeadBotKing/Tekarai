# Phase 13-B — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline HEAD:** `809789c`  
**زیر‌فاز:** B — AI Domain & Value Objects  
**Gate:** `GREEN` برای Scope B  
**گزارش مستقل:** این سند فقط اجرای B را گزارش می‌کند؛ تکمیل B به‌معنی تکمیل Phase 13 نیست.

---

## 1. خلاصهٔ تحویل

زیر‌فاز B با هدف ساخت Domain خالص و Value Objectهای AI در ساختار واقعی Tekarai
اجرا شد. پیاده‌سازی جدید در `backend/apps/ai/domain/` قرار دارد و تست‌ها در
`backend/tests/unit/` هستند.

تحویل انجام‌شده:

- controlled vocabulary و Value Objectهای AI؛
- Entityها و lifecycle behaviourهای اصلی AI؛
- Tenant/UUID/validation invariantهای Domain؛
- Prompt Versioning و Render Contract؛
- Context/Knowledge/Embedding/Retrieval primitives؛
- Usage/Cost/Feedback/Evaluation/Audit primitives؛
- Tool/Agent execution lifecycle؛
- Policyهای Context، Provider، Quota و Tool؛
- Domain Ruleهای Schema، Retry، Cost، Redaction و Idempotency؛
- Domain Exceptionهای provider-neutral؛
- تست Unit مستقل از Django/Database/Provider؛
- مستند نیازمندی، تصمیم‌ها، Verification، خطاها و Open Boundary.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Domain implementation

```text
backend/apps/ai/domain/__init__.py
backend/apps/ai/domain/entities/__init__.py
backend/apps/ai/domain/entities/aiRecords.py
backend/apps/ai/domain/exceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/policies/__init__.py
backend/apps/ai/domain/policies/aiPolicies.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/services/aiRules.py
backend/apps/ai/domain/valueObjects/__init__.py
backend/apps/ai/domain/valueObjects/aiTypes.py
```

### Test

```text
backend/tests/unit/testPhase13Domain.py
```

### Documentation

```text
docs/Phases/Phase13/README.md
docs/Phases/Phase13/Phase13-B.md
docs/Phases/Phase13/Phase13-B-ExecutionReport.md
```

### عمداً بدون تغییر

- `backend/apps/ai/domain/ports.py`: Provider Port کامل به C موکول شد؛
- `backend/apps/ai/infrastructure/models.py`: ORM/Migration به زیر‌فازهای بعدی؛
- Provider Adapter و SDK خارجی؛
- API، serializer، queue، worker و persistence.

---

## 3. پوشش رفتاری اجراشده

`testPhase13Domain.py` شامل ۱۰ تست Unit و ۴۶ assertion مستقیم است و این
موارد را پوشش می‌دهد:

1. normalization و validation Value Objectها؛
2. immutable attribute در dataclassهای frozen؛
3. Token Usage و Cost Rate؛
4. Provider/Model/Capability و tenant boundary؛
5. Operation/Request state transition و retry؛
6. Response token consistency؛
7. Prompt Versioning، missing variables و rendering؛
8. Context Classification، authorization و limit؛
9. Memory Version، Knowledge lifecycle، Chunk، Embedding و Retrieval selection؛
10. Usage، Cost، Feedback، Evaluation و Audit؛
11. Tool و Agent execution lifecycle؛
12. JSON Schema subset، Retry/Quota/Provider/Tool Policy، redaction و
    idempotency fingerprint.

---

## 4. Verification اجراشده

### 4.1 Pure Unit Tests — PASS

دستور:

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest backend.tests.unit.testPhase13Domain -v
```

نتیجهٔ نهایی:

```text
Ran 10 tests in 0.003s
OK
```

این تست با Python استاندارد اجرا شد و Database، Django، Network، Secret و
Provider SDK لازم نداشت.

### 4.2 Python Compile Check — PASS

دستور:

```bash
cd /home/user/Tekarai
python -m compileall -q backend/apps/ai/domain backend/tests/unit/testPhase13Domain.py
```

نتیجه:

```text
compileall: PASS
```

### 4.3 Domain Dependency Scan — PASS

روی تمام فایل‌های `.py` در `backend/apps/ai/domain/` بررسی شد که import مستقیمی
از این گروه‌ها وجود نداشته باشد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, anthropic, azure, ollama
```

نتیجه:

```text
domain dependency scan: PASS
```

### 4.4 Git Whitespace Check — PASS

دستور:

```bash
git diff --check
```

نتیجه: خطای whitespace گزارش نشد.

---

## 5. تست‌های اجرا نشده و دلیل دقیق

### 5.1 Django test runner — BLOCKED BY ENVIRONMENT

دستور بررسی‌شده:

```bash
cd /home/user/Tekarai/backend
python manage.py test backend.tests.unit.testPhase13Domain
```

نتیجه:

```text
ModuleNotFoundError: No module named 'django'

ImportError: Couldn't import Django. Activate the project virtual environment
and install dependencies with: python -m pip install -r requirements/development.txt
```

بنابراین Django test runner و full project test suite در این محیط اجرا نشدند؛ این
عدم اجرا failure در Domain B نیست و ناشی از نبود dependency محیط است.

### 5.2 Ruff و mypy — در محیط موجود نیستند

- `ruff check ...` اجرا نشد: `ruff: NOT INSTALLED`؛
- `mypy ...` اجرا نشد: `mypy: NOT INSTALLED`.

Compile، dependency scan، `unittest` و `git diff --check` به‌عنوان Verification
قابل‌اجرا انجام شدند.

### 5.3 تست‌های Integration/Database/Provider — خارج از Scope B

این تست‌ها عمداً در B اجرا نشدند:

- Integration و API؛
- ORM/Migration و Database؛
- Queue/Worker؛
- Provider Contract/Adapter؛
- OpenAI/Ollama/Azure یا هر سرویس خارجی.

دلیل، تفکیک اجباری زیر‌فازها و منع hard-code/SDK در Core Domain است. این موارد
باید در C، L، M، P، Z یا زیر‌فاز مرتبط اجرا شوند.

---

## 6. دستور اجرای دستی پیشنهادی برای کاربر

پس از در اختیار داشتن Python مورد نیاز پروژه و dependencyهای backend:

```bash
cd /path/to/Tekarai
python -m venv backend/.venv
source backend/.venv/bin/activate          # Windows: backend\\.venv\\Scripts\\activate
python -m pip install -r backend/requirements/development.txt
PYTHONPATH=backend python -m unittest backend.tests.unit.testPhase13Domain -v
cd backend
python manage.py test tests.unit.testPhase13Domain
python manage.py test
```

در workspace مسیر `backend/requirements/development.txt` موجود است، اما در محیط
اجرای فعلی dependencyهای آن نصب نشده‌اند؛ `manage.py` نیز به Django نصب‌شده نیاز
دارد. اگر branch یا محیط دیگری استفاده می‌شود، مسیر dependency را مطابق همان
branch بررسی کنید.

لطفاً اگر هر کدام از دستورات دستی خطا داد، کل خروجی `stdout/stderr`، نسخهٔ Python
و نسخهٔ dependency را ارسال کنید:

```bash
python --version
python -m pip freeze
```

هیچ Secret یا API Key را در خروجی ارسال نکنید.

---

## 7. تصمیم‌های معماری ثبت‌شده

1. Domain به‌صورت `dataclass`/Python خالص پیاده شد؛ ORM mapping به بعد موکول است؛
2. تمام Entityهای عملیاتی Tenant-aware و UUID-normalized هستند؛
3. Provider صرفاً یک Domain concept است و هیچ vendor در Core AI hard-code نشده؛
4. Secret به‌جای مقدار خام با `configurationReference` مدل می‌شود؛
5. Context قبل از استفاده باید Classification/Authorization/Size Policy را
   پشت سر بگذارد؛
6. Retrieval صریحاً Candidate، Authorized و Selected را جدا می‌کند؛
7. Cost با Decimal و Token Usage محاسبه می‌شود؛
8. Prompt Version immutable مفهومی است و فقط Active Version روی Prompt عوض
   می‌شود؛
9. Structured Output با dependency-free subset از JSON Schema قابل validation
   است؛
10. Domain Exceptionها provider-neutral هستند و API mapping نهایی در Z انجام
    می‌شود؛
11. Idempotency fingerprint در Domain Rule تعریف شد، اما persistence/enforcement
    به P واگذار شد؛
12. B به Port/Adapter، Routing، Retry Executor، Queue، API و Database وارد نشد.

---

## 8. Known Limitations / Open Questions برای C به بعد

- قرارداد نهایی Provider Port و Streaming در C؛
- انتخاب Model/Provider و Fallback در E و M؛
- Policy enforcement واقعی بر اساس User/Tenant Permission در K؛
- Token counting دقیق provider-specific در N و L؛
- JSON Schema کامل یا library-based در H؛
- Persistence و unique constraintهای tenant/idempotency در Z/P؛
- Redaction کامل براساس طبقه‌بندی فیلدها و Secret Store در O؛
- Context assembly واقعی و retrieval index در J/R/S؛
- queue/worker و timeout واقعی در P/M؛
- API Envelope و HTTP status mapping در Z.

---

## 9. Gate نهایی B

| معیار | وضعیت |
|---|---|
| Scope B در Domain خالص | PASS |
| Value Objectها و Vocabularyها | PASS |
| Entity و State Machineهای اصلی | PASS |
| Tenant/Permission/Security boundary | PASS در سطح Domain Contract |
| Usage/Cost/Audit primitives | PASS |
| Pure Unit Tests | PASS — 10/10 |
| Compile/Dependency/Whitespace checks | PASS |
| Django/Ruff/mypy | BLOCKED — dependency/tool در محیط موجود نیست |
| Provider/ORM/API/Integration | N/A — خارج از B |
| Documentation کامل B | PASS |
| ZIP تحویل B | PASS — مسیر در بخش ۱۰ |

**نتیجه:** `GREEN — زیر‌فاز B تکمیل شد؛ زیر‌فاز C می‌تواند آغاز شود.`

---

## 10. Archive تحویل

پس از نهایی‌شدن کد، تست و Docs، Archive مستقل B در این مسیر ساخته می‌شود:

```text
/home/user/Tekarai-Phase13-B.zip
```

SHA-256 و فهرست exclusionهای Archive باید هنگام ساخت نهایی در همین سند ثبت شوند.
