============================================================

NOTE (2026-08-27): Contradictions resolved in CanonicalCommunication.md.
See: /home/user/Tekarai/docs/CanonicalCommunication.md

TEKARAI ENTERPRISE PLATFORM

PHASE 10 — COMMUNICATION PLATFORM

============================================================



PHASE OBJECTIVE

============================================================



در این فاز باید Communication Platform Tekarai به‌صورت

Enterprise Grade طراحی و پیاده‌سازی شود.



Communication نباید یک قابلیت فرعی داخل یک App ساده باشد.



Communication باید به‌عنوان یکی از Platform Capabilityهای

اصلی Tekarai طراحی شود.



سیستم باید از ابتدا برای موارد زیر آماده باشد:



\- Direct Messaging

\- Group Messaging

\- Channels

\- Presence

\- Voice Call

\- Group Voice Call

\- Video Call

\- Video Meeting

\- Screen Sharing

\- Meeting Management

\- Participant Management

\- Meeting Recording

\- Meeting Transcript

\- AI Meeting Summary

\- File Sharing

\- Document Sharing

\- Message Notifications

\- Real-Time Events

\- Audit

\- Permission Management

\- Future External Communication Providers





============================================================

1\. ARCHITECTURAL PRINCIPLES

============================================================



Communication Platform باید از اصول زیر پیروی کند:



\- Domain Driven Design

\- Clean Architecture

\- SOLID

\- Modular Monolith

\- Event Driven Architecture

\- API First

\- Security First

\- Multi-Tenant

\- Audit First

\- Extensibility First

\- Provider Agnostic

\- Real-Time Ready

\- Cloud Ready

\- Offline Ready

\- AI Native



هیچ Domain دیگری نباید مستقیماً منطق داخلی Communication را

کنترل کند.



Communication باید API و Domain Contract مشخص داشته باشد.





============================================================

2\. DOMAIN BOUNDARY

============================================================



Communication Domain شامل موارد زیر است:



Communication

&#x20;   |

&#x20;   +── Conversations

&#x20;   |

&#x20;   +── Messages

&#x20;   |

&#x20;   +── Channels

&#x20;   |

&#x20;   +── Participants

&#x20;   |

&#x20;   +── Presence

&#x20;   |

&#x20;   +── Calls

&#x20;   |

&#x20;   +── Meetings

&#x20;   |

&#x20;   +── Recordings

&#x20;   |

&#x20;   +── Transcripts

&#x20;   |

&#x20;   +── Reactions

&#x20;   |

&#x20;   +── Attachments

&#x20;   |

&#x20;   +── Notifications Integration

&#x20;   |

&#x20;   +── AI Integration

&#x20;   |

&#x20;   +── Audit Integration





Communication Domain نباید مسئول موارد زیر باشد:



\- User Identity

\- Employee Management

\- Organization Structure

\- File Storage Infrastructure

\- AI Model Execution

\- Notification Delivery Infrastructure

\- Authentication



این موارد توسط Domain یا Infrastructure مربوط به خودشان

مدیریت می‌شوند.





============================================================

3\. COMMUNICATION CORE CONCEPT

============================================================



مفهوم اصلی سیستم باید Conversation باشد.



Conversation می‌تواند یکی از انواع زیر باشد:



DIRECT

GROUP

CHANNEL

MEETING



هر Conversation دارای:



\- ID

\- Tenant

\- Type

\- Name

\- Description

\- Created By

\- Created At

\- Updated At

\- Status

\- Metadata



است.





============================================================

4\. CONVERSATION

============================================================



Entity:



Conversation



Fields:



id

tenantId

type

name

description

createdBy

createdAt

updatedAt

isActive

metadata



Conversation Type:



DIRECT

GROUP

CHANNEL

MEETING



Conversation باید قابلیت Archive شدن داشته باشد.



Conversation حذف فیزیکی نمی‌شود مگر اینکه Policy سیستم

صراحتاً اجازه دهد.



Soft Delete باید رعایت شود.





============================================================

5\. CONVERSATION PARTICIPANT

============================================================



Entity:



ConversationParticipant



Fields:



id

conversationId

userId

role

status

joinedAt

leftAt

lastReadMessageId

