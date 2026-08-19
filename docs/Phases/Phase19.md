PHASE 19 — SQL SERVER DATABASE ARCHITECTURE \& DATA PLATFORM

TEKARAI IMPLEMENTATION SPECIFICATION



============================================================

1\. هدف فاز

============================================================



هدف Phase 19 طراحی و پیاده‌سازی معماری Database و Data Platform

برای Tekarai است.



Database باید:



\- Enterprise-grade

\- Multi-tenant

\- Secure

\- Consistent

\- Auditable

\- Scalable

\- Maintainable

\- Performant

\- Migration-safe

\- Extensible



باشد.



Database نباید صرفاً مجموعه‌ای از Tableها باشد.



باید یک Data Foundation استاندارد برای تمام Platformهای Tekarai

فراهم کند.





============================================================

2\. Database Technology

============================================================



Database اصلی Tekarai:



Microsoft SQL Server



Django ORM به عنوان Application ORM استفاده می‌شود.



اصل مهم:



Application

&#x20;   ↓

Repository / Application Services

&#x20;   ↓

Django ORM

&#x20;   ↓

SQL Server



Application نباید مستقیماً SQL Server را در تمام نقاط سیستم

مصرف کند.





============================================================

3\. DATABASE ARCHITECTURE

============================================================



معماری کلی:



Tekarai Application

&#x20;       |

&#x20;       v

Application Layer

&#x20;       |

&#x20;       v

Repository Layer

&#x20;       |

&#x20;       v

Django ORM

&#x20;       |

&#x20;       v

SQL Server





Infrastructure مسئول:



\- Connection

\- Transactions

\- Persistence

\- Query Optimization

\- Database Configuration

\- Database Health





است.





============================================================

4\. DATABASE PRINCIPLES

============================================================



Database باید بر اساس اصول زیر ساخته شود:



1\. Data Integrity

2\. Referential Integrity

3\. Tenant Isolation

4\. Auditability

5\. Consistency

6\. Explicit Relationships

7\. Controlled Cascades

8\. Index Strategy

9\. Migration Safety

10\. Performance

11\. Security

12\. Observability





============================================================

5\. MULTI-TENANCY

============================================================



Tekarai باید Multi-Tenant باشد.



Tenant موجودیت اصلی سیستم است.



ساختار:



Tenant

&#x20; |

&#x20; +-- Users

&#x20; +-- Roles

&#x20; +-- Projects

&#x20; +-- Tasks

&#x20; +-- Documents

&#x20; +-- Reports

&#x20; +-- Workflows

&#x20; +-- Other Resources





هر داده‌ای که Tenant-specific است باید Tenant Context داشته باشد.





============================================================

6\. TENANT ISOLATION

============================================================



Tenant Isolation باید در Backend enforce شود.



Frontend نباید منبع امنیت Tenant باشد.



هیچ Query مربوط به Resourceهای Tenant نباید بدون Tenant Scope

اجرا شود.





اصل:



NO TENANT CONTEXT

=

NO TENANT DATA ACCESS





============================================================

7\. TENANT ID

============================================================



Tenant ID باید:



\- Stable

\- Unique

\- Non-guessable



باشد.



در صورت استفاده از UUID:



Tenant.id = UUID





باشد.





============================================================

8\. GLOBAL VS TENANT DATA

============================================================



Database باید دو نوع داده را تفکیک کند.



GLOBAL DATA



اطلاعاتی که متعلق به هیچ Tenant خاصی نیستند.



مثال:



System Configuration

Country

Currency

Timezone





TENANT DATA



اطلاعات متعلق به Tenant.



مثال:



Users

Projects

Tasks

Documents

Reports





هر Model باید مشخص کند Global است یا Tenant-scoped.





============================================================

9\. BASE MODEL

============================================================



Modelهای اصلی باید از یک Base Model استاندارد استفاده کنند.



Base Fields:



id

createdAt

updatedAt





در صورت نیاز:



createdBy

updatedBy





و برای Soft Delete:



deletedAt

deletedBy

isActive





============================================================

10\. PRIMARY KEY

============================================================



Primary Key باید استاندارد و یکسان باشد.



ترجیح معماری Tekarai:



UUID





مزایا:



\- Distributed-safe

\- Non-sequential exposure

\- مناسب Multi-Tenant

\- مناسب Integration

\- مناسب آینده سیستم





============================================================

11\. AUDIT FIELDS

============================================================



Entityهای مهم باید Audit Information داشته باشند.



حداقل:



createdAt

updatedAt

createdBy

updatedBy





در صورت Soft Delete:



deletedAt

deletedBy





============================================================

12\. SOFT DELETE

============================================================



برای Entityهای Business-critical حذف فیزیکی نباید Default باشد.



به جای:



DELETE





از:



deletedAt





استفاده شود.



Entity حذف‌شده نباید در Queryهای عادی نمایش داده شود.





============================================================

13\. HARD DELETE

============================================================



Hard Delete فقط در شرایط کنترل‌شده مجاز است.



مثال:



\- Temporary Data

\- Cache

\- Technical Records

\- Data Retention Cleanup





و باید Policy مشخص داشته باشد.





============================================================

14\. DATABASE NAMING

============================================================



Naming باید Consistent باشد.



Table:



camelCase



مثال:



users

tenants

projects

projectMembers





Field:



camelCase



مثال:



createdAt

tenantId

updatedById





Constraint و Index نیز باید Naming Convention مشخص داشته باشند.





============================================================

15\. TABLE NAMING

============================================================



Tableها باید نام واضح داشته باشند.



بد:



tbl1

data

items2





خوب:



projects

tasks

documents

notifications





============================================================

16\. FOREIGN KEY

============================================================



تمام Relationshipهای واقعی باید Foreign Key داشته باشند.



نباید صرفاً:



projectId = UUIDField()





استفاده شود اگر رابطه واقعی Django Model وجود دارد.



در صورت Relationship واقعی:



ForeignKey / OneToOneField / ManyToManyField





استفاده شود.





============================================================

17\. CASCADE POLICY

============================================================



CASCADE نباید بدون تحلیل استفاده شود.



برای هر Relationship باید مشخص شود:



CASCADE

PROTECT

SET\_NULL

SET\_DEFAULT





مثال:



User حذف شد

↓

Historical Records نباید حذف شوند.





پس:



SET\_NULL





می‌تواند مناسب باشد.





============================================================

18\. RELATIONSHIP TYPES

============================================================



Tekarai باید Relationshipها را دقیق تعریف کند.



One-to-One



One-to-Many



Many-to-One



Many-to-Many





Many-to-Manyهای مهم بهتر است Explicit Through Model داشته باشند.





============================================================

19\. EXPLICIT THROUGH MODELS

============================================================



مثال:



Project

\+

User



رابطه:



ProjectMember





می‌تواند شامل:



project

user

role

joinedAt

isActive





باشد.



این مدل بهتر از ManyToMany ساده برای Business Relationship است.





============================================================

20\. CONSTRAINTS

============================================================



Database باید Integrity را enforce کند.



استفاده از:



UniqueConstraint

CheckConstraint

ForeignKey

Not Null

Default





در موارد لازم الزامی است.





============================================================

21\. UNIQUE CONSTRAINT

============================================================



Unique بودن باید در Database enforce شود.



مثال:



Tenant.code





نباید فقط در Python بررسی شود.



Database باید آخرین لایه تضمین باشد.





============================================================

22\. COMPOSITE UNIQUE

============================================================



در Multi-Tenant معمولاً Unique بودن باید Tenant-aware باشد.



مثال:



Tenant + Project Code





یعنی:



tenantId

\+

code





Unique باشد.





============================================================

23\. NULL POLICY

============================================================



NULL نباید بی‌دلیل استفاده شود.



برای هر Field باید مشخص شود:



Required

Optional

Nullable





NULL و Empty String نباید بدون دلیل جایگزین یکدیگر شوند.





============================================================

24\. DATA TYPES

============================================================



Data Type باید دقیق انتخاب شود.



مثال:



UUID

Boolean

Integer

BigInteger

Decimal

Date

DateTime

Text

CharField





برای Money:



Float استفاده نشود.



از Decimal استفاده شود.





============================================================

25\. MONEY

============================================================



مقادیر مالی باید:



Decimal





باشند.



مثال مفهومی:



amount = DecimalField(...)





Precision و Scale باید متناسب با Domain انتخاب شوند.





============================================================

26\. DATE/TIME

============================================================



تمام Timestampهای سیستمی باید:



Timezone-aware





باشند.



Database/Application باید یک سیاست واحد برای Timezone داشته باشد.



ترجیح:



UTC Storage



Localized Presentation





============================================================

27\. ENUM / CHOICES

============================================================



Statusها نباید به شکل Stringهای پراکنده در کد نوشته شوند.



مثال بد:



status = "done"



در نقاط مختلف سیستم.





باید Enum / Controlled Vocabulary وجود داشته باشد.





============================================================

28\. STATUS FIELDS

============================================================



Status باید:



\- Defined

\- Validated

\- Consistent





باشد.



مثال:



DRAFT

ACTIVE

SUSPENDED

COMPLETED

CANCELLED





============================================================

29\. DATABASE SCHEMA ORGANIZATION

============================================================



Database باید Domainها را به صورت منطقی سازمان‌دهی کند.



نمونه:



Identity



Tenant



Organization



Project



Task



Document



Workflow



Notification



Reporting



Audit



Intelligence



Administration





ساختار نهایی باید با Domain Model Tekarai هماهنگ باشد.





============================================================

30\. IDENTITY DATA

============================================================



Identity Domain شامل موجودیت‌هایی مانند:



User

Role

Permission

UserRole

RolePermission





است.





============================================================

31\. TENANT DATA

============================================================



Tenant Domain شامل:



Tenant

TenantSettings

TenantMembership

TenantConfiguration





در صورت نیاز.





============================================================

32\. ORGANIZATION DATA

============================================================



Organization Domain می‌تواند شامل:



Department

Team

Position

Employee Profile





باشد.





============================================================

33\. PROJECT DATA

============================================================



Project Domain می‌تواند شامل:



Project

ProjectMember

ProjectStatus

ProjectMetadata





باشد.





============================================================

34\. TASK DATA

============================================================



Task Domain می‌تواند شامل:



Task

TaskAssignment

TaskComment

TaskStatus

TaskDependency

TaskLabel





باشد.





============================================================

35\. DOCUMENT DATA

============================================================



Document Domain می‌تواند شامل:



Document

DocumentVersion

DocumentCategory

DocumentPermission

DocumentMetadata





باشد.





============================================================

36\. WORKFLOW DATA

============================================================



Workflow Domain می‌تواند شامل:



Workflow

WorkflowDefinition

WorkflowInstance

WorkflowStep

WorkflowTransition

WorkflowApproval





باشد.





============================================================

37\. NOTIFICATION DATA

============================================================



Notification Domain می‌تواند شامل:



Notification

NotificationRecipient

NotificationPreference





باشد.





============================================================

38\. REPORTING DATA

============================================================



Reporting Domain می‌تواند شامل:



ReportDefinition

ReportExecution

ReportSchedule

ReportResult





باشد.





============================================================

39\. AUDIT DATA

============================================================



Audit Domain باید بتواند ثبت کند:



Actor

Action

Resource

Resource ID

Tenant

Timestamp

Result

Metadata





Audit Data نباید به سادگی قابل تغییر باشد.





============================================================

40\. INTELLIGENCE DATA

============================================================



Project Intelligence می‌تواند اطلاعاتی مانند:



ProjectSnapshot

DependencyAnalysis

ArchitectureAnalysis

Insight

Recommendation

Decision





را ذخیره کند.



ساختار دقیق باید با Domain Model مربوطه هماهنگ شود.





============================================================

41\. CONFIGURATION DATA

============================================================



Configuration می‌تواند شامل:



SystemConfiguration

TenantConfiguration

UserPreference





باشد.



Configuration نباید با Business Data مخلوط شود.





============================================================

42\. JSON DATA

============================================================



JSON می‌تواند برای:



\- Flexible Metadata

\- Configuration

\- External Payload

\- AI Metadata





استفاده شود.



اما JSON نباید جایگزین Relational Modeling شود.



اطلاعاتی که نیاز به:



\- Query

\- Index

\- Relationship

\- Constraint





دارند باید Column/Model واقعی داشته باشند.





============================================================

43\. NORMALIZATION

============================================================



Database باید تا حد منطقی Normalized باشد.



از Duplicate Data غیرضروری جلوگیری شود.



Denormalization فقط با دلیل Performance/Architecture انجام شود.





============================================================

44\. INDEX STRATEGY

============================================================



Index باید بر اساس Query Pattern طراحی شود.



Indexهای مهم معمولاً شامل:



tenantId

createdAt

updatedAt

status

foreign keys





هستند.



اما Index اضافی ایجاد نکن.



هر Index هزینه:



INSERT

UPDATE

DELETE

Storage





دارد.





============================================================

45\. COMPOSITE INDEX

============================================================



در Multi-Tenant Queryهای رایج:



tenantId + field





می‌تواند Index مناسب باشد.



مثال:



tenantId

\+

status





یا:



tenantId

\+

createdAt





اما فقط بر اساس Query Pattern واقعی ایجاد شود.





============================================================

46\. UNIQUE INDEX

============================================================



Unique Index برای Business Ruleهایی که Unique بودن لازم دارند

