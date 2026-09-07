# Self-Learning Platform API — Phase 16

Base path: `/api/v1/learning/`

All tenant and actor identity comes from the authenticated bearer/API-key context. IDs supplied by clients are always re-scoped by repository queries. Successful responses use the standard Tekarai success envelope.

## Permissions

| Permission | Scope |
|---|---|
| `learning.view` | List/read tenant learning resources and metrics |
| `learning.observe` | Append immutable operational experiences |
| `learning.manage` | Dataset, experiment, evaluation and validation management |
| `learning.run` | Queue asynchronous experiment jobs |
| `learning.approve` | Human approve/reject decisions |
| `learning.deploy` | Canary deployment and rollback |
| `learning.feedback` | Sourced human/system/business feedback |
| `learning.monitor` | Production metric ingestion and drift detection |

Creators cannot approve their own artifacts. Validation, approval and deployment permissions are intentionally separate.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `experiences/` | List or append immutable traced experience |
| GET/POST | `datasets/` | List or create semantic-versioned dataset |
| POST | `datasets/{id}/build/` | Add sourced samples and compute deterministic dataset hash |
| POST | `datasets/{id}/validate/` | Validate sample threshold and approve dataset |
| GET/POST | `experiments/` | List or create experiment against an approved dataset version |
| POST | `experiments/{id}/run/` | Create idempotent durable job; returns `202` |
| GET | `jobs/{id}/` | Read durable job/run outcome |
| GET | `artifacts/` | List immutable artifact versions |
| GET | `artifacts/{id}/` | Read artifact metadata/checksum/state |
| POST | `artifacts/{id}/evaluate/` | Evaluate candidate and baseline comparison |
| POST | `artifacts/{id}/validate/` | Apply performance/regression/safety/resource/business gates |
| POST | `artifacts/{id}/approve/` | Human approval with reason |
| POST | `artifacts/{id}/reject/` | Human rejection with reason |
| POST | `artifacts/{id}/deploy/` | Start/advance 5→25→50→100 canary |
| POST | `artifacts/{id}/rollback/` | Restore prior stable deployment with reason |
| GET | `deployments/` | Deployment history |
| GET/POST | `metrics/` | Summary or append observed artifact/deployment metrics |
| POST | `drift/` | Data/concept/prediction/performance drift check |
| POST | `feedback/` | Append sourced feedback |

## Lifecycle rules

1. A sample must reference an experience from the same tenant.
2. An experiment requires an `APPROVED` dataset and freezes version/hash/configuration/seed/code/environment data in its run.
3. Running is asynchronous and requires an idempotency key of at least eight characters.
4. An artifact is generated only by a successful run and is stored by immutable checksum URI.
5. Evaluation precedes validation. Validation checks absolute thresholds, baseline regressions, artifact integrity, reproducibility, safety, data leakage, compatibility, latency, resource usage and business constraints.
6. Approval requires passed validation and a reviewer distinct from the artifact creator.
7. Production starts at 5%. Every subsequent canary stage requires observed metrics. Stages cannot be skipped.
8. At 100%, the prior deployment becomes `SUPERSEDED` but remains available. Rollback deactivates the candidate and restores that stable version.

## Validation policy example

```json
{
  "policy": {
    "minimums": {"accuracy": 0.82, "f1": 0.80},
    "maximums": {"latencyMs": 150, "errorRate": 0.05},
    "maximumRegression": {"accuracy": 0.01, "latencyMs": 20},
    "safetyPassed": true,
    "dataLeakagePassed": true,
    "compatibilityPassed": true,
    "resourceUsagePassed": true,
    "businessConstraintsPassed": true
  }
}
```

The exact policy snapshot and reproducibility hash are persisted with each validation.

## Error semantics

- `401`: no valid principal
- `403`: action permission denied
- `404`: resource is absent in the current tenant (cross-tenant IDs have the same result)
- `409`: invalid lifecycle transition, reused idempotency key, immutable version/checksum conflict, failed canary gate
- `422`: invalid input, missing source, secret-bearing metadata, invalid semantic version or metric
- `429`: scoped rate policy exceeded
