# Tekarai --- Master Implementation Specification

**Document status:** Authoritative implementation specification\
**Product:** Tekarai Enterprise Operations Platform\
**Starting condition:** Previous implementation is considered lost.
Rebuild from zero.\
**Primary backend:** Python 3.12 + Django 6 + Django REST Framework +
SQL Server\
**Architecture:** Modular Monolith + DDD + Clean Architecture + SOLID +
Event-Driven\
**Target:** Production-ready, enterprise-grade, globally reusable
platform

## 1. Purpose

This document is the master specification for rebuilding Tekarai from an
empty repository.

A developer or coding agent must be able to use this document as the
primary execution contract. It must not invent architecture, rename
domains, introduce customer-specific assumptions, or skip stages because
a simpler implementation appears convenient.

Tekarai is not a factory-specific application. The original target
environment included a pharmaceutical factory, but the product itself
must remain a general-purpose Enterprise Operations Platform.

Industry-specific behavior must be implemented through extensions,
connectors, configuration, and Industry Packs.

## 2. Non-Negotiable Rules

1.  Production-ready code only.
2.  No placeholder classes, fake services, TODO implementations, or
    throwaway architecture.
3.  No domain logic in Django views.
4.  No direct cross-domain database manipulation.
5.  No circular domain dependencies.
6.  Domain rules must be explicit and testable.
7.  Every persistent entity must have an explicit lifecycle strategy.
8.  Auditable business operations must produce audit information.
9.  Security is part of the architecture, not a later feature.
10. Multi-tenancy must be designed before business data is implemented.
11. API contracts must be stable and versionable.
12. Migrations must be deterministic and reviewed.
13. Tests are required for every completed capability.
14. Every implementation phase ends with verification.
15. Never silently change an architectural decision.
16. If a requirement is unclear, document the ambiguity in an Open
    Question rather than guessing.
17. Never couple the core product to one customer's organization,
    terminology, or workflow.
18. Django is an implementation framework, not the domain architecture.
19. AI is a platform capability integrated into the product, not a
    decorative add-on.
20. Communication is a first-class platform domain.

## 3. Product Definition

Tekarai provides a unified enterprise platform for:

-   Identity and access
-   Tenants and organizations
-   Employees and people operations
-   Projects and tasks
-   Assets and devices
-   Maintenance
-   Documents
-   Workflow and approvals
-   Communication
-   Notifications
-   Analytics and reporting
-   AI capabilities
-   External integrations
-   Audit and governance

The system must support web, mobile, desktop, machine/agent clients, and
external integrations.

## 4. Repository Target

``` text
tekarai/
├── backend/
├── frontend-web/
├── mobile/
├── desktop/
├── agents/
├── ai/
├── sdk/
├── docs/
├── deployment/
└── infrastructure/
```

The backend is the first implementation target.

## 5. Backend Technology Baseline

Use:

-   Python 3.12
-   Django 6
-   Django REST Framework
-   SQL Server
-   mssql-django
-   SimpleJWT
-   django-environ
-   django-cors-headers
-   pyodbc
-   Waitress for the Windows deployment baseline where applicable

Future infrastructure may add Redis, Django Channels, ASGI deployment,
background job infrastructure, object storage, search infrastructure,
WebRTC infrastructure, and event transport.

Do not add infrastructure merely because it is fashionable. Add it when
a documented capability requires it.

## 6. Architecture

Tekarai follows:

``` text
Presentation
    ↓
Application
    ↓
Domain
    ↓
Infrastructure
```

Dependencies point inward.

### Presentation

Contains REST API, WebSocket endpoints, authentication adapters,
serializers, and request/response mapping.

Presentation must not contain business rules.

### Application

Contains use cases, commands, queries, orchestration, transaction
boundaries, application services, and DTOs.

### Domain

Contains entities, value objects, aggregates, domain services, domain
events, business rules, and repository contracts.

The domain must not import Django models, HTTP classes, Redis clients,
SQL Server drivers, or external SDKs.

### Infrastructure

Contains Django ORM implementations, repository implementations,
database access, external services, Redis, messaging, storage, search,
and integration adapters.

## 7. Domain Map

Initial bounded contexts:

1.  Platform Core
2.  Identity
3.  Organization
4.  People / HR
5.  Projects
6.  Tasks
7.  Assets
8.  Devices
9.  Maintenance
10. Documents
11. Workflow
12. Communication
13. Notifications
14. Analytics
15. AI
16. Integration
17. Audit

These contexts are conceptual boundaries first. They must not
automatically become separate deployable services.

Tekarai starts as a Modular Monolith.

## 8. Platform Core

Core owns cross-cutting primitives such as:

-   UUID identity
-   timestamps
-   activation state
-   soft deletion
-   lifecycle metadata
-   tenant ownership primitives
-   common exceptions
-   common result/response contracts
-   base repository contracts
-   domain event abstractions

A generic base model must not become a dumping ground for business
fields.

## 9. Identity

Identity owns:

-   User
-   authentication credentials
-   sessions
-   authentication factors
-   roles
-   permissions
-   access policies
-   tokens
-   identity lifecycle

The custom User model must be established before dependent domains.

The final identity design must support tenant-aware users, account
status, authentication state, security metadata, role assignment, and
permission evaluation.

Never use email or username as an architectural primary key.

## 10. Organization

Organization owns:

-   Tenant
-   Organization
-   legal/organizational metadata
-   organizational units
-   departments
-   locations
-   organizational hierarchy

A tenant is the top-level isolation boundary.

Business entities that are tenant-owned must have an explicit tenant
relationship.

Cross-tenant data access is forbidden unless a documented platform-level
capability explicitly allows it.

## 11. People / HR

People owns:

-   Employee profile
-   employment lifecycle
-   positions
-   job titles
-   reporting relationships
-   employee assignments
-   skills
-   competencies
-   evaluation participants

Do not place HR-specific fields into the Identity User model unless they
are truly identity concerns.

## 12. Projects and Tasks

Projects owns projects, project membership, project lifecycle, project
phases, project objectives, and project metadata.

Tasks owns tasks, task status, priorities, assignments, dependencies,
checklists, comments, task history, and task relations.

A task may reference a project through a defined contract, but Tasks
must not reach into Project internals.

## 13. Assets, Devices and Maintenance

Assets owns the enterprise asset lifecycle.

Devices owns technical devices and machine metadata.

Maintenance owns maintenance plans, work orders, maintenance schedules,
incidents, service history, and maintenance outcomes.

Industry-specific equipment protocols belong in Integration/Industry
extensions.

## 14. Documents

Documents owns document metadata, document versions, document lifecycle,
document classification, document permissions, and document relations.

Binary storage must be abstracted behind a storage interface.

Database records and binary object storage must not be tightly coupled.

## 15. Workflow

Workflow owns workflow definitions, workflow versions, workflow
instances, steps, transitions, approvals, delegation, escalation, and
state history.

Workflow must be generic enough to serve documents, projects, tasks, HR
operations, maintenance, and other domains.

## 16. Communication

Communication is a first-class domain.

Capabilities:

-   direct chat
-   group chat
-   channels
-   messages
-   attachments
-   presence
-   voice calls
-   group voice calls
-   video meetings
-   screen sharing
-   meeting recording
-   transcription
-   AI meeting summary

Real-time communication should use WebSockets / Django Channels where
appropriate.

WebRTC handles media transport.

Redis may provide channel-layer/presence support.

Media must not be transported through Django request/response APIs.

## 17. Notifications

Notifications owns in-app notifications, email notification requests,
push notification requests, notification preferences, delivery status,
and templates.

Notification generation should be event-driven where practical.

## 18. Analytics and Performance Engine

The Performance Engine must support daily, weekly, monthly, quarterly,
and annual evaluations.

Requirements:

-   multiple evaluators
-   configurable evaluator weights
-   editable scores
-   score history
-   audit trail
-   calculation rules
-   historical snapshots
-   KPI relationships
-   AI analysis and prediction

The calculation engine must be deterministic and independently testable.

AI recommendations must never silently overwrite authoritative business
records.

## 19. AI Platform

AI is a core platform capability.

Required capabilities include:

-   project analysis
-   performance analysis
-   equipment analysis
-   meeting summarization
-   task extraction
-   letter generation
-   KPI analysis
-   recommendations
-   predictions
-   knowledge graph

Architecture must separate model providers, prompt definitions, AI use
cases, model configuration, inference execution, knowledge retrieval,
and audit/governance.

AI output must be classified as advisory, draft, automated, or
authoritative.

Authoritative business changes require explicit business rules and
authorization.

## 20. Integration Hub

The Integration Hub provides adapters for external systems.

Potential integrations:

-   REST APIs
-   webhooks
-   MQTT
-   OPC-UA
-   Siemens WinCC
-   SAP
-   industry-specific connectors

External integrations must use ports/adapters.

Never place vendor SDK calls inside domain entities.

## 21. Audit

Audit must record important security and business changes.

At minimum support:

-   actor
-   tenant
-   timestamp
-   operation
-   target type
-   target identifier
-   change metadata
-   request/correlation identifier
-   source/client information where permitted

Audit records are append-oriented and must not be casually editable.

## 22. Multi-Tenancy

Tenant isolation is mandatory.

Rules:

-   every tenant-owned aggregate has tenant ownership
-   application services must enforce tenant scope
-   selectors/repositories must require tenant context where applicable
-   API authorization must not rely only on client-provided tenant IDs
-   cross-tenant queries are prohibited by default
-   administrative cross-tenant operations must be explicit and audited

Tenant context must be established before executing tenant-scoped use
cases.

## 23. Database Rules

SQL Server is the initial system of record.

Default identifier:

``` text
UUID
```

Persistent entities require:

-   primary key
-   lifecycle timestamps where appropriate
-   tenant ownership where appropriate
-   indexes based on actual access patterns
-   uniqueness constraints
-   foreign-key rules
-   deletion strategy

Do not create indexes blindly. Every index must have a query/access
justification.

Migrations are source-controlled artifacts.

Never manually edit production database structure outside the migration
strategy.

## 24. API Rules

API conventions must include:

-   versioned endpoints
-   consistent response envelope
-   consistent error envelope
-   authentication
-   authorization
-   pagination
-   filtering
-   sorting
-   validation
-   rate limiting
-   idempotency where needed

Example:

``` text
/api/v1/<domain>/<resource>/
```

Serializers map transport data to application DTOs. They must not become
the location of domain business rules.

## 25. Event Architecture

Distinguish:

-   Domain Events
-   Integration Events
-   Commands
-   Queries

Events represent facts.

Commands represent requests to perform actions.

Queries must not mutate business state.

Event handlers must be idempotent where duplicate delivery is possible.

Retries and dead-letter handling are infrastructure concerns.

## 26. Security

Security baseline:

-   secure password handling through Django authentication primitives
-   JWT for API authentication where appropriate
-   authorization at application boundaries
-   object-level authorization
-   tenant isolation
-   CSRF protection where applicable
-   CORS restrictions
-   secure secrets management
-   production DEBUG disabled
-   secure cookie settings where applicable
-   audit of security-sensitive operations
-   rate limiting
-   input validation
-   dependency vulnerability management

Never commit secrets.

## 27. Testing

Required levels:

1.  Domain unit tests
2.  Application/use-case tests
3.  Repository/integration tests
4.  API tests
5.  Permission/security tests
6.  Event/integration tests
7.  End-to-end tests
8.  Performance tests where required

A capability is not complete until its required tests pass.

## 28. Quality Gate

Before accepting a backend change:

``` powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

The project should also adopt Ruff, Black, and Mypy where configuration
is established.

A green quality gate is part of Definition of Done.

## 29. Implementation Order

``` text
0  Repository / Documentation
1  Environment / Settings
2  Platform Core
3  Identity
4  Organization
5  People
6  Projects
7  Tasks
8  Assets
9  Devices
10 Maintenance
11 Documents
12 Workflow
13 Communication
14 Notifications
15 Analytics
16 Performance
17 Audit
18 AI
19 Integration Hub
20 Security Hardening
21 Testing / E2E
22 Deployment
23 Production Readiness
```

Do not implement advanced AI or WebRTC before platform primitives and
identity/tenant boundaries are stable.

## 30. Required Implementation Pattern

For each capability:

``` text
1. Read specification
2. Define domain concepts
3. Define entities/value objects
4. Define aggregate boundaries
5. Define repository contracts
6. Define application use cases
7. Define infrastructure
8. Define API contract
9. Define permissions
10. Define events
11. Define migrations
12. Write tests
13. Run quality gate
14. Review architecture
15. Commit
16. Update documentation
```

## 31. File-by-File Rule

Every file must have:

-   one clear responsibility
-   defined layer
-   defined owning domain
-   defined dependencies
-   defined tests

Avoid giant `models.py`, `services.py`, or `utils.py` files.

## 32. Definition of Done

A feature is Done only when:

-   domain behavior is implemented
-   application use case exists where needed
-   persistence is implemented
-   authorization is implemented
-   API is implemented where needed
-   migrations are created
-   tests pass
-   quality checks pass
-   documentation is updated
-   audit behavior is verified where required
-   tenant isolation is verified where applicable

## 33. Rebuild Principle

The previous implementation is considered unavailable.

Therefore:

-   do not assume previous files exist
-   do not assume previous migrations exist
-   do not assume previous database tables exist
-   do not reuse undocumented code
-   reconstruct the architecture from this specification
-   create a clean, deterministic baseline

If an existing repository contains remnants, inspect them first and
compare them against this specification. Do not blindly trust remnants.

## 34. Final Goal

The completed Tekarai platform must be:

-   multi-tenant
-   secure
-   modular
-   auditable
-   extensible
-   API-first
-   AI-native
-   cloud-ready
-   suitable for enterprise deployment
-   suitable for industry extensions
-   maintainable for 5--10+ years

This document is the architectural and implementation authority unless a
newer approved Architecture Decision Record explicitly supersedes a
rule.
