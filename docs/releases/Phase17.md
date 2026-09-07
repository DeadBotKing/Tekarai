# Tekarai 0.17.0 — Phase 17

Phase 17 introduces the Project Intelligence Platform as a Clean Architecture bounded context.

## Delivered

- Read-only secure workspace boundary and immutable reproducible snapshots.
- Filesystem, language, framework, dependency, architecture, Git, test, documentation and configuration analyzers through a plugin registry.
- Internal/external dependencies, cycles, high coupling, possibly unused packages, layers, violations, symbols, test/documentation/configuration evidence and Git activity/hot files.
- Snapshot comparison, rename detection, affected-file analysis, selective hash/content reuse and analyzer-specific immutable cache fingerprints.
- Versioned knowledge and graph nodes/edges; explained health and technical-debt evidence.
- Evidence-mandatory insights, recommendations and deterministic triage decisions.
- Budgeted task context, secret exclusion, project resume and a tenant-bound Agent context application contract.
- 21 tenant-scoped tables, immutable artifact storage, audit/event history, idempotent async jobs, retry/error isolation and full management API.
- Version bump from 0.16.0 to 0.17.0.

AI remains optional and is never the source of truth; actual project state plus deterministic analyzers remains authoritative.
