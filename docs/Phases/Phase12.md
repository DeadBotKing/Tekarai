PHASE 12 — NOTIFICATIONS \& COMMUNICATION FOUNDATION

12.0 هدف فاز



در این فاز باید زیرساخت Enterprise برای Communication و Notification در Meryx طراحی و پیاده‌سازی شود.



این فاز نباید صرفاً به ساخت یک Notification Model محدود شود.



هدف این است که Meryx بتواند از یک هسته‌ی یکپارچه برای:



In-App Notification

Email Notification

Push Notification

SMS Notification

System Notification

Event-based Notification

Notification Template

User Preferences

Notification Delivery

Delivery Status

Retry

Scheduling

Read/Unread State

Priority

Multi-Tenant Notification

Auditability



استفاده کند.



معماری باید از ابتدا برای اضافه شدن کانال‌های جدید بدون تغییر Core طراحی شود.



12.1 اصل معماری



Notification نباید مستقیماً به Business Logic متصل شود.



اشتباه:



TaskService

&#x20;   ↓

send\_email()



معماری صحیح:



Business Event

&#x20;     ↓

Event Bus

&#x20;     ↓

Notification Application Layer

&#x20;     ↓

Notification Policy

&#x20;     ↓

Notification Template

&#x20;     ↓

Notification Delivery

&#x20;     ↓

Channel Adapter

&#x20;     ↓

Email / SMS / Push / In-App



Business Domain فقط Event تولید می‌کند.



Notification Platform تصمیم می‌گیرد:



آیا Notification ارسال شود؟

برای چه کسی؟

با چه Template؟

با چه Channel؟

با چه Priority؟

در چه زمانی؟

چند بار Retry شود؟

12.2 Notification Domain



Notification باید یک Bounded Context مستقل باشد.



ساختار مفهومی:



Notification Context

│

├── Notification

├── NotificationRecipient

├── NotificationTemplate

├── NotificationChannel

├── NotificationPreference

├── NotificationDelivery

├── NotificationAttempt

├── NotificationSchedule

└── NotificationEvent

12.3 Notification



موجودیت اصلی Notification.



نمونه مفهومی:



Notification

│

├── id

├── tenant

├── type

├── title

├── body

├── priority

├── severity

├── source\_type

├── source\_id

├── created\_at

└── metadata



Notification باید مستقل از Delivery باشد.



یک Notification ممکن است از طریق چند Channel ارسال شود.



مثلاً:



Notification

&#x20;   │

&#x20;   ├── In-App Delivery

&#x20;   ├── Email Delivery

&#x20;   └── Push Delivery

12.4 Notification Type



Notification Type نباید Hard-Code شود.



نمونه:



TASK\_ASSIGNED

TASK\_OVERDUE

PROJECT\_COMPLETED

DOCUMENT\_APPROVED

DOCUMENT\_REJECTED

MEETING\_STARTED

SYSTEM\_ALERT

SECURITY\_ALERT



Type باید قابلیت توسعه داشته باشد.



12.5 Priority



حداقل:



LOW

NORMAL

HIGH

URGENT

CRITICAL



Priority باید روی Routing و Delivery Policy تأثیرگذار باشد.



مثلاً:



CRITICAL

&#x20;   ↓

In-App

Email

Push

SMS



در حالی که:



LOW

&#x20;   ↓

In-App



کافی باشد.



12.6 Severity



Severity از Priority جداست.



مثلاً:



INFO

WARNING

ERROR

CRITICAL



Priority مشخص می‌کند Notification چقدر فوری است.



Severity مشخص می‌کند Event چقدر جدی است.



12.7 Recipient



Notification می‌تواند چند Recipient داشته باشد.



Notification

&#x20;     ↓

NotificationRecipient

&#x20;     ├── User A

&#x20;     ├── User B

&#x20;     └── User C



Recipient باید وضعیت مستقل داشته باشد.



مثلاً:



UNREAD

READ

ARCHIVED

DISMISSED

12.8 Read State



Read شدن Notification نباید روی خود Notification ذخیره شود.



اشتباه:



Notification.is\_read



زیرا Notification ممکن است چند Recipient داشته باشد.



صحیح:



NotificationRecipient.is\_read



بنابراین:



Notification

&#x20;    │

&#x20;    ├── Recipient A → READ

&#x20;    ├── Recipient B → UNREAD

&#x20;    └── Recipient C → READ

12.9 Notification Template



Notification باید Template داشته باشد.



