PHASE 17 — PROJECT INTELLIGENCE PLATFORM

MERYX IMPLEMENTATION SPECIFICATION



============================================================

1\. هدف فاز

============================================================



هدف Phase 17 ساخت Project Intelligence Platform در Meryx است.



Project Intelligence مسئول ایجاد قابلیت درک، تحلیل و شناخت

ساختار، وضعیت، وابستگی‌ها، تغییرات و رفتار پروژه‌های تحت مدیریت

Meryx است.



این Platform باید بتواند یک Project را از دید فنی و عملیاتی

مشاهده و تحلیل کند و از اطلاعات آن یک تصویر ساختاریافته و قابل

استفاده برای سایر بخش‌های Meryx تولید کند.



Project Intelligence باید بتواند:



\- Workspace پروژه را شناسایی کند.

\- ساختار فایل‌ها و Directoryها را تحلیل کند.

\- زبان‌های برنامه‌نویسی را تشخیص دهد.

\- Frameworkها را شناسایی کند.

\- Dependencyها را استخراج کند.

\- Git History را تحلیل کند.

\- تغییرات پروژه را تشخیص دهد.

\- وضعیت فعلی پروژه را Snapshot کند.

\- معماری پروژه را تحلیل کند.

\- روابط بین Moduleها را استخراج کند.

\- مشکلات معماری را شناسایی کند.

\- Technical Debt را شناسایی کند.

\- Project Knowledge تولید کند.

\- Context قابل استفاده برای Agentها تولید کند.

\- Recommendation تولید کند.

\- Insight تولید کند.

\- Decision Support ایجاد کند.

\- وضعیت پروژه را در طول زمان دنبال کند.



Project Intelligence نباید فقط یک File Scanner باشد.



باید یک سیستم مستقل برای:



OBSERVATION

→ ANALYSIS

→ KNOWLEDGE

→ INSIGHT

→ RECOMMENDATION

→ DECISION SUPPORT



باشد.





============================================================

2\. جایگاه Project Intelligence در معماری Meryx

============================================================



Project Intelligence یک Platform مستقل در Meryx است.



ساختار مفهومی:



Core

&#x20;   ↓

Domain

&#x20;   ↓

Application

&#x20;   ↓

Platform

&#x20;   ↓

Project Intelligence

&#x20;   ↓

Projects / Agents / AI / Dashboard / Reporting





Project Intelligence نباید مستقیماً به:



\- Django Views

\- REST API

\- Frontend

\- Admin

\- HTTP Request

\- ORM



وابسته شود.



Infrastructure باید جزئیات File System، Git، Parserها،

Database و سایر ابزارهای خارجی را پیاده‌سازی کند.





============================================================

3\. اصل اساسی

============================================================



Project Intelligence باید بر اساس اصول زیر ساخته شود:



\- Clean Architecture

\- Domain-Driven Design

\- Dependency Inversion

\- Explicit Boundaries

\- Immutable Snapshots

\- Versioning

\- Reproducibility

\- Explainability

\- Auditability

\- Incremental Analysis

\- Deterministic Processing

\- Tenant Isolation





============================================================

4\. معماری منطقی

============================================================



Project Intelligence باید Pipeline زیر را داشته باشد:



PROJECT

&#x20;   ↓

SNAPSHOT

&#x20;   ↓

OBSERVATION

&#x20;   ↓

ANALYSIS

&#x20;   ↓

KNOWLEDGE BUILDING

&#x20;   ↓

INSIGHT ENGINE

&#x20;   ↓

RECOMMENDATION ENGINE

&#x20;   ↓

DECISION ENGINE

&#x20;   ↓

CONTEXT PACKAGE





ترتیب Pipeline نباید بدون دلیل تغییر کند.





============================================================

5\. مرحله Snapshot

============================================================



Snapshot نشان‌دهنده وضعیت پروژه در یک لحظه مشخص است.



Snapshot باید شامل:



\- Project ID

\- Tenant ID

\- Workspace

\- Timestamp

\- File Tree

