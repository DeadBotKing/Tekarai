# Phase 13-L — Execution Report

**تاریخ:** 2026-09-05  
**زیر‌فاز:** L — Provider Adapterها  
**وضعیت:** ✅ COMPLETED — Provider Adapter Gate GREEN  
**مخزن:** `DeadBotKing/Tekarai`  
**سند مرجع:** [`Phase13-L.md`](Phase13-L.md)  
**گزارش قبلی:** [`Phase13-K-ExecutionReport.md`](Phase13-K-ExecutionReport.md)

---

## 1. خلاصهٔ تحویل

زیر‌فاز L لایهٔ آداپتورهای فروشنده را روی قرارداد فاز 13-C پیاده کرد:
پنج آداپتور واقعی (OpenAI، Azure OpenAI، Ollama، Anthropic، Local)، یک کلاس
پایهٔ مشترک با سطح کامل `AIProviderPort`، ترنسپورت بدون وابستگی جدید،
نگاشت نهایی خطاها به سطح پایدار دامنه، پاک‌سازی سِکرِت، فکتوری
پیکربندی‌محور و سیم‌کشی تنظیمات. ۴۷ تست جدید (۳۸ واحد + ۹ یکپارچگی با
سرور HTTP محلی واقعی) اضافه شد و سوئیت کامل از 725 تست با ۱۰ شکاف
معماریِ به‌جامانده به **772 تست کاملاً سبز** رسید.

## 2. فایل‌های ایجادشده

### کد (10 فایل)

| فایل | مسئولیت |
|---|---|
| `backend/apps/ai/infrastructure/providers/providerErrors.py` | نگاشت خطای فروشنده/ترنسپورت به خطاهای دامنه + توابع پاک‌سازی سِکرِت |
| `backend/apps/ai/infrastructure/providers/providerHttp.py` | ترنسپورت استاندارد (urllib): JSON + جریان خطی، تایم‌اوت، سیگنال‌های داخلی |
| `backend/apps/ai/infrastructure/providers/providerAdapterBase.py` | کلاس پایهٔ `HttpProviderAdapterBase` — سطح کامل پورت، گیت قابلیت، نرمال‌سازی، سلامت، تخمین توکن |
| `backend/apps/ai/infrastructure/providers/openAiProvider.py` | آداپتور OpenAI / OpenAI-compatible (chat + embeddings + SSE) |
| `backend/apps/ai/infrastructure/providers/azureOpenAiProvider.py` | آداپتور Azure OpenAI (deployment URL + api-key + api-version) |
| `backend/apps/ai/infrastructure/providers/ollamaProvider.py` | آداپتور Ollama آفلاین/محلی (`/api/chat`، `/api/embed`، NDJSON) |
| `backend/apps/ai/infrastructure/providers/anthropicProvider.py` | آداپتور Anthropic Messages (بدون امبدینگ؛ گیت قابلیت) |
| `backend/apps/ai/infrastructure/providers/localProvider.py` | آداپتور مدل سازمانی/محلی با قرارداد خنثی |
| `backend/apps/ai/infrastructure/providers/providerFactory.py` | `ProviderAdapterConfig` + فکتوری fail-closed + پیش‌نیازهای هر نوع |
| `backend/apps/ai/infrastructure/providers/providerWiring.py` | سیم‌کشی تنظیمات (تنها نقطهٔ خواندن تنظیمات جنگو) |

### تست (2 فایل — ۴۷ تست)

| فایل | پوشش |
|---|---|
| `backend/tests/unit/testPhase13ProviderAdapters.py` | ۳۸ تست: پیلودها، نرمال‌سازی، گیت قابلیت، نگاشت خطا، پاک‌سازی سِکرِت، فکتوری، سیم‌کشی، ادغام رجیستری |
| `backend/tests/integration/testPhase13ProviderAdapterContract.py` | ۹ تست روی سوکت واقعی: چرخهٔ کامل تولید/استریم/امبدینگ، 429/401 روی سیم، تایم‌اوت واقعی، اتصال ردشده، سلامت زنده |

### پیکربندی و مستندات

| فایل | تغییر |
|---|---|
| `backend/config/settings/base.py` | بلوک `AI_PROVIDER_ADAPTERS` + `aiProviderTimeoutSeconds` (همه از محیط) |
| `backend/.env.example` | ۱۴ متغیر جدید `aiProvider*` با پیش‌فرض‌های خالی/امن |
| `docs/Phases/Phase13/Phase13-L.md` | قرارداد زیر‌فاز (این بسته) |
| `docs/Phases/Phase13/Phase13-L-ExecutionReport.md` | همین گزارش |
| `docs/Phases/Phase13/README.md` | جدول وضعیت: L تکمیل، M بعدی + لینک‌ها |
| `docs/Phases/Phase13.md` | ایندکس زیرفازها: A..L کامل، دروازهٔ بعدی M |

