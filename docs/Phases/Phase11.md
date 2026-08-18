MERYX — PHASE 11

COMMUNICATION PLATFORM

Enterprise Communication, Messaging, Presence \& Meetings

1\. هدف فاز



در این فاز باید Communication Platform مریکس به‌صورت کامل و Enterprise طراحی و پیاده‌سازی شود.



Communication نباید یک Chat ساده باشد.



این فاز باید یک زیرساخت ارتباطی عمومی، Multi-Tenant، Extensible، Auditable و قابل توسعه برای سال‌های آینده ایجاد کند که بتواند موارد زیر را پشتیبانی کند:



Direct Chat

Group Chat

Channels

Public Channels

Private Channels

Official Communication

Internal Messaging

Presence

Typing Indicators

Read Receipts

Message Reactions

Message Editing

Message Deletion

Message Attachments

Message Replies

Message Threads

Mentions

Message Search

Voice Call

Group Voice Call

Video Call

Group Video Meeting

Screen Sharing

Meeting Rooms

Meeting Participants

Meeting Recording

Meeting Transcription

AI Meeting Summary

AI Action Item Extraction

Communication Notifications

Communication Audit

Communication Retention

Communication Permissions

2\. اصل معماری



Communication باید به‌عنوان یک Domain مستقل طراحی شود.



نباید:



مستقیماً به UI وابسته باشد.

منطق Business آن داخل View نوشته شود.

مستقیماً به WebSocket Handler وابسته باشد.

مستقیماً به Redis وابسته باشد.

مستقیماً به WebRTC وابسته باشد.

منطق AI داخل مدل‌های Django قرار گیرد.



معماری:



Presentation

&#x20;   ↓

Application

&#x20;   ↓

Domain

&#x20;   ↓

Infrastructure



و:



Web API

WebSocket

WebRTC

Mobile

Desktop

Agent

AI

&#x20;   ↓

Communication Application Layer

&#x20;   ↓

Communication Domain

&#x20;   ↓

Infrastructure

3\. جایگاه Communication در Meryx



ساختار منطقی:



Meryx

│

├── Platform

├── Identity

├── Organization

├── HR

├── Projects

├── Tasks

├── Assets

├── Documents

├── Workflow

├── Communication

│   ├── Messaging

│   ├── Channels

│   ├── Presence

│   ├── Calls

│   ├── Meetings

│   ├── Recording

│   └── Communication AI

├── Notifications

├── Analytics

├── AI

└── Integration Hub



Communication باید بتواند با سایر Domainها Integration داشته باشد ولی مالک داده‌های Domainهای دیگر نباشد.



4\. Multi-Tenancy



تمام Communication Data باید Tenant-aware باشد.



حداقل موجودیت‌های زیر باید Tenant داشته باشند:



Conversation

ConversationMember

Channel

ChannelMember

Message

MessageAttachment

Call

Meeting

MeetingParticipant

MeetingRecording

CommunicationPolicy



هیچ Query مربوط به Communication نباید بدون Tenant Context اجرا شود.



5\. Conversation



Conversation Aggregate Root اصلی Messaging است.



انواع:



DIRECT

GROUP

CHANNEL

SYSTEM



Conversation باید شامل:



id

tenant

type

name

description

created\_by

created\_at

updated\_at

is\_active

deleted\_at



برای Direct Conversation نباید اجازه ایجاد چند Conversation فعال بین یک زوج User داده شود.



6\. ConversationMember



برای عضویت افراد:



ConversationMember



Fields:



id

conversation

user

role

joined\_at

left\_at

is\_active

last\_read\_message

muted\_until

notification\_level



Roles:



OWNER

ADMIN

MODERATOR

MEMBER

READ\_ONLY

7\. Direct Chat



Direct Chat باید:



User A

&#x20;   ↕

Conversation

&#x20;   ↕

User B



باشد.



نباید برای Direct Chat جدول جداگانه‌ای ایجاد شود مگر در آینده نیاز Performance یا Domain خاصی ایجاد شود.



8\. Group Chat



Group Chat باید بتواند:



چند کاربر داشته باشد.

Owner داشته باشد.

Admin داشته باشد.

Member اضافه کند.

Member حذف کند.

Member Leave کند.

نام داشته باشد.

Description داشته باشد.

تصویر داشته باشد.

Notification policy داشته باشد.

9\. Channel



Channel یک مفهوم مستقل از Group Chat است.