\- File Metadata

\- Git State

\- Environment Information

\- Analysis Version

\- Snapshot Hash



باشد.



Snapshot باید قابل بازتولید و قابل مقایسه باشد.





============================================================

6\. File System Intelligence

============================================================



سیستم باید بتواند:



\- Directoryها را شناسایی کند.

\- Fileها را شناسایی کند.

\- File Type را تشخیص دهد.

\- File Size را ثبت کند.

\- Last Modified را ثبت کند.

\- Hash فایل را محاسبه کند.

\- فایل‌های Binary را تشخیص دهد.

\- فایل‌های Generated را تشخیص دهد.

\- فایل‌های Ignored را تشخیص دهد.

\- فایل‌های Temporary را تشخیص دهد.



فایل‌هایی مانند:



venv

\_\_pycache\_\_

.git

node\_modules

build

dist

coverage



نباید به صورت پیش‌فرض وارد تحلیل محتوایی شوند.





============================================================

7\. Language Detection

============================================================



Project Intelligence باید بتواند زبان‌های پروژه را تشخیص دهد.



مثال:



Python

JavaScript

TypeScript

HTML

CSS

SQL

PowerShell

C#

Java

Go



نتیجه باید شامل:



\- Language

\- File Count

\- LOC تقریبی

\- Percentage

\- Extensions



باشد.





============================================================

8\. Framework Detection

============================================================



سیستم باید Frameworkهای پروژه را شناسایی کند.



برای مثال:



Django

FastAPI

Flask

React

Next.js

Vue

Angular

.NET

Spring



Detection می‌تواند بر اساس:



\- Dependency

\- Configuration

\- Directory Structure

\- File Pattern

\- Import

\- Package Metadata



انجام شود.





============================================================

9\. Dependency Analysis

============================================================



Project Intelligence باید Dependency Graph ایجاد کند.



Graph باید روابط زیر را مشخص کند:



Project

&#x20;   ↓

Package

&#x20;   ↓

Module

&#x20;   ↓

File

&#x20;   ↓

Import





سیستم باید بتواند:



\- Dependency داخلی

\- Dependency خارجی

\- Circular Dependency

\- Unused Dependency

\- High Coupling

\- Dependency Direction



را تحلیل کند.





============================================================

10\. Architecture Analysis

============================================================



سیستم باید Architecture پروژه را بررسی کند.



موارد:



\- Layer Detection

\- Module Boundaries

\- Dependency Direction

\- Circular Dependency

\- Cross-layer Access

\- Architecture Violations

\- Coupling

\- Cohesion





مثال:



Presentation

&#x20;   ↓

Application

&#x20;   ↓

Domain

&#x20;   ↓

Infrastructure



اگر:



Domain

&#x20;   ↓

Presentation



باشد:



Architecture Violation





============================================================

11\. Git Intelligence

============================================================



Project Intelligence باید Git را تحلیل کند.



اطلاعات:



\- Current Branch

\- Current Commit

\- Commit Count

\- Modified Files

\- Added Files

\- Deleted Files

\- Renamed Files

\- Contributors

\- Recent Changes

\- Commit Frequency

\- Hot Files

\- Change Frequency





همچنین باید بتواند Change History را نگه دارد.





============================================================

12\. Change Detection

============================================================



سیستم باید بتواند Snapshotها را با یکدیگر مقایسه کند.



مثال:



Snapshot A

&#x20;   ↓

Snapshot B



نتیجه:



Added:

&#x20;   file\_a.py



Modified:

&#x20;   service.py



Deleted:

&#x20;   old\_service.py





============================================================

13\. Project Knowledge

============================================================



Project Knowledge اطلاعات ساختاریافته‌ای است که از Analysis

تولید می‌شود.



Knowledge می‌تواند شامل:



\- Project Structure

\- Modules

\- Dependencies

\- Frameworks

\- Architecture

\- Important Files

\- Entry Points

\- Configuration

\- Tests

\- Documentation

\- Git Information

\- Known Issues





باشد.





============================================================

