============================================================

MERYX — PHASE 14

COMMUNICATION PLATFORM

============================================================



STATUS

\------

Phase: 14

Previous Phase: 13 — AI Platform

Current Phase: Communication Platform

Next Phase: 15



PURPOSE

\-------

در این فاز باید Communication Platform مریکس به‌صورت

Enterprise-Grade طراحی و پیاده‌سازی شود.



Communication نباید یک Chat ساده باشد.



این Domain باید یک زیرساخت ارتباطی عمومی، توسعه‌پذیر،

Audit-able، Real-Time، Multi-Tenant و AI-Native برای کل

Meryx Platform باشد.



Communication باید بتواند در آینده بدون تغییر بنیادی معماری

از موارد زیر پشتیبانی کند:



\- Direct Chat

\- Group Chat

\- Channels

\- Official Communication

\- Internal Messaging

\- Voice Call

\- Group Voice Call

\- Video Meeting

\- Group Video Meeting

\- Screen Sharing

\- Presence

\- Typing Indicator

\- Read Receipts

\- Delivery Receipts

\- File Sharing

\- Message Reactions

\- Message Editing

\- Message Deletion

\- Message Reply

\- Message Forwarding

\- Message Threading

\- Message Search

\- Meeting Recording

\- Meeting Transcription

\- AI Meeting Summary

\- AI Action Item Extraction

\- AI Task Extraction

\- AI Meeting Insights

\- Notifications

\- Communication Audit

\- Retention Policies

\- Communication Policies



============================================================

1\. ARCHITECTURAL POSITION

============================================================



Communication یک Bounded Context مستقل است.



نباید منطق Communication در Domainهای دیگر پخش شود.



Domainهای دیگر فقط باید از طریق:



\- Application Services

\- Domain Events

\- Integration Events

\- Public APIs



با Communication ارتباط داشته باشند.



Communication نباید مستقیماً به Modelهای داخلی Domainهای دیگر

وابسته شود.



نمونه:



Projects نباید مستقیماً Message را مدیریت کند.



Projects باید Event یا Application Command ایجاد کند.



Communication مسئول مدیریت ارتباط است.



============================================================

2\. CORE ARCHITECTURAL PRINCIPLES

============================================================



Communication باید از اصول زیر پیروی کند:



\- DDD

\- Clean Architecture

\- SOLID

\- Modular Monolith

\- Event Driven Architecture

\- API First

\- Security First

\- Multi-Tenant

\- Audit First

\- Real-Time First

\- AI Native

\- Cloud Ready

\- Offline Ready

\- Extensible

\- Configuration over Customization



Communication باید از ابتدا به شکلی طراحی شود که در آینده بتواند

در صورت نیاز به Service مستقل تبدیل شود.



در Phase 14 نباید Microservice اجباری ایجاد شود.



معماری فعلی:



Modular Monolith



اما Boundaryهای Domain باید کاملاً مشخص باشند.



============================================================

3\. TECHNOLOGY

============================================================



Backend:



Python 3.12

Django 6

Django REST Framework

SQL Server

mssql-django

SimpleJWT



Real-Time:



Django Channels

ASGI

Redis



Real-Time transport باید WebSocket باشد.



Voice/Video:



WebRTC



WebRTC مسئول Media Transport است.



Django مسئول:



\- Signaling

\- Authorization

\- Session Management

\- Meeting Management

\- Participant Management

\- Security

\- Audit



باشد.



Redis مسئول:



\- Presence

\- WebSocket Channel Layer

\- Ephemeral State

\- Typing State

\- Distributed Coordination



باشد.



Database مسئول:



\- Persistent Communication Data

\- Messages

\- Conversations

\- Meetings

\- Participants

\- Policies

\- Audit References

\- Metadata



باشد.



============================================================

4\. COMMUNICATION DOMAIN MAP

============================================================



Communication باید حداقل شامل Subdomainهای زیر باشد:



1\. Conversation Management

2\. Messaging

3\. Channel Management

4\. Membership

5\. Presence

6\. Message Interaction

7\. File Attachment

8\. Notification Integration

9\. Voice Communication

10\. Video Communication

11\. Meeting Management

12\. Screen Sharing

13\. Recording

14\. Transcription

15\. AI Communication Intelligence

16\. Search

17\. Retention

18\. Moderation

19\. Audit

20\. Integration



============================================================

5\. CONVERSATION MODEL

============================================================



Conversation مفهوم اصلی Messaging است.



