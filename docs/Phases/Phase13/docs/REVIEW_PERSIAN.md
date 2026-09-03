# بررسی کامل مستندات پوشهٔ `docs/` — پروژهٔ Tekarai

> تاریخ بررسی: ۲۰۲۶-۰۸-۳۰
> روش: کلون کامل مخزن `github.com/DeadBotKing/Tekarai`، خواندن هر ۱۳۵ فایل داخل `docs/`
> (شامل پوشه‌های `adr/`, `architecture/`, `api/`, `database/`, `development/`,
> `operations/`, `Phases/`, `Phase 1-3/` تاریخی و فایل‌های ریشه).

---

## ۱. پروژه در یک نگاه

| مورد | مقدار |
|---|---|
| نام محصول | **Tekarai** (ری‌برند شده از نام قدیمی **Meryx**) |
| نوع | Enterprise Operations Platform عمومی، چند-مستأجری (Multi-Tenant)، قابل فروش |
| مشتری مرجع | کارخانهٔ داروسازی «Ronak» — فقط مرجع، نه مرز محصول |
| سبک معماری | Modular Monolith + DDD + Clean Architecture + SOLID + Event-Driven |
| Backend | Python 3.12 · Django 6.1 · DRF 3.18 · SQL Server (mssql-django/pyodbc) · SimpleJWT (در عمل JWT داخلی HS256) |
| Real-time | Django Channels 4.3 + Daphne 4.2 + channels-redis 4.3 · WebRTC/SFU برای media |
| Async | پورت صف (InlineNotificationQueue فعلی؛ Celery/RQ بعداً) |
| هدف | پلتفرمی که ۵–۱۰ سال بدون بازنویسی معماری دوام بیاورد |

**شعار مستندات:** هدف فقط «اجرا شدن» نیست؛ هدف «ساختن پلتفرمِ درست» است.

---

## ۲. ساختار پوشهٔ docs (۱۳۵ فایل)

```
docs/
├── ۷ سند ریشه‌ای (هستهٔ handoff) + ANALYSIS.md + Handoff.md
├── adr/                  ۲۵ سند تصمیم معماری (ADR-001 … ADR-024 + README)
├── architecture/         ۲۲ سند معماری مرجع (فاز ۲ و فاز ۳)
├── api/                  ۴ سند (APIArchitecture، COMMUNICATION_API، NOTIFICATION_API)
├── database/             ۲۳ سند + ۱ ابزار پایتون (ERD، دیکشنری ۱۹۵ موجودیت، قواعد، …)
├── Phases/               ۲۰ فاز + ۴ manifest/report (فاز ۸ و ۹)
├── Phase 1|2|3/          آرشیو تاریخیِ «بیلد گم‌شده» (commit 29621f6 که هرگز push نشد)
├── development/          ۷ گزارش اجرای فاز ۱–۷ + راهنمای Running & Testing
├── operations/           دو Runbook (فاز ۸ و ۹)
└── deployment|domain|product|security/   فقط README placeholder (محتوا در فازهای بعدی)
```

### نکتهٔ مهم: فایل‌های دوتایی (Duplicates)
ریشهٔ docs دو دسته فایل با محتوای تقریباً یکسان دارد:

| نسخهٔ UPPER_SNAKE (قدیمی، نام Meryx) | نسخهٔ PascalCase (جدید، نام Tekarai) |
|---|---|
| `MERYX_MASTER_IMPLEMENTATION_SPECIFICATION.md` | `TekaraiMasterImplementationSpecification.md` |
| `ARCHITECTURE_HANDOFF.md` | `ArchitectureHandoff.md` |
| `DATA_FLOW_DOCUMENTATION.md` | `DataFlowDocumentation.md` |
| `DEVELOPMENT_RULES.md` | `DevelopmentRules.md` |
| `EXECUTION_GUIDE.md` | `ExecutionGuide.md` |

