# Phase 13-K — Execution Report

**تاریخ اجرا:** 2026-09-03  
**Repository:** `https://github.com/DeadBotKing/Tekarai.git`  
**Baseline ثبت‌شدهٔ Phase 13:** `809789c`  
**زیر‌فاز:** K — Tenant Isolation، Authorization و Permission Filtering  
**Gate:** `GREEN` برای Scope K  
**قرارداد قبلی:** [`Phase13-J.md`](Phase13-J.md)  
**قرارداد K:** [`Phase13-K.md`](Phase13-K.md)  
**زیر‌فاز بعدی:** L — Provider Adapterها

---

## 1. خلاصهٔ تحویل

در زیر‌فاز K، مرز pure و fail-closed برای Tenant Isolation، Authorization و
Permission Filtering در ساختار واقعی Tekarai ساخته شد. K از یک Principal snapshot
و Grantهای صریح استفاده می‌کند و به‌صورت پیش‌فرض هیچ مجوزی را از صرف عضویت در
Tenant یا نوع `SYSTEM` استنباط نمی‌کند.

تحویل اصلی K:

- `AuthorizationPrincipal` با Tenant، Subject، Role و direct permission؛
- `AuthorizationResource` بدون payload یا metadata حساس؛
- `PermissionGrant` با target Subject یا Role؛
- exact و prefix wildcard permission matching؛
- Allow/Deny با deny precedence؛
- resource، source، classification و external-provider selectors؛
- grant priority و expiry؛
- default deny immutable policy؛
- Tenant mismatch rejection؛
- principal/grant in-memory registry با duplicate protection؛
- safe Principal/Grant descriptors؛
- immutable و audit-ready `AuthorizationDecision`؛
- safe `SourcePermissionDecision` و `PermissionFilterResult`؛
- filtering sourceهای J قبل از assembly؛
- permission مستقل برای Context Build، Context Read و Context Export؛
- `AuthorizedContextEngine` برای محافظت از build، read، describe و list؛
- typed authorization helper برای Request، Response، Prompt، Model، Provider و
  Capability؛
- deep-copy snapshot isolation؛
- 11 تست اختصاصی K و regression ترکیبی B تا K؛
- Compile، Purity، Secret، Documentation Link، Whitespace، Archive integrity و
  Extracted Archive regression.

K authentication، identity lookup، persistence یا Provider execution انجام نمی‌دهد.
Application/Identity باید Principal و Grant snapshot معتبر را به این boundary تحویل
دهد و O باید Decisionها را در صورت نیاز audit پایدار کند.

---

## 2. فایل‌های ایجادشده یا تغییرکرده

### Implementation

```text
backend/apps/ai/domain/services/authorizationService.py
backend/apps/ai/domain/services/__init__.py
```

قراردادهای اصلی:

```text
AuthorizationPrincipal
AuthorizationResource
PermissionGrant
AuthorizationPolicy
AuthorizationDecision
PermissionFilterResult
AuthorizationService
AuthorizedContextEngine
```

Aliasها:

```text
PermissionService
PermissionEngine
AuthorizationEngine
AIAuthorizationService
TenantAuthorizationService
InMemoryAuthorizationService
PermissionFilteringService
Permission / PermissionRule
Principal / ResourceReference
AccessDecision / PermissionDecision
AuthorizationContext
PermissionAwareContextEngine
AIContextAuthorizationEngine
AuthorizedContextBuilder
```

### Exceptionها

```text
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
```

خطاهای K:

```text
AIAuthorizationDenied
AIAuthorizationPrincipalInvalid
AIAuthorizationGrantInvalid
AIAuthorizationPolicyInvalid
AIAuthorizationTenantMismatch
AIAuthorizationAlreadyRegistered
AIAuthorizationNotFound
```

`AIAuthorizationDenied` از `AIPermissionDenied` ارث می‌برد تا compatibility با
permission boundary قبلی حفظ شود.

### Tests

```text
backend/tests/unit/testPhase13Authorization.py
```

تست اختصاصی شامل 11 case برای قرارداد Principal/Resource، default deny، allow،
deny precedence، wildcard، role، selectors، expiry، registry، source filtering،
Context integration، external export، lookup authorization، aliases و purity است.

