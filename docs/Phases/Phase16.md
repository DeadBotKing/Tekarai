PHASE 16 — SELF-LEARNING PLATFORM

TEKARAI IMPLEMENTATION SPECIFICATION



============================================================

1\. هدف فاز

============================================================



هدف Phase 16 ساخت Self-Learning Platform در Tekarai است.



این فاز باید بستری ایجاد کند که سیستم بتواند:



\- رفتار سیستم را مشاهده کند.

\- داده‌های عملیاتی را جمع‌آوری کند.

\- نتایج تصمیم‌ها و عملیات را ثبت کند.

\- از تاریخچه عملکرد، الگو استخراج کند.

\- کیفیت تصمیم‌ها و عملکرد سیستم را ارزیابی کند.

\- Feedback تولید کند.

\- Knowledge قابل استفاده برای آینده ایجاد کند.

\- مدل‌ها، Ruleها، Policyها یا Strategyهای قابل یادگیری را مدیریت کند.

\- فرآیند یادگیری را کنترل‌شده، قابل ردیابی و قابل Rollback نگه دارد.



Self-Learning نباید به معنی «سیستم خودش هر چیزی را تغییر دهد» باشد.



هر تغییر یادگیرنده باید:



Observation

→ Data Collection

→ Evaluation

→ Learning

→ Validation

→ Approval

→ Deployment

→ Monitoring

→ Rollback



را طی کند.



هیچ Learning Artifact نباید بدون Validation وارد Production شود.





============================================================

2\. جایگاه Self-Learning در معماری Tekarai

============================================================



Self-Learning یک Platform مستقل در معماری Tekarai است.



وابستگی مفهومی:



Core

&#x20;   ↓

Domain

&#x20;   ↓

Application

&#x20;   ↓

Platform

&#x20;   ↓

Self-Learning Platform

&#x20;   ↓

AI / Decision / Operational Systems



Self-Learning نباید مستقیماً به:



\- Django Views

\- Django ORM در Domain

\- REST API

\- Frontend

\- HTTP Request

\- Admin Panel



وابسته شود.



Infrastructure باید جزئیات تکنولوژی را پیاده‌سازی کند.



Self-Learning باید از Interface / Port استفاده کند.





============================================================

3\. اصل معماری

============================================================



Self-Learning Platform باید بر اساس:



\- Clean Architecture

\- Domain-Driven Design

\- Dependency Inversion

\- Explicit Boundaries

\- Event-Driven Architecture

\- Immutable History

\- Versioning

\- Auditability

\- Reproducibility

\- Validation

\- Rollback



ساخته شود.





============================================================

4\. اجزای اصلی

============================================================



Self-Learning Platform شامل بخش‌های زیر است:



1\. Observation

2\. Experience Collection

3\. Dataset Management

4\. Feature/Signal Extraction

5\. Learning Engine

6\. Evaluation Engine

7\. Validation Engine

8\. Model/Policy Versioning

9\. Experiment Management

10\. Approval System

11\. Deployment Management

12\. Monitoring

13\. Feedback Loop

14\. Rollback

15\. Learning Audit





============================================================

5\. DOMAIN MODEL

============================================================



Entityهای اصلی:



LearningExperience



LearningDataset



LearningSample



LearningExperiment



LearningRun



LearningArtifact



ModelVersion



PolicyVersion



EvaluationResult



ValidationResult



Approval



Deployment



Feedback



LearningMetric



LearningEvent



LearningSnapshot





============================================================

6\. LearningExperience

============================================================



LearningExperience نشان‌دهنده یک تجربه واقعی سیستم است.



فیلدهای پیشنهادی:



\- id

\- tenantId

\- source

\- context

\- input

\- action

\- expectedOutcome

\- actualOutcome

\- reward

\- success

\- timestamp

\- metadata



قواعد:



\- Experience نباید حذف فیزیکی شود.

\- History باید immutable باشد.