انواع:



PUBLIC

PRIVATE

RESTRICTED

ANNOUNCEMENT



Channel باید بتواند به Organization، Department، Project یا سایر Business Contextها متصل شود.



اما نباید به آنها وابسته باشد.



مثلاً:



Project

&#x20;  ↓

Channel



یک Integration Reference است.



10\. ChannelMember



برای Channel:



ChannelMember



با:



channel

user

role

joined\_at

left\_at

is\_active



Roles:



OWNER

ADMIN

MODERATOR

MEMBER

11\. Message



Message یکی از مهم‌ترین Aggregateهای Communication است.



Fields اصلی:



id

tenant

conversation

sender

message\_type

body

reply\_to

thread\_root

created\_at

updated\_at

edited\_at

deleted\_at

is\_edited

is\_deleted



Message Types:



TEXT

SYSTEM

FILE

IMAGE

VIDEO

AUDIO

VOICE

LOCATION

LINK

CALL\_EVENT

MEETING\_EVENT

AI\_GENERATED

12\. Message Lifecycle



Lifecycle:



CREATED

&#x20;   ↓

DELIVERED

&#x20;   ↓

READ



در صورت ویرایش:



CREATED

&#x20;   ↓

EDITED



در صورت حذف:



CREATED

&#x20;   ↓

DELETED



حذف Message نباید الزاماً Hard Delete باشد.



13\. Message Edit



ویرایش Message باید Audit شود.



مثلاً:



Message

&#x20;   ↓

MessageRevision



MessageRevision:



id

message

previous\_body

new\_body

changed\_by

changed\_at



History نباید حذف شود.



14\. Message Reaction



موجودیت:



MessageReaction



Fields:



id

message

user

reaction\_type

created\_at



مثلاً:



👍

❤️

😂

😮

😢



Reactionها باید Extensible باشند.



15\. Message Attachment



موجودیت:



MessageAttachment



Fields:



id

message

file

file\_name

mime\_type

size

checksum

storage\_key

created\_at



File Storage نباید داخل Database ذخیره شود.



Database فقط Metadata را نگه دارد.



16\. Message Thread



Thread باید امکان ایجاد Conversation منطقی داخل Message را فراهم کند.



ساختار:



Message

&#x20;  │

&#x20;  ├── Reply

&#x20;  ├── Reply

&#x20;  ├── Reply

&#x20;  └── Reply



Fields:



thread\_root

reply\_to

17\. Mention



موجودیت:



MessageMention



Fields:



id

message

mentioned\_user

position\_start

position\_end

created\_at



Mention باید Notification ایجاد کند.



18\. Read Receipt



برای Message:



MessageReadReceipt



Fields:



message

user

read\_at



اما برای Performance بالا باید امکان نگهداری:



ConversationMember.last\_read\_message



نیز وجود داشته باشد.



19\. Delivery Receipt



موجودیت:



MessageDelivery



States:



SENT

DELIVERED

FAILED



این اطلاعات باید برای Real-Time Messaging قابل استفاده باشد.



20\. Presence



Presence Platform باید مستقل باشد.



States:



ONLINE

OFFLINE

AWAY

BUSY

DO\_NOT\_DISTURB

INVISIBLE



Presence باید بتواند:



user

status

last\_seen

device

updated\_at



را مدیریت کند.



21\. Multi Device Presence



یک User ممکن است چند Device داشته باشد:



User

&#x20;├── Web

&#x20;├── Mobile

&#x20;├── Desktop

&#x20;└── Agent



Presence باید Aggregate شود.



مثلاً:



Web = Online

Mobile = Offline

Desktop = Online





User = Online

22\. Typing Indicator



Typing Indicator نباید در Database ذخیره شود.



باید از:



WebSocket

Redis



استفاده کند.



Flow:



Client

&#x20;↓

WebSocket

&#x20;↓

Redis

&#x20;↓

Other Clients

23\. Real-Time Architecture



برای Real-Time:



Client

&#x20;  ↓

WebSocket

&#x20;  ↓

Django Channels

&#x20;  ↓

Application Layer

&#x20;  ↓

Domain



Redis برای:



Channel Layer

Presence

Transient State

Pub/Sub

Distributed Coordination



استفاده شود.



Redis نباید Source of Truth Business Data باشد.



24\. WebSocket Architecture



WebSocket Consumer نباید Business Logic داشته باشد.



