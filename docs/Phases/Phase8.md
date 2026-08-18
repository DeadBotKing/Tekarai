============================================================

MERYX ENTERPRISE PLATFORM

PHASE 8 — COMMUNICATION PLATFORM

============================================================



STATUS

\------------------------------------------------------------

This phase defines the complete communication architecture

inside Meryx.



The implementation must NOT be reduced to a simple chat app.



Communication is a first-class Enterprise capability and must

support:



\- Direct Chat

\- Group Chat

\- Channels

\- Presence

\- Voice Calls

\- Group Voice Calls

\- Video Meetings

\- Screen Sharing

\- Meeting Recording

\- Official Letters

\- Notifications integration

\- File sharing

\- Message search

\- Message reactions

\- Message editing

\- Message deletion

\- Message threading

\- Read / delivery states

\- Meeting participants

\- Meeting lifecycle

\- AI Meeting Summary

\- AI-generated action items

\- Auditability

\- Multi-tenancy

\- Permission control

\- Extensibility





============================================================

1\. ARCHITECTURAL PRINCIPLES

============================================================



Communication must follow:



\- DDD

\- Clean Architecture

\- SOLID

\- Event Driven Architecture

\- API First

\- Security First

\- Multi-Tenant Architecture

\- Audit First

\- Extensible Architecture

\- Cloud Ready

\- Offline Ready



Communication must NOT contain business logic inside:



\- Django Views

\- Django Serializers

\- WebSocket Consumers

\- URL handlers



Business logic belongs inside Application / Domain services.



Django is an infrastructure/framework concern.



WebRTC is a media transport technology.



Redis is infrastructure.



Django Channels is the real-time transport layer.



None of these technologies may become the domain model.





============================================================

2\. COMMUNICATION DOMAIN

============================================================



Create a dedicated Communication bounded context.



Conceptual structure:



communication/

&#x20;   domain/

&#x20;   application/

&#x20;   infrastructure/

&#x20;   interfaces/





The domain must remain independent from:



\- Django Channels

\- Redis

\- WebRTC

\- SQL Server

\- REST framework

\- external AI providers





============================================================

3\. CORE DOMAIN CONCEPTS

============================================================



The communication domain must contain the following concepts.





3.1 Conversation



Represents a communication container.



Types:



DIRECT

GROUP

CHANNEL

MEETING



Properties:



\- id

\- tenant

\- type

\- name

\- description

\- created\_at

\- created\_by

\- updated\_at

\- archived\_at

\- is\_active





3.2 ConversationParticipant



Represents membership in a conversation.



Properties:



\- id

\- conversation

\- user

\- role

\- joined\_at

\- left\_at

\- is\_muted

\- notification\_level

\- last\_read\_message

\- is\_active





Roles:



\- OWNER

\- ADMIN

\- MODERATOR

\- MEMBER

\- GUEST





3.3 Message



Represents a communication message.



Properties:



\- id

\- conversation

\- sender

\- message\_type

\- body

\- reply\_to

\- created\_at

\- updated\_at

\- deleted\_at

\- edited\_at



Message types:



\- TEXT

\- FILE

\- IMAGE

\- AUDIO

\- VIDEO

\- SYSTEM

\- MEETING

\- LOCATION

\- LINK

\- AI\_GENERATED





3.4 MessageAttachment



Represents a file attached to a message.



Must integrate with the future Documents/File subsystem.



Do NOT duplicate the document storage architecture here.





3.5 MessageReaction



Represents a reaction.



Properties:



\- message

\- user

\- reaction

\- created\_at



A user should not create duplicate identical reactions

on the same message.





3.6 MessageReadState



Tracks message delivery/read state.



States:



SENT

DELIVERED

READ





3.7 MessageMention



Represents user mentions.



Example:



@user





3.8 MessageThread



Supports threaded discussions.



A message may act as a thread root.



Replies reference the root message.





============================================================

4\. CHANNELS

============================================================



Channels are persistent communication spaces.



Examples:



\- Engineering

\- Management

\- Production

\- HR

\- Project Alpha



Channels must support:



\- public channels

\- private channels

\- restricted channels

\- membership management

\- moderators

\- pinned messages

\- archived channels

\- channel description

\- channel topic





Channel access must be permission-based.



Never rely only on frontend restrictions.





============================================================

