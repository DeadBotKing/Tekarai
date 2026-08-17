============================================================

MERYX — PHASE 02

ARCHITECTURE \& ARCHITECTURAL DECISION RECORDS

============================================================



STATUS:

PHASE 02 — ARCHITECTURE \& ADRs



PREVIOUS PHASE:

PHASE 01 — FOUNDATION \& REPOSITORY



PURPOSE:

تبدیل Foundation ایجادشده در Phase 01 به یک Architecture Specification

رسمی، قابل اجرا، قابل تست و قابل توسعه برای Meryx.



در این فاز هنوز نباید وارد طراحی کامل Business Domainها، ERD نهایی

یا پیاده‌سازی گسترده Modelهای Django شویم.



هدف Phase 02 این است که قبل از رشد کد، مرزهای معماری کاملاً مشخص شوند.



\------------------------------------------------------------

1\. CORE PRINCIPLE

\------------------------------------------------------------



Meryx یک Enterprise Operations Platform است.



Meryx باید:



\- عمومی باشد.

\- Multi-Tenant باشد.

\- قابل توسعه باشد.

\- قابل فروش باشد.

\- Industry Agnostic باشد.

\- Cloud Ready باشد.

\- Offline Ready باشد.

\- AI Native باشد.

\- API First باشد.

\- Security First باشد.

\- قابل Audit باشد.

\- قابل Extension باشد.



Meryx نباید برای یک شرکت یا صنعت خاص طراحی شود.



اگر یک قابلیت فقط برای یک صنعت خاص مورد نیاز باشد، باید در آینده

به صورت:



Industry Pack

Extension

Plugin

Integration



پیاده‌سازی شود.



Core Platform نباید به Industry Logic وابسته شود.



\------------------------------------------------------------

2\. ARCHITECTURAL STYLE

\------------------------------------------------------------



Architecture Style:



MODULAR MONOLITH



Meryx در ابتدا یک Modular Monolith خواهد بود.



اما معماری باید به شکلی باشد که در آینده در صورت نیاز بتوان

بخش‌هایی از سیستم را بدون بازنویسی Business Logic به Service

مستقل تبدیل کرد.



هدف:



Modular Monolith First

Distributed Systems Only When Justified



Microservices نباید صرفاً به دلیل Enterprise بودن محصول استفاده شوند.



\------------------------------------------------------------

3\. ARCHITECTURAL PRINCIPLES

\------------------------------------------------------------



اصل 01:

Platform First



اصل 02:

API First



اصل 03:

Domain Driven Design



اصل 04:

Clean Architecture



اصل 05:

SOLID



اصل 06:

Event Driven



اصل 07:

Security First



اصل 08:

AI Native



اصل 09:

Cloud Ready



اصل 10:

Offline Ready



اصل 11:

Configuration over Customization



اصل 12:

Documentation Driven Development



اصل 13:

Everything is Auditable



اصل 14:

Everything is Extensible



اصل 15:

Explicit over Implicit



اصل 16:

Separation of Concerns



اصل 17:

Dependency Inversion



اصل 18:

Backward Compatibility



اصل 19:

Observability by Design



اصل 20:

Testability by Design



\------------------------------------------------------------

4\. ARCHITECTURE LAYERS

\------------------------------------------------------------



Meryx باید از Separation of Concerns واقعی استفاده کند.



Logical Architecture:



&#x20;                   CLIENTS

&#x20;                      │

&#x20;                      ▼

&#x20;               API / INTERFACE

&#x20;                      │

&#x20;                      ▼

&#x20;               APPLICATION LAYER

&#x20;                      │

&#x20;                      ▼

&#x20;                 DOMAIN LAYER

&#x20;                      │

&#x20;                      ▼

&#x20;             INFRASTRUCTURE LAYER



همچنین Cross-Cutting Concerns باید جدا باشند:



\- Security

\- Logging

\- Audit

\- Observability

\- Configuration

\- Events

\- Caching

\- Messaging

\- Error Handling



\------------------------------------------------------------

5\. DOMAIN LAYER

\------------------------------------------------------------



Domain Layer مالک Business Rules است.



Domain Layer نباید وابسته به:



\- HTTP

\- REST Framework

\- Django Views

\- Serializers

\- Database implementation