قابل استفاده است.





============================================================

47\. DATABASE QUERY PERFORMANCE

============================================================



از Queryهای:



N+1

Unbounded Query

SELECT \* غیرضروری

Repeated Query





جلوگیری شود.





============================================================

48\. ORM PERFORMANCE

============================================================



در Django باید از ابزارهایی مانند:



select\_related

prefetch\_related

only

defer

annotate





در صورت نیاز استفاده شود.





============================================================

49\. TRANSACTIONS

============================================================



عملیات چندمرحله‌ای Business باید Transaction داشته باشند.



مثال:



Create Project

\+

Create Membership

\+

Create Initial Task





یا همه موفق شوند یا هیچ‌کدام.





============================================================

50\. ATOMICITY

============================================================



Database Operationهای مرتبط باید Atomic باشند.



در Django:



transaction.atomic()





در موارد مناسب استفاده شود.





============================================================

51\. CONCURRENCY

============================================================



در عملیات حساس باید Concurrency کنترل شود.



ابزارهای ممکن:



select\_for\_update

Optimistic Locking

Unique Constraints





بسته به سناریو.





============================================================

52\. RACE CONDITIONS

============================================================



Business Logic نباید به این شکل باشد:



CHECK

↓

DO





اگر دو Request همزمان وارد شوند ممکن است هر دو موفق شوند.



Integrity باید در Database نیز enforce شود.





============================================================

53\. MIGRATIONS

============================================================



تمام Schema Changes باید از Migration عبور کنند.



هرگز Database Production را دستی تغییر نده مگر در

Emergency Procedure مستند.





============================================================

54\. MIGRATION RULES

============================================================



Migration باید:



\- Deterministic

\- Reviewable

\- Reversible در حد امکان

\- Safe

\- Version-controlled





باشد.





============================================================

55\. MIGRATION SAFETY

============================================================



برای تغییرات بزرگ:



1\. Add New Field

2\. Deploy Code

3\. Backfill

4\. Validate

5\. Switch Usage

6\. Remove Old Field





از تغییرات مخرب مستقیم جلوگیری شود.





============================================================

56\. INITIAL MIGRATION

============================================================



هر App باید Migrationهای استاندارد خودش را داشته باشد.



Migrationها باید در Git Commit شوند.





============================================================

57\. MIGRATION CONFLICT

============================================================



Conflict بین Migrationها باید با دقت Resolve شود.



نباید Migration History بدون بررسی حذف شود.





============================================================

58\. DATABASE SEEDING

============================================================



Seed Data باید از Migrationهای Business جدا باشد.



Seedها برای:



\- Permissions

\- Default Roles

\- System Configuration

\- Reference Data





استفاده می‌شوند.





============================================================

59\. REFERENCE DATA

============================================================



داده‌های ثابت و مرجع باید مشخص باشند.



مثال:



Country

Currency

Timezone

Language





باید Strategy مشخص داشته باشند.





============================================================

60\. DATABASE SECURITY

============================================================



Database Credentialها نباید در Git قرار بگیرند.



Configuration باید از:



Environment Variables

Secret Management





استفاده کند.





============================================================

61\. DATABASE USER

============================================================



Application نباید با SQL Server Administrator اجرا شود.



Database User باید Minimum Required Permissions داشته باشد.





============================================================

62\. LEAST PRIVILEGE

============================================================



اصل:



Application User

≠

Database Administrator





باشد.





============================================================

63\. BACKUP

============================================================



Database باید Backup Strategy داشته باشد.



حداقل:



Full Backup



و در صورت نیاز:



Differential

Transaction Log





============================================================

64\. RESTORE

============================================================



Backup بدون Restore Test قابل اعتماد نیست.



باید Restore Procedure تست شود.





============================================================

65\. DISASTER RECOVERY

============================================================



برای Production باید مشخص شود:



RPO

RTO

Backup Frequency

Retention

Restore Procedure





============================================================

66\. DATA RETENTION

============================================================



برای هر Data Category باید مشخص شود:



Retention Period

Archive Policy

Deletion Policy





نباید Data برای همیشه بدون Policy نگهداری شود.





============================================================

67\. ARCHIVING

============================================================



داده‌های قدیمی در صورت نیاز باید:



Archive





شوند.



Archive نباید Queryهای اصلی را بی‌دلیل سنگین کند.





============================================================

68\. AUDIT RETENTION

============================================================



Audit Data معمولاً باید Retention مستقل داشته باشد.



حذف Audit نباید بدون Policy انجام شود.





============================================================

69\. DATABASE MONITORING

============================================================