Conversation می‌تواند یکی از انواع زیر باشد:



DIRECT

GROUP

CHANNEL

MEETING



نوع Conversation باید Extensible باشد.



نباید برای هر نوع Conversation یک سیستم Messaging جدا ساخته شود.



همه Messageها باید متعلق به Conversation باشند.



ساختار مفهومی:



Conversation

&#x20;   |

&#x20;   +-- Members

&#x20;   |

&#x20;   +-- Messages

&#x20;   |

&#x20;   +-- Attachments

&#x20;   |

&#x20;   +-- Reactions

&#x20;   |

&#x20;   +-- Read States

&#x20;   |

&#x20;   +-- Events

&#x20;   |

&#x20;   +-- Permissions

&#x20;   |

&#x20;   +-- Retention Policy



============================================================

6\. CONVERSATION ENTITY

============================================================



Conversation باید حداقل اطلاعات زیر را داشته باشد:



\- id

\- tenant

\- type

\- name

\- description

\- avatar

\- created\_by

\- created\_at

\- updated\_at

\- archived\_at

\- deleted\_at

\- is\_active



برای DIRECT Conversation:



name ممکن است از Members مشتق شود.



برای GROUP:



name قابل تنظیم است.



برای CHANNEL:



name و slug باید وجود داشته باشند.



============================================================

7\. CONVERSATION MEMBERSHIP

============================================================



Member باید Entity مستقل باشد.



ConversationMember:



\- id

\- conversation

\- user

\- role

\- joined\_at

\- left\_at

\- is\_active

\- muted\_until

\- last\_read\_message

\- notification\_level



Roleهای اولیه:



OWNER

ADMIN

MODERATOR

MEMBER

GUEST



Role system باید Extensible باشد.



============================================================

8\. MESSAGE DOMAIN

============================================================



Message Entity اصلی Messaging است.



Message باید حداقل شامل:



\- id

\- conversation

\- sender

\- message\_type

\- content

\- reply\_to

\- thread\_root

\- created\_at

\- edited\_at

\- deleted\_at

\- is\_edited

\- is\_deleted



باشد.



Message Type:



TEXT

SYSTEM

FILE

IMAGE

AUDIO

VIDEO

LOCATION

MEETING

CALL

AI\_GENERATED



سیستم Message Type باید قابل توسعه باشد.



============================================================

9\. MESSAGE LIFECYCLE

============================================================



Message Lifecycle:



CREATED

|

v

SENT

|

v

DELIVERED

|

v

READ



و در صورت نیاز:



EDITED

DELETED



Message نباید Hard Delete شود مگر تحت Policy خاص.



در حالت عادی:



Soft Delete



استفاده شود.



============================================================

10\. MESSAGE DELIVERY

============================================================



سیستم باید Delivery State را برای هر Recipient مدیریت کند.



MessageDelivery:



\- message

\- recipient

\- status

\- delivered\_at

\- read\_at



Status:



SENT

DELIVERED

READ

FAILED



برای Conversationهای بزرگ نباید طراحی به شکلی باشد که

تعداد رکوردهای Delivery به شکل کنترل‌نشده رشد کند.



برای Channelهای بزرگ باید Read State بهینه باشد.



============================================================

11\. MESSAGE EDITING

============================================================



کاربر می‌تواند Message را Edit کند، اما:



Original Message نباید از بین برود.



Message Revision باید وجود داشته باشد.



MessageRevision:



\- id

\- message

\- previous\_content

\- new\_content

\- edited\_by

\- edited\_at



تمام Editها باید Audit شوند.



============================================================

12\. MESSAGE DELETION

============================================================



Deletion باید Policy Driven باشد.



مثلاً:



USER\_DELETE\_OWN

ADMIN\_DELETE

MODERATOR\_DELETE

RETENTION\_DELETE

LEGAL\_DELETE



Message حذف‌شده باید در صورت مجاز بودن Policy به شکل:



"This message was deleted."



نمایش داده شود.



اما Audit Record باید باقی بماند.



============================================================

13\. MESSAGE REPLY

============================================================



Message می‌تواند Reply داشته باشد.



ساختار:



Message

&#x20;  |

&#x20;  +-- reply\_to

&#x20;  |

&#x20;  +-- thread\_root



این امکان باید Threading را نیز پشتیبانی کند.



============================================================

14\. MESSAGE THREADING

============================================================



Thread باید برای:



\- Discussion

\- Project Discussion

