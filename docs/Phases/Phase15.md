============================================================

TEKARAI — PHASE 15

NOTIFICATION PLATFORM

============================================================



STATUS

\------

Phase: 15

Previous Phase: 14 — Communication Platform

Current Phase: 15 — Notification Platform

Next Phase: 16



PURPOSE

\-------

در این فاز باید Notification Platform Tekarai به‌صورت

Enterprise-Grade، Multi-Tenant، Event-Driven، قابل توسعه،

قابل Audit و مستقل از Domainهای دیگر طراحی و پیاده‌سازی شود.



Notification Platform مسئول تصمیم‌گیری، ایجاد، زمان‌بندی،

Routing، Delivery، Tracking و مدیریت چرخه عمر Notificationها است.



Notification نباید داخل Domainهای دیگر پیاده‌سازی شود.



مثلاً:



Tasks نباید Email ارسال کند.

Projects نباید Push Notification ارسال کند.

Communication نباید مستقیماً Notification ایجاد کند.

Documents نباید مستقیماً SMS ارسال کند.



این Domainها فقط Event یا Notification Request تولید می‌کنند.



Notification Platform تصمیم می‌گیرد:



\- آیا Notification لازم است؟

\- برای چه کسی؟

\- از چه Channelی؟

\- با چه Templateای؟

\- چه زمانی؟

\- با چه Priorityای؟

\- با چه Policyای؟

\- چند بار Retry شود؟

\- آیا کاربر Notification را دریافت کرده؟

\- آیا Read شده؟

\- آیا Delivery موفق بوده؟



============================================================

1\. ARCHITECTURAL POSITION

============================================================



Notification Platform یک Bounded Context مستقل است.



Notification باید یک Infrastructure عمومی برای کل Tekarai باشد.



Domainهای مختلف می‌توانند Notification تولید کنند:



\- Identity

\- HR

\- Projects

\- Tasks

\- Documents

\- Workflow

\- Communication

\- Meetings

\- Devices

\- Reports

\- AI

\- System



اما Notification Platform مالک Business Entityهای این Domainها نیست.



Notification Platform فقط Notification را مدیریت می‌کند.



============================================================

2\. ARCHITECTURAL PRINCIPLES

============================================================



Notification Platform باید بر اساس:



\- DDD

\- Clean Architecture

\- SOLID

\- Event Driven Architecture

\- Modular Monolith

\- API First

\- Multi-Tenancy

\- Security First

\- Audit First

\- Async Processing

\- Idempotency

\- Retry Safety

\- Provider Abstraction

\- Template Driven Design

\- Policy Driven Delivery

\- Observability



ساخته شود.



معماری باید از ابتدا قابلیت انتقال Notification Platform

به یک سرویس مستقل در آینده را داشته باشد.



اما در Phase 15 نباید Microservice اجباری ساخته شود.



============================================================

3\. TECHNOLOGY

============================================================



Backend:



Python 3.12

Django 6

Django REST Framework

SQL Server

Redis

Django Channels در صورت نیاز به Real-Time



برای Async Processing:



Celery

Redis



Notification Platform باید از Async Processing استفاده کند.



ارسال Email، SMS، Push و سایر Notificationهای خارجی

نباید Request HTTP اصلی را Block کنند.



============================================================

4\. NOTIFICATION CHANNELS

============================================================



سیستم باید از ابتدا Channel Abstraction داشته باشد.



Channelهای پایه:



IN\_APP

EMAIL

SMS

PUSH

WEB\_PUSH

WEBSOCKET



Channelهای آینده:



WHATSAPP

TELEGRAM

TEAMS

SLACK

VOICE

OTHER



نباید منطق هر Provider در Notification Service اصلی قرار گیرد.



============================================================

5\. CHANNEL PROVIDER ABSTRACTION

============================================================



هر Channel باید Provider مستقل داشته باشد.



مثلاً:



EmailChannel

&#x20;   |

&#x20;   +-- SMTPProvider

&#x20;   +-- SendGridProvider

&#x20;   +-- AmazonSESProvider



SMSChannel

&#x20;   |

&#x20;   +-- ProviderA

&#x20;   +-- ProviderB



PushChannel

&#x20;   |

&#x20;   +-- FCMProvider

&#x20;   +-- APNSProvider



Notification Platform نباید به یک Provider خاص وابسته باشد.



============================================================

6\. NOTIFICATION ENTITY

============================================================



Notification Entity باید حداقل شامل:



\- id

\- tenant

\- recipient

\- actor

\- type

\- title

\- body

\- payload

\- priority

\- status

\- createdAt

\- scheduledAt

\- expiresAt

\- sentAt

\- deliveredAt

\- readAt

\- failedAt



باشد.



Status:



CREATED

QUEUED

PROCESSING

SENT

DELIVERED

READ

FAILED

CANCELLED

EXPIRED



============================================================

7\. NOTIFICATION TYPE

============================================================



Notification Type باید قابل توسعه باشد.



مثال:



TASK\_ASSIGNED

TASK\_COMPLETED

PROJECT\_CREATED

PROJECT\_UPDATED

DOCUMENT\_SHARED

DOCUMENT\_APPROVED

MESSAGE\_RECEIVED

MEETING\_STARTED

MEETING\_INVITATION

SYSTEM\_ALERT

SECURITY\_ALERT

AI\_INSIGHT

WORKFLOW\_APPROVAL\_REQUIRED



Notification Type نباید به صورت Hard-Coded در

Serviceهای مختلف پخش شود.



============================================================

8\. PRIORITY

============================================================



Notification باید Priority داشته باشد.



LOW

NORMAL

HIGH

URGENT

CRITICAL



Priority روی:



\- Queue

\- Retry

\- Delivery

\- User Preference

\- Escalation



اثر می‌گذارد.



============================================================

9\. RECIPIENT MODEL

============================================================



Recipient می‌تواند:



\- User

\- Group

\- Department

\- Role

\- Organization

\- Dynamic Audience



باشد.



اما Notification در نهایت باید قابل Resolve شدن به

Recipientهای واقعی باشد.



مثال:



Task Assigned to Department X



ابتدا:



Department X



و سپس:



User A

User B

User C



به عنوان Recipient Resolution.



============================================================

10\. ACTOR

============================================================



Notification باید Actor داشته باشد.



مثال:



User A assigned Task to User B.



Notification:



actor = User A

recipient = User B



برای Notificationهای سیستمی:



actor = System



============================================================

11\. NOTIFICATION PAYLOAD

============================================================



Payload باید JSON-based و Versioned باشد.



مثال:



{

&#x20;   "taskId": "...",

&#x20;   "projectId": "...",

&#x20;   "action": "assigned"

}



Payload نباید شامل اطلاعات غیرضروری یا Sensitive Data باشد.



Payload باید امکان Deep Link کردن به UI را فراهم کند.



============================================================

12\. NOTIFICATION PREFERENCE

============================================================



کاربر باید بتواند Notification Preferences خود را کنترل کند.



مثال:



Task Assignment:



IN\_APP = ON

EMAIL = ON

PUSH = ON

SMS = OFF



Meeting:



IN\_APP = ON

EMAIL = ON

PUSH = ON



Marketing:



EMAIL = OFF



============================================================

13\. PREFERENCE HIERARCHY

============================================================



Preference باید چند سطح داشته باشد:



System Default

&#x20;       |

&#x20;       v

Tenant Policy

&#x20;       |

&#x20;       v

Organization Policy

&#x20;       |

&#x20;       v

User Preference

&#x20;       |

&#x20;       v

Notification Type Preference

&#x20;       |

&#x20;       v

Channel Preference



Policy نهایی باید بر اساس بالاترین سطح مجاز

محاسبه شود.



User نباید بتواند Policy امنیتی اجباری Tenant را

Override کند.



============================================================

14\. USER NOTIFICATION SETTINGS

============================================================



User Notification Settings باید شامل:



\- enabled

\- channel

\- notificationType

\- quietHours

\- frequency

\- digestMode



باشد.



============================================================

15\. QUIET HOURS

============================================================



کاربر باید بتواند Quiet Hours تعریف کند.



مثال:



22:00 تا 07:00



در این بازه Notificationهای عادی:



\- Queue می‌شوند

\- Delayed می‌شوند

\- یا Digest می‌شوند



اما:



CRITICAL



می‌تواند Policy خاص داشته باشد.



============================================================

16\. DIGEST

============================================================



Notification Platform باید قابلیت Digest داشته باشد.



مثال:



به جای 20 Notification:



20 Tasks Updated



در یک Notification Digest نمایش داده شود.



Digest می‌تواند:



HOURLY

DAILY

WEEKLY



باشد.



============================================================

17\. IN-APP NOTIFICATION

============================================================



In-App Notification باید Persistent باشد.



User باید بتواند:



\- List

\- Read

\- Mark as Read

\- Mark All as Read

\- Delete

\- Archive



را انجام دهد.



Unread Count باید بهینه باشد.



============================================================

18\. READ STATE

============================================================



Notification باید Read State داشته باشد.



حداقل:



UNREAD

READ



Read timestamp نیز ذخیره شود.



Read operation باید Idempotent باشد.



============================================================

19\. BULK NOTIFICATION

============================================================



سیستم باید Bulk Notification را پشتیبانی کند.



مثال:



ارسال یک Notification به:



10,000 User



نباید یک HTTP Request را برای 10,000 User ایجاد کند.



باید:



Notification Job

&#x20;   |

&#x20;   v

Audience Resolution

&#x20;   |

&#x20;   v

Batching

&#x20;   |

&#x20;   v

Queue

&#x20;   |

&#x20;   v

Workers



استفاده شود.



============================================================

20\. ASYNC ARCHITECTURE

============================================================



Flow:



Domain Event

&#x20;   |

&#x20;   v

Notification Event Handler

&#x20;   |

&#x20;   v

Notification Policy

&#x20;   |

&#x20;   v

Recipient Resolution

&#x20;   |

&#x20;   v

Template Resolution

&#x20;   |

&#x20;   v

Notification Creation

&#x20;   |

&#x20;   v

Queue

&#x20;   |

&#x20;   v

Worker

&#x20;   |

&#x20;   v

Provider

&#x20;   |

&#x20;   v

Delivery Result

&#x20;   |

&#x20;   v

Tracking



============================================================

21\. CELERY

============================================================



Celery مسئول:



\- Async Delivery

\- Retry

\- Scheduling

\- Batch Processing

\- Digest Processing

\- Cleanup



است.



Taskهای Celery باید Idempotent باشند.



============================================================

22\. QUEUE DESIGN

============================================================



Queueها می‌توانند بر اساس Priority تقسیم شوند.



مثال:



critical

high

normal

low



Workerها باید بتوانند Queueهای مختلف را Process کنند.



Notificationهای Critical نباید پشت هزاران

Notification کم‌اهمیت گیر کنند.



============================================================

23\. RETRY

============================================================



Retry باید Exponential Backoff داشته باشد.



مثال:



Attempt 1

&#x20;   ↓

5 sec



Attempt 2

&#x20;   ↓

30 sec



Attempt 3

&#x20;   ↓

2 min



Attempt 4

&#x20;   ↓

10 min



مقادیر باید Configurable باشند.



============================================================

24\. MAX RETRY

============================================================



برای هر Notification Type و Provider:



Max Retry



قابل تنظیم باشد.



بعد از پایان Retry:



FAILED



و Failure Reason ذخیره شود.



============================================================

25\. DEAD LETTER QUEUE

============================================================



Notificationهای Failed پس از Max Retry باید وارد:



Dead Letter Queue



شوند.



Admin باید بتواند:



\- Inspect

\- Retry

\- Cancel

\- Diagnose



انجام دهد.



============================================================

26\. FAILURE CLASSIFICATION

============================================================



Failure باید طبقه‌بندی شود.



TEMPORARY

PERMANENT

RATE\_LIMITED

AUTHENTICATION\_ERROR

INVALID\_RECIPIENT

PROVIDER\_ERROR

NETWORK\_ERROR

CONTENT\_ERROR

POLICY\_BLOCKED



Retry فقط برای Failureهای قابل Retry انجام شود.



============================================================

27\. IDEMPOTENCY

============================================================



Notification Creation باید Idempotent باشد.



هر Event باید:



eventId



داشته باشد.



یک Event نباید دوبار Notification ایجاد کند.



برای این منظور باید:



NotificationEventRecord



یا Outbox/Inbox Pattern



استفاده شود.



============================================================

28\. EVENT DRIVEN INTEGRATION

============================================================



نمونه Event:



TaskAssigned



Notification Platform دریافت می‌کند:



TaskAssigned



سپس:



1\. Recipient را Resolve می‌کند.

2\. Policy را بررسی می‌کند.

3\. Preference را بررسی می‌کند.

4\. Template را انتخاب می‌کند.

5\. Notification ایجاد می‌کند.

6\. Queue می‌کند.

7\. Delivery انجام می‌دهد.



============================================================

29\. OUTBOX PATTERN

============================================================



برای جلوگیری از Lost Event:



Domain Transaction

&#x20;      |

&#x20;      +--> Business Data

&#x20;      |

&#x20;      +--> Outbox Event



هر دو در یک Transaction ثبت شوند.



سپس:



Outbox Processor

&#x20;      |

&#x20;      v

Notification Processing



این روش برای Eventهای مهم الزامی است.



============================================================

30\. TEMPLATE SYSTEM

============================================================



Notification نباید متن خود را Hard-Code کند.



Template System باید وجود داشته باشد.



Template:



\- id

\- tenant

\- notificationType

\- channel

\- language

\- subject

\- body

\- version

\- status



باشد.



============================================================

31\. TEMPLATE VERSIONING

============================================================



Template باید Version داشته باشد.



مثال:



TaskAssigned Email v1

TaskAssigned Email v2



Notificationهای قبلی نباید با تغییر Template

تغییر کنند.



============================================================

