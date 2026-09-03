# Phase 13-J — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** J — Context Engine و Context Builder  
**Gate:** `GREEN` برای Scope J  
**قرارداد قبلی:** [`Phase13-I.md`](Phase13-I.md)  
**قرارداد J:** [`Phase13-J.md`](Phase13-J.md)  
**زیر‌فاز بعدی:** K — Tenant Isolation، Authorization و Permission Filtering

---

## 1. خلاصهٔ تحویل

در زیر‌فاز J، Context Builder و Context Engine روی ساختار واقعی Domain فاز 13
پیاده‌سازی شد. Builder از Entity واقعی `AIContext` و Value Object واقعی
`ContextSource` در B استفاده می‌کند و برای حل نبودن `tenantId` در `ContextSource`
یک wrapper صریح و Tenant-bound به نام `ContextSourceCandidate` فراهم می‌کند.

تحویل J شامل این قابلیت‌هاست:

- Context assembly deterministic و provider-agnostic؛
- Tenant isolation برای request، source، registration، lookup و listing؛
- رد `ContextSource` خام که Tenant scope ندارد؛
- رد candidate متعلق به Tenant دیگر؛
- authorization اولیهٔ `authorized` و permission predicate اختیاری؛
- classification filtering با `ContextPolicy.allowedClassifications`؛
- external-provider boundary با `allowExternalProvider`؛
- Restricted redaction با marker ثابت و state قابل trace؛
- حذف empty source، duplicate source و sourceهای خارج از limit؛
- enforcement همزمان `maxSources`، `maxCharacters` و `maxTokens`؛
- token estimation با `aiRules.estimateTokens`؛
- safe source descriptors و safe Context descriptor؛
- SHA-256 content fingerprint بدون قرار دادن متن در descriptor؛
- حذف recursively شدن secret-like metadata keyها از Context source metadata؛
- in-memory registration با duplicate protection؛
- request-aware latest lookup و Tenant-aware listing؛
- deep-copy/snapshot isolation برای context، source metadata و read models؛
- exception boundary اختصاصی J؛
- 10 تست اختصاصی J و regression ترکیبی 90 تستی B تا J؛
- Compile، Purity، Documentation Link، Whitespace، Archive integrity و Extracted
  Archive regression.

J فقط Context را می‌سازد و ثبت in-memory انجام می‌دهد. منبع داده را fetch نمی‌کند،
Provider را اجرا نمی‌کند و authorization واقعی را جایگزین Application/K نمی‌کند.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/services/contextEngine.py
backend/apps/ai/domain/services/__init__.py
```

قراردادهای اصلی:

```text
ContextSourceCandidate
ContextSourceDescriptor
ContextDescriptor
ContextBuildResult
ContextBuilder
ContextEngine
```

Aliasهای ثبت‌شده:

```text
AIContextBuilder
AIContextEngine
AIContextSourceCandidate
TenantBoundContextSource
ContextService
InMemoryContextEngine
ContextBuilderService
```

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای J:

```text
AIContextSourceInvalid
AIContextTenantMismatch
AIContextPolicyInvalid
AIContextAlreadyRegistered
AIContextNotFound
AIContextTooLarge
```

### Tests

```text
backend/tests/unit/testPhase13ContextEngine.py
```

تست اختصاصی شامل 10 case برای assembly، policy، authorization، external
boundary، redaction، budgets، deduplication، Tenant isolation، registration،
snapshot isolation، descriptor safety و purity است.

### Documentation و Index

```text
docs/Phases/Phase13/Phase13-J.md
docs/Phases/Phase13/Phase13-J-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

---

## 3. رفتارهای Verification‌شده

### 3.1 Source Contract و Tenant Isolation

- `ContextSourceCandidate` tenantId را به UUID normalize می‌کند؛
- source identity باید string غیرخالی باشد؛
- classification با `DataClassification` کنترل می‌شود؛
- `ContextSource` خام در Builder پذیرفته نمی‌شود؛
- candidate متعلق به Tenant دیگر با `AIContextTenantMismatch` رد می‌شود؛
- requestId و contextId نیز UUID و در lookup Tenant-aware هستند؛
- Context registry با کلید `(tenantId, contextId)` کار می‌کند؛
- Tenant دیگر Context را در lookup یا listing نمی‌بیند؛
- `latestForRequest` فقط در همان Tenant جست‌وجو می‌کند.

### 3.2 Authorization و Policy

ترتیب تصمیم‌گیری قبل از ساخت `ContextSource` نهایی verify شد:

```text
Tenant/source validation
→ duplicate check
→ authorized flag
→ permissionFilter
→ classification policy
→ external-provider policy
→ empty check
→ maxSources
→ Restricted redaction
→ maxCharacters
→ maxTokens
→ ContextSource construction
```

