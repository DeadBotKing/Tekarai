============================================================

MERYX ENTERPRISE PLATFORM

PHASE 3 — DOMAIN ARCHITECTURE

============================================================



STATUS:

PLANNING / DESIGN ONLY



IMPORTANT:

در این فاز هنوز هیچ Model، Migration، API یا کد Business Logic

پیاده‌سازی نشود.



هدف این فاز:

تبدیل Business Capability Map فاز 2 به یک Domain Architecture

شفاف، قابل پیاده‌سازی و قابل توسعه برای 5 تا 10 سال آینده.



============================================================

1\. OBJECTIVE

============================================================



در پایان Phase 3 باید دقیقاً مشخص باشد:



1\. چه Domainهایی در Meryx وجود دارند.

2\. هر Domain چه مسئولیتی دارد.

3\. هر Domain چه چیزهایی را مالک است.

4\. کدام Domainها Core هستند.

5\. کدام Domainها Supporting هستند.

6\. کدام Domainها Generic هستند.

7\. مرز هر Bounded Context کجاست.

8\. Aggregateهای اصلی هر Domain چیست.

9\. Entityهای اصلی هر Aggregate چیست.

10\. Value Objectهای اصلی چیست.

11\. Domain Eventهای اصلی چیست.

12\. وابستگی Domainها به یکدیگر چگونه است.

13\. چه Domainهایی اجازه دارند مستقیماً به یکدیگر وابسته شوند.

14\. چه Domainهایی باید از Event Bus استفاده کنند.

15\. کدام اطلاعات باید در اختیار Domainهای دیگر قرار گیرد.

16\. کدام اطلاعات نباید از مرز Domain خارج شود.

17\. ساختار آینده Django Apps بر اساس این Domain Boundaries چگونه خواهد بود.



============================================================

2\. ARCHITECTURAL PRINCIPLE

============================================================



Meryx یک Modular Monolith Enterprise است.



معماری باید:



\- DDD

\- Clean Architecture

\- SOLID

\- Domain Driven Design

\- Bounded Context

\- Aggregate

\- Domain Event

\- Application Service

\- Domain Service

\- Repository Pattern

\- Dependency Inversion



را رعایت کند.



قانون اصلی:



Business Domain نباید به Django وابسته باشد.



Django یک Infrastructure / Delivery Framework است.



Business Rule نباید داخل:



\- View

\- Serializer

\- URL

\- Django Admin

\- Model.save()

\- Signal

\- HTTP Handler



قرار گیرد.



============================================================

3\. DOMAIN CLASSIFICATION

============================================================



تمام Domainهای Meryx باید در یکی از سه گروه زیر قرار گیرند.



\------------------------------------------------------------

3.1 GENERIC SUBDOMAIN

\------------------------------------------------------------



قابلیت‌هایی که تقریباً در هر Enterprise Platform وجود دارند.



نمونه:



Identity

Authentication

Authorization

Notification

Audit

File Management

Configuration



این بخش‌ها نباید منطق صنعت خاص داشته باشند.



\------------------------------------------------------------

3.2 SUPPORTING SUBDOMAIN

\------------------------------------------------------------



قابلیت‌هایی که برای Meryx مهم هستند اما مزیت اصلی محصول نیستند.



نمونه:



Documents

Reporting

Dashboard

Communication

Device Management

Integration



\------------------------------------------------------------

3.3 CORE DOMAIN

\------------------------------------------------------------



قابلیت‌هایی که ارزش اصلی Meryx را ایجاد می‌کنند.



Core Domain باید قابل توسعه و قابل هوشمندسازی باشد.



نمونه:



Organization Management

Workforce Management

Performance Management

Project Operations

Workflow

AI Intelligence

Enterprise Operations Intelligence



============================================================

4\. BOUNDED CONTEXTS

============================================================



Meryx باید حداقل Contextهای زیر را داشته باشد.



\------------------------------------------------------------

CONTEXT 01 — IDENTITY

\------------------------------------------------------------



مسئول:



\- User

\- Authentication

\- Credentials

\- Sessions

\- Roles

\- Permissions

\- Access Policies

\- Security Identity



مالک Identity است.



نباید مالک Employee باشد.



Employee متعلق به Workforce / HR Domain است.



\------------------------------------------------------------

CONTEXT 02 — TENANCY