32\. TEMPLATE LANGUAGE

============================================================



Template باید Multi-Language باشد.



مثال:



fa

en

de

tr



Language Resolution:



User Language

&#x20;   ↓

Tenant Default

&#x20;   ↓

System Default



============================================================

33\. TEMPLATE RENDERING

============================================================



Template Engine باید Variable Injection داشته باشد.



مثال:



Hello {{ userName }}



Task "{{ taskTitle }}" has been assigned to you.



Variableها باید Validate شوند.



Template نباید اجازه اجرای Arbitrary Code بدهد.



============================================================

34\. EMAIL

============================================================



Email باید:



\- To

\- CC

\- BCC

\- Subject

\- HTML Body

\- Plain Text Body

\- Attachments



را پشتیبانی کند.



Email Provider باید Abstract باشد.



============================================================

35\. SMS

============================================================



SMS باید:



\- Phone Number

\- Message

\- Provider

\- Delivery Status



داشته باشد.



SMS Length و Provider Constraint باید رعایت شود.



============================================================

36\. PUSH NOTIFICATION

============================================================



Push Notification باید Device Token را پشتیبانی کند.



UserDevice:



\- user

\- deviceId

\- platform

\- token

\- lastSeen

\- isActive



Platform:



IOS

ANDROID

WEB



============================================================

37\. DEVICE TOKEN SECURITY

============================================================



Device Token اطلاعات حساس محسوب می‌شود.



باید:



\- Secure Storage

\- Rotation

\- Revocation

\- Expiration



پشتیبانی شود.



============================================================

38\. WEB PUSH

============================================================



Web Push باید Subscription Object داشته باشد.



Subscription:



\- endpoint

\- publicKey

\- authSecret

\- user

\- createdAt

\- expiresAt



اطلاعات Credential باید امن نگهداری شوند.



============================================================

39\. WEBSOCKET NOTIFICATION

============================================================



برای Notificationهای Real-Time:



Notification Event

&#x20;   |

&#x20;   v

Redis

&#x20;   |

&#x20;   v

WebSocket

&#x20;   |

&#x20;   v

Client



WebSocket فقط Transport است.



Notification Business Logic نباید در Consumer باشد.



============================================================

40\. NOTIFICATION DELIVERY

============================================================



Delivery باید Entity مستقل باشد.



NotificationDelivery:



\- id

\- notification

\- channel

\- provider

\- status

\- providerMessageId

\- attemptCount

\- queuedAt

\- sentAt

\- deliveredAt

\- failedAt

\- failureCode

\- failureMessage



باشد.



============================================================

41\. DELIVERY STATUS

============================================================



QUEUED

PROCESSING

SENT

DELIVERED

FAILED

CANCELLED



باید پشتیبانی شود.



Provider ممکن است فقط:



SENT



را تأیید کند و Delivery واقعی بعداً مشخص شود.



============================================================

42\. PROVIDER CALLBACK

============================================================



Providerها می‌توانند Webhook داشته باشند.



مثال:



Provider

&#x20;  |

&#x20;  | Delivery Webhook

&#x20;  v

Tekarai

&#x20;  |

&#x20;  v

Delivery Update



Webhook باید:



\- Authenticate

\- Validate Signature

\- Idempotent Process



شود.



============================================================

43\. NOTIFICATION SCHEDULING

============================================================



Notification می‌تواند Future Scheduled باشد.



مثال:



Reminder at 08:00 tomorrow.



Notification:



scheduledAt



خواهد داشت.



Scheduler باید Notification را در زمان مناسب

به Queue منتقل کند.



============================================================

44\. EXPIRATION

============================================================



Notification می‌تواند:



expiresAt



داشته باشد.



اگر قبل از Delivery منقضی شد:



EXPIRED



شود.



مثال:



Approval Request بعد از Deadline دیگر معتبر نیست.



============================================================

45\. ESCALATION

============================================================



Notificationهای Critical می‌توانند Escalation داشته باشند.



مثال:



Level 1:

User



اگر Read نشد:



Level 2:

Manager



اگر همچنان Read نشد:



Level 3:

Administrator



Escalation باید Policy Driven باشد.



============================================================

46\. NOTIFICATION POLICY

============================================================



Notification Policy باید تعیین کند:



\- آیا Notification ارسال شود؟

\- چه Recipientهایی؟

\- چه Channelهایی؟

\- چه Priorityای؟

\- چه زمانی؟

\- Quiet Hours اعمال شود؟

\- Digest شود؟

\- Escalation شود؟

\- Retry شود؟



Policy نباید در Domainهای مختلف تکرار شود.



============================================================

47\. NOTIFICATION RULE

============================================================



Rule Engine می‌تواند Event را به Notification تبدیل کند.



