============================================================

TEKARAI — PHASE 05

DATABASE DICTIONARY + BUSINESS RULES

============================================================



هدف این فاز:



در Phase 4 معماری ERD و ساختار کلی Database طراحی شد.



در Phase 5 باید این طراحی از سطح:



"چه Entityهایی داریم؟"



به سطح:



"دقیقاً هر Entity چه داده‌ای دارد و چه قوانینی بر آن حاکم است؟"



تبدیل شود.



خروجی این فاز باید آن‌قدر دقیق باشد که یک Developer بتواند بدون حدس زدن:



\- SQL Schema

\- Django Models

\- Constraints

\- Indexes

\- Validation Rules

\- Domain Rules

\- Services

\- Repositories

\- API Validation



را بر اساس آن پیاده‌سازی کند.



در این فاز هیچ Business Rule مهمی نباید شفاهی یا ضمنی باقی بماند.



============================================================

1\. PHASE 5 PRINCIPLE

============================================================



Database Dictionary:



WHAT DATA EXISTS?



Business Rules:



WHAT IS ALLOWED?



Domain Rules:



WHAT MUST ALWAYS BE TRUE?



Validation Rules:



WHAT MUST BE REJECTED?



این چهار مفهوم باید از یکدیگر تفکیک شوند.



============================================================

2\. DATABASE DICTIONARY

============================================================



برای هر Entity باید Dictionary کامل ایجاد شود.



فرمت استاندارد:



Entity Name:

Domain:

Purpose:

Owner:

Tenant Scoped:

Soft Deletable:

Auditable:



Fields:



\- Field Name

\- Data Type

\- Nullable

\- Default

\- Length / Precision

\- Required

\- Unique

\- Indexed

\- Foreign Key

\- Description



============================================================

3\. FIELD NAMING

============================================================



نام‌گذاری Database باید استاندارد و یکدست باشد.



استفاده:



camelCase



مثال:



createdAt

updatedAt

tenantId

employeeId

projectId



ممنوع:



created\_at

TenantId

EmployeeID



============================================================

4\. FIELD TYPES

============================================================



Data Type باید بر اساس مفهوم واقعی داده انتخاب شود.



نمونه:



UUID:

Entity Identity



VARCHAR:

Short Text



NVARCHAR:

Unicode Text



TEXT:

Long Text



BOOLEAN:

True/False



DATETIME:

Timestamp



DECIMAL:

Money / Precision Values



INTEGER:

Counters / Quantities



JSON:

Dynamic Extension Data



هر استفاده از JSON باید مستند شود.



============================================================

5\. REQUIRED VS OPTIONAL

============================================================



برای هر Field باید مشخص شود:



Required



یا:



Optional



Optional بودن نباید صرفاً به خاطر راحتی Developer باشد.



اگر Business Rule می‌گوید مقدار باید وجود داشته باشد:



Database و Application هر دو باید آن را enforce کنند.



============================================================

6\. NULL POLICY

============================================================



NULL باید معنی مشخص داشته باشد.



نباید از NULL به عنوان:



"هر چیزی"



استفاده شود.



مثلاً:



deletedAt = NULL



یعنی Entity حذف نشده است.



اما:



description = NULL



باید دقیقاً مشخص کند که آیا:



Description وجود ندارد



یا:



Description هنوز ثبت نشده است.



============================================================

7\. DEFAULT VALUE POLICY

============================================================



Default فقط زمانی تعریف شود که از نظر Domain منطقی باشد.



مثال مناسب:



isActive = TRUE



مثال نامناسب:



status = "active"



بدون اینکه Domain Rule آن را تعریف کرده باشد.



============================================================

8\. ENUM POLICY

============================================================



برای Statusها و Typeهای کنترل‌شده باید مجموعه مقادیر مجاز مشخص باشد.



مثلاً:



TaskStatus:



TODO

IN\_PROGRESS

BLOCKED

DONE