5\. DIRECT CHAT

============================================================



Direct Chat represents a private conversation between users.



Rules:



\- exactly two active participants

\- same two users must not accidentally create unlimited

&#x20; duplicate direct conversations

\- tenant boundaries must be enforced

\- users from different tenants cannot communicate unless

&#x20; explicit cross-tenant communication is introduced later





============================================================

6\. GROUP CHAT

============================================================



Group conversations support:



\- multiple participants

\- roles

\- invitations

\- participant removal

\- mute

\- notifications

\- message history

\- file sharing





The system must maintain a complete membership history.





============================================================

7\. PRESENCE SYSTEM

============================================================



Presence is a real-time capability.



States:



ONLINE

OFFLINE

AWAY

BUSY

DO\_NOT\_DISTURB

IN\_MEETING



Presence must not be stored exclusively in SQL Server.



Architecture:



Client

&#x20;   ↓

WebSocket

&#x20;   ↓

Django Channels

&#x20;   ↓

Redis

&#x20;   ↓

Presence Service





Persistent information may be stored in SQL Server where

business requirements require historical/audit information.





============================================================

8\. REAL-TIME ARCHITECTURE

============================================================



Primary technologies:



Django Channels

Redis

WebSocket



Architecture:



Web Client

&#x20;    |

&#x20;    | WebSocket

&#x20;    ↓

Django Channels

&#x20;    |

&#x20;    ↓

Communication Application Layer

&#x20;    |

&#x20;    ↓

Domain

&#x20;    |

&#x20;    ↓

Infrastructure

&#x20;    |

&#x20;    ├── SQL Server

&#x20;    └── Redis





WebSocket consumers must remain thin.



Consumer responsibilities:



\- authenticate connection

\- identify tenant

\- validate transport input

\- call application service

\- send response/event





Consumer must NOT contain:



\- business rules

\- database business logic

\- permission algorithms

\- message creation rules

\- meeting rules





============================================================

9\. EVENT ARCHITECTURE

============================================================



Communication must emit domain/application events.



Examples:



MessageCreated

MessageEdited

MessageDeleted

MessageRead

ParticipantJoined

ParticipantLeft

ConversationCreated

ConversationArchived



CallStarted

CallAccepted

CallRejected

CallEnded



MeetingCreated

MeetingStarted

MeetingEnded

ParticipantJoinedMeeting

ParticipantLeftMeeting



RecordingStarted

RecordingStopped



AITranscriptionCompleted

AISummaryGenerated

AIActionItemsGenerated





These events must be usable by:



\- Notification

\- Audit

\- AI

\- Analytics

\- Search

\- Workflow

\- Integration Hub





============================================================

10\. VOICE CALL ARCHITECTURE

============================================================



Voice calls must use WebRTC.



Meryx backend is NOT the audio transport.



Architecture:



Client A

&#x20;   |

&#x20;   | WebRTC

&#x20;   |

&#x20;   +----------------+

&#x20;                    |

&#x20;                 Media

&#x20;                    |

&#x20;   +----------------+

&#x20;   |

Client B





Backend responsibilities:



\- authentication

\- authorization

\- call session creation

\- signaling

\- participant management

\- call state

\- audit

\- call metadata





WebRTC responsibilities:



\- audio transport

\- media negotiation

\- peer connection





Django Channels responsibilities:



\- signaling transport





Redis responsibilities:



\- ephemeral signaling/state

\- presence

\- distributed real-time coordination





============================================================

11\. WEBRTC SIGNALING

============================================================



Signaling messages must support:



OFFER

ANSWER

ICE\_CANDIDATE

CALL\_INVITE

CALL\_ACCEPT

CALL\_REJECT

CALL\_END

MEDIA\_STATE\_CHANGE





The signaling protocol must be versioned.



Example:



communication.signal.v1





Do not hard-code signaling assumptions throughout the system.





============================================================

12\. GROUP VOICE CALL

============================================================



Group calls require a scalable media architecture.



Do NOT design the backend as a simple peer-to-peer mesh

for unlimited participants.



The architecture must allow future integration with an

SFU (Selective Forwarding Unit).



Conceptual architecture:



Participants

&#x20;    ↓

WebRTC

&#x20;    ↓

SFU

&#x20;    ↓

Other Participants





Meryx controls:



\- meeting session

\- authorization

