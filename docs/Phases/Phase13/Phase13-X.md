# Phase 13-X — Tool Registry و Tool Execution

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** X از A تا Z
**وضعیت:** COMPLETED — Tool Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§28، §30، §38، §40، §42، §43، §46، §47)
**قراردادهای قبلی:** [B](Phase13-B.md) (`AITool`/`AIToolExecution`)، [H](Phase13-H.md) (JSON Schema)،
[K](Phase13-K.md) (مجوز)، [O](Phase13-O.md) (حسابرسی و `isSecretKey`)، [W](Phase13-W.md) (رصد)
**گزارش اجرا:** [`Phase13-X-ExecutionReport.md`](Phase13-X-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

§30 زنجیره را می‌کشد و بعد یک جملهٔ کوتاه می‌گوید که کل زیر‌فاز از آن
می‌آید:

```text
AI → Tool Registry → Permission Check → Tool Execution → Result → AI
```

> **AI نباید Tool را مستقیم اجرا کند.**

سؤال معماری X:

> **چطور کاری کنیم که «مدل ابزار را مستقیم اجرا نکند» یک قاعدهٔ نوشتاری
> نباشد، بلکه چیزی باشد که *نمی‌شود* نقضش کرد؟**

پاسخ X: مدل فقط `ToolProposal` تولید می‌کند و runner فقط `ExecutionTicket`
می‌پذیرد. تنها راه ساخت Ticket، تابع `prepareExecution` است که یک
`GateDecision` **مجاز** می‌خواهد — و آن هم فقط از عبور از رجیستری، بررسی
مجوز K و (در ریسک بالا) تأیید انسانی به دست می‌آید. مسیر میان‌بری از
پیشنهاد خام به اجرا **وجود ندارد**.

سؤال دوم، **Open Question شمارهٔ ۱۰**: رجیستری و گردش‌کار تأیید ابزار
چیست؟ پاسخ در §5 و §7.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ اثر، ریسک، حالت تأیید و وضعیت رجیستری؛
2. `ToolPolicy` که ریسک را به تأیید نگاشت می‌کند (بستن OQ #10)؛
3. اثر انگشت آرگومان و پاک‌سازی راز با تعریف مشترک پلتفرم؛
4. سه موجودیت: تعریف نسخه‌ای، تأیید انسانی، فراخوانی — با پل به فاز B؛
5. `ToolRegistry`، `ArgumentValidator`، `ToolGatekeeper`، `ExecutionBudget`؛
6. `ExecutionTicket` به‌عنوان تنها ورودی runner؛
7. سرویس اپلیکیشن: چرخهٔ رجیستری، اجرا، گردش‌کار تأیید، خواندن، نگه‌داری؛
8. سه جدول و مهاجرت `0011`؛
9. پیکربندی `AI_TOOL_*`؛
10. سه سطح تست، شامل زنجیرهٔ §30 با موتور مجوز واقعی K.

### 2.2 خارج از Scope

- **ارکستراسیون چندمرحله‌ای ابزارها** — زیر‌فاز Y (Agent)؛
- **اجرای ناهمگام ابزار** — X هم‌زمان است؛ Y در صورت نیاز kind صف اضافه
  می‌کند (تصمیم X-D7)؛
- **پیاده‌سازی ابزارهای واقعی** (`searchProject`، `sendNotification`) —
  دامنه‌های مالک؛ X فقط قرارداد و مسیر اجراست؛
- **UI صف تأیید** — فاز ۱۸؛
- **API عمومی** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (ToolApplicationService، CallableToolRunner)
   │  ├─ ToolDefinitionStore / ApprovalStore / InvocationStore
   │  ├─ ToolPermissionChecker → Phase 13-K
   │  ├─ ToolRunner            → آداپتور دامنهٔ مالک
   │  └─ ToolAuditLogger       → Phase 13-O
   ↓
Domain (ToolRegistry، ArgumentValidator، ToolGatekeeper،
        ExecutionBudget، ExecutionTicket)      ← خالص، بدون جنگو
```

---

## 4. قرارداد تعریف ابزار

| فیلد | نقش |
|---|---|
| `code` + `version` | کلید طبیعی؛ نسخه‌ها **تغییرناپذیر**اند |
| `effect` | `READ_ONLY` / `MUTATING` / `EXTERNAL` / `NOTIFYING` |
| `riskLevel` | `LOW` … `CRITICAL` — محرک تأیید |
| `inputSchema`/`outputSchema` | زیرمجموعهٔ JSON Schema فاز H |
| `requiredPermission` | کد مجوز K (پیش‌فرض `AI_TOOL_EXECUTE`) |
| `declaredApprovalMode` | فقط می‌تواند **سخت‌گیرانه‌تر** از سیاست باشد |
| `timeoutSeconds`/`maxCallsPerRequest` | سقف‌های اجرایی |

تغییر اسکیما یعنی **نسخهٔ جدید**، پس فراخوانی ثبت‌شده در ماه گذشته هنوز با
همان قراردادی خوانده می‌شود که واقعاً استفاده کرده بود.

---

## 5. قرارداد رجیستری (نیمهٔ اول OQ #10)

`DRAFT → PENDING_APPROVAL → APPROVED → SUSPENDED ⇄ APPROVED → RETIRED`

- ابزار در `DRAFT` متولد می‌شود و **هرگز** مستقیم اجرا نمی‌شود؛
- رد کردن دلیل اجباری دارد و به `DRAFT` برمی‌گرداند؛
- `RETIRED` پایانی است؛
- `resolve` بدون نسخه، **آخرین نسخهٔ APPROVED** را می‌دهد، نه آخرین نسخه —
  وگرنه یک draft با صرف وجود داشتن قابل فراخوانی می‌شد.

---

## 6. قرارداد سیاست ریسک/تأیید

| ریسک | حالت پیش‌فرض | تعداد تأییدکننده |
|---|---|---|
| LOW / MEDIUM | `AUTOMATIC` | ۰ |
| HIGH | `HUMAN_REQUIRED` | ۱ |
| CRITICAL | `DUAL_CONTROL` | ۲ (دو نفر متمایز) |

قاعدهٔ نامتقارن: ابزار می‌تواند حالت **سخت‌گیرانه‌تر** اعلام کند، هرگز
بازتر. یک ورودی رجیستری نمی‌تواند خودش را از بازبینی انسانی معاف کند.
`DISABLED` همیشه برنده است.

---

## 7. قرارداد گردش‌کار تأیید (نیمهٔ دوم OQ #10)

- تأیید به **اثر انگشت آرگومان‌ها** گره خورده است: تأیید برای
  `{"projectId":"P-1"}` مجوز `{"projectId":"P-2"}` نیست؛
- `DUAL_CONTROL` دو نفر **متمایز** می‌خواهد؛ یک نفر دو بار رد می‌شود؛
- **درخواست‌کننده نمی‌تواند تأیید خودش را بدهد**؛
- تأیید TTL دارد؛ منقضی که شد، دوباره باید پرسید؛
- **رد کردن تا پایان همان پنجره می‌چسبد** (تصمیم X-D6): وگرنه یک Agent
  در حلقه، بازبینی انسانی را به اسپم تبدیل می‌کرد.

---

## 8. قرارداد اجرا

1. رجیستری resolve می‌کند؛
2. آرگومان‌ها **قبل از هر نوشتنی** با اسکیما و سقف حجم اعتبارسنجی می‌شوند؛
3. بودجهٔ درخواست و تشخیص حلقه اعمال می‌شود؛
4. ردیف فراخوانی با آرگومان‌های **پاک‌سازی‌شده** ثبت می‌شود؛
5. مجوز K و وضعیت تأیید بررسی می‌شود؛
6. فقط در صورت `allowed`، Ticket ساخته و به runner داده می‌شود؛
7. خروجی با `outputSchema` اعتبارسنجی می‌شود؛
8. موفقیت/شکست/رد — همه ثبت و حسابرسی می‌شوند.

**هر پیشنهاد یک ردیف می‌شود، حتی وقتی جواب «نه» است.** «Agent چه چیزی را
امتحان کرد؟» باید پاسخ داشته باشد.

---

## 9. قرارداد بودجه و حلقه

سقف فراخوانی در یک درخواست = کمینهٔ سقف سیاست و سقف خود ابزار. تکرار
اثر انگشت یکسان بیش از `maxRepeatsPerRequest` یعنی حلقه و رد می‌شود —
بدون نیاز به تایمر.

---

## 10. قرارداد پیکربندی (§42)

`aiToolEnabled`, `aiToolAutomaticBelowRisk`, `aiToolDualControlAtRisk`,
`aiToolMaxCallsPerRequest`, `aiToolMaxRepeatsPerRequest`,
`aiToolTimeoutSeconds`, `aiToolMaxArgumentBytes`,
`aiToolApprovalTtlSeconds`, `aiToolRetentionDays`.

---

## 11. قرارداد نگه‌داری (§46)

فقط فراخوانی‌های تسویه‌شده (`SUCCEEDED`/`FAILED`/`DENIED`/`CANCELLED`)
حذف می‌شوند. فراخوانی‌ای که منتظر تصمیم انسان است هرگز زیر نگه‌داری غیب
نمی‌شود.

---

## 12. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIToolInvalid` | `AI_TOOL_INVALID` | 422 |
| `AIToolNotFound` | `AI_TOOL_NOT_FOUND` | 404 |
| `AIToolAlreadyRegistered` | `AI_TOOL_ALREADY_REGISTERED` | 409 |
| `AIToolNotApproved` | `AI_TOOL_NOT_APPROVED` | 409 |
| `AIToolDenied` (فاز B) | `AI_TOOL_DENIED` | 403 |
| `AIToolArgumentsInvalid` | `AI_TOOL_ARGUMENTS_INVALID` | 422 |
| `AIToolOutputInvalid` | `AI_TOOL_OUTPUT_INVALID` | 422 |
| `AIToolBudgetExceeded` | `AI_TOOL_BUDGET_EXCEEDED` | 429 |
| `AIToolApprovalRequired` | `AI_TOOL_APPROVAL_REQUIRED` | 202 |
| `AIToolApprovalNotFound` | `AI_TOOL_APPROVAL_NOT_FOUND` | 404 |
| `AIToolExecutionFailed` | `AI_TOOL_EXECUTION_FAILED` | 502 |

---

## 13. تصمیم‌های ثبت‌شده

- **X-D1 — Ticket تنها ورودی runner است.** قاعدهٔ §30 ساختاری شد، نه
  توصیه‌ای.
- **X-D2 — نسخه‌ها تغییرناپذیرند؛ تغییر اسکیما = نسخهٔ جدید.**
- **X-D3 — resolve پیش‌فرض روی آخرین نسخهٔ APPROVED.**
- **X-D4 — اعلام سخت‌گیرانه‌تر مجاز، بازتر ممنوع.**
- **X-D5 — تأیید به اثر انگشت آرگومان گره خورده است.**
- **X-D6 — رد کردن تا پایان پنجره‌اش می‌چسبد** (ضد اسپم بازبینی).
- **X-D7 — بدون kind صف تازه.** اجرای ابزار در X هم‌زمان است؛ اجرای
  ناهمگام و چندمرحله‌ای کار Y است.
- **X-D8 — پاک‌سازی راز به `isSecretKey` فاز O واگذار شد** به‌جای تعریف
  دوم؛ یک تعریف، یک نقطهٔ اصلاح.
- **X-D9 — runner فقط آرگومان‌های اعتبارسنجی‌شده را می‌بیند**، نه principal
  و نه پیشنهاد خام؛ پیاده‌سازی ابزار نمی‌تواند اختیار خودش را گسترش دهد.

---

## 14. Open Questions برای زیر‌فازهای بعدی

1. اجرای ناهمگام ابزار و kind صف اختصاصی (Y)؛
2. زنجیرهٔ ابزار در یک Agent و بودجهٔ مشترک بین مراحل (Y)؛
3. صف تأیید و اعلان به تأییدکننده از طریق فاز ۱۲ (Y/Z)؛
4. sandbox اجرای ابزار خارجی و مرز شبکه (Z/فاز ۲۰)؛
5. نسخه‌بندی معنایی ابزار و سازگاری عقب‌رو برای Agentهای در حال اجرا (Y).

---

## 15. Acceptance Criteria

- [x] واژگان بستهٔ اثر، ریسک، حالت تأیید و وضعیت؛
- [x] `ToolPolicy` با نگاشت ریسک→تأیید و قاعدهٔ نامتقارن اعلام؛
- [x] اثر انگشت آرگومان و پاک‌سازی راز با تعریف مشترک؛
- [x] سه موجودیت با Invariant، چرخهٔ حیات و پل به فاز B؛
- [x] رجیستری با resolve روی آخرین نسخهٔ APPROVED؛
- [x] اعتبارسنجی آرگومان و خروجی با اسکیمای فاز H؛
- [x] gatekeeper fail-closed برای draft، suspended، بدون مجوز و بدون تأیید؛
- [x] **ساخت Ticket از تصمیم مسدود ناممکن**؛
- [x] بودجهٔ درخواست و تشخیص حلقه؛
- [x] تأیید تک‌نفره و dual control با دو نفر متمایز؛
- [x] منع تأیید توسط درخواست‌کننده؛
- [x] انقضای تأیید و چسبندگی رد؛
- [x] ثبت هر پیشنهاد، حتی رد شده؛
- [x] پاک‌سازی راز پیش از ذخیره، تأییدشده روی ردیف دیتابیس؛
- [x] ایزولاسیون Tenant در رجیستری، تأیید و فراخوانی؛
- [x] سوئیچ fail-closed و نبود permission checker ⇒ امتناع؛
- [x] چهار action حسابرسی و زنجیرهٔ سالم؛
- [x] نگه‌داری فقط روی فراخوانی‌های تسویه‌شده؛
- [x] سه جدول + مهاجرت `0011_toolPlatform` بدون drift؛
- [x] ۱۵۴ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های X تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-Y may begin.`
