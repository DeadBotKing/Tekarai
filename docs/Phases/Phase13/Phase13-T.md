# Phase 13-T — AI Memory

**فاز:** 13 — AI Platform & Intelligence Foundation
**زیر‌فاز:** T از A تا Z
**وضعیت:** COMPLETED — Memory Gate GREEN
**تاریخ قرارداد و اجرا:** 2026-09-05
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§16، §17، §20، §28، §37، §38، §40، §42، §43، §46، §47)
**قراردادهای قبلی:** [B](Phase13-B.md) (`AIMemory` و `MEMORY_SCOPES`)، [J](Phase13-J.md) (Context)،
[K](Phase13-K.md) (مجوز)، [O](Phase13-O.md) (حسابرسی)، [P](Phase13-P.md) (صف)،
[S](Phase13-S.md) (بازیابی)
**گزارش اجرا:** [`Phase13-T-ExecutionReport.md`](Phase13-T-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

سند مادر (§17) پنج صفت برای حافظهٔ AI الزامی می‌کند: **Tenant-aware،
User-aware، Permission-aware، Versioned، Auditable** — و یک خط قرمز:
«AI Memory نباید جایگزین Database اصلی Tekarai شود».

سؤال معماری T:

> **حافظه چطور می‌تواند مفید باشد بدون اینکه به یک پایگاه دادهٔ دوم و
> بی‌مرز تبدیل شود؟**

پاسخ T دو بخش دارد:

1. **هیچ چیز بی‌کران نیست.** هر Scope سقف تعداد، سقف حجم مقدار، عمر
   (TTL) و استراتژی eviction دارد. این دقیقاً **Open Question شمارهٔ ۸**
   زیر‌فاز A است که در T بسته می‌شود.
2. **حافظه فقط از مسیر مجاز وارد Prompt می‌شود.** `buildContextSources`
   حافظه را از فیلتر fail-closed زیر‌فاز K عبور می‌دهد — همان مسیری که
   دانش از آن می‌گذرد. بدون فیلتر، هیچ حافظه‌ای در دسترس نیست.

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

1. واژگان بستهٔ نوع حافظه، استراتژی eviction و verdict نگه‌داری؛
2. `MemoryKey` (آدرس نرمال‌شده)، `ScopeBudget` و `MemoryBudget`؛
3. هویت قطعی مقدار: canonical کردن، checksum و اندازه‌گیری بایت؛
4. موجودیت نسخه‌ای `AIMemoryEntry` با مالکیت، انقضا، supersession و پل به B؛
5. `MemoryWriter` (CREATED / UNCHANGED / VERSIONED)؛
6. `RetentionEvaluator` (انقضا + دو استراتژی eviction + حالت غیرفعال)؛
7. `MemorySelector` (اولویت Scope، آخرین نسخه، مالکیت، بودجهٔ توکن)؛
8. سرویس اپلیکیشن: remember، recall، history، list، forget، retention، purge؛
9. مشارکت در Context از طریق فیلتر K؛
10. جدول `aiMemoryEntries` و مهاجرت `0007`؛
11. پیکربندی `AI_MEMORY_*` و handler نگه‌داری برای صف P؛
12. سه سطح تست.

### 2.2 خارج از Scope

- **خلاصه‌سازی خودکار گفت‌وگو** (تولید حافظه با مدل) — زیر‌فاز U/Y؛
- **Embedding حافظه و جست‌وجوی معنایی روی آن** — با Q/S ممکن است ولی در
  T فعال نشده (تصمیم T-D6)؛
- **رابط کاربری فراموشی و درخواست حذف داده** — زیر‌فاز Z؛
- **حافظهٔ Agent در حین اجرای چندمرحله‌ای** — زیر‌فاز Y از همین API
  استفاده می‌کند؛
- **API عمومی و permission codeها** — زیر‌فاز Z.

---

## 3. جایگاه معماری

```text
Application (MemoryApplicationService، MemoryMaintenanceJobHandler)
   │  ├─ MemoryEntryStore       → aiMemoryEntries
   │  ├─ MemoryPermissionFilter → Phase 13-K (fail-closed)
   │  └─ MemoryAuditLogger      → Phase 13-O
   ↓
Domain (MemoryWriter، RetentionEvaluator، MemorySelector، AIMemoryEntry)
   ← خالص، بدون جنگو
```

---

## 4. قرارداد موجودیت (§T.4)

| فیلد | قاعده |
|---|---|
| کلید طبیعی | `(tenantId, scope, memoryKey, ownerKey, version)` — یکتا در دیتابیس |
| `memoryKey` | آدرس نرمال‌شده: حروف کوچک، بدون فاصله، الگوی `[a-z0-9._:-]` |
| `value` | JSON-safe؛ canonical و کلید-مرتب می‌شود |
| `checksum` | SHA-256 مقدار canonical — کلید idempotency نوشتن |
| `sizeBytes` | اندازهٔ مقدار canonical، مبنای سقف حجم |
| `version` | صعودی و **تغییرناپذیر**؛ نوشتن جدید = نسخهٔ جدید |
| `userId` | مالک اختیاری؛ `NULL` یعنی سراسری Tenant |
| `ownerKey` | فرافکن غیر-NULL از `userId` (`"tenant"` یا UUID) — چون در SQL دو `NULL` برابر نیستند و بدون آن، نسخهٔ تکراری یک اسلات سراسری بی‌صدا مجاز می‌شد |
| `classification` | مبنای تصمیم فیلتر K |
| `expiresAt` | از TTL همان Scope، مگر اینکه فراخوان صریح بدهد |

---

## 5. قرارداد نوشتن (§T.5)

| Verdict | شرط |
|---|---|
| `CREATED` | اسلات خالی است، یا نسخهٔ قبلی منقضی/غیرفعال شده |
| `UNCHANGED` | همان مقدار و همان طبقه‌بندی — هیچ نوشتنی رخ نمی‌دهد |
| `VERSIONED` | مقدار یا طبقه‌بندی عوض شده، یا `force=True` |

نسخهٔ قبلی **ویرایش نمی‌شود**: `supersededAt` می‌خورد و غیرفعال می‌شود.
تاریخچه با `history()` قابل خواندن است — این همان «Auditable» بند §17 است.

---

## 6. قرارداد سقف و نگه‌داری (Open Question #8)

پیش‌فرض‌های پلتفرم به‌ازای Scope:

| Scope | maxEntries | TTL | maxValueBytes |
|---|---|---|---|
| `SHORT_TERM` | ۵۰ | ۱ روز | ۸ KB |
| `CONVERSATION` | ۱۰۰ | ۳۰ روز | ۱۶ KB |
| `TASK` | ۲۰۰ | ۹۰ روز | ۱۶ KB |
| `AGENT` | ۲۰۰ | ۹۰ روز | ۳۲ KB |
| `LONG_TERM` | ۵۰۰ | بدون انقضا | ۳۲ KB |

قواعد:

- پیکربندی فقط می‌تواند این پیش‌فرض‌ها را **تنگ‌تر** کند، نه بازتر؛
- مقدار بزرگ‌تر از سقف ⇒ `AI_MEMORY_VALUE_TOO_LARGE` (بدون truncate)؛
- سرریز تعداد ⇒ eviction با `OLDEST_FIRST` (پیش‌فرض) یا `LOWEST_PRIORITY`؛
- `NONE` یعنی «به‌جای حذف، خطا بده» (`AI_MEMORY_BUDGET_EXCEEDED`)؛
- ردیف evict شده **پاک نمی‌شود**، غیرفعال می‌شود تا حسابرسی بماند؛
- `purgeMemoryRetention` فقط نسخه‌های بازنشسته را بعد از افق نگه‌داری
  حذف می‌کند؛ یک حافظهٔ زنده هرگز خاموش نمی‌رود.

---

## 7. قرارداد خواندن

- `recall` آخرین نسخهٔ **قابل استفاده** (فعال، بدون supersede، منقضی‌نشده)
  را برمی‌گرداند وگرنه `AI_MEMORY_NOT_FOUND`؛
- `history` همهٔ نسخه‌ها را از قدیم به جدید می‌دهد؛
- `listMemories` با فیلتر Scope/گفت‌وگو/مالک.

---

## 8. قرارداد مالکیت (§T.8)

| ردیف | چه کسی می‌بیند |
|---|---|
| `userId = NULL` (سراسری Tenant) | همهٔ اصیل‌های همان Tenant |
| `userId = X` | فقط X |

جست‌وجوی بدون مالک عمداً **فقط** ردیف‌های سراسری را می‌بیند؛ جست‌وجو با
مالک، ردیف‌های او به‌علاوهٔ سراسری‌ها را. دو کاربر می‌توانند زیر یک کلید،
اسلات‌های کاملاً مستقل داشته باشند.

---

## 9. قرارداد مشارکت در Context (§20، §T.9)

1. انتخاب: فقط نسخهٔ آخر هر کلید، مرتب بر اساس اولویت Scope
   (`INSTRUCTION → AGENT → TASK → CONVERSATION → SHORT_TERM → LONG_TERM`)
   و سپس تازگی؛
2. بودجه: سقف تعداد و سقف توکن؛
3. **فیلتر K روی همان `ContextSourceCandidate`‌هایی که دانش از آن‌ها
   می‌گذرد** — حافظه در Prompt در نوع خودش استثنا نیست؛
4. بدون فیلتر ⇒ `AIConfigurationError` (fail-closed)؛
5. حسابرسی `MEMORY_RECALLED` با شمارش مجاز/ردشده.

---

## 10. قرارداد فراموشی (§46)

- `forget()` نرم: همهٔ نسخه‌های فعال بازنشسته می‌شوند، ردیف‌ها می‌مانند؛
- `forget(hard=True)`: کل تاریخچهٔ آن اسلات حذف می‌شود (حق فراموش‌شدن)؛
- هر دو حالت مالک-محدودند و حسابرسی `MEMORY_FORGOTTEN` می‌گیرند؛
- نوشتن دوباره پس از فراموشی، نسخهٔ بعدی را می‌سازد (شماره‌گذاری ادامه
  می‌یابد، تا تاریخچه گمراه‌کننده نشود).

---

## 11. قرارداد پیکربندی (§42)

`aiMemoryEnabled`, `aiMemoryMaxEntriesPerScope`, `aiMemoryDefaultTtlSeconds`,
`aiMemoryMaxValueBytes`, `aiMemoryEviction`, `aiMemoryContextMaxEntries`,
`aiMemoryContextMaxTokens`, `aiMemoryRetentionDays`,
`aiMemoryUseScopeDefaults`.

---

## 12. قرارداد نگه‌داری ناهمگام

`MemoryMaintenanceJobHandler` روی kind `GENERIC` صف P: اعمال بودجهٔ
Scopeها و (اختیاری) purge افق نگه‌داری. هر دو گام idempotent‌اند.

---

## 13. خطاها (§43)

| خطا | کد پایدار | HTTP |
|---|---|---|
| `AIMemoryInvalid` | `AI_MEMORY_INVALID` | 422 |
| `AIMemoryNotFound` | `AI_MEMORY_NOT_FOUND` | 404 |
| `AIMemoryValueTooLarge` | `AI_MEMORY_VALUE_TOO_LARGE` | 422 |
| `AIMemoryBudgetExceeded` | `AI_MEMORY_BUDGET_EXCEEDED` | 409 |
| `AIMemoryPolicyInvalid` | `AI_MEMORY_POLICY_INVALID` | 422 |

---

## 14. تصمیم‌های ثبت‌شده

- **T-D1 — نسخه‌ها ردیف‌اند، نه ویرایش.** تاریخچه بخشی از قرارداد است.
- **T-D2 — بستن Open Question #8 با بودجهٔ per-scope.** هیچ Scope بدون
  سقف نیست و پیکربندی فقط تنگ‌تر می‌کند.
- **T-D3 — سنتینل `ownerKey`.** ستون nullable در کلید یکتا روی SQL
  کار نمی‌کند؛ همان الگوی `none:<jobId>` زیر‌فاز P تکرار شد.
- **T-D4 — eviction بر پایهٔ `createdAt`، نه LRU.** LRU نیازمند نوشتن در
  هر خواندن است؛ این هزینه آگاهانه رد شد. `LOWEST_PRIORITY` برای
  کاربردهایی که اهمیت را صریح اعلام می‌کنند در دسترس است.
- **T-D5 — جدول تازه به‌جای بازنویسی `aiMemory` فاز B.** جدول قدیمی
  نسخه‌بندی، checksum، اندازه و طبقه‌بندی ندارد و تغییر درجای آن ردیف‌های
  موجود را می‌شکست؛ پل موجودیتی به B حفظ شد.
- **T-D6 — حافظه در T بردار نمی‌شود.** جست‌وجوی معنایی روی حافظه با
  Q/S ممکن است ولی تا نیازِ ثابت‌شده اضافه نمی‌شود (YAGNI آگاهانه).
- **T-D7 — evict یعنی غیرفعال، نه حذف.** حذف فیزیکی فقط با purge افق
  نگه‌داری یا `forget(hard=True)`.

---

## 15. Open Questions برای زیر‌فازهای بعدی

1. خلاصه‌سازی خودکار حافظهٔ گفت‌وگو و معیار کیفیتش (U/Y)؛
2. آیا حافظهٔ بلندمدت باید embedding و جست‌وجوی معنایی داشته باشد (S/W)؛
3. سیاست تعارض: وقتی کاربر و Agent هم‌زمان یک اسلات را می‌نویسند (Y)؛
4. سهمیهٔ حافظه به‌ازای کاربر (نه فقط Scope) و هزینهٔ آن (N/Z)؛
5. صادرات/واردات حافظه هنگام انتقال Tenant (Z).

---

## 16. Acceptance Criteria

- [x] واژگان بسته و اعتبارسنجی کامل بودجه‌ها؛
- [x] کلید نرمال‌شده و هویت قطعی مقدار (canonical + checksum + size)؛
- [x] موجودیت نسخه‌ای با مالکیت، انقضا، supersede و پل به فاز B؛
- [x] سه verdict نوشتن، شامل no-op واقعی؛
- [x] TTL هر Scope و شروع خط نسخهٔ جدید پس از انقضا؛
- [x] سقف تعداد با دو استراتژی eviction و حالت «خطا بده»؛
- [x] evict و forget ردیف را برای حسابرسی نگه می‌دارند؛
- [x] purge فقط نسخه‌های بازنشسته را حذف می‌کند؛
- [x] مالکیت: سراسری در برابر کاربر-محور، در خواندن و حذف؛
- [x] ایزولاسیون Tenant در همهٔ مسیرها؛
- [x] انتخاب Context با اولویت Scope، آخرین نسخه و بودجهٔ توکن؛
- [x] عبور اجباری حافظه از فیلتر K و fail-closed بودن نبود فیلتر؛
- [x] چهار action حسابرسی و زنجیرهٔ سالم؛
- [x] یکتایی نسخه در سطح دیتابیس، حتی برای اسلات سراسری؛
- [x] جدول + مهاجرت `0007_memoryPlatform` بدون drift؛
- [x] نُه کلید پیکربندی و handler نگه‌داری صف؛
- [x] ۱۲۴ تست جدید سبز؛
- [x] `ruff`/`ruff format`/`mypy` روی همهٔ فایل‌های T تمیز؛
- [x] بدون وابستگی جدید و بدون Secret.

**نتیجهٔ Gate:** `GREEN — Phase 13-U may begin.`
