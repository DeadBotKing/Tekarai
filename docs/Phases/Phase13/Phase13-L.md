# Phase 13-L — Provider Adapterها

**محصول:** Tekarai Enterprise Operations Platform  
**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** L از A تا Z  
**وضعیت:** قرارداد اجرا  
**تاریخ ثبت:** 2026-09-05  
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§6، §7، §23، §41، §42، §43، §50 STEP 8)  
**قرارداد قبلی:** [`Phase13-K.md`](Phase13-K.md)  
**قرارداد مرجع پورت:** [`Phase13-C.md`](Phase13-C.md)  
**گزارش اجرا:** [`Phase13-L-ExecutionReport.md`](Phase13-L-ExecutionReport.md)

---

## 1. هدف و سؤال معماری

زیر‌فاز L مرز واقعی بین پلتفرم و سرویس‌های بیرونی هوش مصنوعی را می‌سازد.
تا پیش از L، پلتفرم فقط یک `DeterministicAIProvider` آفلاین داشت؛ از اینجا به
بعد هر Provider تجاری یا سازمانی فقط از طریق یک **Adapter** وارد می‌شود که
قرارداد فاز 13-C را پیاده می‌کند.

L به این سؤال پاسخ می‌دهد:

> چگونه بدون وابستگی Core به هیچ فروشنده، بدون نشت Exception یا Secret، و با
> رفتار fail-closed، پنج کلاس متفاوت از سرویس‌دهنده (OpenAI، Azure OpenAI،
> Ollama، Anthropic، Local/Enterprise) را پشت یک پورت واحد قابل‌تعویض کنیم؟

سه اصل ثابت:

1. **هر فروشنده فقط یک Adapter است** (§23 سند مادر) — هیچ‌کدام در دامنه یا
   اپلیکیشن وارد نمی‌شود؛
2. **خطای فروشنده هرگز از مرز عبور نمی‌کند** — همهٔ شکست‌ها به خطاهای پایدار
   دامنه (فاز 13-B) نگاشت می‌شوند (C §3 قاعدهٔ ۵: نگاشت نهایی در L)؛
3. **Secret فقط در لحظهٔ ساخت آداپتور وارد می‌شود** — نه در `ProviderRequestContext`،
   نه در خطاها، نه در Health، نه در لاگ (C §8 قاعدهٔ ۴).

---

## 2. Scope و Non-Scope

### 2.1 داخل Scope

- ترنسپورت سبک‌وزن و بدون وابستگی جدید (کتابخانهٔ استاندارد) برای درخواست/پاسخ
  JSON و جریان‌های خطی (SSE/NDJSON) با تایم‌اوت؛
- کلاس پایهٔ `HttpProviderAdapterBase` با سطح کامل `AIProviderPort`:
  اعتبارسنجی ورودی، گیت قابلیت‌ها، نگاشت خطا، نرمال‌سازی خروجی،
  سلامت‌سنجی و تخمین توکن؛
- پنج آداپتور: `OpenAiProviderAdapter`، `AzureOpenAiProviderAdapter`،
  `OllamaProviderAdapter`، `AnthropicProviderAdapter`، `LocalProviderAdapter`؛
- نگاشت کامل خطا: تایم‌اوت، قطعی اتصال، 401/403، 404 مدل، 429، 400/422،
  5xx و بدنهٔ نامعتبر؛
- پاک‌سازی (Redaction) سِکرِت از همهٔ پیام‌های بیرونی؛
- فکتوری پیکربندی‌محور `buildProviderAdapter` + سیم‌کشی تنظیمات
  (`AI_PROVIDER_ADAPTERS`) بدون هیچ مقدار هاردکدشدهٔ فروشنده در دامنه؛
- ساخت/استریم/امبدینگ/سلامت برای هر آداپتور مطابق قرارداد §5 فاز 13-C؛
- تست واحد آفلاین با ترنسپورت جعلی + تست یکپارچگی با سرور HTTP محلی واقعی؛
- ادغام با `ProviderRegistry` فاز 13-D (ثبت و resolve آداپتور).

### 2.2 خارج از Scope

- Retry / Fallback / Timeout Executor — زیر‌فاز **M**؛
- Usage / Cost / Quota tracking — زیر‌فاز **N**؛
- Audit و Governance خروجی — زیر‌فاز **O**؛
- Queue / Worker / اجرای Async — زیر‌فاز **P**؛
- Embedding foundation، RAG و Knowledge — زیر‌فازهای **Q تا S**؛
- هر مدل/مهاجرت/ریپازیتوری جدید دیتابیس — این زیر‌فاز هیچ اسکیما تغییری
  نمی‌دهد؛
- اندپوینت API عمومی برای مدیریت آداپتورها — زیر‌فاز **Z**.

---

## 3. جایگاه معماری

