============================================================

TEKARAI ENTERPRISE PLATFORM

PHASE 9 — NOTIFICATION PLATFORM

============================================================



STATUS

\------------------------------------------------------------

This phase defines the complete Notification Platform of Tekarai.



Notification is a cross-cutting Enterprise capability.



It must provide a unified mechanism for delivering events and

notifications to users, teams, departments, systems and

external channels.



The Notification Platform must support:



\- In-App Notifications

\- Push Notifications

\- Email Notifications

\- SMS Notifications

\- Desktop Notifications

\- Mobile Notifications

\- Browser Notifications

\- Notification Preferences

\- Notification Templates

\- Notification Rules

\- Notification Categories

\- Priority

\- Delivery Status

\- Retry

\- Scheduling

\- Digests

\- Read / Unread State

\- Acknowledgement

\- User Preferences

\- Tenant Policies

\- Multi-Channel Delivery

\- Event Driven Delivery

\- Audit

\- Rate Limiting

\- Idempotency

\- Extensibility

\- AI-generated notifications



Notification must NOT become tightly coupled to individual

business domains.



Projects, Tasks, HR, Communication, Workflow, AI, Devices,

Maintenance and other domains publish events.



Notification consumes those events and decides whether,

when and how a notification should be delivered.





============================================================

1\. ARCHITECTURAL PRINCIPLES

============================================================



Notification follows:



\- DDD

\- Clean Architecture

\- SOLID

\- Event Driven Architecture

\- API First

\- Security First

\- Multi-Tenant Architecture

\- Configuration over Customization

\- Audit First

\- Cloud Ready

\- Offline Ready

\- Provider Agnostic Design



Notification must not contain business logic belonging to:



\- Projects

\- Tasks

\- HR

\- Communication

\- Documents

\- Workflow

\- AI

\- Devices



Notification only handles notification-related concerns.





============================================================

2\. BOUNDED CONTEXT

============================================================



Create:



Notification Bounded Context





Conceptual structure:



notifications/

&#x20;   domain/

&#x20;   application/

&#x20;   infrastructure/

&#x20;   interfaces/





The exact physical Django package structure may be adapted to

the final Tekarai repository architecture.



The logical boundaries are mandatory.





============================================================

3\. NOTIFICATION AGGREGATE

============================================================



Notification represents a notification generated for a target.



Core properties:



\- id

\- tenant

\- recipient

\- notificationType

\- category

\- title

\- body

\- priority

\- source

\- sourceType

\- sourceId

\- createdAt

\- scheduledAt

\- expiresAt

\- readAt

\- acknowledgedAt

\- status





Statuses:



PENDING

PROCESSING

DELIVERED

PARTIALLY\_DELIVERED

FAILED

EXPIRED

CANCELLED





============================================================

4\. NOTIFICATION CATEGORIES

============================================================



Notifications must be categorized.



Examples:



SYSTEM

SECURITY

TASK

PROJECT

HR

DOCUMENT

WORKFLOW

COMMUNICATION

MEETING

DEVICE

MAINTENANCE

AI

REPORT

ADMINISTRATION





Tenants must be able to configure notification behavior

without changing application code.





============================================================

5\. PRIORITY

============================================================



Supported priorities:



LOW

NORMAL

HIGH

URGENT

CRITICAL





Priority may affect:



\- delivery order

\- channel selection

\- retry policy

\- escalation

\- UI presentation

\- notification sound

\- push behavior





CRITICAL notifications may bypass some user preferences only

when explicitly permitted by security/business policy.



Do not allow arbitrary bypass behavior.





============================================================

6\. NOTIFICATION SOURCE

============================================================



Every notification should identify its origin.



Example:



sourceType = Task

sourceId = UUID





Example:



TaskOverdueEvent

&#x20;       ↓

Notification Engine

&#x20;       ↓

Notification





This allows users and administrators to understand where the

notification originated.





============================================================

7\. EVENT-DRIVEN ARCHITECTURE

============================================================



Business domains publish events.



Example:



TaskAssigned

&#x20;     ↓

Event Bus

&#x20;     ↓

Notification Engine

&#x20;     ↓

Notification Policy

&#x20;     ↓

Delivery Channels





Other examples:



TaskOverdue

ProjectDeadlineApproaching

DocumentApproved

DocumentRejected

WorkflowAssigned

MeetingInvitation

