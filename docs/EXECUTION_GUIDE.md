# Meryx --- Execution Guide

## Purpose

This is the operational guide for rebuilding Meryx from zero.

The person executing these instructions may have little or no prior
knowledge of the project.

## Phase 0 --- Prepare the Repository

Target:

``` text
meryx/
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

Create the directories first.

Do not implement business domains yet.

## Phase 1 --- Backend Bootstrap

Enter the backend directory.

Create a virtual environment:

``` powershell
py -3.12 -m venv venv
```

Activate:

``` powershell
.\venv\Scripts\Activate.ps1
```

Upgrade packaging tools:

``` powershell
python -m pip install --upgrade pip
```

Create `requirements.txt` according to the approved technology baseline.

Install:

``` powershell
python -m pip install -r requirements.txt
```

Verify:

``` powershell
python --version
python -m pip --version
```

The Python executable must come from the virtual environment.

## Phase 2 --- Django Project

Create Django project configuration.

Expected conceptual structure:

``` text
backend/
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── urls.py
└── apps/
```

Do not create all business apps and models at once.

## Phase 3 --- Settings

Establish:

-   environment loading
-   secret key configuration
-   debug configuration
-   allowed hosts
-   database configuration
-   installed apps
-   middleware
-   REST Framework
-   authentication
-   CORS
-   timezone
-   static/media configuration
-   logging

Secrets belong in environment variables.

Never commit `.env`.

## Phase 4 --- SQL Server

Configure SQL Server through environment-driven settings.

Required conceptual variables:

``` text
DB_ENGINE
DB_NAME
DB_USER
DB_PASSWORD
DB_HOST
DB_PORT
```

Use the approved SQL Server backend.

Verify connectivity before building business domains.

## Phase 5 --- Platform Core

Implement first:

``` text
UUID identity
Base timestamps
Lifecycle state
Soft-delete infrastructure
Audit metadata primitives
Tenant context primitives
Common exceptions
Common response contracts
```

Then:

``` powershell
python manage.py check
python manage.py makemigrations
python manage.py migrate
```

## Phase 6 --- Identity

Implement:

``` text
User
Authentication
Session/token concepts
Role
Permission
Identity membership
```

The User model must be established before most dependent domains.

Verify:

``` powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

## Phase 7 --- Organization

Implement:

``` text
Tenant
Organization
OrganizationUnit
Department
Location
Hierarchy
```

Define tenant isolation before adding People/Projects.

## Phase 8 --- People

Implement:

``` text
Employee
Position
JobTitle
Employment
ReportingRelationship
Skills
Competencies
```

Keep Employee separate from authentication identity.

## Phase 9 --- Projects

Implement:

``` text
Project
ProjectMember
ProjectPhase
ProjectObjective
```

Add lifecycle and authorization.

## Phase 10 --- Tasks

Implement:

``` text
Task
TaskAssignment
TaskDependency
TaskChecklist
TaskComment
TaskHistory
```

Support priority, status, due dates, assignment, and dependencies.

## Phase 11 --- Assets / Devices

Implement asset lifecycle first.

Then technical devices.

Do not mix generic asset management with vendor-specific machine
protocols.

## Phase 12 --- Maintenance

Implement:

``` text
MaintenancePlan
MaintenanceSchedule
WorkOrder
MaintenanceEvent
MaintenanceHistory
```

Integrations are added later.

## Phase 13 --- Documents

Implement:

``` text
Document
DocumentVersion
DocumentClassification
DocumentPermission
DocumentRelation
```

Storage abstraction must be present.

## Phase 14 --- Workflow

Implement:

``` text
WorkflowDefinition
WorkflowVersion
WorkflowInstance
WorkflowStep
WorkflowTransition
Approval
Delegation
Escalation
```

Workflow must be generic.

## Phase 15 --- Communication

Add:

``` text
Conversation
ConversationMember
Channel
Message
Attachment
Presence
Call
Meeting
Recording
```

Then:

``` text
Django Channels
Redis
WebRTC signaling
```

Do not start with media transport implementation.

## Phase 16 --- Notifications

Implement:

``` text
Notification
NotificationPreference
NotificationTemplate
DeliveryAttempt
```

Connect notification creation to events.

## Phase 17 --- Analytics

Implement read/reporting structures.

Avoid coupling dashboards to aggregate internals.

## Phase 18 --- Performance

Implement concepts such as:

``` text
EvaluationPeriod
Evaluation
Evaluator
EvaluationScore
Weight
KPI
PerformanceSnapshot
```

Support daily/weekly/monthly/quarterly/annual periods.

All score changes must be auditable.

## Phase 19 --- Audit

Implement audit infrastructure and integrate it into important
operations.

## Phase 20 --- AI

Implement AI abstraction first:

``` text
AI Capability
Model Provider Port
Prompt Definition
Context Builder
Inference Service
AI Result
AI Audit
```

Then implement individual capabilities.

## Phase 21 --- Integration Hub

Add:

``` text
REST
Webhooks
MQTT
OPC-UA
WinCC
SAP
```

only when each connector has a defined contract.

## Phase 22 --- Quality

Establish:

``` text
ruff
black
mypy
pytest
```

CI must enforce the quality gate.

## Phase 23 --- Security Hardening

Verify:

-   tenant isolation
-   authorization
-   token security
-   CORS
-   CSRF
-   secrets
-   rate limiting
-   audit
-   production settings

## Phase 24 --- Deployment

Prepare:

``` text
Docker
environment configuration
database backup
logging
monitoring
health checks
deployment scripts
rollback
```

Production deployment must be reproducible.

## Phase 25 --- Final Verification

Run:

``` powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

Then run configured static analysis and type checks.

No known critical failure may remain.

## Execution Discipline

Never jump from Phase 1 to Phase 15 because Communication looks more
interesting.

Architecture dependencies exist for a reason.

The implementation proceeds in dependency order.