اشتباه:



class ChatConsumer:

&#x20;   def receive(...):

&#x20;       # create message

&#x20;       # permission

&#x20;       # database

&#x20;       # notification



درست:



Consumer

&#x20;↓

Command

&#x20;↓

Application Service

&#x20;↓

Domain

&#x20;↓

Repository

&#x20;↓

Event

&#x20;↓

Notification / WebSocket

25\. Communication Events



Communication باید Event Driven باشد.



Events:



ConversationCreated

ConversationMemberAdded

ConversationMemberRemoved





MessageCreated

MessageEdited

MessageDeleted

MessageRead

MessageDelivered





ReactionAdded

ReactionRemoved





UserMentioned





ChannelCreated

ChannelMemberAdded

ChannelMemberRemoved





UserPresenceChanged





CallStarted

CallEnded





MeetingCreated

MeetingStarted

MeetingEnded





ParticipantJoined

ParticipantLeft





RecordingStarted

RecordingCompleted





TranscriptCompleted

MeetingSummaryGenerated

26\. Voice Call



Call Aggregate:



Call



Fields:



id

tenant

conversation

call\_type

status

started\_at

ended\_at

initiated\_by



Types:



VOICE

VIDEO

27\. Call Participant

CallParticipant



Fields:



call

user

joined\_at

left\_at

status



Status:



INVITED

RINGING

CONNECTED

DECLINED

MISSED

LEFT

28\. Group Call



Group Call باید بتواند چند Participant داشته باشد.



Call

&#x20;├── Participant

&#x20;├── Participant

&#x20;├── Participant

&#x20;└── Participant



تعداد Participant نباید در Domain Core Hard-Code شود.



محدودیت باید Configuration/Policy باشد.



29\. WebRTC



WebRTC مسئول:



Audio

Video

Screen Sharing

Peer Connection

Media Streams



است.



Meryx Backend مسئول Media Streaming نیست.



Backend مسئول:



Signaling

Authentication

Authorization

Room Management

Participant Management

Session Lifecycle



است.



30\. WebRTC Signaling



Flow:



Client A

&#x20;  ↓

WebSocket

&#x20;  ↓

Signaling Service

&#x20;  ↓

Client B



Messages:



OFFER

ANSWER

ICE\_CANDIDATE

JOIN

LEAVE

MUTE

UNMUTE

CAMERA\_ON

CAMERA\_OFF

SCREEN\_SHARE\_STARTED

SCREEN\_SHARE\_STOPPED

31\. Meeting



Meeting باید Aggregate مستقل داشته باشد.



Fields:



id

tenant

title

description

host

scheduled\_start

scheduled\_end

actual\_start

actual\_end

status

meeting\_type

created\_at



Types:



INSTANT

SCHEDULED

RECURRING

32\. Meeting Status

SCHEDULED

WAITING

LIVE

ENDED

CANCELLED

33\. Meeting Participant

MeetingParticipant



Fields:



meeting

user

role

invited\_at

joined\_at

left\_at

attendance\_status



Roles:



HOST

CO\_HOST

PRESENTER

PARTICIPANT

OBSERVER

34\. Meeting Room



Meeting Room باید Session را از Meeting Definition جدا کند.



Meeting

&#x20;  ↓

MeetingRoom

&#x20;  ↓

MeetingSession



این جداسازی برای:



Recurring meetings

Reconnect

Multiple sessions

Recording

Audit



ضروری است.



35\. Screen Sharing



Screen Sharing باید Session State داشته باشد.



ScreenShareSession



Fields:



meeting

user

started\_at

ended\_at



Media خود Screen Share نباید داخل Database ذخیره شود.



36\. Meeting Recording

MeetingRecording



Fields:



id

meeting

storage\_key

file\_name

mime\_type

size

duration

checksum

started\_at

ended\_at

created\_at



Recording باید:



Permission controlled

Encrypted where required

Audited

Retention-aware



باشد.



37\. Meeting Transcript

MeetingTranscript



Fields:



id

meeting

language

status

content\_reference

created\_at

completed\_at



Transcript می‌تواند توسط AI Pipeline پردازش شود.



38\. AI Meeting Summary



AI نباید مستقیماً Meeting را تغییر دهد.



Flow:



Meeting

&#x20;↓

Recording / Transcript

&#x20;↓

AI Processing

&#x20;↓

AI Output

&#x20;↓