CANCELLED



مقدار خارج از مجموعه نباید پذیرفته شود.



============================================================

9\. TENANT RULES

============================================================



هر Entity باید یکی از این حالات را داشته باشد:



GLOBAL



یا:



TENANT\_SCOPED



یا:



HYBRID



GLOBAL:



داده مستقل از Tenant است.



TENANT\_SCOPED:



هر رکورد متعلق به یک Tenant است.



HYBRID:



برخی داده‌ها Global و برخی Tenant-specific هستند.



این وضعیت باید برای تک‌تک Entityها مشخص شود.



============================================================

10\. TENANT ISOLATION RULE

============================================================



هیچ Query عادی نباید بتواند داده Tenant دیگر را برگرداند.



تمام Repository/Selectorها باید Tenant Context داشته باشند.



مثال:



getProject(projectId, tenantId)



نباید صرفاً:



getProject(projectId)



باشد.



Tenant Isolation یک Security Requirement است، نه فقط یک Feature.



============================================================

11\. UNIQUE RULES

============================================================



برای هر Entity باید Unique Ruleها مشخص شوند.



مثال:



Employee Number:



UNIQUE(tenantId, employeeNumber)



Project Code:



UNIQUE(tenantId, code)



Department Code:



UNIQUE(tenantId, code)



اما:



Tenant.code



می‌تواند Global Unique باشد.



============================================================

12\. BUSINESS ID VS DATABASE ID

============================================================



هر Entity می‌تواند دو نوع Identity داشته باشد:



Technical Identity:



id UUID



Business Identity:



code / number / reference



مثال:



Project:



id = UUID



code = PRJ-2026-001



این دو نباید با یکدیگر ترکیب شوند.



============================================================

13\. ENTITY STATUS

============================================================



هر Status باید Business Meaning داشته باشد.



مثال:



Project:



DRAFT

PLANNED

ACTIVE

ON\_HOLD

COMPLETED

CANCELLED

ARCHIVED



برای هر Status باید مشخص شود:



\- چه زمانی ایجاد می‌شود.

\- چه کسی می‌تواند آن را تغییر دهد.

\- به چه Statusهایی می‌تواند برود.

\- آیا برگشت مجاز است یا خیر.



============================================================

14\. STATE TRANSITION

============================================================



State Machine باید برای Entityهای مهم تعریف شود.



مثال:



DRAFT

&#x20; ↓

PLANNED

&#x20; ↓

ACTIVE

&#x20; ↓

COMPLETED



و:



ACTIVE

&#x20; ↓

ON\_HOLD

&#x20; ↓

ACTIVE



اما:



COMPLETED

&#x20; X

ACTIVE



نباید بدون Rule مشخص مجاز باشد.



============================================================

15\. USER BUSINESS RULES

============================================================



User و Employee مستقل هستند.



User مسئول:



Identity



Employee مسئول:



Employment



یک Employee می‌تواند User داشته باشد.



اما هر Employee الزاماً نباید User باشد.



این موضوع باید در Business Rules صریح باشد.



============================================================

16\. EMPLOYEE RULES

============================================================



Employee باید بتواند:



\- در سازمان قرار گیرد.

\- Position داشته باشد.

\- Manager داشته باشد.

\- Assignment داشته باشد.

\- Employment History داشته باشد.

\- Skill داشته باشد.

\- Certification داشته باشد.

\- Evaluation داشته باشد.



تغییر Department نباید اطلاعات Assignment قبلی را حذف کند.



============================================================

17\. ORGANIZATION RULES

============================================================



Organization Structure باید Hierarchical باشد.



هر OrganizationUnit می‌تواند Parent داشته باشد.



اما:



OrganizationUnit نباید Parent خودش باشد.



Cycle در Organization Hierarchy ممنوع است.



مثال غیرمجاز:



A → B → C → A



============================================================

18\. PROJECT RULES

============================================================



Project باید:



\- Tenant داشته باشد.

\- Owner داشته باشد.

\- Status داشته باشد.

\- Code داشته باشد.



Project Code در Tenant باید Unique باشد.



Project بدون Owner فقط در Statusهای مشخص مجاز است.



Project پس از Completion نباید بدون Permission ویژه تغییر کند.



تمام تغییرات مهم Project باید Audit شوند.



============================================================

19\. PROJECT MEMBER RULES

============================================================



ProjectMember باید:



projectId

employee/userId

role

joinedAt

leftAt



داشته باشد.



یک فرد نباید همزمان چند رکورد Active برای یک Project داشته باشد.



Constraint منطقی:



ONE ACTIVE MEMBERSHIP PER PERSON PER PROJECT



============================================================

20\. TASK RULES

============================================================



Task باید:



\- Owner/Assignee مشخص داشته باشد.

\- Status داشته باشد.

\- Priority داشته باشد.

\- Created timestamp داشته باشد.

\- Tenant Context داشته باشد.



Task متعلق به Project می‌تواند باشد.



اما Task باید در صورت نیاز مستقل از Project نیز قابل استفاده باشد.



============================================================

21\. TASK DEPENDENCY RULE

============================================================



Task Dependency باید از:



Task → Task



تشکیل شود.



Task نباید به خودش وابسته باشد.



Cycle Dependency باید جلوگیری شود.



مثال غیرمجاز:



A → B

B → C

C → A



============================================================

22\. DOCUMENT RULES

============================================================



Document باید:



\- Owner

\- Type

\- Status

\- Version



داشته باشد.



Document Version نباید overwrite شود.



هر تغییر مهم:



New Version



ایجاد می‌کند.



============================================================

23\. DOCUMENT VERSION RULE

============================================================



برای هر Document:



Version Number



باید قابل تشخیص باشد.



مثال:



1

2

3



نسخه حذف‌شده نباید باعث از بین رفتن تاریخچه شود.



آخرین Version باید مشخص باشد.



============================================================

24\. ASSET RULES

============================================================



هر Asset باید:



\- Asset Type

\- Status

\- Owner

\- Location



داشته باشد.



Assignmentهای Asset باید History داشته باشند.



تغییر Owner نباید Owner قبلی را حذف کند.



============================================================

25\. DEVICE RULES

============================================================



Device باید:



\- Unique Identity

\- Device Type

\- Status

\- Registration Information



داشته باشد.



Device Registration باید قابل Audit باشد.



Heartbeat باید Timestamp داشته باشد.



Device Offline بودن باید بر اساس Policy تعریف شود.



نباید صرفاً با:



isOnline



تصمیم‌گیری شود.



============================================================

26\. MAINTENANCE RULES

============================================================



Maintenance Work Order باید:



\- Asset/Device

\- Priority

\- Status

\- Requester

\- Assignee

\- Schedule



را پشتیبانی کند.



Work Orderهای Completed نباید بدون Permission ویژه تغییر کنند.



============================================================

27\. COMMUNICATION RULES

============================================================



Conversation:



باید حداقل یک Owner/Creator داشته باشد.



ConversationMember:



هر User نباید بتواند بدون Permission عضو Conversation خصوصی شود.



Message:



پس از ارسال باید Immutable یا محدود به Edit Policy باشد.



Message Edit باید Audit شود.



Message Delete:



Soft Delete



یا:



Tombstone



بسته به Policy.



============================================================

28\. VOICE CALL RULES

============================================================



VoiceCall باید شامل:



caller

participants

startedAt

endedAt

status

callType



باشد.



Call Type:



DIRECT

GROUP



Voice Call نباید Audio Stream را در Database ذخیره کند.



Database فقط Metadata را نگه می‌دارد.



Media:



WebRTC



است.



============================================================

29\. VIDEO MEETING RULES

============================================================



Meeting باید:



\- Host

\- Participants

\- Start Time

\- End Time