Monitoring باید شامل:



Connection Count

Query Duration

CPU

Memory

Storage

Deadlocks

Blocking

Failed Queries

Index Usage





باشد.





============================================================

70\. HEALTH CHECK

============================================================



Tekarai باید Database Health Check داشته باشد.



مثال:



Application

&#x20;↓

Database Health Check

&#x20;↓

SQL Server Connectivity

&#x20;↓

Response





Health Check نباید اطلاعات حساس Database را expose کند.





============================================================

71\. CONNECTION POOL

============================================================



Database Connection Management باید استاندارد باشد.



Connectionهای غیرضروری نباید باز بمانند.





============================================================

72\. TIMEOUT

============================================================



Database Operationها باید Timeout مناسب داشته باشند.



Queryهای بدون Timeout در Production خطرناک هستند.





============================================================

73\. LONG-RUNNING QUERIES

============================================================



Queryهای طولانی باید قابل شناسایی باشند.



Threshold مشخص شود.



مثال مفهومی:



Slow Query

=

Query Duration > Defined Threshold





Threshold باید بر اساس محیط تعیین شود.





============================================================

74\. DEADLOCK MANAGEMENT

============================================================



Deadlock باید:



\- Detect

\- Log

\- Analyze

\- Mitigate





شود.



Retry فقط در موارد مناسب انجام شود.





============================================================

75\. SQL SERVER FEATURES

============================================================



در صورت نیاز و با بررسی معماری می‌توان از قابلیت‌های SQL Server

استفاده کرد:



\- Transactions

\- Indexes

\- Constraints

\- Views

\- Stored Procedures در موارد مشخص

\- Full Text Search در صورت نیاز

\- Temporal Features در صورت نیاز

\- Partitioning در مقیاس بالا





اما هیچ Feature دیتابیسی نباید بدون نیاز واقعی اضافه شود.





============================================================

76\. STORED PROCEDURES

============================================================



Stored Procedure نباید جایگزین Application Architecture شود.



فقط برای مواردی که واقعاً مزیت دارند استفاده شود.





============================================================

77\. VIEWS

============================================================



View می‌تواند برای:



\- Reporting

\- Read Models

\- Complex Read Queries





استفاده شود.



Business Write Logic نباید بدون دلیل داخل View قرار گیرد.





============================================================

78\. REPORTING DATABASE

============================================================



در مقیاس بالا ممکن است Reporting Workload از Transactional

Workload جدا شود.



این تصمیم باید در مراحل Scale Architecture گرفته شود.



در V1 الزاماً Database جدا نیاز نیست.





============================================================

79\. READ/WRITE SEPARATION

============================================================



در صورت رشد سیستم:



Write Database

\+

Read Replica





می‌تواند در نظر گرفته شود.



اما از ابتدا پیچیدگی غیرضروری ایجاد نشود.





============================================================

80\. DATA ACCESS LAYER

============================================================



Business Logic نباید مستقیماً Queryهای ORM را همه‌جا اجرا کند.



ساختار پیشنهادی:



Application Service

&#x20;↓

Repository Interface

&#x20;↓

Repository Implementation

&#x20;↓

Django ORM





============================================================

81\. REPOSITORY RULE

============================================================



Repository مسئول Persistence است.



Repository نباید Business Workflow را مدیریت کند.





============================================================

82\. DOMAIN MODEL VS DATABASE MODEL

============================================================



Database Model نباید الزاماً برابر Domain Model باشد.



Persistence Concern

و

Domain Concern





باید تا حد ممکن جدا باشند.





============================================================

83\. DATABASE MIGRATION TESTING

============================================================



Migrationها باید در CI تست شوند.



حداقل:



Fresh Database

↓

All Migrations

↓

Success





و:



Existing Database

↓

New Migration

↓

Success





============================================================

84\. DATABASE TESTING

============================================================



باید تست شوند:



Constraints

Foreign Keys

Unique Rules

Transactions

Tenant Isolation

Soft Delete

Permissions

Repositories





============================================================

85\. TENANT ISOLATION TEST

============================================================



این تست الزامی است.



Tenant A

نباید بتواند:



Tenant B Data





را مشاهده یا تغییر دهد.





============================================================

86\. SECURITY TEST

============================================================



موارد زیر تست شوند:



Unauthorized Query

Cross-Tenant Access

Invalid Tenant ID

Deleted Tenant

Disabled User

Permission Bypass





============================================================

87\. DATA INTEGRITY TEST

============================================================



باید بررسی شود:



Foreign Key Integrity



Unique Constraints



Required Fields