\------------------------------------------------------------



مسئول:



\- Tenant

\- Tenant Configuration

\- Tenant Lifecycle

\- Tenant Isolation

\- Tenant Membership



قانون:



تمام داده‌های Tenant-aware باید Tenant Boundary داشته باشند.



\------------------------------------------------------------

CONTEXT 03 — ORGANIZATION

\------------------------------------------------------------



مسئول:



\- Organization

\- Legal Entity

\- Business Unit

\- Department

\- Division

\- Team

\- Organizational Hierarchy

\- Positions



Organization نباید مسئول اطلاعات شخصی Employee باشد.



\------------------------------------------------------------

CONTEXT 04 — WORKFORCE / HR

\------------------------------------------------------------



مسئول:



\- Employee

\- Employment

\- Contract

\- Job

\- Position Assignment

\- Attendance

\- Leave

\- Skills

\- Employee Lifecycle



Employee با User یکی نیست.



رابطه:



User = Identity



Employee = Workforce Person / Employment Record



\------------------------------------------------------------

CONTEXT 05 — PERFORMANCE

\------------------------------------------------------------



مسئول:



\- Performance Cycle

\- KPI

\- Evaluation

\- Evaluation Criteria

\- Reviewer

\- Reviewer Weight

\- Score

\- Performance Result

\- Performance History



قوانین:



چند مدیر می‌توانند یک Employee را ارزیابی کنند.



هر Evaluator می‌تواند Weight داشته باشد.



Score باید قابل اصلاح باشد.



تمام اصلاحات باید Audit شوند.



\------------------------------------------------------------

CONTEXT 06 — PROJECT

\------------------------------------------------------------



مسئول:



\- Project

\- Project Member

\- Project Phase

\- Project Milestone

\- Project Budget

\- Project Status

\- Project Risk



Project نباید Task implementation را مستقیماً مالک شود اگر Task

به عنوان Context مستقل تعریف شده باشد.



\------------------------------------------------------------

CONTEXT 07 — TASK / WORK MANAGEMENT

\------------------------------------------------------------



مسئول:



\- Task

\- Subtask

\- Assignment

\- Priority

\- Status

\- Deadline

\- Dependency

\- Checklist

\- Task Comment

\- Task Activity



Task می‌تواند متعلق به Project باشد.



اما Task Domain باید مستقل باقی بماند.



\------------------------------------------------------------

CONTEXT 08 — ASSET

\------------------------------------------------------------



مسئول:



\- Asset

\- Asset Type

\- Asset Category

\- Ownership

\- Assignment

\- Lifecycle

\- Asset Status



\------------------------------------------------------------

CONTEXT 09 — DEVICE / OT

\------------------------------------------------------------



مسئول:



\- Device

\- Device Type

\- Device Registration

\- Device Health

\- Telemetry

\- Device Connection

\- Industrial Connector



قابلیت‌هایی مانند WinCC نباید Core Domain را آلوده کنند.



WinCC باید Integration / Industry Extension باشد.



\------------------------------------------------------------

CONTEXT 10 — MAINTENANCE

\------------------------------------------------------------



مسئول:



\- Maintenance Plan

\- Preventive Maintenance

\- Corrective Maintenance

\- Work Order

\- Maintenance Schedule

\- Maintenance History



Maintenance می‌تواند با Asset و Device Integration داشته باشد.



\------------------------------------------------------------

CONTEXT 11 — DOCUMENT

\------------------------------------------------------------



مسئول:



\- Document

\- Document Version

\- Folder

\- Metadata

\- Document Permission

\- Document Lifecycle

\- Document Relation



\------------------------------------------------------------

CONTEXT 12 — WORKFLOW

\------------------------------------------------------------



مسئول:



\- Workflow Definition

\- Workflow Version

\- Workflow Instance

\- Workflow Step

\- Approval

\- Approval Assignment

\- Workflow Transition



Workflow باید Generic باشد.



نباید به یک Business Domain خاص Hard-Code شود.



\------------------------------------------------------------

CONTEXT 13 — COMMUNICATION

\------------------------------------------------------------



مسئول:



\- Direct Chat

\- Group Chat

\- Channel

\- Message

\- Conversation

\- Participant

\- Presence

\- Call

\- Meeting



قابلیت‌های:



\- Voice Call

\- Group Voice Call

