# Tekarai 0.16.0 — Self-Learning Platform

**Release date:** 2026-09-06  
**Specification:** `docs/Phases/Phase16.md`

## Delivered

- Independent `learning` bounded context following Tekarai Clean Architecture boundaries.
- Immutable traced experiences, semantic-versioned datasets and sourced samples.
- Reproducible experiments/runs with dataset hash, seed, code/configuration/environment/dependency identity.
- Immutable checksum-addressed artifacts and separate model/policy version records.
- Deterministic safe baseline learning/evaluation engines behind replaceable ports.
- Baseline comparison and validation gates for performance, regression, integrity, safety, leakage, compatibility, latency, resources and business constraints.
- Human approval/rejection with separation of duties.
- Versioned 5→25→50→100 canary deployment requiring metrics at every advancement.
- Stable-version snapshots and audited rollback.
- Human/system/business feedback and basic data/concept/prediction/performance drift detection.
- Durable idempotent Celery jobs, SQL-backed runs/errors and dedicated training/monitoring queues.
- Learning events, metrics and immutable hash-bearing audit evidence.
- Tenant-scoped repositories, action permissions, API rate policies and secret-bearing payload rejection.
- 18-table reversible migration, complete API, tests and operations documentation.

## Migration

```bash
cd backend
python manage.py migrate
```

Migration: `learning.0001_initial`. It creates all Phase 16 tables and rolls back cleanly.

## Workers

```bash
celery -A config worker -l INFO -Q learning.training
celery -A config worker -l INFO -Q learning.monitoring
celery -A config beat -l INFO
```

## Compatibility

Phase 16 is additive. Existing Phase 1–15 APIs and schemas remain compatible. The learning platform references source identifiers without introducing ORM coupling to other bounded contexts.