mutedUntil

notificationsEnabled

createdAt

updatedAt



Participant Role:



OWNER

ADMIN

MODERATOR

MEMBER

GUEST



Participant Status:



ACTIVE

LEFT

REMOVED

BANNED



Business Rules:



1\. هر Conversation حداقل یک Owner دارد.



2\. Owner نمی‌تواند بدون انتقال مالکیت حذف شود.



3\. Participant حذف‌شده نباید بتواند Message جدید ارسال کند.



4\. Participant می‌تواند Conversation را mute کند.



5\. آخرین Message خوانده‌شده باید قابل ثبت باشد.



6\. Permissionها باید در Domain کنترل شوند.





============================================================

6\. DIRECT MESSAGE

============================================================



Direct Message باید بین دو User ایجاد شود.



سیستم نباید اجازه ایجاد چند Conversation فعال برای

همان دو User را بدهد.



مثلاً:



User A

User B



باید یک Direct Conversation منطقی داشته باشند.



اگر Conversation قبلی وجود داشته باشد:



Conversation جدید ساخته نشود.



Conversation موجود دوباره استفاده شود.





============================================================

7\. GROUP CHAT

============================================================



Group Conversation باید امکان موارد زیر را داشته باشد:



\- Add Member

\- Remove Member

\- Promote Member

\- Demote Member

\- Rename Group

\- Change Description

\- Change Avatar

\- Mute

\- Archive

\- Leave Group



تمام عملیات مهم باید Audit شوند.





============================================================

8\. CHANNEL

============================================================



Channel باید برای ارتباط سازمانی طراحی شود.



Channel Type:



PUBLIC

PRIVATE

RESTRICTED



Channel می‌تواند متعلق به یک Organization Context باشد.



Channel باید امکان:



\- Members

\- Moderators

\- Posts

\- Replies

\- Mentions

\- Attachments

\- Reactions

\- Notifications



داشته باشد.



Channel نباید به Employee یا Department خاصی hard-code شود.





============================================================

9\. MESSAGE

============================================================



Entity:



Message



Fields:



id

tenantId

conversationId

senderId

messageType

body

replyToId

threadRootId

editedAt

deletedAt

createdAt

updatedAt

metadata



Message Types:



TEXT

SYSTEM

FILE

IMAGE

VIDEO

AUDIO

DOCUMENT

LINK

CALL\_EVENT

MEETING\_EVENT

AI\_GENERATED





============================================================

10\. MESSAGE LIFECYCLE

============================================================



Message State:



CREATED

DELIVERED

READ

EDITED

DELETED



Message lifecycle باید Event Driven باشد.



نمونه:



MessageCreated

&#x20;   ↓

MessageDelivered

&#x20;   ↓

MessageRead



MessageEdited



MessageDeleted





============================================================

11\. MESSAGE EDIT

============================================================



Message باید قابل Edit باشد.



اما Edit نباید تاریخچه را نابود کند.



در صورت نیاز باید MessageRevision ایجاد شود.



Entity:



MessageRevision



Fields:



id

messageId

previousBody

newBody

editedBy

editedAt





این قابلیت برای Audit و Enterprise Compliance مهم است.





============================================================

12\. MESSAGE DELETE

============================================================



Delete باید Soft Delete باشد.



اطلاعات اصلی نباید بلافاصله از Database حذف شود.



MessageDeleted Event تولید شود.



برای Compliance باید امکان نگهداری Audit History وجود داشته باشد.





============================================================

13\. MESSAGE REACTION

============================================================



Entity:



MessageReaction



Fields:



id

messageId

userId

reactionType

createdAt



کاربر نباید بتواند یک Reaction مشابه را چند بار

روی یک Message ثبت کند.





============================================================

14\. MESSAGE THREAD

============================================================



Message باید قابلیت Thread داشته باشد.



ساختار:



Message

&#x20;   |

&#x20;   +── Reply

&#x20;   +── Reply

&#x20;   +── Reply



Thread باید Conversation را شلوغ نکند.



هر Reply باید:



replyToId

threadRootId



داشته باشد.





============================================================

15\. MESSAGE MENTION

============================================================



سیستم باید Mention را پشتیبانی کند.



