# Phase 13-C — Provider Port & Provider Contract

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** C از A تا Z  
**وضعیت:** COMPLETED — Provider Contract Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد B:** [`Phase13-B.md`](Phase13-B.md)  
**گزارش اجرا:** [`Phase13-C-ExecutionReport.md`](Phase13-C-ExecutionReport.md)

---

## 1. هدف

C مرز رسمی بین AI Domain/Application و Provider Adapterهای Infrastructure را
پیاده‌سازی می‌کند. هر Provider واقعی در زیر‌فازهای بعدی فقط از این Contract
استفاده خواهد کرد و هیچ نوع پاسخ، Exception یا SDK-specific object خود را به
Application/Domain نشت نمی‌دهد.

C این موارد را تحویل می‌دهد:

- `AIProviderPort` به‌صورت Python `Protocol`؛
- Contract ورودی Generation؛
- Contract خروجی Generation؛
- Structured Generation و JSON Schema boundary؛
- Streaming chunk contract؛
- Embedding و Batch Embedding contract؛
- Token Counting contract؛
- Provider Capability Handshake؛
- Health Snapshot contract؛
- Tenant/Trace/Correlation/Idempotency context؛
- validation و normalization خروجی Adapter؛
- Offline Deterministic Provider برای تست Contract؛
- Compatibility با API سادهٔ قبلی `generate(prompt=..., model=...)` و
  `embed(text=..., model=...)`.

---

## 2. مرز Scope

### داخل Scope C

- تعریف Port و داده‌های provider-neutral؛
- تعریف دقیق انواع عملیات قابل پشتیبانی؛
- validation ورودی/خروجی در مرز Port؛
- قابلیت‌های Generation، Structured Generation، Stream، Embedding و Token Count؛
- Health Check غیرحساس؛
- تست Adapter Contract با Provider قطعی و Offline؛
- حفظ backward compatibility برای مصرف‌کنندهٔ موجود.

### خارج از Scope C

- OpenAI، Azure، Ollama، Anthropic یا هر Adapter واقعی؛
- انتخاب Provider و Model و Routing؛
- Retry/Timeout/Fallback Executor؛
- Queue/Worker/Async orchestration؛
- ORM، Migration، Repository و Database؛
- API، Serializer و HTTP Response Envelope؛
- محاسبهٔ Cost و Usage persistence؛
- اجرای واقعی Network یا Secret Store.

این موارد به D تا Z واگذار شده‌اند.

---

## 3. جایگاه معماری

```text
Business/Application Service
          │
          ▼
  GenerationRequest / ProviderRequestContext
          │
          ▼
     AIProviderPort  ← این زیر‌فاز
          │
          ▼
  Provider-neutral Result / Chunk / Health
          │
          ▼
Infrastructure Adapter
(OpenAI / Azure / Ollama / Local / ... در مراحل بعد)
```

قواعد وابستگی:

1. Domain/Application فقط Port و Contractهای این سند را می‌شناسند؛
2. Adapter می‌تواند SDK یا HTTP داشته باشد، اما فقط در Infrastructure؛
3. Core AI هیچ Vendor را import یا hard-code نمی‌کند؛
4. Adapter باید پاسخ خود را به `GenerationResult`، `GenerationChunk`،
   `EmbeddingResult` یا Contract معادل normalize کند؛
5. Exception خام Provider نباید از Port عبور کند؛ Mapping نهایی در L/M انجام
   می‌شود؛
6. Context Tenant/Trace باید در هر عملیات حساس به Adapter تحویل شود؛
7. Health نباید Secret، API Key، Token یا متن Prompt را برگرداند.

---

## 4. Contractهای داده

### 4.1 `ProviderRequestContext`

Context مشترک بین Application و Adapter است:

| فیلد | قاعده |
|---|---|
| `tenantId` | اجباری و UUID معتبر |
| `requestId` | UUID اختیاری برای اتصال به `AIRequest` |
| `operationId` | UUID اختیاری برای عملیات چندمرحله‌ای |
| `correlationId` | اگر ارسال نشود در Domain تولید می‌شود |
| `traceId` | اگر ارسال نشود در Domain تولید می‌شود |
| `idempotencyKey` | برای عملیات حساس/تکرارشونده باید ارسال شود؛ در عملیات ساده اختیاری است |

