# Tekarai --- Architecture Handoff

## Purpose

This document transfers the architectural intent of Tekarai to a new
developer or coding agent.

The previous codebase must be treated as lost. The new implementation
must be reconstructed from the project specification and validated
continuously.

## 1. What Tekarai Is

Tekarai is a general-purpose Enterprise Operations Platform.

It is not:

-   a factory-only system
-   an HR-only system
-   a project-management-only system
-   an AI chatbot
-   a collection of unrelated Django apps

The original business environment was a pharmaceutical factory, but that
environment is a reference customer/domain, not the product boundary.

## 2. Architecture Style

Tekarai uses:

-   Domain-Driven Design
-   Clean Architecture
-   SOLID
-   Modular Monolith
-   API First
-   Event Driven
-   Security First
-   AI Native
-   Cloud Ready
-   Offline Ready
-   Configuration over Customization
-   Documentation Driven Development

The first deployment is a Modular Monolith.

Do not prematurely split domains into microservices.

## 3. Dependency Direction

``` text
Presentation
      ↓
Application
      ↓
Domain
      ↑
Infrastructure
```

Infrastructure implements interfaces defined by inner layers.

Domain code must remain framework-independent.

## 4. Domain Boundary

Each bounded context owns its own business concepts.

A domain may expose:

-   application use cases
-   public DTOs/contracts
-   events
-   repository interfaces

A domain must not directly manipulate another domain's internal models.

Bad:

``` text
Tasks → direct SQL update of Projects tables
```

Good:

``` text
Tasks → Application Contract / Domain Event → Projects
```

## 5. Domain Map

``` text
Platform Core
Identity
Organization
People
Projects
Tasks
Assets
Devices
Maintenance
Documents
Workflow
Communication
Notifications
Analytics
Performance
AI
Integration
Audit
```

These are logical boundaries. They may map to Django apps/modules, but
the architecture is not defined by Django app names.

## 6. Core Architectural Invariants

1.  Tenant isolation is enforced.
2.  Authorization is enforced server-side.
3.  Domain logic does not live in views.
4.  External systems are accessed through adapters.
5.  AI does not bypass authorization.
6.  Audit information is preserved for important operations.
7.  Migrations are version controlled.
8.  Events represent facts.
9.  Commands request changes.
10. Queries do not mutate state.
11. Domain code does not depend on Django.
12. API contracts are versioned.
13. Tests accompany implementation.
14. Security-sensitive actions are auditable.
15. Customer-specific logic does not leak into the Core.

## 7. Backend Layers

### Presentation

``` text
REST Views
Serializers
URL Routing
WebSocket Consumers
Authentication Adapters
```

### Application

``` text
CreateProject
AssignTask
ApproveDocument
CreateMaintenanceWorkOrder
StartMeeting
EvaluateEmployee
```

### Domain

``` text
Project
Task
Document
Workflow
Meeting
EmployeeEvaluation
```

### Infrastructure

``` text
Django ORM Repository
SQL Server
Redis
Object Storage
External API Adapter
WebRTC Adapter
AI Provider Adapter
```

## 8. Tenant Boundary

Tenant is the highest normal business isolation boundary.

Every tenant-owned operation must have tenant context.

The client must not be trusted to establish authorization merely by
submitting a tenant UUID.

Tenant context must be derived from authenticated
identity/session/authorized administrative context.

## 9. Identity Boundary

Identity owns who the user is and how the user authenticates.

Organization/People owns organizational and employment facts.

Therefore:

``` text
Identity.User
    ≠
People.Employee
```

A user may correspond to an employee, but these concepts are not
interchangeable.

## 10. Communication Boundary

Communication must support:

``` text
Direct Chat
Group Chat
Channels
Presence
Voice Call
Group Voice
Video Meeting
Screen Sharing
Recording
Transcription
AI Summary
```

Architecture:

``` text
Client
  ↓
WebSocket / Signaling
  ↓
Communication Application
  ↓
WebRTC / Media Infrastructure
```

Django must not become the media transport layer.

## 11. AI Boundary

AI must be accessed through application-level capabilities.

Example:

``` text
Performance Analysis Use Case
        ↓
AI Application Service
        ↓
Model Provider Port
        ↓
OpenAI / Local Model / Other Provider
```

Never:

``` text
Django View → random LLM API call
```

## 12. Integration Boundary

Every external system gets an adapter.

Examples:

``` text
WinCC Adapter
SAP Adapter
OPC-UA Adapter
MQTT Adapter
REST Adapter
```

The domain knows the business concept, not the vendor protocol.

## 13. Data Ownership

Every table must have a clear owner.

No shared "god tables".

Cross-domain reporting must use:

-   read models
-   reporting projections
-   controlled queries
-   events
-   analytics models

Do not compromise domain boundaries merely to make reporting convenient.

## 14. Scaling Strategy

Start:

``` text
Modular Monolith
+
SQL Server
+
Redis when required
```

Evolve toward service decomposition only when proven scale or isolation
requirements justify it.

Microservices are an optimization, not the starting architecture.

## 15. Extension Strategy

Industry-specific functionality belongs in:

``` text
Industry Pack
Plugin
Connector
Configuration
Extension Module
```

Never hard-code a pharmaceutical-factory-specific rule into Core unless
the rule is genuinely generic.

## 16. Architectural Decision Process

Before a major architectural change:

1.  State the problem.
2.  State constraints.
3.  List alternatives.
4.  Evaluate consequences.
5.  Choose one.
6.  Record an ADR.
7.  Update affected documentation.
8.  Implement.
9.  Test.
10. Verify.

No silent architecture changes.

## 17. Rebuild Starting Point

The implementation begins from:

``` text
empty repository
```

The first work is documentation and repository bootstrap.

Then:

``` text
Environment
→ Core
→ Identity
→ Organization
→ People
→ Business Domains
→ Communication
→ AI
→ Integration
→ Production
```

## 18. What Must Never Happen

Do not:

-   put everything in one models.py
-   put all business logic in views
-   call external APIs directly from models
-   use global mutable state
-   skip migrations
-   bypass authorization
-   trust tenant IDs from clients
-   mix authentication and employee data
-   let AI mutate business data without authorization
-   build microservices before domain boundaries are proven
-   create undocumented abstractions
-   introduce temporary code into the production architecture

## 19. Resume Protocol

At the beginning of every new development session record:

``` text
Current Phase:
Current Sprint:
Current Domain:
Current Task:
Repository State:
Last Verified Commit:
Last Green Quality Gate:
Open Questions:
```

Then continue from the first incomplete acceptance criterion.

Never restart completed work unless verification proves it is invalid.