\- Redis

\- Celery

\- External APIs



باشد.



Domain باید تا حد امکان مستقل و قابل تست باشد.



Business Rule نباید داخل:



View

Serializer

URL

Admin

Middleware



قرار گیرد.



\------------------------------------------------------------

6\. APPLICATION LAYER

\------------------------------------------------------------



Application Layer مسئول Orchestration است.



وظایف:



\- اجرای Use Caseها

\- هماهنگی Domainها

\- Transaction orchestration

\- Authorization orchestration

\- Calling repositories

\- Publishing application events

\- Calling external ports



Application Layer نباید مالک Business Ruleهای Domain شود.



Application Layer باید Use Case-oriented باشد.



مثال مفهومی:



CreateProject

AssignTask

ApproveDocument

StartWorkflow

CreateMeeting



هرکدام باید به صورت Use Case قابل تعریف باشند.



\------------------------------------------------------------

7\. INFRASTRUCTURE LAYER

\------------------------------------------------------------



Infrastructure مسئول پیاده‌سازی تکنولوژی است.



مثال:



\- Django ORM

\- SQL Server

\- Redis

\- File Storage

\- Email Provider

\- WebRTC infrastructure

\- External APIs

\- AI Providers

\- Message Brokers



Infrastructure نباید Business Rule را مالک شود.



Infrastructure باید Interface/Portهای تعریف‌شده توسط لایه‌های بالاتر

را پیاده‌سازی کند.



\------------------------------------------------------------

8\. INTERFACE LAYER

\------------------------------------------------------------



Interface Layer شامل Adapterهای ارتباط با سیستم بیرونی است.



مثال:



REST API

WebSocket

CLI

Admin

Webhooks

External API adapters



Interface Layer باید درخواست را به Application Layer منتقل کند.



Business Logic نباید در API Viewها نوشته شود.



\------------------------------------------------------------

9\. DEPENDENCY RULE

\------------------------------------------------------------



Dependency Direction باید کنترل‌شده باشد.



اصل:



Outer Layers → Inner Layers



اما:



Inner Layers → Outer Layers



ممنوع است.



به صورت مفهومی:



Infrastructure

&#x20;     ↓

Application

&#x20;     ↓

Domain



Interface

&#x20;     ↓

Application

&#x20;     ↓

Domain



Domain نباید به Infrastructure وابسته باشد.



\------------------------------------------------------------

10\. DEPENDENCY INVERSION

\------------------------------------------------------------



اگر Domain/Application به یک Infrastructure capability نیاز دارد،

باید از Abstraction استفاده شود.



مثال مفهومی:



Application نیاز دارد User Repository داشته باشد.



Application نباید مستقیماً به:



Django ORM



وابسته شود.



بلکه:



UserRepository

&#x20;   ↓

Repository Interface

&#x20;   ↓

Django Repository Implementation



استفاده شود.



\------------------------------------------------------------

11\. MODULARITY

\------------------------------------------------------------



Meryx باید به Domain/Capability Moduleهای مستقل تقسیم شود.



Target Capability Map:



Platform Core

Identity

Organization

People / HR

Projects

Tasks

Assets

Devices

Maintenance

Documents

Workflow

Communication

Notifications

Analytics

AI

Integration Hub



این فهرست در Phaseهای بعدی دقیق‌تر خواهد شد.



Agent نباید در Phase 02 برای همه این موارد Model بسازد.



در این فاز فقط Boundaryها مشخص می‌شوند.



\------------------------------------------------------------

12\. MODULE BOUNDARIES

\------------------------------------------------------------



هر Module باید:



\- مسئولیت مشخص داشته باشد.

\- API داخلی مشخص داشته باشد.

\- Dependency مشخص داشته باشد.

\- Domain Model مشخص داشته باشد.

\- Application Services مشخص داشته باشد.

\- Infrastructure Adapter مشخص داشته باشد.

\- Event Contract مشخص داشته باشد.



Module نباید مستقیماً به دیتابیس Module دیگر دسترسی پیدا کند

مگر اینکه Architecture Specification صراحتاً چنین چیزی را مجاز کند.



\------------------------------------------------------------

13\. DOMAIN BOUNDARY RULE

\------------------------------------------------------------



هر Domain مالک داده و Business Rule خودش است.