\- Status



داشته باشد.



Meeting می‌تواند Recording داشته باشد.



Recording باید Reference به Storage داشته باشد.



Binary Video نباید به صورت عادی داخل Database ذخیره شود.



============================================================

30\. PRESENCE RULES

============================================================



Presence:



ONLINE

AWAY

BUSY

OFFLINE

DO\_NOT\_DISTURB



می‌تواند باشد.



Presence State باید Realtime باشد.



Database نباید تنها منبع Truth برای Presence لحظه‌ای باشد.



Realtime:



Redis / Channels



Persistence:



Database



============================================================

31\. NOTIFICATION RULES

============================================================



Notification باید:



Recipient



داشته باشد.



Notification Delivery باید Status داشته باشد:



PENDING

SENT

DELIVERED

FAILED

READ



Delivery Failure باید قابل Retry باشد.



============================================================

32\. AUDIT RULES

============================================================



تمام عملیات حساس باید Audit شوند.



حداقل:



CREATE

UPDATE

DELETE

LOGIN

LOGOUT

PERMISSION\_CHANGE

ROLE\_CHANGE

EXPORT

DOWNLOAD

APPROVAL

REJECTION



Audit Event باید شامل Actor و Timestamp باشد.



============================================================

33\. AUDIT IMMUTABILITY

============================================================



Audit Record نباید توسط User عادی:



UPDATE



یا:



DELETE



شود.



Audit باید Append-Oriented باشد.



============================================================

34\. WORKFLOW RULES

============================================================



Workflow باید Generic باشد.



Workflow Instance باید وضعیت مستقل از Definition داشته باشد.



Workflow Version نباید با تغییر Definitionهای قبلی overwrite شود.



هر Approval باید:



Actor

Timestamp

Decision

Comment



داشته باشد.



============================================================

35\. APPROVAL RULE

============================================================



Approval می‌تواند:



APPROVED

REJECTED

PENDING

CANCELLED



باشد.



Rejected Approval باید Reason داشته باشد مگر اینکه Business Rule خلاف آن را تعیین کند.



============================================================

36\. NOTIFICATION + EVENT RULE

============================================================



Notification نباید مستقیماً در Domain Core ایجاد شود.



Domain Event:



مثلاً:



TaskCompleted



سپس:



Notification Handler



Notification ایجاد می‌کند.



این طراحی باعث کاهش Coupling می‌شود.



============================================================

37\. AI RULES

============================================================



AI Output نباید به عنوان حقیقت قطعی سیستم ذخیره شود.



Prediction:



Prediction



است.



Fact:



Business Data



است.



AI باید بتواند:



Model

Model Version

Provider

Prompt/Context Reference

Input Reference

Output

Confidence

Timestamp



را ثبت کند.



============================================================

38\. AI AUDIT

============================================================



AI Decisionهای مهم باید قابل Trace باشند.



باید مشخص باشد:



کدام Model؟



کدام Version؟



چه Inputی؟



چه زمانی؟



چه Outputی؟



چه Confidenceی؟



این موضوع برای Explainability حیاتی است.



============================================================

39\. INTEGRATION RULES

============================================================



External Integration باید:



Connection



داشته باشد.



Credential نباید Plain Text ذخیره شود.



Integration Execution باید:



STARTED

SUCCESS

FAILED

RETRYING



را پشتیبانی کند.



خطاهای Integration باید قابل Trace باشند.



============================================================

40\. FILE RULES

============================================================



File Metadata:



نام

Size

Mime Type

Checksum

Storage Provider

Storage Key



را نگه می‌دارد.



Binary:



Object/File Storage



است.



Checksum برای تشخیص تغییر/تکرار فایل استفاده شود.



============================================================

41\. SECURITY RULES

============================================================



Authorization باید در Application Layer enforce شود.



Database فقط بخشی از Integrity را enforce می‌کند.



هیچ API نباید صرفاً به User Authentication اکتفا کند.