\- participants

\- signaling

\- meeting state

\- metadata



SFU controls:



\- media routing





The SFU implementation may initially be an infrastructure

adapter.



The domain must not depend on a specific SFU vendor.





============================================================

13\. VIDEO MEETINGS

============================================================



Meeting is a specialized communication aggregate.



Meeting states:



SCHEDULED

WAITING

LIVE

ENDED

CANCELLED





Meeting properties:



\- id

\- conversation

\- organizer

\- title

\- description

\- scheduled\_start

\- scheduled\_end

\- actual\_start

\- actual\_end

\- meeting\_status





Meeting participants:



\- invited

\- accepted

\- declined

\- joined

\- left





============================================================

14\. SCREEN SHARING

============================================================



Screen sharing is a WebRTC media capability.



The backend manages:



\- permission

\- participant state

\- audit

\- meeting state



The actual screen stream is handled by WebRTC.





============================================================

15\. RECORDING

============================================================



Recording must be treated as an explicit capability.



The system must support:



\- recording requested

\- recording started

\- recording stopped

\- recording processing

\- recording available

\- recording failed



Recording metadata must be persisted.



Actual binary recording storage must integrate with the

future document/storage infrastructure.



Do NOT store large media blobs directly inside communication

domain tables unless a deliberate architecture decision is

made later.





============================================================

16\. OFFICIAL LETTERS

============================================================



Official Letters are NOT ordinary chat messages.



They belong to a formal communication/document workflow.



They must eventually support:



\- sender

\- recipient

\- organization

\- department

\- subject

\- body

\- attachments

\- reference number

\- status

\- approval

\- signature

\- dispatch

\- receipt

\- audit trail





Official Letter should integrate with:



Documents

Workflow

Organization

Identity

Audit

Notifications





Do not implement official letters as:



Message(message\_type="LETTER")





They require a dedicated domain model.





============================================================

17\. MESSAGE SECURITY

============================================================



Every communication operation must validate:



\- authenticated user

\- tenant

\- conversation membership

\- conversation role

\- resource ownership

\- permission

\- object state





Never trust:



\- client-provided tenant ID

\- client-provided sender ID

\- client-provided permissions





Sender identity must come from authenticated context.





============================================================

18\. MULTI-TENANCY

============================================================



Every communication aggregate must belong to a Tenant

directly or indirectly.



Examples:



Tenant

&#x20;  |

&#x20;  └── Conversation

&#x20;         |

&#x20;         ├── Participants

&#x20;         └── Messages





Cross-tenant communication must NOT be enabled implicitly.





============================================================

19\. AUDIT

============================================================



Communication actions must be auditable.



Examples:



\- conversation created

\- participant added

\- participant removed

\- message created

\- message edited

\- message deleted

\- message read

\- call started

\- call ended

\- meeting created

\- participant joined

\- participant removed

\- recording started

\- recording stopped





Audit records must contain enough information to reconstruct

important security/business events.





============================================================

20\. NOTIFICATIONS

============================================================



Communication integrates with Notification Domain.



Examples:



NewMessage

Mention

CallIncoming

CallMissed

MeetingInvitation

MeetingStarting

ParticipantJoined





Communication should emit events.



Notification system decides:



\- push

\- email

\- in-app

\- desktop

\- mobile





Communication must not directly implement every notification

transport.





============================================================

21\. AI INTEGRATION

============================================================



AI must consume communication events/data through defined

interfaces.



AI capabilities:



\- message summarization

\- meeting transcription

\- meeting summary

\- action-item extraction

\- topic extraction

\- sentiment analysis

\- conversation classification

\- knowledge extraction

\- semantic search

\- automatic task creation

\- automatic document generation





Example:



MeetingEnded

&#x20;     ↓

AI Processing

&#x20;     ↓

Transcript

&#x20;     ↓

Summary

&#x20;     ↓

Action Items

&#x20;     ↓

Tasks





AI must NOT directly modify domain state without going

through application services and authorization rules.





============================================================

22\. SEARCH

============================================================



Communication must eventually support:



\- message search

\- conversation search

\- participant search

\- attachment search

\- semantic search





Search infrastructure must remain replaceable.



The domain must not depend on Elasticsearch/OpenSearch/etc.





============================================================

23\. OFFLINE SUPPORT

============================================================



