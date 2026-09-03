# Meryx --- Development Rules

These rules are mandatory for every human developer and AI coding agent.

## 1. Before Coding

Always:

1.  Read `MERYX_MASTER_IMPLEMENTATION_SPECIFICATION.md`.
2.  Read `ARCHITECTURE_HANDOFF.md`.
3.  Read `DATA_FLOW_DOCUMENTATION.md`.
4.  Read this document.
5.  Read `EXECUTION_GUIDE.md`.
6.  Inspect the current repository.
7.  Identify the current implementation phase.
8.  Identify dependencies and acceptance criteria.

Never start coding based only on a ticket title.

## 2. Never Guess

If something is missing:

``` text
STOP
→ identify Open Question
→ document it
→ resolve it
→ continue
```

Do not invent domain behavior.

## 3. Code Quality

Required:

-   clear names
-   small cohesive modules
-   explicit types
-   testable functions
-   meaningful exceptions
-   deterministic behavior
-   documented public contracts

Avoid:

-   magic values
-   hidden global state
-   circular imports
-   giant modules
-   generic utils.py dumping grounds
-   duplicated business rules

## 4. Django Rules

Django is framework support.

Do not put complex domain behavior in:

``` text
views.py
serializers.py
admin.py
models.py
```

Django models represent persistence and may contain simple
persistence-oriented behavior, but core business decisions belong in
domain/application layers.

## 5. Model Rules

Every model must answer:

-   Which bounded context owns it?
-   Which aggregate owns it?
-   Is it tenant-scoped?
-   What is its lifecycle?
-   What is its deletion policy?
-   Which fields are immutable?
-   Which fields are unique?
-   Which indexes are required?
-   Which operations must be audited?

## 6. Service Rules

Do not create services merely to move code into another file.

A service must have a defined responsibility.

Good:

``` text
CreateProjectUseCase
ApproveDocumentUseCase
AssignTaskUseCase
```

Avoid:

``` text
CommonService
ManagerService
UniversalService
UtilsService
```

## 7. Repository Rules

Domain/application layers depend on repository interfaces.

Infrastructure implements them.

Example:

``` text
Domain:
    ProjectRepository

Infrastructure:
    DjangoProjectRepository
```

Do not make domain code depend on Django ORM QuerySets.

## 8. API Rules

Every endpoint must define:

-   authentication
-   authorization
-   request schema
-   response schema
-   errors
-   pagination where applicable
-   filtering where applicable
-   idempotency where applicable
-   audit implications

## 9. Database Rules

Never:

-   manually modify production schema without migration
-   delete migrations casually
-   rename columns without migration planning
-   create unbounded text fields without justification
-   add indexes without access-pattern reasoning

Migrations are source controlled.

## 10. Migration Rules

After model changes:

``` powershell
python manage.py makemigrations
python manage.py makemigrations --check
python manage.py migrate
python manage.py check
```

Migration files must be reviewed.

## 11. Testing Rules

Every feature must have tests.

At minimum:

``` text
happy path
validation failure
authorization failure
business rule failure
tenant isolation
important edge cases
```

## 12. Security Rules

Never:

-   commit secrets
-   log passwords/tokens
-   trust client tenant IDs
-   bypass permission checks
-   expose internal exceptions
-   allow arbitrary object access
-   return sensitive data without authorization

## 13. AI Rules

AI-generated code is not automatically trusted.

AI agents must:

1.  inspect files
2.  understand architecture
3.  implement the smallest correct change
4.  run tests
5.  run quality checks
6.  inspect failures
7.  fix them
8.  repeat until green

An agent must not rewrite unrelated code merely because it can.

## 14. Change Scope

Each change must have a defined scope.

Do not mix unrelated architectural changes in one task.

## 15. Git Rules

Commit logical units.

Examples:

``` text
feat(identity): establish tenant-aware user model
feat(tasks): implement task assignment use case
fix(workflow): prevent unauthorized approval transition
test(documents): add version lifecycle coverage
```

## 16. Definition of Done

A change is complete only when:

-   implementation exists
-   architecture is respected
-   tests pass
-   migration state is correct
-   security is verified
-   documentation is updated
-   quality gate is green

## 17. Forbidden Shortcuts

Never use:

``` text
TODO: implement later
pass
raise NotImplementedError
fake repository
fake API
temporary database logic
hard-coded customer rules
```

unless the specification explicitly defines an abstract extension point
and the code is intentionally an interface/contract.

## 18. Documentation Rule

When behavior changes, update:

-   relevant domain documentation
-   API documentation
-   data flow documentation
-   ADR if architecture changes
-   changelog

## 19. AI Agent Rule

An AI agent must never claim success without evidence.

Good completion report:

``` text
Implemented X.

Verified:
- manage.py check: PASS
- migration check: PASS
- tests: PASS
- architecture dependency review: PASS
```

## 20. Final Rule

When in doubt:

``` text
Protect the architecture first.
Protect data integrity second.
Protect security third.
Then optimize developer convenience.
```