```text
Application / AI Service
        │
        ▼
Phase 13-D ProviderRegistry  ← resolve(tenantId, providerCode)
        │
        ▼
Phase 13-C AIProviderPort (contract)
        │
        ▼
Phase 13-L Adapter Layer (این زیر‌فاز)
   ├── HttpProviderAdapterBase (generate/stream/embed/count/health)
   ├── providerErrors (نگاشت خطا + redaction)
   ├── providerHttp (ترنسپورت استاندارد، تایم‌اوت، جریان خطی)
   ├── OpenAI · Azure OpenAI · Ollama · Anthropic · Local
   └── providerFactory + providerWiring (پیکربندی‌محور)
        │
        ▼
شبکه / سرویس بیرونی (هرگز وارد دامنه نمی‌شود)
```

قواعد وابستگی:

1. دامنه و اپلیکیشن فقط پورت و رجیستری را می‌شناسند؛ آداپتورها را مستقیم
   وارد نمی‌کنند (رجیستری یا سیم‌کشی آن‌ها را تحویل می‌دهد)؛
2. همهٔ آداپتورها در `apps/ai/infrastructure/providers/` قرار دارند؛
3. آداپتورها فریم‌ورک‌آزاد ساخته می‌شوند (تزریق از طریق سازنده) تا بدون
   Django هم تست شوند؛ فقط ماژول سیم‌کشی تنظیمات را می‌خواند؛
4. ترنسپورت قابل تزریق است — تست واحد بدون سوکت، تست یکپارچگی با سوکت واقعی.

---

## 4. قرارداد ترنسپورت

`UrllibJsonTransport` تنها وابستگی شبکه‌ای این زیر‌فاز است:

| ویژگی | قرارداد |
|---|---|
| کتابخانه | فقط کتابخانهٔ استاندارد (تصمیم L-D1 — بدون وابستگی جدید) |
| تایم‌اوت | اجباری و مثبت؛ پیش‌فرض ۳۰ ثانیه از تنظیمات |
| ورودی | متد، آدرس، پیلود JSON، هدرها |
| خروجی | `HttpResponse(status, body, headers)` بدون تفسیر فروشنده |
| جریان | `streamLines()` برای SSE و NDJSON |
| خطا | فقط دو سیگنال داخلی: `TransportTimeout` و `TransportConnectionFailed` |

## 5. قرارداد نگاشت خطا (نهایی — طبق §43 سند مادر)

| علت | خطای دامنه |
|---|---|
| تایم‌اوت شبکه | `AIRequestTimeout` |
| قطعی اتصال / DNS / خطای ترنسپورت ناشناخته | `AIProviderUnavailable` |
| HTTP 401 یا 403 | `AIProviderUnavailable` (اعتبارنامه رد شده) |
| HTTP 404 همراه نام مدل | `AIModelUnavailable` |
| HTTP 429 | `AIProviderRateLimited` |
| HTTP 400 یا 422 | `ValidationFailedError` (طبق §44 هرگز بی‌دلیل Retry نمی‌شود) |
| سایر وضعیت‌های خطا | `AIProviderUnavailable` |
| بدنهٔ غیر JSON یا ساختار نامعتبر خروجی | `AIOutputValidationFailed` |
| خطاهای خود دامنه | بدون تغییر عبور می‌کنند |

قوانین تکمیلی:

- هیچ متن خام فروشنده‌ای بدون پاک‌سازی سِکرِت بیرون نمی‌رود؛
- `healthCheck()` هرگز خطا پرتاب نمی‌کند: `HEALTHY` / `DEGRADED` /
  `UNAVAILABLE` / `UNKNOWN`؛
- تشخیص قابلیت‌ها قبل از هر فراخوانی بررسی می‌شود (مثلاً امبدینگ روی
  Anthropic با خطای اعتبارسنجی پایدار رد می‌شود، نه خطای فروشنده).

---

## 6. قرارداد آداپتورها

### 6.1 سطح مشترک (کلاس پایه)

`generate / generateRequest / generateStructured / stream / embed / embedBatch /
countTokens / healthCheck / capabilities / providerCode` — دقیقاً سطح
`AIProviderPort` فاز 13-C. کلاس پایه این موارد را یک‌بار پیاده می‌کند:

1. ساخت `GenerationRequest` معتبر از ورودی‌ها؛
2. گیت قابلیت (`GENERATION` / `STRUCTURED_GENERATION` / `STREAMING` / `EMBEDDING`)؛
3. ارسال با هدرهای احراز + هدرهای `X-Correlation-Id` / `X-Trace-Id`
   (هویت مستأجر هرگز به فروشنده ارسال نمی‌شود)؛
4. نگاشت خطا و نرمال‌سازی خروجی؛
5. `validateGenerationResult` با تطبیق مدل و پرووایدر.

### 6.2 آداپتورهای پنج‌گانه