تفاوت‌ها فقط در نام محصول (Meryx ← Tekarai) و نام فایل‌های ارجاعی است. نسخهٔ PascalCase
مرجع است (طبق ترتیب خواندن `README.md`). نسخهٔ UPPER باقیماندهٔ ری‌برند ناقص است و
باید حذف یا آرشیو شود.

---

## ۳. سلسله‌مراتب منبع حقیقت (Source of Truth)

```
ADRهای تأییدشده  →  MasterImplementationSpec  →  ArchitectureHandoff /
DataFlow / DevelopmentRules  →  ExecutionGuide  →  کد
```

اگر کد با اسپک در تضاد باشد، **کد غلط است** مگر آنکه ADR جدید رسماً جایگزین کند.

ترتیب خواندن اجباری: Master Spec ← Architecture Handoff ← Data Flow ←
Development Rules ← Execution Guide ← Handoff.

---

## ۴. خلاصهٔ محتوای اسناد اصلی

### ۴-۱. هستهٔ Handoff (ریشه)
- **MasterImplementationSpec (۶۸۶ خط، ۳۴ بخش):** قرارداد اصلی بازسازی. ۲۰ قانون
  غیرقابل‌مذاکره، ۱۷ دامنه، نقشهٔ ریپو، بِیس‌لاین تکنولوژی، ۴ لایهٔ معماری
  (Presentation → Application → Domain ← Infrastructure)، قواعد دیتابیس/API/
  Event/Security/Testing، ترتیب پیاده‌سازی ۰–۲۳ و Definition of Done.
- **ArchitectureHandoff (۴۰۳ خط):** ۱۹ بخش — سبک معماری، جهت وابستگی، مرز
  دامنه‌ها، Invariantها، استراتژی اسکیل (اول Monolith بعد Microservice)،
  استراتژی Extension (Industry Pack/Plugin)، پروتکل Resume.
- **DataFlowDocumentation (۴۰۷ خط):** ۲۰ جریان استاندارد — Command، Query،
  Authentication، Authorization (شش لایه)، Tenant، Project→Task، Document→Workflow،
  Chat، Voice/Video، Notification، AI، RAG (فیلتر دسترسی قبل از رفتن به مدل)،
  Integration، Audit، Failure، Transaction، Idempotency، Lifecycle، Read Models.
- **DevelopmentRules (۲۹۴ خط):** ۲۰ قانون اجباری — بدون حدس (Open Question)،
  قواعد Django/Model/Service/Repository/API/DB/Migration/Testing/Security/Git،
  ممنوعیت‌ها (TODO، pass، NotImplementedError، Fake)، قانون نهایی:
  «معماری را اول حفظ کن، بعد یکپارچگی داده، بعد امنیت، آخر راحتی توسعه‌دهنده».
- **ExecutionGuide (۴۵۸ خط):** راهنمای اجرای ۲۶ فاز (۰ تا ۲۵) با دستورات
  PowerShell/Linux — از ساخت ریپو تا استقرار و تأیید نهایی.
- **ANALYSIS.md (۳۱۶ خط، فارسی):** تحلیل پیشین مستندات — ارزشمند اما **قدیمی**
  (پایین‌تر توضیح داده می‌شود).

### ۴-۲. ADRها (adr/) — ۲۴ تصمیم معماری
| گروه | ADRها | تصمیم کلیدی |
|---|---|---|
| پایه (فاز ۱) | 001–011 | محصول نه مشتری · Modular Monolith · Django 6 · SQL Server · API-First · DDD · Clean Arch · Event-Driven · Config محیطی · Security First · مرز SQLite (فقط dev/test) · نام‌گذاری camelCase |
| فاز ۲ | 012–018 | Multi-Tenant ردیفی · AI-Native (Port/Adapter) · Extension/Plugin · Integration (Ports&Adapters) · Observability · Cloud-Ready (stateless) · Offline-Ready (UUID + idempotency) |
| فاز ۶–۹ | 019–024 | توکن session مات چرخشی ← سپس JWT داخلی HS256 (بدون وابستگی جدید) · OpenAPI ساز داخلی · استثنای Shared Kernel · Channels+Daphne+Redis برای Real-time · معماری تحویل Notification (تک‌گیرنده، صف قابل‌تعویض، Outbox) |