\- Meeting Discussion

\- Channel Discussion



قابل استفاده باشد.



Thread باید بتواند:



\- Root Message

\- Replies

\- Participants

\- Last Activity

\- Unread Count



را مدیریت کند.



============================================================

15\. MESSAGE REACTION

============================================================



Reaction باید Entity مستقل باشد.



MessageReaction:



\- message

\- user

\- reaction\_type

\- created\_at



کاربر نباید بتواند یک Reaction یکسان را چندبار روی

یک Message ثبت کند.



Unique Constraint:



(message, user, reaction\_type)



============================================================

16\. MESSAGE FORWARDING

============================================================



Forward کردن Message نباید Original Message را Duplicate کند

مگر برای Snapshot مورد نیاز.



Forwarded Message باید Reference به Original Message داشته باشد.



اطلاعات:



\- original\_message

\- forwarded\_by

\- forwarded\_at



در صورت نیاز Snapshot برای حفظ تاریخی محتوا ذخیره شود.



============================================================

17\. FILE ATTACHMENTS

============================================================



File باید از Message جدا باشد.



MessageAttachment:



\- id

\- message

\- file

\- file\_name

\- mime\_type

\- size

\- checksum

\- storage\_key

\- created\_at



فایل نباید مستقیماً در Database ذخیره شود مگر برای Use Case خاص.



Storage abstraction باید وجود داشته باشد.



امکان استفاده از:



\- Local Storage

\- S3

\- Azure Blob

\- Other Object Storage



باید وجود داشته باشد.



============================================================

18\. CHANNELS

============================================================



Channel یک Conversation تخصصی است.



Channel باید قابلیت:



\- Public

\- Private

\- Restricted



داشته باشد.



Channel:



\- name

\- slug

\- description

\- visibility

\- owner

\- created\_at

\- archived\_at



Channel باید Permission مستقل داشته باشد.



============================================================

19\. PRESENCE

============================================================



Presence باید Real-Time باشد.



Presence State:



ONLINE

AWAY

BUSY

DO\_NOT\_DISTURB

OFFLINE

INVISIBLE



Presence نباید به‌صورت دائمی برای هر Heartbeat در Database

ذخیره شود.



Redis برای State لحظه‌ای استفاده شود.



Database فقط برای:



\- Last Seen

\- User Preference

\- Status History در صورت نیاز



استفاده شود.



============================================================

20\. TYPING INDICATOR

============================================================



Typing Indicator باید Ephemeral باشد.



نباید هر Typing Event در SQL Server ذخیره شود.



Flow:



Client

&#x20;   |

&#x20;   v

WebSocket

&#x20;   |

&#x20;   v

Channels

&#x20;   |

&#x20;   v

Redis

&#x20;   |

&#x20;   v

Recipients



Typing Event:



USER\_STARTED\_TYPING

USER\_STOPPED\_TYPING



============================================================

21\. REAL-TIME ARCHITECTURE

============================================================



Real-Time Flow:



Client

&#x20;  |

&#x20;  | WebSocket

&#x20;  v

Django Channels

&#x20;  |

&#x20;  v

Authentication

&#x20;  |

&#x20;  v

Authorization

&#x20;  |

&#x20;  v

Application Service

&#x20;  |

&#x20;  v

Domain Event

&#x20;  |

&#x20;  v

Redis Channel Layer

&#x20;  |

&#x20;  v

Connected Clients



WebSocket Consumer نباید Business Logic داشته باشد.



Consumer فقط:



\- Receive

\- Validate Transport Input

\- Authenticate

\- Dispatch Command

\- Return Event



را انجام دهد.



Business Logic باید در Application Layer باشد.



============================================================

22\. WEBSOCKET SECURITY

============================================================



WebSocket باید:



\- Authenticate

\- Authorize

\- Validate Tenant

\- Validate Conversation Membership

\- Rate Limit

\- Validate Payload



را انجام دهد.



کاربر نباید بتواند فقط با داشتن Conversation ID

به Conversation متصل شود.



============================================================

23\. VOICE CALL

============================================================



Voice Call باید از Conversation جدا ولی قابل اتصال باشد.



Call Session:



\- id

\- tenant

\- conversation

\- initiated\_by

\- type

\- status

\- started\_at

\- ended\_at



Call Type:



DIRECT\_AUDIO

GROUP\_AUDIO



Call Status:



RINGING

CONNECTING

ACTIVE

ENDED

FAILED

