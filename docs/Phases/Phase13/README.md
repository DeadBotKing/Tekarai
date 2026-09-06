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
| [G](Phase13-G.md) | Request و Operation Lifecycle | ✅ تکمیل شد |
| [H](Phase13-H.md) | Response و Structured Output | ✅ تکمیل شد |
| [I](Phase13-I.md) | Prompt Platform و Versioning | ✅ تکمیل شد |
| [J](Phase13-J.md) | Context Engine و Context Builder | ✅ تکمیل شد |
| [K](Phase13-K.md) | Tenant Isolation، Authorization و Permission Filtering | ✅ تکمیل شد |
| [L](Phase13-L.md) | Provider Adapterها | ✅ تکمیل شد |
| [M](Phase13-M.md) | Fallback، Retry، Timeout و Error Boundary | ✅ تکمیل شد |
| [N](Phase13-N.md) | Usage، Token، Latency، Cost و Quota | ✅ تکمیل شد |
| [O](Phase13-O.md) | Audit و Governance | ✅ تکمیل شد |
| [P](Phase13-P.md) | Async Execution، Queue و Worker | ✅ تکمیل شد |
| [Q](Phase13-Q.md) | Embedding Foundation | ✅ تکمیل شد |
| [R](Phase13-R.md) | Knowledge Ingestion، Chunking و Indexing | ✅ تکمیل شد |
| [S](Phase13-S.md) | Retrieval، RAG و Reranking | ✅ تکمیل شد |
| [T](Phase13-T.md) | AI Memory | ✅ تکمیل شد |
| [U](Phase13-U.md) | Evaluation | ✅ تکمیل شد |
| [V](Phase13-V.md) | Feedback | ✅ تکمیل شد |
| [W](Phase13-W.md) | Observability و Monitoring | ✅ تکمیل شد |
| [X](Phase13-X.md) | Tool Registry و Tool Execution | ✅ تکمیل شد |
| [Y](Phase13-Y.md) | Agent Foundation | ✅ تکمیل شد — [گزارش](Phase13-Y-ExecutionReport.md) |
| [Z](Phase13-Z.md) | API، Migration، تست نهایی و Release | ✅ تکمیل شد — [گزارش](Phase13-Z-ExecutionReport.md) |

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
- قرارداد G: [`Phase13-G.md`](Phase13-G.md)
- گزارش زیر‌فاز G: [`Phase13-G-ExecutionReport.md`](Phase13-G-ExecutionReport.md)
- قرارداد H: [`Phase13-H.md`](Phase13-H.md)
- گزارش زیر‌فاز H: [`Phase13-H-ExecutionReport.md`](Phase13-H-ExecutionReport.md)
- قرارداد I: [`Phase13-I.md`](Phase13-I.md)
- گزارش زیر‌فاز I: [`Phase13-I-ExecutionReport.md`](Phase13-I-ExecutionReport.md)
- قرارداد J: [`Phase13-J.md`](Phase13-J.md)
- گزارش زیر‌فاز J: [`Phase13-J-ExecutionReport.md`](Phase13-J-ExecutionReport.md)
- قرارداد K: [`Phase13-K.md`](Phase13-K.md)
- گزارش زیر‌فاز K: [`Phase13-K-ExecutionReport.md`](Phase13-K-ExecutionReport.md)
- قرارداد L: [`Phase13-L.md`](Phase13-L.md)
- گزارش زیر‌فاز L: [`Phase13-L-ExecutionReport.md`](Phase13-L-ExecutionReport.md)
- قرارداد N: [`Phase13-N.md`](Phase13-N.md)
- گزارش زیر‌فاز N: [`Phase13-N-ExecutionReport.md`](Phase13-N-ExecutionReport.md)
- قرارداد O: [`Phase13-O.md`](Phase13-O.md)
- گزارش زیر‌فاز O: [`Phase13-O-ExecutionReport.md`](Phase13-O-ExecutionReport.md)
- قرارداد M: [`Phase13-M.md`](Phase13-M.md)
- گزارش زیر‌فاز M: [`Phase13-M-ExecutionReport.md`](Phase13-M-ExecutionReport.md)
- قرارداد P: [`Phase13-P.md`](Phase13-P.md)
- گزارش زیر‌فاز P: [`Phase13-P-ExecutionReport.md`](Phase13-P-ExecutionReport.md)
- قرارداد Q: [`Phase13-Q.md`](Phase13-Q.md)
- گزارش زیر‌فاز Q: [`Phase13-Q-ExecutionReport.md`](Phase13-Q-ExecutionReport.md)
- قرارداد R: [`Phase13-R.md`](Phase13-R.md)
- گزارش زیر‌فاز R: [`Phase13-R-ExecutionReport.md`](Phase13-R-ExecutionReport.md)
- قرارداد S: [`Phase13-S.md`](Phase13-S.md)
- گزارش زیر‌فاز S: [`Phase13-S-ExecutionReport.md`](Phase13-S-ExecutionReport.md)
- قرارداد T: [`Phase13-T.md`](Phase13-T.md)
- گزارش زیر‌فاز T: [`Phase13-T-ExecutionReport.md`](Phase13-T-ExecutionReport.md)
- قرارداد U: [`Phase13-U.md`](Phase13-U.md)
- گزارش زیر‌فاز U: [`Phase13-U-ExecutionReport.md`](Phase13-U-ExecutionReport.md)
- قرارداد V: [`Phase13-V.md`](Phase13-V.md)
- گزارش زیر‌فاز V: [`Phase13-V-ExecutionReport.md`](Phase13-V-ExecutionReport.md)
- قرارداد W: [`Phase13-W.md`](Phase13-W.md)
- گزارش زیر‌فاز W: [`Phase13-W-ExecutionReport.md`](Phase13-W-ExecutionReport.md)
- قرارداد X: [`Phase13-X.md`](Phase13-X.md)
- گزارش زیر‌فاز X: [`Phase13-X-ExecutionReport.md`](Phase13-X-ExecutionReport.md)
- قرارداد Y: [`Phase13-Y.md`](Phase13-Y.md)
- گزارش زیر‌فاز Y: [`Phase13-Y-ExecutionReport.md`](Phase13-Y-ExecutionReport.md)
- قرارداد Z: [`Phase13-Z.md`](Phase13-Z.md)
- گزارش زیر‌فاز Z: [`Phase13-Z-ExecutionReport.md`](Phase13-Z-ExecutionReport.md)