IncomingCall

MessageMentioned

DeviceOffline

MaintenanceDue

EmployeeEvaluationCompleted

SecurityAlert

AIRecommendationCreated





The source domain must NOT directly call:



sendEmail()

sendSms()

sendPush()





Instead:



Domain Event

&#x20;   ↓

Notification Application Layer





============================================================

8\. NOTIFICATION POLICY ENGINE

============================================================



Notification behavior must be configurable.



A policy determines:



\- whether notification is enabled

\- who receives it

\- priority

\- channels

\- template

\- schedule

\- retry policy

\- escalation

\- digest behavior





Example:



TaskOverdue



Policy:



Recipient:

&#x20;   Task Assignee



Channels:

&#x20;   In-App

&#x20;   Push

&#x20;   Email



Priority:

&#x20;   HIGH



Retry:

&#x20;   3 attempts



Escalation:

&#x20;   Manager after 24 hours





Policies must be configuration-driven.





============================================================

9\. RECIPIENT RESOLUTION

============================================================



Notification must support multiple recipient types.



Examples:



USER

ROLE

DEPARTMENT

TEAM

PROJECT

CHANNEL

ORGANIZATION

TENANT

EXTERNAL\_RECIPIENT





Recipient resolution must be handled by a dedicated service.



Example:



ResolveNotificationRecipientsService





Do NOT place recipient-resolution logic inside templates or

delivery providers.





============================================================

10\. USER NOTIFICATION PREFERENCES

============================================================



Users must control notification preferences.



Examples:



Task notifications:

&#x20;   In-App = ON

&#x20;   Push = ON

&#x20;   Email = OFF



Meeting notifications:

&#x20;   In-App = ON

&#x20;   Push = ON

&#x20;   Email = ON





Preferences may exist at multiple levels:



Global

Category

Notification Type

Channel





The most specific applicable preference wins.





============================================================

11\. TENANT NOTIFICATION POLICIES

============================================================



Tenant administrators may configure organizational rules.



Examples:



\- disable SMS

\- force security alerts

\- configure email provider

\- configure default digest frequency

\- configure retention

\- configure allowed channels





Tenant policies must never weaken mandatory platform-level

security rules.





============================================================

12\. DELIVERY CHANNELS

============================================================



The platform must support channel adapters.



Required conceptual interfaces:



NotificationChannel

NotificationProvider





Example channels:



InAppNotificationChannel

EmailNotificationChannel

PushNotificationChannel

SmsNotificationChannel

DesktopNotificationChannel

BrowserNotificationChannel





Infrastructure implementations may include:



SMTP

Firebase

APNs

Web Push

SMS Provider

Microsoft Graph

Other future providers





The domain must not depend on any provider.





============================================================

13\. PROVIDER ABSTRACTION

============================================================



Correct architecture:



Notification

&#x20;    ↓

Channel Interface

&#x20;    ↓

Provider Interface

&#x20;    ↓

Provider Adapter





Example:



EmailChannel

&#x20;    ↓

EmailProvider

&#x20;    ↓

SMTPProvider





Future:



EmailChannel

&#x20;    ↓

EmailProvider

&#x20;    ↓

MicrosoftGraphProvider





Changing the provider must not require modifying domain logic.





============================================================

14\. IN-APP NOTIFICATIONS

============================================================



In-App notifications are persisted.



The frontend retrieves them through REST APIs and may receive

real-time updates through WebSocket.



Architecture:



Business Event

&#x20;     ↓

Notification Engine

&#x20;     ↓

Database

&#x20;     ↓

WebSocket Event

&#x20;     ↓

Frontend





The WebSocket event is an optimization.



The database remains the source of truth for persistent

notification state.





============================================================

15\. PUSH NOTIFICATIONS

============================================================



Push delivery must support:



\- mobile

\- browser

\- desktop where supported





Device registration must be modeled separately.



Concept:



NotificationDevice



Properties:



\- id

\- user

\- tenant

\- platform

\- deviceIdentifier

\- pushToken

\- provider

\- createdAt

\- lastSeenAt

\- revokedAt

\- isActive





Never assume one user has one device.





============================================================

16\. EMAIL

============================================================



Email notification must support:



\- subject

\- HTML body

\- plain-text body

\- attachments where allowed

\- template

\- localization

\- reply-to

\- sender identity





Email sending must be asynchronous.