14\. Knowledge Builder

============================================================



Knowledge Builder باید Analysis Resultها را به Knowledge تبدیل کند.



Pipeline:



Raw Observation

&#x20;   ↓

Analysis Result

&#x20;   ↓

Normalized Data

&#x20;   ↓

Knowledge

&#x20;   ↓

Knowledge Graph





Knowledge باید Version داشته باشد.





============================================================

15\. Knowledge Graph

============================================================



Project Intelligence باید بتواند در صورت نیاز Graph ایجاد کند.



Nodeها:



Project

Module

Package

File

Class

Function

Dependency

Framework

Configuration

Test





Edgeها:



IMPORTS

CONTAINS

DEPENDS\_ON

CALLS

IMPLEMENTS

TESTS

CONFIGURES

EXTENDS





============================================================

16\. Insight Engine

============================================================



Insight Engine باید از Knowledge، Insight تولید کند.



مثال:



\- Module X بسیار Coupled است.

\- File Y بیشترین تغییر را دارد.

\- Module Z تست کافی ندارد.

\- Dependency Circular وجود دارد.

\- Architecture Layer نقض شده است.





Insight باید دارای:



\- Severity

\- Confidence

\- Evidence

\- Source

\- Timestamp





باشد.





============================================================

17\. Insight Severity

============================================================



Severity:



INFO

LOW

MEDIUM

HIGH

CRITICAL





============================================================

18\. Recommendation Engine

============================================================



Recommendation Engine باید بر اساس Insightها پیشنهاد ارائه دهد.



مثال:



Insight:



High Coupling in Module A



Recommendation:



Split Module A into:



A.domain

A.application

A.infrastructure





Recommendation باید شامل:



\- Problem

\- Recommendation

\- Reason

\- Evidence

\- Expected Benefit

\- Risk

\- Priority





باشد.





============================================================

19\. Decision Engine

============================================================



Decision Engine باید بتواند Recommendationها را ارزیابی کند.



Decision می‌تواند:



ACCEPT

REJECT

DEFER

REVIEW\_REQUIRED





باشد.



Decision نباید بدون Evidence ساخته شود.





============================================================

20\. Agent Context Package

============================================================



یکی از مهم‌ترین خروجی‌های Project Intelligence:



Agent Context Package



است.



این Package باید اطلاعات لازم برای Agent را فراهم کند.



حداقل:



\- Project Overview

\- Project Tree

\- Architecture

\- Important Modules

\- Dependencies

\- Current State

\- Recent Changes

\- Known Issues

\- Constraints

\- Development Rules

\- Relevant Files

\- Relevant Symbols

\- Recommendations





============================================================

21\. Context Builder

============================================================



Context Builder باید Context را بر اساس Task بسازد.



ورودی:



Task



Project Knowledge



Workspace State



Architecture



History



نتیجه:



Task-specific Context





Context نباید کل Workspace را بدون دلیل وارد Prompt کند.





============================================================

22\. Context Budget

============================================================



Context Builder باید Token Budget داشته باشد.



اولویت:



1\. Directly Relevant Files

2\. Dependencies

3\. Architecture Rules

4\. Recent Changes

5\. Related Tests

6\. Documentation

7\. Secondary Context





============================================================

23\. Resume Generator

============================================================



Project Intelligence باید بتواند وضعیت پروژه را برای ادامه کار

تولید کند.



Resume باید شامل:



\- Current State

\- Completed Work

\- Current Problems

\- Pending Tasks

\- Architecture State

\- Recent Changes

\- Recommended Next Step





باشد.





============================================================

24\. Project State

============================================================



Project State باید وضعیت فعلی Project را نمایش دهد.



State:



INITIALIZING

SCANNING

ANALYZING

READY

CHANGED

STALE

ERROR





============================================================

25\. Incremental Analysis

============================================================



هر بار نباید کل Project از ابتدا تحلیل شود.



اگر فقط:



service.py



تغییر کرده باشد، سیستم باید بتواند فقط بخش‌های مرتبط را