The architecture must support offline-capable clients.



Client may temporarily store:



\- unsent messages

\- pending events

\- read states





Server must provide deterministic identifiers and

idempotency mechanisms.



Duplicate message submission must not create duplicate

messages.





============================================================

24\. IDEMPOTENCY

============================================================



Operations that may be retried must support idempotency.



Especially:



\- send message

\- call initiation

\- meeting creation

\- participant invitation

\- file upload completion





Example:



client\_request\_id



A retry using the same request ID must not create another

business object.





============================================================

25\. DOMAIN EVENTS VS INTEGRATION EVENTS

============================================================



Do not mix them.



Domain Event:



MessageCreated



Integration Event:



CommunicationMessageCreatedV1





Domain events belong inside the domain/application boundary.



Integration events are designed for external consumers.





============================================================

26\. DATABASE DESIGN

============================================================



Initial conceptual tables:



communication\_conversations

communication\_conversation\_participants

communication\_messages

communication\_message\_attachments

communication\_message\_reactions

communication\_message\_mentions

communication\_message\_read\_states

communication\_meetings

communication\_meeting\_participants

communication\_calls

communication\_call\_participants

communication\_recordings

communication\_channels

communication\_channel\_memberships

communication\_pins





All tables must follow the global Meryx database standards:



\- UUID primary key

\- created\_at

\- updated\_at

\- created\_by where applicable

\- updated\_by where applicable

\- soft-delete where appropriate

\- tenant relationship

\- indexes

\- constraints

\- audit strategy





============================================================

27\. INDEXING

============================================================



Important indexes include:



Conversation:



tenant\_id

type

is\_active





Participant:



conversation\_id

user\_id

conversation\_id + user\_id





Message:



conversation\_id

sender\_id

created\_at

reply\_to\_id





ReadState:



message\_id

user\_id





Meeting:



tenant\_id

scheduled\_start

status





Call:



meeting\_id

status

started\_at





Composite indexes must be introduced based on actual query

patterns, not arbitrarily.





============================================================

28\. TRANSACTION BOUNDARIES

============================================================



Application services define transaction boundaries.



Example:



SendMessageService



1\. authenticate

2\. resolve tenant

3\. validate conversation

4\. validate membership

5\. validate message

6\. create message

7\. persist

8\. create domain event

9\. commit

10\. publish integration event

11\. trigger notifications





The event must not be published as successfully completed

before the transaction is safely committed.



Use an Outbox pattern where reliable event delivery is

required.





============================================================

29\. OUTBOX

============================================================



Communication events that must reach external systems should

use an Outbox mechanism.



Concept:



Database Transaction

&#x20;       |

&#x20;       +-- Business Data

&#x20;       |

&#x20;       +-- Outbox Event

&#x20;               |

&#x20;               ↓

&#x20;         Event Dispatcher

&#x20;               |

&#x20;               ↓

&#x20;      Notification / AI / Analytics / Integration





This prevents lost events.





============================================================

30\. API ARCHITECTURE

============================================================



REST API responsibilities:



\- conversation management

\- participant management

\- message history

\- search

\- meeting scheduling

\- meeting metadata

\- recording metadata

\- administration





WebSocket responsibilities:



\- real-time messages

\- typing indicators

\- presence

\- signaling

\- read receipts

\- live meeting state





REST must not be replaced by WebSocket merely because the

operation is related to communication.





============================================================

31\. TYPING INDICATORS

============================================================



Typing state is ephemeral.



It should normally live in:



WebSocket + Redis



Do not persist every typing event in SQL Server.





============================================================

32\. READ RECEIPTS

============================================================



Read state is business-relevant and may require persistence.



Example:



Message A

&#x20;   |

&#x20;   +-- User 1 → READ

&#x20;   +-- User 2 → DELIVERED

&#x20;   +-- User 3 → SENT





Bulk updates should be supported to avoid excessive database

writes.





============================================================

33\. MESSAGE EDITING

============================================================



Editing rules must be explicit.



Possible policy:



\- sender can edit own message

\- editing window configurable

\- admins may have elevated rights

\- edited\_at recorded

\- audit record created





Do not physically destroy historical state when audit/history

requirements require preservation.





============================================================

34\. MESSAGE DELETION

============================================================



Default behavior:



Soft Delete



Deleted messages may display:



"Message deleted"





Actual physical deletion must be governed by:



\- retention policy

\- legal policy

\- tenant policy

\- administrator policy





============================================================

35\. DOMAIN SERVICES

============================================================



Expected application/domain services include:



CreateConversationService

AddParticipantService

RemoveParticipantService

SendMessageService

EditMessageService

DeleteMessageService

MarkMessageReadService

CreateChannelService

ArchiveConversationService



StartCallService

AcceptCallService

RejectCallService

EndCallService



CreateMeetingService

JoinMeetingService

LeaveMeetingService

StartMeetingService

EndMeetingService



StartRecordingService

StopRecordingService





Names may evolve during implementation, but responsibilities

must remain separated.





============================================================

36\. REPOSITORIES

============================================================



Domain/application code must depend on interfaces.



Examples:



ConversationRepository

MessageRepository

MeetingRepository

CallRepository

RecordingRepository

PresenceRepository





Infrastructure provides implementations.



Example:



DjangoConversationRepository





Domain must not directly use Django ORM.





============================================================

37\. DEPENDENCY DIRECTION

============================================================



Correct:



Interfaces

&#x20;   ↓

Application

&#x20;   ↓

Domain



Infrastructure

&#x20;   ↓

implements interfaces





Incorrect:



Domain

&#x20;   ↓

Django ORM



Domain

&#x20;   ↓

Redis



Domain

&#x20;   ↓

Django Channels





These dependencies are forbidden.





============================================================

38\. TESTING

============================================================



Communication must have:



Unit Tests

Integration Tests

API Tests

WebSocket Tests

Security Tests

Permission Tests

Concurrency Tests

Idempotency Tests





Critical scenarios:



\- unauthorized conversation access

\- cross-tenant access

\- duplicate message

\- duplicate participant

\- invalid meeting state

\- unauthorized recording

\- call authorization

\- message edit authorization

\- message deletion authorization

\- event delivery failure





============================================================

39\. OBSERVABILITY

============================================================



Communication must produce structured logs and metrics.



Metrics:



messages\_per\_second

active\_connections

active\_calls

active\_meetings

websocket\_errors

message\_delivery\_latency

event\_processing\_latency

failed\_signaling\_requests





Never log:



\- passwords

\- tokens

\- private message bodies unnecessarily

\- sensitive media





============================================================

40\. IMPLEMENTATION ORDER

============================================================



Implementation must proceed in this order:



STEP 1

Communication domain boundaries



STEP 2

Conversation domain



STEP 3

Participant domain



STEP 4

Message domain



STEP 5

Channel domain



STEP 6

REST APIs



STEP 7

WebSocket infrastructure



STEP 8

Redis presence



STEP 9

Events



STEP 10

Outbox



STEP 11

Voice signaling



STEP 12

WebRTC integration



STEP 13

Meetings



STEP 14

Group calls



STEP 15

Recording



STEP 16

AI integration



STEP 17

Search



STEP 18

Offline/idempotency



STEP 19

Performance optimization



STEP 20

Security hardening





============================================================

41\. DEFINITION OF DONE

============================================================



Phase 8 is NOT complete when chat messages merely work.



Phase 8 is complete only when:



\[ ] Communication bounded context exists



\[ ] Domain/application/infrastructure boundaries exist



\[ ] Direct Chat works



\[ ] Group Chat works



\[ ] Channels work



\[ ] Message lifecycle works



\[ ] File attachments integrate correctly



\[ ] Read states work



\[ ] Reactions work



\[ ] Mentions work



\[ ] Presence works



\[ ] WebSocket architecture works



\[ ] Redis integration works



\[ ] Domain events exist



\[ ] Outbox exists



\[ ] Voice signaling works



\[ ] WebRTC integration exists



\[ ] Meetings work



\[ ] Group meetings work



\[ ] Screen sharing is supported



\[ ] Recording architecture exists



\[ ] Notification integration exists



\[ ] AI integration interfaces exist



\[ ] Audit integration exists



\[ ] Multi-tenancy is enforced



\[ ] Permission system is enforced



\[ ] Idempotency exists



\[ ] Security tests pass



\[ ] Integration tests pass



\[ ] WebSocket tests pass



\[ ] Documentation exists



\[ ] Architecture decisions are documented





============================================================

END OF PHASE 8

============================================================