مثلاً:



Template:

TASK\_ASSIGNED



Title:



Task assigned to you



Body:



Task {{ task.title }} has been assigned to you by {{ actor.name }}.



Template باید از Business Logic جدا باشد.



12.10 Template Versioning



Templateها باید Version داشته باشند.



مثلاً:



TASK\_ASSIGNED

&#x20;   ├── v1

&#x20;   ├── v2

&#x20;   └── v3



نسخه فعال باید مشخص باشد.



Templateهای قبلی نباید حذف شوند.



این موضوع برای Audit و Historical Reconstruction ضروری است.



12.11 Template Localization



از ابتدا باید چندزبانه بودن در معماری دیده شود.



مثلاً:



TASK\_ASSIGNED

│

├── fa

├── en

├── de

└── tr



Language باید بر اساس:



User Preference

Tenant Policy

System Default



تعیین شود.



12.12 Notification Channel



Channel باید Abstract باشد.



مثلاً:



NotificationChannel

│

├── IN\_APP

├── EMAIL

├── PUSH

├── SMS

└── WEBHOOK



نباید Notification Service مستقیماً Email Service را صدا بزند.



باید Adapter استفاده شود.



12.13 Channel Adapter



معماری:



NotificationChannel

&#x20;       ↓

ChannelAdapter

&#x20;       │

&#x20;       ├── InAppAdapter

&#x20;       ├── EmailAdapter

&#x20;       ├── PushAdapter

&#x20;       ├── SmsAdapter

&#x20;       └── WebhookAdapter



هر Adapter باید Interface مشخصی داشته باشد.



مثلاً مفهومی:



send(notification, recipient)

12.14 Delivery



Delivery نشان می‌دهد Notification از یک Channel مشخص برای Recipient مشخص ارسال شده است.



Notification

&#x20;     ↓

Recipient

&#x20;     ↓

Delivery

&#x20;     ↓

Channel



مثلاً:



Notification #100





Recipient: User A





Delivery 1 → IN\_APP

Delivery 2 → EMAIL

Delivery 3 → PUSH

12.15 Delivery Status



حداقل:



PENDING

QUEUED

PROCESSING

SENT

DELIVERED

FAILED

CANCELLED

EXPIRED



تفاوت SENT و DELIVERED باید حفظ شود.



مثلاً:



SENT



یعنی Provider درخواست را قبول کرده.



DELIVERED



یعنی Provider تأیید کرده که پیام به مقصد رسیده است.



12.16 Delivery Attempt



هر تلاش برای ارسال باید ثبت شود.



NotificationDelivery

&#x20;       │

&#x20;       ├── Attempt 1 → FAILED

&#x20;       ├── Attempt 2 → FAILED

&#x20;       └── Attempt 3 → SENT



هر Attempt می‌تواند شامل:



attempt\_number

started\_at

completed\_at

status

provider

provider\_message\_id

error\_code

error\_message

response\_metadata



باشد.



12.17 Retry Policy



Retry نباید Hard-Code شود.



باید قابل تنظیم باشد.



مثلاً:



max\_attempts = 5

initial\_delay = 30 sec

backoff = exponential

max\_delay = 1 hour



نمونه:



Attempt 1

↓ 30 sec





Attempt 2

↓ 1 min





Attempt 3

↓ 2 min





Attempt 4

↓ 4 min





Attempt 5

12.18 Dead Letter



Deliveryهایی که بعد از Retryهای مجاز همچنان Fail شده‌اند باید قابل شناسایی باشند.



FAILED

&#x20;  ↓

Retry

&#x20;  ↓

Retry

&#x20;  ↓

Retry

&#x20;  ↓

DEAD LETTER



این اطلاعات برای Operations و Monitoring ضروری است.



12.19 Notification Preference



هر User باید بتواند Notification Preference داشته باشد.



مثلاً:



Task Assigned

&#x20;   In-App = ON

&#x20;   Email = ON

&#x20;   Push = OFF

&#x20;   SMS = OFF



یا:



Security Alert

&#x20;   In-App = ON

&#x20;   Email = ON

&#x20;   Push = ON

&#x20;   SMS = ON

12.20 Preference Hierarchy



Preference باید قابلیت Override داشته باشد.



ترتیب پیشنهادی:



System Policy

&#x20;     ↓

Tenant Policy

&#x20;     ↓

User Preference

&#x20;     ↓

Notification Override



