# Phase 13-B — AI Domain & Value Objects

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** B از A تا Z  
**وضعیت:** COMPLETED — Domain Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-A.md`](Phase13-A.md)  
**گزارش اجرا:** [`Phase13-B-ExecutionReport.md`](Phase13-B-ExecutionReport.md)

---

## 1. هدف

B لایهٔ Domain فاز ۱۳ را به‌صورت Framework-free ایجاد می‌کند. این زیر‌فاز
تعریف اجرایی مفاهیم AI، Value Objectهای اعتبارسنجی‌شده، State Machineهای اصلی
و Invariantهای پایه را تحویل می‌دهد تا بخش‌های C تا Z بتوانند روی Contractهای
پایدار کار کنند.

B عمداً هیچ وابستگی به این موارد ندارد:

- Django و Django ORM؛
- Django REST Framework و HTTP؛
- Redis، Channels، Celery یا Queue؛
- OpenAI، Azure، Ollama، Anthropic یا هر Vendor SDK؛
- SQL Server، SQLite یا Database؛
- فایل‌سیستم و Network.

---

## 2. نگاشت به سند مادر

| سند مادر | خروجی B |
|---|---|
| §5 AI Domain Components | Entityهای اصلی و Aggregate conceptها |
| §6 AI Provider | `AIProvider` و Policyهای Provider |
| §7 AI Model | `AIModel` و Cost/Capability invariants |
| §8 Model Types | `ModelType` و `MODEL_TYPES` |
| §9 AI Capability | `CapabilityCode` و `AICapability` |
| §10 AI Request | `AIRequest` و lifecycle آن |
| §11 AI Response | `AIResponse` و token/classification invariants |
| §§12–14 Structured Output و Prompt | Schema contract و `AIPromptVersion` |
| §17 AI Memory | `AIMemory` و version/expiry |
| §§18–19 Knowledge/Embedding | `AIKnowledgeItem`, `AIKnowledgeChunk`, `AIEmbedding` |
| §§20–21 Retrieval/RAG | `AIRetrieval` و جداسازی Candidate/Authorized/Selected |
| §§26–28 Usage/Cost/Audit | `AIUsage`, `AICost`, `AIAuditRecord` |
| §§32–33 Evaluation/Feedback | `AIEvaluation`, `AIFeedback` |
| §§30–31 Tool/Agent | `AITool`, `AIToolExecution`, `AIAgent`, `AIAgentExecution` |
| §§38، 43–48 | Tenant، Error، Privacy، Policy و validation invariants |

---

## 3. Value Objectهای تحویل‌شده

### 3.1 Controlled Vocabularies

مقادیر زیر در Domain ثبت شده‌اند و در مرحلهٔ بعد به Database/API enum mapping
می‌شوند:

- `MODEL_TYPES`: `LLM`, `EMBEDDING`, `VISION`, `SPEECH_TO_TEXT`,
  `TEXT_TO_SPEECH`, `CLASSIFICATION`, `RERANKER`, `MULTIMODAL`, `CUSTOM`؛
- `CAPABILITY_CODES`: generation، summarization، classification، extraction،
  translation، QA، recommendation، prediction، anomaly، document، meeting،
  task، KPI، retrieval، embedding و reranking؛
- `REQUEST_TYPES`: `GENERATE`, `SUMMARIZE`, `CLASSIFY`, `EXTRACT`, `PREDICT`,
  `RECOMMEND`, `ASK`, `EMBED`, `RERANK`, `TOOL`؛
- `REQUEST_STATUSES`: `PENDING → QUEUED → RUNNING → COMPLETED/FAILED/CANCELLED`؛
- `RESPONSE_STATUSES`: `COMPLETED`, `FAILED`, `VALIDATION_FAILED`؛
- `OUTPUT_CLASSIFICATIONS`: `ADVISORY`, `DRAFT`, `AUTOMATED`, `AUTHORITATIVE`؛
- `DATA_CLASSIFICATIONS`: `PUBLIC`, `INTERNAL`, `CONFIDENTIAL`, `RESTRICTED`؛
- `MEMORY_SCOPES`: `SHORT_TERM`, `LONG_TERM`, `CONVERSATION`, `TASK`, `AGENT`؛
- `KNOWLEDGE_STATUSES`: `PENDING`, `INDEXING`, `READY`, `FAILED`, `ARCHIVED`؛
- `EVALUATION_METHODS`: `MANUAL`, `AUTOMATIC`, `BATCH`؛
- `FEEDBACK_SENTIMENTS`: `POSITIVE`, `NEGATIVE`, `NEUTRAL`؛
- `TOOL_EXECUTION_STATUSES` و `AGENT_EXECUTION_STATUSES`؛
- `PRIORITIES`: `LOW`, `NORMAL`, `HIGH`, `CRITICAL`.

مقادیر `CUSTOM_*` برای Capability توسعه‌پذیر هستند، اما Code همچنان باید
قواعد نام‌گذاری Domain را رعایت کند.

### 3.2 Value Objectهای رفتاری

| Value Object | رفتار و قاعده |
|---|---|
| `ModelType` | فقط نوع مدل کنترل‌شده را قبول می‌کند |
| `CapabilityCode` | Code را normalize می‌کند و Capability استاندارد یا `CUSTOM_*` می‌پذیرد |
| `RequestType` / `RequestStatus` | نوع و وضعیت درخواست را validate می‌کنند |
| `OutputClassification` | جلوی مقدار خارج از چهار سطح Governance را می‌گیرد |
| `DataClassification` | سطح محرمانگی Context/Knowledge/Provider را validate می‌کند |
| `MemoryScope` | Scope حافظه را محدود و قابل جست‌وجو می‌کند |
| `TokenUsage` | Token منفی ممنوع و `totalTokens` مشتق‌شده است |
| `Money` | Decimal، مقدار غیرمنفی و Currency سه‌حرفی را enforce می‌کند |
| `CostRate` | Cost را بر اساس Token و نرخ input/output محاسبه می‌کند |
| `RetryPolicy` | تعداد تلاش، backoff و سقف delay را validate می‌کند |
| `ContextSource` | Domain/Entity/Id/Classification/authorization metadata را نگه می‌دارد |
| `JsonSchema` | قرارداد Schema ساختاری را به شکل provider-neutral نگه می‌دارد |

هیچ Value Objectی API، Provider یا Persistence را صدا نمی‌زند.

---

## 4. Entityها و Aggregate Boundary

### 4.1 Registry Aggregates

#### `AIProvider`

مالک تعریف Provider است، نه Business Domain. Invariantهای آن:

- `tenantId` و UUID معتبر؛
- `code` غیرخالی و طبق Code Grammar؛
- `name` و `providerType` اجباری؛
- `allowedDataClassifications` فقط از Vocabulary معتبر؛
- `configurationReference` فقط Reference است و Secret خام نیست؛
- Provider می‌تواند با `permitsClassifications()` Policy داده را بررسی کند.

#### `AIModel`

مدل به یک Provider تعلق دارد و شامل `modelType`، Version، Context Window،
Capabilityهای ورودی/خروجی، Streaming/Tools/Vision/Embedding و نرخ Token است.

- Context Window باید مثبت باشد؛
- نرخ Cost منفی ممنوع است؛
- Provider و Model با `providerId`/`tenantId` از هم جدا می‌مانند؛
- `costRate()` نرخ provider-neutral برای Usage تولید می‌کند؛
- قابلیت Model با `supportsCapability()` بررسی می‌شود.

#### `AICapability`

Capability مستقل از Provider و Model است. فعال‌بودن و معتبر بودن Request Type
را کنترل می‌کند؛ انتخاب Provider در B انجام نمی‌شود.

#### `AIPrompt` و `AIPromptVersion`

`AIPrompt` Aggregate Root است و Versionها childهای immutable مفهومی آن هستند:

- Version از ۱ شروع می‌شود؛
- Template خالی ممنوع است؛
- Variableها باید Identifier معتبر باشند؛
- Version قبلی overwrite نمی‌شود؛
- Prompt فقط یک `activeVersionId` را reference می‌کند؛
- `render()` فقط Variableهای اعلام‌شده را جایگزین می‌کند و Missing Variable را
  خطا می‌دهد.

### 4.2 Execution Aggregates

#### `AIOperation`

یک عملیات منطقی است که می‌تواند چند Request، retry و fallback داشته باشد.
`correlationId` و `traceId` در صورت عدم ارسال، در Domain تولید می‌شوند.

Stateهای مجاز:

```text
PENDING → RUNNING → COMPLETED
                    ↘ FAILED
                    ↘ CANCELLED