مثال:



EVENT:

TASK\_OVERDUE



RULE:

IF task.assignee exists

THEN notify assignee



AND:



IF overdue > 24h

THEN notify manager



Rule Engine باید قابل توسعه باشد.



============================================================

48\. USER OPT-OUT

============================================================



کاربر باید بتواند از Notificationهای اختیاری

Opt-Out کند.



اما Notificationهای اجباری:



SECURITY

SYSTEM

LEGAL

COMPLIANCE



ممکن است قابل خاموش کردن نباشند.



============================================================

49\. TENANT POLICY

============================================================



Tenant Administrator باید بتواند:



\- Allowed Channels

\- Default Templates

\- Required Notifications

\- Quiet Hours

\- Rate Limits

\- Retention

\- Provider

\- Branding



را تنظیم کند.



============================================================

50\. BRANDING

============================================================



Email و Push در صورت نیاز باید Tenant Branding داشته باشند.



مثال:



\- Logo

\- Company Name

\- Colors

\- Footer

\- Contact Information



Template باید Branding را از Tenant Context دریافت کند.



============================================================

51\. SECURITY

============================================================



Notification Platform باید:



\- Tenant Isolation

\- RBAC

\- Object-Level Authorization

\- Secure Provider Credentials

\- Webhook Signature Validation

\- Rate Limiting

\- Input Validation

\- Template Sandboxing

\- Audit Logging



را رعایت کند.



============================================================

52\. PROVIDER CREDENTIALS

============================================================



Credentialهای Provider نباید در Source Code قرار گیرند.



باید از:



Environment Variables

Secret Manager

Secure Configuration



استفاده شود.



Database نباید Credential خام را ذخیره کند.



============================================================

53\. AUDIT

============================================================



حداقل Audit Eventها:



NOTIFICATION\_CREATED

NOTIFICATION\_QUEUED

NOTIFICATION\_SENT

NOTIFICATION\_DELIVERED

NOTIFICATION\_READ

NOTIFICATION\_FAILED

NOTIFICATION\_CANCELLED

NOTIFICATION\_EXPIRED

NOTIFICATION\_RETRIED

TEMPLATE\_CREATED

TEMPLATE\_UPDATED

TEMPLATE\_ACTIVATED

PREFERENCE\_CHANGED

DEVICE\_REGISTERED

DEVICE\_REVOKED

PROVIDER\_CHANGED



============================================================

54\. OBSERVABILITY

============================================================



Metrics:



\- Notifications Created

\- Notifications Sent

\- Notifications Delivered

\- Notifications Failed

\- Delivery Rate

\- Failure Rate

\- Retry Rate

\- Queue Length

\- Queue Latency

\- Provider Latency

\- Template Rendering Time

\- Webhook Processing Time

\- Unread Count

\- Active Devices



Logs باید Structured باشند.



============================================================

55\. MONITORING

============================================================



Alert باید برای موارد زیر وجود داشته باشد:



\- Queue Backlog

\- High Failure Rate

\- Provider Down

\- Redis Down

\- Celery Worker Down

\- Delivery Latency Spike

\- Webhook Failure Spike

\- Database Failure



============================================================

56\. SEARCH

============================================================



کاربر باید بتواند Notificationهای خود را Search کند.



Search Fields:



\- Type

\- Status

\- Date

\- Read State

\- Channel



Search باید Tenant و User Scoped باشد.



============================================================

57\. API

============================================================



REST API:



GET /api/v1/notifications/

GET /api/v1/notifications/{id}/



POST /api/v1/notifications/{id}/read/

POST /api/v1/notifications/read-all/



DELETE /api/v1/notifications/{id}/



GET /api/v1/notification-preferences/

PATCH /api/v1/notification-preferences/



GET /api/v1/devices/

POST /api/v1/devices/

DELETE /api/v1/devices/{id}/



Admin:



GET /api/v1/admin/notification-templates/

POST /api/v1/admin/notification-templates/



GET /api/v1/admin/notification-deliveries/



============================================================

58\. API RULES

============================================================



تمام APIها باید:



\- Authentication

\- Authorization

\- Tenant Isolation

\- Validation

\- Pagination

\- Rate Limiting



داشته باشند.



Notificationهای User دیگر نباید قابل مشاهده باشند.



============================================================

59\. APPLICATION USE CASES

============================================================



حداقل Use Caseها:



CreateNotification

QueueNotification

SendNotification

CancelNotification

RetryNotification

MarkNotificationRead

MarkAllNotificationsRead

ScheduleNotification

ResolveRecipients

ResolveTemplate

RenderTemplate

ProcessDelivery

ProcessProviderWebhook

CreateDigest

SendDigest

EscalateNotification

RegisterDevice

