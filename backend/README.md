# Tekarai Backend

Django backend of the Tekarai Enterprise Operations Platform.
**Current state: Phase 01 — Foundation.** No business domains exist yet
(that is deliberate — see `docs/Phases/Phase1.md`).

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | Django 6 · Django REST Framework |
| Database | Microsoft SQL Server (`mssql-django`, `pyodbc`, ODBC Driver 18) |
| Configuration | django-environ (`.env`, never committed) |
| Serving (prod baseline) | Waitress (Windows) |
| Quality gate | Ruff · Ruff Format · Mypy · Django test runner |

SQLite is available for offline development and hermetic tests only
(`docs/adr/ADR-011.md`). Production accepts SQL Server exclusively.

## Layout (Phase 01)

```
backend/
├── manage.py
├── config/
│   ├── settings/          base · development · testing · production
│   ├── environment.py     env parsing + database config builder (unit-tested)
│   ├── healthCheck.py     /healthz/ (liveness) · /readyz/ (readiness: app+db)
│   ├── urls.py · wsgi.py · asgi.py
├── apps/                  EMPTY by design — business apps arrive per phase
├── tests/
│   ├── unit/              configuration parsing rules
│   ├── integration/       health endpoints over the Django test client
│   └── architecture/      security policy · dependency rules · naming · hygiene
├── requirements/          base · development · testing · production (pinned)
├── scripts/               setup + quality gate (PowerShell & Bash)
├── docs/                  backend-level notes
├── .env.example           template with all mandatory categories
└── pyproject.toml         ruff + mypy + coverage configuration
```

## Development Setup

Windows (PowerShell, from `backend/`):

```powershell
.\scripts\setupEnvironment.ps1
```

Linux / macOS:

```bash
bash scripts/setupEnvironment.sh
```

The scripts create `venv/`, install pinned dependencies from
`requirements/development.txt`, and copy `.env.example` → `.env` when missing.
The Python executable must always come from the virtual environment.

## Environment Setup

Copy the template manually if you prefer:

```powershell
copy .env.example .env
```

Fill in local values. **Never commit `.env`.** Categories covered:
APPLICATION · DJANGO/SECURITY · DATABASE · CORS · LOGGING · CACHE · EMAIL ·
STORAGE · JWT (reserved) · EXTERNAL SERVICES (reserved).

## Running the Backend

```powershell
python manage.py check
python manage.py runserver
```

Health endpoints: `GET /healthz/` (liveness) and `GET /readyz/`
(readiness — application + database, 503 when degraded).

## Running Tests

```powershell
python manage.py test --settings=config.settings.testing
```

## Quality Checks (Definition of Done gate)

```powershell
python manage.py check --settings=config.settings.testing
python manage.py makemigrations --check --settings=config.settings.testing
python manage.py test --settings=config.settings.testing
ruff check .
ruff format --check .
mypy config apps tests
```

Or run everything at once: `.\scripts\verifyQuality.ps1`
(Linux: `bash scripts/verifyQuality.sh`).

## Naming Conventions (ADR-001)

- Functions/variables/files: `camelCase` (`buildDatabaseConfig`, `dbHost`)
- Classes: `PascalCase`
- Framework identifiers: untouched (`SECRET_KEY`, `INSTALLED_APPS`,
  `select_related`, `SET_NULL`, `is_staff`)
- Enforced by `tests/architecture/test_namingConventions.py`