دوباره تحلیل کند.



Flow:



Change Detection

&#x20;   ↓

Affected Files

&#x20;   ↓

Affected Modules

&#x20;   ↓

Affected Dependencies

&#x20;   ↓

Partial Re-analysis





============================================================

26\. Cache

============================================================



Analysis Resultهای Immutable باید Cache شوند.



Cache Key می‌تواند شامل:



\- File Hash

\- Analyzer Version

\- Configuration Version



باشد.





============================================================

27\. Analyzer Architecture

============================================================



Analyzerها باید Plugin-like باشند.



Interface:



Analyzer



هر Analyzer باید بتواند:



analyze(snapshot)



را اجرا کند.





Analyzerهای پایه:



FilesystemAnalyzer



LanguageAnalyzer



FrameworkAnalyzer



DependencyAnalyzer



ArchitectureAnalyzer



GitAnalyzer



TestAnalyzer



DocumentationAnalyzer



ConfigurationAnalyzer





============================================================

28\. Analyzer Result

============================================================



هر Analyzer باید Result استاندارد تولید کند.



Result شامل:



\- Analyzer Name

\- Analyzer Version

\- Status

\- Timestamp

\- Findings

\- Metrics

\- Errors

\- Metadata





باشد.





============================================================

29\. Error Isolation

============================================================



Failure یک Analyzer نباید کل Pipeline را نابود کند.



مثال:



GitAnalyzer FAILED



اما:



FilesystemAnalyzer

LanguageAnalyzer

DependencyAnalyzer



می‌توانند ادامه دهند.



Pipeline باید Failure را ثبت کند.





============================================================

30\. Orchestrator

============================================================



Project Intelligence Orchestrator مسئول اجرای Pipeline است.



وظایف:



\- Load Project

\- Create Snapshot

\- Execute Analyzers

\- Aggregate Results

\- Build Knowledge

\- Generate Insights

\- Generate Recommendations

\- Generate Decisions

\- Build Context

\- Persist Results





============================================================

31\. Application Use Cases

============================================================



Use Caseهای اصلی:



CreateProjectSnapshot



AnalyzeProject



AnalyzeChangedProject



BuildProjectKnowledge



GenerateProjectInsights



GenerateRecommendations



EvaluateRecommendations



BuildAgentContext



GenerateProjectResume



CompareSnapshots



GetProjectState



GetProjectArchitecture



GetProjectDependencies



GetProjectChanges





============================================================

32\. Repository Interfaces

============================================================



Interfaceهای مورد نیاز:



ProjectSnapshotRepository



ProjectAnalysisRepository



ProjectKnowledgeRepository



ProjectInsightRepository



ProjectRecommendationRepository



ProjectDecisionRepository



ProjectContextRepository



ProjectStateRepository





============================================================

33\. Storage

============================================================



Storage می‌تواند شامل:



Database

File Storage

Object Storage

Cache



باشد.



Raw Snapshot و Artifactهای بزرگ نباید بدون دلیل داخل جدول‌های

Relational ذخیره شوند.





============================================================

34\. Database Entities

============================================================



جداول مفهومی:



project\_snapshots



project\_files



project\_file\_hashes



project\_analyses



project\_analysis\_results



project\_dependencies



project\_architectures



project\_knowledge



project\_knowledge\_nodes



project\_knowledge\_edges



project\_insights



project\_recommendations



project\_decisions



project\_context\_packages



project\_states



project\_changes



project\_resume





============================================================

35\. Versioning

============================================================



موارد زیر باید Version داشته باشند:



Snapshot

Analyzer

Knowledge

Context Package

Recommendation

Decision





هیچ Snapshot قبلی نباید overwrite شود.





============================================================

36\. Multi-Tenancy

============================================================



تمام Project Intelligence Dataهای Tenant-specific باید:



tenant\_id



داشته باشند.



هیچ Tenant نباید:



\- Snapshot

\- Knowledge

\- Context

\- Insight

\- Recommendation



Tenant دیگر را ببیند.





============================================================

