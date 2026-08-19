╔══════════════════════════════════════════════════════════════════════════════╗

║                              TEKARAI — PHASE 06                              ║

║                    API ARCHITECTURE \& APPLICATION LAYER                     ║

╚══════════════════════════════════════════════════════════════════════════════╝



هدف فاز:

طراحی و پیاده‌سازی لایه Application و API به‌صورت Enterprise Grade،

به‌گونه‌ای که Domain Logic مستقیماً به Django View، Serializer یا HTTP

وابسته نباشد.



این فاز بعد از تکمیل:

\- Architecture Foundation

\- Business Capability Map

\- Domain Architecture

\- Enterprise ERD

\- Database Architecture



اجرا می‌شود.



──────────────────────────────────────────────────────────────────────────────

1\. هدف اصلی فاز

──────────────────────────────────────────────────────────────────────────────



در این فاز باید مرز بین موارد زیر کاملاً مشخص و enforce شود:



Client

&#x20; ↓

API

&#x20; ↓

Application

&#x20; ↓

Domain

&#x20; ↓

Infrastructure

&#x20; ↓

Database / External Systems



هیچ View نباید Business Logic اصلی را اجرا کند.



هیچ Serializer نباید Business Rule را مالک باشد.



هیچ Model نباید مسئول اجرای Use Case باشد.



Application Layer مالک Use Caseها است.



Domain Layer مالک Business Ruleها است.



Infrastructure Layer مالک ارتباط با Database و External Services است.





──────────────────────────────────────────────────────────────────────────────

2\. معماری نهایی

──────────────────────────────────────────────────────────────────────────────



&#x20;                        ┌──────────────────────┐

&#x20;                        │      Web Client      │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │     Mobile Client    │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │     Desktop Client   │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │      API Layer       │

&#x20;                        │ REST / WebSocket     │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │ Application Layer    │

&#x20;                        │ Commands / Queries   │

&#x20;                        │ Use Cases             │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │    Domain Layer      │

&#x20;                        │ Entities / Rules     │

&#x20;                        │ Value Objects        │

&#x20;                        │ Domain Services      │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │ Infrastructure       │

&#x20;                        │ Repositories         │

&#x20;                        │ ORM / External APIs  │

&#x20;                        └──────────┬───────────┘

&#x20;                                   │

&#x20;                        ┌──────────▼───────────┐

&#x20;                        │ SQL Server / Redis   │

&#x20;                        │ Storage / Services   │

&#x20;                        └──────────────────────┘





──────────────────────────────────────────────────────────────────────────────

3\. Dependency Rules

──────────────────────────────────────────────────────────────────────────────



قانون شماره 1:



Domain نباید Django را import کند.



ممنوع:



from django.db import models



داخل Domain.



قانون شماره 2:



Domain نباید DRF را import کند.



قانون شماره 3:



Application نباید به HTTP وابسته باشد.



قانون شماره 4:



API نباید Business Logic داشته باشد.



قانون شماره 5:



Infrastructure می‌تواند Django و ORM را بشناسد.



قانون شماره 6:



Dependency باید به سمت داخل باشد.



API

&#x20;↓

Application

&#x20;↓

Domain



و:



Infrastructure

&#x20;↓

Domain / Application Contracts





──────────────────────────────────────────────────────────────────────────────

4\. Application Layer

──────────────────────────────────────────────────────────────────────────────



Application Layer وظیفه اجرای Use Caseهای سیستم را دارد.



مثال:



Create Tenant

Create User

Assign User to Tenant

Create Department

Create Employee

Create Project

Create Task

Create Document

Send Notification



هر Use Case باید مستقل طراحی شود.





ساختار پیشنهادی:



backend/

└── apps/

&#x20;   └── <boundedContext>/

&#x20;       ├── domain/

&#x20;       ├── application/

&#x20;       │   ├── commands/

&#x20;       │   ├── queries/

&#x20;       │   ├── useCases/

&#x20;       │   ├── dto/

&#x20;       │   └── services/

&#x20;       ├── infrastructure/