| آداپتور | کد | احراز | قابلیت‌ها | نکته |
|---|---|---|---|---|
| `OpenAiProviderAdapter` | `OPENAI` | Bearer Key (اجباری) | Generation · Structured · Streaming · Embedding · TokenCount | حالت `json_schema` وقتی اسکیما موجود باشد، وگرنه `json_object` |
| `AzureOpenAiProviderAdapter` | `AZURE_OPENAI` | هدر `api-key` (اجباری) + `apiVersion` | مانند OpenAI | آدرس استقرار: `/openai/deployments/{model}/...` |
| `OllamaProviderAdapter` | `OLLAMA` | بدون کلید (اختیاری) | مانند OpenAI | مسیرهای `/api/chat`، `/api/embed`، `/api/tags`؛ JSON با `format:"json"` |
| `AnthropicProviderAdapter` | `ANTHROPIC` | `x-api-key` + `anthropic-version` (اجباری) | Generation · Streaming · TokenCount | بدون امبدینگ و بدون حالت ساختاریافته — گیت قابلیت رد می‌کند |
| `LocalProviderAdapter` | `LOCAL` | اختیاری | Generation · Structured · TokenCount (+Embedding انتخابی) | قرارداد خنثای سازمانی: `POST {base}{invocationPath}` با همان شکل درخواست/پاسخ پلتفرم |

`DeterministicAIProvider` فاز 13-C همچنان برای تست آفلاین از طریق فکتوری
(`providerType="DETERMINISTIC"`) در دسترس است.

### 6.3 فکتوری و سیم‌کشی

- `ProviderAdapterConfig` (frozen) تنها نقطهٔ ورود تنظیمات است؛
- `buildProviderAdapter(config)` fail-closed است: نوع ناشناخته، کلید یا آدرس
  ناقص → خطای دامنه در لحظهٔ ساخت؛
- `buildConfiguredProviderAdapters()` از `settings.AI_PROVIDER_ADAPTERS`
  می‌خواند و فقط ورودی‌های کامل را می‌سازد (حدس نمی‌زند)؛
- مقادیر از متغیرهای محیطی با نام‌های camelCase (ADR-001/ADR-009):
  `aiProviderOpenAiApiKey`, `aiProviderAzureOpenAiApiVersion`,
  `aiProviderOllamaBaseUrl`, `aiProviderAnthropicApiKey`,
  `aiProviderLocalBaseUrl`, `aiProviderTimeoutSeconds` و… (الگو:
  `backend/.env.example`).

---

## 7. تست و تأیید

1. **واحد (آفلاین):** ترنسپورت جعلی — پیلودها، نرمال‌سازی، گیت قابلیت‌ها،
   نگاشت هر کلاس خطا، پاک‌سازی سِکرِت، سلامت، فکتوری، سیم‌کشی و ادغام با
   رجیستری؛
2. **یکپارچگی (سوکت واقعی):** سرور `http.server` محلی — چرخهٔ کامل
   تولید/استریم/امبدینگ، نگاشت 429 و 401 روی سیم، طبقه‌بندی تایم‌اوت واقعی،
   اتصال ردشده، سلامت زنده؛
3. **معماری:** تست‌های نگارش/لایه/کانتکست‌ها سبز می‌مانند؛
4. هیچ فراخوانی شبکه‌ای به بیرون از `127.0.0.1` در تست‌ها وجود ندارد.

---

## 8. معیارهای پذیرش

- [ ] هر شش آداپتور (پنج فروشنده + Deterministic) از طریق فکتوری ساخته می‌شوند
      و در `AIProviderPort` صدق می‌کنند؛
- [ ] نگاشت خطای جدول §5 برای همهٔ آداپتورها یکسان و تست‌شده است؛
- [ ] سِکرِت در هیچ خطا، Health یا لاگ ظاهر نمی‌شود؛
- [ ] جریان‌های SSE و NDJSON با تکهٔ پایانی `isFinal` قرارداد را رعایت می‌کنند؛
- [ ] فکتوری و سیم‌کشی کاملاً پیکربندی‌محور و بدون مقدار هاردکدشدهٔ فروشنده
      در دامنه هستند؛
- [ ] آداپتورها در `ProviderRegistry` فاز 13-D ثبت و حل می‌شوند؛
- [ ] تست‌های واحد و یکپارچگی آفلاین سبز هستند؛
- [ ] درگاه کیفیت (تست کامل، lint، تایپ، `manage.py check`،
      `makemigrations --check`) سبز است؛
- [ ] مستندات قرارداد و گزارش اجرا با شواهد ثبت شده‌اند.

**ورودی زیر‌فاز بعد:** [`Phase13-M.md`](Phase13-M.md) — Fallback، Retry،
Timeout و Error Boundary روی همین سطح خطایی پایدار.