RevokeDevice

UpdatePreference



============================================================

60\. DOMAIN LAYER

============================================================



Business Rules باید در Domain قرار بگیرند.



مثال:



Notification.canSend()

Notification.canRetry()

Notification.canCancel()

Notification.canExpire()



Preference.allows()

Policy.allows()

Delivery.canRetry()



نباید این قوانین فقط در View یا Serializer باشند.



============================================================

61\. REPOSITORIES

============================================================



Repository Interfaces:



INotificationRepository

INotificationDeliveryRepository

INotificationPreferenceRepository

INotificationTemplateRepository

IDeviceRepository

INotificationPolicyRepository



Implementation:



Django ORM



اما Domain نباید مستقیماً به ORM وابسته شود.



============================================================

62\. INFRASTRUCTURE

============================================================



Infrastructure باید شامل:



Django ORM

Celery

Redis

Email Providers

SMS Providers

Push Providers

Webhook Handlers

Template Engine

Object Storage در صورت نیاز



باشد.



Providerها باید Adapter داشته باشند.



============================================================

63\. DATABASE MODEL MAP

============================================================



حداقل Modelهای Persistent:



Tenant

Notification

NotificationDelivery

NotificationPreference

NotificationTemplate

NotificationTemplateVersion

NotificationPolicy

NotificationEvent

NotificationDigest

UserDevice

PushSubscription

NotificationProvider

NotificationAudit



مدل Tenant ممکن است توسط Identity/Organization

مالکیت داشته باشد و Notification فقط Reference کند.



============================================================

64\. DATABASE INDEXES

============================================================



Notification:



tenant

recipient

createdAt

status

readAt

scheduledAt

notificationType



NotificationDelivery:



notification

channel

status

provider

createdAt



Preference:



user

notificationType

channel



Template:



tenant

notificationType

channel

language

status



Device:



user

platform

isActive



Indexها باید بر اساس Query Pattern واقعی تکمیل شوند.



============================================================

65\. CONSTRAINTS

============================================================



نمونه:



UserDevice(user, deviceId)



NotificationPreference(

&#x20;   user,

&#x20;   notificationType,

&#x20;   channel

)



Template:



tenant

notificationType

channel

language

version



باید Constraints مناسب داشته باشند.



============================================================

66\. DATA RETENTION

============================================================



Notification Data باید Retention Policy داشته باشد.



مثال:



30 Days

90 Days

1 Year

7 Years

Indefinite



Retention باید Configurable باشد.



اما Audit و Compliance Data ممکن است

Retention متفاوت داشته باشند.



============================================================

67\. CLEANUP

============================================================



Background Jobs باید:



\- Expired Notifications

\- Old Deliveries

\- Old Digests

\- Revoked Devices

\- Old Temporary Data



را Cleanup کنند.



Cleanup نباید داده‌های Audit را حذف کند

مگر طبق Policy.



============================================================

68\. RATE LIMITING

============================================================



Rate Limit برای:



\- Notification Creation

\- Bulk Notification

\- Email

\- SMS

\- Push

\- Webhook

\- Template Rendering



باید وجود داشته باشد.



Provider Rate Limit نیز باید رعایت شود.



============================================================

69\. ANTI-SPAM

============================================================



سیستم باید از Notification Flood جلوگیری کند.



مثال:



اگر یک Event در مدت کوتاه چندین بار اتفاق افتاد:



Notification Aggregation



انجام شود.



مثلاً:



"15 tasks were updated."



به جای:



15 Notification جدا.



============================================================

70\. DEDUPLICATION

============================================================



Notificationهای Duplicate باید قابل شناسایی باشند.



Deduplication Key می‌تواند شامل:



tenant

recipient

notificationType

sourceEntity

sourceEvent

timeWindow



باشد.



مثال:



TASK\_OVERDUE



نباید هر دقیقه Notification جدید ایجاد کند.



============================================================

71\. TRANSACTIONAL CONSISTENCY

============================================================



Notification Event باید با Transaction اصلی

سازگار باشد.



نباید چنین وضعیتی ایجاد شود:



Database Commit Failed

ولی Notification ارسال شد.



یا:



Database Commit شد

ولی Event گم شد.



برای Eventهای مهم:



Outbox Pattern



استفاده شود.



============================================================

72\. EVENT VERSIONING

============================================================



Event Schema باید Version داشته باشد.



مثال:



TaskAssigned.v1

TaskAssigned.v2



Notification Consumer باید بتواند Versionهای

پشتیبانی‌شده را مدیریت کند.



============================================================

73\. AI INTEGRATION

============================================================



AI Platform می‌تواند برای:



\- Notification Summarization

\- Smart Digest

\- Notification Prioritization

\- Spam Detection