## 3. تغییرات اصلاحی مستند (تکامل دروازه — هرگز بی‌صدا نیست)

فازهای 13-B تا 13-K با تست‌های خالص اجرا شده بودند و سوئیت جنگو/لینتر
را اجرا نکرده بودند (گزارش K: «Django Test Runner / Ruff / mypy —
BLOCKED»); در نتیجه ۱۰ تست معماری از پیش شکسته بود. L آن‌ها را به‌صورت
مستند و هم‌راستای رویهٔ فاز ۶ («تکامل عمدی دروازه») برطرف کرد:

1. ثبت رسمی کانتکست `ai` در رجیستر افتتاح
   (`tests/architecture/testNoBusinessDomains.py` — `OPENED_CONTEXTS` و
   `allowedApps`) و حذف آن از فهرست ممنوعه؛ ثبت در
   `tests/architecture/testPhase3DomainArchitecture.py`؛
2. `apps/ai/apps.py` به الگوی فاز ۹ بازنویسی شد (مدل‌ها در
   `AppConfig.ready` از infrastructure وارد می‌شوند)؛
3. حذف `apps/ai/models.py` (پل ریشه)، `apps/ai/migrations/` و
   `apps/ai/tests/` (ناقض لایه‌بندی و نام‌گذاری) و
   `apps/ai/domain/exceptions.py` مرده (بستهٔ همنام مرجع است)؛
4. تغییر نام دو کلاس داخلی با پیشوند خط‌زیر به
   `RegisteredRequestState` / `RegisteredResponseState` (قانون نام‌گذاری
   فاز ۱)؛
5. افزودن هوک‌های فریم‌ورکی `http.server` به فهرست معافیت نام‌گذاری
   (با یادداشت فاز ۱۳، مشابه هوک‌های Channels در فاز ۸/۹)؛
6. افزودن `resolvedRequestId()` به `apps/ai/domain/ports.py` — خطای تایپی
   موجود از فاز 13-C (همان کلاس خطا) بدون تغییر رفتار برطرف شد.

## 4. تصمیم‌ها و سؤال‌های باز

| # | تصمیم | دلیل |
|---|---|---|
| L-D1 | ترنسپورت فقط با کتابخانهٔ استاندارد؛ هیچ وابستگی جدیدی اضافه نشد | رویهٔ خانه (JWT داخلی در ADR-022، OpenAPI داخلی در ADR-020)؛ نیاز L با `urllib` پوشش می‌یابد |
| L-D2 | آداپتورها فریم‌ورک‌آزاد (تزریق سازنده)؛ فقط `providerWiring` تنظیمات جنگو را می‌خواند | تست‌پذیری بدون Django + حفظ جهت وابستگی |
| L-D3 | سِکرِت فقط در ساخت آداپتور؛ از هیچ خطا/سلامت/لاگی عبور نمی‌کند | قرارداد §8 فاز 13-C و اصول امنیت |
| L-D4 | جدول نگاشت خطای §5 سند قرارداد، نهایی و یکسان برای همهٔ آداپتورها | §43 سند مادر + قاعدهٔ ۵ از §3 فاز 13-C |
| L-D5 | تخمین توکن محلی و قطعی (بدون توکنایزر فروشنده) | قرارداد §5.5 پورت؛ دقت مدل‌محور در زیر‌فازهای بعدی |
| L-D6 | وضعیت 401/403 به `AIProviderUnavailable` نگاشت می‌شود (نه اجازه‌دهی تجاری) | خطای پیکربندی است؛ راه‌حل آن تغییر اعتبارنامه است |
| L-D7 | سیم‌کشی فقط ورودی‌های کامل را می‌سازد؛ ورودی ناقص حذف می‌شود، حدس زده نمی‌شود | قانون «هرگز حدس نزن» — توسعه‌دهنده با متغیر محیطی فعال می‌کند |

سؤال‌های باز (ارجاع به زیر‌فازهای بعد): سیاست تلاش مجدد و مدار قطع → **M**؛
ثبت مصرف/هزینهٔ واقعی به‌جای تخمین → **N**؛ Audit فراخوانی‌های فروشنده → **O**؛
اجرای Async/صف → **P**.

## 5. شواهد اجرا (دروازهٔ کیفیت)

