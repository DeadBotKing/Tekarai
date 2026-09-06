# گزارش اجرا — Phase 13-T: AI Memory

**تاریخ:** 2026-09-05 · **وضعیت:** Memory Gate GREEN
**قرارداد:** [`Phase13-T.md`](Phase13-T.md) · **مجری:** Arena.ai Agent Mode
**Baseline:** درخت پس از تحویل S (سوییت ۱۴۱۲ تست)

---

## ۱. خلاصهٔ تحویل

هر پنج صفتی که §17 برای حافظهٔ AI الزامی کرده بود، به‌صورت مکانیزم واقعی
پیاده شد: **Tenant-aware** (هر مسیر tenant-scoped)، **User-aware** (اسلات
سراسری در برابر کاربر-محور)، **Permission-aware** (عبور اجباری از فیلتر
fail-closed زیر‌فاز K)، **Versioned** (نسخه‌ها ردیف‌اند و ویرایش نمی‌شوند)
و **Auditable** (چهار action در دفتر O + تاریخچهٔ کامل قابل خواندن).

و مهم‌تر: **Open Question شمارهٔ ۸ زیر‌فاز A بسته شد.** هر Scope سقف تعداد،
سقف حجم، عمر و استراتژی eviction دارد؛ پیکربندی فقط می‌تواند این‌ها را
تنگ‌تر کند. هیچ بخشی از حافظه بی‌کران نیست.

**۱۲۴ تست جدید سبز** (۵۵ واحد + ۴۳ کاربردی + ۲۶ یکپارچگی). کل سوییت از
۱۴۱۲ به **۱۵۳۶ تست** رسید با **همان ۶ شکست پیشین**. هر سه گیت کیفیت روی
فایل‌های T تمیز است و بدهی مخزن **صفر واحد** رشد کرد (۲۹۳ ruff و ۵۸۳ mypy،
عین عدد pristine).

## ۲. فایل‌های ایجادشده

### ۲.۱ کد (۷ فایل، ۱۹۷۴ خط)