\- هر Experience باید قابل trace باشد.

\- tenant isolation الزامی است.





============================================================

7\. LearningDataset

============================================================



Dataset مجموعه‌ای از Experienceها یا Sampleهای قابل استفاده برای Learning است.



فیلدها:



\- id

\- tenantId

\- name

\- version

\- description

\- source

\- status

\- sampleCount

\- createdAt

\- createdBy

\- metadata



Status:



DRAFT

BUILDING

READY

VALIDATING

APPROVED

ARCHIVED

FAILED





============================================================

8\. LearningSample

============================================================



هر Sample باید قابل بازتولید باشد.



فیلدها:



\- id

\- datasetId

\- input

\- target

\- context

\- sourceExperienceId

\- weight

\- metadata



Sample نباید بدون Source مشخص وارد Dataset شود.





============================================================

9\. LearningExperiment

============================================================



Experiment برای اجرای یک فرآیند Learning مشخص است.



فیلدها:



\- id

\- tenantId

\- name

\- description

\- datasetVersion

\- algorithm

\- configuration

\- baselineVersion

\- status

\- createdAt

\- completedAt



Status:



CREATED

RUNNING

COMPLETED

FAILED

CANCELLED





============================================================

10\. LearningRun

============================================================



هر اجرای واقعی Learning باید Run مستقل داشته باشد.



اطلاعات:



\- experimentId

\- startedAt

\- finishedAt

\- parameters

\- environment

\- datasetHash

\- codeVersion

\- artifactId

\- metrics

\- logs

\- status





============================================================

11\. LearningArtifact

============================================================



Artifact نتیجه یک Learning Run است.



می‌تواند شامل:



\- Model

\- Policy

\- Rule Set

\- Embedding

\- Knowledge Artifact

\- Configuration

\- Strategy



باشد.



فیلدها:



\- id

\- type

\- version

\- storageUri

\- checksum

\- createdByRun

\- metadata

\- status





============================================================

12\. ModelVersion

============================================================



هر Model باید Version مستقل داشته باشد.



مثال:



model:

&#x20;   recommendationModel



versions:



&#x20;   1.0.0

&#x20;   1.1.0

&#x20;   1.2.0



هیچ Model Version نباید overwrite شود.



نسخه جدید باید Artifact جدید ایجاد کند.





============================================================

13\. EvaluationResult

============================================================



بعد از Training باید Evaluation انجام شود.



EvaluationResult شامل:



\- accuracy

\- precision

\- recall

\- f1

\- latency

\- errorRate

\- businessMetrics

\- baselineComparison

\- datasetVersion

\- modelVersion



Metricها باید بر اساس نوع Learning قابل توسعه باشند.





============================================================

14\. Validation

============================================================



Evaluation با Validation متفاوت است.



Evaluation:



آیا مدل عملکرد مناسبی دارد؟



Validation:



آیا مدل اجازه ورود به مرحله بعد را دارد؟



Validation باید موارد زیر را بررسی کند:



\- minimum performance

\- regression

\- safety

\- data leakage

\- reproducibility

\- compatibility

\- latency

\- resource usage

\- business constraints





============================================================

15\. Baseline

============================================================



هر Learning Artifact باید با Baseline مقایسه شود.



مثال:



Baseline:

Model v1.2



Candidate:

Model v1.3



مقایسه:



v1.2:

accuracy = 0.81



v1.3:

accuracy = 0.84



اما فقط accuracy کافی نیست.



باید Metrics دیگر نیز بررسی شوند.





============================================================

16\. Regression Detection

============================================================



اگر Candidate در یک بخش بهتر ولی در بخش مهم دیگری بدتر باشد، نباید خودکار Deploy شود.



مثال:



Accuracy ↑

Latency ↑↑

Error Rate ↑



نتیجه:



REJECT





============================================================

17\. Learning Policy

============================================================



هر نوع Learning باید Policy داشته باشد.



Policy مشخص می‌کند:



\- چه داده‌ای قابل استفاده است.

\- چه زمانی Learning اجرا شود.

\- چه Metricهایی بررسی شوند.

\- حداقل Score چقدر باشد.

\- چه Regressionهایی ممنوع هستند.

\- چه کسی Approval بدهد.

\- آیا Auto Deployment مجاز است یا خیر.





============================================================

18\. Experiment Reproducibility

============================================================



هر Experiment باید قابل بازسازی باشد.



برای هر Run باید ثبت شود:



\- Dataset Version

\- Dataset Hash

\- Code Version

\- Configuration

\- Parameters

\- Environment

\- Dependency Versions

\- Model Version

\- Random Seed در صورت وجود

\- Execution Timestamp





============================================================

19\. Feedback Loop

============================================================



Feedback Loop:



Production

&#x20;   ↓

Observation

&#x20;   ↓

Experience

&#x20;   ↓

Feedback

&#x20;   ↓

Dataset

&#x20;   ↓

Learning

&#x20;   ↓

Evaluation

&#x20;   ↓

Validation

&#x20;   ↓

Candidate

&#x20;   ↓

Approval

&#x20;   ↓

Deployment

&#x20;   ↓

Production





============================================================

20\. Feedback

============================================================



Feedback می‌تواند:



\- Positive

\- Negative

\- Neutral

\- Human

\- System-generated

\- Business-generated



باشد.



فیلدهای پیشنهادی:



\- id

\- experienceId

\- type

\- score

\- source

\- comment

\- createdAt

\- metadata





============================================================

21\. Human Feedback

============================================================



سیستم باید امکان Human-in-the-loop داشته باشد.



Human می‌تواند:



\- Approve

\- Reject

\- Correct

\- Label

\- Rate

\- Flag



کند.



Human Feedback باید Audit شود.





============================================================

22\. Approval

============================================================



هیچ Candidate نباید بدون Approval وارد Production شود؛ مگر اینکه Learning Policy صراحتاً Auto Deployment را مجاز کرده باشد.



Approval شامل:



\- artifactId

\- reviewer

\- decision

\- reason

\- timestamp





============================================================

23\. Deployment

============================================================



Deployment باید Versioned باشد.



مثال:



Model v1.4



Deployment:



STAGED

→ CANARY

→ ACTIVE



در صورت مشکل:



ACTIVE

→ ROLLBACK

→ v1.3





============================================================

24\. Canary Deployment

============================================================



در صورت پشتیبانی سیستم، Candidate ابتدا روی بخشی از Traffic اجرا شود.



مثال:



5%

→ 25%

→ 50%

→ 100%



در هر مرحله Metrics بررسی شوند.





============================================================

25\. Monitoring

============================================================



بعد از Deployment باید Monitoring فعال باشد.



موارد قابل پایش:



\- Accuracy

\- Error Rate

\- Latency

\- Drift

\- Resource Usage

\- Business KPI

\- Failure Rate





============================================================

26\. Drift Detection

============================================================



سیستم باید امکان تشخیص تغییر Distribution را داشته باشد.



انواع:



Data Drift

Concept Drift

Prediction Drift

Performance Drift





============================================================

27\. Rollback

============================================================



Rollback باید سریع و قابل اطمینان باشد.



Rollback باید بتواند Candidate فعلی را غیرفعال کرده و آخرین Version سالم را فعال کند.



هیچ Artifact قبلی نباید برای Rollback حذف شود.





============================================================

28\. Learning Events

============================================================



Eventهای پیشنهادی:



LearningExperienceCreated



LearningDatasetCreated



LearningDatasetReady



LearningExperimentStarted



LearningExperimentCompleted



LearningExperimentFailed



LearningArtifactCreated



EvaluationCompleted



ValidationPassed



ValidationFailed



LearningArtifactApproved



LearningArtifactRejected



DeploymentStarted



DeploymentCompleted



DeploymentFailed