مثال:



@User



@Channel



@Everyone



Mention باید به Notification Platform متصل شود.





============================================================

16\. ATTACHMENT

============================================================



Communication نباید فایل را مستقیماً داخل Database ذخیره کند.



فایل باید توسط File/Document Storage Platform مدیریت شود.



Communication فقط Reference نگهداری می‌کند.



مثلاً:



Attachment



id

messageId

documentId

fileName

mimeType

size

createdAt



Communication نباید Storage Provider خاصی را hard-code کند.





============================================================

17\. PRESENCE SYSTEM

============================================================



Presence باید وضعیت لحظه‌ای User را مشخص کند.



Status:



ONLINE

AWAY

BUSY

DO\_NOT\_DISTURB

OFFLINE

INVISIBLE



Presence باید Real-Time باشد.



اطلاعات Presence نباید فقط از Database خوانده شود.



برای Real-Time Presence باید از:



Django Channels

Redis



استفاده شود.





============================================================

18\. USER PRESENCE

============================================================



Presence Record می‌تواند شامل:



userId

tenantId

status

lastSeenAt

connectedAt

deviceId

connectionId



باشد.



یک User ممکن است همزمان چند Device داشته باشد.



بنابراین Presence نباید فرض کند:



One User = One Connection





============================================================

19\. DEVICE PRESENCE

============================================================



هر Connection باید قابل شناسایی باشد.



مثلاً:



Desktop

Web

Mobile

Tablet



سیستم باید بتواند Presence را در سطح Device مدیریت کند.





============================================================

20\. REAL-TIME ARCHITECTURE

============================================================



Real-Time Communication باید با:



Django Channels

Redis



پیاده‌سازی شود.



Architecture:



Client

&#x20;  |

WebSocket

&#x20;  |

Django Channels

&#x20;  |

Channel Layer

&#x20;  |

Redis

&#x20;  |

Communication Application Layer

&#x20;  |

Domain





Business Logic نباید مستقیماً داخل Consumer نوشته شود.





============================================================

21\. WEBSOCKET RULE

============================================================



Consumer فقط باید مسئول:



\- Connection

\- Authentication Context

\- Subscription

\- Receiving Event

\- Sending Event



باشد.



Consumer نباید:



\- Business Rule

\- Database Business Logic

\- Permission Logic

\- Message Creation Logic



را مستقیماً اجرا کند.



Consumer باید Application Service را صدا بزند.





============================================================

22\. CALL PLATFORM

============================================================



سیستم باید Voice و Video Communication را پشتیبانی کند.



Call Type:



AUDIO

VIDEO



Call Scope:



DIRECT

GROUP

MEETING





============================================================

23\. CALL ENTITY

============================================================



Entity:



CallSession



Fields:



id

tenantId

conversationId

initiatorId

type

status

startedAt

endedAt

provider

providerSessionId

metadata



Call Status:



INITIATED

RINGING

ACTIVE

ENDED

FAILED

CANCELLED





============================================================

24\. CALL PARTICIPANT

============================================================



Entity:



CallParticipant



Fields:



id

callSessionId

userId

joinedAt

leftAt

status

deviceId

metadata





============================================================

25\. CALL PROVIDER ABSTRACTION

============================================================



Communication نباید به WebRTC implementation خاصی

وابسته شود.



Interface تعریف شود:



CallProvider



Operations:



createSession()

joinSession()

leaveSession()

endSession()

getSessionStatus()



Providerهای آینده:



WebRTC

Twilio

Agora

Jitsi

Microsoft Teams Integration

Other Providers



نباید نیاز به تغییر Domain داشته باشند.





============================================================

26\. WEBRTC

============================================================



WebRTC باید به‌عنوان یکی از Provider/Transportهای

Communication در نظر گرفته شود.



WebRTC مسئول:



\- Media Transport

\- Audio

\- Video

\- Screen Stream



است.



Business Domain نباید WebRTC API را مستقیماً بشناسد.





============================================================

27\. MEETING

============================================================



Meeting یک مفهوم Enterprise است و با Call ساده یکی نیست.



Meeting باید شامل:



id

tenantId

conversationId

title

description

organizerId

scheduledStart

