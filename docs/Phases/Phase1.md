============================================================

TEKARAI — PHASE 01

FOUNDATION \& REPOSITORY

============================================================



STATUS:

PHASE 01 — FOUNDATION \& REPOSITORY



PURPOSE:

ساخت پایه‌ی فنی و Repository پروژه Tekarai از صفر.



این فاز فقط مسئول ایجاد Foundation پروژه است.

در این فاز نباید وارد پیاده‌سازی Business Domain، Entityهای تجاری،

ERD نهایی، APIهای Business، AI، Workflow، Communication یا UI شویم.



\------------------------------------------------------------

1\. PROJECT IDENTITY

\------------------------------------------------------------



Product Name:

Tekarai



Product Type:

Enterprise Operations Platform



Architecture Style:

Modular Monolith



Architectural Principles:

\- Platform First

\- API First

\- Domain Driven Design

\- Clean Architecture

\- SOLID

\- Event Driven

\- Security First

\- AI Native

\- Cloud Ready

\- Offline Ready

\- Configuration over Customization

\- Documentation Driven Development

\- Everything is Auditable

\- Everything is Extensible



Tekarai باید یک محصول عمومی و قابل فروش باشد.



Tekarai نباید به یک شرکت، کارخانه، صنعت یا مشتری خاص وابسته باشد.



Industry-specific functionality باید بعداً به شکل:

\- Industry Pack

\- Extension

\- Plugin

\- Integration

پیاده‌سازی شود.



Core Platform نباید شامل منطق اختصاصی یک مشتری باشد.



\------------------------------------------------------------

2\. PRIMARY OBJECTIVE

\------------------------------------------------------------



در پایان Phase 01 باید یک Repository تمیز، استاندارد،

قابل توسعه و Production-Oriented داشته باشیم که بتواند

تمام فازهای بعدی Tekarai روی آن ساخته شوند.



هدف این فاز:



1\. ایجاد Repository

2\. ایجاد Backend foundation

3\. ایجاد Frontend foundation placeholder

4\. ایجاد documentation foundation

5\. ایجاد deployment/infrastructure foundation

6\. ایجاد Git structure

7\. ایجاد environment management

8\. ایجاد configuration foundation

9\. ایجاد development standards

10\. ایجاد testing foundation

11\. ایجاد CI foundation

12\. ایجاد project documentation

13\. ایجاد naming conventions

14\. ایجاد dependency management

15\. ایجاد baseline quality gates



\------------------------------------------------------------

3\. REQUIRED REPOSITORY STRUCTURE

\------------------------------------------------------------



Repository باید در نهایت ساختاری مشابه زیر داشته باشد:



tekarai/

│

├── backend/

│

├── frontend-web/

│

├── mobile/

│

├── desktop/

│

├── agents/

│

├── ai/

│

├── sdk/

│

├── docs/

│

├── deployment/

│

├── infrastructure/

│

├── .gitignore

├── .gitattributes

├── README.md

└── LICENSE



در Phase 01 لازم نیست تمام بخش‌ها دارای implementation باشند.



اما structure باید از ابتدا مشخص باشد.



\------------------------------------------------------------

4\. BACKEND FOUNDATION

\------------------------------------------------------------



Backend تکنولوژی اصلی:



Python

Django

Django REST Framework

SQL Server



Backend باید به صورت مستقل قابل اجرا باشد.



Backend باید شامل:



backend/

│

├── manage.py

│

├── config/

│

├── apps/

│

├── tests/

│

├── docs/

│

├── requirements/

│

├── scripts/

│

├── .env.example

└── README.md



باشد.



در صورت انتخاب ساختار متفاوت، Agent باید دلیل معماری آن را

در ADR ثبت کند.



\------------------------------------------------------------

5\. DJANGO FOUNDATION

\------------------------------------------------------------



Django باید با ساختار configuration چندمحیطی ایجاد شود.



حداقل:



config/

└── settings/

&#x20;   ├── base.py

&#x20;   ├── development.py

&#x20;   ├── testing.py

&#x20;   └── production.py



اصل:



Development configuration

Testing configuration

Production configuration



نباید در یک فایل واحد قفل شوند.



Environment-specific configuration باید از Environment Variables

خوانده شود.



هیچ Secret نباید Hard-Code شود.



\------------------------------------------------------------

6\. ENVIRONMENT MANAGEMENT

\------------------------------------------------------------



باید فایل:



.env.example



ایجاد شود.



فایل واقعی:



.env



نباید وارد Git شود.



حداقل Configuration Categories:



APPLICATION

DATABASE

SECURITY

DJANGO

LOGGING

CACHE

EMAIL

STORAGE

CORS

JWT

EXTERNAL SERVICES



مقادیر واقعی Secret نباید در Repository ذخیره شوند.



\------------------------------------------------------------

7\. DEPENDENCY MANAGEMENT

\------------------------------------------------------------



تمام dependencyها باید Version Pinning یا Constraint مناسب داشته باشند.



Dependencyها باید دسته‌بندی شوند:



Production Dependencies

Development Dependencies

Testing Dependencies



Dependency اضافه کردن بدون دلیل ممنوع است.



هر Dependency باید حداقل یکی از این دلایل را داشته باشد:



\- Architectural requirement

\- Framework requirement

\- Security requirement

\- Infrastructure requirement

\- Business requirement

\- Operational requirement



از اضافه کردن Library صرفاً برای راحتی کدنویسی خودداری شود.



\------------------------------------------------------------

8\. GIT FOUNDATION

\------------------------------------------------------------



Git Repository باید از ابتدا استاندارد باشد.



حداقل فایل‌ها:



.gitignore

.gitattributes

README.md



باید موارد زیر Ignore شوند:



Python cache

\_\_pycache\_\_

\*.pyc

Virtual environments

.env

IDE files

OS generated files

Build artifacts

Test artifacts

Coverage files

Temporary files

Local databases

Secrets

Generated files



Virtual Environment نباید وارد Git شود.



\------------------------------------------------------------

9\. DOCUMENTATION FOUNDATION

\------------------------------------------------------------



در Repository باید Documentation Structure ایجاد شود.



حداقل:



docs/

│

├── architecture/

├── adr/

├── api/

├── database/

├── domain/

├── development/

├── deployment/

├── security/

├── operations/

└── product/



Documentation باید Version Controlled باشد.



تصمیمات معماری مهم باید در ADR ثبت شوند.



\------------------------------------------------------------

10\. ADR FOUNDATION

\------------------------------------------------------------



ساختار:



docs/adr/



باید ایجاد شود.



اولین ADRها باید حداقل این موضوعات را ثبت کنند:



ADR-001 Product Architecture

ADR-002 Modular Monolith

ADR-003 Backend Technology

ADR-004 Database Technology

ADR-005 API First

ADR-006 Domain Driven Design

ADR-007 Clean Architecture

ADR-008 Event Driven Architecture

ADR-009 Configuration Management

ADR-010 Security Principles



ADRها باید شامل:



Context

Decision

Alternatives

Consequences



باشند.



\------------------------------------------------------------

11\. QUALITY FOUNDATION

\------------------------------------------------------------



Quality Gate باید از Phase 01 وجود داشته باشد.



حداقل:



Formatting

Linting

Type Checking

Testing



در ادامه پروژه ابزارهای دقیق می‌توانند تثبیت شوند.



اصل مهم:



هیچ Feature جدیدی نباید بدون Test وارد Repository شود.



\------------------------------------------------------------

12\. TESTING FOUNDATION

\------------------------------------------------------------



Testing structure باید از ابتدا وجود داشته باشد.



حداقل:



tests/

├── unit/

├── integration/

└── architecture/



در آینده:



contract/

e2e/

performance/

security/



نیز اضافه خواهند شد.



در Phase 01 حداقل باید بتوانیم:



\- Test runner را اجرا کنیم.

\- یک test ساده موفق اجرا شود.

\- Test configuration مستقل باشد.



\------------------------------------------------------------

13\. ARCHITECTURE TESTING

\------------------------------------------------------------



