# Meryx / Tekarai — تحلیل کامل مستندات `docs/`

> این فایل خروجی مطالعه‌ی کامل ۲۷ سند مخزن است (۶ سند ریشه + ۲۱ فایل فاز).
> وضعیت: فقط مستندات. **هیچ کدی در مخزن وجود ندارد.**

---

## ۱. پروژه در یک نگاه

| مورد | مقدار |
|---|---|
| نام محصول | **Meryx** (نام مخزن `Tekarai` است) |
| نوع محصول | Enterprise Operations Platform — عمومی، Multi-Tenant، قابل فروش |
| مشتری مرجع | کارخانه داروسازی «رونق/Ronak» — فقط به‌عنوان reference، نه مرز محصول |
| سبک معماری | Modular Monolith + DDD + Clean Architecture + SOLID + Event-Driven |
| Backend | Python 3.12 · Django 6 · DRF · SQL Server · mssql-django · SimpleJWT · pyodbc · django-environ · Waitress |
| Real-time | Django Channels · Redis · WebRTC (فقط media) |
| Async | Celery + Redis |
| وضعیت شروع | «پیاده‌سازی قبلی گم شده — از صفر بازسازی کن» |
| هدف | پلتفرمی که ۵ تا ۱۰ سال بدون بازنویسی معماری دوام بیاورد |

**شعار اصلی مستندات:** هدف فقط «اجرا شدن برنامه» نیست، هدف «ساختن پلتفرم درست» است.

---

## ۲. سلسله‌مراتب منبع حقیقت (Source of Truth)

```
ADR های تأییدشده
      ↓
MERYX_MASTER_IMPLEMENTATION_SPECIFICATION.md
      ↓
ARCHITECTURE_HANDOFF / DATA_FLOW / DEVELOPMENT_RULES
      ↓
EXECUTION_GUIDE
      ↓
Code
```

اگر کد با اسپکِ تأییدشده در تضاد باشد، **کد غلط است** تا وقتی معماری رسماً عوض شود.

ترتیب مطالعه‌ی اجباری: Master Spec → Architecture Handoff → Data Flow → Development Rules → Execution Guide → Handoff.

---

## ۳. لایه‌بندی و قانون وابستگی

```
Presentation (REST, WebSocket, Serializer, Auth Adapter)
      ↓
Application (Use Case, Command, Query, DTO, Transaction, Orchestration)
      ↓
Domain (Entity, VO, Aggregate, Domain Event, Domain Service, Repository Contract)
      ↑
Infrastructure (Django ORM, SQL Server, Redis, Storage, Providers)
```

- Domain **حق ندارد** Django / DRF / HTTP / ORM / Redis / SDK خارجی را import کند.
- Infrastructure اینترفیس‌هایی را که لایه‌های داخلی تعریف کرده‌اند پیاده می‌کند (Dependency Inversion).
- Business Rule ممنوع در: `views.py`, `serializers.py`, `models.py`, `admin.py`, `urls.py`, Signal, `Model.save()`, WebSocket Consumer, Middleware.
- Django «فریم‌ورک» است نه «معماری».

**ساختار استاندارد هر Bounded Context:**
```
apps/<context>/
    domain/        entities · value_objects · aggregates · events · services · repositories · exceptions
    application/   commands · queries · use_cases · dto · services · handlers
    infrastructure/ models · repositories · persistence · providers · migrations
    presentation/  api/ (serializers · views · urls · permissions · schemas)
```

---

## ۴. نقشه‌ی دامنه‌ها (Bounded Contexts)

**Core (ارزش اصلی محصول):** Organization · Workforce · Performance · Project Operations · Workflow · AI Intelligence
**Supporting:** Documents · Reporting · Dashboard · Communication · Devices · Integration
**Generic:** Identity · Auth · Notification · Audit · Files · Configuration

فهرست کامل ۲۰ کانتکست (فاز ۳): Identity · Tenancy · Organization · Workforce/HR · Performance · Project · Task · Asset · Device/OT · Maintenance · Document · Workflow · Communication · Notification · Audit · Reporting/Analytics · AI · Integration · Configuration · Platform Core