CANCELLED



============================================================

24\. VIDEO CALL

============================================================



Video Call نیز باید Session مستقل داشته باشد.



Call Type:



DIRECT\_VIDEO

GROUP\_VIDEO



Media باید از WebRTC عبور کند.



Server نباید Media Stream را Proxy کند مگر معماری آینده

صراحتاً چنین نیازی داشته باشد.



============================================================

25\. WEBRTC SIGNALING

============================================================



Meryx Server مسئول Signaling است.



Signaling Messages:



OFFER

ANSWER

ICE\_CANDIDATE

HANGUP

RENEGOTIATE



Flow:



Caller

&#x20;|

&#x20;| OFFER

&#x20;v

Meryx

&#x20;|

&#x20;v

Callee



Callee

&#x20;|

&#x20;| ANSWER

&#x20;v

Meryx

&#x20;|

&#x20;v

Caller



ICE Candidateها نیز از همین Signaling Channel عبور می‌کنند.



============================================================

26\. MEETING DOMAIN

============================================================



Meeting باید Entity مستقل باشد.



Meeting:



\- id

\- tenant

\- title

\- description

\- organizer

\- scheduled\_start

\- scheduled\_end

\- actual\_start

\- actual\_end

\- status

\- meeting\_type

\- recording\_policy

\- transcription\_policy



Status:



SCHEDULED

STARTING

LIVE

ENDED

CANCELLED



============================================================

27\. MEETING PARTICIPANTS

============================================================



MeetingParticipant:



\- meeting

\- user

\- role

\- joined\_at

\- left\_at

\- status

\- permissions



Role:



HOST

CO\_HOST

PRESENTER

PARTICIPANT

GUEST



============================================================

28\. MEETING PERMISSIONS

============================================================



Meeting باید Permission داشته باشد برای:



\- Speak

\- Video

\- Screen Share

\- Chat

\- Record

\- Invite

\- Remove Participant

\- Mute Participant



Permissionها نباید Hard-Coded باشند.



============================================================

29\. SCREEN SHARING

============================================================



Screen Sharing از WebRTC انجام می‌شود.



Server فقط:



\- Permission

\- Session State

\- Signaling

\- Audit



را مدیریت می‌کند.



Media Server نباید در Core Architecture اجباری باشد.



============================================================

30\. MEETING RECORDING

============================================================



Recording باید Policy Driven باشد.



MeetingRecording:



\- meeting

\- started\_at

\- ended\_at

\- storage\_key

\- duration

\- file\_size

\- checksum

\- status



Recording Status:



STARTING

RECORDING

PROCESSING

AVAILABLE

FAILED

DELETED



Recording باید Audit شود.



============================================================

31\. TRANSCRIPTION

============================================================



Meeting Recording یا Live Audio می‌تواند وارد

Transcription Pipeline شود.



Flow:



Audio

&#x20;|

&#x20;v

Transcription Service

&#x20;|

&#x20;v

Transcript

&#x20;|

&#x20;v

AI Analysis

&#x20;|

&#x20;+--> Summary

&#x20;|

&#x20;+--> Action Items

&#x20;|

&#x20;+--> Decisions

&#x20;|

&#x20;+--> Tasks

&#x20;|

&#x20;+--> Insights



============================================================

32\. AI MEETING SUMMARY

============================================================



AI باید بتواند:



\- Summary

\- Decisions

\- Action Items

\- Risks

\- Questions

\- Tasks

\- Participants

\- Topics



را استخراج کند.



AI Output نباید مستقیماً به‌عنوان Fact پذیرفته شود.



AI-generated content باید:



\- source

\- model

\- confidence

\- generated\_at

\- version



داشته باشد.



============================================================

33\. AI TASK EXTRACTION

============================================================



AI می‌تواند از Conversation یا Meeting:



Task پیشنهاد کند.



اما:



AI نباید بدون Policy و Authorization

Task واقعی ایجاد کند.



بهتر است:



AI Suggestion

&#x20;   |

&#x20;   v

Human Approval

&#x20;   |

&#x20;   v

Task Creation



باشد.



============================================================

34\. AI COMMUNICATION SEARCH

============================================================



AI باید بتواند در آینده روی Communication داده‌ها:



\- Semantic Search

\- Summarization

\- Topic Extraction

\- Sentiment Analysis

\- Entity Extraction

\- Knowledge Graph Extraction



انجام دهد.



اما Security Boundary باید قبل از AI Retrieval اعمال شود.



