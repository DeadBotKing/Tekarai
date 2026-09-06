# گزارش اجرا — Phase 13-Y: Agent Foundation

**تاریخ:** 2026-09-06 · **وضعیت:** Agent Gate GREEN
**قرارداد:** [`Phase13-Y.md`](Phase13-Y.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل X (سوییت ۲۰۶۸ تست، ۶ شکست پیشین)

---

## ۱. خلاصهٔ تحویل

§31 یک جمله دارد: «Agent نباید فقط یک Prompt باشد». Y آن را به یک واقعیت
**ساختاری** تبدیل کرد: مدل فقط `AgentModelReply` تولید می‌کند — دادهٔ
فروزم و غیرقابل‌اعتماد. تنها مسیری که یک پیشنهاد به اجرا می‌رسد، حلقهٔ
برنامه‌ریزی-اجرا `AgentPlanner` است، و هر پیشنهاد پیش از آنکه به زنجیرهٔ
X برسد از **سطح دسترسی** Agent عبور می‌کند. Agent هیچ runner و هیچ SDK
نمی‌شناسد؛ پورت `AgentToolExecutor` تنها پنجره‌اش به ابزارهاست.

**Open Question شمارهٔ ۱۱ با دو محور بسته شد**:

- **چه می‌تواند بکند** — واژگان بستهٔ چهارمراتبهٔ
  `ADVISORY`/`READ_ONLY`/`MUTATING`/`AUTONOMOUS` با فهرست اثر، که
  *ساختاری* اعمال می‌شود: پیشنهادی فراتر از سطح هرگز به X نمی‌رسد و
  با هیچ تأییدی قابل «خرید» نیست (تست‌های
  `testProposalBeyondTheAccessLevelNeverReachesTheExecutor` و
  `testAdvisoryAgentCannotProposeAnyTool`)؛
- **چه کسی «بلی» بگوید** — ریسک به `AUTOMATIC`/`HUMAN_REQUIRED`/
  `DUAL_CONTROL` نگاشت می‌شود با همان نامتقارنی X (اعلام سخت‌گیرانه‌تر
  مجاز، بازتر ممنوع)، دو نفر **متمایز** برای dual control، و درخواست‌کننده
  نمی‌تواند اجرای خودش را تأیید کند.

**۱۴۲ تست جدید سبز** (۷۰ واحد + ۴۵ کاربردی + ۲۷ یکپارچگی). کل سوییت از
۲۰۶۸ به **۲۲۱۰ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های Y تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۶۵ mypy
— هر دو برابر عدد pristine با همان دستور اندازه‌گیری).

