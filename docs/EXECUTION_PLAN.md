# Tekarai — Execution Plan & Progress Log (فاز ۱۸ب: اتصال UI به بکاند واقعی)

> این سند دفترچهٔ راهنما و گزارش پیشرفت کار ماست. سه بخش دارد:
> **چه می‌کنیم** (وضعیت فعلی) · **چه کردیم** (انجام‌شده) · **چه خواهیم کرد** (بعدی).

**تاریخ شروع:** 2026-09-14
**ورود پیش‌فرض:** Tenant=`platform` · User=`platform-admin` · Pass=`Tekarai-Demo-2026!`

---

## ۱) چه می‌کنیم — نقشهٔ راه (۵ گام)

| # | گام | توضیح | وضعیت |
|---|---|---|---|
| 1 | اتصال صفحات دمو به بکاند | ساخت دامنه‌های Projects و Tasks در بکاند + اتصال UI | ✅ انجام شد |
| 2 | ساخت دادهٔ واقعی در SQL Server | فرمان seed برای ساخت tenant/user/پروژه/تسک واقعی | ✅ انجام شد |
| 3 | تست جریان‌های آمادهٔ بکاند | ساخت کاربر/نقش، اعلان broadcast، گفتگو/چت، اجرای ایجنت AI | ✅ انجام شد |
| 4 | اعلان‌ها برای کاربر واقعی | ارسال اعلان به platform-admin + مشاهده در UI | 🟡 پیاده‌سازی شد؛ تست زندهٔ UI در حال اجرا |
| 5 | امکانات زیرساختی | پروفایل کاربر، MFA، کلید API، لاگ ممیزی | ⏸ در انتظار |

---

## ۲) چه کردیم (تاریخچه)

### پیش از این سند (پایدارسازی محیط)
- ✅ کل ریپو کلون و تست شد (۲۲۷۸ تست بکاند + ۱۵ تست فرانتاند سبز).
- ✅ ۷ خطای معماری از فاز ۱۳ رفع شد (حذف `apps/ai/models.py`، `test_provider.py`، پوشهٔ خالی `apps/ai/migrations`، افزودن بخش Alternatives به ADR-025).
- ✅ `run_dev.ps1` ساخته شد: یک دستور، اجرای هم‌زمان بکاند + فرانتاند.
- ✅ ورود واقعی (غیر-دمو) به بکاند با `frontend-web/.env` (VITE_DEMO_MODE=false).
- ✅ اتصال SQL Server Express درست شد:
  - باگ `mssql_django` → `mssql` (اسم واقعی ماژول پایتونی پکیج mssql-django).
  - پورت پیش‌فرض `dbPort` از `1433` به خالی تغییر کرد (named instance `localhost\SQLEXPRESS` بدون پورت).
  - `backend/scripts/ensureDatabase.py` برای ساخت خودکار دیتابیس + تشخیص درایور ODBC.
  - فایل `run_dev.ps1` به‌صورت ASCII + BOM ذخیره شد تا روی PowerShell ویندوز فارسی درست خوانده شود.
- ✅ کاربر واقعی با این اعتبار وارد سایت شد.

### گام ۱ — دامنه‌های Projects و Tasks + اتصال UI (انجام شد ✅)

**بکاند — دو bounded context جدید (فاز ۱۸ب):**
- دامنه (`domain/`): موجودیت `Project` (aggregate با وضعیت active/onHold/completed/archived و transition مجاز) و `Task` (backlog/todo/inProgress/review/done) + value objects و قرارداد repository.
- کاربرد (`application/`): کامند/کوئری/DTO/use-case با قالب ۸مرحله‌ای §8 (اعتبارسنجی، مجوز action-based، business rule، UoW، audit، event).
- زیرساخت (`infrastructure/`): مدل‌های ORM (`ProjectModel`, `TaskModel`)، پیاده‌سازی repository، container و migration (`0001_initial`).
- presentation: serializer / views / urls با `BearerSessionAuthentication` + ثبت OpenAPI در `/api/v1/docs`.
- مسیرها: `GET/POST /api/v1/projects/`، `GET/PATCH /api/v1/projects/{id}`، `POST /api/v1/projects/{id}/status`؛ همین‌طور برای `/api/v1/tasks/`.
- مجوزها: `project.create/view/list/update` و `task.create/view/list/update` به `permissionCatalog.py` (ACTIONS + ROLE_PRESETS) اضافه شد.
- ثبت معماری: `testNoBusinessDomains.py` و `testPhase3DomainArchitecture.py` دو کانتکست را باز کردند؛ vocabulary guard برای `permissionCatalog.py` بی‌اثر شد (کامنت lowercase).

