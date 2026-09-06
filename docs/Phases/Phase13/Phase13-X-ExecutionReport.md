# گزارش اجرا — Phase 13-X: Tool Registry و Tool Execution

**تاریخ:** 2026-09-05 · **وضعیت:** Tool Gate GREEN
**قرارداد:** [`Phase13-X.md`](Phase13-X.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل W (سوییت ۱۹۱۴ تست)

---

## ۱. خلاصهٔ تحویل

§30 یک جملهٔ کوتاه دارد: «AI نباید Tool را مستقیم اجرا کند». X آن را به
یک واقعیت **نوعی** تبدیل کرد: مدل فقط `ToolProposal` می‌سازد، runner فقط
`ExecutionTicket` می‌پذیرد، و تنها سازندهٔ Ticket تابعی است که یک
`GateDecision` مجاز می‌خواهد. مسیر میان‌بری از پیشنهاد خام به اجرا وجود
ندارد — تست `testABlockedDecisionCannotProduceATicket` دقیقاً همین را
تثبیت می‌کند.

**Open Question شمارهٔ ۱۰ بسته شد**: رجیستری یک چرخهٔ حیات پنج‌حالته است و
گردش‌کار تأیید، ریسک را به `AUTOMATIC` / `HUMAN_REQUIRED` / `DUAL_CONTROL`
نگاشت می‌کند — با دو نفر **متمایز** برای ریسک بحرانی و منع تأیید توسط
درخواست‌کننده.

**۱۵۴ تست جدید سبز** (۷۱ واحد + ۵۴ کاربردی + ۲۹ یکپارچگی). کل سوییت از
۱۹۱۴ به **۲۰۶۸ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های X تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۲۷۰۷ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/toolTypes.py` | ۲۸۵ | واژگان اثر/ریسک/تأیید/وضعیت، `ToolPolicy`، اثر انگشت، پاک‌سازی راز |
| `backend/apps/ai/domain/entities/toolRecords.py` | ۴۵۲ | `AIToolDefinition`، `AIToolApproval` (dual control)، `AIToolInvocation` + پل به فاز B |
| `backend/apps/ai/domain/services/toolEngine.py` | ۳۶۶ | `ToolProposal`، `ToolRegistry`، `ArgumentValidator`، `ToolGatekeeper`، `ExecutionBudget`، `ExecutionTicket` |
| `backend/apps/ai/domain/toolPorts.py` | ۱۲۱ | شش پورت، از جمله `ToolRunner` که فقط Ticket می‌پذیرد |
| `backend/apps/ai/application/services/toolService.py` | ۹۳۶ | چرخهٔ رجیستری، زنجیرهٔ اجرا، گردش‌کار تأیید، `CallableToolRunner` |
| `backend/apps/ai/infrastructure/repositories/toolRepositories.py` | ۴۰۷ | سه store جنگو |
| `backend/apps/ai/infrastructure/migrations/0011_toolPlatform.py` | ۱۴۰ | سه جدول |

### ۲.۲ تست (۳ فایل، ۱۷۰۲ خط، ۱۵۴ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Tools.py` | ۷۱ | واژگان، سیاست، اثر انگشت/پاک‌سازی، سه موجودیت، رجیستری، اعتبارسنجی، gatekeeper، بودجه، **ناممکن‌بودن ساخت Ticket از تصمیم مسدود** |
| `backend/tests/application/testPhase13ToolUseCases.py` | ۵۴ | رجیستری، زنجیرهٔ §30 با **K واقعی**، گردش‌کار تأیید و dual control، بودجه، خواندن، نگه‌داری، حسابرسی |
| `backend/tests/integration/testPhase13ToolContract.py` | ۲۹ | قرارداد persistence سه جدول، جست‌وجوهای تأیید، تاریخچهٔ اثر انگشت، نگه‌داری |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | سه مدل جدید |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۱۰ خطای جدید X (`AIToolDenied` فاز B بازاستفاده شد) |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۴۳ → ۴۷) |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های X |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export سه store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_TOOL_*` (۹ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۴۳ به ۴۷ |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت X |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **پاک‌سازی راز به فاز O واگذار شد.** پیاده‌سازی اول الگوهای مخفی را
   خودش تطبیق می‌داد؛ تست نشان داد این نسخهٔ دوم با تعریف پلتفرم فرق
   می‌کند (بهویژه دربارهٔ `token` که O عمداً استثنا کرده تا `totalTokens`
   متریک زنده بماند). X حالا مستقیم `isSecretKey` را صدا می‌زند: یک
   تعریف، یک نقطهٔ اصلاح. تست جداگانه‌ای این واگذاری را تثبیت می‌کند.
2. **رد کردن تا پایان پنجره‌اش می‌چسبد (X-D6).** پیاده‌سازی اول پس از یک
   «نه» اجازه می‌داد همان پیشنهاد بلافاصله دوباره باز شود؛ یعنی یک Agent
   در حلقه می‌توانست بازبینی انسانی را به اسپم تبدیل کند. حالا یک رد
   زندهٔ هم‌اثرانگشت مستقیم `AI_TOOL_DENIED` می‌دهد و تست ثابت می‌کند
   سه تلاش پیاپی **یک** ردیف تأیید بیشتر نمی‌سازد.
3. **`findLatest` به پورت اضافه شد** تا رد قابل یافتن باشد، نه فقط تأیید.
4. **timeout تیکت هرگز از سیاست فراتر نمی‌رود** حتی اگر ابزار عدد بزرگ‌تری
   اعلام کند.
5. **runner فقط آرگومان‌های اعتبارسنجی‌شده را می‌بیند** — نه principal، نه
   پیشنهاد خام. یک پیاده‌سازی ابزار نمی‌تواند اختیار خودش را گسترش دهد.
6. **بودجه = کمینهٔ سقف سیاست و سقف خود ابزار**، پس ابزار حساس می‌تواند
   سخت‌گیرتر از پلتفرم باشد.

## ۴. اثبات عمودی

با `AuthorizationService` واقعی فاز K:

- ابزار `DRAFT` هرگز اجرا نمی‌شود (`AI_TOOL_NOT_APPROVED`)؛
- بدون grant، فراخوانی `AI_TOOL_DENIED` می‌گیرد و **ردیفش با وضعیت DENIED
  ثبت می‌شود**؛
- grant محدود به یک ابزار، ابزار دوم را باز نمی‌کند؛
- ریسک HIGH ⇒ اجرا متوقف، تأیید باز می‌شود، runner صدا زده **نمی‌شود**؛
  پس از grant توسط شخص دوم، همان پیشنهاد اجرا می‌شود؛
- ریسک CRITICAL ⇒ با یک تأیید هنوز مسدود؛ با دو تأییدکنندهٔ متمایز اجرا؛
- تأیید برای `{"projectId":"P-1"}` مجوز `P-2` نیست؛
- `apiKey` در ردیف دیتابیس `[REDACTED]` است، `projectId` سالم.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد X | ۷۱/۷۱ ✅ |
| تست کاربردی X | ۵۴/۵۴ ✅ |
| تست یکپارچگی X | ۲۹/۲۹ ✅ |
| سوییت کامل | **۲۰۶۸ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح X | ✅ All checks passed |
| format سطح X | ✅ formatted |
| type سطح X | ✅ صفر خطا در فایل‌های X |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۲۲ بند §۱۵ قرارداد با اجرای مستقیم تست تأیید شد.

## ۸. درخت بایگانی تحویل X

```text
backend/apps/ai/
├── domain/
│   ├── toolPorts.py
│   ├── valueObjects/toolTypes.py
│   ├── entities/toolRecords.py
│   └── services/toolEngine.py
├── application/services/toolService.py
└── infrastructure/{models.py,migrations/0011_toolPlatform.py,
    repositories/toolRepositories.py}
backend/tests/{unit/testPhase13Tools.py,
  application/testPhase13ToolUseCases.py,
  integration/testPhase13ToolContract.py}
docs/Phases/Phase13/{Phase13-X.md,Phase13-X-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-Y — Agent Foundation**: §31. موجودیت‌های `AIAgent` و
`AIAgentExecution` و واژگان `AGENT_EXECUTION_STATUSES` از فاز B موجودند.
Y باید Open Question شمارهٔ ۱۱ (سطح دسترسی Agent و تأیید انسانی) را ببندد
و همهٔ قطعات را به هم وصل کند: هویت و دستورالعمل، قابلیت‌ها (F)، ابزارها
(X)، حافظه (T) و دانش (R/S) — زیر همان حکمرانی fail-closed.

**تحویل:** فایل `Tekarai-Phase13-X.zip` (checksum در فایل جانبی `.sha256`).