باید دقیقاً مشخص باشد کدام Policy بر دیگری اولویت دارد.



12.21 Quiet Hours



کاربر باید بتواند Quiet Hours داشته باشد.



مثلاً:



22:00 → 08:00



اما Notificationهای Critical ممکن است Quiet Hours را Override کنند.



بنابراین:



NORMAL

&#x20;   ↓

Delayed





CRITICAL

&#x20;   ↓

Immediate

12.22 Scheduled Notification



Notification باید امکان Scheduling داشته باشد.



مثلاً:



Send at:

2026-09-01 09:00



Scheduled Notification باید وضعیت داشته باشد:



SCHEDULED

CANCELLED

PROCESSING

COMPLETED

FAILED

12.23 Event Driven Notification



Notification باید از Event Bus تغذیه شود.



مثلاً:



TaskAssignedEvent

&#x20;       ↓

NotificationEventHandler

&#x20;       ↓

Notification

&#x20;       ↓

NotificationPolicy

&#x20;       ↓

Delivery



یا:



DocumentApprovedEvent

&#x20;       ↓

Notification

12.24 Notification Rules



Notification Rule باید مشخص کند:



WHEN

&#x20;   event occurs





IF

&#x20;   condition matches





THEN

&#x20;   create notification



مثلاً:



WHEN Task becomes overdue

IF Task priority = HIGH

THEN notify manager + assignee



این Rule Engine در آینده می‌تواند به Workflow Engine متصل شود.



12.25 Multi-Tenancy



تمام Notificationهای Business باید Tenant Scoped باشند.



نباید:



Tenant A



بتواند Notificationهای:



Tenant B



را مشاهده کند.



Tenant Isolation باید در:



Query

Service

Permission

API

Event

Delivery



رعایت شود.



12.26 Security



Notification ممکن است حاوی اطلاعات حساس باشد.



بنابراین:



Authorization

Tenant Isolation

Access Control

Audit

Data Minimization



باید رعایت شود.



Notification نباید اطلاعاتی را نشان دهد که Recipient اجازه دسترسی به Source Entity آن را ندارد.



12.27 Source Entity



Notification باید بتواند به Source Object اشاره کند.



مثلاً:



source\_type = Task

source\_id = UUID



یا:



source\_type = Project

source\_id = UUID



این Reference باید Generic و قابل توسعه باشد.



12.28 Deep Link



Notification باید بتواند مقصد UI داشته باشد.



مثلاً:



/task/123



اما URL نباید تنها منبع Authorization باشد.



کاربر هنگام باز کردن Resource باید مجدداً Authorization شود.



12.29 API



APIهای اصلی:



GET    /notifications

GET    /notifications/{id}

POST   /notifications/{id}/read

POST   /notifications/{id}/unread

POST   /notifications/{id}/archive

POST   /notifications/{id}/dismiss

GET    /notifications/unread-count

GET    /notification-preferences

PUT    /notification-preferences



Admin/Operations API:



GET /notification-deliveries

GET /notification-deliveries/{id}

POST /notification-deliveries/{id}/retry

12.30 WebSocket



برای Real-Time Notification باید معماری WebSocket از ابتدا در نظر گرفته شود.



Stack:



Django Channels

&#x20;       ↓

Redis

&#x20;       ↓

WebSocket

&#x20;       ↓

Client



مثلاً:



Task Assigned

&#x20;     ↓

Event

&#x20;     ↓

Notification

&#x20;     ↓

WebSocket

&#x20;     ↓

Browser



کاربر نباید برای Notificationهای Real-Time دائماً Poll کند.



12.31 Email



Email باید Adapter-based باشد.



مثلاً:



EmailProvider



و Providerهای مختلف:



SMTP

SendGrid

Amazon SES

Microsoft Graph



Core نباید به Provider خاصی وابسته باشد.



12.32 SMS



SMS نیز باید Provider مستقل داشته باشد.



مثلاً:



SmsProvider



و Providerها قابل تعویض باشند.



12.33 Push



Push Notification باید از Provider abstraction استفاده کند.



معماری:



PushAdapter

&#x20;   ↓

Provider

&#x20;   ↓

Device Token



Device Token باید مستقل از User نگهداری شود.



یک User ممکن است چند Device داشته باشد.



12.34 Device Notification



ساختار:



User

&#x20;├── Device A

&#x20;├── Device B

&#x20;└── Device C



هر Device می‌تواند:



platform

device\_id

push\_token

last\_seen

is\_active