- `authorized=False` با `NOT_AUTHORIZED` drop می‌شود؛
- permission predicate false با `PERMISSION_FILTERED` drop می‌شود؛
- exception predicate به `AIContextPolicyInvalid` تبدیل می‌شود؛
- classification خارج از policy با `CLASSIFICATION_NOT_PERMITTED` drop می‌شود؛
- external Context بدون اجازهٔ policy با `EXTERNAL_PROVIDER_NOT_PERMITTED` drop
  می‌شود؛
- source حذف‌شده هیچ‌گاه وارد `AIContext.content` یا `AIContext.sources` نمی‌شود؛
- sourceهای dropped فقط identity، classification و reason امن دارند.

### 3.3 Restricted و Secret Safety

- Restricted فقط وقتی مجاز باشد وارد build می‌شود؛
- با `redactRestricted=True` متن آن با `[REDACTED:RESTRICTED]` جایگزین می‌شود؛
- `AIContext.redacted` و `ContextSourceDescriptor.wasRedacted` درست ثبت می‌شوند؛
- marker نیز در character/token budget محاسبه می‌شود؛
- secret-like metadata keyهای `api_key`، `apikey`، `password`، `secret`،
  `secret_key`، `token`، `access_token`، `refresh_token` و
  `connection_string` از metadata خروجی حذف می‌شوند؛
- descriptor شامل content، raw metadata، credential یا secret value نیست؛
- fingerprint فقط digest متنی است و متن را به‌صورت مستقیم expose نمی‌کند؛
- J Secret Resolution یا PII scanner ادعا نمی‌کند.

### 3.4 Determinism و Limits

- ترتیب sourceهای پذیرفته‌شده همان ترتیب ورودی است؛
- separator assembled content دقیقاً `\n\n` است؛
- deduplication با `(sourceDomain, sourceEntityType, sourceEntityId)` انجام می‌شود؛
- duplicate با `DUPLICATE_SOURCE` drop می‌شود؛
- empty و whitespace-only با `EMPTY_CONTENT` drop می‌شوند؛
- `maxSources` با `MAX_SOURCES` enforce می‌شود؛
- `maxCharacters` روی assembled content، شامل separator، enforce می‌شود؛
- `maxTokens` با `estimateTokens` روی همان assembled content enforce می‌شود؛
- source خارج از budget truncate نمی‌شود و به‌صورت کامل drop می‌شود؛
- Context بدون source معتبر است و content خالی/fingerprint متن خالی دارد؛
- content fingerprint برای متن یکسان deterministic است.

### 3.5 Read Model و Snapshot Isolation

`ContextDescriptor` شامل Tenant/Request/Context IDs، source count، source
references، excluded count، character/token counts، fingerprint، redaction state،
external flag و createdAt است؛ متن Context و source metadata را ندارد.

`ContextSourceDescriptor` شامل source identity، classification، inclusion، drop
reason و redaction flag است؛ source content و metadata را ندارد.

تمام descriptorها immutable هستند. Engine در registration و lookup deep-copy
انجام می‌دهد تا mutation caller روی state داخلی اثر نگذارد. `registerContext` برای
Context دارای source خام عمداً خطا می‌دهد، چون B `ContextSource` به‌تنهایی Tenant
scope قابل اثبات ندارد؛ Context دارای source باید از `buildContext` یا
`registerResult` وارد شود.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی J از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13ContextEngine -v
```

نتیجهٔ نهایی:

```text
Ran 10 tests
OK
```

### 4.2 Regression ترکیبی B تا J — PASS

```bash
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Domain \
  backend.tests.unit.testPhase13ProviderPort \
  backend.tests.unit.testPhase13ProviderRegistry \
  backend.tests.unit.testPhase13ModelRegistry \
  backend.tests.unit.testPhase13CapabilityRegistry \
  backend.tests.unit.testPhase13RequestLifecycle \
  backend.tests.unit.testPhase13ResponseLifecycle \
  backend.tests.unit.testPhase13PromptPlatform \
  backend.tests.unit.testPhase13ContextEngine -v
```

نتیجهٔ نهایی:

```text
Ran 90 tests
OK
```

### 4.3 Python Compile — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13ContextEngine.py
```

نتیجه:

```text
compileall: PASS
```

### 4.4 Domain Purity — PASS