Check Constraints



Transaction Rollback





============================================================

88\. DATABASE DOCUMENTATION

============================================================



برای هر Domain باید مشخص باشد:



Entity

Fields

Relationships

Constraints

Indexes

Tenant Scope

Audit Policy

Deletion Policy





============================================================

89\. ERD

============================================================



Tekarai باید ERD قابل نگهداری داشته باشد.



ERD باید:



\- Entities

\- Relationships

\- Cardinality

\- Important Constraints





را نمایش دهد.





============================================================

90\. DATABASE DIRECTORY STRUCTURE

============================================================



ساختار مفهومی:



backend/



&#x20;   apps/



&#x20;       identity/

&#x20;           models/

&#x20;           migrations/



&#x20;       tenants/

&#x20;           models/

&#x20;           migrations/



&#x20;       organization/

&#x20;           models/

&#x20;           migrations/



&#x20;       projects/

&#x20;           models/

&#x20;           migrations/



&#x20;       tasks/

&#x20;           models/

&#x20;           migrations/



&#x20;       documents/

&#x20;           models/

&#x20;           migrations/



&#x20;       workflows/

&#x20;           models/

&#x20;           migrations/



&#x20;       notifications/

&#x20;           models/

&#x20;           migrations/



&#x20;       reporting/

&#x20;           models/

&#x20;           migrations/



&#x20;       audit/

&#x20;           models/

&#x20;           migrations/



&#x20;       intelligence/

&#x20;           models/

&#x20;           migrations/





ساختار دقیق باید با App Architecture نهایی Tekarai هماهنگ باشد.





============================================================

91\. MODEL ORGANIZATION

============================================================



اگر Domain بزرگ شد:



models.py





نباید تبدیل به فایل هزاران خطی شود.



مدل‌ها باید در صورت نیاز:



models/

&#x20;   \_\_init\_\_.py

&#x20;   user.py

&#x20;   role.py

&#x20;   permission.py





ساختاربندی شوند.





============================================================

92\. MIGRATION ORGANIZATION

============================================================



Migrationها باید توسط Django مدیریت شوند.



Migration Fileها نباید دستی بازنویسی شوند مگر برای اصلاحات

کاملاً کنترل‌شده.





============================================================

93\. DATABASE CONFIGURATION

============================================================



Database Configuration باید از Environment دریافت شود.



موارد:



dbEngine

dbName

dbHost

dbPort

dbUser

dbPassword





نباید Hardcode شوند.





============================================================

94\. DEVELOPMENT DATABASE

============================================================



Development Environment می‌تواند SQL Server محلی یا Instance

مناسب توسعه داشته باشد.



Developer نباید مجبور باشد Production Database را استفاده کند.





============================================================

95\. TEST DATABASE

============================================================



Test Database باید جدا باشد.



Test نباید داده Production را تغییر دهد.





============================================================

96\. STAGING

============================================================



Staging باید Database مستقل داشته باشد.



Production Data نباید بدون Policy وارد Staging شود.





============================================================

97\. PRODUCTION

============================================================



Production Database باید:



\- Secured

\- Backed Up

\- Monitored

\- Audited

\- Restricted





باشد.





============================================================

98\. ENVIRONMENT ISOLATION

============================================================



Development

≠

Testing

≠

Staging

≠

Production





Databaseهای این محیط‌ها نباید اشتباه با یکدیگر متصل شوند.





============================================================

99\. DATA IMPORT

============================================================



Import باید:



\- Validated

\- Transaction-aware

\- Audited

\- Tenant-aware





باشد.





============================================================

100\. BULK OPERATIONS

============================================================



Bulk Insert/Update باید با دقت استفاده شود.



برای Datasetهای بزرگ:



\- Batch Processing

\- Bulk Operations

\- Transaction Management





در نظر گرفته شود.





============================================================

101\. DATA VALIDATION

============================================================



Validation باید در چند سطح باشد:



Frontend Validation

Backend Validation

Database Constraints





Database آخرین خط Integrity است.





============================================================

102\. DUPLICATE DATA

============================================================



Duplicate Prevention باید:



Application Logic

\+

Database Constraints





را در موارد مهم ترکیب کند.





============================================================

103\. SOFT DELETE QUERY POLICY

============================================================



Repositoryهای عادی باید Deleted Records را برنگردانند.



برای Administrative/Audit Query می‌توان Explicitly Deleted Data

را درخواست کرد.





============================================================

104\. TENANT DELETION

============================================================



حذف Tenant یک عملیات حساس است.



نباید:



DELETE Tenant





