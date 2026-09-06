# Tekarai AI Platform — Phase 13 (A–Z complete)

Provider-agnostic, Tenant-scoped AI foundation with strict Domain/Application/
Infrastructure/Presentation boundaries.

Implemented capabilities include provider/model/capability registries, request and
response lifecycle, prompt versioning, context and authorization, provider adapters,
retry/fallback, usage/cost/quota, audit/governance, durable jobs, embeddings,
knowledge ingestion, RAG, memory, evaluation, feedback, observability, governed tool
execution and versioned agents.

## Public API

The Phase 13-Z API is mounted at `/api/v1/ai/` and exposes:

- versioned agent registry and lifecycle;
- synchronous and idempotent asynchronous runs;
- run/step trace reads;
- human and dual-control approval queues;
- safe job status/cancellation (job payload is never returned);
- non-secret release readiness.

See `docs/Phases/Phase13/Phase13-Z.md` for routes, permissions, deployment and
rollback details.

## Operations

```bash
python manage.py runAiWorker
python manage.py checkPhase13Release
```

Production is fail-closed until `aiAgentDefaultProvider` and
`aiAgentDefaultModel` select an explicitly configured adapter. The deterministic
provider is opt-in and enabled by testing settings only.