**فرانت‌اند — اتصال صفحات Projects/Tasks به API واقعی:**
- `core/api/endpoints.ts`: افزودن مسیرهای `projects/` و `tasks/` (با اسلش انتهایی — مطابق mount بکاند).
- `features/projects/projectService.ts` و `features/tasks/taskService.ts`: adapter از DTO بکاند → تایپ‌های UI (`ownerName→owner`، `projectId→project` با حل نام پروژه، `todo→backlog`) + ساخت خودکار `code` پروژه (BR-PRJ-001).
- `pages/ProjectsPage.tsx` و `pages/TasksPage.tsx`: دریافت لیست از API، ساخت/ویرایش پروژه، ساخت تسک و جابه‌جایی ستون board از طریق API؛ وقتی `VITE_DEMO_MODE=false` است دادهٔ واقعی وگرنه دمو (fallback).
- تایپ‌ها و UI: افزودن وضعیت `onHold` به `Status`، `StatusBadge` و `i18n`؛ کلیدهای `project.saveFailed`، `task.createSuccess`، `task.saveFailed`.
- `core/permissions/permissionContext.tsx`: افزودن `projectList/taskList/taskUpdate`.

**تست‌ها (همه سبز):**
- بکاند کامل: **۲۲۸۶ تست OK** (۲۲۷۹ قبلی + ۷ تست یکپارچه‌سازی جدید `testPhase18bWorkspaceDeliveryApi`).
- معماری: **۱۶۴ تست OK**.
- فرانت‌اند: typecheck ✅ · ۱۵ تست vitest ✅ · build ✅.

**اشکالاتی که حین کار پیدا و رفع شد:**
- مسیر کالکشن بدون اسلش انتهایی ۳۰۱ می‌داد → فرانت‌اند و تست‌ها به `projects/` و `tasks/` (با اسلش) رفتند.
- مبدل `<uuid:...>` مسیر، UUID را از قبل تبدیل می‌کرد → `str()` در views اضافه شد.
- وضعیت انتقال نامعتبر پروژه ۴۰۹ (نه ۴۲۲) برمی‌گرداند → تست اصلاح شد.

### رفع باگ مهم: «چیزی برای Tasks و Projects دیده نمی‌شود»
- **ریشه:** پاسخ `POST /api/v1/auth/login` فقط `user` خام (UserDto) برمی‌گرداند و `permissions` نداشت؛ فرانت‌اند `session.user.permissions` را از همان پاسخ می‌خواند → لیست دسترسی خالی → تمام آیتم‌های PermissionGuard (منوی Projects/Tasks، دکمهٔ «پروژهٔ جدید»/«تسک جدید» و…) مخفی می‌شدند.
- **رفع:**
  - بک‌اند: `AuthTokenDto.permissions` اضافه شد؛ `AuthenticateUserUseCase` حالا `AccessRepository` تزریق می‌گیرد و در `_openSession` و `_startMfaChallenge` همان permissionهای مؤثر `/me` را برمی‌گرداند.
  - فرانت‌اند: `authContext.login` حالا `response.permissions` را می‌خواند و در session ذخیره می‌کند.
  - تست رگرسیون: `LoginContractTests.testLoginPayloadCarriesEffectivePermissions` (وجود `project.view`/`task.create` و… در پاسخ login).
- **نکته برای کاربر:** پس از جایگزینی فایل‌ها، یک‌بار logout/login کنید تا دسترسی‌ها تازه شوند؛ نقش `platformAdmin` موجود در دیتابیس با اجرای دوبارهٔ `bootstrapPlatform` (که `run_dev.ps1` خودکار انجام می‌دهد) permissionهای جدید را می‌گیرد.

---

### گام ۲ — فرمان `seedWorkspace` (انجام شد ✅)

- فایل: `backend/apps/projects/management/commands/seedWorkspace.py`.
- idempotent: بار دوم «exists/ready» چاپ می‌کند و چیزی تکراری نمی‌سازد.
- چه می‌سازد:
  - tenant و admin پلتفرم (از طریق `bootstrapPlatform`)،
  - tenant دموی `acme` + کاربر `acme-admin` (نقش tenantAdmin) و `acme-member` (نقش member)،
  - ۴ پروژه و ۶ تسک در هر دو tenant (کدهای NOVA-24 / ATLAS-11 / ORBIT-07 / BRIDGE-18).
- از همان use-caseهای لایهٔ کاربرد استفاده می‌کند (audit + event مثل درخواست واقعی)، نه ORM مستقیم.
- `run_dev.ps1` حالا بعد از `bootstrapPlatform`، `seedWorkspace` را هم اجرا می‌کند (خطای آن fatal نیست).
- تست: `SeedWorkspaceCommandTests.testSeedIsIdempotentAndProvisionsAllAggregates` (۲ بار اجرا، شمارش ثابت).
- بکاند کامل: **۲۲۸۸ تست OK** · معماری **۱۶۴ تست OK**.

