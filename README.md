# Tekarai

**Enterprise Operations Platform**

Tekarai is a general-purpose, multi-tenant Enterprise Operations Platform.
It is not a factory-only system, an HR-only system, a project-management-only
system, or an AI chatbot. Industry-specific behaviour is delivered through
Industry Packs, extensions, plugins and connectors — never inside the Core.

---

## Product Purpose

Tekarai provides a unified enterprise platform for:

- Identity and access
- Tenants and organizations
- Employees and people operations
- Projects and tasks
- Assets, devices and maintenance
- Documents
- Workflow and approvals
- Communication (chat, channels, voice, video, meetings)
- Notifications
- Analytics, reporting and performance
- AI capabilities
- External integrations
- Audit and governance

It must support web, mobile, desktop, machine/agent clients and external
integrations.

---

## Architecture Overview

```
Presentation
     ↓
Application
     ↓
Domain
     ↑
Infrastructure
```

Dependencies point inward. The Domain layer is framework-independent and must
never import Django, DRF, HTTP classes, Redis, Channels, WebRTC or vendor SDKs.

Architectural style:

```
Modular Monolith · DDD · Clean Architecture · SOLID
API First · Event Driven · Security First · AI Native
Cloud Ready · Offline Ready · Configuration over Customization
```

Microservices are an optimization, not the starting architecture.

---

## Repository Structure

```
tekarai/
├── backend/            Django backend (first implementation target)
├── frontend-web/
├── mobile/
├── desktop/
├── agents/
├── ai/
├── sdk/
├── docs/               Architecture and phase specifications
├── deployment/
└── infrastructure/
```

> Current state: only `docs/` exists. The implementation starts from zero.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 6 · Django REST Framework |
| Database | Microsoft SQL Server (`mssql-django`, `pyodbc`) |
| Auth | SimpleJWT |
| Real-time | Django Channels · Redis · WebSocket |
| Media | WebRTC (transport only — never through Django) |
| Async | Celery · Redis |
| Config | django-environ |
| Deployment | Waitress (Windows baseline) |

---

## Documentation

All architecture and execution documents live in [`docs/`](docs/).

**Mandatory reading order:**

1. [`docs/TekaraiMasterImplementationSpecification.md`](docs/TekaraiMasterImplementationSpecification.md)
2. [`docs/ArchitectureHandoff.md`](docs/ArchitectureHandoff.md)
3. [`docs/DataFlowDocumentation.md`](docs/DataFlowDocumentation.md)
4. [`docs/DevelopmentRules.md`](docs/DevelopmentRules.md)
5. [`docs/ExecutionGuide.md`](docs/ExecutionGuide.md)
6. [`docs/Handoff.md`](docs/Handoff.md)

Phase-by-phase implementation specifications: [`docs/Phases/`](docs/Phases/)
Current documentation review and open questions: [`docs/Analysis.md`](docs/Analysis.md)

---

## Development Setup

```powershell
cd backend
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The Python executable must come from the virtual environment.

## Environment Setup

Copy the template and fill in local values:

```powershell
copy .env.example .env
```

Never commit `.env`. Secrets belong in environment variables or a secret
manager — never in source control.

## Running the Backend

```powershell
python manage.py check
python manage.py migrate
python manage.py runserver
```

## Running Tests

```powershell
python manage.py test
```

## Quality Checks

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
ruff check .
ruff format --check .
mypy .
```

A green quality gate is part of the Definition of Done.

---

## Naming Conventions

| Scope | Convention |
|---|---|
| Python functions / variables | `camelCase` |
| Python classes | `PascalCase` |
| Framework constants (Django) | `UPPER_SNAKE_CASE` |
| Django apps | lowercase |
| Database tables / columns | `camelCase` |
| Documentation files | `PascalCase.md` |
| API routes | REST-oriented, versioned (`/api/v1/...`) |

---

## Source of Truth

```
Approved Architecture Decision Records
        ↓
TekaraiMasterImplementationSpecification.md
        ↓
Architecture / Data Flow / Development Rules
        ↓
Execution Guide
        ↓
Code
```

If code conflicts with the approved specification, the code is considered
wrong until the architecture is explicitly changed.
