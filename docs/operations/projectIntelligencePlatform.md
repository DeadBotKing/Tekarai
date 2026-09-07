# Project Intelligence Operations Runbook

## Configuration

- `projectIntelligenceWorkspaceRoot`: the only filesystem root visible to scanners. Mount read-only in production.
- `projectIntelligenceMaxFiles` (default 50000) and `projectIntelligenceMaxFileBytes` (default 2000000).
- `projectIntelligenceCacheTtlSeconds` (default 86400).
- Artifact root defaults to `backend/var/projectIntelligenceArtifacts`; use durable encrypted object storage through the storage port in clustered production.
- Queue: `project-intelligence.analysis`; Celery task: `projectIntelligence.processJob`.

Start a dedicated worker:

```bash
celery -A config worker -l INFO -Q project-intelligence.analysis
```

A single job can be recovered with:

```bash
python manage.py runIntelligenceJob <job-uuid>
```

## Security controls

The worker and web process need read-only project mounts and write access only to the artifact namespace. The scanner rejects absolute/drive/parent paths, escaping symlinks, `.git`, virtual environments, caches, dependency/build trees, generated artifacts and secret-named files. Git commands are read-only, time-bounded and run with a minimal environment. Never grant shell or project-write capability to an analyzer.

Each project UUID is bound to its original normalized workspace. Authorization is action- and tenant-based. SQL queries include `tenantId`; object IDs alone never authorize access. Use separate database/object-storage credentials per environment, encryption at rest, malware controls and centralized secret injection.

## Processing and recovery

Jobs are idempotent by tenant/project/idempotency key, claimed atomically and dispatched after transaction commit. Transient `OSError` failures requeue with retry count and Celery exponential backoff; permanent failures become terminal, set project state to `ERROR`, append audit/event evidence and retain no raw exception secrets. Re-run with the same key only to inspect the original job; use a new key after remediation.

Analyzer failures are isolated. A subset failure produces `PARTIAL`, while successful findings continue through knowledge generation. All-analyzer failure produces `FAILED`. Cached results are keyed by tenant, relevant input fingerprint, analyzer semantic version and configuration; changing source code does not invalidate unrelated documentation results.

## Integrity and backup

Back up SQL and snapshot artifacts as one recovery set. Verify `artifactChecksum == snapshotHash` and storage bytes before restore or reuse. Append-only records must never be edited; corrections create a new snapshot/version. Restore order: SQL, immutable artifacts, verify hashes, start workers, enqueue fresh analysis if cache is absent.

## Monitoring

Alert on job queue age, terminal/retry rate, scan/analysis duration, files scanned/changed, analyzer failures, artifact verification failure, dependency cycles, architecture violations, insight/recommendation count and context duration. Investigate sudden file-count growth as an ignore-rule or workspace-mount regression.

## Capacity and retention

Use file count/byte limits, worker CPU/memory/time limits and queue concurrency. Large files are hashed but not content-parsed. Retain snapshots and linked analysis/knowledge/context according to audit policy; delete only through an approved tenant-retention workflow that preserves chain consistency. Cache may be expired independently.
