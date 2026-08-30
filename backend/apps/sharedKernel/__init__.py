"""Tekarai Shared Kernel — platform foundation (Phase 06).

Not a business bounded context: this package holds the cross-cutting
architecture pieces every context reuses — domain primitives (errors,
entities, events), application ports (unit of work, audit, authorization
gate), the standard API contract (envelope, exception mapping, pagination,
filtering, idempotency, rate limiting, OpenAPI), correlation/request-context
middleware and structured logging.

Dependency direction (docs/Phases/Phase6.md §3): every layer may depend on
this kernel; the kernel depends on nothing outward. Its `domain` and
`application` packages stay framework-free; only `presentation` and
`infrastructure` touch Django/DRF.
"""
