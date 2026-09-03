# Phase 13-A — Scope, Architecture Boundary & Acceptance Contract

**محصول:** Tekarai Enterprise Operations Platform  
**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** A از A تا Z  
**وضعیت:** COMPLETED — Documentation Baseline  
**تاریخ ثبت:** 2026-09-02  
**سند مادر:** [`../Phase13.md`](../Phase13.md)  
**منبع تصمیم‌های معماری:** ADRهای تأییدشده، به‌خصوص ADR-013، ADR-016، ADR-017 و ADR-018

---

## 1. هدف زیر‌فاز A

زیر‌فاز A کدنویسی قابلیت AI را شروع نمی‌کند. هدف آن ایجاد قرارداد اجرایی و
معماری است تا زیر‌فازهای B تا Z روی یک محدودهٔ روشن، قابل اندازه‌گیری و قابل
بازبینی ساخته شوند.

در پایان A باید دقیقاً مشخص باشد:

- AI در Tekarai یک **Platform Capability** است، نه Chatbot یا Feature مربوط به
  یک Domain خاص؛
- مرز AI Domain، Application، Infrastructure و Presentation کجاست؛
- چه داده‌هایی اجازه دارند وارد Context یا Provider شوند؛
- منبع حقیقت Business Data کدام Domain است؛
- هر خروجی AI چگونه Trace، Audit، Validate و Classify می‌شود؛
- معیار پذیرش هر زیر‌فاز چیست؛
- چه چیزهایی عمداً در A پیاده‌سازی نمی‌شوند.

---

## 2. محدودهٔ رسمی فاز ۱۳

فاز ۱۳ Foundation عمومی AI را ایجاد می‌کند تا Domainهای زیر بتوانند از طریق
Contract از آن استفاده کنند:

- Projects و Tasks؛
- Workforce/HR؛
- Performance و Analytics؛
- Documents و Knowledge؛
- Communication و Meeting Intelligence؛
- Assets و Maintenance؛
- Workflow؛
- Industry Extensions، فقط از طریق Adapter/Contract.

قابلیت‌های هدف عبارت‌اند از:

- Generation، Summarization، Classification، Extraction و Translation؛
- Question Answering، Recommendation، Prediction و Anomaly Detection؛
- Document/Meeting/KPI Analysis و Task Extraction؛
- Embedding، Semantic Search، Retrieval، RAG و Reranking؛
- Memory، Feedback، Evaluation و Governance؛
- Tool و Agent Foundation؛
- Providerهای Local، Cloud و Enterprise بدون قفل‌شدن Core به Vendor.

این فاز مالک دادهٔ اصلی Project، Employee، Document، Message، KPI یا Asset
نیست؛ AI فقط Reference، Context، Index، Metadata و نتیجهٔ قابل‌ردیابی را نگه
می‌دارد.

---

## 3. خارج از محدودهٔ A

موارد زیر در A اجرا نمی‌شوند و به زیر‌فازهای بعدی واگذار می‌شوند:

- تعریف Entity و Value Object اجرایی AI در B؛
- تعریف Portهای Provider در C؛
- ORM Model، Migration یا API Endpoint؛
- اتصال شبکه‌ای به OpenAI، Azure، Ollama، Anthropic یا هر Provider دیگر؛
- ذخیره یا پردازش API Key و Secret؛
- Vector Database واقعی، Embedding و RAG؛
- Queue، Worker، Agent، Tool Execution و Model Inference؛
- تغییر در Domainهای Projects، HR، Documents یا Communication؛
- تصمیم قطعی دربارهٔ Provider تجاری، Vector Store، Broker یا Frontend.

هر مورد خارج از این محدوده باید در گزارش زیر‌فاز مربوطه ثبت شود و نباید به‌صورت
پنهانی وارد A شود.

---

## 4. اصول غیرقابل مذاکره

### 4.1 استقلال از Provider

Core AI نباید `openai`، `anthropic`، `azure`، `ollama` یا SDK مشابه را Import کند.
Provider فقط در Infrastructure Adapter قرار می‌گیرد و از طریق Port مصرف می‌شود.

مسیر مجاز:

```text
Business Domain
    → AI Application Contract
    → AI Service
    → AI Provider Port
    → Provider Adapter
    → External/Local Provider
```

مسیر ممنوع:

```text
Domain/View/Serializer
    → Vendor SDK یا HTTP Provider
```

### 4.2 استقلال Domain از Framework

لایهٔ Domain نباید Django، DRF، ORM، Redis، Channels، HTTP Client یا فایل‌های
Infrastructure را بشناسد.

### 4.3 امنیت و Least Privilege

- Tenant Context قبل از اجرای Use Case برقرار می‌شود؛
- Authorization قبل از Context Assembly و قبل از Inference انجام می‌شود؛
- دادهٔ Restricted یا Confidential فقط با Policy صریح اجازهٔ ارسال خارجی دارد؛
- Prompt Injection و خروجی نامعتبر باید در Boundary کنترل شوند؛
- AI هرگز مجوز جدید تولید نمی‌کند و Security Boundary را دور نمی‌زند.