A web/API request must not wait for an external SMTP provider

unless explicitly required.





============================================================

17\. SMS

============================================================



SMS must be implemented through a provider abstraction.



Support:



\- provider selection

\- retry

\- delivery status

\- rate limiting

\- tenant configuration





SMS must be treated as an expensive delivery channel.



Default behavior should prevent accidental notification

storms.





============================================================

18\. NOTIFICATION TEMPLATES

============================================================



Templates must be separated from business logic.



Template contains:



\- template key

\- language

\- title

\- body

\- subject

\- channel

\- version

\- active status





Example:



task.overdue.v1





Template rendering receives structured data.



Example:



{

&#x20;   taskName,

&#x20;   projectName,

&#x20;   dueDate,

&#x20;   assigneeName

}





Templates must never execute arbitrary Python code.





============================================================

19\. TEMPLATE VERSIONING

============================================================



Templates must be versioned.



Example:



task.assigned.v1

task.assigned.v2





Existing historical notifications must remain interpretable

even if a template changes.





============================================================

20\. LOCALIZATION

============================================================



Notification must support localization.



Language resolution:



1\. User preference

2\. Organization policy

3\. Tenant default

4\. Platform default





Example:



fa-IR

en-US

de-DE





The notification engine must not assume a single language.





============================================================

21\. DIGESTS

============================================================



Users may receive grouped notifications.



Examples:



Hourly Digest

Daily Digest

Weekly Digest





Example:



Instead of:



20 separate task notifications



send:



"You have 20 task updates."





Digest generation must be asynchronous.





============================================================

22\. SCHEDULING

============================================================



Notifications may be:



Immediate

Scheduled

Recurring

Delayed

Digest-based





Example:



MeetingReminder:



scheduledAt =

meetingStart - 15 minutes





The scheduler must not depend on frontend execution.





============================================================

23\. EXPIRATION

============================================================



Notifications may expire.



Examples:



Meeting invitation expires after meeting start.



Temporary security challenge expires after a fixed duration.





Expired notifications must not be delivered.





============================================================

24\. RETRY

============================================================



External delivery can fail.



Retry policy must support:



\- max attempts

\- backoff

\- exponential backoff

\- retryable errors

\- permanent errors





Example:



Attempt 1

&#x20;   ↓

30 seconds



Attempt 2

&#x20;   ↓

2 minutes



Attempt 3

&#x20;   ↓

10 minutes





Never retry permanent errors indefinitely.





============================================================

25\. DELIVERY STATUS

============================================================



Each delivery channel must have its own status.



Example:



Notification:

&#x20;   DELIVERED



Email:

&#x20;   DELIVERED



Push:

&#x20;   FAILED



In-App:

&#x20;   DELIVERED





Therefore the system needs a delivery entity.



Concept:



NotificationDelivery





Properties:



\- id

\- notification

\- channel

\- provider

\- status

\- attemptCount

\- lastAttemptAt

\- deliveredAt

\- failedAt

\- errorCode

\- errorMessage





============================================================

26\. ACKNOWLEDGEMENT

============================================================



Read and acknowledgement are different concepts.



READ:



User has seen notification.



ACKNOWLEDGED:



User explicitly confirmed/accepted the notification.





Example:



Critical Safety Alert



READ ≠ ACKNOWLEDGED





This distinction is important for Enterprise workflows.





============================================================

27\. ESCALATION

============================================================



Notification policies may define escalation.



Example:



CriticalTaskOverdue



T+0:

&#x20;   Employee



T+24h:

&#x20;   Manager



T+48h:

&#x20;   Department Head





Escalation must be policy-driven.



Do not hard-code specific organizational structures.





============================================================

28\. RATE LIMITING

============================================================



Notification storms must be prevented.



Examples:



100 identical notifications

within 1 minute





Possible strategies:



\- throttling

\- aggregation

\- deduplication

\- cooldown

\- digest





Rate limiting may exist at:



User

Tenant

Notification Type

Channel

Provider





============================================================

29\. DEDUPLICATION

============================================================



Identical events may be delivered multiple times.



Notification generation must support idempotency.



Use an idempotency key.



Example:



notificationKey =

tenantId +

eventType +

eventId +

recipientId +

notificationType





The exact implementation may use a hashed key.





============================================================

30\. OUTBOX INTEGRATION

============================================================



Notification should consume reliable integration events.



