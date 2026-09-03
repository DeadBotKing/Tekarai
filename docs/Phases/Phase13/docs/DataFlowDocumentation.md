# Tekarai --- Data Flow Documentation

## 1. Purpose

This document defines how information moves through Tekarai.

The goal is to prevent developers from creating arbitrary data paths.

## 2. Standard Command Flow

``` text
Client
  ↓
HTTP / WebSocket
  ↓
Authentication
  ↓
Authorization
  ↓
Request Validation
  ↓
Application Command / Use Case
  ↓
Domain Aggregate
  ↓
Repository Interface
  ↓
Infrastructure Repository
  ↓
SQL Server
  ↓
Domain Event
  ↓
Event Handler(s)
  ↓
Audit / Notification / Projection / Integration
```

## 3. Query Flow

``` text
Client
  ↓
Authentication
  ↓
Authorization
  ↓
Query
  ↓
Selector / Read Repository
  ↓
Database / Read Model
  ↓
DTO
  ↓
API Response
```

Queries must not modify business state.

## 4. Authentication Flow

``` text
Login Request
    ↓
Identity Authentication
    ↓
Credential Verification
    ↓
User Status Check
    ↓
Tenant / Membership Resolution
    ↓
Token / Session
    ↓
Authenticated Request
```

Authentication proves identity.

Authorization decides what the identity can do.

## 5. Authorization Flow

``` text
Authenticated Principal
        ↓
Tenant Context
        ↓
Permission
        ↓
Role / Policy
        ↓
Object Scope
        ↓
Business Rule
        ↓
Allow / Deny
```

Authorization must occur server-side.

## 6. Tenant Data Flow

``` text
Authenticated User
        ↓
Authorized Tenant Membership
        ↓
Tenant Context
        ↓
Use Case
        ↓
Tenant-Scoped Repository
        ↓
Tenant-Scoped Query
        ↓
Tenant Data
```

Never accept a client-supplied tenant ID as the sole isolation
mechanism.

## 7. Project → Task Flow

``` text
Create Task
    ↓
Task Application Use Case
    ↓
Validate Project Reference
    ↓
Create Task Aggregate
    ↓
Persist Task
    ↓
TaskCreated Event
    ↓
Notifications / Activity / Analytics
```

Tasks must not directly manipulate Project internals.

## 8. Document → Workflow Flow

``` text
Document Submitted
    ↓
Workflow Start Use Case
    ↓
Workflow Instance
    ↓
Approval Step
    ↓
Authorized Approver
    ↓
Approve / Reject
    ↓
Workflow Transition
    ↓
Domain Event
    ↓
Document Status Update / Notification / Audit
```

## 9. Communication Flow

### Chat

``` text
Client
  ↓
WebSocket
  ↓
Communication Consumer
  ↓
Application Use Case
  ↓
Message Aggregate
  ↓
Persistence
  ↓
Message Event
  ↓
Recipients / Notification / Presence
```

### Voice/Video

``` text
Client
  ↓
Signaling
  ↓
WebSocket / Channels
  ↓
WebRTC Negotiation
  ↓
Peer / Media Infrastructure
```

Tekarai backend handles signaling and business state. It is not the media
transport itself.

## 10. Notification Flow

``` text
Business Event
    ↓
Notification Handler
    ↓
Notification Preference Resolution
    ↓
Notification Record
    ↓
Delivery Adapter
    ├── In-App
    ├── Email
    └── Push
```

A failed external notification must not silently erase the underlying
business event.

## 11. AI Flow

``` text
Business Use Case
    ↓
AI Capability
    ↓
Context Builder
    ↓
Authorization / Data Filtering
    ↓
Prompt / Model Selection
    ↓
Model Provider
    ↓
AI Result
    ↓
Validation / Policy
    ↓
Business Decision or Advisory Output
    ↓
Audit
```

AI must receive only data the requesting principal is authorized to use.

## 12. RAG Flow

``` text
Source Document
    ↓
Document Processing
    ↓
Chunking
    ↓
Embedding
    ↓
Vector Index
    ↓
Authorized Retrieval
    ↓
Context Assembly
    ↓
LLM
    ↓
Answer
```

Authorization must be applied during retrieval, not only after
generation.

## 13. Integration Flow

``` text
External System
    ↓
Connector Adapter
    ↓
Validation
    ↓
Integration Event
    ↓
Application Handler
    ↓
Domain Use Case
    ↓
Domain Event
    ↓
Audit / Notification / Analytics
```

External payloads must not be treated as trusted domain objects.

## 14. Audit Flow

``` text
Use Case
    ↓
Business Operation
    ↓
Audit Event / Audit Record
    ↓
Audit Store
```

Audit information must include enough context to reconstruct what
happened.

## 15. Event Flow

Events are facts.

Example:

``` text
TaskAssigned
```

means the assignment happened.

It does not mean:

``` text
Please assign this task
```

The latter is a command.

## 16. Failure Flow

``` text
Operation
   ↓
Failure
   ├── Validation Error
   ├── Authorization Error
   ├── Business Rule Error
   ├── Infrastructure Error
   └── External Integration Error
```

Map errors to stable API error contracts.

Do not expose stack traces or database internals to clients in
production.

## 17. Transaction Boundary

A business use case should define its transaction boundary.

Normal rule:

``` text
Application Use Case
    ↓
Atomic Business Operation
```

Do not scatter transactions across random model methods.

## 18. Idempotency

Operations that may be retried must be designed for idempotency,
especially:

-   external webhooks
-   integration events
-   notification delivery
-   asynchronous commands

A duplicate event must not create duplicate business state.

## 19. Data Lifecycle

Every persistent object must define:

``` text
Creation
→ Active
→ Updated
→ Archived / Deactivated
→ Deleted / Soft Deleted where appropriate
```

Lifecycle must be domain-specific where necessary.

## 20. Read Models

Cross-domain dashboards should not force every request through multiple
aggregate graphs.

Use:

``` text
Domain Events
    ↓
Projection / Read Model
    ↓
Dashboard / Analytics Query
```

This improves performance without destroying domain ownership.