RollbackStarted



RollbackCompleted



DriftDetected



LearningFeedbackReceived





============================================================

29\. APPLICATION LAYER

============================================================



Use Caseهای اصلی:



CreateLearningExperience



CollectExperience



BuildDataset



ValidateDataset



CreateExperiment



RunLearningExperiment



EvaluateArtifact



ValidateArtifact



ApproveArtifact



RejectArtifact



DeployArtifact



MonitorArtifact



DetectDrift



RollbackArtifact



RecordFeedback





============================================================

30\. PORTS

============================================================



Interfaceهای مورد نیاز:



ExperienceRepository



DatasetRepository



ExperimentRepository



ArtifactRepository



EvaluationRepository



ValidationRepository



DeploymentRepository



FeedbackRepository



ModelStorage



DatasetStorage



LearningEngine



EvaluationEngine



ValidationEngine



DeploymentEngine



DriftDetector



MetricCollector





============================================================

31\. INFRASTRUCTURE

============================================================



Infrastructure مسئول اتصال به:



\- Database

\- File Storage

\- Object Storage

\- ML Framework

\- Queue

\- Cache

\- Monitoring

\- Logging



است.



Domain نباید این تکنولوژی‌ها را بشناسد.





============================================================

32\. DATABASE

============================================================



جدول‌های اصلی:



learningExperiences



learningDatasets



learningSamples



learningExperiments



learningRuns



learningArtifacts



modelVersions



policyVersions



evaluationResults



validationResults



learningApprovals



learningDeployments



learningFeedback



learningMetrics



learningEvents



learningSnapshots





============================================================

33\. TENANCY

============================================================



تمام داده‌های Learning که متعلق به Tenant هستند باید tenantId داشته باشند.



هیچ Query نباید بتواند داده Tenant دیگر را مشاهده کند.



Tenant Isolation باید در:



\- Repository

\- Service

\- Query

\- API



رعایت شود.





============================================================

34\. SECURITY

============================================================



Learning Platform باید دارای:



\- Permission

\- Role

\- Audit

\- Tenant Isolation

\- Artifact Integrity

\- Access Control



باشد.



هیچ کاربر عادی نباید بتواند Model Production را مستقیماً تغییر دهد.





============================================================

35\. AUDIT

============================================================



تمام عملیات حساس ثبت شوند:



\- Dataset creation

\- Experiment execution

\- Model creation

\- Evaluation

\- Validation

\- Approval

\- Deployment

\- Rollback

\- Manual feedback



Audit Log باید شامل:



\- actor

\- action

\- target

\- timestamp

\- previousState

\- newState

\- metadata





============================================================

36\. API

============================================================



API باید برای عملیات مدیریتی Learning طراحی شود.



Endpointهای مفهومی:



GET    /learning/experiences/

POST   /learning/experiences/



GET    /learning/datasets/

POST   /learning/datasets/



GET    /learning/experiments/

POST   /learning/experiments/



POST   /learning/experiments/{id}/run/



GET    /learning/artifacts/



GET    /learning/artifacts/{id}/



POST   /learning/artifacts/{id}/evaluate/



POST   /learning/artifacts/{id}/validate/



POST   /learning/artifacts/{id}/approve/



POST   /learning/artifacts/{id}/reject/



POST   /learning/artifacts/{id}/deploy/



POST   /learning/artifacts/{id}/rollback/



GET    /learning/deployments/



GET    /learning/metrics/



POST   /learning/feedback/





این Endpointها فقط Interface هستند و Implementation باید بر اساس API Architecture پروژه انجام شود.





============================================================

37\. ASYNC EXECUTION

============================================================



Learning معمولاً عملیات سنگین است.



بنابراین:



HTTP Request

&#x20;   ↓

Create Job

&#x20;   ↓

Queue

&#x20;   ↓

Worker

&#x20;   ↓

Learning Run

&#x20;   ↓

Result

&#x20;   ↓

