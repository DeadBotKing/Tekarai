# Phase 13-O — Audit و Governance

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** O از A تا Z
**وضعیت:** COMPLETED — Audit/Governance Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§8، §13، §28، §36، §38، §40، §42، §43، §45، §46، §47، §48)
**قراردادهای قبلی:** [B](Phase13-B.md) (موجودیت‌ها)، [G](Phase13-G.md) (چرخه‌عمر و idempotency)،
[K](Phase13-K.md) (ایزولاسیون و Authorization)، [L](Phase13-L.md) (آداپتورها)،
[N](Phase13-N.md) (لج sprawling مصرف و حامل `AIUsageRecorded`)
**گزارش اجرا:** [`Phase13-O-ExecutionReport.md`](Phase13-O-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز O دو ستون «قابل‌حسابرسی‌بودن» پلتفرم AI را می‌سازد: **دفتر حسابرسی
append-only و ضد-دستکاری** که هر عملیات حساس را با «چه‌کسی، کجا، کی، چه، با
چه، چه نتیجه‌ای» ثبت می‌کند (§28)، و **موتور حکمرانی** که پیش از اجرا تصمیم
می‌گیرد کدام provider/model/capability برای کدام tenant مجاز است، دادهٔ
RESTRICTED کجا می‌تواند برود، و سقف هزینهٔ روزانه چقدر است (§48) — همه با
حذف Secret و محتوا از رکوردها (§47) و سیاست نگهداشت صریح (§46).

O به این سؤال پاسخ می‌دهد:

> چگونه هر تصمیم و مصرف حساس AI را چنان ثبت کنیم که نتوان آن را تغییر یا
> پاک کرد (مگر با purge سیاستیِ خودش ثبت‌شده)، هیچ Secret و محتوایی در آن
> ننشیند، و حکمرانی (allowlist مدل/provider، قابلیت‌های فعال، مرز دادهٔ
> حساس، بودجهٔ هزینه) پیش از اجرا و به‌صورت fail-closed اعمال شود — بدون
> آنکه به executor آیندهٔ M، صف P، یا API عمومی Z وابسته باشیم؟

**یادداشت ترتیب اجرا:** O قبل از M ساخته شد اما هیچ وابستگی به کد M ندارد.
M و Z مصرف‌کنندهٔ همین قراردادند: هر تلاش/درخواست از `logAudit` و هر تصمیم
پیش از اجرا از `evaluateGovernance` استفاده می‌کند (§2.2 و §14).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- موجودیت canonical حسابرسی `AIAuditEntry`: tenant، زمان وقوع صریح دامنه،
  actor (نوع + شناسه)، action از واژگان بسته (پوشش §36 + نیازهای O)،
  ارجاع‌های UUID **بدون FK** (تا purge ردیف‌های مرجع، audit را نابود نکند)،
  کدهای capability/provider/model، نسخهٔ prompt، classification، نتیجه،
  کد خطا، correlation/trace، ارجاع منبع context (نه محتوا)، جزئیات scrubشده؛
- زنجیرهٔ hash ضد-دستکاری (`prevHash`/`hash`، مبدأ `GENESIS`) + تابع
  `verifyAuditChain` با تشخیص پیوند شکسته و fork؛
- scrubber قطعی Secret (الگوی نام کلید، بازگشتی روی dict/list) + قاعدهٔ
  دادهٔ RESTRICTED (§47: جزئیات کامل فقط با پرچم صریح tenant)؛
- سیاست حکمرانی `AIGovernancePolicy`: یک سیاست فعال برای هر tenant با
  allowlist provider/model، لیست قابلیت‌های غیرفعال، پرچم عبور دادهٔ
  حساس به بیرون، بودجهٔ روزانهٔ هزینه؛
- موتور تصمیم `GovernanceService.evaluate` با ترتیب ثابت قواعد و خروجی
  ALLOW/DENY مستدل + `raiseForDecision`؛ بودجه فقط با ورودی صریح مصرف
  روز محاسبه می‌شود (کوپل‌شدن به summary مصرف N با Z است)؛
- ثبت خودکار هر تصمیم (ALLOW و DENY) در دفتر حسابرسی با snapshot قواعد؛
- ingestion حامل `AIUsageRecorded` فاز N به رکورد `USAGE_RECORDED`
  (تحقق bindingای که N به O/P سپرده بود؛ transport روی باس همچنان با P)؛
- API ثبت `QUOTA_DENIED` و `logAudit` عمومی برای اتصال چرخه‌عمر G و
  executor آیندهٔ M؛
- retention: purge سیاستی audit و **جدول‌های N** (attempt/counter) با
  `AI_USAGE_RETENTION_DAYS` آماده‌شدهٔ N + رکورد meta `RETENTION_PURGED`
  پس از هر purge با شمارش‌ها؛
- دو جدول جدید (`aiAuditTrail`، `aiGovernancePolicies`) + مهاجرت
  `0003_auditGovernance`؛ فایل‌های N **دست‌نخورده** (purge جدول‌های N از
  repository جدید O انجام می‌شود)؛
- تنظیمات `AI_AUDIT_*` و `AI_GOVERNANCE_*` در `base.py` و `.env.example`
  (§42)؛ هفت خطای جدید با پیشوند `AI` (§43)؛
- تست واحد آفلاین + تست application روی SQLite واقعی + تست یکپارچگی
  قرارداد repositoryها.

### 2.2 خارج از Scope

- اتصال چرخه‌عمر G و executor آیندهٔ M به `logAudit` (مصرف‌کننده‌های این
  قرارداد؛ با M/Z) — واژگان action و API آماده است؛
- transport رویداد روی Event Bus — زیر‌فاز **P** (sink درون‌فرایندی O
  نقطهٔ اتصال است)؛
- بازنویسی `AIService.generate` قدیمی و جدول legacy `aiAuditRecords`:
  O آن را دست نمی‌زند؛ هم‌گرایی ledger در **Z** (همان موضع N در §2.2)؛
- اندپوینت API عمومی audit/governance — زیر‌فاز **Z**؛
- امضای رمزنگاری خارجی (HSM/KMS) برای زنجیره — زنجیرهٔ hash داخلی
  tamper-evidence است نه proof رمزنگاری؛ با O؛
- تبدیل ارز (FX) در بودجه — ناسازگاری ارز fail-closed است (همان موضع N).

---

## 3. جایگاه معماری

```text
Application (AuditApplicationService — این زیر‌فاز)
   ├── define/update/deactivate/describeGovernancePolicy (پیکربندی tenant)
   ├── evaluateGovernance (ارزیابی → ثبت تصمیم → raise در DENY)
   ├── logAudit (ثبت عمومی برای G/M/Z) / logQuotaDenial / ingestUsageRecorded
   ├── listAuditEntries / verifyTenantChain
   └── purgeAuditRetention / purgeUsageRetention (purge + meta-audit)
        │ hydrate (importPolicy/importEntry)
        ▼
Domain (خالص، بدون Django)
   ├── auditTypes (واژگان AUDIT_ACTIONS/ACTOR_TYPES/AUDIT_OUTCOMES، الگوهای scrub)
   ├── auditRecords (AIAuditEntry، AIGovernancePolicy، GovernanceRequest/Decision)
   ├── auditTrail (AuditTrailService، scrubDetail، auditEntryHash، verifyAuditChain)
   ├── governance (GovernanceService، evaluate، raiseForDecision)
   └── auditPorts (AuditRecordStore، GovernancePolicyStore، RetentionPurger)
        │  پیاده‌سازی Django
        ▼
Infrastructure (apps/ai/infrastructure/)
   ├── models (AIAuditTrailModel، AIGovernancePolicyModel — استایل تمیز)
   ├── repositories/auditRepositories (Django stores + purger — فقط نگاشت سطر↔موجودیت)
   └── migrations/0003_auditGovernance
```

قواعد وابستگی:

1. دامنه هیچ importای از Django/ORM/HTTP/Redis/Queue/Provider SDK ندارد؛
2. اپلیکیشن فقط پورت‌ها را می‌شناسد؛ پیاده‌سازی Django تزریق می‌شود؛
3. منطق کسب‌وکار (زنجیره، scrub، ترتیب قواعد حکمرانی، ریاضی بودجه) فقط در
   دامنه است؛ repositoryها فقط نگاشت‌اند؛
4. هیچ Secret، کلید API، prompt، completion یا محتوای context وارد رکوردها،
   descriptorها و پیام‌های خطا نمی‌شود (اثبات با تست)؛
5. تغییر خارج از محدودهٔ O بدون ثبت در گزارش اجرا ممنوع (قرارداد README).

---

## 4. قرارداد Audit Entry (§28)

### 4.1 فیلدها

هر رکورد: `(tenantId، occurredAt، actorType، actorId؟، action، requestId؟،
attemptId؟، policyId؟، capabilityCode، providerCode، modelCode،
promptVersion، classification، outcome، errorCode، correlationId، traceId،
contextSources، detail)`. شناسهٔ رکورد UUID مستقل است. `requestId` و
`attemptId` و `policyId` ستون UUID ساده‌اند — **FK ندارند** تا purge
ردیف‌های مرجع (§9) زنجیرهٔ حسابرسی را پاره نکند و ترتیب حذف مهم نباشد.

### 4.2 واژگان بسته

`AUDIT_ACTIONS` دقیقاً این ۱۵ مقدار است (۹ تای §36 + ۶ تای O):

```text
AIRequestCreated، AIRequestStarted، AIRequestCompleted، AIRequestFailed،
AIResponseGenerated، AIModelChanged، PromptVersionActivated،
AIUsageRecorded، AIFeedbackReceived،
GovernanceAllow، GovernanceDeny، GovernancePolicyDefined،
GovernancePolicyUpdated، QuotaDenied، RetentionPurged
```

مقادیر به‌صورت SCREAMING_SNAKE در دامنه نگه داشته می‌شوند
(`REQUEST_CREATED`، …، `GOVERNANCE_ALLOW`، …). action نامعتبر →
`AIAuditRecordInvalid` (422). actor از `ACTOR_TYPES =
(USER، SYSTEM، SERVICE، API_KEY)`؛ نتیجه از `AUDIT_OUTCOMES = (RECORDED،
ALLOWED، DENIED، SUCCEEDED، FAILED، DEFINED، UPDATED، PURGED)`.

### 4.3 Append-only

سرویس دامنه هیچ متد update/delete ندارد؛ پورت store متد update ندارد؛ تنها
حذف مجاز `deleteBefore` سیاستی است (§9) که خودش ثبت می‌شود. خواندن‌ها همیشه
tenant-scopedاند (شناسهٔ tenant دیگر = not-found).

---

## 5. قرارداد Tamper-Evidence

- `hash = sha256(tenantId ‖ prevHash ‖ payload-canonical-JSON)`؛
- `prevHash` رکورد اول هر tenant رشتهٔ ثابت `GENESIS` است؛
- `verifyAuditChain` روی رکوردهای مرتب `(occurredAt، id)`: بازمحاسبهٔ هر
  hash، تطبیق پیوند، و تشخیص fork (استفادهٔ دوباره از یک `prevHash`
  غیر-GENESIS). هر تخلف → `AIAuditTrailTampered` (500) با جزئیات
  (شناسهٔ رکورد، نوع تخلف)؛
- ترتیب زنجیره با دنبال‌کردن لینک‌ها (نه مرتب‌سازی زمانی) به دست می‌آید،
  پس رکوردهای هم‌میکروثانیه هم قابل‌راستی‌آزمایی‌اند؛ head زنجیره نوک آن
  است (رکوردی که هیچ‌کس به آن اشاره نکرده) نه آخرین رکورد مرتب‌سازی؛
- purge نگهداشت، بازماندگان را در همان تراکنش rebase می‌کند (قدیمی‌ترین
  بازمانده genesis جدید + بازمحاسبهٔ روبه‌جلو) تا verify سخت‌گیرانه همیشه
  برقرار بماند؛ hashها ذاتاً chain-relativeاند و meta رکورد purge، rebase
  مجاز را سند می‌کند؛
- محدودیت ثبت‌شده: خواندن head و نوشتن دو فراخوانی‌اند؛ appendهای کاملاً
  هم‌زمان می‌توانند fork قابل‌تشخیص بسازند (نه گم‌شدگی) — سریال‌سازی با
  worker فاز P؛ verify در خواندن‌های حساس Z صدا زده می‌شود.

---

## 6. قرارداد Privacy و Scrub (§47)

- `scrubDetail` روی dict/list/tuple بازگشتی است؛ کلیدی که یکی از الگوها را
  داشته باشد (`api_key`، `secret`، `password`، `token`، `bearer`،
  `authorization`، `private_key`، `client_secret`، `access_key`، `session`،
  `cookie`، `credentials`، …) مقدارش `[REDACTED]` می‌شود؛ کلمهٔ `token`
  فقط به‌صورت whole-word یا پسوند `*_token` تطبیق می‌کند تا شمارنده‌های
  metering (مثل `totalTokens`) از scrub جان سالم به در ببرند؛ مقادیر
  غیر-JSON به `repr` می‌افتند؛ عمق بازگشت محدود است؛
- قاعدهٔ RESTRICTED: اگر `classification == RESTRICTED` و پرچم
  `allowRestrictedDetail` (سطح فراخوانی، پیش‌فرض از
  `AI_AUDIT_INCLUDE_RESTRICTED_DETAIL=false`) خاموش باشد، کل `detail` با
  نشانگر redact جایگزین می‌شود — ارجاع‌ها (`contextSources` به شکل
  `domain:type:id`) می‌مانند چون محتوا نیستند؛
- تست‌ها: هیچ Secret/محتوایی در سطر ذخیره‌شده نیست (بازخوانی مستقیم سطر).

---

## 7. قرارداد Governance (§48)

### 7.1 سیاست

`AIGovernancePolicy`: یک سیاست برای هر tenant (یکتایی `tenantId`) با
`allowedProviders`/`allowedModels` (لیست خالی = بدون محدودیت — مستند)،
`disabledCapabilities` (deny صریح)، `allowRestrictedToExternal`
(پیش‌فرض False)، `maxCostPerDay` (صفر = نامحدود) + `currency`، وضعیت فعال،
توضیح. نبود سیاست tenant = پیش‌فرض‌های پلتفرم از settings (جایگزینی در سطح
کل آبجکت، نه فیلدبه‌فیلد — مستند).

### 7.2 ارزیابی

ورودی `GovernanceRequest`: tenant، actor، کدهای capability/provider/model،
`providerIsExternal` (را voter — رجیستری آداپتور — می‌داند؛ O طبقه‌بندی
نوع provider را اختراع نمی‌کند)، classification، `estimatedCost` و
`daySpend` (اختیاری؛ Z دومی را از summary مصرف N می‌دهد). ترتیب ثابت:

1. قابلیت غیرفعال → DENY؛
2. provider خارج از allowlist (اگر لیست ناخالی) → DENY؛
3. model خارج از allowlist (اگر لیست ناخالی) → DENY؛
4. RESTRICTED + external + بدون مجوز → DENY؛
5. بودجه: اگر سقف > ۰ و هر دو مبلغ داده شده: ناسازگاری ارز →
   `AIConfigurationError`؛ پیش‌بینی (مصرف + برآورد) > سقف → DENY؛
   اگر `daySpend` داده نشده، قاعدهٔ بودجه رد می‌شود (مستند، نه fail)؛
6. در غیر این صورت ALLOW.

خروجی `GovernanceDecision` با `reasons` (قاعده + پیام برای هر قاعدهٔ
ارزیابی‌شده)؛ `raiseForDecision` روی DENY خطای `AIGovernanceDenied` (403)
با اولین دلیل می‌دهد. **هر تصمیم** (ALLOW و DENY) با snapshot قواعد در
دفتر ثبت می‌شود تا پس از ویرایش سیاست هم قابل‌توضیح بماند.

---

## 8. قرارداد Ports و Application Service

پورت‌ها (`auditPorts.py`): `AuditRecordStore` (append/get/list با فیلتر
action/actor/request/outcome/بازه + `latestHash` + `deleteBefore`)،
`GovernancePolicyStore` (save/get/update/setActive — الگوی N)،
`RetentionPurger` (purgeAuditBefore/purgeAttemptsBefore/purgeCountersBefore
→ شمارش). پیاده‌سازی purge جدول‌های N در فایل جدید O است؛ فایل‌های N
دست‌نخورده می‌مانند.

`AuditApplicationService`:

- `defineGovernancePolicy` / `updateGovernancePolicy` /
  `deactivateGovernancePolicy` / `describeGovernancePolicy` (هر تغییر سیاست
  خودش یک رکورد `GOVERNANCE_POLICY_DEFINED/UPDATED` می‌سازد)؛
- `evaluateGovernance` (ارزیابی دامنه → ثبت تصمیم → raise در DENY؛ خروجی
  `GovernanceGrant`)؛
- `logAudit` (عمومی؛ اعتبارسنجی action، scrub، append)؛
- `logQuotaDenial` (از روی `PolicyDenial` فاز N — بدون import از سرویس N،
  فقط شکل داده)؛
- `ingestUsageRecorded` (از روی حامل `AIUsageRecorded` — بدون محتوا از
  روی ساخت)؛
- `listAuditEntries` / `verifyTenantChain` / `purgeAuditRetention` /
  `purgeUsageRetention` (هر purge پس از اتمام، meta رکورد `RETENTION_PURGED`
  با شمارش‌ها می‌سازد تا خودش purge نشود)؛
- `AuditUsageEventSink(UsageEventSink)` تحقق binding درون‌فرایندی N→O؛
- غیرفعال بودن (`AI_AUDIT_ENABLED=false` / `AI_GOVERNANCE_ENABLED=false`) →
  `AIConfigurationError`، fail-closed.

---

## 9. قرارداد Retention (§46)

- پیش‌فرض‌ها: audit ‏۳۶۵ روز (`AI_AUDIT_RETENTION_DAYS`)، مصرف ۹۰ روز
  (`AI_USAGE_RETENTION_DAYS` از N)؛ کران = `now − days` (روز < ۱ نامعتبر)؛
- purge اتمیک در سطح store (یک `DELETE` با فیلتر) و شمارش دقیق برمی‌گرداند؛
- meta رکورد `RETENTION_PURGED` با `occurredAt=now` پس از purge ساخته
  می‌شود پس در همان purge پاک نمی‌شود و روی head جدید زنجیره می‌نشیند؛
- **افق idempotency:** purge attemptها replay کلیدهای قدیمی را غیرممکن
  می‌کند — `AI_USAGE_RETENTION_DAYS` باید از افق idempotency کسب‌وکار
  بزرگ‌تر باشد (ثبت‌شده، نه پنهان)؛
- حذف شمارنده/attempt هرگز به audit سرایت نمی‌کند (ارجاع بدون FK، §4.1).

---

## 10. قرارداد Configuration (§42)

```text
AI_AUDIT_ENABLED / AI_AUDIT_RETENTION_DAYS / AI_AUDIT_INCLUDE_RESTRICTED_DETAIL
AI_GOVERNANCE_ENABLED / AI_GOVERNANCE_DEFAULT_MAX_COST_PER_DAY / AI_GOVERNANCE_DEFAULT_CURRENCY
```

کلیدهای `aiAudit*`/`aiGovernance*` در `.env.example` با همان مقادیر
پیش‌فرض. صفرِ بودجه یعنی نامحدود؛ سیاست صریح tenant بر پیش‌فرض پلتفرم مقدم
است (در سطح کل آبجکت).

---

## 11. قرارداد Event (§36)

O واژگان action را مالک است و دو binding درون‌فرایندی می‌دهد
(`AuditUsageEventSink`، `logQuotaDenial`)؛ transport روی باس با P است.
وقایع چرخه‌عمر G (`REQUEST_CREATED` …) توسط M/Z با `logAudit` ثبت می‌شوند —
O هیچ کدی از G را تغییر نمی‌دهد.

---

## 12. Purity و Dependency Rules

- دامنهٔ O هیچ import از `django`/`rest_framework`/`redis`/`channels` و هیچ
  ماژول infrastructure ندارد؛
- نام‌گذاری camelCase و PascalCase (تست‌های معماری موجود)؛
- `mypy` روی هر ۷ فایل جدید O بدون خطا؛ `ruff check` و `ruff format` روی
  سطح O سبز؛ `models.py` روی ۱۲۹ خطای پیشین می‌ماند (افزودهٔ O صفر)؛
- محدودیت‌های ثبت‌شده: fork زنجیره در race (قابل‌تشخیص، §5)؛ قاعدهٔ بودجه
  بدون `daySpend` رد می‌شود (§7.2)؛ evaluate→append دو فراخوانی‌اند (تصمیم
  و رکوردش در یک تراکنش نیستند — Z در API با تراکنش می‌پوشاند)؛
- caveat تست (از N): `createdAt` سطرها زمان persistence است؛ `occurredAt`
  audit صریح دامنه است و در تست‌ها قطعی می‌ماند.

---

## 13. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/valueObjects/auditTypes.py
backend/apps/ai/domain/entities/auditRecords.py
backend/apps/ai/domain/services/auditTrail.py
backend/apps/ai/domain/services/governance.py
backend/apps/ai/domain/auditPorts.py
backend/apps/ai/application/services/auditService.py
backend/apps/ai/infrastructure/repositories/__init__.py   (export جدید)
backend/apps/ai/infrastructure/repositories/auditRepositories.py
backend/apps/ai/infrastructure/models.py                (افزایشی: ۲ مدل)
backend/apps/ai/infrastructure/migrations/0003_auditGovernance.py
backend/apps/ai/domain/entities/__init__.py
backend/apps/ai/domain/valueObjects/__init__.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py       (۷ خطای جدید)
backend/apps/ai/domain/exceptions/__init__.py
backend/config/settings/base.py                         (AI_AUDIT_*/AI_GOVERNANCE_*)
backend/.env.example                                    (aiAudit*/aiGovernance*)

backend/tests/unit/testPhase13AuditGovernance.py
backend/tests/application/testPhase13AuditUseCases.py
backend/tests/integration/testPhase13AuditContract.py

docs/Phases/Phase13/Phase13-O.md
docs/Phases/Phase13/Phase13-O-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

APIهای اصلی:

```text
AUDIT_ACTIONS / ACTOR_TYPES / AUDIT_OUTCOMES / SECRET_KEY_PATTERNS
ensureAuditAction / ensureActorType / ensureAuditOutcome
AIAuditEntry / AIGovernancePolicy / GovernanceRequest / GovernanceDecision / DecisionReason
auditEntryHash / verifyAuditChain / scrubDetail
AuditTrailService / AuditEntryDescriptor / AuditEntryFilter / RetentionCutoff
GovernanceService / GovernanceEvaluation / GovernanceGrant? (app) / raiseForDecision
AuditRecordStore / GovernancePolicyStore / RetentionPurger
AuditApplicationService / AuditSettings / AuditUsageEventSink / GovernancePolicyCommand
DjangoAuditRecordStore / DjangoGovernancePolicyStore / DjangoRetentionPurger
```

Aliasها:

```text
AuditLog / InMemoryAuditTrail / AIAuditService
GovernancePolicyService / InMemoryGovernance / AIGovernanceService
AuditTrailApplicationService / AIAuditTrailService
```

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. **M:** executor پیش از هر تلاش `evaluateGovernance` و پس از هر گذار
   `logAudit` را صدا می‌زند؛ تصمیم حکمرانی در سطح request گرفته شود یا
   attempt (هزینهٔ audit هر attempt)؟
2. **Z:** هم‌گرایی ledger جدید `aiAuditTrail` با `aiAuditRecords` قدیمی و
   `AIService.generate`؛ verify زنجیره در خواندن‌های حساس API؛
3. **P:** سریال‌سازی appendهای هم‌زمان (حذف fork §5) + transport باس؛
4. **O-بعدی/بودجه:** اتصال `daySpend` از summary مصرف N در Z؛ ارز واحد
   بودجه در برابر tenantهای چندارزی (فعلاً fail-closed)؛
5. **امضا:** آیا زنجیره به امضای KMS/HSM نیاز دارد یا hash داخلی کافی است؟
   (تصمیم governance، خارج از ۱۳).

---

## 15. Acceptance Criteria

- [x] موجودیت `AIAuditEntry` با همهٔ فیلدهای §28 و ارجاع بدون FK ساخته شد؛
- [x] واژگان بستهٔ ۱۵تایی action (پوشش کامل §36) با خطای 422 روی مقدار
  نامعتبر پیاده شد؛
- [x] append-only در هر سه لایه (بدون update در سرویس و پورت) پیاده شد؛
- [x] زنجیرهٔ hash با مبدأ GENESIS + تشخیص پیوند شکسته و fork پیاده شد؛
- [x] scrubber بازگشتی Secret + قاعدهٔ RESTRICTED پیاده و با بازخوانی سطر
  اثبات شد؛
- [x] `contextSources` فقط ارجاع `domain:type:id` حمل می‌کند (بدون محتوا)؛
- [x] سیاست حکمرانی تک‌تایی tenant با هر پنج محور §48 پیاده شد؛
- [x] ترتیب ثابت شش‌مرحله‌ای ارزیابی + خروجی مستدل ALLOW/DENY پیاده شد؛
- [x] بودجه با ورودی اختیاری مصرف روز؛ ناسازگاری ارز fail-closed؛
- [x] هر تصمیم (ALLOW و DENY) با snapshot قواعد ثبت می‌شود؛
- [x] `AIGovernanceDenied` روی 403 با اولین دلیل؛
- [x] ingestion حامل N بدون محتوا + API ثبت `QUOTA_DENIED`؛
- [x] retention audit و جدول‌های N با meta رکورد شمارش‌دار؛
- [x] افق idempotency در برابر retention مستند شد؛
- [x] دو جدول + مهاجرت `0003_auditGovernance` بدون drift؛ فایل‌های N
  دست‌نخورده؛
- [x] تنظیمات `AI_AUDIT_*`/`AI_GOVERNANCE_*` پیکربندی‌محور؛
- [x] ایزولاسیون tenant در هر چهار لایه تست شد؛
- [x] تست‌های جدید سبز (واحد + کاربردی + یکپارچگی)؛
- [x] گیت کیفیت سطح O سبز (ruff/mypy/format/tests)؛
- [x] اتصال M/Z بدون نیاز به تغییر اسکیما (`logAudit`/`evaluateGovernance`)؛
- [x] مستندات قرارداد و گزارش + به‌روزرسانی README و سند مادر.

**نتیجه:** `GREEN — Phase 13-M may begin.`