&#x20;       └── presentation/





──────────────────────────────────────────────────────────────────────────────

5\. Commands

──────────────────────────────────────────────────────────────────────────────



Command یعنی:



«سیستم باید یک عملیات را انجام دهد.»



مثال:



CreateUserCommand



CreateTenantCommand



CreateProjectCommand



AssignEmployeeCommand



CreateTaskCommand





Command باید فقط Input مورد نیاز Use Case را نگهداری کند.



مثال مفهومی:



CreateTenantCommand



&#x20;   name

&#x20;   code

&#x20;   description

&#x20;   actorId





Command نباید HTTP Request باشد.





──────────────────────────────────────────────────────────────────────────────

6\. Queries

──────────────────────────────────────────────────────────────────────────────



Query یعنی:



«سیستم باید اطلاعاتی را برگرداند.»



مثال:



GetTenantQuery



GetUserQuery



ListEmployeesQuery



ListProjectsQuery



GetTaskDetailsQuery





Query نباید داده را تغییر دهد.



قاعده:



Command → تغییر State



Query → Read State





──────────────────────────────────────────────────────────────────────────────

7\. DTO

──────────────────────────────────────────────────────────────────────────────



DTO = Data Transfer Object



DTO برای انتقال داده بین Layerها استفاده می‌شود.



مثلاً:



CreateTenantDTO



TenantDTO



EmployeeDTO



ProjectDTO





DTO نباید Business Logic داشته باشد.





──────────────────────────────────────────────────────────────────────────────

8\. Use Case

──────────────────────────────────────────────────────────────────────────────



هر Use Case باید یک مسئولیت مشخص داشته باشد.



مثال:



CreateTenantUseCase



ورودی:



CreateTenantCommand



مراحل:



1\. Validate Input

2\. Check Authorization

3\. Check Business Rules

4\. Create Domain Entity

5\. Persist Entity

6\. Generate Domain Event

7\. Audit Operation

8\. Return DTO





Use Case نباید مستقیماً HTTP Response تولید کند.





──────────────────────────────────────────────────────────────────────────────

9\. Transaction Boundary

──────────────────────────────────────────────────────────────────────────────



Transaction باید در Application Layer تعریف شود.



مثلاً:



CreateEmployeeUseCase



کل عملیات باید Atomic باشد.



اگر مرحله 7 شکست خورد:



تمام تغییرات Database باید Rollback شوند.





نباید Transaction Logic داخل View قرار بگیرد.





──────────────────────────────────────────────────────────────────────────────

10\. Repository Pattern

──────────────────────────────────────────────────────────────────────────────



Domain نباید Django ORM را بشناسد.



بنابراین Repository Contract تعریف می‌شود.



مثال مفهومی:



EmployeeRepository



متدها:



create()

getById()

findByCode()

update()

delete()

exists()





Application از Interface استفاده می‌کند.



Infrastructure آن را پیاده‌سازی می‌کند.





ساختار:



domain/

&#x20;   repositories/

&#x20;       employeeRepository.py



infrastructure/

&#x20;   repositories/

&#x20;       djangoEmployeeRepository.py





──────────────────────────────────────────────────────────────────────────────

11\. Service Layer

──────────────────────────────────────────────────────────────────────────────



Serviceها باید به دو دسته تقسیم شوند:



Application Service



Domain Service





Application Service:



Use Case orchestration.





Domain Service:



Business Logicای که متعلق به یک Entity خاص نیست.





مثال:



PerformanceCalculationService



PermissionEvaluationService



KPIEvaluationService





──────────────────────────────────────────────────────────────────────────────

12\. API Layer

──────────────────────────────────────────────────────────────────────────────



API مسئول موارد زیر است:



\- HTTP

\- Authentication

\- Authorization

\- Validation اولیه

\- Serialization

\- Routing

\- Status Codes

\- Error Mapping

\- Pagination

\- Filtering

\- Rate Limiting





API نباید Business Logic اصلی داشته باشد.





──────────────────────────────────────────────────────────────────────────────

13\. API Versioning