37\. Security

============================================================



دسترسی به Workspace باید کنترل شود.



Agent یا User فقط باید Projectهایی را ببیند که Permission دارد.



هیچ Analyzer نباید بتواند خارج از Workspace مجاز File بخواند.





============================================================

38\. Workspace Security

============================================================



Workspace Boundary الزامی است.



Analyzer نباید بتواند:



C:\\



یا:



Parent Directory



را بدون مجوز بخواند.



تمام Pathها باید Normalize و Validate شوند.





============================================================

39\. API

============================================================



Endpointهای مفهومی:



GET    /projects/{id}/intelligence/



POST   /projects/{id}/intelligence/snapshot/



POST   /projects/{id}/intelligence/analyze/



POST   /projects/{id}/intelligence/reanalyze/



GET    /projects/{id}/intelligence/state/



GET    /projects/{id}/intelligence/architecture/



GET    /projects/{id}/intelligence/dependencies/



GET    /projects/{id}/intelligence/insights/



GET    /projects/{id}/intelligence/recommendations/



GET    /projects/{id}/intelligence/context/



POST   /projects/{id}/intelligence/context/build/



GET    /projects/{id}/intelligence/resume/



GET    /projects/{id}/intelligence/changes/



POST   /projects/{id}/intelligence/compare/





این Endpointها فقط Contract هستند و باید با API Architecture

اصلی Meryx هماهنگ شوند.





============================================================

40\. Async Processing

============================================================



Analysis پروژه‌های بزرگ نباید داخل HTTP Request اجرا شود.



Flow:



API

&#x20;   ↓

Create Intelligence Job

&#x20;   ↓

Queue

&#x20;   ↓

Worker

&#x20;   ↓

Snapshot

&#x20;   ↓

Analysis

&#x20;   ↓

Knowledge

&#x20;   ↓

Insight

&#x20;   ↓

Recommendation

&#x20;   ↓

Context

&#x20;   ↓

Complete





============================================================

41\. Job Management

============================================================



هر Intelligence Job باید دارای:



\- id

\- project\_id

\- type

\- status

\- priority

\- created\_at

\- started\_at

\- completed\_at

\- retry\_count

\- error

\- metadata





باشد.





============================================================

42\. Event System

============================================================



Eventهای اصلی:



ProjectSnapshotCreated



ProjectAnalysisStarted



ProjectAnalysisCompleted



ProjectAnalysisFailed



ProjectChanged



ProjectKnowledgeUpdated



ProjectInsightCreated



ProjectRecommendationCreated



ProjectDecisionCreated



ProjectContextBuilt



ProjectResumeGenerated



ArchitectureViolationDetected



DependencyCycleDetected



ProjectAnalysisFailed





============================================================

43\. Audit

============================================================



عملیات مهم باید Audit شوند:



\- Snapshot

\- Analysis

\- Knowledge Update

\- Recommendation

\- Decision

\- Context Generation

\- Configuration Change





Audit باید شامل:



\- Actor

\- Project

\- Action

\- Timestamp

\- Metadata





باشد.





============================================================

44\. Observability

============================================================



Metrics:



\- Scan Duration

\- Analysis Duration

\- Files Scanned

\- Files Changed

\- Analyzer Failures

\- Dependency Count

\- Architecture Violations

\- Insight Count

\- Recommendation Count

\- Context Build Duration





============================================================

45\. Testing

============================================================



Domain Tests:



\- Snapshot

\- Project State

\- Insight

\- Recommendation

\- Decision

\- Versioning



Analyzer Tests:



\- Filesystem

\- Language

\- Framework

\- Dependency

\- Git

\- Architecture



Application Tests:



\- Snapshot Creation

\- Analysis

\- Incremental Analysis

\- Knowledge Building

\- Insight Generation

\- Recommendation Generation

\- Context Building



Integration Tests:



\- Database

\- Workspace

\- Git

\- Storage

\- Cache



API Tests:



\- Authentication

\- Authorization

\- Tenant Isolation

\- Project Access

