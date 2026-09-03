# Phase 13-H — Response و Structured Output

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** H از A تا Z  
**وضعیت:** COMPLETED — Response/Structured Output Gate GREEN  
**تاریخ:** 2026-09-03  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**قرارداد قبلی:** [`Phase13-G.md`](Phase13-G.md)  
**گزارش اجرا:** [`Phase13-H-ExecutionReport.md`](Phase13-H-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز H خروجی AI را از یک String ساده فراتر می‌برد و یک Response boundary
قابل اعتبارسنجی، Tenant-aware، Provider-agnostic و امن ایجاد می‌کند. H از
Entity `AIResponse` فاز B استفاده می‌کند و آن را با یک Service in-memory برای
ثبت Response و یک Contract مستقل برای Structured Output compose می‌کند.

H به این سؤال پاسخ می‌دهد:

> چگونه Response دریافت‌شده از هر Provider را قبل از تحویل یا ثبت canonical،
> به‌صورت مستقل از Vendor normalize و validate کنیم، ارتباط آن با Request را
> حفظ کنیم، خروجی نامعتبر را deliver نکنیم و در عین حال محتوای حساس را از
> Read Model و خطاهای Domain خارج نگه داریم؟

H هیچ Provider را صدا نمی‌زند. Provider Adapter آینده فقط دادهٔ خام را به این
boundary می‌دهد؛ H آن را به متن یا object JSON تبدیل، schema را بررسی و در صورت
موفقیت `AIResponse` ثبت می‌کند.

---

## 2. Scope و Non-Scope

### داخل Scope

- مصرف Entity واقعی `AIResponse` از B؛
- `AIResponseService` به‌عنوان Response registry/coordinator pure و in-memory؛
- Tenant-aware registration، lookup و listing Response؛
- اتصال Response به Request موجود در G در صورت compose شدن با
  `RequestLifecycleService`؛
- رد کردن Request ناشناخته، Tenant دیگر یا Request لغوشده؛
- پشتیبانی از Response متن و Response ساختاریافته؛
- parse کردن JSON string و normalize کردن Mapping به object JSON؛
- object-root contract سازگار با `AIResponse.structuredData: dict`؛
- `StructuredOutputSchema` immutable با name و version؛
- validation بدون dependency خارجی برای subset مشخص JSON Schema؛
- Validation issueهای path/keyword/message بدون echo کردن payload؛
- `anyOf`، `oneOf` و `allOf` و validation تو‌در‌توی object/array؛
- type، required، properties، additionalProperties، enum، const، pattern،
  حداقل/حداکثر طول، item، property و range؛
- fingerprint امن برای Schema؛
- جلوگیری از ثبت Response موفق پیش از validation؛
- ثبت `VALIDATION_FAILED` بدون نگهداری payload نامعتبر؛
- Response `FAILED` با error code پایدار؛
- کنترل `AUTHORITATIVE` با authorization صریح؛
- token count، latency و consistency از Contract B؛
- immutable و non-sensitive `ResponseDescriptor`؛
- duplicate response ID و Tenant isolation؛
- Pure Unit Test و regression کامل B تا H؛
- Documentation، Purity، Compile، Archive و Verification.

### خارج از Scope

- Provider SDK، Adapter، Network و actual inference؛
- Prompt، Prompt Version و Schema ownership دائمی؛ این موارد در I هستند؛
- ORM، Database، Migration، Repository durable و transaction توزیع‌شده؛
- Queue، Worker، Async execution و Streaming transport؛
- Retry، Timeout، Failover و انتخاب Response canonical در چند attempt؛
- Usage aggregation، Cost، Quota، Audit persistence و Monitoring؛
- Authorization کامل User/Role؛ H فقط authorization صریح برای classification
  `AUTHORITATIVE` را به‌صورت input boundary enforce می‌کند و K/Application مالک
  تصمیم permission است؛
- فایل، URL، HTML rendering یا اجرای Tool؛
- نگهداری Secret، API Key، token یا Provider configuration؛
- پشتیبانی از تمام draftهای JSON Schema مانند `$ref`، `not`، `contains` و
  `format`های semantic؛ subset پشتیبانی‌شده در این سند دقیق است.

---

## 3. جایگاه معماری

```text
Provider Adapter آینده (raw text / raw JSON)
                     │
                     ▼
           AIResponseService (H)
              ┌──────┴──────┐
              ▼             ▼
       normalize text   StructuredOutputSchema
              │             │
              └──────┬──────┘
                     ▼
                AIResponse (B)
                     │
                     ▼
      ResponseDescriptor / Application delivery
```

اتصال به زیر‌فازهای قبلی:

```text
AIRequest (B/G) ── tenant + request ownership ──► ResponseService (H)
Capability/Model/Provider IDs (B–F) ────────────► AIResponse (B)
Operation correlation/trace (G) ────────────────► Safe ResponseDescriptor (H)
```

مرز مالکیت:

| مفهوم | مالک |
|---|---|
| Response Entity و token consistency | `AIResponse` در B |
| Request ownership و Request lifecycle | `RequestLifecycleService` در G |
| Structured Output validation | `StructuredOutputSchema` در H |
| Response registration/read model | `AIResponseService` در H |
| Prompt output schema ownership/version | I |
| Provider raw response adaptation | L |
| Retry/Timeout/Failover attempts | M |
| Usage/Cost/Latency aggregation | N |
| Audit و Governance | O |
| Async/Streaming transport | P |

---

## 4. Response Contract

### 4.1 Entity موجود B

`AIResponse` حداقل این داده‌ها را نگه می‌دارد:

- `tenantId`؛
- `requestId`؛
- `modelId` و `providerId`؛
- `status`؛
- `content`؛
- `structuredData`؛
- `inputTokens`، `outputTokens` و `totalTokens`؛
- `latencyMs`؛
- `outputClassification`؛
- `promptVersionId` اختیاری؛
- `errorCode`؛
- `createdAt`.

B در constructor، UUIDها، status، classification، token consistency و latency
را validate می‌کند. H این Contract را تکرار نمی‌کند و فقط Response boundary و
Structured Output را به آن اضافه می‌کند.

### 4.2 Response status

Vocabulary فعلی B/H:

| Status | مفهوم |
|---|---|
| `COMPLETED` | خروجی قابل تحویل و validation‌شده |
| `FAILED` | Provider/application خروجی قابل تحویل تولید نکرده و error code ثبت شده |
| `VALIDATION_FAILED` | دادهٔ خام دریافت شده اما schema/JSON validation شکست خورده است |

`COMPLETED` بدون متن و بدون Structured Object رد می‌شود. `FAILED` و
`VALIDATION_FAILED` باید error code غیرخالی داشته باشند. Payload نامعتبر در
Response validation failure نگهداری نمی‌شود.

### 4.3 Text Response

Text Response نیازمند Schema نیست:

```python
response = responseService.createResponse(
    tenantId,
    requestId,
    modelId,
    providerId,
    content="validated text",
    inputTokens=10,
    outputTokens=25,
    latencyMs=120,
)
```

قواعد:

- `content` باید String باشد؛
- Response موفق باید content غیرخالی یا Structured Object داشته باشد؛
- String خالی و Structured Object خالی، به‌صورت همزمان، خروجی قابل تحویل نیست؛
- متن در `ResponseDescriptor` قرار نمی‌گیرد و فقط `contentPresent` ثبت می‌شود؛
- H متن را HTML، Markdown، Command یا Tool instruction فرض نمی‌کند.

### 4.4 Structured Response

```python
schema = StructuredOutputSchema(
    {
        "type": "object",
        "required": ["summary", "risks"],
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "risks": {"type": "array", "items": {"type": "string"}},
        },
    },
    name="project-summary",
    version="2",
)

response = responseService.createResponse(
    tenantId,
    requestId,
    modelId,
    providerId,
    structuredData='{"summary":"Ready","risks":[]}',
    structuredOutputSchema=schema,
)
```

فرآیند:

```text
Raw JSON string / Mapping
          ↓
JSON parsing and JSON-type normalization
          ↓
Object-root enforcement
          ↓
Schema validation
          ↓
AIResponse(status=COMPLETED)
          ↓
In-memory registration / future delivery
```

`AIResponse.structuredData` در B از نوع object است؛ بنابراین H برای سازگاری با
Entity فعلی، root آرایه یا scalar را به‌عنوان Structured Response قبول نمی‌کند.
آرایه و scalar در propertyهای داخلی Schema مجاز هستند.

---

## 5. StructuredOutputSchema Contract

### 5.1 Immutability و Version

`StructuredOutputSchema` شامل این موارد است:

- `schema`؛
- `name`؛
- `version`.

Schema در زمان ساخت recursively freeze می‌شود و `asDict()` یک representation
قابل استفاده برای adapter می‌دهد. Fingerprint با SHA-256 روی name، version و
canonical schema ساخته می‌شود؛ محتوا یا payload Response در آن وجود ندارد.

Schema به‌صورت Tenant-neutral در H نگه داشته می‌شود. مالکیت دائمی Schema،
فعال‌سازی نسخه و اتصال به Prompt Version در I تعریف خواهد شد.

### 5.2 JSON Schema keywords پشتیبانی‌شده

H این subset dependency-free را validate می‌کند:

#### Type و shape

```text
type: object | array | string | number | integer | boolean | null
```

`type` می‌تواند فهرستی از typeها نیز باشد. برای object:

```text
required
properties
additionalProperties: true | false | schema
minProperties
maxProperties
```

برای array:

```text
items
minItems
maxItems
```

#### Scalar constraints

```text
enum
const
minLength
maxLength
pattern
minimum
maximum
```

`number` finite بودن را enforce می‌کند و Boolean را به‌عنوان Integer/Number
قبول نمی‌کند.

#### Combinators

```text
allOf   همهٔ branchها باید معتبر باشند
anyOf   حداقل یک branch باید معتبر باشد
oneOf   دقیقاً یک branch باید معتبر باشد
```

Validation برای propertyها و itemهای nested نیز recursive است.

### 5.3 Schema Definition Validation

در زمان ساخت Schema این موارد reject می‌شوند:

- Root غیر-object؛
- type ناشناخته یا خالی؛
- `required` غیرلیست یا شامل non-string؛
- `properties` غیر-object؛
- child schema غیر-object؛
- `items` یا combinator نامعتبر؛
- enum غیرلیست؛
- pattern غیررشته‌ای یا Regex نامعتبر؛
- min/max منفی یا غیرinteger؛
- minimum/maximum غیرعددی یا non-finite؛
- name/version خالی.

Keywordهای ناشناخته برای forward compatibility حذف نمی‌شوند و validation آن‌ها
را ادعا نمی‌کند. Keywordهای semantic مانند `format` در این Gate enforce
نمی‌شوند. در صورت نیاز به full JSON Schema، adapter آینده باید قبل از delivery
Validator کامل داشته باشد و نتیجهٔ H را bypass نکند.

---

## 6. Normalization و Validation Failure

### 6.1 ورودی قابل قبول

`normalizeStructuredOutput` این ورودی‌ها را قبول می‌کند:

- Mapping با keyهای String؛
- JSON string که object root دارد؛
- list/tuple در propertyهای nested؛
- String، Integer، finite Float، Boolean و null در جای درست JSON.

Tupleهای nested به List JSON normalize می‌شوند. Decimal، UUID، DateTime، NaN،
Infinity، Object سفارشی و key غیرString رد می‌شوند.

### 6.2 Validation Issue

هر Issue immutable و غیرحساس است:

```text
ValidationIssue(
    path="$.risks[0]",
    keyword="type",
    message="Expected string",
)
```

Issue هرگز مقدار actual، prompt، token، Secret یا payload را در message قرار
نمی‌دهد. path برای debugging ساختاری کافی است.

### 6.3 رفتار خروجی نامعتبر

در `status=COMPLETED`:

- parse/normalization شکست‌خورده → `AIStructuredOutputInvalid`؛
- schema شکست‌خورده → `AIStructuredOutputInvalid` با tuple Issue؛
- Response در Registry ثبت نمی‌شود؛
- هیچ payload ناقصی به‌عنوان موفقیت تحویل نمی‌شود.

برای ثبت یک failure قابل مشاهده:

```python
responseService.createResponse(
    tenantId,
    requestId,
    modelId,
    providerId,
    status="VALIDATION_FAILED",
    structuredData=rawInvalidData,
    structuredOutputSchema=schema,
)
```

در این حالت:

- status برابر `VALIDATION_FAILED` است؛
- `errorCode` پیش‌فرض `AI_STRUCTURED_OUTPUT_INVALID` است؛
- `structuredData` ذخیره‌شده `{}` است؛
- اطلاعاتی مانند تعداد/مسیر Issue فقط در internal registration است و payload
  نامعتبر expose نمی‌شود؛
- Descriptor فقط `hasStructuredData=True` و `structuredOutputValidated=False`
  را نشان می‌دهد.

---

## 7. ResponseService API

### Creation

```text
createResponse(
    tenantId,
    requestId,
    modelId,
    providerId,
    content="...",
    structuredData=...,
    structuredOutputSchema=...,
    status=...,
    outputClassification=...,
    promptVersionId=...,
    inputTokens=...,
    outputTokens=...,
    totalTokens=...,
    latencyMs=...,
    errorCode=...,
    responseId=...,
    authorized=...,
)
```

پارامتر `schema` alias سازگار برای `structuredOutputSchema` است؛ ارسال همزمان
هر دو خطای Domain می‌دهد.

### Registration و Read

| API | رفتار |
|---|---|
| `registerResponse(response, ...)` | ثبت Entity موجود B پس از validation |
| `getResponse(tenantId, responseId)` | Entity در scope Tenant |
| `describeResponse(tenantId, responseId)` | Safe immutable descriptor |
| `listResponses(tenantId, requestId=None, status=None)` | List فیلترشده و Tenant-aware |
| `responseCount(tenantId, requestId=None)` | تعداد Responseهای همان scope |
| `validateStructuredOutput(value, schema)` | normalize، validate و بازگرداندن `StructuredOutput` |
| `register(response, ...)` | alias ثبت |
| `get(tenantId, responseId)` | alias خواندن |

یک Request می‌تواند چند Response record داشته باشد تا Attempt/Provider result
در Phaseهای M و N قابل مدل‌سازی باشد؛ H canonical winner یا deduplicate کردن
Responseهای چند attempt را انجام نمی‌دهد.

### ResponseDescriptor

Descriptor شامل موارد غیرحساس زیر است:

- Tenant، Response، Request، Model و Provider ID؛
- status؛
- وجود content و structured data؛
- validated بودن Structured Output؛
- schema fingerprint؛
- output classification و prompt version ID؛
- token counts و latency؛
- error code؛
- correlation و trace از Request G؛
- createdAt.

Descriptor عمداً این موارد را ندارد:

- content؛
- structuredData؛
- raw provider response؛
- Schema کامل؛
- API Key، Secret، Password، Token یا configuration؛
- Prompt و Context؛
- Provider SDK object.

---

## 8. Request و Tenant Association

اگر `AIResponseService` با `RequestLifecycleService` ساخته شود:

```python
responseService = AIResponseService(requestLifecycle=requestLifecycle)
```

برای هر Response:

1. Request در همان Tenant lookup می‌شود؛
2. Request ناشناخته یا متعلق به Tenant دیگر به
   `AIResponseRequestInvalid` تبدیل می‌شود؛
3. Request `CANCELLED` Response جدید نمی‌پذیرد؛
4. Response موفق برای Request `FAILED` رد می‌شود؛
5. Request به‌صورت implicit complete/start/fail نمی‌شود؛ H فقط ownership را
   بررسی می‌کند؛
6. correlation/trace از Request در Descriptor Response دیده می‌شود.

اگر lifecycle compose نشده باشد، H فقط `AIResponse.tenantId` و `requestId` را
از خود Entity validate می‌کند و outer Application/Repository مالک Request
ownership validation است. این حالت برای migration و composition root مجاز است،
اما Authorization و persistence را ایجاد نمی‌کند.

---

## 9. Failure، Classification و Security

### Failed Response

`status=FAILED` نیازمند error code غیرخالی است و H آن را uppercase می‌کند. H
Provider Exception را به‌عنوان API عمومی عبور نمی‌دهد؛ Adapter آینده باید
exception mapping را پیش از H انجام دهد.

### Output Classification

Classificationهای B عبارت‌اند از:

```text
ADVISORY, DRAFT, AUTOMATED, AUTHORITATIVE
```

برای `AUTHORITATIVE`، caller باید `authorized=True` صریح بدهد؛ در غیر این صورت
`AIPermissionDenied` صادر می‌شود. این فقط یک safety guard در Domain boundary
است و جایگزین K/Application authorization کامل نیست.

### Token و Timing

H مقدارهای زیر را به `AIResponse` B می‌دهد:

- input tokens؛
- output tokens؛
- total tokens؛
- latency.

Entity B consistency و non-negative بودن را enforce می‌کند. H هزینه، quota،
queue time، provider time یا latency aggregate تولید نمی‌کند؛ این موارد در N
و W قرار دارند.

### عدم ذخیرهٔ Secret

- Structured Output فقط JSON-compatible value است؛
- output schema و descriptor دادهٔ raw را expose نمی‌کنند؛
- خطاها payload را echo نمی‌کنند؛
- H هیچ secret resolver یا configuration store ندارد؛
- هیچ Provider یا API Key داخل H hard-code نشده است.

---

## 10. Purity و Dependency Rules

`responseLifecycle.py` فقط از این موارد استفاده می‌کند:

- Python standard library؛
- Entityهای B؛
- Exceptionهای Domain؛
- قواعد authorization/redaction موجود Domain؛
- Contract `RequestLifecycleService` از G.

ممنوع و استفاده‌نشده:

```text
Django / ORM / REST / HTTP / Redis / Queue / Worker
OpenAI / Ollama / Azure / Anthropic / Vendor SDK
Network / File I/O / Secret Store / Database / Persistence
```

Structured validation dependency-free است تا Unit Test بدون نصب Django یا
کتابخانهٔ بیرونی اجرا شود. این به معنی ادعای full JSON Schema standard نیست؛
Contract subset در همین سند مرجع H است.

---

## 11. فایل‌های ایجادشده یا تغییرکرده

```text
backend/apps/ai/domain/services/responseLifecycle.py
backend/apps/ai/domain/services/__init__.py
backend/apps/ai/domain/exceptions/aiExceptions.py
backend/apps/ai/domain/exceptions/__init__.py
backend/tests/unit/testPhase13ResponseLifecycle.py

docs/Phases/Phase13/Phase13-H.md
docs/Phases/Phase13/Phase13-H-ExecutionReport.md
docs/Phases/Phase13/README.md
docs/Phases/Phase13.md
```

API aliasها:

```text
AIResponseService
AIResponseLifecycle
ResponseLifecycleService
ResponseRegistry
AIResponseRegistry
InMemoryResponseRegistry
StructuredOutputValidator
ResponseContract
```

Read Modelها:

```text
StructuredOutputSchema
StructuredOutput
ValidationIssue
ResponseDescriptor
```

---

## 12. Open Questions برای زیر‌فازهای بعدی

1. Schema پایدار و versioned در I چگونه به `AIPromptVersion.outputSchema`
   متصل شود؟
2. آیا در H/P باید root array و non-object Structured Output با Entity جدید
   پشتیبانی شود یا contract B به object محدود بماند؟
3. Validator کامل JSON Schema در کدام Infrastructure boundary نصب و چگونه با
   subset pure H همسان شود؟
4. Responseهای چند Attempt در M چگونه deduplicate و canonical شوند؟
5. آیا Validation Failure باید با Retention/Privacy Policy جداگانه در O/N
   ذخیره شود؟
6. Streaming partial response در P چه زمانی به Response نهایی H تبدیل شود؟
7. آیا `contentPresent` برای String خالی اما whitespace-only باید trim-aware
   شود؟ H در این نسخه فقط non-empty string را قابل تحویل می‌داند.
8. Output Classification و `AUTHORITATIVE` authorization دقیقاً چگونه با K و
   Approval workflow اتصال پیدا کند؟
9. Score، Embedding و Tool Result که در سند مادر آمده‌اند، در H با Entityهای
   تخصصی آینده مدل شوند یا به Response payload جدید نیاز دارند؟
10. Schema fingerprint و response content digest در W/O چه retention و privacy
    policy داشته باشند؟

---

## 13. Acceptance Criteria

- [x] `AIResponse` واقعی B در Response boundary استفاده شد؛
- [x] Text Response و Structured Response پشتیبانی شدند؛
- [x] JSON string به object JSON normalize می‌شود؛
- [x] Structured Output object-root و JSON-compatible enforce می‌شود؛
- [x] Schema immutable، versioned و fingerprintable است؛
- [x] subset مستند JSON Schema شامل nested properties/items/combinators اجرا شد؛
- [x] Schema Definition نامعتبر با خطای Domain رد می‌شود؛
- [x] Validation Issue مسیر و keyword دارد و payload را expose نمی‌کند؛
- [x] Response موفق قبل از validation ثبت نمی‌شود؛
- [x] `VALIDATION_FAILED` payload نامعتبر را retain نمی‌کند؛
- [x] Failed Response error code پایدار می‌خواهد؛
- [x] AUTHORITATIVE بدون authorization صریح رد می‌شود؛
- [x] Token و latency به Entity B واگذار و consistency آن حفظ شد؛
- [x] Request و Tenant ownership با G قابل compose است؛
- [x] Safe immutable ResponseDescriptor ایجاد شد؛
- [x] Duplicate Response ID و Tenant isolation enforce شد؛
- [x] هیچ ORM/API/Queue/Worker/Network/Vendor/Secret وارد Domain H نشده است؛
- [x] Pure Test و regression B تا H اجرا شد؛
- [x] محدودیت Django، Ruff و mypy ثبت شد؛
- [x] Documentation، Verification، Gate و ZIP مستقل آماده شد.

**نتیجه:** `GREEN — Phase 13-I may begin.`