### 4.4 منبع حقیقت

AI نتیجهٔ Advisory، Draft، Automated یا Authoritative تولید می‌کند؛ اما Business
Record اصلی متعلق به Domain مالک است. خروجی `AUTHORITATIVE` فقط با Authorization
صریح و Rule قابل‌ردیابی اجازهٔ اثرگذاری دارد.

### 4.5 Audit و Traceability

هر Operation باید حداقل این زنجیره را حفظ کند:

```text
tenantId
  → correlationId / traceId
  → AIRequest / Operation
  → Context Sources
  → Prompt Version
  → Provider + Model
  → AIResponse
  → Usage + Cost
  → Audit
  → Feedback / Evaluation
```

ذخیرهٔ Secret، Token خام، Prompt حساس یا Context خام فقط طبق Policy مصوب و با
Redaction مجاز است.

### 4.6 Configuration over Customization

Provider، Model، Capability، Prompt، Fallback، Retry، Quota، Cost، Safety،
Retention و Context Limit باید از Configuration/Policy بیایند؛ اعداد و Provider
در Call Site هاردکد نمی‌شوند.

---

## 5. مرز لایه‌ها

| لایه | مالکیت | وابستگی مجاز | ممنوعیت اصلی |
|---|---|---|---|
| Domain | Invariant، Entity، Value Object، Error، Policy و محاسبهٔ خالص | Python stdlib و Shared Kernel خالص | Django، HTTP، ORM، Redis، SDK |
| Application | Use Case، Orchestration، DTO، Transaction و Port مصرفی | Domain و Contractها | Vendor SDK و Query مستقیم ORM |
| Infrastructure | ORM، Migration، Provider Adapter، Queue، Storage، Metrics | Application/Domain Contract و ابزار محیط | قراردادن Business Rule در Adapter |
| Presentation | API، Serializer، Auth Boundary و Mapping | Application Contract | اجرای مستقیم مدل، Provider یا Business Rule |

### مدل جریان Command

```text
Client
 → Authentication
 → Tenant Context
 → Authorization
 → Input Validation
 → AI Use Case
 → Context/Policy Check
 → Model/Prompt Resolution
 → Provider Port
 → Output Validation
 → Persist Request/Response/Usage/Audit
 → Event/Notification
```

### مدل جریان Query

```text
Client
 → Authentication
 → Tenant Boundary
 → Authorization
 → AI Query
 → Tenant-scoped Read Repository
 → DTO
 → Standard Response Envelope
```

---

## 6. مرز داده و مالکیت

### AI می‌تواند نگه‌داری کند

- Provider/Model/Capability configuration؛
- Prompt و نسخهٔ immutable آن؛
- Request/Response و شناسه‌های Trace؛
- Context metadata و منبع مجاز Context؛
- Usage، Token، Latency، Cost و Quota usage؛
- Embedding و Knowledge Index با ارجاع به Source؛
- Memory با Scope، Version، Expiry و Tenant؛
- Feedback، Evaluation، Audit و Governance metadata؛
- Agent/Tool definition و Execution record.

### AI نباید مالک یا جایگزین شود

- Project، Task، Employee، Document، Message یا Asset اصلی؛
- Permission، Role، Tenant Membership یا Authorization اصلی؛
- Audit رسمی Domainهای دیگر؛
- Secret و API Key خام؛
- تنها نسخهٔ یک Business Fact.

هر رکورد AI حساس باید `tenantId` داشته باشد و Repository آن باید Tenant را در
Query اعمال کند؛ دریافت رکورد فقط با `id` بدون Tenant Context مجاز نیست.

---

## 7. طبقه‌بندی خروجی AI

| مقدار | معنی | اثر مجاز |
|---|---|---|
| `ADVISORY` | پیشنهاد یا تحلیل برای انسان | نمایش/ذخیره با Audit؛ بدون تغییر خودکار Business Record |
| `DRAFT` | پیش‌نویس قابل ویرایش | نیازمند Review انسانی قبل از انتشار |
| `AUTOMATED` | عملیات کنترل‌شده با Rule از پیش‌تأییدشده | فقط در Scope و Policy مشخص |
| `AUTHORITATIVE` | نتیجهٔ مجاز برای اثرگذاری بر Record | Authorization صریح، Validation، Audit و امکان Rollback |

هیچ Provider یا Promptی به‌تنهایی اجازهٔ Authoritative شدن ندارد.

---

## 8. معیارهای غیرعملکردی پایه

- **Tenant Isolation:** صفر دسترسی cross-tenant در Unit و Integration Test؛
- **Provider Agnosticism:** تعویض Adapter بدون تغییر Domain/Application؛
- **Determinism در تست:** Test Provider بدون اینترنت، Secret یا API Key؛
- **Idempotency:** درخواست‌ها و Jobهای حساس با کلید idempotency؛
- **Failure Safety:** خطای Provider نباید به‌صورت Vendor Exception به API نشت کند؛
- **Privacy:** Context و Audit قبل از ذخیره/ارسال Redact می‌شوند؛
- **Observability:** correlationId، traceId، status، latency و usage قابل‌ردیابی؛
- **No hidden success:** هیچ Gate بدون Evidence سبز اعلام نمی‌شود؛
- **Backward compatibility:** تغییرات Phase 13 نباید تست‌های Phase 1–12 را بشکند.

