# Phase 13 — AI Platform & Intelligence Foundation

## زیر‌فازبندی A تا Z

این پوشه برنامهٔ اجرایی فاز ۱۳ را به ۲۶ زیر‌فاز مستقل تقسیم می‌کند. سند مادر
همچنان [`../Phase13.md`](../Phase13.md) است؛ هر زیر‌فاز باید با همان سند و ADRهای
تأییدشده سازگار باشد.

| زیر‌فاز | موضوع | وضعیت |
|---|---|---|
| [A](Phase13-A.md) | محدوده، هدف، مرز معماری و معیارهای پذیرش | ✅ تکمیل شد |
| B | AI Domain و Value Objects | ⏳ بعدی |
| C | Provider Port و قرارداد Provider | ⏳ |
| D | Provider Registry | ⏳ |
| E | Model Registry و Routing | ⏳ |
| F | Capability Registry | ⏳ |
| G | Request و Operation Lifecycle | ⏳ |
| H | Response و Structured Output | ⏳ |
| I | Prompt Platform و Versioning | ⏳ |
| J | Context Engine و Context Builder | ⏳ |
| K | Tenant Isolation، Authorization و Permission Filtering | ⏳ |
| L | Provider Adapterها | ⏳ |
| M | Fallback، Retry، Timeout و Error Boundary | ⏳ |
| N | Usage، Token، Latency، Cost و Quota | ⏳ |
| O | Audit و Governance | ⏳ |
| P | Async Execution، Queue و Worker | ⏳ |
| Q | Embedding Foundation | ⏳ |
| R | Knowledge Ingestion، Chunking و Indexing | ⏳ |
| S | Retrieval، RAG و Reranking | ⏳ |
| T | AI Memory | ⏳ |
| U | Evaluation | ⏳ |
| V | Feedback | ⏳ |
| W | Observability و Monitoring | ⏳ |
| X | Tool Registry و Tool Execution | ⏳ |
| Y | Agent Foundation | ⏳ |
| Z | API، Migration، تست نهایی و Release | ⏳ |

## قرارداد اجرای زیر‌فازها

هر زیر‌فاز باید این خروجی‌ها را داشته باشد:

1. سند نیازمندی و دامنهٔ همان زیر‌فاز؛
2. تصمیم‌های معماری و Open Questionهای آن؛
3. فایل‌های تولیدشده/تغییریافته؛
4. تست‌های مرتبط یا دلیل صریح برای به‌تعویق‌افتادن تست سنگین؛
5. شواهد Verification؛
6. گزارش اجرای مستقل و وضعیت Gate؛
7. لینک به زیر‌فاز بعدی.

## قواعد ثبت تغییرات

- هیچ تغییری خارج از محدودهٔ زیر‌فاز فعال بدون ثبت در گزارش انجام نمی‌شود.
- تغییرات کد، Migration و تست‌ها در ریشهٔ `backend/` انجام می‌شوند، اما تمام
  تصمیم‌ها، برنامه، گزارش، Open Question و شواهد در همین بستهٔ `docs/Phases/Phase13/`
  ثبت می‌شوند.
- Providerهای واقعی تا قبل از تعریف Port و Policy مجاز نیستند.
- Secret، API Key و دادهٔ Tenant دیگر نباید در سند، Source Code یا Archive قرار گیرد.

## گزارش‌ها

- گزارش زیر‌فاز A: [`Phase13-A-ExecutionReport.md`](Phase13-A-ExecutionReport.md)
