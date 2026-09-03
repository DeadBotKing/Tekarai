# docs/architecture

**Status:** Phase 02 deliverable — authoritative architecture set.

| Document | Content |
|---|---|
| `SystemArchitecture.md` | system context & container diagrams, 20 principles, cross-cutting concerns, client/offline/configuration architecture |
| `LayerArchitecture.md` | layer diagram & responsibilities, API request flow, transaction boundary, sync/async, DB access & Django usage rules |
| `ModuleArchitecture.md` | module boundary diagram, boundary rules, **architecture matrix** (16 modules), cross-domain communication |
| `DependencyRules.md` | dependency diagram, **dependency matrix**, layer import rules, **RULES A–N** with enforcement mapping |
| `SecurityArchitecture.md` | security layers, authentication/authorization flow diagram, defense-in-depth |
| `MultiTenancyArchitecture.md` | tenant isolation diagram, tenancy model, isolation per layer, test strategy |
| `EventArchitecture.md` | event taxonomy (domain/application/integration), event flow diagram, contract requirements |
| `IntegrationArchitecture.md` | integration flow diagram, adapter rules, connector categories |
| `AIArchitecture.md` | AI architecture diagram, port/adapter rule, authorization & output classification |
| `ExtensionArchitecture.md` | extension types & diagram, stability tiers, review gate |
| `ObservabilityArchitecture.md` | logging/metrics/tracing/health pillars, correlation IDs, audit architecture |
| `StorageArchitecture.md` | StoragePort diagram & rules, cache architecture |

**Phase 03 — Domain Architecture set:**

| Document | Content |
|---|---|
| `DomainArchitecture.md` | umbrella: principles, classification, concept rules, boundaries, industry strategy, Phase-4 ERD conversion, microservice extraction path |
| `BoundedContexts.md` | the 20 bounded contexts: responsibilities, ownership, guardrails, module map |
| `DomainMap.md` | domain map diagram, classification table, at-a-glance ownership |
| `DomainDependencies.md` | dependency rule, graph, context-granularity dependency matrix, TBD list, extraction path |
| `AggregateCatalog.md` | aggregate rules, PerformanceEvaluation worked example, catalog per context with invariants |
| `DomainEvents.md` | event envelope (8 mandatory fields), naming/versioning, catalogue, cross-domain flow |
| `ValueObjectCatalog.md` | shared + per-context value objects with invariants |
| `DomainRules.md` | the 15 domain architecture rules + concept/boundary summaries |

Diagrams are Mermaid (version-control friendly, render on GitHub).
Decisions behind these documents: `../adr/`.