AI نباید اطلاعاتی را ببیند که User اجازه دیدن آن را ندارد.



============================================================

35\. SEARCH

============================================================



Search باید روی:



\- Messages

\- Conversations

\- Channels

\- Attachments

\- Meetings

\- Transcripts



قابل انجام باشد.



Search باید Tenant-Aware و Permission-Aware باشد.



Search Query نباید بتواند داده‌های Tenant دیگر را برگرداند.



============================================================

36\. COMMUNICATION AUDIT

============================================================



حداقل Eventهای Audit:



MESSAGE\_CREATED

MESSAGE\_EDITED

MESSAGE\_DELETED

MESSAGE\_READ

MESSAGE\_FORWARDED

REACTION\_ADDED

REACTION\_REMOVED

MEMBER\_ADDED

MEMBER\_REMOVED

MEMBER\_ROLE\_CHANGED

CHANNEL\_CREATED

CHANNEL\_ARCHIVED

CALL\_STARTED

CALL\_ENDED

MEETING\_CREATED

MEETING\_STARTED

MEETING\_ENDED

PARTICIPANT\_JOINED

PARTICIPANT\_LEFT

RECORDING\_STARTED

RECORDING\_COMPLETED

RECORDING\_DELETED



Audit باید Immutable باشد.



============================================================

37\. RETENTION

============================================================



Communication باید Retention Policy داشته باشد.



Retention می‌تواند برای:



\- Tenant

\- Organization

\- Conversation

\- Channel

\- Meeting



تعریف شود.



نمونه:



30 Days

90 Days

1 Year

7 Years

Indefinite



Retention نباید با Hard-Coded Logic پیاده شود.



============================================================

38\. MODERATION

============================================================



Communication باید قابلیت Moderation داشته باشد.



نمونه:



\- Message Report

\- User Report

\- Content Flag

\- Spam Detection

\- Abuse Detection

\- AI Moderation



Moderation باید Domain مستقل داشته باشد.



============================================================

39\. NOTIFICATION INTEGRATION

============================================================



Communication نباید Notification System خودش را بسازد.



Notification Domain مسئول:



\- Push

\- Email

\- In-App

\- Mobile Notification



است.



Communication فقط Event ایجاد می‌کند.



مثال:



MESSAGE\_CREATED



Notification Platform تصمیم می‌گیرد:



آیا Notification ارسال شود یا نه.



============================================================

40\. OFFICIAL COMMUNICATION

============================================================



Official Letter باید با Messaging معمولی یکی نباشد.



Official Communication باید قابلیت:



\- Document Number

\- Sender

\- Recipient

\- CC

\- Subject

\- Body

\- Attachments

\- Status

\- Approval

\- Signature

\- Delivery Tracking

\- Read Tracking

\- Audit



داشته باشد.



Official Letter باید Domain/Module مستقل داشته باشد اما

می‌تواند از Communication Infrastructure استفاده کند.



============================================================

41\. OFFLINE SUPPORT

============================================================



Client باید بتواند در Offline Mode:



\- Draft Message

\- Queue Message

\- Queue Attachment Metadata

\- Cache Conversations



را مدیریت کند.



Sync Engine باید Conflict Resolution داشته باشد.



Message ID باید Client Generated UUID را نیز پشتیبانی کند

تا Duplicate ایجاد نشود.



============================================================

42\. IDEMPOTENCY

============================================================



تمام Commandهای مهم باید Idempotent باشند.



مثال:



SendMessageCommand



باید بتواند Client Request ID داشته باشد.



اگر Client یک Message را دوبار ارسال کرد:



دو Message ایجاد نشود.



============================================================

43\. RATE LIMITING

============================================================



Rate Limit برای:



\- Send Message

\- Create Conversation

\- Create Channel

\- Start Call

\- Start Meeting

\- Upload Attachment

\- Search



وجود داشته باشد.



Rate Limit باید Configurable باشد.



============================================================

44\. MULTI-TENANCY

============================================================



تمام Communication Entities باید Tenant Boundary داشته باشند

یا از یک Entity Tenant-Bound قابل اطمینان استفاده کنند.



هیچ Query نباید بدون Tenant Context اجرا شود.



اصل مهم:



Tenant Isolation First.



============================================================

45\. DATABASE INDEXING

============================================================



حداقل Indexها:



Conversation:



tenant

type

created\_at



ConversationMember:



conversation

user

is\_active



Message:



conversation