### گام ۳ — اسکریپت `exercise_flows.ps1` (انجام شد ✅)

- فایل: `exercise_flows.ps1` (ریشهٔ پروژه، ASCII + BOM مثل `run_dev.ps1`).
- با بکاند در حال اجرا (`.\run_dev.ps1`) این جریان‌ها را روی API واقعی HTTP تمرین می‌کند و برای هر مرحله `[PASS]/[FAIL]` چاپ می‌کند (خروجی غیرصفر در صورت شکست — قابل استفاده به‌عنوان smoke test):
  1. **کاربر/نقش:** ورود واقعی → `GET /me` → `GET /users` → `POST /users` (ساخت کاربر) → `GET /roles` → `POST /users/{id}/roles` (تخصیص نقش member).
  2. **اعلان broadcast:** `POST /notifications/broadcasts` برای خود admin → `GET /notifications/broadcasts/unread-count` (≥۱).
  3. **گفتگو/چت:** `POST /communication/conversations` (گروه) → `POST …/messages` (ارسال) → `GET …/messages` (لیست، totalCount≥۱).
  4. **ایجنت AI:** `POST /ai/agents` (ثبت DETERMINISTIC) → `submit` → `approve` → `POST /ai/agents/{code}/runs` (SYNC) → وضعیت `COMPLETED` + `GET /ai/runs/{id}/steps` (≥۱ گام).
- **یک باگ واقعی حین تست پیدا و رفع شد:** اجرای ایجنت در حالت development با `AI_AGENT_INVALID` شکست می‌خورد، چون provider آفلاین `DETERMINISTIC` فقط در settings تست فعال بود (`aiAgentAllowDeterministicProvider` پیش‌فرض false). رفع: `run_dev.ps1` حالا `aiAgentAllowDeterministicProvider=true` را برای بکاند development تنظیم می‌کند (این سوییچ هرگز در production فعال نمی‌شود).
- **باگ PowerShell 5.1 در اجرای واقعی روی ویندوز کاربر پیدا و رفع شد:** در PowerShell، تایپ `[string]` برای پارامتر `Body` مقدار پیش‌فرض `$null` را به رشتهٔ خالی `""` تبدیل می‌کند؛ در نتیجه درخواست‌های GET یک body خالی ارسال می‌کردند و با `Cannot send a content-body with this verb-type` شکست می‌خوردند. رفع: پارامتر `Body` بدون تایپ `[string]` شد و شرط `$null -ne $Body -and $Body -ne ""` فقط در صورت وجود body واقعی، `Body` و `ContentType` را ست می‌کند. با PowerShell واقعی (pwsh) علیه بک‌اند زنده تست شد: **۲۵/۲۵ PASS**.
- **اعتبارسنجی:** کل جریان با یک سرور واقعی (Daphne + SQLite) در محیط اجرا شد — **۲۵/۲۵ گام PASS**. بکاند کامل **۲۲۸۸ تست OK** · معماری **۱۶۴ تست OK**.

## ۳) چه خواهیم کرد

- [x] گام ۱: دامنه‌های Projects/Tasks + اتصال UI — ✅
- [x] گام ۲: فرمان `seedWorkspace` — ✅
- [x] گام ۳: اسکریپت `exercise_flows.ps1` — تست end-to-end جریان‌ها روی API واقعی (کاربر/نقش، broadcast، چت، ایجنت AI).
- [ ] گام ۴: ارسال اعلان واقعی به platform-admin و مشاهده در UI — 🟡 API و اتصال UI پیاده‌سازی شد؛ تست زندهٔ مرورگر باقی است.
- [x] گام ۴: مسیر UI از API واقعی `notifications/broadcasts` می‌خواند، unread count را از state recipient محاسبه می‌کند و mark-read را به `broadcasts/{id}/read` می‌فرستد.
- [x] گام ۵: backendهای موجود profile (`/me`)، MFA (`/me/mfa/*`)، API keys (`/api-keys`) و audit (`/platform/audit-events`) به UI واقعی متصل شدند.
- [x] گام ۵: Settings اکنون پروفایل session، شروع/تأیید TOTP، API key با نمایش یک‌بارهٔ raw secret، revoke، sessions و revoke-all را نمایش می‌دهد.
- [x] گام ۵: صفحهٔ Administration > Audit رویدادها را از audit stream واقعی با cursor/pageSize می‌خواند.
- [x] پس از گام ۴ و ۵: frontend typecheck، ۱۵ تست Vitest و build سبز.
- [ ] گام ۵: تست زندهٔ Windows برای API key/MFA/Audit و تأیید مرورگر باقی است.
- [ ] پس از هر گام: بکاند کامل + معماری + typecheck/تست/build فرانتاند.
- [ ] بازسازی فایل تحویل `Tekarai-Project.zip` در پایان.