Authentication:



Who are you?



Authorization:



What are you allowed to do?



Tenant Authorization:



Which Tenant's data may you access?



این سه مفهوم باید جدا باشند.



============================================================

42\. PERMISSION MODEL

============================================================



Permission باید Action-Based باشد.



مثال:



project.view

project.create

project.update

project.delete

project.approve



Role:



مجموعه Permissionها



User:



عضو Roleها



اما Permissionهای خاص User نیز در صورت نیاز ممکن است وجود داشته باشند.



============================================================

43\. ROLE SCOPE

============================================================



Role می‌تواند Scope داشته باشد.



مثال:



GLOBAL

TENANT

ORGANIZATION

DEPARTMENT

PROJECT



مثلاً:



Project Manager



نباید الزاماً به تمام Projectهای Tenant دسترسی داشته باشد.



============================================================

44\. DATA ACCESS RULE

============================================================



Access Control باید چندلایه باشد:



1\. Authentication

2\. Tenant Isolation

3\. Permission

4\. Role

5\. Scope

6\. Object-Level Permission



مثال:



User ممکن است:



project.update



داشته باشد.



اما فقط برای Projectهایی که:



Tenant خودش



و:



Scope مجاز



هستند.



============================================================

45\. CROSS-DOMAIN RULE

============================================================



Domainها نباید مستقیماً Business Ruleهای Domain دیگر را اجرا کنند.



مثلاً:



Task Domain



نباید مستقیماً:



Notification Database



را Update کند.



به جای آن:



TaskCompleted Event



منتشر شود.



============================================================

46\. EVENT RULE

============================================================



Event باید:



Event ID

Event Type

Aggregate ID

Tenant ID

Occurred At

Actor ID

Metadata



داشته باشد.



Eventها باید قابل Trace باشند.



============================================================

47\. AGGREGATE RULE

============================================================



هر Aggregate باید:



Aggregate Root



داشته باشد.



Entityهای داخلی Aggregate نباید بدون Root به صورت آزاد تغییر داده شوند.



مثال:



Project



می‌تواند Aggregate Root باشد.



ProjectMember



در این حالت باید از طریق Project مدیریت شود.



============================================================

48\. AGGREGATE SIZE

============================================================



Aggregate نباید بیش از حد بزرگ شود.



هدف:



Consistency Boundary



است.



تمام Entityهای مرتبط الزاماً داخل یک Aggregate نیستند.



============================================================

49\. TRANSACTION RULE

============================================================



هر Use Case باید Transaction Boundary مشخص داشته باشد.



مثلاً:



CreateProject



می‌تواند شامل:



Project

ProjectMember

AuditEvent



باشد.



تمام عملیات لازم باید Atomic باشند.



============================================================

50\. CONCURRENCY RULE

============================================================



برای Entityهای حساس:



Optimistic Concurrency



باید در نظر گرفته شود.



نمونه:



version



یا:



rowVersion



نباید User بتواند تغییرات شخص دیگر را بدون اطلاع overwrite کند.



============================================================

51\. DATE RULE

============================================================



تمام Timestampها:



UTC



ذخیره شوند.



Timezone کاربر/Tenant هنگام نمایش اعمال شود.



============================================================

52\. MONEY RULE

============================================================



Money:



Decimal



است.



Float ممنوع.



Currency باید مشخص باشد.



مثال:



amount = 125000.50

currency = EUR



============================================================

53\. DATA VALIDATION LAYERS

============================================================



Validation در چند Layer انجام می‌شود:



Layer 1:

API Validation



Layer 2:

Application Validation



Layer 3:

Domain Validation



Layer 4:

Database Constraint



هیچ Layer نباید جای دیگری را به طور کامل حذف کند.



============================================================

54\. DATABASE CONSTRAINTS

============================================================



Constraintهای مهم باید در Database نیز enforce شوند.



نمونه:



UNIQUE