Summary



موجودیت:



MeetingSummary



شامل:



summary

key\_points

decisions

action\_items

risks

topics

confidence

generated\_at

model\_reference

39\. AI Action Items



AI می‌تواند Task Candidate تولید کند:



Meeting

&#x20;↓

AI

&#x20;↓

ActionItemCandidate

&#x20;↓

Human Approval

&#x20;↓

Task



AI نباید بدون Policy و Permission الزاماً Task واقعی ایجاد کند.



40\. Official Communication



Meryx باید امکان Communication رسمی داشته باشد.



مثلاً:



Organization

&#x20;↓

Official Communication

&#x20;↓

Recipient



موجودیت:



OfficialMessage



می‌تواند برای:



ابلاغ

اطلاعیه

بخشنامه

Announcement



استفاده شود.



41\. Official Message Lifecycle

DRAFT

&#x20;↓

REVIEW

&#x20;↓

APPROVED

&#x20;↓

PUBLISHED

&#x20;↓

DELIVERED

&#x20;↓

ACKNOWLEDGED



هر مرحله باید Audit شود.



42\. Communication Permission



Permissionها باید Fine-Grained باشند.



مثلاً:



communication.view

communication.create

communication.edit

communication.delete





message.send

message.edit

message.delete

message.reaction





conversation.create

conversation.manage





channel.create

channel.manage

channel.invite





meeting.create

meeting.manage

meeting.record





recording.view

recording.download





transcript.view

summary.view

43\. Moderation



Communication باید Moderation Layer داشته باشد.



قابلیت‌ها:



Report Message

Report User

Block User

Mute User

Restrict User

Remove Message

Freeze Conversation

44\. Message Reporting

MessageReport



Fields:



message

reported\_by

reason

description

status

reviewed\_by

reviewed\_at

created\_at



Status:



OPEN

UNDER\_REVIEW

RESOLVED

DISMISSED

45\. Blocking

UserBlock



ساختار:



blocker

blocked\_user

reason

created\_at



Business Rule:



کاربر Block شده نباید بتواند Direct Communication جدید ایجاد کند، مگر Policy اجازه دهد.



46\. Retention



Communication باید Retention Policy داشته باشد.



مثلاً:



Messages: 7 years

Recordings: 2 years

Transient Presence: 30 days

Audit: 10 years



این مقادیر نباید Hard-Code شوند.



47\. Search



Message Search باید از Database Query ساده فراتر طراحی شود.



Architecture:



Message

&#x20;↓

Search Index



در آینده می‌توان:



SQL Server Full Text Search



یا Search Engine خارجی اضافه کرد.



Domain نباید به Search Engine وابسته شود.



48\. Notification Integration



Message Event:



MessageCreated



می‌تواند:



Notification

Push Notification

Email

Desktop Notification

Mobile Notification



ایجاد کند.



Communication نباید Notification implementation را داخل خود Domain نگه دارد.



49\. Security



Communication یکی از حساس‌ترین بخش‌های Meryx است.



الزامات:



Authentication

Authorization

Tenant Isolation

Object-Level Permission

Rate Limiting

Message Validation

Attachment Validation

Malware Scanning

Audit Logging

Encryption

Retention

Access Logging

50\. Rate Limiting



برای جلوگیری از Spam:



Messages / minute

Calls / minute

Channel creation

Conversation creation

Attachment uploads

WebSocket connections



باید قابل Configuration باشند.



51\. Database Indexing



Indexهای ضروری باید طراحی شوند.



مثلاً:



Conversation:

tenant\_id

type

created\_at





ConversationMember:

conversation\_id

user\_id

is\_active





Message:

tenant\_id

conversation\_id

created\_at

sender\_id

thread\_root\_id





MessageReadReceipt:

message\_id

user\_id





ChannelMember:

channel\_id

user\_id





Meeting:

tenant\_id

scheduled\_start

status





MeetingParticipant:

meeting\_id

user\_id



Unique Constraints نیز باید در سطح Database اعمال شوند.



52\. Database Naming



نام جدول‌ها باید استاندارد باشند:



communication\_conversations

communication\_conversation\_members

communication\_messages

communication\_message\_revisions

communication\_message\_reactions

communication\_message\_attachments

communication\_message\_mentions

communication\_message\_read\_receipts

communication\_channels

communication\_channel\_members

communication\_calls

communication\_call\_participants

communication\_meetings