\- Intelligent Routing

\- Smart Escalation



استفاده شود.



اما AI نباید بدون Policy Notification ارسال کند.



============================================================

74\. AI PRIORITY

============================================================



در آینده AI می‌تواند Notificationها را اولویت‌بندی کند.



مثال:



100 Notification



AI می‌تواند:



Critical:

3



Important:

12



Low:

85



تشخیص دهد.



اما Final Policy باید قابل کنترل باشد.



============================================================

75\. MULTI-TENANT ISOLATION

============================================================



تمام Notification Queryها باید Tenant Scoped باشند.



اصل:



No Tenant Context

=

No Notification Query



هیچ User نباید بتواند:



\- Notification Tenant دیگر

\- Template Tenant دیگر

\- Policy Tenant دیگر

\- Provider Configuration Tenant دیگر



را مشاهده کند.



============================================================

76\. TESTING

============================================================



حداقل:



Unit Tests

Integration Tests

API Tests

Permission Tests

Tenant Isolation Tests

Celery Tests

Provider Tests

Webhook Tests

Retry Tests

Idempotency Tests

Template Tests

Preference Tests

Scheduling Tests

Digest Tests

Rate Limit Tests

Security Tests

Performance Tests



============================================================

77\. CRITICAL TEST SCENARIOS

============================================================



باید تست شود:



1\.

Event دوبار وارد شود.



نتیجه:

فقط یک Notification.



2\.

Provider Fail شود.



نتیجه:

Retry.



3\.

Provider Permanent Failure بدهد.



نتیجه:

No Retry + Failed.



4\.

Notification در Quiet Hours ایجاد شود.



نتیجه:

Queue یا Digest طبق Policy.



5\.

User Notification را Read کند.



نتیجه:

Read State ثبت شود.



6\.

User Tenant A بخواهد Notification Tenant B را بخواند.



نتیجه:

403 یا 404 طبق Security Policy.



7\.

Provider Webhook دوبار ارسال شود.



نتیجه:

Idempotent.



8\.

10,000 Recipient.



نتیجه:

Batch Processing.



9\.

Celery Worker Restart شود.



نتیجه:

Notification گم نشود.



10\.

Redis Restart شود.



نتیجه:

Persistent Notification Data باقی بماند.



============================================================

78\. PERFORMANCE

============================================================



Notification List باید Pagination داشته باشد.



Unread Count باید Query بهینه داشته باشد.



Bulk Notification باید Batch Processing داشته باشد.



هیچ Loop بزرگی نباید داخل HTTP Request اجرا شود.



تمام عملیات خارجی:



Async



باشند.



============================================================

79\. SCALABILITY

============================================================



Notification Platform باید قابلیت Scale کردن:



API

Celery Workers

Redis

Database

Provider Workers



را داشته باشد.



Workerها باید Stateless باشند.



State Persistent در Database یا Queue نگهداری شود.



============================================================

80\. IMPLEMENTATION ORDER

============================================================



STEP 1

Notification Domain Foundation



STEP 2

Notification Entity



STEP 3

Notification Delivery



STEP 4

Notification Preferences



STEP 5

Notification Types



STEP 6

Notification Templates



STEP 7

Template Versioning



STEP 8

Policy Engine



STEP 9

Event Integration



STEP 10

Outbox Pattern



STEP 11

Celery Infrastructure



STEP 12

Redis Queue



STEP 13

In-App Notification



STEP 14

Read State



STEP 15

Email Provider



STEP 16

SMS Provider



STEP 17

Push Provider



STEP 18

Web Push



STEP 19

WebSocket Notification



STEP 20

Scheduling



STEP 21

Retry



STEP 22

Dead Letter Queue



STEP 23

Digest



STEP 24

Escalation



STEP 25

Deduplication



STEP 26

Rate Limiting



STEP 27

Anti-Spam



STEP 28

Provider Webhooks



STEP 29

Audit



STEP 30

Observability



STEP 31

Security Hardening



STEP 32

Performance Optimization



STEP 33

Full Testing



============================================================

81\. DEFINITION OF DONE

============================================================



Phase 15 زمانی کامل است که:



\[ ] Notification Domain مستقل ساخته شده باشد

\[ ] Notification Entity کامل باشد

\[ ] Notification Delivery کامل باشد

\[ ] In-App Notification فعال باشد

\[ ] Read State فعال باشد

\[ ] Notification Preferences فعال باشد

\[ ] Notification Templates فعال باشند

\[ ] Template Versioning فعال باشد

\[ ] Multi-Language فعال باشد

\[ ] Notification Policy فعال باشد

\[ ] Event-Driven Integration فعال باشد

\[ ] Outbox Pattern پیاده‌سازی شده باشد