Event



نباید Training سنگین داخل Request/Response lifecycle انجام شود.





============================================================

38\. JOB MANAGEMENT

============================================================



هر Learning Job باید دارای:



\- id

\- type

\- status

\- priority

\- createdAt

\- startedAt

\- completedAt

\- retryCount

\- error

\- metadata



باشد.





============================================================

39\. FAILURE HANDLING

============================================================



در صورت Failure:



\- Run باید FAILED شود.

\- Error باید ثبت شود.

\- Artifact ناقص نباید Deploy شود.

\- Retry Policy باید رعایت شود.

\- Event مناسب منتشر شود.

\- Audit ثبت شود.





============================================================

40\. IDEMPOTENCY

============================================================



اجرای دوباره یک Job نباید باعث ایجاد Artifact اشتباه یا Duplicate شود.



برای عملیات حساس از:



\- idempotency key

\- run identifier

\- artifact checksum



استفاده شود.





============================================================

41\. OBSERVABILITY

============================================================



سیستم باید Logging و Metrics داشته باشد.



حداقل:



\- experiment duration

\- training duration

\- evaluation duration

\- deployment duration

\- failure count

\- rollback count

\- drift count





============================================================

42\. DIRECTORY STRUCTURE

============================================================



ساختار پیشنهادی:



apps/

&#x20;   learning/



&#x20;       domain/

&#x20;           entities/

&#x20;           valueObjects/

&#x20;           events/

&#x20;           services/

&#x20;           repositories/



&#x20;       application/

&#x20;           commands/

&#x20;           queries/

&#x20;           services/

&#x20;           useCases/

&#x20;           dto/



&#x20;       infrastructure/

&#x20;           persistence/

&#x20;           storage/

&#x20;           learning/

&#x20;           evaluation/

&#x20;           deployment/

&#x20;           monitoring/



&#x20;       interfaces/

&#x20;           api/

&#x20;           serializers/

&#x20;           views/



&#x20;       tests/

&#x20;           unit/

&#x20;           integration/

&#x20;           e2e/





اگر ساختار نهایی Tekarai استاندارد متفاوتی دارد، ساختار موجود پروژه باید مبنا قرار گیرد و Architecture جدیدی بدون دلیل ایجاد نشود.





============================================================

43\. TESTING

============================================================



حداقل Testها:



Domain Tests



\- Experience creation

\- Dataset rules

\- Experiment state transitions

\- Artifact versioning

\- Approval rules

\- Deployment rules

\- Rollback rules



Application Tests



\- Create Experience

\- Build Dataset

\- Run Experiment

\- Evaluate Artifact

\- Validate Artifact

\- Approve Artifact

\- Deploy Artifact

\- Rollback Artifact



Integration Tests



\- Database

\- Storage

\- Learning Engine

\- Queue

\- Monitoring



API Tests



\- Authentication

\- Authorization

\- Tenant isolation

\- CRUD

\- Approval

\- Deployment

\- Rollback





============================================================

44\. QUALITY GATE

============================================================



قبل از پایان Phase 16:



python manage.py check



pytest



ruff check .



ruff format --check .



mypy .



تمام تست‌ها و Quality Gateها باید سبز باشند.





============================================================

45\. IMPLEMENTATION ORDER

============================================================



ترتیب اجرای فاز:



STEP 1

Domain Entities



STEP 2

Value Objects



STEP 3

Domain Events



STEP 4

Repository Interfaces



STEP 5

Application Use Cases



STEP 6

DTOs



STEP 7

Persistence Models



STEP 8

Repository Implementations



STEP 9

Learning Engine Interface



STEP 10

Evaluation Engine



STEP 11

Validation Engine



STEP 12

Artifact Storage



STEP 13

Experiment Runner



STEP 14

Feedback System



STEP 15

Deployment System



STEP 16

Rollback



STEP 17

Monitoring



STEP 18

Drift Detection



STEP 19

API