communication\_meeting\_participants

communication\_meeting\_rooms

communication\_meeting\_sessions

communication\_meeting\_recordings

communication\_meeting\_transcripts

communication\_meeting\_summaries

communication\_official\_messages

communication\_message\_reports

communication\_user\_blocks

53\. Domain Packages



ساختار پیشنهادی:



apps/

└── communication/

&#x20;   ├── domain/

&#x20;   │   ├── entities/

&#x20;   │   ├── value\_objects/

&#x20;   │   ├── aggregates/

&#x20;   │   ├── events/

&#x20;   │   ├── exceptions/

&#x20;   │   ├── repositories/

&#x20;   │   └── services/

&#x20;   │

&#x20;   ├── application/

&#x20;   │   ├── commands/

&#x20;   │   ├── queries/

&#x20;   │   ├── services/

&#x20;   │   ├── dto/

&#x20;   │   └── handlers/

&#x20;   │

&#x20;   ├── infrastructure/

&#x20;   │   ├── persistence/

&#x20;   │   ├── websocket/

&#x20;   │   ├── redis/

&#x20;   │   ├── webrtc/

&#x20;   │   ├── storage/

&#x20;   │   └── search/

&#x20;   │

&#x20;   ├── presentation/

&#x20;   │   ├── api/

&#x20;   │   ├── websocket/

&#x20;   │   └── serializers/

&#x20;   │

&#x20;   ├── models/

&#x20;   ├── migrations/

&#x20;   ├── tests/

&#x20;   └── apps.py

54\. Dependency Rule



مجاز:



Presentation

&#x20;   ↓

Application

&#x20;   ↓

Domain



و:



Infrastructure

&#x20;   ↓

Domain Interfaces



غیرمجاز:



Domain → Django

Domain → Redis

Domain → Channels

Domain → WebRTC

Domain → SQL Server

Domain → AI

55\. API



APIهای اصلی:



POST   /conversations/

GET    /conversations/

GET    /conversations/{id}/

PATCH  /conversations/{id}/





POST   /conversations/{id}/members/

DELETE /conversations/{id}/members/{user\_id}





GET    /conversations/{id}/messages/

POST   /conversations/{id}/messages/





PATCH  /messages/{id}/

DELETE /messages/{id}/





POST   /messages/{id}/reactions/

DELETE /messages/{id}/reactions/{reaction}





POST   /messages/{id}/read/





GET    /channels/

POST   /channels/





GET    /meetings/

POST   /meetings/





POST   /meetings/{id}/join/

POST   /meetings/{id}/leave/





GET    /meetings/{id}/participants/

GET    /meetings/{id}/recordings/

GET    /meetings/{id}/transcript/

GET    /meetings/{id}/summary/

56\. WebSocket Endpoints



حداقل:



/ws/communication/conversations/{conversation\_id}/

/ws/communication/presence/

/ws/communication/calls/{call\_id}/

/ws/communication/meetings/{meeting\_id}/

57\. WebSocket Event Envelope



تمام Eventها باید Envelope استاندارد داشته باشند:



{

&#x20;   "event\_id": "UUID",

&#x20;   "event\_type": "message.created",

&#x20;   "timestamp": "...",

&#x20;   "tenant\_id": "UUID",

&#x20;   "actor\_id": "UUID",

&#x20;   "payload": {}

}

58\. Idempotency



Commandهای حساس باید Idempotent باشند.



مثلاً:



SendMessage

CreateMeeting

JoinMeeting

AddReaction



نباید با Retry باعث Duplicate Operation شوند.



59\. Transaction Boundary



عملیات مهم باید Transactional باشند.



مثلاً:



Create Message

&#x20;   ↓

Persist Message

&#x20;   ↓

Persist Outbox Event



هر دو باید در یک Transaction باشند.



60\. Outbox Pattern



Communication Eventها باید از Outbox Pattern استفاده کنند.



Database Transaction

&#x20;   │

&#x20;   ├── Message

&#x20;   └── OutboxEvent

&#x20;            ↓

&#x20;       Event Publisher

&#x20;            ↓

&#x20;       Redis / Kafka / etc.



هدف:



جلوگیری از Lost Event.



61\. Observability



Communication باید:



Structured Logging

Metrics

Tracing

Audit

Health Checks



داشته باشد.



Metrics:



messages\_sent\_total

messages\_failed\_total

websocket\_connections