### Documentation و Index

```text
docs/Phases/Phase13/Phase13-K.md
docs/Phases/Phase13/Phase13-K-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

---

## 3. رفتارهای Verification‌شده

### 3.1 Principal و Resource

- Tenant و Subject ID به UUID normalize می‌شوند؛
- Subject type فقط `USER`، `SERVICE` یا `SYSTEM` است؛
- role و direct permission duplicate نمی‌شوند؛
- Principal inactive همیشه deny می‌شود؛
- resource type باید concrete باشد؛
- source resource فقط با source identity کامل ساخته می‌شود؛
- Resource هیچ content، metadata یا credential ندارد؛
- Principal Tenant و Resource Tenant متفاوت با `AIAuthorizationTenantMismatch`
  رد می‌شوند؛
- نوع `SYSTEM` bypass ضمنی ندارد.

### 3.2 Grant Evaluation

ارزیابی نهایی به این ترتیب verify شد:

```text
Tenant mismatch                         → exception
Inactive Principal                      → INACTIVE_PRINCIPAL / deny
Matching DENY + denyOverridesAllow      → EXPLICIT_DENY
Matching ALLOW                          → EXPLICIT_ALLOW
Direct Principal permission              → DIRECT_PERMISSION
No matching rule                        → DEFAULT_DENY
```

- default deny به‌صورت immutable enforce شده است؛
- Deny بر Allow تقدم دارد؛
- permission exact و prefix wildcard مانند `AI_CONTEXT_*` پشتیبانی می‌شود؛
- wildcard خارج از prefix مجاز نیست؛
- Grant دقیقاً Subject یا Role را target می‌کند؛
- Grantهای role برای Roleهای همان Principal evaluate می‌شوند؛
- resourceType و resourceId قابل محدودسازی هستند؛
- sourceDomain، sourceEntityType و sourceEntityId قابل محدودسازی هستند؛
- classification clearance قابل محدودسازی است؛
- `externalProvider=True` فقط Resource external را match می‌کند؛
- Grant منقضی‌شده evaluate نمی‌شود؛
- priority برای انتخاب matched deny/allow deterministic است؛
- نبود grant مجاز به fallback permissive نیست.

### 3.3 Safe Decision و Registry

`AuthorizationDecision` شامل Tenant، Subject، Action، Resource reference، نتیجه،
reason، matched grant، timestamp و fingerprint است. متن source، request input،
metadata حساس، secret یا credential در Decision قرار نمی‌گیرد.

- Principal و Grant registry Tenant-aware هستند؛
- duplicate Principal و Grant رد می‌شود؛
- equivalent semantic Grant با Grant ID متفاوت نیز duplicate محسوب می‌شود؛
- Grant lookup در Tenant دیگر `AIAuthorizationNotFound` می‌دهد؛
- Grant revoke از registry حذف می‌شود؛
- descriptorها immutable هستند؛
- direct grant و Principal snapshot با deep-copy نگهداری می‌شوند؛
- `requirePermission` فقط action امن را در exception قرار می‌دهد.

### 3.4 Permission Filtering

`filterContextSources` پیش از J اجرا می‌شود:

```text
ContextSourceCandidate
        ↓
Tenant scope validation
        ↓
SOURCE_NOT_AUTHORIZED check
        ↓
AuthorizationResource بدون payload
        ↓
AI_CONTEXT_SOURCE_READ evaluation
        ↓
authorizedSources یا safe SourcePermissionDecision
        ↓