این object `frozen` است و Secret یا API Key در آن تعریف نشده است.

### 4.2 `GenerationRequest`

ورودی provider-neutral برای Generation و Structured Generation:

| فیلد | قاعده |
|---|---|
| `prompt` | String غیرخالی |
| `model` | نام/Code مدل، غیرخالی و بدون تفسیر Vendor در Port |
| `systemInstruction` | متن اختیاری |
| `temperature` | عدد finite و غیرمنفی |
| `maxTokens` | اختیاری، در صورت وجود Positive Integer |
| `responseFormat` | فقط `TEXT` یا `JSON` |
| `jsonSchema` | object؛ برای JSON در اختیار Adapter قرار می‌گیرد |
| `stopSequences` | tuple از توقف‌های اختیاری |
| `context` | `ProviderRequestContext` اختیاری برای سازگاری با callهای ساده |
| `metadata` | metadata غیرحساس و provider-neutral |

مقدارهای Vendor-specific مثل `topP`، `frequencyPenalty` یا `logprobs` از طریق
`metadata/kwargs` قابل عبور برای Adapter آینده هستند، اما Core Domain به آن‌ها
وابسته نیست.

### 4.3 `GenerationResult`

خروجی نرمال‌شده:

- `content`؛
- `structuredData`؛
- `inputTokens` و `outputTokens`؛
- `totalTokens` به‌صورت property مشتق‌شده؛
- `model` و `provider`؛
- `finishReason`: `STOP`, `LENGTH`, `TOOL_CALL`, `CONTENT_FILTER`, `ERROR`,
  `UNKNOWN`؛
- `requestId`، `correlationId` و `traceId`؛
- `metadata` غیرحساس.

Result `frozen` است، Token منفی را رد می‌کند و Finish Reason را normalize می‌کند.

### 4.4 `GenerationChunk`

هر آیتم Stream شامل موارد زیر است:

- متن همان بخش در `content`؛
- `index` غیرمنفی؛
- `isFinal`؛
- Finish Reason نرمال‌شده؛
- Model/Provider؛
- Request/Correlation/Trace identifiers.

Port خروجی Stream را `Iterable[GenerationChunk]` تعریف می‌کند تا Adapterهای
sync فعلی بدون تحمیل Event Loop کار کنند. Async/Queue به P واگذار شده است.

### 4.5 `EmbeddingResult`

Contract غنی برای Adapterهایی که علاوه بر Vector به metadata نیاز دارند:

- `vector` غیرخالی و finite؛
- `dimensions` برابر طول Vector؛
- `inputTokens` غیرمنفی؛
- Model، Provider و Request ID اختیاری.

برای backward compatibility، متد اصلی `embed()` همچنان `list[float]` برمی‌گرداند؛
`validateEmbeddingVector()` برای normalize کردن آن به Contract غنی وجود دارد.

### 4.6 `ProviderCapabilities`

Handshake قابلیت‌ها:

```text
GENERATION
STRUCTURED_GENERATION
STREAMING
EMBEDDING
TOKEN_COUNTING
TOOLS
VISION
```

فیلدهای تکمیلی:

- `providerCode`؛
- `maxContextWindow` اختیاری؛
- `supportsTemperature`؛
- `supportsJsonSchema`؛
- `supportsBatchEmbedding`.

Invariantها:

- Structured JSON فقط با `STRUCTURED_GENERATION` معتبر است؛
- `supportsJsonSchema=True` بدون Structured Generation مجاز نیست؛
- Batch Embedding فقط با Embedding capability معتبر است؛
- Feature نامشخص رد می‌شود و Feature check قبل از call انجام می‌شود.

### 4.7 `ProviderHealth`

Health Snapshot فقط دادهٔ غیرحساس دارد:

- `HEALTHY`، `DEGRADED`، `UNAVAILABLE` یا `UNKNOWN`؛
- زمان بررسی؛
- latency غیرمنفی اختیاری؛
- detail غیرحساس.

---

## 5. متدهای `AIProviderPort`

| متد | قرارداد | نتیجه |
|---|---|---|
| `generate()` | Prompt، Model و گزینه‌های عمومی | `GenerationResult` |
| `generateRequest()` | Canonical `GenerationRequest` | `GenerationResult` |
| `generateStructured()` | Prompt، Model و JSON Schema اجباری | `GenerationResult` با `structuredData` |
| `stream()` | Prompt و Model | `Iterable[GenerationChunk]` |
| `embed()` | Text و Embedding Model | `list[float]` برای compatibility |
| `embedBatch()` | مجموعهٔ Textها | `list[list[float]]` |
| `countTokens()` | Text و Model | `int` غیرمنفی |
| `healthCheck()` | Model اختیاری | `ProviderHealth` |
| `capabilities` | Feature handshake | `ProviderCapabilities` |
| `providerCode` | شناسهٔ Adapter | `str` |

### 5.1 Generate

`generate()` باید:

1. ورودی را به Contract معتبر تبدیل کند؛
2. Tenant/Trace context را در صورت وجود به Adapter منتقل کند؛
3. پاسخ Provider را به `GenerationResult` تبدیل کند؛
4. Tokenها و Finish Reason را validate کند؛
5. Exception Vendor را مستقیماً return/raise نکند؛
6. Model/Provider mismatch را پیش از Application تشخیص دهد.

### 5.2 Structured Generation

`generateStructured()` دارای `jsonSchema` اجباری است. Port فقط Contract را حمل و
validation پایه می‌کند؛ validation معنایی کامل Structured Output با Domain Rule
زیر‌فاز H هماهنگ می‌شود.

### 5.3 Streaming

Adapter باید sequence قابل مصرف ارائه دهد. Chunk آخر باید `isFinal=True` و
Finish Reason نهایی داشته باشد. Port در C جریان را ذخیره، retry یا queue نمی‌کند.

### 5.4 Embedding

Vector باید non-empty و finite باشد. در صورت نیاز، Consumer می‌تواند با
`EmbeddingResult` ابعاد و metadata را validate کند. Vector normalization یا
Indexing واقعی به Q/R منتقل می‌شود.

### 5.5 Token Counting

`countTokens()` قرارداد شمارش است، نه الزاماً الگوریتم مشترک. دقت واقعی مدل-
specific در N/L قابل پیاده‌سازی است؛ خروجی Port در هر حال باید integer غیرمنفی
باشد.

---

## 6. Deterministic Provider

`DeterministicAIProvider` یک Test Double کاملاً Offline است:

- هیچ Network یا API Key نمی‌خواهد؛
- Generation تکرارپذیر تولید می‌کند؛
- Structured JSON ساده تولید می‌کند؛
- Stream را از همان Generation بازسازی می‌کند؛
- Embedding هشت‌بعدی deterministic تولید می‌کند؛
- Batch Embedding، Token Count و Health را پشتیبانی می‌کند؛
- برای تست Capability/Contract قابل استفاده است.

مسیر Infrastructure برای کشف تست:

```text
backend/apps/ai/infrastructure/providers/deterministic.py
```

این فایل همان Test Double provider-neutral را re-export می‌کند. علت حفظ نام
قدیمی در `domain.ports`، جلوگیری از شکستن مصرف‌کنندهٔ موجود در Phase 13 است؛
هیچ Provider تجاری یا SDK در Domain اضافه نشده است.

---

## 7. Validation و Error Boundary

### ورودی

موارد زیر قبل از Adapter call رد می‌شوند:

- Prompt خالی؛
- Model خالی؛
- Temperature منفی، غیرfinite یا Boolean؛
- Max Tokens صفر، منفی یا غیرinteger؛
- Response Format ناشناخته؛
- Tenant/Request/Operation UUID نامعتبر؛
- Feature یا Health status ناشناخته.