نکتهٔ مثبت: ADR-022 صراحتاً تصمیم فرمت توکن ADR-019 را «supersede» می‌کند —
نشانهٔ بلوغ فرایند تصمیم‌گیری.

### ۴-۳. معماری مرجع (architecture/)
- **مجموعهٔ فاز ۲ (۱۲ سند):** SystemArchitecture (۲۰ اصل، دیاگرام Mermaid سیستم/
  کانتینر)، LayerArchitecture، ModuleArchitecture (ماتریس ۱۶ ماژول)،
  DependencyRules (قواعد A–N + ماتریس وابستگی)، SecurityArchitecture،
  MultiTenancy، EventArchitecture (سه نوع Event: Domain/Application/Integration)،
  Integration، AI، Extension، Observability (Correlation ID اجباری، Audit ≠ Log)،
  Storage.
- **مجموعهٔ فاز ۳ (۸ سند، دامنه):** DomainArchitecture، **BoundedContexts (۲۰
  کانتکست با جزئیات مسئولیت/مالکیت)**، DomainMap، DomainDependencies (گراف +
  ماتریس)، AggregateCatalog (~۴۵ aggregate با Invariant)، DomainEvents (پاکت
  ۸ فیلدی اجباری + کاتالوگ)، ValueObjectCatalog (۱۰ VO مشترک + اختصاصی)،
  DomainRules (۱۵ قانون).

### ۴-۴. دیتابیس (database/) — کامل‌ترین بخش مستندات
- **مجموعهٔ فاز ۴ (۱۰ سند شماره‌دار):** ERD سازمانی، ERD دامنه‌به‌دامنه (Mermaid)،
  دیکشنری سطح معماری، کاتالوگ ~۱۹۵ موجودیت، روابط/FK، ایندکس، Constraint،
  Tenancy، Audit، Retention.
- **مجموعهٔ فاز ۵ (۱۲ سند معتبرِ مرجع):** `DatabaseDictionary.md` (۱۹۵ موجودیت،
  ۳۱۴۷ خط)، `FieldCatalog.md` (۲۳۳۱ خط)، `EntityCatalog.md`، **۷۱ قانون کسب‌وکار**
  (BR-TEN/SEC/PER/AUD/DAT/…)، کاتالوگ Constraint/Index، **۱۰ ماشین حالت**،
  **۴۵+ کد خطای پایدار**، سیاست Retention (RET-001..020)، استراتژی Migration
  (expand→migrate→contract)، استراتژی Backup (full/diff/log با RPO/RTO)،
  Data Governance.
- **ابزار `tools/generatePhase5Catalogs.py` (۱۸۹۱ خط):** سه کاتالوگ بزرگ را
  از یک دیتاست واحد تولید می‌کند (جلوگیری از ناسازگاری دستی).

### ۴-۵. فازها (Phases/) — ۲۰ اسپک پیاده‌سازی
| فاز | موضوع | خط | وضعیت کد |
|---|---|---|---|
| 1 | Foundation & Repository | 1586 | ✅ پیاده‌سازی شده (گزارش phase01) |
| 2 | Architecture & ADRs | 2930 | ✅ مستندات + تست |
| 3 | Domain Architecture (۲۰ کانتکست) | 2175 | ✅ طراحی |
| 4 | Enterprise ERD | 3072 | ✅ طراحی |
| 5 | DB Dictionary + Business Rules | 3894 | ✅ طراحی |
| 6 | API & Application Layer | 2120 | ✅ کد (۲۳۵ تست) |
| 7 | Identity, AuthN/AuthZ | 2622 | ✅ کد (۳۱۱ تست) |
| 8 | Communication Platform | 2927 | ✅ کد (۳۸۶ تست) |
| 9 | Notification Platform | 3073 | ✅ کد (**۴۵۷ تست**) |
| 10 | Communication (تکراری) | 3977 | ❌ فقط اسپک |
| 11 | Communication (فارسی، ۸۲ بخش) | 3697 | ❌ فقط اسپک |
| 12 | Notification + Comm Foundation | 2175 | ❌ فقط اسپک |
| 13 | AI Platform | 3054 | ❌ فقط اسپک |
| 14 | Communication (تکراری) | 3783 | ❌ فقط اسپک |
| 15 | Notification (تکراری، Celery) | 4101 | ❌ فقط اسپک |
| 16 | Self-Learning / MLOps | 2691 | ❌ فقط اسپک |
| 17 | Project Intelligence (تحلیل کدبیس!) | 3602 | ❌ فقط اسپک |
| 18 | GUI Architecture | 3578 | ❌ فقط اسپک |
| 19 | SQL Server DB (تکراری با ۴/۵) | 4632 | ❌ فقط اسپک |
| 20 | Configuration Management | 4454 | ❌ فقط اسپک |