J ContextEngine
```

- source مجاز در `authorizedSources` باقی می‌ماند؛
- source غیرمجاز حذف می‌شود و متن آن در result/reason نمی‌آید؛
- source با `authorized=False` با reason `SOURCE_NOT_AUTHORIZED` حذف می‌شود؛
- source Tenant دیگر exception است و silently drop نمی‌شود؛
- `PermissionFilterResult` counts و safe decisions را ارائه می‌کند؛
- tuple source payload در `repr` نتیجه مخفی است؛
- J پس از K همچنان classification، redaction و budget را enforce می‌کند.

### 3.5 Context Build و External Boundary

`buildAuthorizedContext` به دو permission مستقل نیاز دارد:

```text
AI_CONTEXT_BUILD
AI_CONTEXT_SOURCE_READ برای هر source
```

برای External Context، `AI_CONTEXT_EXPORT` نیز لازم است. داشتن Build یا Source
Read به‌تنهایی export را مجاز نمی‌کند. پس از عبور K، فقط sourceهای مجاز به
`ContextEngine` فاز J تحویل داده می‌شوند.

تست‌ها verify کردند که:

- build بدون Build permission رد می‌شود؛
- source بدون Source Read وارد Context نمی‌شود؛
- external build بدون Export permission رد می‌شود؛
- external build علاوه بر K به `ContextPolicy.allowExternalProvider=True` نیاز دارد؛
- Context نهایی فقط محتوای authorized را دارد.

### 3.6 Permission-Aware Context Lookup

`AuthorizedContextEngine` برای موارد زیر `AI_CONTEXT_READ` را enforce می‌کند:

- `getContext`؛
- `getResult`؛
- `describeContext`؛
- `listContexts`.

Tenant از Principal گرفته می‌شود و caller نمی‌تواند Tenant دیگری را برای lookup
تزریق کند. Context Engine J بدون K همچنان به‌عنوان Domain baseline قابل استفاده
است، اما Application برای use case حساس باید facade K را consume کند.

### 3.7 Typed Helpers

Helperهای زیر با Tenant principal و resource reference verify شدند:

```text
authorizeTenant
authorizeEntity
authorizeContext
authorizeRequest
authorizeResponse
authorizePrompt
authorizeModel
authorizeProvider
authorizeCapability
```

این helperها فقط Decision می‌سازند و lookup یا mutation موجودیت انجام نمی‌دهند.

---

## 4. تست‌های اجراشده و نتیجه

### 4.1 تست اختصاصی K از ریشهٔ Repository — PASS

```bash
cd /home/user/Tekarai
PYTHONPATH=backend python -m unittest \
  backend.tests.unit.testPhase13Authorization -v
```

نتیجهٔ نهایی:

```text
Ran 11 tests
OK
```

### 4.2 Regression ترکیبی B تا K — PASS

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
  backend.tests.unit.testPhase13ContextEngine \
  backend.tests.unit.testPhase13Authorization -v
```

نتیجهٔ نهایی:

```text
Ran 101 tests
OK
```

### 4.3 Python Compile — PASS

```bash
python -m compileall -q \
  backend/apps/ai/domain \
  backend/tests/unit/testPhase13ContextEngine.py \
  backend/tests/unit/testPhase13Authorization.py
```

نتیجه:

```text
compileall: PASS
```

### 4.4 Domain Purity و Secret Scan — PASS

کل `backend/apps/ai/domain` برای importهای زیر بررسی شد:

```text
django, rest_framework, channels, redis, requests, httpx,
openai, ollama, azure, anthropic, boto3
```

همچنین literalهای credential مانند `sk-` و `Bearer` بررسی شدند.

نتیجه:

```text
domain purity and secret scan: PASS
```

### 4.5 Documentation، Whitespace و Diff — PASS

```text
Python whitespace scan: PASS
documentation link scan: PASS
git diff --check: PASS
```

لینک‌های قرارداد K، گزارش K، سند مادر و زیر‌فاز L بررسی شدند.

### 4.6 محدودیت‌های محیط

Django در environment نصب نیست:

```text
ModuleNotFoundError: No module named 'django'
```

بنابراین Django Test Runner اجرا نشد. `ruff` و `mypy` نیز نصب نیستند. Pure
unittest، compileall، purity، secret، link، whitespace و diff checks بدون این
ابزارها با موفقیت اجرا شدند.

---

## 5. Persistence، Authentication و Concurrency Limitations

Authorization registry K in-memory و process-local است. K موارد زیر را ادعا
نمی‌کند:

- authentication یا identity proof؛
- persistence durable برای Principal/Grant/Decision؛
- database transaction یا unique constraint؛
- revoke propagation بین processها؛
- distributed lock، thread safety یا process safety؛
- cache invalidation؛
- audit event پایدار؛
- role inheritance یا membership resolution خارجی.