──────────────────────────────────────────────────────────────────────────────



از ابتدا Versioning فعال باشد.



مثال:



/api/v1/





در آینده:



/api/v2/





نباید API بدون Version ساخته شود.





──────────────────────────────────────────────────────────────────────────────

14\. Response استاندارد

──────────────────────────────────────────────────────────────────────────────



تمام APIها باید Response Contract استاندارد داشته باشند.



Success:



{

&#x20;   "success": true,

&#x20;   "data": {},

&#x20;   "meta": {},

&#x20;   "errors": \[]

}





Error:



{

&#x20;   "success": false,

&#x20;   "data": null,

&#x20;   "meta": {},

&#x20;   "errors": \[

&#x20;       {

&#x20;           "code": "VALIDATION\_ERROR",

&#x20;           "message": "...",

&#x20;           "field": "..."

&#x20;       }

&#x20;   ]

}





Response Contract باید در کل Tekarai یکسان باشد.





──────────────────────────────────────────────────────────────────────────────

15\. Error Architecture

──────────────────────────────────────────────────────────────────────────────



خطاها باید طبقه‌بندی شوند.



Domain Error

Application Error

Infrastructure Error

Authentication Error

Authorization Error

Validation Error

Not Found Error

Conflict Error

External Service Error





نمونه:



EntityNotFoundError



BusinessRuleViolationError



PermissionDeniedError



ConflictError





API این Exceptionها را به HTTP Response تبدیل می‌کند.





──────────────────────────────────────────────────────────────────────────────

16\. Authentication

──────────────────────────────────────────────────────────────────────────────



Authentication باید از Authorization جدا باشد.



Authentication:



«این کاربر چه کسی است؟»



Authorization:



«این کاربر چه کاری اجازه دارد انجام دهد؟»





در این فاز باید Architecture برای:



JWT

Refresh Token

Session

Service Account

Agent Authentication



در نظر گرفته شود.





──────────────────────────────────────────────────────────────────────────────

17\. Authorization

──────────────────────────────────────────────────────────────────────────────



Tekarai نباید فقط از:



is\_staff

is\_superuser



استفاده کند.



Authorization باید قابلیت:



RBAC

Permission

Role

Scope

Tenant Boundary

Resource Authorization



داشته باشد.





مثال:



user

&#x20;   ↓

role

&#x20;   ↓

permissions

&#x20;   ↓

resource





──────────────────────────────────────────────────────────────────────────────

18\. Multi-Tenancy

──────────────────────────────────────────────────────────────────────────────



Tekarai باید Multi-Tenant باشد.



هیچ Tenant نباید بتواند داده Tenant دیگر را مشاهده کند.



این Rule باید در چند لایه enforce شود:



Application

Repository

Authorization

Database Query





نباید فقط به UI اعتماد شود.





──────────────────────────────────────────────────────────────────────────────

19\. Audit

──────────────────────────────────────────────────────────────────────────────



هر عملیات حساس باید قابل Audit باشد.



مثال:



Create

Update

Delete

Login

Logout

Permission Change

Role Change

Document Access

Export

Download

Approval

Rejection





Audit باید شامل:



actor

tenant

action

resource

resourceId

timestamp

ip

userAgent

before

after

correlationId





باشد.





──────────────────────────────────────────────────────────────────────────────

20\. Idempotency

──────────────────────────────────────────────────────────────────────────────



برای عملیات حساس باید Idempotency در نظر گرفته شود.



مثال:



Payment

Notification

External Integration

Command Processing

File Upload

Webhook





Client بتواند:



Idempotency-Key



ارسال کند.





──────────────────────────────────────────────────────────────────────────────

21\. Pagination

──────────────────────────────────────────────────────────────────────────────



APIهای List نباید تمام رکوردها را برگردانند.



Pagination باید استاندارد باشد.



مثال:



?page=1\&pageSize=50





یا برای Datasetهای بزرگ:



Cursor Pagination





انتخاب روش باید بر اساس نوع Endpoint انجام شود.





──────────────────────────────────────────────────────────────────────────────

