# Phase 13-Y — Agent Foundation

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** Y از A تا Z
**وضعیت:** CONTRACT — آمادهٔ اجرا
**تاریخ قرارداد:** 2026-09-06
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§17، §30، §31، §38، §42، §43، §46، §47)
**قراردادهای قبلی:** [B](Phase13-B.md) (`AIAgent`/`AIAgentExecution`/`AGENT_EXECUTION_STATUSES`)،
[F](Phase13-F.md) (Capability Registry)، [K](Phase13-K.md) (مجوز)،
[O](Phase13-O.md) (حسابرسی و `isSecretKey`)، [S](Phase13-S.md) (Retrieval)،
[T](Phase13-T.md) (Memory)، [X](Phase13-X.md) (Tool Registry و `ExecutionTicket`)
**گزارش اجرا:** [`Phase13-Y-ExecutionReport.md`](Phase13-Y-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

§31 فهرست می‌کند و بعد یک جمله می‌گوید که کل زیر‌فاز از آن می‌آید:

> **Agent نباید فقط یک Prompt باشد.**

Agent در Y نه یک Prompt و نه یک Function در `views.py` است؛ یک **عقدهٔ
حکمرانی‌شده** است که روی همان پلتفرمی ساخته می‌شود که §30 ساخت: هویت و
دستورالعمل نسخه‌ای، قابلیت‌های ثبت‌شده (F)، ابزارهای ثبت‌شده (X)، حافظه
مجازشده (T)، دانش مجازشده (R/S) — همه زیر همان fail-closed.

سؤال معماری Y — **Open Question شمارهٔ ۱۱**:

> **سطح دسترسی Agent و تأیید انسانی چه می‌شوند؟**

پاسخ Y دو محور دارد که باید از هم جدا بمانند:

1. **چه می‌تواند بکند** (Access Level) — واژگان بستهٔ چهارمراتبه که
   *ساختاری* اعمال می‌شود: پیشنهادی که اثرش از سطح بالاتر باشد هرگز به
   زنجیرهٔ X نمی‌رسد؛ اصلاً قابل «اجازه گرفتن» نیست.
2. **چه کسی «بلی» بگوید** (Approval) — ریسکِ Agent به
   `AUTOMATIC` / `HUMAN_REQUIRED` / `DUAL_CONTROL` نگاشت می‌شود با همان
   قاعدهٔ نامتقارن X (اعلام سخت‌گیرانه‌تر مجاز، بازتر ممنوع).

سطح دسترسی می‌تواند MUTATING باشد و تأیید AUTOMATIC؛ می‌تواند READ_ONLY
باشد و تأیید DUAL_CONTROL. قاطی‌کردن این دو محور دقیقاً همان اشتباهی است
که OQ #11 از آن می‌پرسید.

سؤال دوم، **پیوستن قطعات**: مدل فقط `AgentModelReply` تولید می‌کند و
runner ابزار همان runner همیشه‌است — زنجیرهٔ X. مسیر «پاسخ مدل → اجرا»
فقط از طریق Planner است که هر مرحله را با بودجه، دسترسی و ثبت گام
می‌بیند. Agent هیچ SDK و هیچ Runner را نمی‌شناسد.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ سطح دسترسی، وضعیت رجیستری، نوع گام و وضعیت گام؛
2. `AgentPolicy` که ریسک را به تأیید نگاشت می‌کند و بودجه را می‌سازد
   (بستن OQ #11 — نیمهٔ تأیید)؛
3. اثر انگشت ورودی اجرا و پاک‌سازی راز با تعریف مشترک پلتفرم (O/X)؛
4. سه موجودیت اصلی: تعریف نسخه‌ای (`AIAgentDefinition`)، تأیید انسانی
   (`AIAgentApproval`)، اجرا (`AIAgentRun`) + ردیف گام (`AIAgentStep`) —
   با پل به موجودیت‌های `AIAgent`/`AIAgentExecution` فاز B؛
5. `AgentGatekeeper`، `AgentContextBuilder`، `AgentRunBudget`، `AgentPlanner`؛
6. هش پورت: `AgentModelCaller`، `AgentToolExecutor`،
   `AgentMemoryProvider`، `AgentKnowledgeProvider`، `AgentCapabilityResolver`؛
7. سرویس اپلیکیشن: چرخهٔ رجیستری، اجرای چرخهٔ برنامه‌ریزی-اجرا،
   گردش‌کار تأیید، خواندن، نگه‌داری + `ScriptedAgentModelCaller`
   (تست‌پرواییدر قطعی مطابق §41)؛
8. چهار جدول و مهاجرت `0012_agentPlatform`؛
9. پیکربندی `AI_AGENT_*`؛
10. چهار action حسابرسی (`AGENT_REGISTERED` … `AGENT_DENIED`)؛
11. سه سطح تست، شامل چرخهٔ کامل با موتور مجوز واقعی K و ابزارهای واقعی X.

### 2.2 خارج از Scope

- **اجرای ناهمگام Agent و kind صف `AGENT_RUN`** — خاتمهٔ صریح: Y هم‌زمان
  است؛ Z با API تصمیم می‌گیرد (تصمیم Y-D5)؛
- **صف تأیید و اعلان به تأییدکننده از طریق فاز ۱۲** — Z (X-OQ #3)؛
- **Orchestration چند-Agent** (Agent که Agent را صدا بزند) — پس از Z؛
- **Model Routing واقعی داخل Agent** — E مالک Routing است؛ Y فقط
  `modelPolicy` را به‌عنوان Metadata شفاف به Port Model می‌دهد؛
- **API عمومی** — زیر‌فاز Z؛
- **تغییر موجودیت‌های فاز B** — پل‌ها از سمت Y ساخته می‌شوند.

---

## 3. جایگاه معماری

```text
Application (AgentApplicationService، ScriptedAgentModelCaller،
             ToolExecutorAdapter)
   │  ├─ AgentDefinitionStore / ApprovalStore / ExecutionStore
   │  ├─ AgentPermissionChecker   → Phase 13-K
   │  ├─ AgentToolExecutor        → Phase 13-X (زنجیرهٔ §30)
   │  ├─ AgentMemoryProvider      → Phase 13-T (فیلتر K داخلی)
   │  ├─ AgentKnowledgeProvider   → Phase 13-R/S (فیلتر K داخلی)
   │  ├─ AgentCapabilityResolver  → Phase 13-F
   │  └─ AgentAuditLogger         → Phase 13-O
   ↓
Domain (AgentPolicy، AgentGatekeeper، AgentContextBuilder،
        AgentRunBudget، AgentPlanner)             ← خالص، بدون جنگو
   ↓
Ports (AgentModelCaller / AgentToolExecutor / …)
   ↓
Infrastructure (Django Stores، Adapters، مهاجرت 0012)
```

Domain Y هیچ‌گاه `ToolApplicationService` را نمی‌شناسد؛ فقط پورت
`AgentToolExecutor` را. همین فاصله است که §30 را برای Agent هم ساختاری
می‌کند.

---

## 4. قرارداد تعریف Agent

| فیلد | نقش |
|---|---|
| `code` + `version` | کلید طبیعی؛ نسخه‌ها **تغییرناپذیر**ند |
| `instructions` | دستورالعمل نسخه‌ای؛ سقف بایتی از سیاست |
| `accessLevel` | `ADVISORY` / `READ_ONLY` / `MUTATING` / `AUTONOMOUS` |
| `riskLevel` | `LOW` … `CRITICAL` — محرک تأیید (واژگان مشترک با X) |
| `capabilityCodes` | قابلیت‌های **ثبت‌شده در F** که Agent ادعا می‌کند |
| `toolCodes` | ابزارهای **ثبت‌شده در X** که Agent مجاز به پیشنهادشان است |
| `outputSchema` | زیرمجموعهٔ JSON Schema فاز H؛ برای `structured` |
| `contextPolicy` | سقف‌های Context: توکن کل، حافظه، دانش |
| `modelPolicy` | Metadata شفاف برای Port Model (Routing با E) |
| `permissionPolicy` | کد مجوز K (پیش‌فرض `AI_AGENT_RUN`) |
| `executionPolicy` | `maxSteps`/`maxToolCalls`/`maxDurationSeconds` |
| `declaredApprovalMode` | فقط می‌تواند **سخت‌گیرانه‌تر** از سیاست باشد |

تغییر هر فیلد یعنی **نسخهٔ جدید**؛ یک اجرا در حال انجام به نسخه‌ای که
با آن شروع کرده گره خورده است (تصمیم Y-D8).

### 4.1 سطح دسترسی — واژگان بسته

| سطح | اثرهای مجاز ابزار |
|---|---|
| `ADVISORY` | هیچ — Agent صرفاً پاسخ متنی برای انسان |
| `READ_ONLY` | `READ_ONLY` |
| `MUTATING` | `READ_ONLY` + `MUTATING` + `NOTIFYING` |
| `AUTONOMOUS` | همهٔ چهار اثر (شامل `EXTERNAL`) |

قاعدهٔ ساختاری: `AgentPlanner` پیشنهادی که اثرش در فهرست سطح نباشد را
به X نمی‌دهد؛ ردیف گام `DENIED` با کد پایدار می‌گیرد. Agent نمی‌تواند
با تأیید بیشتر، اثر بالاتر بخواهد — سطح در تعریف نسخه‌ای است، نه در
گردش‌کار.

---

## 5. قرارداد رجیستری (آینهٔ X)

`DRAFT → PENDING_APPROVAL → APPROVED → SUSPENDED ⇄ APPROVED → RETIRED`

- Agent در `DRAFT` متولد می‌شود و **هرگز** مستقیم اجرا نمی‌شود؛
- رد کردن دلیل اجباری دارد و به `DRAFT` برمی‌گرداند؛
- `RETIRED` پایانی است؛
- `resolve` بدون نسخه، **آخرین نسخهٔ APPROVED** را می‌دهد.

---

## 6. قرارداد سیاست ریسک/تأیید (نیمهٔ دوم OQ #11)

| ریسک | حالت پیش‌فرض | تعداد تأییدکننده |
|---|---|---|
| LOW / MEDIUM | `AUTOMATIC` | ۰ |
| HIGH | `HUMAN_REQUIRED` | ۱ |
| CRITICAL | `DUAL_CONTROL` | ۲ (دو نفر متمایز) |

نگاشت از پیکربندی می‌آید (`aiAgentAutomaticBelowRisk`،
`aiAgentDualControlAtRisk`) و قاعدهٔ نامتقارن X-D4 بدون تغییر اعمال
می‌شود: یک تعریف Agent نمی‌تواند خودش را از بازبینی انسانی معاف کند.

---

## 7. قرارداد گردش‌کار تأیید (OQ #11 — کامل)

- تأیید به **اثر انگشت ورودی اجرا** گره خورده است: تأیید برای
  `{"task":"تحلیل پروژه A"}` مجوز `{"task":"تحلیل پروژه B"}` نیست؛
- `DUAL_CONTROL` دو نفر **متمایز** می‌خواهد؛
- **درخواست‌کننده نمی‌تواند اجرای خودش را تأیید کند**؛
- تأیید TTL دارد؛ منقضی که شد، دوباره باید پرسید؛
- **رد کردن تا پایان همان پنجره می‌چسبد** (قاعدهٔ ضد اسپم X-D6)؛
- تأیید Agent در **لحظهٔ شروع اجرا** اعمال می‌شود. ابزارِ در میانهٔ اجرا
  که خودش نیاز به تأیید انسانی داشته باشد، در Y اجرا نمی‌شود: گام
  `DENIED` ثبت می‌شود، دلیل به Context کار می‌رسد و مدل تصمیم می‌گیرد
  (تصمیم Y-D11) — چون واژگان فاز B برای اجرای متوقف‌شدهٔ Agent حالت
  ندارد و افزودن حالت پنهانی ممنوع است.

---

## 8. قرارداد اجرا — چرخهٔ برنامه‌ریزی-اجرا

1. رجیستری resolve می‌کند (آخرین نسخهٔ APPROVED یا نسخهٔ صریح)؛
2. ورودی با سقف بایت و اسکیما JSON اعتبارسنجی و پاک‌سازی می‌شود؛
3. **در ردیف اجرا، نسخهٔ Agent قفل می‌شود** (Y-D8)؛
4. مجوز K برای اجرای این Agent (کد `permissionPolicy`)؛
5. قابلیت‌های اعلام‌شده با رجیستری F چک می‌شوند — fail-closed؛
6. تصمیم Gatekeeper؛ اگر تأیید لازم و موجود نباشد: ردیف اجرا `PENDING`
   + تأیید `PENDING` باز می‌شود و **هیچ Model Call انجام نمی‌شود**؛
7. Context ساخته می‌شود: دستورالعمل + حافظه (T) + دانش (R/S) + ورودی —
   هر دو منبع فقط از مسیر مجازشدهٔ K؛ نبود Provider ⇒ Context خالی،
   هرگز «باز» (Y-D6)؛
8. حلقه: Model Reply → اگر پاسخ نهایی: اعتبارسنجی با `outputSchema` و
   `COMPLETED`؛ اگر پیشنهاد ابزار: اعمال سطح دسترسی → بودجه → زنجیرهٔ X
   → نتیجه به Context کار؛
9. هر Model Call و هر Tool Call — **حتی رد شده** — یک ردیف گام می‌شود
   (Y-D7)؛
10. بودجهٔ مشترک بین مراحل (Y-D4): تکرار اثر انگشت یکسان در کل اجرا
    حلقه است، حتی اگر در مراحل مختلف باشد؛
11. موفقیت/شکست/رد — همه ثبت و حسابرسی می‌شوند.

**هر درخواست اجرا یک ردیف می‌شود، حتی وقتی جواب «نه» است.**

---

## 9. قرارداد بودجه (بستن X-OQ #2)

| سقف | منبع | اثر |
|---|---|---|
| `maxSteps` | کمینهٔ سیاست و `executionPolicy` Agent | تعداد Model Call |
| `maxToolCalls` | کمینهٔ سیاست و `executionPolicy` Agent | کل فراخوانی ابزار در کل اجرا |
| `maxDurationSeconds` | کمینهٔ سیاست و `executionPolicy` Agent | زمان واقعی با ساعت تزریقی |
| تکرار اثر انگشت | `aiAgentMaxRepeatsPerRequest` | حلقه — بدون تایمر |
| `maxContextTokens` | کمینهٔ سیاست و `contextPolicy` Agent | سقف Context اولیه |

بودجه **یک نسخه برای کل اجرا** است و بین مراحل مشترک — نه هر مرحله
بودجهٔ تازه.

---

## 10. قرارداد پیکربندی (§42)

`aiAgentEnabled`, `aiAgentAutomaticBelowRisk`, `aiAgentDualControlAtRisk`,
`aiAgentMaxStepsPerRun`, `aiAgentMaxToolCallsPerRun`,
`aiAgentMaxRepeatsPerRequest`, `aiAgentMaxDurationSeconds`,
`aiAgentMaxContextTokens`, `aiAgentMaxInstructionsBytes`,
`aiAgentApprovalTtlSeconds`, `aiAgentRetentionDays`.

هیچ عددی در Call Site هاردکد نمی‌شود؛ `AgentSettings.fromDjangoSettings`
تنها محل خواندن است.

---

## 11. قرارداد نگه‌داری (§46)

فقط اجراهای تسویه‌شده (`COMPLETED`/`FAILED`/`CANCELLED`/`DENIED`) و
گام‌هایشان و تأییدهای **تصمیم‌گرفته** حذف می‌شوند. اجرای `PENDING` و
تأیید در انتظار تصمیم هرگز زیر نگه‌داری غیب نمی‌شوند.

---

## 12. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIAgentInvalid` | `AI_AGENT_INVALID` | 422 |
| `AIAgentNotFound` | `AI_AGENT_NOT_FOUND` | 404 |
| `AIAgentAlreadyRegistered` | `AI_AGENT_ALREADY_REGISTERED` | 409 |
| `AIAgentNotApproved` | `AI_AGENT_NOT_APPROVED` | 409 |
| `AIAgentDenied` | `AI_AGENT_DENIED` | 403 |
| `AIAgentPolicyInvalid` | `AI_AGENT_POLICY_INVALID` | 422 |
| `AIAgentApprovalRequired` | `AI_AGENT_APPROVAL_REQUIRED` | 202 |
| `AIAgentApprovalNotFound` | `AI_AGENT_APPROVAL_NOT_FOUND` | 404 |
| `AIAgentBudgetExceeded` | `AI_AGENT_BUDGET_EXCEEDED` | 429 |
| `AIAgentOutputInvalid` | `AI_AGENT_OUTPUT_INVALID` | 422 |
| `AIAgentExecutionFailed` | `AI_AGENT_EXECUTION_FAILED` | 502 |

خروجی‌های خارج از اسکیما با `AIAgentOutputInvalid` می‌افتند؛ شکست Model
با `AIAgentExecutionFailed` — هرگز Exception Vendor.

---

## 13. تصمیم‌های ثبت‌شده

- **Y-D1 — Agent یک entry رجیستری نسخه‌ای با چرخهٔ پنج‌حالتهٔ X است.**
  تغییر = نسخهٔ جدید؛ اجرا به نسخه قفل می‌شود.
- **Y-D2 — OQ #11 دو محوره:** سطح دسترسی (ساختاری، فهرست اثر) ×
  تأیید (نگاشت ریسک با نامتقارنی X).
- **Y-D3 — Agent هیچ Tool را مستقیم صدا نمی‌زند:** Planner فقط با پورت
  `AgentToolExecutor` حرف می‌زند؛ زنجیرهٔ X تنها مسیری است که وجود
  دارد. قاعدهٔ §30 برای Agent هم ساختاری شد.
- **Y-D4 — یک بودجه برای کل اجرا، بین مراحل مشترک** (بستن X-OQ #2)؛
  حلقه‌یابی روی اثر انگشت در کل اجرا، نه هر مرحله.
- **Y-D5 — Y هم‌زمان است و kind صف تازه نمی‌سازد** (بستن X-OQ #1 با
  خاتمهٔ صریح؛ اجرای ناهمگام Agent به Z/بعد واگذار شد).
- **Y-D6 — حافظه و دانش فقط از مسیر T/S می‌آیند که خودشان Fای
  fail-closed با K هستند؛ نبود Provider = Context خالی، نه Context باز.**
- **Y-D7 — هر اجرا یک ردیف می‌شود و هر گام (Model/Tool) — حتی رد شده —
  یک ردیف گام.** «Agent چه چیزی را امتحان کرد؟» باید پاسخ داشته باشد.
- **Y-D8 — اجرای در حال انجام به نسخهٔ شروع‌شده گره خورده است** (بستن
  X-OQ #5): registry در میانهٔ اجرا می‌تواند suspend/new version کند
  بدون اینکه قرارداد اجرا عوض شود.
- **Y-D9 — اعلان تأییدکننده و صف UI (X-OQ #3) در Z است؛** Y فقط ردیف
  تأیید و `listApprovals` می‌دهد.
- **Y-D10 — Model Boundary یک Port خالص است** با Reply فروزم؛
  `ScriptedAgentModelCaller` تست‌پرواییدر قطعی §41 برای Agent است.
- **Y-D11 — ابزارِ نیازمند تأیید انسانی در میانهٔ اجرا اجرا نمی‌شود؛**
  گام DENIED + دلیل در Context کار. واژگان فاز B حالت «در انتظار» برای
  اجرای Agent ندارد و افزودن حالت پنهانی ممنوع است.
- **Y-D12 — Agent با مجوزِ درخواست‌کننده عمل می‌کند، نه مجوز خودش.**
  Principal انسانِ شروع‌کننده به همهٔ فراخوانی‌های ابزار می‌رسد؛ Agent
  مجوز جدید تولید نمی‌کند (§A.4.3 / §29).
- **Y-D13 — پاک‌سازی راز ورودی/گام با همان `isSecretKey` فاز O/X است؛**
  یک تعریف، یک نقطهٔ اصلاح.

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. API عمومی Agent (ثبت/اجرا/تأیید/ردگیری) و Permission codeهای REST در Z؛
2. اجرای ناهمگام Agent با kind صف و اعلان نتیجه (Z/فاز ۲۰)؛
3. صف تأیید + اعلان به تأییدکننده از طریق فاز ۱۲ (Z)؛
4. Orchestration چند-Agent و بودجهٔ سلسله‌مراتبی (پس از Z)؛
5. نگاشت واقعی `modelPolicy` به Routing فاز E در آداپتور Model (Z).

---

## 15. Acceptance Criteria

- [ ] واژگان بستهٔ سطح دسترسی، اثرهای مجاز، وضعیت رجیستری و گام؛
- [ ] `AgentPolicy` با نگاشت ریسک→تأیید و نامتقارنی اعلام + بودجهٔ مؤثر؛
- [ ] اثر انگشت ورودی اجرا و پاک‌سازی راز با تعریف مشترک؛
- [ ] `AIAgentDefinition` با Invariant، چرخهٔ حیات، `allowsEffect` و پل به B؛
- [ ] `AIAgentApproval` با dual control (دو نفر متمایز) و منع تأیید خودی؛
- [ ] `AIAgentRun` با چرخهٔ حیاتِ دقیقاً فاز B و پل به `AIAgentExecution`؛
- [ ] `AIAgentStep` برای هر Model Call و Tool Call، حتی رد شده؛
- [ ] رجیستری با resolve روی آخرین نسخهٔ APPROVED؛
- [ ] Gatekeeper fail-closed برای draft، suspended، بدون مجوز،
      بدون تأیید، و قابلیتِ غیرفعال‌شده؛
- [ ] ساخت ردیف اجرا از تصمیم مجاز **و** ساخت گام Tool از بدون تصمیم مسدود
      ناممکن (پل‌های ساختاری)؛
- [ ] ابزارِ فراتر از سطح دسترسی هرگز به X نمی‌رسد (تست مستقیم)؛
- [ ] ADVISORY Agent با هر تأییدی ابزار اجرا نمی‌کند؛
- [ ] بودجهٔ مشترک: حلقه در مراحل مختلف تشخیص داده می‌شود؛
- [ ] سقف زمان با ساعت تزریقی؛ سقف توکن Context با `AIContextTooLarge`؛
- [ ] حافظه و دانش فقط از T/S با فیلتر K؛ نبود Provider ⇒ Context خالی؛
- [ ] خروجی Structured با `outputSchema` اعتبارسنجی؛ شکست ⇒ `FAILED`؛
- [ ] Agent با مجوزِ درخواست‌کننده اجرا می‌شود (تست با K واقعی)؛
- [ ] ایزولاسیون Tenant در چهار جدول؛
- [ ] سوئیچ fail-closed و نبود permission checker ⇒ امتناع؛
- [ ] چهار action حسابرسی (`AGENT_REGISTERED`، `AGENT_APPROVED`،
      `AGENT_INVOKED`، `AGENT_DENIED`) و زنجیرهٔ سالم؛
- [ ] نگه‌داری فقط روی ردیف‌های تسویه‌شده؛
- [ ] چهار جدول + مهاجرت `0012_agentPlatform` بدون drift؛
- [ ] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های Y تمیز؛
- [ ] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `… — Phase 13-Z may begin.` (پس از گزارش اجرا)
