# backend/apps

Home of the bounded contexts (Django apps). **Empty by design until the
business phases open** (Phase 01 §23; Phase 02 §45).

## Standard context layout (Phase 02 — LayerArchitecture §5)

```
apps/<context>/
├── domain/            entities · valueObjects · aggregates · events ·
│                      services · repositories (contracts) · exceptions
├── application/       commands · queries · useCases · dto · services ·
│                      handlers · ports
├── infrastructure/    models (Django ORM) · repositories (impl) ·
│                      providers · migrations
└── presentation/      api/ (serializers · views · urls · permissions ·
                       schemas) · consumers · webhooks
```

Rules (docs/architecture/DependencyRules.md):

- Dependencies point inward; domain imports no framework (RULES A–D).
- Cross-context imports target only `apps/<other>/application` contracts
  (RULES E/F).
- Folders/files camelCase (ADR-001); enforced by
  `tests/architecture/testNamingConventions.py` and
  `tests/architecture/testArchitecturalRules.py`.

First contexts to arrive (Phase order): Platform Core → Identity →
Organization → People (per Execution Guide; the Phases roadmap reconciles in
its phases).