### ۴-۶. اسناد تکمیلی
- `api/`: معماری API پیاده‌سازی‌شدهٔ فاز ۶ (envelope، احراز هویت، Idempotency،
  Rate Limit، OpenAPI)، کاتالوگ کامل REST + فریم‌های WebSocket برای Communication
  و Notification.
- `development/`: ۷ گزارش اجرای فاز ۱–۷ با شواهد (تعداد تست، خروجی ruff/mypy) +
  راهنمای Running & Testing (سلامت، کیفیت‌گیت، رفع‌اشکال).
- `operations/`: Runbook فارسی فاز ۸ (نصب Channels، migration، تست، smoke) و
  فاز ۹ (seed قالب‌ها، worker، دمو با curl، WebSocket).
- `Phase 1/2/3/`: **آرشیو بیلد گم‌شده** — manifestهای commit `29621f6` که هرگز
  push نشد؛ با HISTORICAL-NOTE مشخصاً «ARCHIVE ONLY، سند معتبر ندانید».

---

## ۵. وضعیت واقعی کد (تطبیق اسناد با مخزن)

برخلاف ادعای `ANALYSIS.md` که می‌گوید «هیچ کدی در مخزن نیست»، مخزن **اکنون**
شامل پیاده‌سازی کامل فازهای ۱ تا ۹ است:

- **۳۳۴ فایل پایتون** در `backend/`، **۴۵۷ متد تست** (دقیقاً مطابق ادعای
  Phase9Report: 457 tests OK).
- ۵ اپلیکیشن: `sharedKernel`، `tenancy`، `identity`، `communication`،
  `notifications` — هرکدام با ۴ لایهٔ کامل (`domain/application/infrastructure/
  presentation`).
- ۶ migration، ۳ management command (`bootstrapPlatform`, `seedNotifications`,
  `runNotificationWorker`).
- وابستگی‌ها پین‌شده در `requirements/{base,development,testing,production}.txt`
  (Django 6.1، DRF 3.18، Channels 4.3.2، Daphne، channels-redis).
- ۳۲ کامیت در تاریخچهٔ گیت تا `phase 9`.

---

## ۶. مشکلات و تناقض‌های یافت‌شده

### 🔴 بحرانی

1. **اسناد «Canonical» گمشده‌اند اما در ۱۰ فایل ارجاع داده می‌شوند.**
   فازهای ۸، ۹، ۱۰، ۱۱، ۱۲، ۱۴، ۱۵ در NOTE بالای خود به
   `docs/CanonicalCommunication.md` و `docs/CanonicalNotification.md` ارجاع
   می‌دهند که قرار بود تناقض‌های فازهای تکراری را حل کنند — **این دو فایل در
   مخزن وجود ندارند** (آنها متعلق به بیلد گم‌شدهٔ 29621f6 بوده‌اند). عملاً تیم
   فاز ۸ و ۹ را با تصمیم‌های جدید (ADR-023 و ADR-024) حل کرده، اما ارجاعات شکسته
   باقی مانده‌اند.