22\. Filtering / Sorting / Searching

──────────────────────────────────────────────────────────────────────────────



API باید قابلیت:



Filtering

Sorting

Searching



داشته باشد.



مثال:



?status=active



?departmentId=...



?ordering=-createdAt



?search=...





اما Filtering نباید باعث ایجاد SQL Query ناامن شود.





──────────────────────────────────────────────────────────────────────────────

23\. Rate Limiting

──────────────────────────────────────────────────────────────────────────────



برای Endpointهای حساس:



Login

Authentication

Password Reset

OTP

AI

File Upload

Public API



Rate Limiting باید وجود داشته باشد.





──────────────────────────────────────────────────────────────────────────────

24\. API Documentation

──────────────────────────────────────────────────────────────────────────────



API باید از ابتدا قابل مستندسازی باشد.



تمام Endpointها باید مشخص کنند:



Method

URL

Authentication

Permission

Request

Response

Errors

Pagination

Filtering

Examples





OpenAPI باید در معماری دیده شود.





──────────────────────────────────────────────────────────────────────────────

25\. Correlation ID

──────────────────────────────────────────────────────────────────────────────



هر Request باید یک:



Correlation ID



داشته باشد.



این ID باید در:



API

Application

Domain Events

Audit

Logs

External Calls



قابل ردیابی باشد.





هدف:



Trace کردن یک عملیات از ابتدا تا انتها.





──────────────────────────────────────────────────────────────────────────────

26\. Request Lifecycle

──────────────────────────────────────────────────────────────────────────────



Request:



Client

&#x20;↓

Middleware

&#x20;↓

Authentication

&#x20;↓

Authorization

&#x20;↓

API View

&#x20;↓

Serializer / Request DTO

&#x20;↓

Command / Query

&#x20;↓

Use Case

&#x20;↓

Domain

&#x20;↓

Repository

&#x20;↓

Database

&#x20;↓

DTO

&#x20;↓

Serializer

&#x20;↓

Response





──────────────────────────────────────────────────────────────────────────────

27\. File Structure

──────────────────────────────────────────────────────────────────────────────



برای Contextهای Enterprise ساختار باید به سمت زیر حرکت کند:



apps/

└── identity/

&#x20;   ├── domain/

&#x20;   │   ├── entities/

&#x20;   │   ├── valueObjects/

&#x20;   │   ├── services/

&#x20;   │   ├── events/

&#x20;   │   ├── repositories/

&#x20;   │   └── exceptions/

&#x20;   │

&#x20;   ├── application/

&#x20;   │   ├── commands/

&#x20;   │   ├── queries/

&#x20;   │   ├── useCases/

&#x20;   │   ├── dto/

&#x20;   │   └── services/

&#x20;   │

&#x20;   ├── infrastructure/

&#x20;   │   ├── models/

&#x20;   │   ├── repositories/

&#x20;   │   ├── services/

&#x20;   │   └── migrations/

&#x20;   │

&#x20;   └── presentation/

&#x20;       └── api/

&#x20;           ├── serializers/

&#x20;           ├── views/

&#x20;           ├── urls/

&#x20;           └── permissions/





این ساختار باید برای تمام Bounded Contextها به‌صورت استاندارد استفاده شود.





──────────────────────────────────────────────────────────────────────────────

28\. Django Role

──────────────────────────────────────────────────────────────────────────────



Django در Tekarai باید Framework باشد، نه معماری.



Django مسئول:



ORM

Migration

HTTP

Admin

Authentication Infrastructure

Middleware

Configuration



است.



اما Business Architecture نباید به Django وابسته شود.





──────────────────────────────────────────────────────────────────────────────

29\. Testing

──────────────────────────────────────────────────────────────────────────────



در این فاز Testing Architecture نیز باید ایجاد شود.



حداقل:



Unit Tests

Integration Tests

API Tests

Repository Tests

Application Tests

Authorization Tests

Multi-Tenant Isolation Tests





هر Use Case باید مستقل قابل تست باشد.





──────────────────────────────────────────────────────────────────────────────

