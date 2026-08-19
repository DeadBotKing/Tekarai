# Tekarai — تحلیل کامل مستندات `docs/`

> خروجی مطالعه‌ی کامل ۲۹ سند مخزن (۷ سند ریشه + ۲۰ فایل فاز + README).
> وضعیت: فقط مستندات. **هیچ کدی در مخزن وجود ندارد.**
> این نسخه شامل فازهای ۸ و ۱۱ است که بعداً اضافه شدند.

---

## ۱. پروژه در یک نگاه

| مورد | مقدار |
|---|---|
| نام محصول | **Tekarai** |
| نوع محصول | Enterprise Operations Platform — عمومی، Multi-Tenant، قابل فروش |
| مشتری مرجع | کارخانه داروسازی — فقط به‌عنوان reference، نه مرز محصول |
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
TekaraiMasterImplementationSpecification.md
      ↓
ArchitectureHandoff / DataFlowDocumentation / DevelopmentRules
      ↓
ExecutionGuide
      ↓
Code
```

اگر کد با اسپکِ تأییدشده در تضاد باشد، **کد غلط است** تا وقتی معماری رسماً عوض شود.

ترتیب مطالعه‌ی اجباری:
`TekaraiMasterImplementationSpecification` → `ArchitectureHandoff` → `DataFlowDocumentation` → `DevelopmentRules` → `ExecutionGuide` → `Handoff`

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

- Domain **حق ندارد** Django / DRF / HTTP / ORM / Redis / Channels / WebRTC / SDK خارجی را import کند.
- Infrastructure اینترفیس‌هایی را که لایه‌های داخلی تعریف کرده‌اند پیاده می‌کند (Dependency Inversion).
- Business Rule ممنوع در: `views.py`, `serializers.py`, `models.py`, `admin.py`, `urls.py`, Signal, `Model.save()`, WebSocket Consumer, Middleware.
- Django «فریم‌ورک» است نه «معماری».

**ساختار استاندارد هر Bounded Context:**
```
apps/<context>/
    domain/         entities · valueObjects · aggregates · events · services · repositories · exceptions
    application/    commands · queries · useCases · dto · services · handlers
    infrastructure/ models · repositories · persistence · providers · migrations
    presentation/   api/ (serializers · views · urls · permissions · schemas)
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
3. **Tenant ID از کلاینت قابل اعتماد نیست** — باید از identity احرازشده استخراج شود. Isolation در Application + Repository + Database اعمال شود.
4. **PK همه‌جا UUID** — نه Auto-increment؛ Business ID (`code`, `employeeNumber`) جدا از Technical ID.
5. **Unique ها Tenant-aware:** `UNIQUE(tenantId, code)` نه `UNIQUE(code)`.
6. **Soft Delete پیش‌فرض** — `deletedAt` + `isActive`؛ Hard Delete فقط با Policy.
7. **Base Entity:** `id, createdAt, updatedAt, createdBy, updatedBy, deletedAt, deletedBy, isActive`.
8. **Audit فقط `createdAt/updatedAt` نیست** — باید Who/What/When/Where/Why/Before/After + correlationId باشد. Append-only.
9. **Event ≠ Command** — Event یعنی «اتفاق افتاد»، Command یعنی «انجام بده». Query نباید State تغییر دهد.
10. **ارتباط Cross-Domain فقط از طریق Contract یا Event** — نه دسترسی مستقیم به Model/DB دامنه‌ی دیگر.
11. **AI مالک حقیقت کسب‌وکار نیست** — خروجی AI باید advisory / draft / automated / authoritative طبقه‌بندی شود؛ تغییر authoritative نیازمند Authorization صریح.
12. **Provider Abstraction همه‌جا** — AI، Email، SMS، Push، Storage، Call، Search، SFU: هیچ‌کدام نباید در Core هاردکد شوند.
13. **Media از Django عبور نمی‌کند** — WebRTC مسئول transport؛ Django فقط signaling + business state.
14. **Redis هرگز Source of Truth نیست** — فقط Presence، Typing، Channel Layer، Cache، Lock، Rate Limit.
15. **Industry Logic در Core ممنوع** — WinCC/SAP/Pharma باید Industry Pack / Plugin / Connector باشند.
16. **Money = Decimal** (Float ممنوع) + Currency. **Timestamp = UTC** ذخیره، محلی نمایش.
17. **Outbox Pattern** برای جلوگیری از Lost Event.
18. **Idempotency** برای Webhook، Integration Event، Notification، Send Message، Async Command.
19. **CASCADE پیش‌فرض ممنوع** — برای هر FK باید Delete Policy آگاهانه انتخاب شود؛ `createdBy` و … روی `SET_NULL`.
20. **هیچ Index ای بدون توجیه Query Pattern.**
21. **نام‌گذاری فنی `camelCase` است** (Phase 1 §20، Phase 5 §3، Phase 19 §14–15) — فیلدها (`createdAt`, `tenantId`)، جدول‌ها (`projectMembers`)، توابع و متغیرها. کلاس‌ها `PascalCase`. اسناد `PascalCase.md`. فقط ثابت‌ها و APIهای خودِ Django (`INSTALLED_APPS`, `SECRET_KEY`, `select_related`) دست‌نخورده باقی می‌مانند.

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
- نگهداری State در Process Memory (`connectedUsers = {}`) — مانع Horizontal Scaling.
- ادعای موفقیت بدون اجرای واقعی تست‌ها.