STEP 20

Permissions



STEP 21

Audit



STEP 22

Tests



STEP 23

Quality Gate





============================================================

46\. ممنوعیت‌های مهم

============================================================



در Phase 16:



\- Model را مستقیم از View اجرا نکن.

\- Training سنگین را داخل HTTP Request اجرا نکن.

\- Domain را به Django وابسته نکن.

\- Artifact را overwrite نکن.

\- Version قبلی را حذف نکن.

\- بدون Validation Deploy نکن.

\- بدون Audit عملیات حساس انجام نده.

\- Tenant Isolation را دور نزن.

\- Production Model را مستقیم تغییر نده.

\- Feedback را بدون Source ثبت نکن.

\- Dataset بدون Version ایجاد نکن.

\- Experiment بدون Dataset Version اجرا نکن.

\- Artifact بدون Run ایجاد نکن.

\- Deployment بدون Artifact Version انجام نده.

\- Rollback نباید History را حذف کند.





============================================================

47\. DEFINITION OF DONE

============================================================



Phase 16 فقط زمانی Done است که:



\[ ] LearningExperience ساخته شده باشد.



\[ ] Dataset Management ساخته شده باشد.



\[ ] Experiment Management ساخته شده باشد.



\[ ] Learning Run ساخته شده باشد.



\[ ] Artifact Management ساخته شده باشد.



\[ ] Versioning کامل باشد.



\[ ] Evaluation Engine ساخته شده باشد.



\[ ] Validation Engine ساخته شده باشد.



\[ ] Approval Flow ساخته شده باشد.



\[ ] Deployment Flow ساخته شده باشد.



\[ ] Rollback ساخته شده باشد.



\[ ] Feedback Loop ساخته شده باشد.



\[ ] Monitoring ساخته شده باشد.



\[ ] Drift Detection پایه وجود داشته باشد.



\[ ] Audit کامل باشد.



\[ ] Tenant Isolation تست شده باشد.



\[ ] Permissionها تست شده باشند.



\[ ] API تست شده باشد.



\[ ] Unit Tests سبز باشند.



\[ ] Integration Tests سبز باشند.



\[ ] API Tests سبز باشند.



\[ ] Django Check سبز باشد.



\[ ] Ruff سبز باشد.



\[ ] Black/Format Check سبز باشد.



\[ ] Mypy سبز باشد.



\[ ] هیچ TODO بحرانی باقی نمانده باشد.



\[ ] هیچ Placeholder غیرضروری باقی نمانده باشد.



\[ ] هیچ وابستگی Architectureای خلاف قوانین Tekarai ایجاد نشده باشد.





============================================================

48\. خروجی نهایی PHASE 16

============================================================



در پایان این فاز Tekarai باید دارای یک Self-Learning Platform

قابل توسعه، Versioned، Auditable، قابل Validation و قابل Rollback باشد.



این Platform باید بتواند چرخه زیر را اجرا کند:



OBSERVE

&#x20;   ↓

COLLECT

&#x20;   ↓

STORE

&#x20;   ↓

BUILD DATASET

&#x20;   ↓

EXPERIMENT

&#x20;   ↓

LEARN

&#x20;   ↓

EVALUATE

&#x20;   ↓

VALIDATE

&#x20;   ↓

APPROVE

&#x20;   ↓

DEPLOY

&#x20;   ↓

MONITOR

&#x20;   ↓

FEEDBACK

&#x20;   ↓

RELEARN



و در صورت Failure:



MONITOR

&#x20;   ↓

DETECT FAILURE

&#x20;   ↓

ROLLBACK

&#x20;   ↓

RESTORE STABLE VERSION



Phase 16 نباید صرفاً یک ML Module باشد.



این فاز باید یک زیرسیستم کامل برای مدیریت چرخه یادگیری،

ارزیابی، انتشار، پایش و بازگشت نسخه‌های یادگیرنده در Tekarai ایجاد کند.