باعث حذف ناخواسته تمام داده‌ها شود.



باید Tenant Deletion Policy مشخص باشد:



Deactivate

Archive

Retention

Hard Delete





و فقط در شرایط مشخص اجرا شود.





============================================================

105\. USER DELETION

============================================================



User Deletion باید با Historical Data سازگار باشد.



Audit و Historical Records نباید به دلیل حذف User از بین بروند.





============================================================

106\. DATA OWNERSHIP

============================================================



هر Entity مهم باید مشخص کند:



Owner

Tenant

Creator

Updater





در صورت نیاز.





============================================================

107\. DOMAIN BOUNDARIES

============================================================



Database Design نباید باعث ایجاد Coupling غیرضروری بین Domainها شود.



مثال:



Task Domain

نباید اطلاعات داخلی Notification Domain را مستقیماً مدیریت کند.





============================================================

108\. CROSS-DOMAIN RELATIONSHIPS

============================================================



Cross-Domain Relationship باید آگاهانه طراحی شود.



هر Foreign Key باید دلیل معماری داشته باشد.





============================================================

109\. EVENT-BASED DATA UPDATE

============================================================



در موارد مناسب Domain Event می‌تواند باعث Update Domain دیگر شود.



مثال:



ProjectCreated

&#x20;↓

Notification

&#x20;↓

Audit





نباید تمام Domainها مستقیماً Database یکدیگر را تغییر دهند.





============================================================

110\. DATABASE AS SOURCE OF TRUTH

============================================================



Database Source of Truth برای:



Persistent Business Data





است.



Cache

و

Frontend State





Source of Truth نیستند.





============================================================

111\. CACHE CONSISTENCY

============================================================



اگر Cache استفاده شود باید مشخص باشد:



\- TTL

\- Invalidation

\- Ownership

\- Consistency Model





============================================================

112\. DATA VERSIONING

============================================================



برای Entityهای مهم در صورت نیاز باید Version History وجود داشته

باشد.



مثال:



Document

&#x20;↓

Version 1

Version 2

Version 3





============================================================

113\. DOCUMENT VERSIONING

============================================================



Document Update نباید فایل/رکورد قبلی را بدون Policy نابود کند.



DocumentVersion باید در صورت نیاز نگهداری شود.





============================================================

114\. OPTIMISTIC CONCURRENCY

============================================================



برای Resourceهایی که احتمال Edit همزمان دارند می‌توان:



version

updatedAt





یا مکانیزم مشابه استفاده کرد.





============================================================

115\. DATABASE DOCUMENTATION ARTIFACTS

============================================================



Phase 19 باید این مستندات را تولید کند:



DatabaseArchitecture.md



DatabaseSchema.md



DatabaseNamingConvention.md



DatabaseSecurity.md



DatabaseMigrationPolicy.md



DatabaseBackupPolicy.md



DatabasePerformance.md



databaseErd





============================================================

116\. IMPLEMENTATION ORDER

============================================================



STEP 1

SQL Server Environment



STEP 2

Database Configuration



STEP 3

Connection Management



STEP 4

Base Model



STEP 5

Tenant Model



STEP 6

Identity Models



STEP 7

Organization Models



STEP 8

Project Models



STEP 9

Task Models



STEP 10

Document Models



STEP 11

Workflow Models



STEP 12

Notification Models



STEP 13

Reporting Models



STEP 14

Audit Models



STEP 15

Intelligence Models



STEP 16

Constraints



STEP 17

Indexes



STEP 18

Repositories



STEP 19

Transactions



STEP 20

Tenant Isolation



STEP 21

Soft Delete



STEP 22

Audit Integration



STEP 23

Seed Data



STEP 24

Migration Strategy



STEP 25

Backup Strategy



STEP 26

Monitoring



STEP 27

Performance Testing



STEP 28

Security Testing



STEP 29

Tenant Isolation Testing



STEP 30

Migration Testing



STEP 31

ERD



STEP 32

Database Documentation





============================================================

117\. DEFINITION OF DONE

============================================================



Phase 19 فقط زمانی Done است که:



\[ ] SQL Server Configuration کامل باشد.



\[ ] Development Database آماده باشد.



\[ ] Test Database آماده باشد.



\[ ] Production Database Strategy تعریف شده باشد.



\[ ] Base Model ایجاد شده باشد.



\[ ] Tenant Model ایجاد شده باشد.



\[ ] Identity Models ایجاد شده باشند.



\[ ] Organization Models ایجاد شده باشند.



\[ ] Project Models ایجاد شده باشند.