---

## ۹. نقشه‌ی فازها (وضعیت کامل)

| فایل | موضوع | حجم | وضعیت |
|---|---|---|---|
| Phase1 | Foundation & Repository | 19K | ✅ |
| Phase2 | Architecture & ADRs | 33K | ✅ |
| Phase3 | Domain Architecture (Bounded Contexts) | 29K | ✅ |
| Phase4 | Enterprise ERD & Database Architecture | 32K | ✅ |
| Phase5 | Database Dictionary + Business Rules | 39K | ✅ |
| Phase6 | API Architecture & Application Layer | 36K | ✅ |
| Phase7 | Identity, Authentication & Authorization | 42K | ✅ |
| **Phase8** | **Communication Platform** | **27K** | ✅ **جدید** |
| Phase9 | Notification Platform | 28K | ✅ |
| Phase10 | Communication Platform | 41K | ✅ |
| **Phase11** | **Communication Platform** | **31K** | ✅ **جدید** |
| Phase12 | Notifications & Communication Foundation | 22K | ✅ |
| Phase13 | AI Platform & Intelligence Foundation | 35K | ✅ |
| Phase14 | Communication Platform | 41K | ✅ |
| Phase15 | Notification Platform | 45K | ✅ |
| Phase16 | Self-Learning Platform (MLOps) | 27K | ✅ |
| Phase17 | Project Intelligence Platform | 37K | ✅ |
| Phase18 | GUI Architecture & Interface Platform | 34K | ✅ |
| Phase19 | SQL Server Database Architecture | 48K | ✅ |
| Phase20 | Configuration Management & Environment | 47K | ✅ |

**دیگر هیچ فایل خالی وجود ندارد.** اما مشکل بزرگ‌تری آشکار شد ↓

---

## ۱۰. تحلیل فازهای جدید (۸ و ۱۱)

### Phase 8 — Communication Platform (انگلیسی، ۴۱ بخش)
مفاهیم اختصاصی که فقط اینجا هست:
- **SFU (Selective Forwarding Unit)** — تنها فازی که صراحتاً می‌گوید mesh peer-to-peer برای Group Call کافی نیست و باید معماری اجازه‌ی SFU بدهد. (بخش ۱۲)
- **Signaling Protocol Versioning:** `communication.signal.v1` (بخش ۱۱)
- **Official Letters باید Domain Model اختصاصی داشته باشند** — صراحتاً می‌گوید `Message(messageType="LETTER")` غلط است. (بخش ۱۶)
- **تفکیک Domain Event از Integration Event:** `MessageCreated` در برابر `CommunicationMessageCreatedV1` (بخش ۲۵)
- ترتیب پیاده‌سازی ۲۰ مرحله‌ای، جدول‌های `communication_*`