FOREIGN KEY

NOT NULL

CHECK



اما Business Ruleهای پیچیده باید در Domain/Application باقی بمانند.



============================================================

55\. CHECK CONSTRAINT

============================================================



برای Ruleهای ساده Database-level از CHECK استفاده شود.



مثلاً:



amount >= 0



اما Ruleهای پیچیده مانند:



"Employee فقط در صورتی می‌تواند Manager شود که..."



نباید به CHECK Constraint پیچیده تبدیل شوند.



============================================================

56\. INDEX DICTIONARY

============================================================



برای هر Index باید ثبت شود:



Index Name

Table

Columns

Unique?

Purpose

Expected Query

Tenant Scoped?

Estimated Importance



Index بدون Use Case نباید ایجاد شود.



============================================================

57\. FOREIGN KEY DICTIONARY

============================================================



برای هر FK:



Source Entity

Source Field

Target Entity

Target Field

Cardinality

Delete Policy

Nullable

Tenant Rule



ثبت شود.



============================================================

58\. BUSINESS RULE FORMAT

============================================================



تمام Business Ruleها باید با ID ثبت شوند.



فرمت:



BR-001



Name:



Tenant Isolation



Rule:



A User may only access data belonging to an authorized Tenant.



Severity:



CRITICAL



Enforcement:



Application + Repository + Database Integrity



============================================================

59\. RULE CATEGORIES

============================================================



Business Ruleها باید دسته‌بندی شوند:



BR:



Business Rule



SEC:



Security Rule



DAT:



Data Rule



TEN:



Tenant Rule



AUD:



Audit Rule



WF:



Workflow Rule



AI:



AI Rule



COM:



Communication Rule



INT:



Integration Rule



PER:



Permission Rule



PERF:



Performance Rule



============================================================

60\. BUSINESS RULE PRIORITY

============================================================



هر Rule باید Priority داشته باشد:



CRITICAL

HIGH

MEDIUM

LOW



Ruleهای:



Tenant Isolation

Authentication

Authorization

Audit



باید CRITICAL باشند.



============================================================

61\. ERROR RULES

============================================================



برای Ruleهای قابل نقض باید Error Code تعریف شود.



مثال:



TENANT\_ACCESS\_DENIED



PROJECT\_ALREADY\_COMPLETED



INVALID\_STATE\_TRANSITION



DUPLICATE\_BUSINESS\_CODE



PERMISSION\_DENIED



INVALID\_WORKFLOW\_TRANSITION



این Error Codeها بعداً وارد API Error Architecture می‌شوند.



============================================================

62\. BUSINESS RULE TRACEABILITY

============================================================



هر Rule باید قابل Trace باشد.



Business Rule:



BR-PROJECT-001



باید مشخص کند به:



Entity

Use Case

Service

API

Test



متصل است.



هدف:



Requirement

→ Rule

→ Implementation

→ Test



============================================================

63\. DATABASE DICTIONARY DELIVERABLE

============================================================



باید فایل:



DatabaseDictionary.md



ایجاد شود.



برای تمام Entityهای Phase 4.



============================================================

64\. ENTITY CATALOG DELIVERABLE

============================================================



باید فایل:



EntityCatalog.md



شامل تمام Entityها باشد.



برای هر Entity:



Domain

Owner

Purpose

Tenant

Identity

Lifecycle

Audit

Soft Delete



ثبت شود.



============================================================

65\. FIELD CATALOG

============================================================



باید فایل:



FieldCatalog.md



ساخته شود.



برای هر Field:



Entity

Name

Type

Required

Nullable

Default

Unique

Index

FK

Description



ثبت شود.



============================================================

66\. BUSINESS RULE CATALOG

============================================================



باید فایل:



BusinessRuleCatalog.md



ساخته شود.



تمام Ruleها با ID یکتا.



============================================================

67\. CONSTRAINT CATALOG

============================================================



باید فایل:



ConstraintCatalog.md