Architecture:



Business Transaction

&#x20;       ↓

Outbox

&#x20;       ↓

Event Dispatcher

&#x20;       ↓

Notification Consumer

&#x20;       ↓

Notification Engine





This prevents lost notifications.





============================================================

31\. QUEUE / ASYNC PROCESSING

============================================================



External delivery must be asynchronous.



Concept:



API

&#x20;↓

Application Service

&#x20;↓

Database

&#x20;↓

Outbox

&#x20;↓

Message Broker / Worker

&#x20;↓

Notification Worker

&#x20;↓

Provider

&#x20;↓

External Channel





The final broker/worker technology must remain replaceable.





============================================================

32\. NOTIFICATION WORKER

============================================================



Worker responsibilities:



1\. receive notification job

2\. validate notification state

3\. resolve recipient

4\. resolve preferences

5\. resolve policy

6\. select channels

7\. render templates

8\. execute delivery

9\. persist result

10\. schedule retry if necessary

11\. emit delivery event





Worker must be idempotent.





============================================================

33\. SECURITY

============================================================



Notification system must protect:



\- recipient identity

\- message content

\- private information

\- tenant boundaries

\- provider credentials

\- push tokens

\- email addresses

\- phone numbers





Provider secrets must never be stored in source code.





============================================================

34\. MULTI-TENANCY

============================================================



Every persistent notification must be tenant-aware.



Forbidden:



User from Tenant A

&#x20;   ↓

Notification

&#x20;   ↓

User from Tenant B



unless explicit cross-tenant communication is introduced

through a controlled domain.





============================================================

35\. AUDIT

============================================================



Important notification actions must be auditable.



Examples:



NotificationCreated

NotificationScheduled

NotificationDelivered

NotificationFailed

NotificationRead

NotificationAcknowledged

NotificationCancelled

NotificationRetried

NotificationEscalated





Audit must distinguish:



business event



from



delivery event.





============================================================

36\. DATABASE DESIGN

============================================================



Initial conceptual tables:



notifications

notificationDeliveries

notificationPreferences

notificationPreferenceRules

notificationTemplates

notificationTemplateVersions

notificationPolicies

notificationPolicyChannels

notificationDevices

notificationDigests

notificationDigestItems

notificationSchedules





All tables must follow global Tekarai database standards:



\- UUID primary key

\- tenant relationship

\- createdAt

\- updatedAt

\- audit fields where appropriate

\- soft delete where appropriate

\- indexes

\- constraints

\- unique constraints





============================================================

37\. IMPORTANT INDEXES

============================================================



Notifications:



tenantId

recipientId

createdAt

status

category

priority





Unread queries:



recipientId

readAt

createdAt





Delivery:



notificationId

channel

status

nextAttemptAt





Preferences:



tenantId

userId

category

notificationType





Devices:



userId

isActive

platform





Idempotency:



tenantId

idempotencyKey





Indexes must be validated against real query patterns.





============================================================

38\. APPLICATION SERVICES

============================================================



Expected services:



CreateNotificationService



ScheduleNotificationService



CancelNotificationService



MarkNotificationReadService



AcknowledgeNotificationService



ResolveRecipientsService



ResolveNotificationPolicyService



ResolveNotificationPreferencesService



RenderNotificationService



DispatchNotificationService



RetryNotificationDeliveryService



CreateDigestService



SendDigestService



RegisterNotificationDeviceService



RevokeNotificationDeviceService





Responsibilities must remain focused.





============================================================

39\. REPOSITORIES

============================================================



Expected repository interfaces:



NotificationRepository

NotificationDeliveryRepository

NotificationPreferenceRepository

NotificationTemplateRepository

NotificationPolicyRepository

NotificationDeviceRepository

NotificationDigestRepository





Infrastructure implements them.





============================================================

40\. API

============================================================



REST endpoints must support:



List Notifications

Get Notification

Mark Read

Mark Unread

Acknowledge

Delete/Archive where allowed

Get Preferences

Update Preferences

List Devices

Register Device

Revoke Device





Administration APIs:



Manage Templates

Manage Policies

Manage Channels

Manage Tenant Notification Configuration





The API must enforce tenant and user permissions.





============================================================

41\. WEBSOCKET

============================================================



WebSocket should be used for real-time notification delivery.



Example:



NotificationCreated

&#x20;     ↓