PENDING → CANCELLED
```

#### `AIRequest`

هر درخواست AI باید `tenantId`، `capabilityId`، `requestType`، Actor اختیاری،
Source reference، Priority، `correlationId` و `traceId` داشته باشد.

Stateهای مجاز:

```text
PENDING → QUEUED → RUNNING → COMPLETED
                            ↘ FAILED → QUEUED  (retry)
                            ↘ CANCELLED
PENDING → RUNNING
PENDING/QUEUED → CANCELLED
```

- انتقال غیرمجاز رد می‌شود؛
- Retry فقط از `FAILED` مجاز است؛
- `retryCount` منفی ممنوع است؛
- `contextTokenCount` منفی ممنوع است؛
- `parentRequestId` برای زنجیرهٔ Operation نگه داشته می‌شود؛
- `idempotencyKey` در Domain ثبت می‌شود و enforcement آن در P انجام می‌شود.

#### `AIResponse`

Response به Request، Model و Provider متصل است و می‌تواند Content و
`structuredData` نگه دارد.

- Status و Output Classification کنترل‌شده‌اند؛
- Tokenهای ورودی/خروجی منفی نیستند؛
- `totalTokens = inputTokens + outputTokens`؛
- `latencyMs` منفی نیست؛
- Schema Validation از طریق Domain Rule قابل فراخوانی است؛
- `promptVersionId` برای reproducibility حفظ می‌شود.

### 4.3 Context, Knowledge & Retrieval Aggregates

#### `AIContext`

Context حاصل جمع‌آوری Sourceهای مجاز است. `enforceLimit()` سقف Character و
Token را اعمال می‌کند. Context باید قبل از Provider Filtering شده باشد.

#### `AIKnowledgeItem` و `AIKnowledgeChunk`

Knowledge به Source Domain/Entity reference می‌دهد و Business Record را کپی
نمی‌کند.

- Classification اجباری است؛
- Lifecycle: `PENDING → INDEXING → READY/FAILED`؛
- `READY/FAILED → INDEXING` برای re-index؛
- `ARCHIVED` نهایی است؛
- Chunk دارای Item، Ordinal، Content و Token Count است؛
- Content خالی و Ordinal/Token منفی ممنوع است.

#### `AIEmbedding`

Embedding با Source، Model و Vector نگه‌داری می‌شود؛ Dimension باید با طول Vector
برابر باشد و Vector خالی مجاز نیست.

#### `AIRetrieval`

سه مجموعه را عمداً جدا نگه می‌دارد:

```text
candidates → authorizedCandidates → selectedCandidates
```

هرگز Candidate خام مستقیماً به Prompt/LLM ارسال نمی‌شود؛ Authorization باید
قبل از `select()` انجام شود.

### 4.4 Governance Aggregates

- `AIUsage`: Token و زمان‌های Queue/Context/Provider/Validation/Total؛
- `AICost`: Decimal Cost و Currency متصل به Usage؛
- `AIFeedback`: Rating بین ۱ تا ۵ و Sentiment کنترل‌شده؛
- `AIEvaluation`: روش Manual/Automatic/Batch و Metrics نرمال‌شدهٔ ۰ تا ۱؛
- `AIAuditRecord`: Actor، Provider، Model، Prompt Version، Sourceهای Context،
  Classification و Metadata redacted؛
- `AIMemory`: Tenant/User/Scope/Key/Value/Version/Expiry و ایجاد Version جدید؛
- `AITool` و `AIToolExecution`: تعریف Tool و Lifecycle اجرای کنترل‌شده؛
- `AIAgent` و `AIAgentExecution`: Identity، Instruction، Capability/Tool،
  Context/Model/Permission/Execution Policy و Lifecycle اجرای Agent.

---

## 5. Tenant و Security Invariants

تمام Entityهای B که دادهٔ عملیاتی یا Governance دارند باید Tenant-aware باشند.
حداقل این موارد `tenantId` دارند:

```text
AIProvider, AIModel, AICapability, AIPrompt, AIPromptVersion,
AIOperation, AIRequest, AIResponse, AIContext, AIUsage, AICost,
AIMemory, AIKnowledgeItem, AIKnowledgeChunk, AIEmbedding, AIRetrieval,
AIFeedback, AIEvaluation, AIAuditRecord, AITool, AIToolExecution,
AIAgent, AIAgentExecution
```

قواعد:

1. ID به‌تنهایی مجوز دسترسی نیست؛ Repository و Application باید Tenant را
   enforce کنند؛
2. Source با `allowed=False` هرگز Context معتبر نیست؛
3. Provider بدون Policy صریح نباید Confidential/Restricted را به External
   Provider بفرستد؛
4. `AUTHORITATIVE` بدون Authorization صریح مجاز نیست؛
5. Tool بدون Permission و Approval مجاز نیست؛
6. Memory جایگزین Source of Truth Business Domain نیست؛
7. Audit Metadata باید قبل از ذخیره Secretها را Redact کند.

---

## 6. خطاهای Domain

خطاهای پایدار زیر تعریف شده‌اند تا Adapter/Provider Exception به API نشت نکند:

- `AIProviderUnavailable`؛
- `AIModelUnavailable`؛
- `AIRequestTimeout`؛
- `AIQuotaExceeded`؛
- `AITokenLimitExceeded`؛
- `AIContextTooLarge`؛
- `AIOutputValidationFailed`؛
- `AIPermissionDenied`؛
- `AIProviderRateLimited`؛
- `AIPromptNotFound`؛
- `AIIdempotencyConflict`؛
- `AIToolDenied`؛
- `AIConfigurationError`.

این خطاها Code و HTTP mapping پیشنهادی دارند؛ Mapping نهایی به Response Envelope
در زیر‌فاز Z انجام می‌شود.

---

## 7. فایل‌های پیاده‌سازی B

```text
backend/apps/ai/domain/
├── __init__.py
├── entities/
│   ├── __init__.py
│   └── aiRecords.py
├── exceptions.py                         # compatibility surface
├── exceptions/
│   ├── __init__.py
│   └── aiExceptions.py
├── policies/
│   ├── __init__.py
│   └── aiPolicies.py
├── services/
│   ├── __init__.py
│   └── aiRules.py
└── valueObjects/
    ├── __init__.py
    └── aiTypes.py
