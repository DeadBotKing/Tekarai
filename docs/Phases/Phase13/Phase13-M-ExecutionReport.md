# Phase 13-M — Execution Report

**Sub-phase:** M — Fallback، Retry، Timeout و Error Boundary
**Contract:** [`Phase13-M.md`](Phase13-M.md)
**Date:** 2026-09-05
**Result:** ✅ COMPLETE — all acceptance gates GREEN

---

## 1. Scope Delivered

Phase 13-M turns the stable, classified error surface built by Phase 13-L into
a controlled resilience layer: configurable retry with deterministic backoff,
an ordered fallback chain (primary → secondary → … → local), a wall-clock
timeout budget, and a strict error boundary that converts any non-domain
failure into a classified, fatal AI domain error. The executor is a pure
domain service; time and sleeping arrive through injected ports; all tuning
is environment-driven per Master Specification §42.

## 2. Files Created

| File | Purpose |
|---|---|
| `backend/apps/ai/domain/services/providerResilience.py` | Pure domain service: `RetryPolicy`, `FallbackPolicy`, `AttemptRecord`, `ResilienceReport`, `ExecutionOutcome`, `ResilienceClock`/`ResilienceSleeper` ports (+ `MonotonicClock`/`RealSleeper`), `ResilientProviderExecutor` (retry/fallback/timeout-budget/error-boundary/report), `generateWithFallback`, `reportFromError`/`attachReport`, `errorCodeOf`. |
| `backend/apps/ai/infrastructure/providers/resilienceWiring.py` | Composition root for M: reads `settings.AI_RESILIENCE`, parses the fallback chain, validates the budget, builds policies and the executor (`buildResilientExecutor`, `fallbackStepsFor`). |
| `backend/tests/unit/testPhase13Resilience.py` | 22 offline deterministic unit tests (fake clock/sleeper, scripted providers). |
| `backend/tests/integration/testPhase13ResilienceContract.py` | 5 integration tests over a real localhost `ThreadingHTTPServer` replaying scripted failure sequences (503×2→200, 429→200, permanent 400, permanent 503). |

## 3. Files Modified

| File | Change |
|---|---|
| `backend/config/settings/base.py` | New `AI_RESILIENCE` block: `aiRetryMaxAttempts`, `aiRetryInitialBackoffSeconds`, `aiRetryBackoffMultiplier`, `aiRetryMaxBackoffSeconds`, `aiProviderTimeoutBudgetSeconds`, `aiProviderFallbackChain` — all environment-driven. |
| `backend/.env.example` | Documented all six resilience variables in the established camelCase style. |
| `docs/Phases/Phase13/README.md` | M marked complete; N is next; M contract + report linked. |
| `docs/Phases/Phase13.md` | Master index updated (A–M complete, N next). |

## 4. Behaviour Summary

1. **Retry (§44).** Only transient codes retry: `AI_REQUEST_TIMEOUT`,
   `AI_PROVIDER_UNAVAILABLE`, `AI_PROVIDER_RATE_LIMITED`. Everything else —
   model unavailability, output validation failures, permission/quota denials,
   and any non-`TekaraiError` — is fatal on the first attempt. Backoff is
   deterministic: `min(initial × multiplier^retryIndex, maxBackoff)`.
2. **Fallback (§25).** The chain walks primary → fallbacks → (local), one
   retry budget per step. An unresolvable fallback step is recorded `SKIPPED`
   and the chain continues; an unresolvable *primary* raises immediately as a
   configuration error — fallback never repairs configuration.
3. **Timeout budget (§42).** Before every attempt the elapsed wall-clock time
   is compared against `aiProviderTimeoutBudgetSeconds`; exceeding it raises
   `AIRequestTimeout` with the accumulated report attached.
4. **Error boundary.** Any exception that is not a `TekaraiError` is wrapped
   at the boundary into `AIProviderUnavailable` (fatal, `__cause__` preserved)
   — no vendor or framework exception crosses the AI domain.
5. **Reports.** Every terminal outcome carries a `ResilienceReport`
   (attempts, outcomes, error codes, backoff totals, fallback flag). Failed
   executions expose it via `reportFromError(exc)` (`exc.resilienceReport`).

## 5. Gates

| Gate | Result |
|---|---|
| Full backend test suite | ✅ **799 tests OK** (baseline 772 + 27 new) |
| New M unit tests | ✅ 22 OK |
| New M integration tests | ✅ 5 OK (real HTTP transport, request counting) |
| `manage.py check` | ✅ no issues |
| `makemigrations --check` | ✅ only the documented pre-existing Phase-9 `channelprofilemodel.conversationId` drift |
| Ruff (E4/E7/E9/F/I/B/UP) on all M files | ✅ clean |
| mypy (py312) on all M files | ✅ clean |
| Architecture guards | ✅ untouched and passing (vocabulary scan, hook allow-lists) |

## 6. Decisions

- **M-D1 — Reports travel on the exception.** Terminal failures attach a
  frozen `ResilienceReport` to the raised error (`exc.resilienceReport`).
  Callers and later observability work (W) read it with `reportFromError`;
  nothing is persisted yet (persistence belongs to P/Z).
- **M-D2 — Deterministic backoff, no jitter.** The contract fixes an exact
  geometric schedule so tests and operators can reason about timing without
  randomness. A jitter strategy is a future tuning knob, not a missing rule.
- **M-D3 — Fallback never overrides an explicit choice.** `fallbackStepsFor`
  returns steps *after* the requested provider in the configured chain; if the
  requested provider is not in the chain, callers must pass fallbacks
  explicitly. Configuration informs; the request decides.
- **M-D4 — SKIPPED, not fatal, for missing fallback steps.** A deactivated or
  unregistered secondary must not kill the chain; it is recorded and the
  walk continues. The primary remains fail-closed.
- **M-D5 — Budget is checked between attempts.** The executor does not abort a
  request in flight (no cancellation primitive exists in the stdlib
  transport); it prevents *starting* an attempt once the budget is gone.
- **M-D6 — Strict numeric parsing.** `numericSetting` distinguishes "absent"
  (default) from "explicit zero" (validated and rejected), so misconfiguration
  fails loudly instead of silently adopting a default.
- **M-D7 — Idempotency posture (§45).** Retries repeat the same operation;
  the eventual request/operation lifecycle carries one idempotency key across
  all attempts. Deduplication enforcement belongs to later sub-phases.

## 7. Known Debt (unchanged, disclosed in Phase 13-L)

Repository-wide ruff/mypy debt predates Phase 13-L/M and is intentionally not
fixed here; all files owned by M are lint/type clean. The Phase-9
`channelprofilemodel.conversationId` migration drift remains documented.

## 8. Next Gate

Sub-phase **N — Usage، Token، Latency، Cost و Quota**.