created\_at

sender

message\_type



MessageDelivery:



message

recipient

status



Meeting:



tenant

scheduled\_start

status



MeetingParticipant:



meeting

user



Channel:



tenant

slug



Indexها باید بر اساس Query Pattern واقعی تکمیل شوند.



از Index اضافه جلوگیری شود.



============================================================

46\. CONSTRAINTS

============================================================



Database Constraint باید برای Invariants مهم استفاده شود.



نمونه:



Unique:



ConversationMember(conversation, user)



MessageReaction(message, user, reaction\_type)



Channel(tenant, slug)



و سایر Constraints مورد نیاز.



Business Rules مهم نباید فقط در Serializer قرار گیرند.



============================================================

47\. DOMAIN EVENTS

============================================================



Communication باید Eventهای Domain داشته باشد.



مثال:



ConversationCreated

MemberAdded

MessageCreated

MessageEdited

MessageDeleted

MessageRead

CallStarted

CallEnded

MeetingStarted

MeetingEnded

ParticipantJoined

ParticipantLeft

RecordingCompleted



Event باید:



\- event\_id

\- event\_type

\- aggregate\_id

\- tenant\_id

\- occurred\_at

\- actor\_id

\- payload

\- schema\_version



داشته باشد.



============================================================

48\. API ARCHITECTURE

============================================================



REST API برای عملیات Persistent.



WebSocket برای Real-Time.



REST Examples:



POST /conversations/

GET /conversations/

GET /conversations/{id}/

POST /conversations/{id}/members/

DELETE /conversations/{id}/members/{user\_id}/



POST /conversations/{id}/messages/

GET /conversations/{id}/messages/



PATCH /messages/{id}/

DELETE /messages/{id}/



POST /messages/{id}/reactions/

DELETE /messages/{id}/reactions/{reaction}/



POST /meetings/

GET /meetings/

POST /meetings/{id}/join/

POST /meetings/{id}/leave/



API Versioning باید وجود داشته باشد.



مثال:



/api/v1/



============================================================

49\. WEBSOCKET API

============================================================



نمونه:



/ws/conversations/{conversation\_id}/

/ws/meetings/{meeting\_id}/

/ws/presence/



WebSocket Event Envelope:



{

&#x20;   "event\_id": "...",

&#x20;   "event\_type": "...",

&#x20;   "timestamp": "...",

&#x20;   "payload": {}

}



Envelope باید Versioned باشد.



============================================================

50\. APPLICATION LAYER

============================================================



نمونه Use Cases:



CreateConversation

AddMember

RemoveMember

SendMessage

EditMessage

DeleteMessage

ReplyToMessage

ForwardMessage

AddReaction

RemoveReaction

MarkMessageRead

CreateChannel

CreateMeeting

StartMeeting

JoinMeeting

LeaveMeeting

StartCall

EndCall

StartRecording

StopRecording



Application Service مسئول Orchestration است.



============================================================

51\. DOMAIN LAYER

============================================================



Domain باید Business Rules را نگهداری کند.



نمونه:



Conversation.can\_add\_member()

Conversation.can\_remove\_member()

Conversation.can\_send\_message()

Message.can\_edit()

Message.can\_delete()

Meeting.can\_join()

Meeting.can\_start()

Meeting.can\_record()



این قوانین نباید فقط در View یا Serializer باشند.



============================================================

52\. INFRASTRUCTURE LAYER

============================================================



Infrastructure مسئول:



\- Django ORM

\- Redis

\- Channels

\- WebRTC Signaling

\- File Storage

\- Search Backend

\- AI Provider

\- External Services



است.



Domain نباید مستقیماً به Redis یا Django وابسته باشد.



============================================================

53\. REPOSITORY

============================================================



Repository Interface باید در Domain/Application Layer

تعریف شود.



Implementation در Infrastructure باشد.



مثال:



IConversationRepository

IMessageRepository

IMeetingRepository



Django ORM implementation:



DjangoConversationRepository

DjangoMessageRepository

DjangoMeetingRepository



============================================================

54\. CACHING

============================================================



Redis Cache برای:



\- Presence

\- Active Sessions

\- Typing Indicators

\- Frequently Accessed Conversations

\- Permission Cache



قابل استفاده است.



اما Cache نباید Source of Truth باشد.



SQL Server Source of Truth برای Persistent Data است.



============================================================

55\. OBSERVABILITY

============================================================



Communication باید Metrics داشته باشد:



\- Messages per second

\- Active WebSocket Connections

\- Active Meetings

\- Calls

\- Failed Calls

\- WebSocket Errors

\- Message Delivery Latency

\- Message Processing Latency

\- Redis Latency

\- Search Latency



Logs باید Structured باشند.



============================================================

56\. SECURITY

============================================================



Communication یکی از حساس‌ترین Domainهای Meryx است.



باید موارد زیر رعایت شوند:



\- Tenant Isolation

\- RBAC

\- Permission Checks

\- Object-Level Authorization

\- Rate Limiting

\- Input Validation

\- File Validation

\- Malware Scanning

\- Secure WebSocket Authentication

\- Secure Media Signaling

\- Encryption in Transit

\- Encryption at Rest

\- Audit Logging

\- Data Retention

\- Privacy Policies



============================================================

57\. FILE SECURITY

============================================================



قبل از ذخیره Attachment:



\- MIME Validation

\- Extension Validation

\- Size Validation

\- Checksum

\- Malware Scan



انجام شود.



User نباید بتواند Path دلخواه برای Storage تعیین کند.



Storage Key باید توسط Server تولید شود.



============================================================

58\. DATA PRIVACY

============================================================



Communication Data ممکن است شامل اطلاعات حساس باشد.



بنابراین باید:



\- Access Control

\- Retention

\- Deletion Policy

\- Export Policy

\- Audit

\- Data Classification



وجود داشته باشد.



============================================================

59\. TESTING

============================================================



حداقل تست‌ها:



Unit Tests

Integration Tests

API Tests

Permission Tests

Tenant Isolation Tests

WebSocket Tests

Concurrency Tests

Idempotency Tests

Security Tests

Meeting Tests

WebRTC Signaling Tests

File Upload Tests

Retention Tests

Audit Tests



Critical Business Rules باید Unit Test شوند.



============================================================

60\. PERFORMANCE

============================================================



Message List باید Pagination داشته باشد.



از Offset Pagination برای Datasetهای بسیار بزرگ

اجتناب شود.



Cursor Pagination برای Message Stream ترجیح داده شود.



مثال:



GET /messages/?cursor=...



Queryها باید:



\- select\_related

\- prefetch\_related



را در صورت نیاز استفاده کنند.



N+1 Query نباید وجود داشته باشد.



============================================================

61\. SCALABILITY

============================================================



Architecture باید قابلیت Scale کردن:



WebSocket Nodes

API Nodes

Redis

Database

Object Storage

Search

AI Processing



را داشته باشد.



WebSocket State نباید فقط در Memory یک Process نگهداری شود.



Redis Channel Layer باید Shared State مورد نیاز را فراهم کند.



============================================================

62\. DOMAIN BOUNDARY

============================================================



Communication می‌تواند با Domainهای زیر Integration داشته باشد:



Identity

Organization

HR

Projects

Tasks

Documents

Workflow

Notifications

AI

Analytics



اما نباید مالک Entityهای آنها باشد.



مثال:



Communication -> Tasks



فقط از طریق:



TaskCreated

TaskCompleted

TaskAssigned



یا Application API.



============================================================

63\. AI BOUNDARY

============================================================



Communication مالک AI Model نیست.



AI Platform مسئول:



\- Model

\- Prompt

\- Inference

\- Evaluation

\- Provider

\- AI Governance



است.



Communication فقط Use Case ارائه می‌کند:



MeetingSummarizationRequest

TranscriptAnalysisRequest

MessageSemanticSearchRequest



============================================================

64\. IMPLEMENTATION ORDER

============================================================



Implementation باید به ترتیب انجام شود:



STEP 1

Communication Domain Foundation



STEP 2

Conversation



STEP 3

Membership



STEP 4

Message



STEP 5

Message Revision



STEP 6

Reaction



STEP 7

Attachment



STEP 8

Channels



STEP 9

Read State



STEP 10

Real-Time WebSocket



STEP 11

Presence



STEP 12

Typing Indicator



STEP 13

Voice Call



STEP 14

Video Call



STEP 15

Meeting



STEP 16

Meeting Participant



STEP 17

WebRTC Signaling



STEP 18

Screen Sharing



STEP 19

Recording



STEP 20

Transcription



STEP 21

AI Meeting Intelligence



STEP 22

Search



STEP 23

Retention



STEP 24

Moderation



STEP 25

Audit Integration



STEP 26

Notification Integration



STEP 27

Offline Sync