**گراف وابستگی:**
```
                PLATFORM CORE
                      |
      +---------------+---------------+
   TENANCY        IDENTITY      CONFIGURATION
      |
 ORGANIZATION
      |
  WORKFORCE
      |
 +----+----+-------------+
 |         |             |
PERF    PROJECT        ASSET
           |             |
         TASK         DEVICE
                         |
                    MAINTENANCE
```

---

## ۵. تصمیمات معماری کلیدی (Invariant ها)

1. **`Identity.User` ≠ `People.Employee`** — یک User می‌تواند Employee نباشد (Customer، Contractor، AI Agent، Service Account).
2. **Multi-Tenancy از روز اول** — `User → TenantMembership → Tenant`؛ یک User می‌تواند عضو چند Tenant باشد با وضعیت متفاوت در هرکدام.
3. **Tenant ID از کلاینت قابل اعتماد نیست** — باید از identity احرازشده استخراج شود. Isolation در Application + Repository + Database enforce شود.
4. **PK همه‌جا UUID** — نه Auto-increment؛ Business ID (`code`, `employee_number`) جدا از Technical ID.
5. **Unique ها Tenant-aware:** `UNIQUE(tenant_id, code)` نه `UNIQUE(code)`.
6. **Soft Delete پیش‌فرض** — `deleted_at` + `is_active`؛ Hard Delete فقط با Policy.
7. **Base Entity:** `id, created_at, updated_at, created_by, updated_by, deleted_at, deleted_by, is_active`.
8. **Audit فقط `created_at/updated_at` نیست** — باید Who/What/When/Where/Why/Before/After + correlation_id باشد. Append-only.
9. **Event ≠ Command** — Event یعنی «اتفاق افتاد»، Command یعنی «انجام بده». Query نباید State تغییر دهد.
10. **ارتباط Cross-Domain فقط از طریق Contract یا Event** — نه دسترسی مستقیم به Model/DB دامنه‌ی دیگر.
11. **AI مالک حقیقت کسب‌وکار نیست** — خروجی AI باید advisory / draft / automated / authoritative طبقه‌بندی شود؛ تغییر authoritative نیازمند Authorization صریح.
12. **Provider Abstraction همه‌جا** — AI، Email، SMS، Push، Storage، Call، Search: هیچ‌کدام نباید در Core هاردکد شوند.
13. **Media از Django عبور نمی‌کند** — WebRTC مسئول transport؛ Django فقط signaling + business state.
14. **Redis هرگز Source of Truth نیست** — فقط Presence، Typing، Channel Layer، Cache، Lock، Rate Limit.
15. **Industry Logic در Core ممنوع** — WinCC/SAP/Pharma باید Industry Pack / Plugin / Connector باشند.
16. **Money = Decimal** (Float ممنوع) + Currency. **Timestamp = UTC** ذخیره، محلی نمایش.
17. **Outbox Pattern** برای جلوگیری از Lost Event.
18. **Idempotency** برای Webhook، Integration Event، Notification، Send Message، Async Command.
19. **CASCADE پیش‌فرض ممنوع** — برای هر FK باید Delete Policy آگاهانه انتخاب شود؛ `created_by` و … روی `SET_NULL`.
20. **هیچ Index ای بدون توجیه Query Pattern.**

---

## ۶. جریان‌های داده (Data Flow)

**Command:**
`Client → HTTP/WS → Authentication → Authorization → Validation → Use Case → Aggregate → Repository Interface → Infrastructure → SQL Server → Domain Event → Handlers → Audit/Notification/Projection/Integration`

**Query:**
`Client → Auth → Authorization → Query → Selector/Read Repo → DB/Read Model → DTO → Response`

**Authorization چندلایه:** Authentication → Tenant Isolation → Permission → Role → Scope → Object-Level Policy → Business Rule → Allow/Deny

**RAG:** `Document → Chunk → Embedding → Vector Index → Authorized Retrieval → Context → LLM → Answer`
نکته حیاتی: **Permission Filtering باید قبل از ارسال Context به مدل انجام شود، نه بعد از تولید پاسخ.**

---