30\. Logging

──────────────────────────────────────────────────────────────────────────────



Log باید Structured باشد.



هر Log در صورت امکان:



timestamp

level

service

module

operation

actor

tenant

correlationId

requestId

message

exception



داشته باشد.





──────────────────────────────────────────────────────────────────────────────

31\. Security

──────────────────────────────────────────────────────────────────────────────



حداقل موارد:



Input Validation

Authentication

Authorization

Tenant Isolation

CSRF

CORS

Rate Limiting

Secure Headers

Secret Management

Password Hashing

Token Rotation

Audit Logging

File Validation

Upload Restrictions

SQL Injection Protection

Mass Assignment Protection





──────────────────────────────────────────────────────────────────────────────

32\. خروجی‌های الزامی فاز ۶

──────────────────────────────────────────────────────────────────────────────



در پایان Phase 06 باید این موارد وجود داشته باشند:



\[ ] Application Architecture



\[ ] Command Architecture



\[ ] Query Architecture



\[ ] Use Case Architecture



\[ ] DTO Architecture



\[ ] Repository Contracts



\[ ] Repository Implementations



\[ ] Application Services



\[ ] Domain Services Boundary



\[ ] API Architecture



\[ ] API Versioning



\[ ] Standard Response Contract



\[ ] Exception Architecture



\[ ] Authentication Architecture



\[ ] Authorization Architecture



\[ ] Multi-Tenant Enforcement



\[ ] Audit Integration



\[ ] Correlation ID



\[ ] Idempotency Strategy



\[ ] Pagination



\[ ] Filtering



\[ ] Searching



\[ ] Sorting



\[ ] Rate Limiting Architecture



\[ ] OpenAPI Architecture



\[ ] Testing Architecture



\[ ] Logging Architecture





──────────────────────────────────────────────────────────────────────────────

33\. Definition of Done

──────────────────────────────────────────────────────────────────────────────



Phase 06 زمانی تمام شده محسوب می‌شود که:



1\. API مستقیماً Business Logic اجرا نکند.



2\. Use Caseها مستقل از HTTP باشند.



3\. Domain مستقل از Django باشد.



4\. Repository Contract وجود داشته باشد.



5\. Infrastructure Repository را پیاده‌سازی کند.



6\. Authentication و Authorization جدا باشند.



7\. Tenant Isolation enforce شده باشد.



8\. تمام Responseها استاندارد باشند.



9\. Exception Mapping استاندارد باشد.



10\. Audit قابل اتصال به Use Caseها باشد.



11\. Correlation ID در کل Request Flow وجود داشته باشد.



12\. API Versioning وجود داشته باشد.



13\. Test Architecture وجود داشته باشد.



14\. OpenAPI قابل تولید باشد.



15\. تمام معماری مستند شده باشد.





──────────────────────────────────────────────────────────────────────────────

34\. قانون مهم برای پیاده‌سازی

──────────────────────────────────────────────────────────────────────────────



قبل از نوشتن کد:



Architecture → Contract → Interface → Implementation → Test



و نه:



Code → مشکل → اصلاح معماری





هیچ فایل Application یا API بدون مشخص شدن مسئولیت آن ایجاد نشود.



هیچ Dependency جدید بدون بررسی Architecture اضافه نشود.



هیچ Business Rule داخل View، Serializer یا Django Model قرار نگیرد.





──────────────────────────────────────────────────────────────────────────────

35\. خروجی نهایی

──────────────────────────────────────────────────────────────────────────────



بعد از Phase 06:



Tekarai باید یک Application/API Foundation واقعی داشته باشد که بتواند

Bounded Contextهای بعدی مانند:



Identity

Organization

HR

Projects

Tasks

Assets

Documents

Workflow

Communication

Notifications

Analytics

AI

Integration



را بدون شکستن معماری به آن اضافه کند.



Phase 06 نباید صرفاً چند فایل Django ایجاد کند.



این فاز باید ستون فقرات اجرای Use Caseهای کل Tekarai را ایجاد کند.





END OF PHASE 06