\- Video Meeting

\- Screen Sharing

\- Recording



باید در همین Context مدیریت شوند.



\------------------------------------------------------------

CONTEXT 14 — NOTIFICATION

\------------------------------------------------------------



مسئول:



\- Notification

\- Notification Template

\- Delivery

\- Channel

\- User Preference

\- Notification History



Notification باید Event-driven باشد.



مثال:



TaskAssigned

&#x20;       ↓

Event Bus

&#x20;       ↓

Notification Handler



\------------------------------------------------------------

CONTEXT 15 — AUDIT

\------------------------------------------------------------



مسئول:



\- Audit Event

\- Actor

\- Action

\- Entity

\- Previous State

\- New State

\- Timestamp

\- Correlation ID

\- IP / Client Metadata



Audit باید Append-Only باشد.



Audit نباید با Business CRUD مخلوط شود.



\------------------------------------------------------------

CONTEXT 16 — REPORTING / ANALYTICS

\------------------------------------------------------------



مسئول:



\- Reports

\- Report Definitions

\- Dashboards

\- Metrics

\- KPIs

\- Aggregations

\- Analytical Views



Reporting نباید مالک Transactional Data باشد.



داده را از Domainها دریافت می‌کند.



\------------------------------------------------------------

CONTEXT 17 — AI / INTELLIGENCE

\------------------------------------------------------------



مسئول:



\- AI Model Registry

\- AI Provider

\- AI Job

\- AI Prediction

\- AI Recommendation

\- AI Analysis

\- AI Prompt

\- AI Knowledge

\- Knowledge Graph

\- AI Feedback



AI باید Consumer اطلاعات Domainها باشد.



AI نباید مالک Business Truth شود.



\------------------------------------------------------------

CONTEXT 18 — INTEGRATION

\------------------------------------------------------------



مسئول:



\- Integration

\- Connector

\- External System

\- API Credential

\- Webhook

\- Sync Job

\- Integration Event

\- Mapping



تمام Integrationهای خارجی باید از طریق این Boundary انجام شوند.



مثال:



WinCC

ERP

MES

Email

SMS

External HR

External AI

External Storage



\------------------------------------------------------------

CONTEXT 19 — CONFIGURATION

\------------------------------------------------------------



مسئول:



\- System Configuration

\- Tenant Configuration

\- Feature Flags

\- Policies

\- Runtime Settings



Configuration باید از Hard Coding جلوگیری کند.



\------------------------------------------------------------

CONTEXT 20 — PLATFORM CORE

\------------------------------------------------------------



مسئول:



\- Domain primitives

\- Base abstractions

\- Domain Event infrastructure

\- Result

\- Error

\- Identifier

\- Clock

\- Correlation

\- Tenant Context

\- Security Context



Platform Core نباید Business Domain Logic داشته باشد.



============================================================

5\. DOMAIN DEPENDENCY RULE

============================================================



Dependency Direction:



Presentation

&#x20;   ↓

Application

&#x20;   ↓

Domain

&#x20;   ↑

Infrastructure



Domain نباید به Infrastructure وابسته باشد.



\------------------------------------------------------------



بین Bounded Contextها:



مستقیم:



Domain A

&#x20;   ↓

Domain B



فقط زمانی مجاز است که Dependency واقعاً جزء Contract معماری باشد.



در حالت عمومی:



Domain A

&#x20;   ↓

Domain Event

&#x20;   ↓

Event Bus

&#x20;   ↓

Domain B



استفاده شود.



============================================================

6\. AGGREGATE RULES

============================================================



هر Aggregate باید:



\- Root داشته باشد.

\- Boundary مشخص داشته باشد.

\- Invariantهای خودش را کنترل کند.

\- از خارج مستقیماً Child Entity را قابل تغییر نکند.

\- Transaction Boundary مشخص داشته باشد.



مثال:



PerformanceEvaluation

&#x20;   ├── EvaluationReviewer

&#x20;   ├── EvaluationScore

&#x20;   └── EvaluationResult



PerformanceEvaluation = Aggregate Root



نباید:



EvaluationScore

را مستقل و بدون کنترل Aggregate تغییر داد.



============================================================

7\. ENTITY RULE

============================================================



Entity دارای Identity پایدار است.



نمونه:



User

Employee

Project

Task

Asset

Document

WorkflowInstance