## ۷. Quality Gate و Definition of Done

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
ruff check .
ruff format --check .
mypy .
```

**DoD یک Feature:** Domain behavior + Use Case + Persistence + Authorization + API + Migration + Tests سبز + Quality Gate سبز + Documentation به‌روز + Audit تأییدشده + Tenant Isolation تست‌شده.

**فرمت گزارش پایان هر تسک:**
`Task / Phase / Files Created / Modified / Deleted / Architecture Decision / Tests / Migration Status / Quality Checks / Known Issues / Next Task`

**فرمت گزارش خطا:**
`Problem → Evidence → Root Cause → Proposed Solution → Architectural Impact → Implementation → Verification`

**Resume Protocol شروع هر session:**
`Current Phase / Sprint / Domain / Task / Repository State / Last Verified Commit / Last Green Quality Gate / Open Questions`

---

## ۸. ممنوعیت‌های سراسری

- حدس زدن نیازمندی → به‌جایش Open Question ثبت کن.
- `TODO`, `pass`, `raise NotImplementedError`, Fake Repository, Fake API، کد موقت در production.
- کامیت Secret · لاگ کردن Password/Token · نمایش Stack Trace به کلاینت.
- ساخت Microservice قبل از اثبات مرزهای دامنه.
- `models.py` غول‌پیکر · `utils.py` انبار زباله · `CommonService`/`ManagerService`.
- استفاده‌ی صرف از `is_superuser` / `is_staff` برای Authorization.
- Offset Pagination برای Message History حجیم (باید Cursor باشد).
- ساخت رکورد SQL برای هر Typing Event یا Presence Heartbeat.
- ادعای موفقیت بدون اجرای واقعی تست‌ها.

---

## ۹. نقشه‌ی فازها (وضعیت واقعی فایل‌ها)

| فایل | موضوع | حجم | وضعیت |
|---|---|---|---|
| Phase1 | Foundation & Repository | 18K | ✅ کامل |
| Phase2 | Architecture & ADRs | 33K | ✅ کامل |
| Phase3 | Domain Architecture (Bounded Contexts) | 29K | ✅ کامل |
| Phase4 | Enterprise ERD & Database Architecture | 32K | ✅ کامل |
| Phase5 | Database Dictionary + Business Rules | 39K | ✅ کامل |
| Phase6 | API Architecture & Application Layer | 36K | ✅ کامل |
| Phase7 | Identity, Authentication & Authorization | 42K | ✅ کامل |
| **Phase8** | **—** | **0** | ❌ **خالی** |
| Phase9 | Notification Platform | 28K | ✅ کامل |
| Phase10 | Communication Platform | 41K | ✅ کامل |
| **Phase11** | **—** | **0** | ❌ **خالی** |
| Phase12 | Notifications & Communication Foundation | 22K | ✅ کامل |
| Phase13 | AI Platform & Intelligence Foundation | 35K | ✅ کامل |
| Phase14 | Communication Platform (دوباره) | 41K | ✅ کامل |
| Phase15 | Notification Platform (دوباره) | 45K | ✅ کامل |
| Phase16 | Self-Learning Platform (MLOps) | 27K | ✅ کامل |
| Phase17 | Project Intelligence Platform | 37K | ✅ کامل |
| Phase18 | GUI Architecture & Interface Platform | 34K | ✅ کامل |
| Phase19 | SQL Server Database Architecture | 48K | ✅ کامل |
| Phase20 | Configuration Management & Environment | 47K | ✅ کامل |

---

## ۱۰. مشکلات و تناقض‌هایی که پیدا کردم

### 🔴 بحرانی

**۱. دو Roadmap متناقض وجود دارد.**
`Master Spec §29` و `Execution Guide` یک ترتیب ۰–۲۵ تعریف می‌کنند (Core→Identity→Org→People→Projects→Tasks→Assets→…).
فایل‌های `Phases/` ترتیب کاملاً متفاوتی دارند (Foundation→ADR→Domain→ERD→Dictionary→API→Identity→…→GUI→DB→Config).
مثلاً Database Architecture در Execution Guide فاز ۴ است، اما در Phases فاز ۱۹. مشخص نیست کدام حاکم است.

**۲. فاز ۸ و ۱۱ کاملاً خالی‌اند (0 بایت).**
با توجه به ترتیب همسایه‌ها، احتمالاً باید Documents/Workflow و Projects/Tasks می‌بودند — یعنی **دقیقاً دامنه‌های Core محصول مستند نشده‌اند.**

**۳. Notification سه بار و Communication دو بار تعریف شده — با جزئیات متناقض:**
- Notification: فاز ۹ (انگلیسی) + فاز ۱۲ (فارسی) + فاز ۱۵ (فارسی، مفصل‌ترین).
- Communication: فاز ۱۰ + فاز ۱۴.
- تناقض واقعی: فاز ۱۲ می‌گوید Read State باید روی `NotificationRecipient` باشد چون یک Notification چند گیرنده دارد. فاز ۱۵ اما `recipient` و `read_at` را مستقیم روی خود `Notification` می‌گذارد. **این دو مدل داده با هم ناسازگارند.**
- تناقض دوم: فاز ۹ می‌گوید broker/worker باید replaceable بماند؛ فاز ۱۵ صراحتاً Celery را تجویز می‌کند.

**۴. هیچ‌کدام از خروجی‌های اجباری فازها تولید نشده‌اند.**
فازها ده‌ها فایل الزامی می‌خواهند (`DOMAIN_ARCHITECTURE.md`, `ENTITY_CATALOG.md`, `FIELD_CATALOG.md`, `BUSINESS_RULE_CATALOG.md`, `STATE_MACHINE_CATALOG.md`, `ERROR_CODE_CATALOG.md`, `ADR-001..016`, دیاگرام‌ها، …). **هیچ‌کدام موجود نیست.** حتی `docs/architecture/` و `docs/adr/` هم ساخته نشده‌اند.

### 🟡 متوسط

**۵. ترتیب فازها با قانون خودشان می‌جنگد.**
Execution Guide می‌گوید «هرگز از فاز ۱ به ۱۵ نپر، وابستگی‌ها دلیل دارند». اما در Phases، فاز ۷ (Identity) کامل پیاده‌سازی می‌شود در حالی که Database Architecture فاز ۱۹ و Configuration فاز ۲۰ است. یعنی باید مدل‌های Identity را قبل از تثبیت معماری DB و Config بسازی.

**۶. مرز فاز ۱۶ (Self-Learning) و ۱۳ (AI) مبهم است.** هر دو Model Versioning، Evaluation، Feedback، Registry دارند. مشخص نیست چه چیزی مال کدام است.

**۷. فاز ۱۷ (Project Intelligence) از نظر مفهومی ناهمگون است.** بقیه‌ی پلتفرم درباره‌ی «مدیریت عملیات سازمانی» است؛ فاز ۱۷ یک ابزار تحلیل کدبیس (Git، AST، Dependency Graph، Agent Context) است — انگار محصول دوم است.

**۸. فاز ۱۸ تکنولوژی Frontend را مشخص نمی‌کند.** فقط می‌گوید «STEP 1: Frontend Technology Contract». React/Vue/Angular هیچ‌کدام انتخاب نشده.

**۹. ابهام SQL Server + Django 6.** ترکیب Django 6 با `mssql-django` و Channels/ASGI روی SQL Server ریسک سازگاری دارد و در مستندات به آن اشاره نشده.

### 🟢 جزئی

- نام مخزن `Tekarai` است ولی همه‌جای مستندات `Meryx` — رابطه‌شان توضیح داده نشده.
- `README.md` ریشه فقط یک خط `# Tekarai` است، در حالی که فاز ۱ محتوای مفصلی برایش الزام کرده.
- زبان مستندات مخلوط است (فاز ۹ کاملاً انگلیسی، بقیه فارسی/انگلیسی).
- ساختار مخزن هدف (`backend/`, `frontend-web/`, `mobile/`, `desktop/`, `agents/`, `ai/`, `sdk/`, `deployment/`, `infrastructure/`) هنوز ساخته نشده.
- `.gitattributes` هست ولی `.gitignore` و `LICENSE` که فاز ۱ الزام کرده، نیست.

---

## ۱۱. نقطه‌ی واقعی شروع

طبق سند خودشان، وضعیت فعلی دقیقاً این است:

```
Current Phase:          Phase 01 — Foundation & Repository (شروع نشده)
Repository State:       فقط docs/ + .gitattributes + README خالی
Last Green Quality Gate: ندارد
Open Questions:         ۹ مورد بالا
```

اولین کار طبق Handoff: `Repository → Documentation → Backend Bootstrap → Settings → Database Connection → Core → Identity → Organization`.