\[ ] Celery فعال باشد

\[ ] Redis فعال باشد

\[ ] Async Delivery فعال باشد

\[ ] Retry فعال باشد

\[ ] Dead Letter Queue فعال باشد

\[ ] Email Provider abstraction کامل باشد

\[ ] SMS Provider abstraction کامل باشد

\[ ] Push Provider abstraction کامل باشد

\[ ] Web Push architecture کامل باشد

\[ ] WebSocket Notification فعال باشد

\[ ] Scheduled Notification فعال باشد

\[ ] Expiration فعال باشد

\[ ] Digest فعال باشد

\[ ] Escalation فعال باشد

\[ ] Deduplication فعال باشد

\[ ] Anti-Spam فعال باشد

\[ ] Rate Limiting فعال باشد

\[ ] Provider Webhook فعال باشد

\[ ] Audit فعال باشد

\[ ] Observability فعال باشد

\[ ] Metrics فعال باشند

\[ ] Tenant Isolation تست شده باشد

\[ ] Permission Tests سبز باشند

\[ ] Idempotency Tests سبز باشند

\[ ] Retry Tests سبز باشند

\[ ] Webhook Tests سبز باشند

\[ ] Security Tests سبز باشند

\[ ] Performance Tests قابل قبول باشند

\[ ] هیچ Notification مهمی در Failure از بین نرود

\[ ] هیچ Notification Duplicate غیرمجاز ایجاد نشود

\[ ] Documentation کامل باشد



============================================================

82\. ممنوعیت‌ها

============================================================



هرگز:



\- Email را مستقیم از View ارسال نکن.

\- SMS را مستقیم از Domain ارسال نکن.

\- Push را مستقیم از Model ارسال نکن.

\- Notification Logic را داخل Tasks/Projects/Communication قرار نده.

\- Provider را مستقیماً در Business Logic قرار نده.

\- API Request را برای Delivery خارجی Block نکن.

\- Retry نامحدود ایجاد نکن.

\- Notification Duplicate ایجاد نکن.

\- Event را بدون Idempotency پردازش نکن.

\- Credential را در Source Code قرار نده.

\- Provider Secret را Log نکن.

\- Template را با Arbitrary Code اجرا نکن.

\- Tenant Isolation را به Client اعتماد نکن.

\- User Preference را بدون Policy بررسی نکن.

\- Redis را Source of Truth برای Notification Persistent نکن.

\- Notificationهای Bulk را در یک Request Loop نکن.

\- Celery Task را بدون Idempotency طراحی نکن.

\- Webhook را بدون Signature Validation قبول نکن.

\- Audit Record را بدون Policy حذف نکن.



============================================================

83\. FINAL ARCHITECTURAL RESULT

============================================================



در پایان Phase 15:



&#x20;                      TEKARAI

&#x20;                        |

&#x20;            +-----------+-----------+

&#x20;            |                       |

&#x20;            v                       v

&#x20;      Domain Events          Direct Requests

&#x20;            |                       |

&#x20;            +-----------+-----------+

&#x20;                        |

&#x20;                        v

&#x20;             Notification Platform

&#x20;                        |

&#x20;         +--------------+--------------+

&#x20;         |              |              |

&#x20;         v              v              v

&#x20;      Policy         Template       Recipient

&#x20;      Engine          Engine        Resolver

&#x20;         |              |              |

&#x20;         +--------------+--------------+

&#x20;                        |

&#x20;                        v

&#x20;                 Notification

&#x20;                        |

&#x20;                        v

&#x20;                     Queue

&#x20;                        |

&#x20;             +----------+----------+

&#x20;             |          |          |

&#x20;             v          v          v

&#x20;           Email       SMS        Push

&#x20;             |          |          |

&#x20;             +----------+----------+

&#x20;                        |

&#x20;                        v

&#x20;                     Delivery

&#x20;                        |

&#x20;             +----------+----------+

&#x20;             |          |          |

&#x20;             v          v          v

&#x20;           Sent      Delivered    Failed

&#x20;                                     |

&#x20;                                     v

&#x20;                                   Retry

&#x20;                                     |

&#x20;                                     v

&#x20;                               Dead Letter



و در کنار آن:



&#x20;                   Notification

&#x20;                        |

&#x20;         +--------------+--------------+

&#x20;         |              |              |

&#x20;         v              v              v

&#x20;      In-App         WebSocket       Digest

&#x20;         |              |              |

&#x20;         +--------------+--------------+

&#x20;                        |

&#x20;                        v

&#x20;                    User



کل سیستم باید تحت:



Tenant Isolation

Security

Authorization

Audit

Retention

Observability

Idempotency

Scalability



کار کند.



============================================================

END OF PHASE 15

============================================================

