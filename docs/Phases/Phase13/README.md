# Phase 13 — AI Platform & Intelligence Foundation

## زیر‌فازبندی A تا Z

این پوشه برنامهٔ اجرایی فاز ۱۳ را به ۲۶ زیر‌فاز مستقل تقسیم می‌کند. سند مادر
همچنان [`../Phase13.md`](../Phase13.md) است؛ هر زیر‌فاز باید با همان سند و ADRهای
تأییدشده سازگار باشد.

| زیر‌فاز | موضوع | وضعیت |
|---|---|---|
| [A](Phase13-A.md) | محدوده، هدف، مرز معماری و معیارهای پذیرش | ✅ تکمیل شد |
| [B](Phase13-B.md) | AI Domain، Entityها و Value Objectها | ✅ تکمیل شد |
| [C](Phase13-C.md) | Provider Port و قرارداد Provider | ✅ تکمیل شد |
| [D](Phase13-D.md) | Provider Registry | ✅ تکمیل شد |
| [E](Phase13-E.md) | Model Registry و Routing | ✅ تکمیل شد |
| [F](Phase13-F.md) | Capability Registry | ✅ تکمیل شد |
| G | Request و Operation Lifecycle | ⏳ بعدی |
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
- گزارش زیر‌فاز B: [`Phase13-B-ExecutionReport.md`](Phase13-B-ExecutionReport.md)
- گزارش زیر‌فاز C: [`Phase13-C-ExecutionReport.md`](Phase13-C-ExecutionReport.md)
- گزارش زیر‌فاز D: [`Phase13-D-ExecutionReport.md`](Phase13-D-ExecutionReport.md)
- قرارداد E: [`Phase13-E.md`](Phase13-E.md)
- گزارش زیر‌فاز E: [`Phase13-E-ExecutionReport.md`](Phase13-E-ExecutionReport.md)
- قرارداد F: [`Phase13-F.md`](Phase13-F.md)
- گزارش زیر‌فاز F: [`Phase13-F-ExecutionReport.md`](Phase13-F-ExecutionReport.md)