2. **دامنهٔ Communication چهار بار اسپک شده (فاز ۸، ۱۰، ۱۱، ۱۴)** و
   **Notification سه بار (فاز ۹، ۱۲، ۱۵)** — مجموعاً ~۱۴۰ کیلوبایت اسپک با
   تناقض‌های واقعی:
   - نوع چهارم Conversation: فاز ۱۱ می‌گوید `SYSTEM`، بقیه `MEETING`.
   - نام عضویت: فاز ۸/۱۰ `ConversationParticipant` در برابر فاز ۱۱/۱۴
     `ConversationMember` (کد پیاده‌سازی‌شده از `participant` استفاده می‌کند).
   - نقش: `GUEST` (فاز ۸/۱۰/۱۴) در برابر `READ_ONLY` (فاز ۱۱).
   - Presence: `IN_MEETING` (فاز ۸) در برابر `INVISIBLE` (فاز ۱۰/۱۱/۱۴).
   - Meeting: مدل دولایه در برابر مدل سه‌لایهٔ `Meeting → MeetingRoom →
     MeetingSession` (فقط فاز ۱۱).
   - SFU: فقط فاز ۸ آن را الزامی کرده (در ADR-023 به‌عنوان adapter پذیرفته شد).
   - Read State اعلان: فاز ۱۲ می‌گوید روی `NotificationRecipient` (چند گیرنده)
     و `Notification.isRead` را ممنوع می‌کند؛ فاز ۱۵ همان را روی خود Notification
     می‌گذارد. (ADR-024 عملاً مدل تک‌گیرنده را انتخاب کرد.)
   - بروکر: فاز ۹ «بروکر قابل‌تعویض» در برابر فاز ۱۵ که صراحتاً Celery تجویز
     می‌کند. (ADR-024 رویکرد پورت بدون بروکر را انتخاب کرد.)

3. **دو نقشهٔ راه (Roadmap) متناقض.** ExecutionGuide ترتیب ۰–۲۵ دارد
   (مثلاً دیتابیس فاز ۴، Communication فاز ۱۵)؛ اما پوشهٔ Phases ترتیب دیگری دارد
   (دیتابیس فاز ۱۹، Communication فاز ۸/۱۰/۱۱/۱۴). کد عملاً مسیر Phases را رفته.

4. **دامنه‌های Core هنوز هیچ فاز اختصاصی ندارند:** Organization، Workforce/HR،
   Projects، Tasks، Assets، Devices، Maintenance، Documents، Workflow، Audit —
   یعنی همان‌هایی که فاز ۳ «ارزش اصلی محصول» نامیده — فقط در سطح ERD/دیکشنری
   دیتابیس طراحی شده‌اند، نه اسپک پیاده‌سازی. اپ‌های پیاده‌سازی‌شده فعلاً فقط
   sharedKernel، tenancy، identity، communication، notifications هستند.

### 🟡 متوسط

5. **`ANALYSIS.md` قدیمی است:** می‌گوید «هیچ کدی وجود ندارد»، «پوشه‌های
   architecture/ و adr/ ساخته نشده‌اند»، «فاز ۸/۱۱ خالی‌اند» — همه با وضعیت
   فعلی تناقض دارد (همه ساخته و پیاده شده‌اند).
6. **ری‌برند Meryx → Tekarai ناقص است:** ۹ فایل هنوز شامل «Meryx»اند — مهم‌ترینشان
   پنج فایل UPPER_SNAKE ریشه که نسخهٔ قدیمی کامل هستند.
7. **بخش ۸۰ فاز ۱۱ خراب است:** ترتیب پیاده‌سازی از STEP 1 می‌پرد به STEP 8
   (STEP 2–7 در متن جا افتاده‌اند).
8. **مرز فاز ۱۳ (AI) و فاز ۱۶ (Self-Learning) مبهم است:** هر دو Model
   Versioning، Evaluation، Feedback، Registry دارند.