| دروازه | دستور | نتیجه |
|---|---|---|
| بررسی جنگو | `manage.py check` | `System check identified no issues (0 silenced).` |
| سوئیت کامل | `manage.py test tests` | `Ran 772 tests ... OK` (خط پایه قبل از L: 725 تست با ۱۰ شکست معماری) |
| سوئیت اختصاصی L | `manage.py test tests.unit.testPhase13ProviderAdapters tests.integration.testPhase13ProviderAdapterContract` | `Ran 47 tests ... OK` |
| Lint سطح L | `ruff check` روی پرونده‌های جدید/تغییریافته | `All checks passed!` |
| فرمت سطح L | `ruff format --check` | همهٔ فایل‌ها فرمت‌شده |
| تایپ سطح L | `mypy apps/ai/domain/ports.py apps/ai/infrastructure/providers` | `Success: no issues found in 13 source files` |
| مهاجرت | `manage.py makemigrations --check` | L هیچ مدل/مهاجرتی نمی‌افزاید؛ تنها انحراف موجود، `channelprofilemodel.conversationId` از فاز ۹ است که سند تحویل فاز ۱۰ (§10) آن را عمداً دست‌نخورده ثبت کرده است |

## 6. بدهی پیشین (شفاف‌سازی — خارج از دامنهٔ L)

اجرای نخستِ کامل ابزارها روی کل بک‌اند، بدهی به‌جامانده از زیرفازهای قبل
(که هرگز با این ابزارها اجرا نشده بودند) را آشکار کرد: حدود ۲۲۵ خطای
ruff و ۵۶۱ خطای mypy در فایل‌های پیش از L (مانند `apps/ai/infrastructure/models.py`
با ۱۲۹ مورد، `apps/ai/application/services/aiService.py` و تست‌های فاز ۸/۹).
به احترام قاعدهٔ محدودهٔ تغییر، این بدهی در L بازنویسی نشد و باید در یک
زیر‌فاز پاک‌سازی مستقل پیش از M رسیدگی شود. سطح تحویل‌شدهٔ L کاملاً سبز است.

## 7. راستی‌آزمایی معیارهای پذیرش (سند قرارداد §8)

| معیار | وضعیت |
|---|---|
| شش آداپتور از طریق فکتوری ساخته و در پورت صادق‌اند | PASS — `testFactoryBuildsEveryDocumentedAdapterType`, `testEveryAdapterSatisfiesThePortProtocolAndCodeHandshake` |
| نگاشت خطای جدول §5 یکسان و تست‌شده | PASS — ۹ تست نگاشت خطا (واحد) + ۴ تست روی سیم واقعی |
| سِکرِت در هیچ خطا/سلامت/لاگ ظاهر نمی‌شود | PASS — `testCredentialRejectionMapsToProviderUnavailableWithoutSecret`, `testCredentialErrorRedactsTheSecret`, `testHealthCheck*` |
| جریان SSE/NDJSON با تکهٔ پایانی `isFinal` | PASS — سه تست جریان (واحد) + دو تست روی سیم واقعی |
| فکتوری و سیم‌کشی پیکربندی‌محور بدون هاردکد فروشنده در دامنه | PASS — `ProviderFactoryTests` + `ProviderWiringAndRegistryTests` |
| ادغام با `ProviderRegistry` فاز 13-D | PASS — `testAdaptersRegisterIntoThePhase13DRegistry`, `testRegistryRejectsMismatchedAdapterCode` |
| تست‌های واحد و یکپارچگی آفلاین سبز | PASS — 38 + 9 |
| دروازهٔ کیفیت کامل سبز | PASS — بخش ۵ |
| مستندات قرارداد و گزارش | PASS — همین بسته |

**نتیجه:** `GREEN — Phase 13-M may begin.`

## 8. Archive تحویل مستقل L

Archive مستقل L پس از Verification با همان قاعدهٔ زیر‌فازهای قبلی ساخته
می‌شود:

```text
/home/user/Tekarai-Phase13-L.zip
```

Checksum در فایل جانبی `.sha256` ثبت می‌شود (برای جلوگیری از
خود-ارجاعی، مقدار canonical فقط در Delivery Message اعلام می‌شود).
Exclusionها مطابق زیر‌فاز K:

```text
.git, backend/venv, backend/.venv, backend/staticRoot, backend/mediaRoot,
__pycache__, *.pyc, .pytest_cache, .mypy_cache, .ruff_cache, .cache,
node_modules, dist, build, coverage, .tox, .nox, .next, .vite, .turbo
```

## 9. زیر‌فاز بعدی

**M — Fallback، Retry، Timeout و Error Boundary:** سیاست تلاش مجدد روی
سطح خطایی که L تثبیت کرد (کدام خطاها قابل تلاش‌اند، کران تلاش، مدار قطع)،
زنجیرهٔ جایگزینی آداپتور/مدل هنگام خرابی، و مرز خطای یکپارچه برای
مصرف‌کننده‌ها.