\- Intelligence Endpoints





============================================================

46\. Test Fixtures

============================================================



برای تست Analyzerها باید Workspaceهای مصنوعی ساخته شود.



مثال:



fixtures/

&#x20;   simple\_python/

&#x20;   django\_project/

&#x20;   broken\_project/

&#x20;   circular\_dependencies/

&#x20;   layered\_project/

&#x20;   mixed\_language\_project/





هر Fixture باید سناریوی مشخص داشته باشد.





============================================================

47\. Performance

============================================================



Project Intelligence باید برای Projectهای کوچک، متوسط و بزرگ

قابل استفاده باشد.



Optimizationها:



\- Incremental Scan

\- File Hash Cache

\- Analysis Cache

\- Parallel Analyzer Execution در صورت امکان

\- Lazy Context Building

\- Selective Parsing





============================================================

48\. Determinism

============================================================



برای Input یکسان:



Snapshot

و

Analyzer Version



باید نتیجه قابل تکرار داشته باشند.



Timestamp نباید باعث تفاوت محتوای منطقی Analysis شود.





============================================================

49\. Data Integrity

============================================================



هر Snapshot باید Hash داشته باشد.



هر Analysis باید به Snapshot مشخص متصل باشد.



هر Knowledge Version باید به Analysis Version مشخص متصل باشد.



هر Context Package باید به Knowledge Version مشخص متصل باشد.



زنجیره:



Snapshot

&#x20;   ↓

Analysis

&#x20;   ↓

Knowledge

&#x20;   ↓

Insight

&#x20;   ↓

Recommendation

&#x20;   ↓

Decision

&#x20;   ↓

Context





============================================================

50\. Explainability

============================================================



هر Insight و Recommendation باید بتواند بگوید:



WHAT

WHY

EVIDENCE

SOURCE

IMPACT

CONFIDENCE





مثال:



WHAT:

High Coupling



WHY:

Module A imports 18 internal modules.



EVIDENCE:

dependency graph



IMPACT:

High maintenance complexity



CONFIDENCE:

0.94





============================================================

51\. Agent Integration

============================================================



Agent Platform باید بتواند از Project Intelligence استفاده کند.



Agent:



Task

&#x20;   ↓

Project Intelligence

&#x20;   ↓

Task Context

&#x20;   ↓

Agent Brain

&#x20;   ↓

Action





Agent نباید مجبور باشد برای هر Task کل Workspace را خودش

از صفر Scan کند.





============================================================

52\. AI Integration

============================================================



AI می‌تواند در:



\- Insight Generation

\- Recommendation Ranking

\- Semantic Analysis

\- Documentation Understanding

\- Code Understanding



استفاده شود.



اما AI نباید Source of Truth معماری باشد.



Source of Truth:



Actual Project State

\+

Deterministic Analysis





============================================================

53\. AI Safety

============================================================



AI نباید بدون Evidence ادعای معماری کند.



AI Output باید:



\- Source

\- Evidence

\- Confidence



داشته باشد.





============================================================

54\. Documentation Intelligence

============================================================



سیستم باید Documentation پروژه را نیز تحلیل کند.



موارد:



README

Documentation

Architecture Docs

Development Rules

API Docs

Configuration Docs





در صورت تناقض:



Actual Code

باید از Documentation جداگانه گزارش شود.



سیستم نباید بدون Evidence یکی را حقیقت قطعی فرض کند.





============================================================

55\. Project Health

============================================================



Project Intelligence باید امکان محاسبه Project Health را داشته باشد.



محورهای پیشنهادی:



Architecture

Code Quality

Testing

Documentation

Dependencies

Security

Maintainability

Activity





Health Score نباید فقط یک عدد بدون توضیح باشد.



هر Score باید Breakdown داشته باشد.





============================================================

56\. Technical Debt

============================================================



سیستم باید Technical Debt Candidateها را شناسایی کند.



مثال:



\- TODO

\- FIXME

\- High Coupling

\- Dead Code

\- Missing Tests

\- Circular Dependencies