شامل:



Primary Keys

Foreign Keys

Unique Constraints

Check Constraints

Delete Policies



باشد.



============================================================

68\. INDEX CATALOG

============================================================



باید فایل:



IndexCatalog.md



شامل:



Index

Table

Columns

Purpose

Query Pattern



باشد.



============================================================

69\. STATE MACHINE CATALOG

============================================================



باید فایل:



StateMachineCatalog.md



شامل State Machineهای:



Project

Task

Document

Workflow

Maintenance

Notification

Integration

Device

Call

Meeting



باشد.



برای هر State Machine:



States

Allowed Transitions

Forbidden Transitions

Actor

Permission

Side Effects



ثبت شود.



============================================================

70\. ERROR CODE CATALOG

============================================================



باید فایل:



ErrorCodeCatalog.md



ساخته شود.



تمام Error Codeها باید:



Unique

Stable

Documented



باشند.



============================================================

71\. DATA RETENTION RULES

============================================================



برای هر Domain:



Retention Period



باید تعیین شود.



مثال:



Audit:



Long-Term



Documents:



Long-Term



Notifications:



Configurable



Telemetry:



Configurable



Temporary Integration Logs:



Configurable



هیچ داده‌ای نباید بدون Policy وارد Production شود.



============================================================

72\. MIGRATION RULE

============================================================



Migration باید:



Versioned



Reproducible



Reviewable



باشد.



Migration دستی روی Production ممنوع است مگر در Emergency Procedure مستند.



============================================================

73\. DATABASE SEED RULE

============================================================



Reference Data باید از Business Data جدا باشد.



مثلاً:



Task Statuses



Permission Definitions



Notification Channels



System Roles



نباید با داده User مخلوط شوند.



============================================================

74\. REFERENCE DATA

============================================================



Reference Data باید:



Stable ID

Code

Name

Description

Active State



داشته باشد.



Code باید Stable باشد.



============================================================

75\. PRODUCTION DATA RULE

============================================================



Development Data نباید با Production Data مخلوط شود.



Seedهای Development باید جدا باشند.



هیچ Password یا Secret واقعی نباید در Seed قرار گیرد.



============================================================

76\. BACKUP REQUIREMENT

============================================================



Database Architecture باید Backup Strategy داشته باشد.



حداقل:



Full Backup

Differential Backup

Transaction Log Backup



Retention:



طبق Business/Compliance Policy.



============================================================

77\. RECOVERY

============================================================



باید مشخص شود:



RPO



Recovery Point Objective



و:



RTO



Recovery Time Objective



برای Production.



============================================================

78\. DATA MIGRATION

============================================================



در صورت تغییر Schema:



Migration باید:



Backward Compatible



تا حد امکان باشد.



برای تغییرات بزرگ:



Expand

Migrate

Contract



Pattern



استفاده شود.



============================================================

79\. DATA INTEGRITY

============================================================



هیچ Domain نباید بتواند داده Invalid تولید کند.



Integrity باید از طریق:



Domain Rules

Application Services

Database Constraints



حفظ شود.



============================================================

80\. PHASE 5 COMPLETION CRITERIA

============================================================



Phase 5 فقط زمانی Complete است که:



\[ ] Database Dictionary کامل شده باشد.



\[ ] تمام Entityها Dictionary داشته باشند.



\[ ] تمام Fieldها تعریف شده باشند.



\[ ] Data Typeها مشخص شده باشند.



\[ ] Nullable/Required مشخص شده باشد.



\[ ] Defaultها مشخص شده باشند.



\[ ] Unique Rules مشخص شده باشند.



\[ ] FKها مشخص شده باشند.



\[ ] Indexها مشخص شده باشند.



\[ ] Delete Policyها مشخص شده باشند.



\[ ] Tenant Rules مشخص شده باشند.



\[ ] Audit Rules مشخص شده باشند.



\[ ] Soft Delete Rules مشخص شده باشند.