Application/Identity آینده باید Principal و Grantهای معتبر را از منبع مورداعتماد
بسازد. O/Application باید decisionها را audit کند و Infrastructure باید
versioning، revoke، transaction، concurrency، cache و retention را اضافه کند.

---

## 6. تصمیم‌های معماری ثبت‌شده

1. K Principal را authenticate نمی‌کند؛ snapshot احراز‌شده از Application می‌گیرد؛
2. Tenant membership به‌تنهایی permission نیست؛
3. default deny اجباری است؛
4. `SYSTEM` bypass عمومی ندارد؛
5. Grant دقیقاً Subject یا Role را target می‌کند؛
6. Explicit Deny با precedence بالاتر از Allow ارزیابی می‌شود؛
7. wildcard فقط exact یا prefix wildcard محدود است؛
8. Resourceها فقط reference و policy attribute دارند و payload حمل نمی‌کنند؛
9. source identity برای filtering از `ContextSourceCandidate` J ساخته می‌شود؛
10. Source Tenant دیگر exception است تا Cross-Tenant defect پنهان نشود؛
11. Source deny عادی safe drop است و content آن expose نمی‌شود؛
12. Context Build، Source Read و External Export permissionهای جدا هستند؛
13. K sourceهای مجاز را پیش از J assembly جدا می‌کند؛
14. J classification/redaction/budget invariantهای خودش را حفظ می‌کند؛
15. AuthorizationDecision audit-ready است اما audit persistence متعلق به O است؛
16. Principal/Grant registry فقط in-memory است؛
17. هیچ ORM، API، Network، Provider SDK یا Secret dependency وارد K نشده است؛
18. Provider-agnostic بودن Core AI حفظ شده است.

---

## 7. Gate نهایی K

| معیار | وضعیت |
|---|---|
| Authorization service در ساختار واقعی Tekarai | PASS |
| Tenant-aware Principal contract | PASS |
| Tenant-aware Resource contract | PASS |
| Explicit Permission Grant برای Subject/Role | PASS |
| Default deny | PASS |
| Explicit deny precedence | PASS |
| Exact/prefix wildcard matching | PASS |
| Resource/source/classification selectors | PASS |
| External-provider selector | PASS |
| Grant priority و expiry | PASS |
| Principal/Grant duplicate protection | PASS |
| Tenant mismatch rejection | PASS |
| Safe AuthorizationDecision و fingerprint | PASS |
| Safe source permission filtering | PASS |
| Pre-assembly integration با J | PASS |
| Context Build/Read/Export boundary | PASS |
| AuthorizedContextEngine facade | PASS |
| Typed authorization helpers | PASS |
| Snapshot isolation | PASS |
| Pure/provider-agnostic Domain boundary | PASS |
| Pure K tests | PASS — 11/11 |
| Combined B+C+D+E+F+G+H+I+J+K tests | PASS — 101/101 |
| Compile/Purity/Secret/Docs/Whitespace/Diff checks | PASS |
| Django Test Runner | BLOCKED — Django نصب نیست |
| Ruff/mypy | BLOCKED — ابزار نصب نیست |
| Persistence/Authentication/Concurrency | N/A — خارج از Scope K |
| Documentation و index | PASS |
| ZIP مستقل K و SHA-256 | PASS — مسیر در بخش 8 |

**نتیجه:** `GREEN — Phase 13-L may begin.`

---

## 8. Archive تحویل مستقل K

Archive مستقل K پس از Verification ساخته و بررسی شد:

```text
/home/user/Tekarai-Phase13-K.zip
```

SHA-256 canonical در sidecar زیر ثبت شده است:

```text
/home/user/Tekarai-Phase13-K.zip.sha256
```

برای جلوگیری از self-reference، checksum canonical فقط در sidecar و Delivery
Message اعلام می‌شود و در خود Report تکرار نمی‌شود. ZIP با `unzip -tq` بررسی و
پس از Extract، regression B تا K روی محتوای Archive اجرا می‌شود.

Exclusionهای Archive:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox, .nox, .next, .vite, .turbo
```
