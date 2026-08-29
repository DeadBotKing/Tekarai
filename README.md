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
Decisions: `docs/adr/` (ADR-001 … ADR-011).

---

## Repository Structure

```
tekarai/
├── backend/            Django backend — Phase 01 foundation delivered
├── frontend-web/       placeholder (GUI phase)
├── mobile/             placeholder
├── desktop/            placeholder
├── agents/             placeholder
├── ai/                 placeholder (AI phase)
├── sdk/                placeholder
├── docs/               architecture · adr · api · database · domain ·
│                       development · deployment · security · operations ·
│                       product + Phases specs
├── deployment/         placeholder (deployment phase)
├── infrastructure/     placeholder
└── .github/workflows/  backend CI (Linux + Windows quality gate)
```

**Current state: Phase 01 — Foundation & Repository: executed.**
The backend boots, the quality gate is green, and no business domain is
implemented (by design). Execution evidence:
[`docs/development/phase01Report.md`](docs/development/phase01Report.md).

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | Django 6 · Django REST Framework |
| Database | Microsoft SQL Server (`mssql-django`, `pyodbc`) — SQLite dev/tests only |
| Auth | SimpleJWT *(reserved — Identity phase)* |
| Real-time | Django Channels · Redis · WebSocket *(later phases)* |
| Media | WebRTC (transport only — never through Django) *(later phases)* |
| Config | django-environ (`.env`, never committed) |
| Deployment | Waitress (Windows baseline) |
| Quality | Ruff · Ruff Format · Mypy · Django test runner · GitHub Actions |

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
Decision records: [`docs/adr/`](docs/adr/)
Current documentation review and open questions: [`docs/ANALYSIS.md`](docs/ANALYSIS.md)

---

## Development Setup

Windows (PowerShell):

```powershell
cd backend
.\scripts\setupEnvironment.ps1
```

Linux / macOS:

```bash
cd backend
bash scripts/setupEnvironment.sh
```

The scripts create `venv/`, install pinned dependencies
(`requirements/development.txt`) and copy `.env.example` → `.env` when missing.
The Python executable must come from the virtual environment.

## Environment Setup

`backend/.env.example` documents every configuration category
(APPLICATION · DJANGO/SECURITY · DATABASE · CORS · LOGGING · CACHE · EMAIL ·
STORAGE · JWT · EXTERNAL SERVICES). Copy it and fill local values:

```powershell
copy .env.example .env
```

Never commit `.env`. Secrets belong in environment variables or a secret
manager — never in source control. Production is fail-closed: missing
`SECRET_KEY`, `ALLOWED_HOSTS`, CSRF/CORS lists or SQL Server database
configuration abort startup (ADR-009/ADR-010).

## Running the Backend

```powershell
python manage.py check
python manage.py runserver
```

Health endpoints (Phase 01 §17):

- `GET /healthz/` — liveness (application only)
- `GET /readyz/` — readiness (application + database; 503 when degraded)

## Running Tests

```powershell
python manage.py test --settings=config.settings.testing
```

## Quality Checks

```powershell
python manage.py check --settings=config.settings.testing
python manage.py makemigrations --check --settings=config.settings.testing
python manage.py test --settings=config.settings.testing
ruff check .
ruff format --check .
mypy config apps tests
```

Or all at once: `.\scripts\verifyQuality.ps1` / `bash scripts/verifyQuality.sh`.
CI runs the same gate on Linux **and** Windows
(`.github/workflows/backendCi.yml`). A green quality gate is part of the
Definition of Done.

---

## Naming Conventions

| Scope | Convention |
|---|---|
| Python functions / variables / files | `camelCase` |
| Private helper prefix | `_camelCase` |
| Python classes | `PascalCase` |
| Framework constants (Django) | `UPPER_SNAKE_CASE` |
| Django apps | lowercase |
| Database tables / columns | `camelCase` |
| Documentation files | `PascalCase.md` or standardized uppercase |
| API routes | REST-oriented, versioned (`/api/v1/...`) |

Enforced by `backend/tests/architecture/testNamingConventions.py`.

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