\- Deprecated Dependencies

\- Architecture Violations





هر مورد باید Evidence داشته باشد.





============================================================

57\. Project Resume

============================================================



Resume Generator باید یک وضعیت قابل انتقال ایجاد کند.



ساختار:



PROJECT

CURRENT STATE

ARCHITECTURE

RECENT CHANGES

ACTIVE PROBLEMS

COMPLETED WORK

PENDING WORK

KNOWN CONSTRAINTS

RECOMMENDED NEXT ACTION





این Resume باید برای انتقال Context بین Sessionها قابل استفاده باشد.





============================================================

58\. Context Package

============================================================



Context Package باید Metadata داشته باشد:



\- project\_id

\- snapshot\_id

\- knowledge\_version

\- generated\_at

\- generator\_version

\- task

\- token\_budget

\- included\_files

\- included\_modules

\- excluded\_files





============================================================

59\. Directory Structure

============================================================



ساختار مفهومی:



apps/

&#x20;   project\_intelligence/



&#x20;       domain/

&#x20;           entities/

&#x20;           value\_objects/

&#x20;           events/

&#x20;           services/

&#x20;           repositories/



&#x20;       application/

&#x20;           commands/

&#x20;           queries/

&#x20;           use\_cases/

&#x20;           services/

&#x20;           dto/



&#x20;       infrastructure/

&#x20;           filesystem/

&#x20;           git/

&#x20;           parsers/

&#x20;           analyzers/

&#x20;           persistence/

&#x20;           cache/

&#x20;           storage/



&#x20;       interfaces/

&#x20;           api/

&#x20;           serializers/

&#x20;           views/



&#x20;       tests/

&#x20;           unit/

&#x20;           integration/

&#x20;           e2e/

&#x20;           fixtures/





ساختار نهایی باید با Project Structure اصلی Meryx هماهنگ باشد.





============================================================

60\. IMPLEMENTATION ORDER

============================================================



STEP 1

Project Intelligence Domain



STEP 2

Snapshot Model



STEP 3

Workspace Boundary



STEP 4

Filesystem Analyzer



STEP 5

Language Analyzer



STEP 6

Framework Analyzer



STEP 7

Git Analyzer



STEP 8

Dependency Analyzer



STEP 9

Architecture Analyzer



STEP 10

Test Analyzer



STEP 11

Documentation Analyzer



STEP 12

Analyzer Registry



STEP 13

Analysis Orchestrator



STEP 14

Knowledge Builder



STEP 15

Knowledge Graph



STEP 16

Insight Engine



STEP 17

Recommendation Engine



STEP 18

Decision Engine



STEP 19

Project State



STEP 20

Change Detection



STEP 21

Incremental Analysis



STEP 22

Context Builder



STEP 23

Resume Generator



STEP 24

Persistence



STEP 25

Caching



STEP 26

Async Jobs



STEP 27

Events



STEP 28

Audit



STEP 29

API



STEP 30

Permissions



STEP 31

Agent Integration



STEP 32

Tests



STEP 33

Quality Gate





============================================================

61\. ممنوعیت‌های مهم

============================================================



در Phase 17:



\- کل Workspace را برای هر Request دوباره Scan نکن.

\- Analyzer را مستقیماً به View وصل نکن.

\- Domain را به Django وابسته نکن.

\- Path خارج از Workspace را نخوان.

\- Snapshot قبلی را overwrite نکن.

\- Knowledge Version قبلی را overwrite نکن.

\- AI را Source of Truth قرار نده.

\- Insight بدون Evidence تولید نکن.

\- Recommendation بدون Evidence تولید نکن.

\- Context بدون Version تولید نکن.

\- Tenant Isolation را دور نزن.

\- Git History را بدون مجوز تغییر نده.

\- Project Files را Modify نکن مگر اینکه Capability صراحتاً برای

&#x20; این کار طراحی شده باشد.

\- Analyzer Failure را مخفی نکن.

\- Error را بدون ثبت عبور نده.