از همان ابتدا باید امکان Architecture Tests وجود داشته باشد.



هدف:



جلوگیری از Dependencyهای غیرمجاز.



مثلاً:



Domain نباید به Infrastructure وابسته باشد.



Domain نباید به Django وابسته باشد مگر اینکه

تصمیم معماری رسمی چنین چیزی را مشخص کند.



Infrastructure نباید Business Rule را مالک شود.



API Layer نباید مستقیماً Business Logic پیچیده را اجرا کند.



این قوانین در فازهای بعدی دقیق‌تر خواهند شد.



\------------------------------------------------------------

14\. SECURITY FOUNDATION

\------------------------------------------------------------



Security باید از Phase 01 در نظر گرفته شود.



حداقل اصول:



\- Secret Management

\- Environment-based configuration

\- Secure password handling

\- HTTPS-ready configuration

\- Secure cookies

\- CORS configuration

\- CSRF configuration

\- Security headers

\- Production DEBUG=False

\- Allowed Hosts configuration

\- Database credential isolation



در Phase 01 هنوز Authentication کامل ساخته نمی‌شود.



Authentication در Phase مربوط به Identity ساخته خواهد شد.



\------------------------------------------------------------

15\. DATABASE FOUNDATION

\------------------------------------------------------------



Database:



Microsoft SQL Server



Django باید از:



mssql-django



یا Adapter رسمی/تأییدشده‌ی سازگار با معماری پروژه استفاده کند.



Database credentials باید از Environment دریافت شوند.



Database migration system باید فعال باشد.



اما:



در Phase 01 هیچ Business Entity نهایی ساخته نشود.



یعنی هنوز:



Employee

Department

Project

Task

Asset

Document

Workflow

Chat

Meeting

و سایر Domain Entityها



پیاده‌سازی نشوند.



\------------------------------------------------------------

16\. APPLICATION STARTUP

\------------------------------------------------------------



در پایان Phase 01 باید بتوانیم Backend را اجرا کنیم.



حداقل باید این command موفق باشد:



python manage.py check



و Django بدون Error بالا بیاید.



همچنین development server باید اجرا شود.



\------------------------------------------------------------

17\. HEALTH CHECK

\------------------------------------------------------------



یک Health Check Foundation ایجاد شود.



Health Check باید بتواند وضعیت پایه سیستم را بررسی کند.



حداقل:



Application

Database



در فازهای بعد:



Cache

Queue

Storage

External Services



اضافه خواهند شد.



Health endpoint باید Business Logic نداشته باشد.



\------------------------------------------------------------

18\. PROJECT README

\------------------------------------------------------------



README اصلی باید شامل:



\- Product Name

\- Product Purpose

\- Architecture Overview

\- Repository Structure

\- Technology Stack

\- Development Setup

\- Environment Setup

\- Running Backend

\- Running Tests

\- Quality Checks

\- Documentation Location



باشد.



README نباید تبدیل به محل نگهداری جزئیات Business Logic شود.



\------------------------------------------------------------

19\. DEVELOPMENT RULES

\------------------------------------------------------------



از Phase 01 قوانین زیر اجباری هستند:



RULE 01:

No hard-coded secrets.



RULE 02:

No production credentials in repository.



RULE 03:

No business logic in views.



RULE 04:

No business logic in serializers.



RULE 05:

No direct database access from controllers/views unless explicitly justified.



RULE 06:

Business logic belongs to appropriate application/domain layer.



RULE 07:

All important architectural decisions must be documented.



RULE 08:

Every feature must have tests.



RULE 09:

Every migration must be reviewed.



RULE 10:

No unnecessary dependency.



RULE 11:

No copy-paste architecture.



RULE 12:

No temporary implementation without explicit ADR.



RULE 13:

Do not create models merely because Django makes model creation easy.



RULE 14:

Do not redesign previously approved architecture without documenting the reason.



RULE 15:

Never silently introduce architectural decisions.



\------------------------------------------------------------

20\. NAMING CONVENTIONS

\------------------------------------------------------------



Python:



camelCase

for functions and variables.