active\_calls

active\_meetings

message\_latency

delivery\_latency

read\_latency

62\. Testing



حداقل:



Unit Tests

Message creation

Message editing

Message deletion

Reaction

Thread

Mention

Permission

Conversation lifecycle

Meeting lifecycle

Integration Tests

Database

Redis

WebSocket

Authentication

Tenant isolation

API Tests



تمام Endpointها.



WebSocket Tests

connect

authenticate

send

receive

disconnect

reconnect

Security Tests

cross-tenant access

unauthorized message access

unauthorized recording access

blocked user

permission escalation

63\. Performance Requirements



Communication باید برای Scale طراحی شود.



اهداف اولیه:



100,000+ users

10,000+ concurrent WebSocket connections

High message throughput

Horizontal scaling

Multiple application instances

Multiple WebSocket instances



این اعداد Configuration/Capacity Planning هستند و نباید بدون Benchmark به‌عنوان تضمین عملکرد تلقی شوند.



64\. Horizontal Scaling



نباید هیچ State مهمی داخل Process Memory نگه داشته شود.



بد:



connected\_users = {}



در Production.



به‌جای آن:



Redis

Database

Distributed Coordination



استفاده شود.



65\. Offline Support



Communication باید Offline-aware باشد.



Client باید بتواند:



Offline

&#x20;↓

Create message

&#x20;↓

Local queue

&#x20;↓

Reconnect

&#x20;↓

Sync



انجام دهد.



Backend باید Idempotency را پشتیبانی کند.



66\. Synchronization



Sync API باید در آینده قابل اضافه شدن باشد:



GET /communication/sync



با:



cursor

last\_event\_id

timestamp



برای دریافت تغییرات بعد از آخرین Sync.



67\. Communication Audit



تمام عملیات حساس:



Message Edited

Message Deleted

User Added

User Removed

Permission Changed

Recording Started

Recording Accessed

Recording Downloaded

Transcript Accessed

Summary Generated

Official Message Approved



باید Audit شوند.



68\. Privacy



سیستم باید قابلیت:



Data Export

Data Retention

Data Deletion

Legal Hold

Access Review



را در معماری آینده داشته باشد.



69\. Legal Hold



برای Enterprise باید امکان:



LegalHold



وجود داشته باشد.



در صورت Legal Hold:



Message

Recording

Transcript

Document



نباید طبق Retention معمول حذف شود.



70\. Communication Policy



موجودیت:



CommunicationPolicy



می‌تواند تنظیم کند:



message\_retention\_days

recording\_retention\_days

max\_attachment\_size

allowed\_file\_types

max\_message\_length

max\_group\_members

max\_meeting\_participants

allow\_external\_users

allow\_recording

allow\_screen\_sharing

allow\_message\_edit

allow\_message\_delete

71\. External Communication



معماری باید در آینده امکان External User داشته باشد.



مثلاً:



Meryx User

&#x20;     ↕

External Guest



ولی External User نباید به‌صورت پیش‌فرض به Tenant دسترسی عمومی داشته باشد.



72\. Integration با Project



مثلاً:



Project

&#x20;  ↓

Project Channel



یا:



Task

&#x20;↓

Message



اما Communication مالک Project/Task نیست.



73\. Integration با Documents



Attachment باید بتواند به Document Platform متصل شود.



مثلاً:



Message

&#x20;↓

Attachment

&#x20;↓

Document Reference



اما File Storage باید مستقل باشد.



74\. Integration با Notifications



Event:



MessageCreated



می‌تواند Notification ایجاد کند.



اما Notification Service مسئول Delivery است.



75\. Integration با AI



AI باید بتواند:



Summarize Conversation

Summarize Meeting

Detect Action Items

Extract Decisions

Generate Official Letter

Classify Communication

Search Semantic Messages

Detect Topics

Generate Recommendations



را انجام دهد.



AI Output باید قابل Audit باشد.



76\. AI Governance



AI-generated content باید مشخص باشد:



generated\_by\_ai = true

model\_id

model\_version

prompt\_version

generated\_at

confidence

human\_review\_status

77\. Human Approval



موارد حساس:



Official Communication

AI-generated Letter

AI-generated Task

AI-generated Decision



نباید بدون Policy اجازه انتشار خودکار داشته باشند.



78\. File Security



Attachment باید قبل از قابل‌استفاده شدن:



Extension Validation

MIME Validation