scheduledEnd

actualStart

actualEnd

status

meetingType

joinPolicy

recordingPolicy

createdAt

updatedAt





============================================================

28\. MEETING STATUS

============================================================



SCHEDULED

WAITING

LIVE

ENDED

CANCELLED





============================================================

29\. MEETING PARTICIPANT

============================================================



MeetingParticipant:



id

meetingId

userId

role

invitedAt

joinedAt

leftAt

status

attendanceDuration

metadata



Roles:



HOST

CO\_HOST

PARTICIPANT

GUEST





============================================================

30\. MEETING PERMISSIONS

============================================================



Meeting باید Permissionهای زیر را پشتیبانی کند:



CAN\_JOIN

CAN\_SPEAK

CAN\_VIDEO

CAN\_SHARE\_SCREEN

CAN\_RECORD

CAN\_CHAT

CAN\_INVITE

CAN\_REMOVE\_PARTICIPANT

CAN\_END\_MEETING





============================================================

31\. SCREEN SHARING

============================================================



Screen Sharing باید به‌عنوان Media Capability تعریف شود.



Types:



SCREEN

WINDOW

TAB



Domain فقط Event و Capability را مدیریت می‌کند.



Media Transport توسط WebRTC/Provider انجام می‌شود.





============================================================

32\. RECORDING

============================================================



Recording باید Metadata داشته باشد.



Entity:



MeetingRecording



Fields:



id

meetingId

startedAt

endedAt

duration

storageReference

format

size

status

createdBy

createdAt



Recording File نباید داخل Database ذخیره شود.





============================================================

33\. RECORDING STATUS

============================================================



REQUESTED

RECORDING

PROCESSING

READY

FAILED

DELETED





============================================================

34\. TRANSCRIPT

============================================================



Meeting Transcript باید مستقل از Recording باشد.



Entity:



MeetingTranscript



Fields:



id

meetingId

language

status

contentReference

createdAt

updatedAt





Transcript Status:



PENDING

PROCESSING

READY

FAILED





============================================================

35\. TRANSCRIPT SEGMENTS

============================================================



در صورت نیاز Transcript باید Segment داشته باشد.



TranscriptSegment:



id

transcriptId

speakerId

startTime

endTime

text

confidence





این ساختار برای AI Meeting Analysis ضروری است.





============================================================

36\. AI MEETING SUMMARY

============================================================



AI نباید مستقیماً داخل Communication Domain پیاده‌سازی شود.



Communication فقط AI Service را صدا می‌زند.



Flow:



Meeting End

&#x20;   ↓

Recording / Transcript

&#x20;   ↓

AI Analysis

&#x20;   ↓

Summary

&#x20;   ↓

Action Items

&#x20;   ↓

Decisions

&#x20;   ↓

Tasks





============================================================

37\. AI MEETING OUTPUT

============================================================



AI می‌تواند موارد زیر تولید کند:



\- Summary

\- Key Points

\- Decisions

\- Action Items

\- Participants

\- Topics

\- Risks

\- Follow Ups

\- Extracted Tasks



Task ایجادشده باید به Task Domain ارسال شود.



Communication نباید Task Model را مستقیماً مدیریت کند.





============================================================

38\. NOTIFICATION INTEGRATION

============================================================



Communication باید Event تولید کند.



Examples:



MessageCreated

MessageMentioned

MessageReceived

CallIncoming

MeetingInvitation

MeetingStarting

ParticipantJoined

ParticipantLeft

MeetingEnded





Notification Platform مسئول Delivery است.





============================================================

39\. AUDIT INTEGRATION

============================================================



تمام عملیات حساس باید Audit شوند.



حداقل:



\- ConversationCreated

\- ConversationUpdated

\- ParticipantAdded

\- ParticipantRemoved

\- ParticipantRoleChanged

\- MessageCreated

\- MessageEdited

\- MessageDeleted

\- MeetingCreated

\- MeetingCancelled

\- RecordingStarted

\- RecordingDeleted

\- CallStarted

\- CallEnded



Audit باید شامل Actor و Timestamp و Tenant باشد.





============================================================

40\. SECURITY

============================================================



Communication باید Security First باشد.



Rules:



\- Tenant Isolation

\- Object Level Authorization

\- Conversation Permission

\- Participant Permission

\- Message Authorization

\- Attachment Authorization

\- Meeting Authorization

\- Recording Authorization



User نباید بتواند با تغییر UUID به Conversation

Tenant دیگر دسترسی پیدا کند.





============================================================

41\. MULTI-TENANCY

============================================================



تمام Communication Entities باید Tenant-aware باشند.



Tenant ID باید در Queryهای حساس enforce شود.



Cross-Tenant Communication به‌صورت پیش‌فرض ممنوع است.



اگر در آینده Cross-Tenant Communication لازم شد،

باید Capability مستقل داشته باشد.





============================================================

42\. DATABASE INDEXING

============================================================



حداقل Indexهای مورد نیاز:



Conversation:



tenantId

tenantId + type

tenantId + createdAt



Participant:



conversationId

userId

conversationId + userId



Message:



conversationId + createdAt

senderId

replyToId

threadRootId



Presence:



tenantId + userId

userId + status



Meeting:



tenantId + scheduledStart

organizerId

status



Call:



conversationId

initiatorId

status



Indexها باید بر اساس Query Pattern واقعی تکمیل شوند.





============================================================

43\. CONSTRAINTS

============================================================



Database Constraintها باید برای Integrity استفاده شوند.



مثلاً:



Unique:

conversation + user participant



Unique:

message + reaction + user



Unique:

tenant + channel code



Foreign Key Integrity



Check Constraints در موارد مناسب





============================================================

44\. DOMAIN EVENTS

============================================================



Communication باید Eventهای Domain مشخص داشته باشد.



حداقل:



ConversationCreated

ConversationArchived

ParticipantAdded

ParticipantRemoved



MessageCreated

MessageEdited

MessageDeleted

MessageRead

MessageReactionAdded



PresenceChanged



CallStarted

CallEnded

ParticipantJoinedCall

ParticipantLeftCall



MeetingCreated

MeetingStarted

MeetingEnded

ParticipantJoinedMeeting

ParticipantLeftMeeting



RecordingStarted

RecordingReady



TranscriptReady



MeetingSummaryGenerated





============================================================

45\. APPLICATION SERVICES

============================================================



Application Services باید Use Caseها را پیاده کنند.



حداقل:



CreateConversation

GetConversation

ArchiveConversation



AddParticipant

RemoveParticipant

ChangeParticipantRole



SendMessage

EditMessage

DeleteMessage

MarkMessageAsRead

AddReaction

RemoveReaction



CreateChannel

UpdateChannel



UpdatePresence



StartCall

JoinCall

LeaveCall

EndCall



CreateMeeting

StartMeeting

JoinMeeting

LeaveMeeting

EndMeeting



StartRecording

StopRecording



GenerateTranscript



GenerateMeetingSummary





============================================================

46\. DOMAIN SERVICES

============================================================



Business Ruleهای پیچیده باید در Domain Service باشند.



مثلاً:



ConversationPermissionService

ParticipantPolicy

MessagePolicy

MeetingPermissionService

CallPolicy





============================================================

47\. REPOSITORIES

============================================================



Domain نباید مستقیماً به Django ORM وابسته باشد.



Interface:



ConversationRepository

MessageRepository

ParticipantRepository

MeetingRepository

CallRepository

PresenceRepository





Infrastructure implementation:



Django ORM Repository





============================================================

48\. API

============================================================



REST API باید برای عملیات معمول استفاده شود.



نمونه:



/api/v1/communication/conversations/

/api/v1/communication/messages/

/api/v1/communication/channels/

/api/v1/communication/meetings/

/api/v1/communication/calls/

/api/v1/communication/presence/





API Versioning اجباری است.





============================================================

49\. WEBSOCKET API

============================================================



نمونه:



/ws/v1/communication/



Connection باید Authentication داشته باشد.



User فقط باید Eventهایی را دریافت کند که مجاز به دریافت

آنهاست.





============================================================

50\. EVENT CONTRACT

============================================================



تمام Real-Time Eventها باید Schema مشخص داشته باشند.



مثلاً:



{

&#x20;   "event": "message.created",

&#x20;   "version": 1,

&#x20;   "tenantId": "...",

&#x20;   "conversationId": "...",

&#x20;   "messageId": "...",

&#x20;   "timestamp": "...",

&#x20;   "payload": {}

}





Event Contract باید Versioned باشد.





============================================================

51\. OFFLINE SUPPORT

============================================================



Communication باید برای Offline Client آماده باشد.



Client باید بتواند:



\- دریافت Messageهای از دست رفته

\- Sync

\- Retry

\- Conflict Detection



را انجام دهد.



Message باید قابلیت Idempotency داشته باشد.





============================================================

52\. IDEMPOTENCY

============================================================



برای عملیات حساس مانند:



Send Message

Create Meeting

Join Meeting



باید امکان Idempotency وجود داشته باشد.



Client Retry نباید باعث Duplicate Operation شود.





============================================================

53\. PAGINATION

============================================================



Message List نباید Offset Pagination ساده در حجم بالا

استفاده کند.



برای Message History باید Cursor Pagination استفاده شود.



مثلاً:



before

after

cursor



ترجیحاً بر اساس:



createdAt

id



ترکیبی برای ordering پایدار.





============================================================

54\. MESSAGE SEARCH

============================================================



Search باید به‌عنوان Capability مستقل طراحی شود.



Communication Domain نباید به Search Engine خاصی وابسته باشد.



Future Providers:



SQL Search

Full Text Search

Elasticsearch

OpenSearch

Other Search Engine





============================================================

55\. RETENTION

============================================================



Enterprise Customer ممکن است Policyهای متفاوت داشته باشد.



مثلاً:



Message Retention

Recording Retention

Transcript Retention



Retention باید Configurable و Tenant-aware باشد.





============================================================

56\. COMPLIANCE

============================================================



Communication باید برای آینده آماده موارد زیر باشد:



\- Legal Hold

\- Retention Policy

\- Audit

\- Export

\- Data Access

\- Data Deletion Policy

\- Compliance Reporting



این قابلیت‌ها نباید با حذف فیزیکی ساده طراحی شوند.





============================================================

57\. OBSERVABILITY

============================================================



Communication باید Metrics داشته باشد.



حداقل:



messagesSentTotal

messagesFailedTotal

activeConnections

activeCalls

activeMeetings

websocketConnections

messageDeliveryLatency

messageProcessingLatency

callFailureRate





Logs باید Structured باشند.





============================================================

58\. TESTING

============================================================



تست‌ها باید شامل:



Unit Tests

Domain Tests

Application Tests

Repository Tests

API Tests

Permission Tests

Integration Tests

WebSocket Tests

Concurrency Tests

Idempotency Tests

Multi-Tenant Tests





============================================================

59\. SECURITY TESTS

============================================================



باید صراحتاً تست شود:



Tenant A cannot access Tenant B.



User A cannot access private Conversation of User B.



Removed participant cannot send messages.



Unauthorized user cannot read recording.



Unauthorized user cannot join meeting.



Unauthorized user cannot receive WebSocket events.





============================================================

60\. PERFORMANCE TESTS

============================================================



باید برای موارد زیر Load Test طراحی شود:



\- Message Sending

\- Message Retrieval

\- WebSocket Connections

\- Presence Updates

\- Group Chat

\- Large Channel

\- Large Meeting





============================================================

61\. PROJECT STRUCTURE

============================================================



ساختار پیشنهادی:



apps/

&#x20;   communication/

&#x20;       \_\_init\_\_.py



&#x20;       domain/

&#x20;           entities/

&#x20;           valueObjects/

&#x20;           events/

&#x20;           services/

&#x20;           repositories/

&#x20;           policies/



&#x20;       application/

&#x20;           commands/

&#x20;           queries/

&#x20;           services/

&#x20;           dto/



&#x20;       infrastructure/

&#x20;           models/

&#x20;           repositories/

&#x20;           providers/

&#x20;           persistence/



&#x20;       interfaces/

&#x20;           api/

&#x20;           websocket/



&#x20;       tests/

&#x20;           unit/

&#x20;           integration/

&#x20;           api/

&#x20;           websocket/



&#x20;       apps.py





در صورت استفاده از معماری فعلی Repository،