مثال:



Employee Domain

مالک Employee Business Rules است.



Project Domain

مالک Project Business Rules است.



Task Domain

مالک Task Business Rules است.



Document Domain

مالک Document Business Rules است.



Communication Domain

مالک Communication Business Rules است.



این Domainها نباید Business Logic یکدیگر را کپی کنند.



\------------------------------------------------------------

14\. CROSS-DOMAIN COMMUNICATION

\------------------------------------------------------------



ارتباط Domainها باید از Contractهای مشخص انجام شود.



روش‌های مجاز:



\- Application Service

\- Domain Interface

\- Application Event

\- Domain Event

\- Query Interface

\- Integration Contract



روش ممنوع:



دسترسی مستقیم و کنترل‌نشده به Model داخلی Domain دیگر.



\------------------------------------------------------------

15\. EVENT-DRIVEN FOUNDATION

\------------------------------------------------------------



Meryx باید Event Driven باشد.



دو نوع Event باید از ابتدا از نظر معماری تفکیک شوند:



Domain Event

Application Event



Eventها باید:



\- نام مشخص داشته باشند.

\- Version داشته باشند.

\- Producer مشخص داشته باشند.

\- Consumer مشخص داشته باشند.

\- Payload Contract مشخص داشته باشند.

\- قابلیت Audit داشته باشند.



Event schema نباید به implementation داخلی یک Django Model وابسته باشد.



\------------------------------------------------------------

16\. SYNCHRONOUS VS ASYNCHRONOUS

\------------------------------------------------------------



Agent باید مشخص کند کدام عملیات:



Synchronous



و کدام عملیات:



Asynchronous



هستند.



Synchronous مناسب برای:



\- عملیات کوتاه

\- درخواست‌های مستقیم API

\- Validation

\- Queryهای سریع



Asynchronous مناسب برای:



\- ارسال Notification

\- پردازش فایل

\- AI Processing

\- گزارش‌گیری سنگین

\- Event Consumers

\- Integration Jobs

\- Background Processing



است.



انتخاب Async نباید بدون دلیل انجام شود.



\------------------------------------------------------------

17\. API ARCHITECTURE

\------------------------------------------------------------



Meryx API First است.



API باید:



\- Versioned

\- Documented

\- Consistent

\- Secure

\- Observable

\- Testable



باشد.



API نباید مستقیماً Business Logic را اجرا کند.



ساختار مفهومی:



Request

&#x20;  ↓

Authentication

&#x20;  ↓

Authorization

&#x20;  ↓

Validation

&#x20;  ↓

Application Use Case

&#x20;  ↓

Domain

&#x20;  ↓

Infrastructure

&#x20;  ↓

Response



\------------------------------------------------------------

18\. API VERSIONING

\------------------------------------------------------------



API باید از ابتدا قابلیت Versioning داشته باشد.



مثال:



/api/v1/



در آینده:



/api/v2/



نسخه جدید نباید بدون برنامه نسخه قبلی را بشکند.



Breaking Change باید:



\- Documented

\- Versioned

\- Tested



باشد.



\------------------------------------------------------------

19\. SECURITY ARCHITECTURE

\------------------------------------------------------------



Security باید Cross-Cutting Concern باشد.



لایه‌های Security:



Authentication

Authorization

Tenant Isolation

Permission Management

Secrets Management

Input Validation

Rate Limiting

Audit Logging

Security Monitoring



در Phase 02 فقط Architecture تعریف می‌شود.



پیاده‌سازی کامل Identity و Authorization در Phaseهای مربوط انجام خواهد شد.



\------------------------------------------------------------

20\. MULTI-TENANCY ARCHITECTURE

\------------------------------------------------------------



Meryx باید Multi-Tenant باشد.



Tenant باید یک Architectural Boundary مهم باشد.



هدف:



Tenant A

نباید بتواند داده Tenant B را مشاهده یا تغییر دهد.



Tenant Isolation باید در:



Application

Domain

Persistence

Authorization

API



در نظر گرفته شود.



Tenant filtering نباید فقط به Frontend وابسته باشد.



\------------------------------------------------------------

21\. TENANT CONTEXT

\------------------------------------------------------------



هر Request در معماری نهایی باید در صورت نیاز دارای:



Tenant Context



باشد.



Tenant Context باید بتواند مشخص کند:



\- Tenant

\- User

\- Organization Context

\- Permissions

\- Roles



در حال اجرای Request هستند.



Tenant Context نباید صرفاً یک Global Variable باشد.



\------------------------------------------------------------

22\. AUDIT ARCHITECTURE

\------------------------------------------------------------



اصل:



Everything is Auditable.



سیستم باید بتواند تغییرات مهم را ثبت کند.



Audit باید بتواند مشخص کند:



Who

What

When

Where

Why

Before

After



تا حد امکان.



Audit نباید صرفاً به:



created\_at

updated\_at



محدود شود.



\------------------------------------------------------------

23\. OBSERVABILITY

\------------------------------------------------------------



Meryx باید از ابتدا قابلیت:



Logging

Metrics

Tracing

Health Checks

Error Monitoring



را در Architecture پیش‌بینی کند.



هر Request مهم باید قابل Trace شدن باشد.



Correlation ID / Request ID باید در معماری دیده شود.



\------------------------------------------------------------

24\. CONFIGURATION ARCHITECTURE

\------------------------------------------------------------



Configuration باید از Code جدا باشد.



Configuration باید بتواند:



Development

Testing

Staging

Production



را پشتیبانی کند.



هیچ Secret نباید در Source Code باشد.



Configuration باید:



Explicit

Validated

Typed



باشد.



\------------------------------------------------------------

25\. STORAGE ARCHITECTURE

\------------------------------------------------------------



Storage باید Abstract باشد.



Application نباید مستقیماً به:



Local File System



وابسته شود.



باید امکان استفاده از:



Local Storage

Object Storage

Cloud Storage



وجود داشته باشد.



مثلاً:



StoragePort

&#x20;   ↓

LocalStorageAdapter

S3StorageAdapter

AzureStorageAdapter

...



جزئیات Provider نباید وارد Domain شود.



\------------------------------------------------------------

26\. CACHE ARCHITECTURE

\------------------------------------------------------------



Cache باید یک Infrastructure Concern باشد.



Business Logic نباید به Redis API وابسته باشد.



Cache باید:



\- Optional

\- Replaceable

\- Observable

\- Invalidatable



باشد.



\------------------------------------------------------------

27\. EXTERNAL INTEGRATION ARCHITECTURE

\------------------------------------------------------------



External Systems نباید مستقیماً وارد Domain شوند.



هر Integration باید Adapter داشته باشد.



مثال:



External System

&#x20;      ↓

Integration Adapter

&#x20;      ↓

Application Contract

&#x20;      ↓

Domain



نمونه Integrationهای آینده:



ERP

HR Systems

SCADA

WinCC

Email

SMS

AI Providers

Cloud Services

Payment

Identity Providers



\------------------------------------------------------------

28\. AI ARCHITECTURE

\------------------------------------------------------------



AI در Meryx یک Core Capability است.



اما Domainها نباید مستقیماً به یک AI Provider خاص وابسته شوند.



نباید:



Domain → OpenAI API



یا:



Domain → Local LLM



داشته باشیم.



باید:



AI Capability

&#x20;     ↓

AI Port

&#x20;     ↓

Provider Adapter



باشد.



Provider می‌تواند در آینده تغییر کند.



\------------------------------------------------------------

29\. EXTENSION ARCHITECTURE

\------------------------------------------------------------



Meryx باید قابل Extension باشد.



Extension می‌تواند:



\- Industry Pack

\- Plugin

\- Integration

\- AI Provider

\- Storage Provider

\- Notification Provider



باشد.



Core نباید برای هر Customer تغییر داده شود.



Configuration و Extension باید جایگزین Customer-specific forks شوند.



\------------------------------------------------------------

30\. OFFLINE ARCHITECTURE

\------------------------------------------------------------



Meryx باید Offline Ready باشد.



Offline Ready به معنی Offline-first بودن کل سیستم در Phase 02 نیست.



یعنی Architecture باید اجازه دهد Clientهای خاص بتوانند:



\- Data Cache

\- Local Queue

\- Sync

\- Conflict Resolution



داشته باشند.



جزئیات در Phaseهای بعدی طراحی خواهد شد.



\------------------------------------------------------------