Notification WebSocket Event

&#x20;     ↓

Connected Client





If the client is offline:



Notification remains persisted.



When the client reconnects:



Client synchronizes from REST/API state.





============================================================

42\. CLIENT SYNCHRONIZATION

============================================================



Client must not assume WebSocket delivery is reliable.



Correct model:



Database

&#x20;  ↓

Source of Truth



WebSocket

&#x20;  ↓

Real-Time Optimization



REST synchronization

&#x20;  ↓

Recovery mechanism





============================================================

43\. AI INTEGRATION

============================================================



AI may generate notifications.



Examples:



"Project Alpha is likely to miss its deadline."



"Employee performance decreased significantly."



"Machine failure probability increased."



"Important meeting action items remain unresolved."





AI-generated notifications must still pass through the

Notification Platform.



AI must not directly send:



email

SMS

push





AI:



AI Event

&#x20;  ↓

Notification Engine

&#x20;  ↓

Policy

&#x20;  ↓

Delivery





============================================================

44\. ANALYTICS

============================================================



Notification system should expose metrics such as:



notificationsCreated

notificationsDelivered

notificationsFailed

deliveryLatency

readRate

acknowledgementRate

channelUsage

retryRate

providerFailureRate

notificationVolume





These metrics feed the future Analytics platform.





============================================================

45\. OBSERVABILITY

============================================================



Structured logging must include:



\- notificationId

\- tenantId

\- recipientId

\- channel

\- provider

\- deliveryStatus

\- attempt

\- correlationId





Never log sensitive notification content unless explicitly

required and protected.





============================================================

46\. CORRELATION

============================================================



Every notification flow should support:



correlationId



and where appropriate:



causationId





Example:



TaskUpdated

&#x20;   correlationId = X



NotificationCreated

&#x20;   correlationId = X

&#x20;   causationId = TaskUpdatedEvent





This enables distributed tracing.





============================================================

47\. FAILURE ISOLATION

============================================================



Failure of one channel must not necessarily fail the whole

notification.



Example:



Email provider DOWN



must NOT prevent:



\- In-App notification

\- Push notification





The system should track partial delivery.





============================================================

48\. PROVIDER FAILOVER

============================================================



Future architecture must allow:



Primary Email Provider

&#x20;       ↓

Failure

&#x20;       ↓

Secondary Email Provider





Same principle applies to:



SMS

Push

Other external delivery providers





Failover must be configurable.





============================================================

49\. TESTING

============================================================



Required tests:



Unit Tests

Integration Tests

API Tests

Event Tests

Worker Tests

Provider Adapter Tests

Security Tests

Multi-Tenant Tests

Concurrency Tests

Idempotency Tests

Retry Tests





Critical scenarios:



\- duplicate event

\- duplicate notification

\- duplicate delivery

\- provider failure

\- timeout

\- retry

\- partial delivery

\- tenant isolation

\- preference override

\- critical notification

\- expired notification

\- cancelled notification

\- device revoked

\- offline user

\- digest generation





============================================================

50\. DEFINITION OF DONE

============================================================



Phase 9 is complete only when:



\[ ] Notification bounded context exists



\[ ] Notification aggregate exists



\[ ] Delivery model exists



\[ ] Notification preferences exist



\[ ] Notification policies exist



\[ ] Templates exist



\[ ] Template versioning exists



\[ ] Multi-language support exists



\[ ] In-App notifications work



\[ ] WebSocket delivery works



\[ ] Email adapter exists



\[ ] Push adapter exists



\[ ] SMS architecture exists



\[ ] Provider abstraction exists



\[ ] Device registration exists



\[ ] Scheduling exists



\[ ] Retry exists



\[ ] Exponential backoff exists



\[ ] Deduplication exists



\[ ] Idempotency exists



\[ ] Rate limiting exists



\[ ] Digest architecture exists



\[ ] Escalation exists



\[ ] Expiration exists



\[ ] Acknowledgement exists



\[ ] Outbox integration exists



\[ ] Async worker architecture exists



\[ ] Audit integration exists



\[ ] AI integration interface exists



\[ ] Analytics events exist



\[ ] Tenant isolation is enforced



\[ ] Security tests pass



\[ ] API tests pass



\[ ] Worker tests pass



\[ ] Integration tests pass



\[ ] Documentation exists





============================================================

END OF PHASE 9

============================================================