**چهار قطعهٔ X به Y پیوستند**: هویت و دستورالعمل (B)، قابلیت‌ها (F)،
ابزارها (X)، حافظه (T)، دانش (R/S) — همه زیر همان fail-closed.

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۸ فایل، ۳۹۲۰ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/agentTypes.py` | ۲۹۰ | واژگان سطح دسترسی + فهرست اثر، `AgentPolicy`، اثر انگشت ورودی، پاک‌سازی راز (دورزنی O/X) |
| `backend/apps/ai/domain/entities/agentRecords.py` | ۵۹۹ | `AIAgentDefinition` (نسخه‌ای، چرخهٔ حیات)، `AIAgentApproval` (dual control)، `AIAgentRun` (ماشین وضعیتِ دقیقاً B)، `AIAgentStep` + پل‌ها به موجودیت‌های B |
| `backend/apps/ai/domain/agentPorts.py` | ۱۴۸ | نه پورت: سه store، Model، ToolExecutor، Memory، Knowledge، Capability، Permission، Audit |
| `backend/apps/ai/domain/services/agentEngine.py` | ۷۷۵ | `AgentModelRequest`/`Reply`، `AgentContextBuilder`، `AgentGatekeeper`، `AgentRunBudget` (مشترک بین مراحل)، `AgentPlanner` — حلقهٔ plan-act |
| `backend/apps/ai/application/services/agentService.py` | ۱۳۲۹ | چرخهٔ رجیستری، اجرای چرخه، گردش‌کار تأیید، نگه‌داری، `ScriptedAgentModelCaller` (§41) و `ToolExecutorAdapter` (پل به زنجیرهٔ X) |
| `backend/apps/ai/infrastructure/repositories/agentRepositories.py` | ۴۶۲ | چهار store جنگو؛ sweep نگه‌داری فقط ردیف‌های تسویه‌شده |
| `backend/apps/ai/infrastructure/agentAdapters.py` | ۱۳۳ | Resolver قابلیت (F) + آداپتورهای حافظه (T) و دانش (R/S) — fail-closed به Context خالی |
| `backend/apps/ai/infrastructure/migrations/0012_agentPlatform.py` | ۱۸۴ | چهار جدول |

### ۲.۲ تست (۳ فایل، ۲۴۸۹ خط، ۱۴۲ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Agents.py` | ۷۰ | واژگان و یکنواختی allowlist، سیاست و نامتقارنی، اثر انگشت/پاک‌سازی، چهار موجودیت و چرخه‌های حیات، gatekeeper fail-closed، بودجهٔ مشترک و حلقه‌یابی بین مراحل، context builder، **حلقهٔ plan-act با تضمین ساختاری** (پیشنهاد فراتر از سطح هرگز به executor نمی‌رسد) |
| `backend/tests/application/testPhase13AgentUseCases.py` | ۴۵ | رجیستری، دروازهٔ اجرا با **K واقعی**، زنجیرهٔ **X واقعی** در دل اجرای Agent، دو محور OQ #11، گره‌خوردگی تأیید به اثر انگشت، TTL، چسبندگی رد، حافظه/دانش، پنهان‌سازی راز در ردیف اجرا، ایزولاسیون Tenant، نگه‌داری، حسابرسی |
| `backend/tests/integration/testPhase13AgentContract.py` | ۲۷ | قرارداد persistence چهار جدول، یکتایی نسخه در دیتابیس، جست‌وجوهای تأیید (pending/usable/latest شامل رد قابل‌یافتن)، ترتیب گام‌ها به‌عنوان ردیابی، sweep نگه‌داری، احیای ردیف‌های فاسد، resolver قابلیت |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | چهار مدل جدید |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۱۱ خطای جدید `AIAgent*` (کدهای `AI_AGENT_*`) |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۴۷ → ۵۱) |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های Y |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export سه store (+Mapperهای agent با پیشوند برای اجتناب از تداخل نام) |
| `config/settings/base.py` + `backend/.env.example` | بلوک `AI_AGENT_*` (۱۱ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۴۷ به ۵۱ |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت Y |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **حساب بودجه به شیوهٔ «claim» است** (`checkModelCall`/`checkToolCall`
   هم بررسی می‌کنند و سهم را ثبت). یک فراخوانی شکست‌خورده هم مرحله‌اش را
   مصرف می‌کند؛ اجرای Agent نمی‌تواند مدلِ کرش‌کرده را رایگان دوباره بزند.
   ردیف‌های *ردشدهٔ* دسترسی هم در شمار تکرار می‌آیند (سبک X): مدلی که
   مدام همان ابزارِ ممنوع را پیشنهاد بدهد، حلقه است حتی بدون تایمر.
2. **اثر انگشت ابزارِ اعلام‌نشده** (که نسخهٔ رجیستری ندارد) با نسخهٔ
   جانشین `1` ساخته می‌شود؛ کلید فقط برای تشخیص حلقه است و ذخیره
   نمی‌شود — ردیف گام، آرگومان‌های پاک‌شده را نگه می‌دارد.
3. **شناسهٔ فراخوانیِ ابزار، انسانِ شروع‌کنندهٔ اجراست** (Y-D12):
   `ToolExecutorAdapter` `actorId` را از `subjectId`ٔ principal می‌گیرد،
   نه از پیشنهاد مدل. Agent هویت نمی‌سازد؛ test
   `testPrincipalPropagatesToEveryToolCall` همین را تثبیت می‌کند.
4. **approvalId صریح و ناموجود یک خطای کارستنده است**
   (`AI_AGENT_APPROVAL_NOT_FOUND`)، نه «تأیید ندارد»: باز کردن خودکار
   تأیید تازه برای id اشتباه، تایپو را به اسپم بازبینی تبدیل می‌کرد.
   (توسعه‌ای دقیق‌تر نسبت به رفتار X.)
5. **پرواییدرِ حافظه/دانشی که خطا بدهد، برای آن اجرا *غایب* است** —
   اجرای Agent با Context خالی‌تر ادامه می‌یابد، هرگز «باز» (Y-D6).
   این fail-closed در دو لایه است: خودِ T/S و همچنین سرویس Y.
6. **دانش فقط با query صریح پرسیده می‌شود** (`query`/`question` در ورودی
   اجرا)؛ خودِ `task` دلیلِ فراخوانی retrieval نیست — دانش‌خوانی یک
   عمل خواندنیِ آگاهانه و حساب‌رسی‌پذیر است، نه پیش‌فرضِ هر اجرا.
7. **نگه‌داری Y سه لایه پاک می‌کند**: اجراهای تسویه‌شده + گام‌هایشان +
   (از طریق قرارداد store) تأییدهای تصمیم‌گرفته؛ اجراهای `PENDING` و
   تأییدهای در انتظار هرگز. `createdAt` که `auto_now_add` دارد فقط از
   مسیر `update` بازمحور می‌شود — تست‌ها همین مسیر را آزمایش می‌کنند.
8. **خروجی Structured فقط وقتی اسکیما اعلام شده اعتبارسنجی می‌شود**
   (بازاستفاده از `validateJsonSchema` فاز H)؛ شکست، اجرای را `FAILED`
   با `AI_AGENT_OUTPUT_INVALID` می‌کند.

## ۴. اثبات عمودی

با `AuthorizationService` واقعی فاز K و زنجیرهٔ `ToolApplicationService`
واقعی فاز X در یک اجرای Agent:

- Agent در `DRAFT` قابل اجرا نیست (`AI_AGENT_NOT_APPROVED`)؛
- بدون grant، اجرای Agent ردیف `DENIED` می‌گیرد و **مدل اصلاً صدا
  زده نمی‌شود**؛
- ریسک HIGH ⇒ ردیف اجرا `PENDING` + تأیید `PENDING` باز می‌شود و
  **هیچ Model Call انجام نمی‌شود**؛ پس از grant، اجرای بعدی (همان
  اثر انگشت) اجرا می‌شود؛
- ریسک CRITICAL ⇒ با یک تأیید هنوز مسدود؛ شخص دوم **متمایز** لازم است؛
  تکرار همان تأییدکننده و تأیید توسط درخواسته‌کننده هر دو رد می‌شوند؛
- رد کردن، تا پایان پنجره می‌چسبد: سه تلاش پیاپی، ردیف تأیید تازه
  نساخت (قاعدهٔ ضد اسپم X-D6)؛
- تأیید برای `{"task":"analyze A"}` مجوز `{"task":"analyze B"}` نیست —
  اثر انگشت ورودی، مرز تأیید است؛
- analystِ `READ_ONLY` پیشنهاد `CREATE_TASK` (`MUTATING`) بدهد: ردیف گام
  `DENIED` با `AI_AGENT_ACCESS_LEVEL_EXCEEDED`، **صفحهٔ فراخوانی X صفر**؛
  `DISPATCHER`ِ `AUTONOMOUS` همان ابزار `EXTERNAL` را با همان زنجیره اجرا
  می‌کند؛
- ابزارِ HIGH-risk در میانهٔ اجرا (Y-D11): اجرا متوقف **نمی‌شود**؛ گام
  `DENIED` با `AI_AGENT_TOOL_APPROVAL_REQUIRED`، X خودش تأیید را باز
  می‌کند و فراخوانی را `PENDING` پارک می‌کند، و مدل تصمیم می‌گیرد؛
- حلقه: همان فراخوانی در سه مرحلهٔ مختلف تشخیص داده می‌شود
  (`AI_AGENT_BUDGET_EXCEEDED`) — بودجه بین مراحل مشترک است (X-OQ #2 بسته)؛
- `apiKey` در ردیف اجرا `[REDACTED]` است، `task` سالم (تعریف مشترک O)؛
- حافظه و دانش فقط با query صریح و از مسیر T/S وارد Context می‌شوند؛
  نبود یا شکست پرواییدر ⇒ بخش خالی، نه Context باز.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد Y | ۷۰/۷۰ ✅ |
| تست کاربردی Y | ۴۵/۴۵ ✅ |
| تست یکپارچگی Y | ۲۷/۲۷ ✅ |
| سوییت کامل | **۲۲۱۰ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح Y | ✅ All checks passed |
| format سطح Y | ✅ formatted |
| type سطح Y | ✅ صفر خطا در فایل‌های Y |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۶۵ = عدد pristine (با همان دستور اندازه‌گیری) |
| مهاجرت `ai` | بدون drift (`makemigrations --check`) |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری/نام‌گذاری (قالب‌های `apps/ai/models.py`،
`apps/ai/tests/test_provider.py` و تست‌های معماری وابسته به آن‌ها)، ۲۹۳ ruff
و ۵۶۵ mypy مخزن — همه از baselineِ X، بدون اضافه یا کم.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۲۴ بند §۱۵ قرارداد با اجرای مستقیم تست تأیید شد؛ بند
«ساخت ردیف اجرا از تصمیم مجاز» با تست‌های `testRunningWithoutPermissionDeniesAndRecordsTheRow`
و `testHighRiskOpensApprovalAndMakesNoModelCall` و بند «هر گام ردیف
می‌شود» با `testStepRoundTripAndOrdinalOrdering` و `testStepOrdinalIsUniquePerRun`
پوشش داده شد.

## ۸. درخت بایگانی تحویل Y

```text
backend/apps/ai/
├── domain/
│   ├── agentPorts.py
│   ├── valueObjects/agentTypes.py
│   ├── entities/agentRecords.py
│   └── services/agentEngine.py
├── application/services/agentService.py
└── infrastructure/
    ├── models.py (+۴ مدل)
    ├── migrations/0012_agentPlatform.py
    ├── agentAdapters.py
    └── repositories/agentRepositories.py
backend/tests/{unit/testPhase13Agents.py,
  application/testPhase13AgentUseCases.py,
  integration/testPhase13AgentContract.py}
docs/Phases/Phase13/{Phase13-Y.md,Phase13-Y-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

`Phase 13-Z` (API عمومی، تصمیم اجراي ناهمگام و صف تأیید/اعلان، مهاجرت و
ریلیز) می‌تواند آغاز شود — پورت‌ها و ردیف‌هایی که Y ساخت، دقیقاً همان
سطحی است که REST باید روی آن بنشیند: هیچ رفتار جدیدی لازم نیست، فقط
معرّفی.

**نتیجهٔ Gate:** `GATE_Y=GREEN — Phase 13-Z may begin.`