Size Validation

Checksum

Malware Scan

Storage Isolation

Access Control



شود.



79\. ممنوعیت‌های مهم



در این فاز:



❌ Business Logic داخل View



❌ Business Logic داخل Serializer



❌ Business Logic داخل WebSocket Consumer



❌ Redis به‌عنوان Database اصلی



❌ ذخیره فایل در Database



❌ ذخیره Media در Process Memory



❌ Hard-Code کردن Limits



❌ Hard-Code کردن Retention



❌ وابستگی Domain به Django



❌ وابستگی Domain به Redis



❌ وابستگی Domain به WebRTC



❌ AI مستقیم روی Database



80\. ترتیب پیاده‌سازی



Communication نباید یک‌باره ساخته شود.



ترتیب:



STEP 1

Reaction





STEP 8

Mention





STEP 9

Read/Delivery Receipt





STEP 10

Attachment





STEP 11

WebSocket





STEP 12

Redis





STEP 13

Presence





STEP 14

Notifications Integration





STEP 15

Voice Call





STEP 16

Video Call





STEP 17

Meeting





STEP 18

WebRTC Signaling





STEP 19

Screen Sharing





STEP 20

Recording





STEP 21

Transcript





STEP 22

AI Summary





STEP 23

Official Communication





STEP 24

Moderation





STEP 25

Retention





STEP 26

Search





STEP 27

Audit





STEP 28

Performance Optimization





STEP 29

Security Hardening





STEP 30

Production Validation

81\. Definition of Done



Phase 11 زمانی کامل است که:



\[ ] Communication Domain implemented

\[ ] Multi-Tenant isolation implemented

\[ ] Conversation implemented

\[ ] Direct Chat implemented

\[ ] Group Chat implemented

\[ ] Channels implemented

\[ ] Messages implemented

\[ ] Threads implemented

\[ ] Reactions implemented

\[ ] Mentions implemented

\[ ] Read receipts implemented

\[ ] Delivery receipts implemented

\[ ] Attachments implemented

\[ ] Presence implemented

\[ ] WebSocket implemented

\[ ] Redis integration implemented

\[ ] Voice Call implemented

\[ ] Video Call architecture implemented

\[ ] Meeting implemented

\[ ] Meeting Participants implemented

\[ ] WebRTC signaling implemented

\[ ] Screen Sharing implemented

\[ ] Recording architecture implemented

\[ ] Transcript architecture implemented

\[ ] AI Summary architecture implemented

\[ ] Official Communication implemented

\[ ] Moderation implemented

\[ ] Retention implemented

\[ ] Search architecture implemented

\[ ] Audit implemented

\[ ] Permission system implemented

\[ ] Outbox implemented

\[ ] Idempotency implemented

\[ ] API tests passed

\[ ] WebSocket tests passed

\[ ] Security tests passed

\[ ] Tenant isolation tests passed

\[ ] Performance tests passed

\[ ] Documentation completed

82\. خروجی نهایی Phase 11



در پایان Phase 11 باید Communication Platform به این شکل باشد:



&#x20;                   MERYX

&#x20;                     │

&#x20;            COMMUNICATION PLATFORM

&#x20;                     │

&#x20;       ┌─────────────┼─────────────┐

&#x20;       │             │             │

&#x20;   MESSAGING     PRESENCE       CALLING

&#x20;       │             │             │

&#x20;  ┌────┼────┐        │        ┌────┴────┐

&#x20;  │    │    │        │        │         │

&#x20;Direct Group Channel  │      Voice     Video

&#x20;  │    │    │         │        │         │

&#x20;  └────┴────┴─────────┴────────┴─────────┘

&#x20;                     │

&#x20;                  MEETINGS

&#x20;                     │

&#x20;         ┌───────────┼───────────┐

&#x20;         │           │           │

&#x20;      WebRTC     Recording    Transcript

&#x20;                                 │

&#x20;                                 ↓

&#x20;                             AI ENGINE

&#x20;                                 │

&#x20;                ┌────────────────┼───────────────┐

&#x20;                │                │               │

&#x20;             Summary         Decisions      Action Items



اصل کلیدی: Communication در Meryx فقط «چت» نیست؛ یک Enterprise Communication Infrastructure است که Messaging، Presence، Calling، Meetings، Official Communication، Audit، Security و AI را در یک معماری یکپارچه ولی ماژولار قرار می‌دهد.