31\. CLIENT ARCHITECTURE

\------------------------------------------------------------



Meryx باید چند Client را پشتیبانی کند:



Web

Mobile

Desktop

Agent

External API Client



Backend نباید به UI خاص وابسته باشد.



تمام Clientها باید از Contractهای رسمی API/Events استفاده کنند.



\------------------------------------------------------------

32\. COMMUNICATION ARCHITECTURE

\------------------------------------------------------------



Communication Platform در معماری کلان باید از ابتدا دیده شود.



Capabilities:



Direct Chat

Group Chat

Channels

Official Letters

Voice Call

Group Voice Call

Video Meeting

Screen Sharing

Presence

Recording

AI Meeting Summary



Technology candidates:



Django Channels

WebSocket

Redis

WebRTC



اما در Phase 02 فقط Boundary و Responsibility تعریف می‌شود.



Implementation در Phase Communication انجام خواهد شد.



\------------------------------------------------------------

33\. DOMAIN EVENTS VS INTEGRATION EVENTS

\------------------------------------------------------------



این دو نباید با هم اشتباه شوند.



Domain Event:



برای داخل Domain / Application Architecture.



Integration Event:



برای ارتباط با سیستم یا Module خارجی.



هر دو باید Contract مستقل داشته باشند.



\------------------------------------------------------------

34\. TRANSACTION BOUNDARY

\------------------------------------------------------------



Transaction باید بر اساس Use Case و Business Consistency تعریف شود.



نباید یک Transaction عظیم برای کل سیستم ایجاد شود.



Transaction Boundary باید:



Explicit

Testable

Documented



باشد.



\------------------------------------------------------------

35\. DATABASE ACCESS RULE

\------------------------------------------------------------



Database access باید کنترل‌شده باشد.



Domain نباید QuerySetهای Django را بشناسد.



Business Logic نباید در:



models.py

views.py

serializers.py



پخش شود.



Django Model می‌تواند Persistence Representation باشد،

اما نباید به صورت خودکار معادل Domain Model فرض شود.



\------------------------------------------------------------

36\. DJANGO USAGE RULE

\------------------------------------------------------------



Django Framework است، نه Architecture.



Meryx نباید:



Architecture = Django



فرض کند.



Django باید به عنوان Infrastructure / Framework استفاده شود.



در صورت تعارض:



Business Architecture

بر

Framework Convenience



اولویت دارد.



\------------------------------------------------------------

37\. DOCUMENTATION REQUIREMENTS

\------------------------------------------------------------



در پایان Phase 02 باید حداقل اسناد زیر وجود داشته باشند:



docs/

│

├── architecture/

│   ├── system\_architecture.md

│   ├── layer\_architecture.md

│   ├── module\_architecture.md

│   ├── dependency\_rules.md

│   ├── security\_architecture.md

│   ├── multi\_tenancy\_architecture.md

│   ├── event\_architecture.md

│   ├── integration\_architecture.md

│   ├── ai\_architecture.md

│   └── extension\_architecture.md

│

└── adr/

&#x20;   ├── ADR-001-...

&#x20;   ├── ADR-002-...

&#x20;   └── ...



نام دقیق فایل‌ها می‌تواند متفاوت باشد،

اما محتوای مورد نیاز باید وجود داشته باشد.



\------------------------------------------------------------

38\. ADR REQUIREMENTS

\------------------------------------------------------------



حداقل ADRهای Phase 02:



ADR-001:

Meryx as Enterprise Operations Platform



ADR-002:

Modular Monolith Architecture



ADR-003:

Clean Architecture



ADR-004:

Domain Driven Design



ADR-005:

API First Architecture



ADR-006:

Event Driven Architecture



ADR-007:

Multi-Tenant Architecture



ADR-008:

Security First Architecture



ADR-009:

AI Native Architecture



ADR-010:

Extension / Plugin Strategy



ADR-011:

Database Strategy



ADR-012:

Integration Strategy



ADR-013:

Observability Strategy



ADR-014:

Configuration Strategy



ADR-015:

Cloud Ready Strategy



ADR-016:

Offline Ready Strategy



اگر تصمیمی قبلاً در Phase 01 ثبت شده باشد،

Agent نباید ADR متناقض ایجاد کند.



\------------------------------------------------------------