STEP 28

Performance Optimization



STEP 29

Security Hardening



STEP 30

Full Testing



============================================================

65\. DEFINITION OF DONE

============================================================



Phase 14 زمانی کامل است که:



\[ ] Conversation کامل باشد

\[ ] Direct Chat کار کند

\[ ] Group Chat کار کند

\[ ] Channels کار کنند

\[ ] Membership کامل باشد

\[ ] Messaging کامل باشد

\[ ] Reply کار کند

\[ ] Threading کار کند

\[ ] Editing کار کند

\[ ] Soft Delete کار کند

\[ ] Reactions کار کنند

\[ ] Attachments کار کنند

\[ ] Read State کار کند

\[ ] Delivery State کار کند

\[ ] WebSocket فعال باشد

\[ ] Presence فعال باشد

\[ ] Typing Indicator فعال باشد

\[ ] Voice Call architecture کامل باشد

\[ ] Video Call architecture کامل باشد

\[ ] WebRTC Signaling کامل باشد

\[ ] Meeting کامل باشد

\[ ] Participants کامل باشند

\[ ] Screen Sharing architecture کامل باشد

\[ ] Recording architecture کامل باشد

\[ ] Transcription architecture کامل باشد

\[ ] AI Summary architecture کامل باشد

\[ ] AI Task Extraction architecture کامل باشد

\[ ] Search architecture کامل باشد

\[ ] Retention کامل باشد

\[ ] Audit کامل باشد

\[ ] Notification Integration کامل باشد

\[ ] Tenant Isolation تست شده باشد

\[ ] Permission Tests سبز باشند

\[ ] WebSocket Tests سبز باشند

\[ ] API Tests سبز باشند

\[ ] Security Tests سبز باشند

\[ ] Performance Tests قابل قبول باشند

\[ ] هیچ N+1 Query وجود نداشته باشد

\[ ] تمام Critical Business Rules تست شده باشند

\[ ] Documentation کامل باشد



============================================================

66\. ممنوعیت‌ها

============================================================



هرگز:



\- WebSocket Consumer را محل Business Logic نکن.

\- Redis را Source of Truth نکن.

\- Media را بدون نیاز از Server عبور نده.

\- Permission را فقط در Frontend پیاده نکن.

\- Tenant Filtering را به Client اعتماد نکن.

\- Message را Hard Delete نکن مگر Policy مشخص وجود داشته باشد.

\- AI را بدون Authorization به Communication Data متصل نکن.

\- Attachment را بدون Security Validation ذخیره نکن.

\- Notification Logic را داخل Message Model قرار نده.

\- Business Rule را فقط در Serializer قرار نده.

\- Domain را به Django ORM وابسته نکن.

\- Domain را به Redis وابسته نکن.

\- از Global State برای Communication استفاده نکن.

\- برای هر Conversation یک WebSocket Process اختصاصی ایجاد نکن.

\- برای هر Typing Event رکورد SQL ایجاد نکن.

\- برای هر Presence Heartbeat رکورد SQL ایجاد نکن.

\- Microservice را فقط برای "Enterprise بودن" اضافه نکن.



============================================================

67\. FINAL ARCHITECTURAL RESULT

============================================================



در پایان Phase 14، Meryx باید دارای یک Communication Platform

Enterprise باشد که:



&#x20;                   ┌───────────────────────┐

&#x20;                   │       MERYX           │

&#x20;                   │  Communication Core   │

&#x20;                   └───────────┬───────────┘

&#x20;                               │

&#x20;            ┌──────────────────┼──────────────────┐

&#x20;            │                  │                  │

&#x20;            v                  v                  v

&#x20;      Messaging           Channels           Meetings

&#x20;            │                  │                  │

&#x20;            v                  v                  v

&#x20;      Conversations        Members          Participants

&#x20;            │                                     │

&#x20;            v                                     v

&#x20;      Attachments                            WebRTC

&#x20;            │                                     │

&#x20;            v                                     v

&#x20;         Search                             Voice/Video

&#x20;            │

&#x20;            v

&#x20;      AI Intelligence

&#x20;            │

&#x20;      ┌─────┼─────┬───────────┐

&#x20;      v     v     v           v

&#x20;   Summary Tasks Insights Knowledge



و تمام این زیرسیستم باید تحت:



Tenant Isolation

Security

Authorization

Audit

Retention

Observability

Scalability



کار کند.



============================================================

END OF PHASE 14

============================================================

