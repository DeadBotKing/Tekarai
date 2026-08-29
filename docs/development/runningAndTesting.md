# Tekarai — Running & Testing Guide (Phase 01–03 state)

Step-by-step for Windows (PowerShell) and Linux/macOS. Current project
state: foundation backend (Phase 01) + architecture documentation
(Phase 02/03). No business domains exist yet — by design.

---

## 1. Prerequisites

- **Python 3.12+** (project baseline; 3.12 pinned in CI)
- Windows: `py -3.12` launcher installed — or Linux/macOS: `python3.12`
- Git
- No SQL Server needed for local dev/tests (SQLite dev/test exception,
  ADR-011). Production requires SQL Server + ODBC Driver 18.

## 2. One-time setup

### Windows (PowerShell)

```powershell
git clone https://github.com/DeadBotKing/Tekarai.git
cd Tekarai\backend
.\scripts\setupEnvironment.ps1
```

### Linux / macOS

```bash
git clone https://github.com/DeadBotKing/Tekarai.git
cd Tekarai/backend
bash scripts/setupEnvironment.sh
```

What the script does (same steps manually, if you prefer):

```powershell
cd backend
py -3.12 -m venv venv                  # python3.12 -m venv venv  (Linux)
.\venv\Scripts\Activate.ps1            # source venv/bin/activate  (Linux)
python -m pip install --upgrade pip
python -m pip install -r requirements\development.txt   # requirements/development.txt on Linux
copy .env.example .env                 # cp .env.example .env
```

`.env` stays local — it is git-ignored (verified by architecture tests).

## 3. Run the backend

```powershell
python manage.py check          # must print: no issues
python manage.py runserver      # http://127.0.0.1:8000
```

Verify health endpoints:

| URL | Meaning | Expected |
|---|---|---|
| `GET /healthz/` | liveness (application only) | 200 `{"status":"ok","phase":"01-foundation",...}` |
| `GET /readyz/` | readiness (application + database) | 200 with `database.status = "ok"` and latency |

(With default dev settings the database is SQLite (`db.sqlite3`), created
automatically on first database use.)

## 4. Run the tests

```powershell
python manage.py test --settings=config.settings.testing
```

Expected: `Ran 92 tests ... OK` (63 Phase-01 + 13 Phase-02 + 16 Phase-03
architecture tests).

Run one suite only:

```powershell
python manage.py test tests.unit --settings=config.settings.testing
python manage.py test tests.integration --settings=config.settings.testing
python manage.py test tests.architecture --settings=config.settings.testing
```

## 5. Full quality gate (Definition of Done)

All at once:

```powershell
.\scripts\verifyQuality.ps1          # bash scripts/verifyQuality.sh (Linux)
```

Or step by step:

```powershell
python manage.py check --settings=config.settings.testing
python manage.py makemigrations --check --settings=config.settings.testing
python manage.py test --settings=config.settings.testing
ruff check .
ruff format --check .
mypy config apps tests
```

All six must pass — the same gate runs in CI (`.github/workflows/backendCi.yml`)
on Ubuntu **and** Windows.

## 6. Testing against SQL Server (optional, production-like)

1. Install **ODBC Driver 18 for SQL Server** on your machine.
2. Edit `backend/.env`:

   ```ini
   dbEngine=mssql
   dbHost=your-server
   dbPort=1433
   dbName=TekaraiCore
   dbUser=tekarai
   dbPassword=your-password
   ```

3. `python manage.py check` → connectivity is validated when the DB is
   first used; production settings additionally enforce the mssql-only rule
   (`config.settings.production` rejects everything else at import).

## 7. Configuration reference

All categories with defaults and placeholders: `backend/.env.example`
(APPLICATION · DJANGO/SECURITY · DATABASE · CORS · LOGGING · CACHE · EMAIL ·
STORAGE · JWT · EXTERNAL SERVICES). Naming: framework keys keep
UPPER_SNAKE_CASE; project keys are camelCase (ADR-001/011).

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `Couldn't import Django` | venv not activated — `.\venv\Scripts\Activate.ps1` / `source venv/bin/activate` |
| `Unsupported dbEngine` | typo in `.env` — only `mssql` and `sqlite` allowed |
| PowerShell blocks scripts | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` or `powershell -ExecutionPolicy Bypass -File .\scripts\setupEnvironment.ps1` |
| ODBC driver error (mssql) | install ODBC Driver 18; or stay on `dbEngine=sqlite` for dev |
| Port 8000 busy | `python manage.py runserver 8010` |
| Tests fail on git checks | run from a real git clone (architecture tests call `git check-ignore`) |
| `testNoViewsOrSerializersExistYet` lists `venv/site-packages` paths | fixed in the Phase-03 hotfix (test now excludes `venv/`, `site-packages`, caches) — update your copy |
| `testRootGitignoreTxtRemnantIsGone` fails | a stale `.gitignore.txt` from an older copy sits next to `.gitignore` — delete it: `Remove-Item ..\.gitignore.txt` (from `backend/`), then re-run tests |
| WARNING/ERROR log lines during tests (`Method Not Allowed`, `Service Unavailable`) | **expected** — negative tests deliberately send bad requests (405) and simulate database-down (503); not failures |
