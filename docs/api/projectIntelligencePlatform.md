# Project Intelligence API — Phase 17

Base path: `/api/v1/projects/{projectId}/intelligence/`. All responses use the Tekarai success/error envelope, require a valid bearer session, derive `tenantId` and actor from trusted request context, and never accept either identity from payloads.

## Permissions

| Action | Required permission |
|---|---|
| Read overview/state/architecture/dependencies/insights/recommendations/context/resume/changes, compare, job | `projectIntelligence.view` |
| Create immutable snapshot | `projectIntelligence.manage` |
| Queue full/incremental analysis | `projectIntelligence.analyze` |
| Build task context | `projectIntelligence.context` |

Project IDs are tenant-scoped and permanently bound to their first normalized workspace. Workspace paths are relative to `PROJECT_INTELLIGENCE_WORKSPACE_ROOT`; absolute paths, drive paths, parent traversal and escaping symlinks are rejected.

## Endpoints

- `GET /projects/{id}/intelligence/` — current state, architecture, knowledge, insights, recommendations, context and resume.
- `POST .../snapshot/` — body `{ "workspace": "relative/path" }`; creates or idempotently returns an immutable snapshot.
- `POST .../analyze/` — body `{ "workspace", "idempotencyKey", "priority" }`; returns `202` job.
- `POST .../reanalyze/` — same contract; enables incremental fingerprints and selective analyzer cache reuse.
- `GET .../state/`
- `GET .../architecture/`
- `GET .../dependencies/`
- `GET .../insights/`
- `GET .../recommendations/`
- `GET .../context/`
- `POST .../context/build/` — `{ "task": "...", "tokenBudget": 4000 }`, 256–100000 tokens.
- `GET .../resume/`
- `GET .../changes/`
- `POST .../compare/` — `{ "fromSnapshotId", "toSnapshotId?" }`; omitted target means latest.
- `GET /project-intelligence/jobs/{jobId}/`

## Lifecycle and integrity

`PROJECT → SNAPSHOT → OBSERVATION → ANALYSIS → KNOWLEDGE → INSIGHT → RECOMMENDATION → DECISION → CONTEXT`.

Snapshots, analyses, knowledge, graph records, insights, recommendations, decisions, contexts, changes and resumes are append-only/versioned. Snapshot artifacts use SHA-256, immutable tenant/project partitions and integrity verification before incremental reuse. Analyzer results include name, semantic version, status, timestamp, findings, metrics, isolated errors, metadata and deterministic hash.

## Errors

- `401` unauthenticated; `403` missing action permission.
- `404` tenant-scoped snapshot/job not found.
- `409` project/workspace rebinding, missing prerequisite or integrity conflict.
- `422` invalid UUID/path/budget/priority/payload.
- `429` rate limit exceeded.

Secrets and secret-named files are never placed in analyzer content or agent context. Analyzer exception messages are not exposed or persisted verbatim.