```

فایل تست:

```text
backend/tests/unit/testPhase13Domain.py
```

`ports.py` موجودِ قبلی به‌عنوان مرجع ابتدایی نگه داشته شده و Provider Port کامل
در زیر‌فاز C تکمیل می‌شود؛ B به هیچ Adapter یا SDK وابسته نیست.

---

## 8. تست و Verification Matrix

| گروه | پوشش B |
|---|---|
| Value Object | نوع مدل، Capability، Classification، Token، Money، Retry |
| Provider/Model/Capability | Tenant، Code Grammar، active capability و cost |
| Lifecycle | Operation و Request transition و retry |
| Response | Token consistency و classification |
| Prompt | Immutable version contract، render و missing variable |
| Context | Classification، authorized flag و size limit |
| Knowledge/Retrieval | Lifecycle، Chunk، Dimension و authorized selection |
| Usage/Governance | Cost، Feedback، Evaluation و Audit |
| Tool/Agent | تعریف و اجرای lifecycle |
| Security | Tenant fields، Provider Policy، Quota، Tool Approval و redaction |
| Architecture | Compile و نبود import Framework/Vendor در Domain |

تست‌های B باید بدون اینترنت، Secret، Database و Provider واقعی اجرا شوند.

---

## 9. Acceptance Criteria و Exit Gate

- [x] تمام مفاهیم Domain اصلی Phase 13 در Entityهای pure ثبت شده‌اند؛
- [x] Vocabularyهای §§8–9 و وضعیت‌های Lifecycle کنترل شده‌اند؛
- [x] تمام Entityهای عملیاتی Tenant-aware هستند؛
- [x] Prompt Versioning و Render Contract تعریف شده است؛
- [x] Request/Operation/Knowledge/Tool/Agent State Machine دارند؛
- [x] Response Token Invariant و Output Classification enforce شده است؛
- [x] Context Source و Retrieval سه‌مرحله‌ای، مرز Permission را حفظ می‌کنند؛
- [x] Cost با Decimal و Token Usage تعریف شده است؛
- [x] Domain Errorهای Provider-neutral تعریف شده‌اند؛
- [x] هیچ Domain import از Django/DRF/HTTP/Redis/Channels/SDK ندارد؛
- [x] تست‌های pure B سبز هستند؛
- [x] کارهای B در Docs ثبت شده‌اند؛
- [x] Provider Adapter، ORM و API عمداً وارد B نشده‌اند.

**نتیجه:** `GREEN — Phase 13-C may begin.`

---

## 10. کارهایی که به C واگذار می‌شوند

- قرارداد نهایی `AIProviderPort`؛
- `GenerationResult`، Streaming، Structured Generation، Embed و Token Count؛
- Provider Capability handshake؛
- تبدیل Provider-specific error به خطاهای B؛
- Test Provider به‌عنوان Adapter در Infrastructure؛
- تست Contract برای Adapterها.