Identity نباید صرفاً بر اساس Name باشد.



Meryx از UUID به عنوان Primary Identifier استفاده می‌کند.



============================================================

8\. VALUE OBJECT RULE

============================================================



Value Object Identity مستقل ندارد.



نمونه:



EmailAddress

PhoneNumber

Money

Address

DateRange

Percentage

Score

Coordinates

FileSize

Duration



Value Object باید:



\- Immutable

\- Validated

\- Side-effect free



باشد.



============================================================

9\. DOMAIN EVENT RULE

============================================================



Business Eventها باید Explicit باشند.



نمونه:



UserRegistered

EmployeeHired

EmployeeTerminated

ProjectCreated

TaskAssigned

TaskCompleted

PerformanceEvaluationSubmitted

PerformanceEvaluationChanged

DocumentApproved

WorkflowStarted

WorkflowCompleted

AssetAssigned

MaintenanceRequired

DeviceOffline

MeetingStarted

MeetingEnded



Event باید شامل حداقل:



\- Event ID

\- Event Type

\- Aggregate ID

\- Tenant ID

\- Occurred At

\- Correlation ID

\- Actor ID

\- Version



باشد.



============================================================

10\. CROSS DOMAIN EXAMPLE

============================================================



مثال:



Employee

&#x20;   ↓

Performance Evaluation

&#x20;   ↓

PerformanceEvaluationSubmitted

&#x20;   ↓

Event Bus

&#x20;   ├── Audit

&#x20;   ├── Notification

&#x20;   ├── Analytics

&#x20;   └── AI



Performance Domain نباید مستقیماً:



NotificationService

AuditService

AIService



را صدا بزند.



هر Context باید مستقل بماند.



============================================================

11\. TENANT BOUNDARY

============================================================



Meryx از ابتدا Multi-Tenant طراحی می‌شود.



Tenant باید Boundary امنیتی باشد.



هر Aggregate که Tenant-owned است باید Tenant Context داشته باشد.



هیچ Query نباید بتواند بدون دلیل معتبر داده Tenant دیگر را مشاهده کند.



Tenant Isolation باید در:



\- Application Layer

\- Repository Layer

\- Database Layer



تا حد امکان enforce شود.



============================================================

12\. SECURITY BOUNDARY

============================================================



Identity مسئول Authentication است.



Authorization باید بر اساس:



\- User

\- Role

\- Permission

\- Policy

\- Resource

\- Tenant

\- Organization Scope



انجام شود.



نباید فقط:



if user.is\_superuser



استفاده شود.



============================================================

13\. DOMAIN VS DJANGO APP

============================================================



Django App الزاماً معادل Domain نیست.



اما برای Modular Monolith:



هر Bounded Context ترجیحاً یک Module مستقل داشته باشد.



مثال:



apps/

&#x20;   identity/

&#x20;   tenancy/

&#x20;   organization/

&#x20;   workforce/

&#x20;   performance/

&#x20;   projects/

&#x20;   tasks/

&#x20;   assets/

&#x20;   devices/

&#x20;   maintenance/

&#x20;   documents/

&#x20;   workflow/

&#x20;   communication/

&#x20;   notifications/

&#x20;   audit/

&#x20;   analytics/

&#x20;   ai/

&#x20;   integrations/

&#x20;   configuration/

&#x20;   platform/



هر Module باید Boundary مشخص داشته باشد.



============================================================

14\. INTERNAL MODULE STRUCTURE

============================================================



ساختار پیشنهادی هر Domain:



domain\_name/



&#x20;   domain/

&#x20;       entities/

&#x20;       value\_objects/

&#x20;       aggregates/

&#x20;       events/

&#x20;       services/

&#x20;       repositories/

&#x20;       exceptions/



&#x20;   application/

&#x20;       commands/

&#x20;       queries/

&#x20;       services/

&#x20;       dto/

&#x20;       handlers/



&#x20;   infrastructure/

&#x20;       persistence/

&#x20;       repositories/

&#x20;       integrations/



&#x20;   presentation/

&#x20;       api/

&#x20;       serializers/

&#x20;       views/



این ساختار باید قبل از پیاده‌سازی نهایی بررسی شود.



============================================================

15\. BUSINESS LOGIC RULE

============================================================



Business Logic در:



Domain Layer



Application orchestration در:



Application Layer



Database access در:



Infrastructure Layer



HTTP در:



Presentation Layer



قرار می‌گیرد.



مثال:



BAD:



View

&#x20;   ↓

Model.save()

&#x20;   ↓

Business Logic



GOOD:



API

&#x20;   ↓

Application Command

&#x20;   ↓

Domain Aggregate

&#x20;   ↓

Domain Event

&#x20;   ↓

Repository

&#x20;   ↓

Infrastructure



============================================================

16\. TRANSACTION RULE

============================================================



Transaction Boundary باید با Aggregate Boundary هماهنگ باشد.



از Transactionهای بسیار بزرگ جلوگیری شود.



یک Business Operation نباید بدون دلیل چندین Aggregate و چندین

Bounded Context را در یک Transaction دیتابیسی قفل کند.



برای عملیات Cross-Domain از Eventual Consistency استفاده شود

در مواردی که Business Rule اجازه می‌دهد.



============================================================

17\. DOMAIN SERVICE

============================================================



Domain Service زمانی استفاده شود که:



Business Rule متعلق به یک Entity یا Aggregate مشخص نیست.



مثال:



PerformanceScoreCalculationService



اگر منطق فقط متعلق به:



PerformanceEvaluation



است، باید داخل Aggregate / Domain Object قرار گیرد.



Domain Service نباید به یک Service Layer عمومی برای همه چیز تبدیل شود.



============================================================

18\. REPOSITORY RULE

============================================================



Repository متعلق به Domain Contract است.



مثال:



EmployeeRepository

ProjectRepository

TaskRepository



Domain باید Interface را تعریف کند.



Infrastructure implementation را فراهم می‌کند.



مثال:



Domain:



IProjectRepository



Infrastructure:



SqlServerProjectRepository



============================================================

19\. AI BOUNDARY

============================================================



AI اجازه ندارد Business Entity را مستقیماً تغییر دهد مگر از طریق

Application Contract معتبر.



مثال:



AI Recommendation

&#x20;   ↓

Recommendation Review

&#x20;   ↓

Business Decision

&#x20;   ↓

Application Command

&#x20;   ↓

Domain



AI نباید:



AI

&#x20;   ↓

Database UPDATE



انجام دهد.



============================================================

20\. INTEGRATION BOUNDARY

============================================================



External System:



WinCC

ERP

MES

Email

SMS

External Storage



نباید مستقیماً به Domain داخلی دسترسی داشته باشد.



مسیر صحیح:



External System

&#x20;   ↓

Integration Adapter

&#x20;   ↓

Integration Application Layer

&#x20;   ↓

Domain Command / Event



============================================================

21\. ARCHITECTURAL RULES

============================================================



Rule 01:

هیچ Domain به Database Schema Domain دیگر وابسته نشود.



Rule 02:

هیچ Domain مستقیماً Model داخلی Domain دیگر را Import نکند.



Rule 03:

Cross-Domain Communication باید از Contract یا Event انجام شود.



Rule 04:

Business Rule داخل View نوشته نشود.



Rule 05:

Business Rule داخل Serializer نوشته نشود.



Rule 06:

Business Rule داخل Signal نوشته نشود.



Rule 07:

Infrastructure نباید وارد Domain شود.



Rule 08:

AI نباید Business Truth را مالک شود.



Rule 09:

Audit باید مستقل باشد.



Rule 10:

Tenant Isolation از ابتدا طراحی شود.



Rule 11:

External Integration فقط از Integration Boundary عبور کند.



Rule 12:

هر Aggregate باید Invariantهای خود را enforce کند.



Rule 13:

هر Event باید Versionable باشد.



Rule 14:

هر عملیات حساس باید قابل Audit باشد.



Rule 15:

هیچ Domain نباید به Domain داخلی دیگری دسترسی مستقیم به

Database داشته باشد.



============================================================

22\. DOMAIN MAP

============================================================



&#x20;                   PLATFORM CORE

&#x20;                         |

&#x20;       +-----------------+-----------------+

&#x20;       |                 |                 |

&#x20;    TENANCY          IDENTITY        CONFIGURATION

&#x20;       |

&#x20;  ORGANIZATION

&#x20;       |

&#x20;   WORKFORCE

&#x20;       |

&#x20;+------+------+----------------+

&#x20;|             |                |