---

## 9. نگاشت A تا Z به سند مادر

| بخش سند مادر | زیر‌فاز |
|---|---|
| §§1–4: Objective، Principles، Responsibilities، Architecture | A |
| §§5–9: Domain Components، Provider، Model، Types، Capability | B–F |
| §§10–14: Request، Response، Structured Output، Prompt و Versioning | G–I |
| §§15–21: Context، Memory، Knowledge، Embedding، Retrieval و RAG | J، Q–T، S |
| §§22–25: AI Service، Provider Abstraction، Routing، Fallback | C، E، L، M |
| §§26–29: Cost، Latency، Audit، Security | K، N، O |
| §§30–36: Tools، Agents، Evaluation، Feedback، Observability، Async | P، U–Y، W، X |
| §§37–48: Data، Tenant، API، Testing، Provider، Config، Error، Retry، Privacy، Governance | A، K، L، M، N، O، Z |
| §§49–54: Package، Order، DoD، Forbidden، Result، Output | A و Z |

---

## 10. خروجی‌های رسمی A

این زیر‌فاز باید این فایل‌ها را ثبت کند:

- `docs/Phases/Phase13/README.md` — فهرست A تا Z و وضعیت؛
- `docs/Phases/Phase13/Phase13-A.md` — همین قرارداد اجرایی؛
- `docs/Phases/Phase13/Phase13-A-ExecutionReport.md` — شواهد و گزارش؛
- لینک از سند مادر `docs/Phases/Phase13.md` به بستهٔ A تا Z.

هیچ Migration، Provider Adapter یا Business Model در A خروجی ندارد.

---

## 11. Acceptance Criteria و Exit Gate

A فقط وقتی تکمیل محسوب می‌شود که تمام موارد زیر برقرار باشد:

- [x] محدودهٔ فاز ۱۳ و خارج از محدودهٔ A ثبت شده باشد؛
- [x] مرز چهار لایه و جریان Command/Query مشخص شده باشد؛
- [x] استقلال از Provider و Framework صریحاً ثبت شده باشد؛
- [x] مالکیت داده و Tenant Boundary تعریف شده باشد؛
- [x] Output Classification و شرط Authoritative ثبت شده باشد؛
- [x] امنیت، Privacy، Audit، Idempotency و Failure Boundary ثبت شده باشد؛
- [x] تمام §§1–54 سند مادر به زیر‌فازها نگاشت شده باشد؛
- [x] زیر‌فازهای B تا Z با وضعیت مشخص در Index ثبت شده باشند؛
- [x] گزارش اجرای A و محدودیت‌های Verification ثبت شده باشد؛
- [x] هیچ Secret یا Provider واقعی در A اضافه نشده باشد؛
- [x] تغییرات A از تغییرات کدِ زیر‌فازهای بعدی جدا نگه داشته شده باشد.

**نتیجهٔ Gate:** `GREEN — Phase 13-B may begin after review of this contract.`

---

## 12. Open Questions برای زیر‌فازهای بعد

این موارد در A عمداً حل نهایی نمی‌شوند و باید در بخش مربوطه با ADR یا Decision
Record بسته شوند:

1. قرارداد دقیق `AIProviderPort` و قابلیت Streaming در C؛
2. استراتژی Model Routing و اولویت Tenant Policy در E؛
3. نوع JSON Schema Validator در H؛
4. منبع Context و قرارداد Permission در J/K؛
5. Transport مشترک Adapterهای Cloud/Local در L؛
6. انتخاب Queue/Broker و تضمین Exactly-once/At-least-once در P؛
7. نوع Vector Store و الگوریتم Reranker در Q/R/S؛
8. سقف و Retention حافظهٔ AI در T؛
9. روش Evaluation و معیارهای قابل‌قبول در U؛
10. Registry و Approval Workflow ابزارها در X؛
11. سطح دسترسی Agent و Human Approval در Y؛
12. فهرست نهایی API و Permission codeها در Z.

تا زمان بسته‌شدن هر Open Question، از حدس‌زدن و Hardcode کردن تصمیم مربوطه
خودداری می‌شود.

---

## 13. دستور آغاز B

قبل از شروع B باید:

1. این سند توسط مالک محصول تأیید شود؛
2. گزارش A بررسی شود؛
3. هیچ Secret یا Provider واقعی برای تست لازم نباشد؛
4. تست‌های هر بخش از ابتدا کنار همان بخش نوشته شوند؛
5. در صورت سنگین‌بودن محیط، تست‌ها ثبت شوند و اجرای آن‌ها به مالک محصول
   منتقل شود، نه اینکه حذف شوند.

**زیر‌فاز بعدی:** B — AI Domain و Value Objects.
