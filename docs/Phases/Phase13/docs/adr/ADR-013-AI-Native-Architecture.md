# ADR-013 — AI Native Architecture

**Status:** ACCEPTED
**Date:** 2026-08-29
**Phase:** 02 — Architecture & ADRs
**Phase-2 reference:** required ADR "AI Native Architecture"

## Context

AI is a platform capability in Tekarai (project/performance/equipment
analysis, meeting summaries, task extraction, letters, KPI analysis,
predictions, knowledge graph). Domains must be able to use AI without any
domain coupling to a specific model vendor, and AI must never bypass
authorization or silently mutate business records (Master Specification §19,
Phase 02 §28).

## Decision

1. Every AI usage follows the port/adapter shape:
   `AI Capability → AI Port → Provider Adapter` (OpenAI / local model / other
   providers are interchangeable configuration, never hard-coded).
2. AI is accessed through **application-level capabilities** — a use case
   calls an AI application service; domain entities never call providers.
3. **Authorization applies before inference:** the context builder feeds the
   model only data the requesting principal is authorized to use (RAG
   retrieval is permission-filtered before context assembly).
4. **Output classification is mandatory:** every AI result is labelled
   advisory / draft / automated / authoritative. Authoritative business
   changes require explicit business rules and authorization (AI governance).
5. AI providers, prompts (versioned), model configuration and inference
   execution are separate architectural concerns (detailed in Phase 13;
   self-learning in Phase 16; code intelligence in Phase 17).

## Alternatives

- **Direct provider SDK calls inside domains** — rejected: vendor lock-in,
  untestable, bypasses authorization.
- **AI as an external microservice from day one** — deferred: premature; the
  modular monolith exposes AI as an internal capability first.
- **AI output written directly to business tables** — rejected: no audit, no
  accountability; classification + authorization are mandatory.

## Consequences

- Positive: provider freedom (incl. offline/local models), testable AI use
  cases, governance-ready audit trail.
- Negative: prompt versioning, evaluation and cost management become managed
  artefacts (Phase 13/16 carry that cost).
- `docs/architecture/AIArchitecture.md` is the binding architecture detail.