PERFORMANCE  PROJECT          ASSET

&#x20;              |                |

&#x20;            TASK            DEVICE

&#x20;                               |

&#x20;                         MAINTENANCE



Supporting Domains:



DOCUMENT

WORKFLOW

COMMUNICATION

NOTIFICATION

AUDIT

ANALYTICS

INTEGRATION



Cross-Cutting Intelligence:



AI / INTELLIGENCE



============================================================

23\. INDUSTRY EXTENSION RULE

============================================================



Meryx نباید برای یک صنعت خاص Hard-Code شود.



مثلاً:



Pharmaceutical

Manufacturing

Construction

Oil \& Gas

Retail

Healthcare

Technology



باید بتوانند روی Core Meryx ساخته شوند.



مثال:



Meryx Core

&#x20;   +

Manufacturing Pack



یا:



Meryx Core

&#x20;   +

Pharmaceutical Pack



یا:



Meryx Core

&#x20;   +

Industrial Automation Pack



WinCC نباید جزء Core Platform باشد.



WinCC یک Integration / Industry Extension است.



============================================================

24\. خروجی اجباری PHASE 3

============================================================



قبل از رفتن به Phase 4 باید فایل‌های زیر تولید شوند:



docs/architecture/

&#x20;   DOMAIN\_ARCHITECTURE.md

&#x20;   DOMAIN\_MAP.md

&#x20;   BOUNDED\_CONTEXTS.md

&#x20;   DOMAIN\_DEPENDENCIES.md

&#x20;   AGGREGATE\_CATALOG.md

&#x20;   DOMAIN\_EVENTS.md

&#x20;   VALUE\_OBJECT\_CATALOG.md

&#x20;   DOMAIN\_RULES.md



============================================================

25\. ACCEPTANCE CRITERIA

============================================================



Phase 3 فقط زمانی COMPLETE است که:



\[ ] تمام Bounded Contextها مشخص شده باشند.



\[ ] مسئولیت هر Context مشخص باشد.



\[ ] Core / Supporting / Generic مشخص شده باشد.



\[ ] Aggregateهای اصلی مشخص شده باشند.



\[ ] Aggregate Rootها مشخص شده باشند.



\[ ] Value Objectهای اصلی مشخص شده باشند.



\[ ] Domain Eventهای اصلی مشخص شده باشند.



\[ ] Dependency Graph مشخص شده باشد.



\[ ] Tenant Boundary مشخص شده باشد.



\[ ] Security Boundary مشخص شده باشد.



\[ ] Integration Boundary مشخص شده باشد.



\[ ] AI Boundary مشخص شده باشد.



\[ ] Industry Extension Strategy مشخص شده باشد.



\[ ] Domain Rules مستند شده باشند.



\[ ] هیچ Business Logic مهمی خارج از Domain قرار نگرفته باشد.



\[ ] Architecture بدون نیاز به Django قابل توضیح باشد.



\[ ] Architecture برای Modular Monolith مناسب باشد.



\[ ] مسیر احتمالی استخراج آینده بعضی Contextها به Microservice

مشخص باشد.



============================================================

26\. ممنوعیت‌های PHASE 3

============================================================



در این فاز ممنوع است:



\- ساخت Migration

\- ساخت Database Table

\- ساخت API

\- ساخت Serializer

\- ساخت View

\- ساخت Django Model

\- اتصال Business Logic به Django

\- شروع CRUD

\- ایجاد Foreign Key صرفاً برای راحتی

\- طراحی Database بدون Domain Boundary

\- Hard-Code کردن Industry Logic

\- ساخت Microservice بدون نیاز واقعی



============================================================

27\. خروجی نهایی

============================================================



در پایان Phase 3 باید بتوانیم با یک نگاه بفهمیم:



Meryx چه Domainهایی دارد؟



هر Domain چه چیزی را مالک است؟



Aggregateهای آن چیست؟



چه Eventهایی تولید می‌کند؟



به چه Domainهایی وابسته است؟



چه Domainهایی به آن وابسته‌اند؟



چه داده‌ای از مرز آن خارج می‌شود؟



چه داده‌ای نباید خارج شود؟



و در نهایت:



چگونه این Domain Architecture در Phase 4

به Enterprise ERD تبدیل خواهد شد؟



============================================================

END OF PHASE 3

============================================================