39\. ARCHITECTURE DIAGRAMS

\------------------------------------------------------------



حداقل Diagramهای زیر باید ایجاد شوند:



1\. System Context Diagram



2\. Container Diagram



3\. Layer Diagram



4\. Module Boundary Diagram



5\. Dependency Diagram



6\. Event Flow Diagram



7\. Multi-Tenant Isolation Diagram



8\. API Request Flow



9\. Authentication Flow



10\. Integration Flow



11\. AI Architecture Diagram



12\. Extension Architecture Diagram



Diagramها باید قابل نگهداری باشند.



ترجیحاً از Mermaid یا ابزار Version-Control-Friendly استفاده شود.



\------------------------------------------------------------

40\. ARCHITECTURE MATRIX

\------------------------------------------------------------



Agent باید یک Matrix ایجاد کند.



مثال:



Module

Responsibility

Owns Data

Consumes

Produces

Depends On

Exposes



برای تمام Capabilityهای اصلی.



حداقل:



Platform Core

Identity

Organization

People

Projects

Tasks

Assets

Devices

Maintenance

Documents

Workflow

Communication

Notifications

Analytics

AI

Integration Hub



\------------------------------------------------------------

41\. DEPENDENCY MATRIX

\------------------------------------------------------------



یک Dependency Matrix ایجاد شود.



مثلاً:



Identity → Platform Core

Organization → Identity + Platform Core

Projects → Organization + Identity

Tasks → Projects + Identity

...



اما Dependencyها نباید حدسی باشند.



اگر Dependency هنوز قطعی نیست:



STATUS = TO BE DECIDED



و باید ADR یا Design Decision ایجاد شود.



\------------------------------------------------------------

42\. ARCHITECTURAL RULES TO ENFORCE

\------------------------------------------------------------



حداقل قوانین:



RULE A:

Domain cannot depend on Infrastructure.



RULE B:

Domain cannot depend on HTTP.



RULE C:

Domain cannot depend on Django Views.



RULE D:

Domain cannot depend on external providers.



RULE E:

Modules cannot access another module's private implementation.



RULE F:

Cross-module communication must use explicit contracts.



RULE G:

Business logic cannot live in serializers.



RULE H:

Business logic cannot live in views.



RULE I:

Secrets cannot exist in source code.



RULE J:

Tenant isolation must be enforced server-side.



RULE K:

Every public API must be versioned.



RULE L:

Every important event must have a contract.



RULE M:

Every architectural decision must be documented.



RULE N:

No architecture shortcut without documented justification.



\------------------------------------------------------------

43\. REQUIRED FILE CREATION COMMAND

\------------------------------------------------------------



Agent باید قبل از ایجاد فایل‌ها ابتدا Repository را بررسی کند.



ممنوع:



فرض کردن اینکه فایل وجود ندارد.



ابتدا:



Directory Inspection

File Inspection

Configuration Inspection

Git Inspection



انجام شود.



سپس فایل‌های لازم ایجاد شوند.



\------------------------------------------------------------

44\. IMPLEMENTATION ORDER

\------------------------------------------------------------



ترتیب اجرای Phase 02:



STEP 01:

Inspect Phase 01.



STEP 02:

Validate Foundation.



STEP 03:

Create Architecture Documentation.



STEP 04:

Define Layers.



STEP 05:

Define Module Boundaries.



STEP 06:

Define Dependency Rules.



STEP 07:

Define Event Architecture.



STEP 08:

Define Multi-Tenancy Architecture.



STEP 09:

Define Security Architecture.



STEP 10:

Define Integration Architecture.



STEP 11:

Define AI Architecture.



STEP 12:

Define Extension Architecture.



STEP 13:

Create Architecture Diagrams.



STEP 14:

Create ADRs.



STEP 15:

Create Architecture Matrix.



STEP 16:

Create Dependency Matrix.



STEP 17:

Review for contradictions.



STEP 18:

Run Architecture Tests where possible.



STEP 19:

Run Quality Gate.



STEP 20:

Execute Phase Exit Gate.



\------------------------------------------------------------

45\. WHAT MUST NOT HAPPEN

\------------------------------------------------------------



در Phase 02 نباید:



\- 300 Entity ساخته شود.

\- ERD نهایی ساخته شود.