ساختار باید با Architecture Specification اصلی Tekarai

هماهنگ شود.



نباید بدون دلیل Architecture جدیدی اختراع شود.





============================================================

62\. DJANGO RULE

============================================================



Django Model فقط Persistence Model است.



Business Logic نباید در:



models.py

views.py

serializers.py

consumers.py



پخش شود.



Business Logic باید در:



Domain

Application



قرار گیرد.





============================================================

63\. SERIALIZER RULE

============================================================



Serializer مسئول:



\- Input Validation

\- Output Serialization



است.



Serializer نباید Business Workflow را اجرا کند.





============================================================

64\. VIEW RULE

============================================================



View فقط:



Request

&#x20;   ↓

Authentication

&#x20;   ↓

Permission

&#x20;   ↓

Application Service

&#x20;   ↓

Response



را مدیریت کند.





============================================================

65\. TRANSACTION MANAGEMENT

============================================================



عملیات Atomic باید با Transaction مدیریت شوند.



مثلاً:



Send Message



باید Message و Event/Outbox مربوطه را به شکل

Transactionally Consistent مدیریت کند.





============================================================

66\. OUTBOX PATTERN

============================================================



برای Eventهای مهم باید Outbox Pattern در نظر گرفته شود.



Flow:



Database Transaction

&#x20;       ↓

Domain Change

&#x20;       ↓

Outbox Event

&#x20;       ↓

Event Dispatcher

&#x20;       ↓

Redis / Notification / AI / Other Systems





این کار برای جلوگیری از Lost Event ضروری است.





============================================================

67\. REDIS

============================================================



Redis می‌تواند برای:



\- WebSocket Channel Layer

\- Presence

\- Short-lived State

\- Distributed Locks

\- Rate Limiting

\- Pub/Sub



استفاده شود.



Redis نباید Source of Truth برای داده‌های دائمی باشد.





============================================================

68\. RATE LIMITING

============================================================



باید برای موارد زیر Rate Limit وجود داشته باشد:



Send Message

Create Conversation

Call Start

Meeting Create

WebSocket Connection

Presence Update





============================================================

69\. ABUSE PROTECTION

============================================================



سیستم باید برای آینده آماده:



Spam Detection

Message Flood Protection

User Blocking

Conversation Blocking

Rate Limiting



باشد.





============================================================

70\. USER BLOCKING

============================================================



User باید بتواند User دیگری را Block کند.



Block باید روی:



Direct Message

Call

Meeting Invitation



اعمال شود؛ مگر Permission/Policy سازمانی خلاف آن باشد.





============================================================

71\. ARCHITECTURAL DEPENDENCY RULE

============================================================



Communication:



MAY depend on:



Identity

Organization

File/Document

Notification

Audit

AI Contracts



Communication MUST NOT depend on concrete implementations

of these systems.



مثلاً:



Communication → AI Interface



مجاز است.



Communication → Concrete OpenAI Client



غلط است.





============================================================

72\. DEFINITION OF DONE

============================================================



Phase 10 فقط زمانی Complete است که:



\[ ] Communication Domain مشخص شده باشد.



\[ ] Entityها طراحی شده باشند.



\[ ] Relationships مشخص باشند.



\[ ] Business Rules مشخص باشند.



\[ ] Permission Model مشخص باشد.



\[ ] Multi-Tenant Isolation مشخص باشد.



\[ ] Message Lifecycle طراحی شده باشد.



\[ ] Conversation Lifecycle طراحی شده باشد.



\[ ] Presence Architecture طراحی شده باشد.



\[ ] WebSocket Architecture طراحی شده باشد.



\[ ] Call Architecture طراحی شده باشد.



\[ ] Meeting Architecture طراحی شده باشد.



\[ ] Recording Architecture طراحی شده باشد.



\[ ] Transcript Architecture طراحی شده باشد.



\[ ] AI Integration Contract طراحی شده باشد.



\[ ] Notification Integration طراحی شده باشد.



\[ ] Audit Integration طراحی شده باشد.



\[ ] Repository Interfaces طراحی شده باشند.



\[ ] Application Services مشخص شده باشند.



\[ ] Domain Services مشخص شده باشند.



