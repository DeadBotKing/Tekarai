# Tekarai --- Handoff

## Start Here

You are taking over development of Tekarai.

Assume:

> The previous implementation has been lost.

Do not assume previous source code, migrations, database tables, models,
APIs, or configuration exist.

Your job is to rebuild Tekarai from zero according to the project
documents.

## Mandatory Reading Order

Read these files in this order:

1.  `TekaraiMasterImplementationSpecification.md`
2.  `ArchitectureHandoff.md`
3.  `DataFlowDocumentation.md`
4.  `DevelopmentRules.md`
5.  `ExecutionGuide.md`

Then inspect the repository.

## Product

Tekarai is a general-purpose Enterprise Operations Platform.

Original reference environment:

``` text
Pharmaceutical manufacturing / Ronak
```

But Tekarai itself must remain industry-neutral.

## Current State

The correct starting assumption is:

``` text
Previous implementation unavailable
Current implementation = zero
```

Rebuild cleanly.

## Required Architectural Stack

``` text
DDD
Clean Architecture
SOLID
Modular Monolith
API First
Event Driven
Security First
AI Native
Cloud Ready
Offline Ready
```

Backend:

``` text
Python 3.12
Django 6
Django REST Framework
SQL Server
mssql-django
SimpleJWT
```

## First Mission

Do not start by creating random domain models.

First create:

``` text
Repository
Documentation
Backend Bootstrap
Settings
Database Connection
Core
Identity
Organization
```

Then proceed according to the implementation phases.

## Agent Instructions

If you are an AI coding agent:

### You MUST

-   inspect the repository before editing
-   read the specification
-   understand current phase
-   preserve architecture
-   make complete changes
-   run verification
-   report evidence

### You MUST NOT

-   guess missing requirements
-   rewrite unrelated files
-   delete architecture documents
-   bypass tests
-   invent domain behavior
-   claim success without running checks
-   introduce placeholder production code

## Completion Reporting

At the end of each task report:

``` text
Task:
Phase:
Files Created:
Files Modified:
Files Deleted:
Architecture Decision:
Tests:
Migration Status:
Quality Checks:
Known Issues:
Next Task:
```

## If Something Is Wrong

Use:

``` text
Problem
→ Evidence
→ Root Cause
→ Proposed Solution
→ Architectural Impact
→ Implementation
→ Verification
```

Do not hide failures.

## Source of Truth

The hierarchy is:

``` text
Approved Architecture Decision Records
        ↓
TekaraiMasterImplementationSpecification.md
        ↓
Architecture / Data Flow / Development Rules
        ↓
Execution Guide
        ↓
Code
```

If code conflicts with the approved specification, the code is
considered wrong until the architecture is explicitly changed.

## Final Objective

Build Tekarai as a production-grade enterprise platform that can evolve
for 5--10+ years without requiring an architectural rewrite.

The goal is not merely to make the application run.

The goal is to build the correct platform.