### Phase 11 — Communication Platform (فارسی، ۸۲ بخش)
مفاهیم اختصاصی که فقط اینجا هست:
- **تفکیک سه‌لایه‌ی `Meeting → MeetingRoom → MeetingSession`** — برای Recurring meeting، Reconnect و چند Session. (بخش ۳۴) هیچ فاز دیگری این را ندارد.
- **`CommunicationPolicy` به‌عنوان Entity** با ۱۲ تنظیم: `messageRetentionDays`, `maxAttachmentSize`, `maxGroupMembers`, `allowRecording`, … (بخش ۷۰)
- **Moderation کامل:** `MessageReport`, `UserBlock` با State Machine (بخش ۴۳–۴۵)
- **Legal Hold** — داده تحت Legal Hold نباید طبق Retention معمول حذف شود. (بخش ۶۹)
- **Official Message Lifecycle:** `DRAFT → REVIEW → APPROVED → PUBLISHED → DELIVERED → ACKNOWLEDGED` (بخش ۴۱)
- **Multi-Device Presence Aggregation:** Web=Online + Mobile=Offline ⇒ User=Online (بخش ۲۱)
- **AI Governance fields:** `generatedByAi`, `modelId`, `modelVersion`, `promptVersion`, `confidence`, `humanReviewStatus` (بخش ۷۶)
- **اهداف Scale:** 100,000+ user و 10,000+ concurrent WebSocket (بخش ۶۳)
- **`ANNOUNCEMENT`** به‌عنوان نوع چهارم Channel (بخش ۹)

---

## ۱۱. مشکلات و تناقض‌ها

### 🔴 بحرانی

**۱. Communication چهار بار تعریف شده — فازهای ۸، ۱۰، ۱۱، ۱۴.**
مجموعاً ۱۳۹ کیلوبایت اسپک برای یک دامنه. تناقض‌های واقعی بین آن‌ها:

| موضوع | فاز ۸ | فاز ۱۰ | فاز ۱۱ | فاز ۱۴ |
|---|---|---|---|---|
| انواع Conversation | DIRECT/GROUP/CHANNEL/MEETING | DIRECT/GROUP/CHANNEL/MEETING | DIRECT/GROUP/CHANNEL/**SYSTEM** | DIRECT/GROUP/CHANNEL/MEETING |
| نام Entity عضویت | `ConversationParticipant` | `ConversationParticipant` | **`ConversationMember`** | **`ConversationMember`** |
| Role ها | OWNER/ADMIN/MODERATOR/MEMBER/GUEST | همان | **READ_ONLY** به‌جای GUEST | OWNER/ADMIN/MODERATOR/MEMBER/GUEST |
| Presence States | شامل **IN_MEETING** | شامل **INVISIBLE** | شامل INVISIBLE | شامل INVISIBLE |
| Meeting Session | ندارد | ندارد | **Meeting/Room/Session سه‌لایه** | دولایه |
| SFU | **الزامی** | ذکر نشده | ذکر نشده | ذکر نشده |

این‌ها اگر همزمان پیاده شوند، چهار مدل داده‌ی ناسازگار تولید می‌کنند.

**۲. Notification سه بار تعریف شده — فازهای ۹، ۱۲، ۱۵.**
تناقض اصلی همچنان پابرجاست: فاز ۱۲ می‌گوید Read State باید روی `NotificationRecipient` باشد چون یک Notification چند گیرنده دارد و صراحتاً `Notification.isRead` را ممنوع می‌کند؛ اما فاز ۱۵ دقیقاً `recipient` و `readAt` را روی خود `Notification` می‌گذارد.
تناقض دوم: فاز ۹ می‌گوید broker باید replaceable بماند؛ فاز ۱۵ صراحتاً Celery را تجویز می‌کند.

**۳. دو Roadmap متناقض.**
`TekaraiMasterImplementationSpecification §29` و `ExecutionGuide` یک ترتیب ۰–۲۵ تعریف می‌کنند. فایل‌های `Phases/` ترتیب کاملاً متفاوتی دارند. مثلاً Database Architecture در ExecutionGuide فاز ۴ است اما در Phases فاز ۱۹؛ Communication در ExecutionGuide فاز ۱۵ است اما در Phases فازهای ۸/۱۰/۱۱/۱۴.

**۴. دامنه‌های Core همچنان مستند نشده‌اند.**
با پر شدن فاز ۸ و ۱۱، معلوم شد هر دو Communication بودند. یعنی **هنوز هیچ فاز اختصاصی‌ای برای Projects، Tasks، Documents، Workflow، HR/Workforce و Performance وجود ندارد** — دقیقاً همان‌هایی که فاز ۳ آن‌ها را «Core Domain» و ارزش اصلی محصول نامیده. این دامنه‌ها فقط در سطح ERD (فاز ۴/۵) و DB (فاز ۱۹) اشاره شده‌اند، نه اسپک پیاده‌سازی.

**۵. هیچ‌کدام از خروجی‌های اجباری فازها تولید نشده‌اند.**
فازها ده‌ها فایل الزامی می‌خواهند (`DomainArchitecture.md`, `EntityCatalog.md`, `FieldCatalog.md`, `BusinessRuleCatalog.md`, `StateMachineCatalog.md`, `ErrorCodeCatalog.md`, `ADR-001..016`، دیاگرام‌ها). هیچ‌کدام موجود نیست. پوشه‌های `docs/architecture/` و `docs/adr/` هم ساخته نشده‌اند.

### 🟡 متوسط

**۶. فاز ۱۱ بخش ۸۰ خراب است.** ترتیب پیاده‌سازی از «STEP 1 Reaction» شروع می‌شود و بعد می‌پرد به «STEP 8 Mention» — یعنی STEP 2 تا ۷ (Conversation، Member، Message و…) در متن جا افتاده‌اند.

**۷. ترتیب فازها با قانون خودشان می‌جنگد.** ExecutionGuide می‌گوید «هرگز از فاز ۱ به ۱۵ نپر». اما در Phases، فاز ۷ (Identity) کامل پیاده‌سازی می‌شود در حالی که Database Architecture فاز ۱۹ و Configuration فاز ۲۰ است.

**۸. مرز فاز ۱۳ (AI) و ۱۶ (Self-Learning) مبهم است.** هر دو Model Versioning، Evaluation، Feedback و Registry دارند.

**۹. فاز ۱۷ (Project Intelligence) از نظر مفهومی ناهمگون است.** بقیه درباره‌ی «مدیریت عملیات سازمانی» است؛ فاز ۱۷ یک ابزار تحلیل کدبیس (Git، AST، Dependency Graph، Agent Context) است — انگار محصول دوم.

**۱۰. تکنولوژی Frontend مشخص نشده.** فاز ۱۸ فقط می‌گوید «STEP 1: Frontend Technology Contract».

**۱۱. ریسک سازگاری Django 6 + mssql-django + ASGI/Channels روی SQL Server** در هیچ سندی بررسی نشده.

### 🟢 جزئی

- `README.md` ریشه تقریباً خالی است، در حالی که فاز ۱ بند ۱۸ محتوای مفصلی الزام کرده.
- ساختار مخزن هدف (`backend/`, `frontend-web/`, `mobile/`, `desktop/`, `agents/`, `ai/`, `sdk/`, `deployment/`, `infrastructure/`) ساخته نشده.
- `.gitignore` و `LICENSE` که فاز ۱ الزام کرده وجود ندارند.
- زبان مستندات مخلوط است (فاز ۸ و ۹ انگلیسی، بقیه فارسی/انگلیسی).

---

## ۱۲. پیشنهاد عملی

**قبل از نوشتن اولین خط کد، این سه تصمیم باید گرفته شود:**

1. **ادغام فازهای Communication (۸+۱۰+۱۱+۱۴) در یک اسپک واحد.**
   پیشنهاد پایه: فاز ۱۴ (کامل‌ترین ساختار) + `Meeting/Room/Session` و `CommunicationPolicy` و Moderation و Legal Hold از فاز ۱۱ + الزام SFU و تفکیک Domain/Integration Event از فاز ۸.
   نام‌گذاری قطعی: `ConversationMember` (۲ به ۲ است، ولی فازهای جدیدتر ۱۱ و ۱۴ این را می‌گویند).

2. **ادغام فازهای Notification (۹+۱۲+۱۵) و حل تناقض Read State.**
   مدل فاز ۱۲ از نظر معماری درست است (چند گیرنده ⇒ Read State روی Recipient).

3. **انتخاب یک Roadmap واحد** و نوشتن اسپک برای دامنه‌های Core که هنوز فاز ندارند: Projects، Tasks، Documents، Workflow، Workforce، Performance.

**نقطه‌ی واقعی شروع:**
```
Current Phase:           Phase 01 — Foundation & Repository (شروع نشده)
Repository State:        فقط docs/ + .gitattributes + README خالی
Last Green Quality Gate: ندارد
Open Questions:          ۱۱ مورد بالا
```

اولین کار طبق Handoff:
`Repository → Documentation → Backend Bootstrap → Settings → Database Connection → Core → Identity → Organization`