\[ ] State Machineها مشخص شده باشند.



\[ ] Business Ruleها ID داشته باشند.



\[ ] Security Rules تعریف شده باشند.



\[ ] Permission Rules تعریف شده باشند.



\[ ] Error Codeها تعریف شده باشند.



\[ ] Data Retention مشخص شده باشد.



\[ ] Migration Strategy مشخص شده باشد.



\[ ] Backup Strategy مشخص شده باشد.



\[ ] Recovery Strategy مشخص شده باشد.



\[ ] Traceability تعریف شده باشد.



============================================================

81\. PHASE 5 OUTPUTS

============================================================



در پایان Phase 5 حداقل باید این فایل‌ها وجود داشته باشند:



DatabaseDictionary.md



EntityCatalog.md



FieldCatalog.md



BusinessRuleCatalog.md



ConstraintCatalog.md



IndexCatalog.md



StateMachineCatalog.md



ErrorCodeCatalog.md



DataRetentionPolicy.md



DatabaseMigrationStrategy.md



DatabaseBackupStrategy.md



DataGovernance.md



============================================================

82\. IMPORTANT IMPLEMENTATION RULE

============================================================



تا زمانی که Phase 5 تأیید نشده:



Django Modelهای نهایی ساخته نشوند.



ممنوع:



شروع تصادفی Model نویسی



ساخت Migration بر اساس حدس



ساخت API قبل از مشخص شدن Ruleها



ساخت Serializer قبل از مشخص شدن Contract



ساخت Permission قبل از مشخص شدن Authorization Model



============================================================

83\. PHASE 5 FINAL GATE

============================================================



در پایان Phase 5 باید بتوانیم برای هر Entity پاسخ دقیق این سؤال‌ها را بدهیم:



این Entity چیست؟



چرا وجود دارد؟



مالک آن کدام Domain است؟



Tenant دارد؟



Primary Key چیست؟



Business Identity چیست؟



چه Fieldهایی دارد؟



کدام Fieldها Required هستند؟



کدام Nullable هستند؟



Default چیست؟



چه Constraintهایی دارد؟



چه Indexهایی دارد؟



چه Relationshipهایی دارد؟



چه کسی می‌تواند آن را ایجاد کند؟



چه کسی می‌تواند آن را تغییر دهد؟



چه کسی می‌تواند آن را حذف کند؟



چه Statusهایی دارد؟



State Transitionها چیست؟



چه Business Ruleهایی دارد؟



چه Permissionهایی دارد؟



چه Auditهایی دارد؟



چه Errorهایی ممکن است رخ دهد؟



چه مدت نگهداری می‌شود؟



چگونه Backup می‌شود؟



چگونه Restore می‌شود؟



چگونه Test می‌شود؟



============================================================

PHASE 5 RESULT

============================================================



بعد از تکمیل این فاز:



Architecture

&#x20;       ↓

Capability Map

&#x20;       ↓

Domain Architecture

&#x20;       ↓

Enterprise ERD

&#x20;       ↓

Database Dictionary

&#x20;       ↓

Business Rules

&#x20;       ↓

Database Constraints

&#x20;       ↓

Implementation Specification



به یک نقطه پایدار می‌رسد.



از اینجا به بعد می‌توانیم وارد Implementation شویم.



============================================================

NEXT PHASE

============================================================



PHASE 6



DOMAIN IMPLEMENTATION ARCHITECTURE



در Phase 6 مشخص می‌شود:



\- Django App Boundaries

\- Domain Packages

\- Entities

\- Value Objects

\- Aggregates

\- Repositories

\- Domain Services

\- Application Services

\- Commands

\- Queries

\- Events

\- DTOs

\- Dependency Injection

\- Module Boundaries



و سپس آماده ورود کنترل‌شده به پیاده‌سازی واقعی Tekarai می‌شویم.



============================================================

END OF PHASE 05

============================================================

