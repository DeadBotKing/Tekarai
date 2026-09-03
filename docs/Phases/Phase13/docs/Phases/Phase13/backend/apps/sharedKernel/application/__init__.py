"""Application layer of the shared kernel (framework-free).

Command/Query message bases (Phase 06 §5–§7), the request context that
carries correlationId/actor/tenant through the whole flow (§25), the UseCase
template implementing the eight canonical steps (§8) with the transaction
boundary in the application layer (§9), and the ports the outside world
implements (§10) — unit of work, audit recorder, event dispatcher,
authorization gate, session verifier, idempotency store, rate limiter,
clock.
"""
