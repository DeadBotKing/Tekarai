# Tekarai Backend 0.13.0 — Phase 13 AI Platform

**Release date:** 2026-09-06  
**Gate:** `GATE_Z=GREEN — PHASE_13=COMPLETE`

## Highlights

- Provider-neutral AI Platform from Domain ports through production adapters.
- Tenant-aware request/response, prompt, context, memory, knowledge and RAG foundations.
- Usage, cost, quota, audit, governance, evaluation, feedback and observability.
- Durable asynchronous queue and worker.
- Governed tool registry/execution and versioned Agent foundation.
- Public `/api/v1/ai/` API for Agent registry, runs, approvals, jobs and readiness.
- Idempotent `AGENT_RUN` jobs with secret redaction and live permission re-check.
- Offline deterministic integration tests; no internet or API key required.

## Upgrade

1. Back up the database and secret store.
2. Configure `aiAgentDefaultProvider` and `aiAgentDefaultModel`.
3. Run `python manage.py migrate --plan`, then `python manage.py migrate`.
4. Run `python manage.py checkPhase13Release`.
5. Deploy the API and at least one `python manage.py runAiWorker` process.
6. Monitor AI job depth, failures, audit-chain verification and provider health.

No new migration was introduced by Z; the final Phase 13 schema migration is
`ai.0012_agentPlatform`.

## Compatibility

The REST surface is additive under `/api/v1/ai/`. Existing Phase 1–12 URLs are
unchanged. The queue vocabulary adds `AGENT_RUN`; existing job kinds and persisted
rows remain compatible.

## Known pre-existing debt

The repository-wide test suite contains six pre-existing architecture/naming failures,
plus 293 Ruff and 583 Mypy findings at pristine HEAD. Phase 13-Z adds zero findings and
no new test failure. See the Z execution report for measured evidence.

## Security notes

- The deterministic provider is disabled by default outside testing.
- Readiness output contains provider names and booleans, never credentials.
- Job API omits payloads.
- Async input is scrubbed before persistence.
- Worker authorization is checked at execution time.