| فایل | خط | نقش |
|---|---|---|
| `backend/apps/ai/domain/valueObjects/memoryTypes.py` | ۲۷۲ | واژگان، `MemoryKey`، `ScopeBudget`/`MemoryBudget` (بستن Open Question #8)، canonical/checksum/size |
| `backend/apps/ai/domain/entities/memoryRecords.py` | ۲۴۹ | `AIMemoryEntry` نسخه‌ای با مالکیت، انقضا، supersede، پروجکشن Context و پل به فاز B |
| `backend/apps/ai/domain/services/memoryEngine.py` | ۳۶۱ | `MemoryWriter`، `RetentionEvaluator`، `MemorySelector` |
| `backend/apps/ai/domain/memoryPorts.py` | ۸۲ | سه پورت باریک (store، فیلتر K، دفتر O) |
| `backend/apps/ai/application/services/memoryService.py` | ۷۲۳ | `MemorySettings`، `MemoryApplicationService`، `MemoryMaintenanceJobHandler` |
| `backend/apps/ai/infrastructure/repositories/memoryRepositories.py` | ۲۲۶ | `DjangoMemoryEntryStore` + سنتینل `ownerKey` |
| `backend/apps/ai/infrastructure/migrations/0007_memoryPlatform.py` | ۶۱ | جدول `aiMemoryEntries` |

### ۲.۲ تست (۳ فایل، ۱۲۷۱ خط، ۱۲۴ تست)

| فایل | تعداد | پوشش |
|---|---|---|
| `backend/tests/unit/testPhase13Memory.py` | ۵۵ | واژگان، کلید، ریاضی مقدار، بودجه‌ها، موجودیت، writer، retention، selector |
| `backend/tests/application/testPhase13MemoryUseCases.py` | ۴۳ | نوشتن/نسخه/تاریخچه، مالکیت، ایزولاسیون، سقف و TTL و eviction، فراموشی، Context با K واقعی، کار صف |
| `backend/tests/integration/testPhase13MemoryContract.py` | ۲۶ | قرارداد persistence: نسخه‌ها، مالکیت، یکتایی، حذف‌ها، sweep نگه‌داری |

### ۲.۳ فایل‌های تغییرکرده

| فایل | تغییر |
|---|---|
| `apps/ai/infrastructure/models.py` | مدل `AIMemoryEntryModel` (جدول تازه؛ `aiMemory` فاز B دست‌نخورده) |
| `apps/ai/domain/exceptions/aiExceptions.py` + `__init__.py` | ۵ خطای جدید T |
| `apps/ai/domain/valueObjects/auditTypes.py` | ۴ action جدید (۳۰ → ۳۴) |
| `apps/ai/domain/{entities,services,valueObjects}/__init__.py` | re-export ماژول‌های T |
| `apps/ai/infrastructure/repositories/__init__.py` | re-export store |
| `config/settings/base.py` + `.env.example` | بلوک `AI_MEMORY_*` (۹ کلید) |
| `tests/unit/testPhase13AuditGovernance.py` | شمارش واژگان O از ۳۰ به ۳۴ |
| `docs/Phases/Phase13/README.md` + `docs/Phases/Phase13.md` | وضعیت T |

## ۳. تصمیم‌های پیاده‌سازی (فراتر از قرارداد)

1. **سنتینل `ownerKey` — نقصی که تست یکپارچگی گرفت.** کلید یکتای اولیه
   شامل `userId` nullable بود؛ چون SQL دو `NULL` را برابر نمی‌داند، دو
   نسخهٔ تکراری از یک اسلات **سراسری Tenant** بی‌صدا مجاز می‌شد. ستون
   غیر-NULL `ownerKey` (`"tenant"` یا UUID) اضافه شد و کلید یکتا روی آن
   بنا شد — همان الگویی که زیر‌فاز P برای `idempotencyKey` خالی به کار
   برده بود. دو تست اختصاصی این رفتار را تثبیت می‌کنند.
2. **evict یعنی غیرفعال‌سازی، نه حذف.** ردیف برای حسابرسی می‌ماند و فقط
   purge افق نگه‌داری آن را فیزیکی حذف می‌کند.
3. **`OLDEST_FIRST` به‌جای LRU.** LRU نیازمند نوشتن در هر خواندن است؛ این
   هزینه آگاهانه رد شد و `LOWEST_PRIORITY` برای اعلام صریح اهمیت اضافه شد.
4. **پیکربندی فقط تنگ‌تر می‌کند.** `MemorySettings.budget()` پیش‌فرض‌های
   per-scope پلتفرم را با سقف پیکربندی‌شده تلاقی می‌دهد؛ یک تنظیم اشتباه
   نمی‌تواند سقف short-term را از long-term بازتر کند.
5. **شماره‌گذاری نسخه پس از فراموشی ادامه می‌یابد** (نه ریست) تا تاریخچه
   گمراه‌کننده نشود.
6. **پروجکشن Context در دامنه یک mapping ساده است**، نه `ContextSourceCandidate`؛
   ساخت شیء زیر‌فاز J در لایهٔ اپلیکیشن انجام می‌شود تا دامنه به موتور
   Context وابسته نشود.

## ۴. اثبات عمودی

- **نسخه‌بندی:** سه بار نوشتن ⇒ سه ردیف، دو تای اول `isActive=False` با
  `supersededAt`، مقدار قدیمی دست‌نخورده، `recall` آخرین را می‌دهد.
- **مالکیت:** حافظهٔ کاربر A برای کاربر B اصلاً وجود ندارد
  (`AI_MEMORY_NOT_FOUND`)، ولی حافظهٔ سراسری برای هر دو هست.
- **مجوز:** اصیل بدون grant با وجود دو حافظهٔ موجود، صفر بلوک Context
  می‌گیرد؛ با grant محدود به یک اسلات، فقط همان؛ حافظهٔ `RESTRICTED` هرگز.
- **سقف:** با `maxEntriesPerScope=3`، نوشتن چهارم قدیمی‌ترین را evict
  می‌کند، `MEMORY_EVICTED` در دفتر ثبت می‌شود و ردیف برای حسابرسی می‌ماند.
- **TTL:** حافظهٔ `SHORT_TERM` با TTL ۶۰ ثانیه پس از پنج دقیقه
  `AI_MEMORY_NOT_FOUND` می‌دهد و نوشتن بعدی خط نسخهٔ تازه می‌سازد.
- **ناهمگام:** `submitJob(kind="GENERIC")` → `runOnce()` → `SUCCEEDED` با
  خلاصهٔ scopes/expired/evicted/purged.

## ۵. گیت‌ها (اجرا شده)

| گیت | نتیجه |
|---|---|
| تست واحد T | ۵۵/۵۵ ✅ |
| تست کاربردی T | ۴۳/۴۳ ✅ |
| تست یکپارچگی T | ۲۶/۲۶ ✅ |
| سوییت کامل | **۱۵۳۶ تست، ۶ شکست پیشین** (بدون تغییر) |
| lint سطح T | ✅ All checks passed |
| format سطح T | ✅ formatted |
| type سطح T | ✅ صفر خطا در فایل‌های T |
| lint مخزن | ۲۹۳ = عدد pristine |
| type مخزن | ۵۸۳ = عدد pristine |
| مهاجرت `ai` | بدون drift |
| بررسی سیستم | تمیز (۰ issue) |

## ۶. بدهی پیشین (دست‌نخورده)

شش شکست معماری از `apps/ai/models.py` و `apps/ai/tests/test_provider.py`،
۲۹۳ ruff و ۵۸۳ mypy مخزن، و drift مهاجرت `communication`.

## ۷. راستی‌آزمایی معیارهای پذیرش

هر ۱۹ بند §۱۶ قرارداد با اجرای مستقیم تست تأیید شد.

## ۸. درخت بایگانی تحویل T

```text
backend/apps/ai/
├── domain/
│   ├── memoryPorts.py
│   ├── valueObjects/memoryTypes.py
│   ├── entities/memoryRecords.py
│   └── services/memoryEngine.py
├── application/services/memoryService.py
└── infrastructure/{models.py,migrations/0007_memoryPlatform.py,
    repositories/memoryRepositories.py}
backend/tests/{unit/testPhase13Memory.py,
  application/testPhase13MemoryUseCases.py,
  integration/testPhase13MemoryContract.py}
docs/Phases/Phase13/{Phase13-T.md,Phase13-T-ExecutionReport.md}
```

## ۹. زیر‌فاز بعدی

**Phase 13-U — Evaluation**: سنجش کیفیت خروجی AI. موجودیت `AIEvaluation`
و واژگان `EVALUATION_METHODS` از فاز B موجودند؛ U باید روش ارزیابی و
معیارهای قابل‌قبول (Open Question شمارهٔ ۹ زیر‌فاز A) را ببندد و به
بازیابی S و حافظهٔ T وصل شود.

**تحویل:** فایل `Tekarai-Phase13-T.zip` (checksum در فایل جانبی `.sha256`).