\[ ] Task Models ایجاد شده باشند.



\[ ] Document Models ایجاد شده باشند.



\[ ] Workflow Models ایجاد شده باشند.



\[ ] Notification Models ایجاد شده باشند.



\[ ] Reporting Models ایجاد شده باشند.



\[ ] Audit Models ایجاد شده باشند.



\[ ] Intelligence Models ایجاد شده باشند.



\[ ] Foreign Keys صحیح باشند.



\[ ] Unique Constraints تعریف شده باشند.



\[ ] Check Constraints لازم ایجاد شده باشند.



\[ ] Index Strategy پیاده شده باشد.



\[ ] Tenant Isolation پیاده شده باشد.



\[ ] Soft Delete Policy پیاده شده باشد.



\[ ] Audit Fields پیاده شده باشند.



\[ ] Repository Layer پیاده شده باشد.



\[ ] Transaction Strategy پیاده شده باشد.



\[ ] Migration Strategy کامل باشد.



\[ ] Seed Strategy وجود داشته باشد.



\[ ] Backup Strategy تعریف شده باشد.



\[ ] Restore Procedure تعریف شده باشد.



\[ ] Monitoring تعریف شده باشد.



\[ ] Health Check وجود داشته باشد.



\[ ] Database Security بررسی شده باشد.



\[ ] Tenant Isolation Tests سبز باشند.



\[ ] Constraint Tests سبز باشند.



\[ ] Repository Tests سبز باشند.



\[ ] Migration Tests سبز باشند.



\[ ] Performance Tests پایه سبز باشند.



\[ ] ERD تهیه شده باشد.



\[ ] Database Documentation کامل باشد.





============================================================

118\. ممنوعیت‌های Phase 19

============================================================



هرگز:



\- Database را مستقیم از Frontend مصرف نکن.

\- SQL Server Admin را برای Application استفاده نکن.

\- Tenant Isolation را فقط به Frontend واگذار نکن.

\- Business Ruleهای مهم را فقط در Python نگه ندار.

\- Unique Rule مهم را فقط در Application بررسی نکن.

\- Foreign Key واقعی را با UUID خام جایگزین نکن.

\- همه چیز را CASCADE نکن.

\- همه چیز را Soft Delete نکن.

\- همه چیز را JSON نکن.

\- برای همه Fieldها Index نساز.

\- Query بدون Pagination روی داده بزرگ اجرا نکن.

\- Production Database را در Development استفاده نکن.

\- Production Secret را در Git ذخیره نکن.

\- Migration History را بدون دلیل حذف نکن.

\- Database را دستی و خارج از Migration تغییر نده.

\- Hard Delete را بدون Policy انجام نده.

\- Database Admin را به Application Credential تبدیل نکن.

\- Cross-Tenant Query را بدون Explicit Scope اجرا نکن.





============================================================

119\. FINAL ARCHITECTURAL RESULT

============================================================



در پایان Phase 19، Tekarai باید یک Data Platform استاندارد داشته

باشد که تمام Platformهای قبلی و آینده بتوانند روی آن قرار بگیرند.



ساختار نهایی:



USER

&#x20;↓

GUI

&#x20;↓

API

&#x20;↓

APPLICATION

&#x20;↓

REPOSITORY

&#x20;↓

ORM

&#x20;↓

SQL SERVER

&#x20;↓

PERSISTENT DATA





و در تمام مسیر:



AUTHENTICATION

\+

AUTHORIZATION

\+

TENANT ISOLATION

\+

DATA VALIDATION

\+

AUDIT

\+

TRANSACTION

\+

OBSERVABILITY





باید رعایت شود.





============================================================

120\. اصل نهایی Phase 19

============================================================



Database نباید فقط محلی برای ذخیره Objectهای Python باشد.



Database باید یک Data Foundation واقعی برای Tekarai باشد.



تمام طراحی باید به گونه‌ای انجام شود که Tekarai بتواند در آینده:



\- Tenantهای بیشتر

\- Userهای بیشتر

\- Data بیشتر

\- Domainهای بیشتر

\- Integrationهای بیشتر

\- Reportهای بیشتر

\- AI Features بیشتر

\- Project Intelligence بیشتر

\- Workflowهای پیچیده‌تر





را بدون بازطراحی بنیادی Database پشتیبانی کند.



Phase 19 زمانی موفق است که Database:



STABLE

\+

SECURE

\+

CONSISTENT

\+

TENANT-SAFE

\+

AUDITABLE

\+

PERFORMANT

\+

MIGRATION-SAFE

\+

SCALABLE





باشد.