### خروجی

موارد زیر در مرز Contract رد می‌شوند:

- Token منفی یا غیرinteger؛
- Finish Reason ناشناخته؛
- Provider/Model نامنطبق با Request؛
- Embedding خالی، non-finite یا Dimension نامعتبر؛
- Stream index منفی؛
- Health latency منفی.

Exceptionهای نهایی که Adapterهای آینده باید به آن‌ها map کنند در B تعریف شده‌اند:
`AIProviderUnavailable`، `AIModelUnavailable`، `AIRequestTimeout`،
`AIProviderRateLimited`، `AIOutputValidationFailed` و موارد مرتبط. Exception
خام SDK نباید از Infrastructure عبور کند.

---

## 8. Tenant، Security و Observability

1. Port به‌صورت پیش‌فرض Provider را Tenant-blind نمی‌کند؛ Context دارای Tenant
   اجباری است؛
2. `correlationId` و `traceId` برای Traceability تولید یا عبور داده می‌شوند؛
3. عملیات حساس باید `idempotencyKey` داشته باشند؛ enforcement persistence در P/Z؛
4. Context شامل Secret نیست؛ Secret فقط از طریق Secret Store و در Adapter آینده
   resolve می‌شود؛
5. Health/metadata نباید Prompt، Token، API Key یا محتوای محرمانه را log کند؛
6. Usage، Cost و Audit در B/N/O مصرف‌کنندهٔ Result هستند، نه مسئولیت Port؛
7. Provider Port هیچ Cross-Tenant lookup، Permission decision یا Database query
   انجام نمی‌دهد.

---

## 9. Backward Compatibility

Contract C API جدید را اضافه می‌کند، اما callهای موجود زیر را حفظ می‌کند:

```python
provider.generate(prompt="hello", model="test")
provider.embed(text="hello", model="test")
```

همچنین موارد زیر به‌صورت رسمی اضافه شدند:

```python
provider.generateRequest(GenerationRequest(...))
provider.generateStructured(prompt="...", model="...", jsonSchema={...})
provider.stream(prompt="...", model="...")
provider.embedBatch(texts=("...", "..."), model="...")
provider.countTokens(text="...", model="...")
provider.healthCheck(model="...")
```

---

## 10. فایل‌های پیاده‌سازی

```text
backend/apps/ai/domain/ports.py
backend/apps/ai/infrastructure/providers/deterministic.py
backend/tests/unit/testPhase13ProviderPort.py
```

Documentation:

```text
docs/Phases/Phase13/Phase13-C.md
docs/Phases/Phase13/Phase13-C-ExecutionReport.md
```

فایل‌های B که C روی Contract آن‌ها تکیه دارد، بدون ورود به Provider SDK باقی
مانده‌اند.

---

## 11. Acceptance Criteria

- [x] `AIProviderPort` به‌صورت Protocol تعریف شد؛
- [x] Generate و Structured Generate contract شدند؛
- [x] Streaming chunk contract تعریف شد؛
- [x] Embedding و Batch Embedding contract شدند؛
- [x] Token Counting contract تعریف شد؛
- [x] Capability و Health handshake تعریف شد؛
- [x] Tenant/Trace/Correlation context تعریف شد؛
- [x] Idempotency context برای عملیات حساس فراهم شد؛
- [x] ورودی/خروجی Contract validation دارد؛
- [x] Provider-specific object در Contract نشت نمی‌کند؛
- [x] Deterministic Provider برای تست Offline موجود است؛
- [x] Compatibility با `generate` و `embed` قبلی حفظ شد؛
- [x] هیچ Vendor SDK در Domain وارد نشد؛
- [x] تست‌های pure C سبز هستند؛
- [x] مستندات Scope، تصمیم، خطا، تست و محدودیت ثبت شده‌اند؛
- [x] Provider واقعی، Routing، Retry، Queue و Persistence به مراحل درست واگذار
  شده‌اند.

**نتیجه:** `GREEN — Phase 13-D may begin.`
