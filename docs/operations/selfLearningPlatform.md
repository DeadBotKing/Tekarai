# Self-Learning Platform Operations Runbook

## Safety model

Phase 16 is a governed lifecycle, not autonomous production mutation:

`OBSERVE → COLLECT → DATASET → EXPERIMENT → LEARN → EVALUATE → VALIDATE → APPROVE → CANARY → MONITOR → ACTIVE`

A failed production gate follows:

`MONITOR → DETECT → ROLLBACK → RESTORE STABLE VERSION`

SQL stores lifecycle truth. Celery is execution transport. Artifact storage is immutable. No worker/provider state can bypass validation, approval, tenant scope or deployment state.

## Deployment

1. Back up SQL and artifact storage.
2. Deploy code with workers stopped.
3. Run `python manage.py migrate`.
4. Verify the 18 Phase 16 tables and immutable storage mount.
5. Start a dedicated training worker and monitoring worker.
6. Start one Celery beat scheduler.
7. Start API instances and execute a non-production canary smoke test.

```bash
celery -A config worker -l INFO -Q learning.training --concurrency=2
celery -A config worker -l INFO -Q learning.monitoring --concurrency=2
celery -A config beat -l INFO
```

Training concurrency should reflect CPU/GPU/memory limits. Never share unrestricted user code with a worker. The built-in deterministic engine executes no supplied code.

## Artifact storage

Local development uses `backend/var/learningArtifacts/{tenant}/{name}/{version}/{sha256}.artifact`. Production should bind the `ModelStorage` port to versioned object storage with:

- write-once/object-lock semantics;
- server-side encryption;
- tenant prefix isolation;
- checksum verification on evaluation/deployment;
- retention of superseded versions;
- independently tested restore.

Never overwrite or delete a stable artifact required by deployment history. Before any deployment, URI content must match the persisted SHA-256.

## Job recovery

Jobs contain identifiers only and are published after SQL commit. Worker execution creates an independent run containing dataset hash, code version, configuration, parameters, environment, dependency identity, random seed, timestamps, metrics and bounded logs.

- `QUEUED`: safe to republish if broker publication was interrupted.
- `RUNNING`: investigate worker heartbeat before intervention.
- `FAILED`: error code/message and run evidence are persisted; fix the cause and create/retry a governed run.
- `COMPLETED`: replay is idempotent and does not create another artifact.

Manual replay:

```bash
python manage.py runLearningJob JOB_UUID
```

Do not mutate run/job rows directly.

## Canary operation

A new production deployment must start at 5%, then move only to 25%, 50%, and 100%. Before each advancement:

1. ingest observed metrics tied to that deployment/artifact;
2. compare business and technical signals to the approved baseline;
3. verify error/latency/resource ceilings and minimum quality;
4. retain the gate evidence;
5. advance only if the gate passes.

At 100%, the previous deployment is marked `SUPERSEDED`, not deleted. A deployment snapshot preserves the previous pointer and candidate state.

## Rollback

Rollback requires `learning.deploy`, a non-empty reason, a current canary/active deployment and a prior stable deployment. The engine deactivates the candidate, reapplies the previous artifact at 100%, marks the candidate deployment/artifact rolled back, restores the previous artifact as active, emits `RollbackCompleted`, and writes both shared and learning audit evidence.

If automatic rollback infrastructure is unavailable, stop new traffic at the routing layer, run the authorized rollback API, verify the checksum of the restored artifact and confirm monitoring recovery.

## Drift and monitoring

Ingest finite metrics through `POST /api/v1/learning/metrics/`; deployment IDs must belong to the selected artifact in the same tenant. Drift compares observed and baseline values with relative thresholds for:

- DATA
- CONCEPT
- PREDICTION
- PERFORMANCE

Alert on:

- queue age/depth and missing worker heartbeats;
- failed jobs/runs and repeated retries;
- evaluation or validation failure growth;
- canary error/latency/resource regression;
- `DriftDetected` events;
- rollback count;
- artifact checksum failure;
- approval/deployment attempts denied by policy;
- unusual experience/feedback ingestion volume.

Metrics summary exposes average experiment/training/evaluation/deployment durations plus failure, rollback and drift counts.

## Security and privacy

- Metadata/input/context must be JSON-compatible, finite and bounded.
- Secret-like keys (password, token, API key, credential, private key) are rejected.
- Dataset samples require same-tenant source experiences.
- Feedback requires a real same-tenant experience, deployment or artifact.
- Repository queries include tenant scope.
- Normal members cannot evaluate, validate, approve or deploy.
- Training runs must consume approved datasets only.
- Audits and experiences have no delete API.

Apply data minimization before observation. Do not use protected/sensitive data for learning without an approved domain policy, purpose and retention basis.

## Backup and disaster recovery

Back up SQL and artifact object versions as a consistency pair. On restore:

1. restore SQL;
2. restore all artifact checksums referenced by non-archived deployments;
3. run checksum verification;
4. reconcile queued/running jobs;
5. verify the current active deployment pointer;
6. resume workers, then traffic.