9. **فاز ۱۷ ناهمگون است:** بقیهٔ فازها دربارهٔ عملیات سازمانی‌اند؛ فاز ۱۷ یک
   ابزار تحلیل کدبیس است (Git، AST، Dependency Graph، Agent Context،
   FastAPI در بخشی از متن) — انگار محصول دوم.
10. **تکنولوژی Frontend هنوز تصمیم‌گیری نشده:** فاز ۱۸ با «STEP 1: Frontend
    Technology Contract» شروع می‌کند ولی انتخابی نکرده؛ پوشهٔ `frontend-web/`
    خالی است.
11. **ریسک سازگاری Django 6 + mssql-django روی مسیر ASGI/Channels** به‌عنوان
    Open Question در ADR-004 ثبت شده ولی بررسی/تجربه‌ای برایش مستند نشده.
12. **ارجاع شکستهٔ `PascalCase.md`** در ADR-001 (منظور قرارداد نام‌گذاری است،
    نه فایل).

### 🟢 جزئی

13. مسیرهای مطلق لوکال در مستندات عملیاتی: `C:\Users\Mitra\Desktop\Tekarai`
    در Runbookها و گزارش‌های فاز — برای دیگر توسعه‌دهندگان گمراه‌کننده است.
14. زبان مستندات مخلوط است (فارسی/انگلیسی) — فاز ۸ و ۹ انگلیسی، فاز ۱۱ فارسی،
    فاز ۷ نیمه‌فارسی.
15. پوشه‌های `product/`, `security/`, `domain/`, `deployment/` فقط placeholder
    دارند (با این حال محتوای security در ADRها و architecture موجود است).
16. خطای تایپی مشترک: `tekraiExceptionHandler` (به‌جای tekarai) در APIArchitecture.
17. پوشهٔ `MyInstractions/` (غلط املاییِ Instructions) با دو فایل یادداشت شخصی.

---

## ۷. جمع‌بندی و پیشنهادها

**نقاط قوت واقعی:**
- نظم معماری فوق‌العاده جدی: DDD/Clean Architecture با تست‌های معماری مکانیکی
  (قواعد A–N وارد کد شده‌اند)، ADRهای زنده که یکدیگر را supersede می‌کنند.
- لایهٔ دیتابیس بسیار عمیق و حرفه‌ای (۱۹۵ موجودیت، ۷۱ قانون، ۱۰ ماشین حالت،
  کدهای خطای پایدار، ابزار تولید خودکار).
- کد فاز ۱–۹ با مستندات هم‌خوان است (۴۵۷ تست، گزارش‌های مبتنی بر شواهد).

**اقدامات پیشنهادی (به‌ترتیب اولویت):**

1. تصمیم نهایی دربارهٔ فازهای تکراری Communication/Notification ثبت شود:
   یا فایل‌های Canonical بازسازی شوند، یا فازهای ۱۰/۱۱/۱۴ و ۱۲/۱۵ به‌صورت
   «SUPERSEDED by Phase 8/9 + ADR-023/024» علامت‌گذاری و آرشیو شوند.
2. ارجاعات شکسته به Canonical\*.md اصلاح یا حذف شوند.
3. فایل‌های UPPER_SNAKE ریشه (نسخهٔ Meryx) حذف شوند تا منبع حقیقت دوگانه نماند.
4. `ANALYSIS.md` به‌روزرسانی شود (وضعیت جدید: فاز ۱–۹ پیاده‌سازی شده).
5. Roadmap واحد انتخاب شود (عملاً مسیر Phases جلو رفته — ExecutionGuide باید
   تطبیق داده شود).
6. اسپک دامنه‌های Core غایب (Organization، HR، Projects، Tasks، Documents،
   Workflow) اولویت بعدی توسعه باشد.
7. تصمیم تکنولوژی Frontend پیش از فاز ۱۸ گرفته شود.
8. مسیرهای مطلق `C:\Users\Mitra\...` از Runbookها پاک‌سازی شوند.

---

*این گزارش حاصل مطالعهٔ کامل هر ۱۳۵ فایل پوشهٔ docs و تطبیق آن با کد واقعی مخزن است.*