PascalCase

for classes.



UPPER\_SNAKE\_CASE

for framework-level constants only.



Django applications:

lowercase names.



Database:

camelCase.



API:

REST-oriented naming.



Files:

camelCase.



Architecture documents:

UPPERCASE or clearly standardized naming.



Naming must remain consistent across the project.



\------------------------------------------------------------

21\. COMMAND FOUNDATION

\------------------------------------------------------------



Agent must provide reproducible commands for setup.



Examples:



Create virtual environment.



Install dependencies.



Run migrations when appropriate.



Run checks.



Run tests.



Run formatter.



Run linter.



Run type checker.



Start development server.



Commands must be Windows-compatible because development

environment may be Windows.



Do not assume Linux-only commands.



\------------------------------------------------------------

22\. DEFINITION OF DONE

\------------------------------------------------------------



Phase 01 is NOT complete until all conditions below are true:



\[ ] Repository structure exists.



\[ ] Backend exists.



\[ ] Django starts correctly.



\[ ] Settings are environment-aware.



\[ ] .env.example exists.



\[ ] Real .env is ignored by Git.



\[ ] Virtual environment is ignored by Git.



\[ ] Database configuration exists.



\[ ] Development configuration exists.



\[ ] Testing configuration exists.



\[ ] Production configuration exists.



\[ ] Documentation structure exists.



\[ ] ADR structure exists.



\[ ] README exists.



\[ ] Test infrastructure exists.



\[ ] At least one test passes.



\[ ] Health check exists.



\[ ] python manage.py check succeeds.



\[ ] Quality tools can run.



\[ ] No secrets are committed.



\[ ] No business domain implementation has been prematurely created.



\[ ] Git repository is clean and understandable.



\------------------------------------------------------------

23\. FORBIDDEN ACTIONS IN PHASE 01

\------------------------------------------------------------



DO NOT:



\- Build Employee domain.

\- Build HR domain.

\- Build Project domain.

\- Build Task domain.

\- Build Asset domain.

\- Build Communication domain.

\- Build AI domain.

\- Build Workflow domain.

\- Build final ERD.

\- Create hundreds of Django models.

\- Implement JWT authentication.

\- Implement WebRTC.

\- Implement Chat.

\- Implement AI services.

\- Implement industry-specific logic.

\- Hard-code secrets.

\- Add unnecessary packages.

\- Skip tests.

\- Skip documentation.

\- Mix development and production settings.



\------------------------------------------------------------

24\. REQUIRED OUTPUT OF AGENT

\------------------------------------------------------------



At the end of Phase 01 Agent must report:



1\. Files created.

2\. Directories created.

3\. Dependencies installed.

4\. Configuration completed.

5\. Tests created.

6\. Tests executed.

7\. Quality checks executed.

8\. Commands used.

9\. Architecture decisions made.

10\. ADRs created.

11\. Known limitations.

12\. Phase 01 completion status.



The Agent must NOT simply say:



"Phase completed."



It must provide evidence.



\------------------------------------------------------------

25\. PHASE 01 EXIT GATE

\------------------------------------------------------------



Phase 01 can only be marked:



COMPLETED



when all Definition of Done items are satisfied.



If any required item fails:



STATUS = BLOCKED



Agent must identify:



\- Failed item

\- Error

\- Root cause

\- Proposed fix

\- Files affected

\- Verification command



and must NOT continue to Phase 02 until the Exit Gate passes.



\------------------------------------------------------------

26\. NEXT PHASE

\------------------------------------------------------------



After Phase 01 is completely verified:



NEXT PHASE:



PHASE 02 — ARCHITECTURE \& ADRs



Phase 02 will formalize:



\- System Architecture

\- Layer Boundaries

\- Module Boundaries

\- Dependency Rules

\- Domain Boundaries

\- Architectural Constraints

\- Extension Model

\- Integration Model

\- Security Architecture

\- Scalability Strategy

\- ADR Baseline



Do NOT begin Phase 02 until Phase 01 Exit Gate is GREEN.



============================================================

END OF PHASE 01

============================================================