داشته باشد.



12.35 Audit



تمام عملیات مهم باید Audit شوند.



مثلاً:



Notification Created

Notification Read

Notification Archived

Notification Dismissed

Delivery Sent

Delivery Failed

Delivery Retried

Preference Changed

Template Changed

12.36 Observability



Notification Platform باید Metric داشته باشد.



حداقل:



notifications\_created

notifications\_sent

notifications\_failed

notifications\_delivered

notifications\_retried

notification\_latency

delivery\_latency

provider\_failure\_rate

12.37 Logging



Log باید شامل:



tenant\_id

notification\_id

recipient\_id

delivery\_id

channel

provider

status

correlation\_id

timestamp



باشد.



اطلاعات حساس نباید Log شوند.



12.38 Idempotency



Notification Delivery باید Idempotent باشد.



اگر یک Event دوبار پردازش شد، نباید Notification دوبار ایجاد شود مگر اینکه Business Rule اجازه دهد.



باید از:



event\_id

idempotency\_key



استفاده شود.



12.39 Transaction Boundary



ایجاد Business Event و ثبت Transactional State باید به صورت قابل اعتماد انجام شود.



برای Eventهایی که باید Notification ایجاد کنند، معماری باید در آینده قابلیت:



Transactional Outbox



را داشته باشد.



ساختار:



Business Transaction

&#x20;      ↓

Database Transaction

&#x20;      ↓

Outbox Event

&#x20;      ↓

Event Processor

&#x20;      ↓

Notification

12.40 Queue



ارسال Notificationهای خارجی نباید Request/Response API را Block کند.



مثلاً:



HTTP Request

&#x20;    ↓

Create Notification

&#x20;    ↓

Queue Delivery

&#x20;    ↓

HTTP Response



سپس:



Worker

&#x20;  ↓

Email/SMS/Push



در آینده Queue می‌تواند با ابزارهایی مانند Celery/RQ یا زیرساخت مشابه پیاده‌سازی شود.



Core نباید به Queue Provider خاصی وابسته شود.



12.41 Domain Events



Notification Context باید Eventهای خودش را تولید کند.



مثلاً:



NotificationCreated

NotificationRead

NotificationDelivered

NotificationDeliveryFailed

NotificationRetryScheduled

12.42 Domain Services



Serviceهای اصلی:



NotificationCreationService

NotificationRoutingService

NotificationDeliveryService

NotificationPreferenceService

NotificationTemplateService

NotificationSchedulingService

NotificationRetryService

12.43 Repository / Selector



Query Logic نباید در View قرار بگیرد.



مثلاً:



NotificationSelector

NotificationDeliverySelector

NotificationPreferenceSelector



برای Queryها استفاده شوند.



12.44 Permission



Permissionها باید Domain-aware باشند.



مثلاً:



CanViewNotification

CanManageNotification

CanManageTemplate

CanRetryDelivery

CanManagePreferences

12.45 Testing



حداقل تست‌ها:



Notification Creation

Recipient Assignment

Read State

Unread State

Archive

Dismiss

Template Rendering

Template Version

Localization

Preference Resolution

Quiet Hours

Priority Routing

Delivery Creation

Delivery Status

Retry

Dead Letter

Idempotency

Tenant Isolation

Authorization

WebSocket Notification

12.46 ساختار پیشنهادی App



در این مرحله Notification را به شکل یک Domain مستقل توسعه بده.



ساختار پیشنهادی:



apps/

└── notifications/

&#x20;   ├── \_\_init\_\_.py

&#x20;   ├── apps.py

&#x20;   │

&#x20;   ├── domain/

&#x20;   │   ├── entities/

&#x20;   │   ├── value\_objects/

&#x20;   │   ├── events/

&#x20;   │   ├── services/

&#x20;   │   └── repositories/

&#x20;   │

&#x20;   ├── application/

&#x20;   │   ├── commands/

&#x20;   │   ├── queries/

&#x20;   │   ├── services/

&#x20;   │   └── handlers/

&#x20;   │

&#x20;   ├── infrastructure/

&#x20;   │   ├── persistence/

&#x20;   │   ├── providers/

&#x20;   │   ├── channels/

&#x20;   │   └── messaging/

&#x20;   │

&#x20;   ├── models/

&#x20;   │

&#x20;   ├── api/

&#x20;   │   ├── serializers/

&#x20;   │   ├── views/

&#x20;   │   ├── permissions/