\- کل Repository را بدون نیاز وارد Agent Context نکن.





============================================================

62\. DEFINITION OF DONE

============================================================



Phase 17 فقط زمانی Done است که:



\[ ] Project Snapshot ساخته شده باشد.



\[ ] Snapshot Versioning وجود داشته باشد.



\[ ] Workspace Boundary امن باشد.



\[ ] Filesystem Analyzer ساخته شده باشد.



\[ ] Language Detection ساخته شده باشد.



\[ ] Framework Detection ساخته شده باشد.



\[ ] Git Analysis ساخته شده باشد.



\[ ] Dependency Analysis ساخته شده باشد.



\[ ] Architecture Analysis ساخته شده باشد.



\[ ] Test Analysis ساخته شده باشد.



\[ ] Documentation Analysis ساخته شده باشد.



\[ ] Analyzer Registry ساخته شده باشد.



\[ ] Analysis Orchestrator ساخته شده باشد.



\[ ] Knowledge Builder ساخته شده باشد.



\[ ] Knowledge Graph ساخته شده باشد.



\[ ] Insight Engine ساخته شده باشد.



\[ ] Recommendation Engine ساخته شده باشد.



\[ ] Decision Engine ساخته شده باشد.



\[ ] Change Detection ساخته شده باشد.



\[ ] Incremental Analysis ساخته شده باشد.



\[ ] Context Builder ساخته شده باشد.



\[ ] Resume Generator ساخته شده باشد.



\[ ] Project State ساخته شده باشد.



\[ ] Persistence کامل باشد.



\[ ] Cache وجود داشته باشد.



\[ ] Async Processing وجود داشته باشد.



\[ ] Eventها پیاده‌سازی شده باشند.



\[ ] Audit وجود داشته باشد.



\[ ] Tenant Isolation تست شده باشد.



\[ ] Permissionها تست شده باشند.



\[ ] Agent Integration انجام شده باشد.



\[ ] API Tests سبز باشند.



\[ ] Integration Tests سبز باشند.



\[ ] Unit Tests سبز باشند.



\[ ] Django Check سبز باشد.



\[ ] Ruff سبز باشد.



\[ ] Format Check سبز باشد.



\[ ] Mypy سبز باشد.



\[ ] هیچ TODO بحرانی باقی نمانده باشد.



\[ ] هیچ Placeholder غیرضروری باقی نمانده باشد.



\[ ] هیچ Architecture Violation بحرانی باقی نمانده باشد.





============================================================

63\. خروجی نهایی PHASE 17

============================================================



در پایان Phase 17، Meryx باید بتواند یک Project را به صورت

ساختاریافته مشاهده و تحلیل کند.



چرخه نهایی:



PROJECT

&#x20;   ↓

SNAPSHOT

&#x20;   ↓

OBSERVATION

&#x20;   ↓

ANALYSIS

&#x20;   ↓

DEPENDENCY GRAPH

&#x20;   ↓

ARCHITECTURE MODEL

&#x20;   ↓

PROJECT KNOWLEDGE

&#x20;   ↓

INSIGHTS

&#x20;   ↓

RECOMMENDATIONS

&#x20;   ↓

DECISIONS

&#x20;   ↓

TASK CONTEXT

&#x20;   ↓

AGENT



و در صورت تغییر پروژه:



CHANGE

&#x20;   ↓

CHANGE DETECTION

&#x20;   ↓

AFFECTED AREA

&#x20;   ↓

INCREMENTAL ANALYSIS

&#x20;   ↓

KNOWLEDGE UPDATE

&#x20;   ↓

NEW CONTEXT





Project Intelligence باید در پایان Phase 17 به عنوان

«سیستم ادراک و درک پروژه» در Meryx عمل کند.



این Platform نباید صرفاً File Scanner، Code Parser یا گزارش‌ساز

باشد؛ بلکه باید Source ساختاریافته‌ای از وضعیت، معماری، وابستگی،

تاریخچه، Knowledge، Insight و Context پروژه برای سایر Platformهای

Meryx فراهم کند.