\- Business Modelهای کامل ساخته شوند.

\- HR implementation انجام شود.

\- Project implementation انجام شود.

\- Task implementation انجام شود.

\- Chat implementation انجام شود.

\- WebRTC implementation انجام شود.

\- AI provider implementation انجام شود.

\- JWT implementation کامل شود.

\- Frontend implementation گسترده انجام شود.

\- Database schema نهایی ایجاد شود.



Phase 02 درباره:



ARCHITECTURE



است، نه Feature Development.



\------------------------------------------------------------

46\. DEFINITION OF DONE

\------------------------------------------------------------



Phase 02 فقط زمانی Complete است که:



\[ ] System Architecture مشخص شده.



\[ ] Layer Architecture مشخص شده.



\[ ] Module Boundaries مشخص شده.



\[ ] Dependency Rules مشخص شده.



\[ ] Domain/Application/Infrastructure responsibilities مشخص شده.



\[ ] Multi-Tenancy Architecture مشخص شده.



\[ ] Security Architecture مشخص شده.



\[ ] Event Architecture مشخص شده.



\[ ] API Architecture مشخص شده.



\[ ] Integration Architecture مشخص شده.



\[ ] AI Architecture مشخص شده.



\[ ] Extension Architecture مشخص شده.



\[ ] Storage Architecture مشخص شده.



\[ ] Configuration Architecture مشخص شده.



\[ ] Observability Architecture مشخص شده.



\[ ] Offline Strategy مشخص شده.



\[ ] Client Architecture مشخص شده.



\[ ] Architecture Diagrams ایجاد شده.



\[ ] Architecture Matrix ایجاد شده.



\[ ] Dependency Matrix ایجاد شده.



\[ ] ADRها ایجاد شده‌اند.



\[ ] تناقض معماری وجود ندارد.



\[ ] Documentation قابل فهم و قابل اجراست.



\[ ] Architecture Tests در صورت امکان اجرا شده‌اند.



\[ ] Phase 01 همچنان GREEN است.



\------------------------------------------------------------

47\. PHASE EXIT GATE

\------------------------------------------------------------



برای عبور از Phase 02:



Architecture Review = PASS



Documentation Review = PASS



Dependency Review = PASS



Security Architecture Review = PASS



Multi-Tenant Review = PASS



Extension Review = PASS



ADR Review = PASS



Quality Gate = GREEN



اگر هرکدام FAIL باشد:



STATUS = BLOCKED



Agent نباید Phase 03 را شروع کند.



\------------------------------------------------------------

48\. FINAL REPORT FORMAT

\------------------------------------------------------------



Agent در پایان Phase 02 باید دقیقاً این موارد را گزارش کند:



PHASE:

02



STATUS:

COMPLETED / BLOCKED



FILES CREATED:



ARCHITECTURE DECISIONS:



ADR CREATED:



MODULES DEFINED:



DEPENDENCY RULES:



EVENT STRATEGY:



SECURITY STRATEGY:



MULTI-TENANCY STRATEGY:



AI STRATEGY:



EXTENSION STRATEGY:



DIAGRAMS CREATED:



TESTS RUN:



QUALITY CHECKS:



KNOWN ISSUES:



OPEN QUESTIONS:



NEXT PHASE:



PHASE 03 — DOMAIN ARCHITECTURE



Agent حق ندارد فقط بنویسد:



"Phase 02 completed."



باید Evidence ارائه کند.



\------------------------------------------------------------

49\. NEXT PHASE

\------------------------------------------------------------



بعد از موفقیت کامل Phase 02:



NEXT:



PHASE 03 — DOMAIN ARCHITECTURE



Phase 03 شامل:



\- Bounded Contexts

\- Domain Map

\- Capability Map

\- Aggregates

\- Entities

\- Value Objects

\- Domain Services

\- Domain Events

\- Invariants

\- Domain Relationships

\- Context Mapping

\- Ownership Rules



خواهد بود.



Phase 03 نقطه‌ای است که وارد طراحی واقعی Domain Model می‌شویم.



اما حتی در Phase 03 نیز تا زمانی که Domain Architecture تأیید نشده،

نباید به صورت بی‌قاعده Django Model تولید شود.



============================================================

END OF PHASE 02

============================================================