\[ ] REST API Contract مشخص شده باشد.



\[ ] WebSocket Contract مشخص شده باشد.



\[ ] Event Contract مشخص شده باشد.



\[ ] Database Index Strategy مشخص شده باشد.



\[ ] Retention Strategy مشخص شده باشد.



\[ ] Security Model مشخص شده باشد.



\[ ] Testing Strategy مشخص شده باشد.



\[ ] Performance Strategy مشخص شده باشد.



\[ ] Observability Strategy مشخص شده باشد.



\[ ] Outbox Strategy مشخص شده باشد.





============================================================

73\. IMPLEMENTATION ORDER

============================================================



Implementation باید به ترتیب زیر انجام شود:



STEP 1

Communication Domain Specification



STEP 2

Conversation



STEP 3

ConversationParticipant



STEP 4

Message



STEP 5

MessageRevision



STEP 6

MessageReaction



STEP 7

MessageThread



STEP 8

Channel



STEP 9

Application Services



STEP 10

Repository Interfaces



STEP 11

Django Persistence Models



STEP 12

Database Constraints



STEP 13

REST API



STEP 14

Permission System



STEP 15

Domain Events



STEP 16

Outbox



STEP 17

Redis Integration



STEP 18

WebSocket Layer



STEP 19

Presence



STEP 20

Call Abstraction



STEP 21

Meeting



STEP 22

Meeting Participants



STEP 23

Recording



STEP 24

Transcript



STEP 25

AI Integration



STEP 26

Notification Integration



STEP 27

Audit Integration



STEP 28

Search Integration



STEP 29

Retention



STEP 30

Observability



STEP 31

Tests



STEP 32

Security Tests



STEP 33

Performance Tests





============================================================

74\. DO NOT DO

============================================================



در این فاز موارد زیر ممنوع است:



\- قرار دادن Business Logic داخل View

\- قرار دادن Business Logic داخل Serializer

\- قرار دادن Business Logic داخل Django Consumer

\- اتصال مستقیم Domain به Django ORM

\- اتصال مستقیم Domain به Redis

\- اتصال مستقیم Domain به WebRTC

\- اتصال مستقیم Domain به OpenAI

\- ذخیره فایل داخل Database

\- ذخیره دائمی Presence در Redis به‌عنوان Source of Truth

\- Cross-Tenant Query بدون کنترل

\- Hard-code کردن Provider

\- Hard-code کردن Industry

\- حذف فیزیکی Message بدون Policy

\- استفاده از Offset Pagination برای Message History حجیم

\- ایجاد Duplicate Direct Conversation

\- ایجاد Duplicate Reaction

\- ارسال Event بدون کنترل Transaction

\- ایجاد API بدون Permission

\- ایجاد WebSocket بدون Authorization





============================================================

75\. PHASE 10 FINAL OUTPUT

============================================================



خروجی نهایی Phase 10 باید شامل:



1\. Communication Architecture Specification



2\. Communication Domain Model



3\. Communication ERD



4\. Communication Database Dictionary



5\. Communication Business Rules



6\. Permission Matrix



7\. REST API Specification



8\. WebSocket Specification



9\. Event Contract Specification



10\. Provider Abstraction Specification



11\. WebRTC Integration Specification



12\. Meeting Specification



13\. Recording Specification



14\. Transcript Specification



15\. AI Integration Specification



16\. Notification Integration Specification



17\. Audit Integration Specification



18\. Retention Specification



19\. Security Specification



20\. Testing Specification



21\. Performance Specification



22\. Observability Specification



23\. Implementation Plan



24\. Migration Plan





============================================================

PHASE 10 COMPLETION CONDITION

============================================================



Phase 10 زمانی تمام شده است که Communication Platform

به‌صورت یک Domain مستقل، قابل تست، قابل توسعه، Multi-Tenant،

Real-Time، Secure و Provider-Agnostic طراحی و پیاده‌سازی شده

باشد و هیچ Business Logic مهمی خارج از مرزهای معماری تعریف‌شده

قرار نگرفته باشد.



پس از تأیید کامل Phase 10، پروژه وارد Phase 11 می‌شود.



============================================================

END OF PHASE 10

============================================================