&#x20;   │   └── urls.py

&#x20;   │

&#x20;   ├── selectors/

&#x20;   ├── services/

&#x20;   ├── migrations/

&#x20;   └── tests/



اگر ساختار فعلی Repository با این Structure متفاوت است، بدون بررسی کل Architecture نباید کورکورانه Rename یا Move انجام شود.



12.47 Database Entities



در این فاز حداقل موجودیت‌های زیر باید در ERD دیده شوند:



notifications

notification\_recipients

notification\_templates

notification\_template\_versions

notification\_channels

notification\_preferences

notification\_deliveries

notification\_attempts

notification\_schedules

notification\_devices

notification\_rules

notification\_events



این فهرست حداقل است و در طراحی نهایی ممکن است بر اساس ERD نهایی تفکیک یا ترکیب شود.



12.48 Indexing



Indexهای مهم:



tenant\_id

recipient\_id

created\_at

is\_read

status

priority

channel

notification\_type

scheduled\_at



Indexهای Composite باید بر اساس Query Pattern واقعی طراحی شوند.



مثلاً:



(tenant\_id, recipient\_id, created\_at)



و:



(tenant\_id, recipient\_id, is\_read)



ولی قبل از ایجاد Indexهای زیاد باید Query Workload مشخص شود.



12.49 Constraints



باید Database Constraint استفاده شود.



مثلاً:



unique idempotency key

valid status values

valid priority values

valid channel values



Business Ruleهای حیاتی نباید فقط در Serializer پیاده‌سازی شوند.



12.50 Definition of Done



فاز 12 فقط زمانی کامل است که:



\[ ] Notification Domain طراحی شده

\[ ] Notification Entity مشخص شده

\[ ] Recipient Model مشخص شده

\[ ] Template System طراحی شده

\[ ] Template Versioning طراحی شده

\[ ] Localization طراحی شده

\[ ] Channel Abstraction طراحی شده

\[ ] Delivery طراحی شده

\[ ] Delivery Attempt طراحی شده

\[ ] Retry Policy طراحی شده

\[ ] Dead Letter طراحی شده

\[ ] Preference System طراحی شده

\[ ] Quiet Hours طراحی شده

\[ ] Scheduling طراحی شده

\[ ] Event Integration طراحی شده

\[ ] Idempotency طراحی شده

\[ ] Tenant Isolation رعایت شده

\[ ] Authorization طراحی شده

\[ ] Audit Integration طراحی شده

\[ ] WebSocket Architecture مشخص شده

\[ ] Provider Abstraction مشخص شده

\[ ] Queue Architecture مشخص شده

\[ ] Database Index Strategy مشخص شده

\[ ] API Contract مشخص شده

\[ ] Tests طراحی شده

\[ ] Documentation نوشته شده

12.51 ممنوعیت‌های فاز



در این فاز:



❌ Business Domainها نباید Email Service مستقیم صدا بزنند.





❌ Notification نباید به یک Provider خاص وابسته شود.





❌ Notification.is\_read نباید برای Multi-Recipient استفاده شود.





❌ ارسال Email/SMS نباید داخل HTTP Request اصلی انجام شود.





❌ Tenant Isolation نباید فقط در Frontend باشد.





❌ Retry نباید Hard-Code شود.





❌ Template نباید داخل Python Code پراکنده شود.





❌ Authorization نباید فقط روی Notification اعمال شود؛

&#x20;  Source Entity نیز باید قابل دسترسی باشد.





❌ Delivery بدون Audit نباید نهایی شود.





❌ Event Processing بدون Idempotency نباید Production Ready تلقی شود.

12.52 خروجی نهایی فاز 12



در پایان Phase 12 باید این مجموعه را داشته باشیم:



Notification Domain Specification

Notification ERD

Notification Database Dictionary

Notification API Specification

Notification Event Specification

Notification Channel Specification

Notification Provider Specification

Notification Delivery State Machine

Notification Retry Specification

Notification Preference Specification

Notification Security Specification

Notification Audit Specification

Notification Testing Specification

Notification Implementation

Notification Documentation



نکته مهم: در این فاز هنوز نباید وارد پیاده‌سازی Voice/Video Meeting کامل شویم. Communication Real-Time مثل Chat، Presence، WebRTC و Meeting باید در فازهای اختصاصی Communication/Collaboration پیاده‌سازی شوند؛ این فاز زیرساخت Notification و Integration آن با Event-driven Platform را آماده می‌کند.