کل `backend/apps/ai/domain` و فایل سرویس J برای importهای زیر بررسی شد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic, boto3
```

نتیجه:

```text
domain purity scan: PASS
```

J هیچ ORM، API، Network، Provider SDK، Queue، Worker، Redis یا Secret Store
ندارد. تست اختصاصی J نیز نبود coupling به Provider و نبود literalهایی مانند
`sk-` و `Bearer` را بررسی می‌کند.

### 4.5 Documentation، Whitespace و Diff — PASS

```text
documentation link scan: PASS
git diff --check: PASS
Python whitespace scan: PASS
```

لینک‌های قرارداد J، گزارش J، سند مادر و زیر‌فاز K در index بررسی شدند.

### 4.6 Django، Ruff و mypy — محدودیت محیط

Django در environment فعلی نصب نیست:

```text
ModuleNotFoundError: No module named 'django'
```

بنابراین Django Test Runner اجرا نشد. همچنین `ruff` و `mypy` نصب نیستند.
Pure unittest، compileall، purity، link، whitespace و diff check جایگزین‌های
قابل اجرای این محیط بودند.

---

## 5. Persistence و Concurrency Limitations

`ContextEngine` در J in-memory و process-local است. این موارد عمداً ادعا نشده‌اند:

- durable persistence؛
- database uniqueness؛
- transaction؛
- distributed lock؛
- multi-process یا thread safety؛
- cross-instance ordering؛
- retention، encryption یا erasure policy.

در adapter آینده باید Tenant key، permission/classification boundary،
deduplication، safe metadata، fingerprint، duplicate protection و snapshot
contract حفظ شوند. concurrency و persistence واقعی باید در Infrastructure/Application
اضافه شوند، نه با ادعای کاذب داخل Pure Domain J.

---

## 6. تصمیم‌های معماری ثبت‌شده

1. `ContextSourceCandidate` به‌جای حدس Tenant از `ContextSource` خام استفاده شد؛
2. source فاقد Tenant scope معتبر fail-closed رد می‌شود؛
3. ContextBuilder منبع داده را fetch نمی‌کند و فقط candidateهای caller را consume
   می‌کند؛
4. authorization به `authorized` flag و pure `permissionFilter` محدود و explicit
   شد؛ lookup واقعی permission به K/Application واگذار شد؛
5. policy پیش از ساخت ContextSource نهایی اعمال می‌شود؛
6. external-provider فقط یک boundary policy است و Provider execution نیست؛
7. Restricted source در صورت مجاز بودن با marker ثابت redacted می‌شود؛
8. source خارج از character/token budget truncate نمی‌شود و کامل drop می‌شود؛
9. source identity کلید deduplication است و first-in-order winner است؛
10. `estimateTokens` از B reuse شد تا estimator J با baseline سازگار بماند؛
11. descriptorها immutable و بدون متن/metadata حساس هستند؛
12. fingerprint با SHA-256 برای traceability استفاده شد؛
13. metadata secret-like recursively حذف می‌شود و Secret Resolution وجود ندارد؛
14. `ContextEngine` با کلید `(tenantId, contextId)` in-memory است؛
15. registration Context دارای source خام بدون proof Tenant scope عمداً رد می‌شود؛
16. build result تولیدشده توسط Builder provenance داخلی `tenantScoped` دارد تا
    `registerResult` مرز registration را حفظ کند؛
17. Engine و Builder deep-copy snapshot می‌دهند؛
18. persistence، lock، concurrency، Provider، API، audit و usage به آینده واگذار
    شده‌اند و در J ادعا نمی‌شوند؛
19. هیچ Provider خاصی به Core AI وابسته نشده است.

---

## 7. Gate نهایی J

| معیار | وضعیت |
|---|---|
| Context Builder در ساختار واقعی Tekarai | PASS |
| استفاده از `AIContext` واقعی B | PASS |
| استفاده از `ContextSource` واقعی B | PASS |
| Tenant-bound source wrapper | PASS |
| رد source فاقد Tenant scope | PASS |
| Tenant isolation برای source/request/context | PASS |
| Authorization و permission predicate boundary | PASS |
| Classification filtering | PASS |
| External-provider policy boundary | PASS |
| Restricted redaction | PASS |
| Deduplication و empty-source filtering | PASS |
| maxSources enforcement | PASS |
| maxCharacters enforcement | PASS |
| maxTokens enforcement با `estimateTokens` | PASS |
| Safe dropped-source reasons | PASS |
| Sensitive metadata removal | PASS |
| Safe fingerprint و immutable descriptors | PASS |
| In-memory registration و duplicate protection | PASS |
| Snapshot isolation | PASS |
| Pure/provider-agnostic Domain boundary | PASS |
| Pure J tests | PASS — 10/10 |
| Combined B+C+D+E+F+G+H+I+J tests | PASS — 90/90 |
| Compile/Docs/Whitespace/Diff checks | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Persistence/Concurrency/Provider execution | N/A — خارج از Scope J |
| Documentation و index | PASS |
| ZIP مستقل J و SHA-256 | PASS — مسیر در بخش 8 |

**نتیجه:** `GREEN — Phase 13-K may begin.`

---

## 8. Archive تحویل مستقل J

Archive مستقل J پس از Verification ساخته و بررسی شد:

```text
/home/user/Tekarai-Phase13-J.zip
```

SHA-256 canonical در sidecar زیر ثبت شده است:

```text
/home/user/Tekarai-Phase13-J.zip.sha256
```

برای جلوگیری از self-reference، checksum canonical فقط در sidecar و Delivery
Message اعلام می‌شود و در خود Report تکرار نمی‌شود. ZIP با `unzip -tq` بررسی و
پس از Extract، regression B تا J روی محتوای Archive اجرا می‌شود.

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox
```
