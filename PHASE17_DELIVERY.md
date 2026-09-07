# تحویل نهایی فاز ۱۷ — Project Intelligence Platform

نسخه: **Tekarai 0.17.0**  
وضعیت: **کامل، تست‌شده و آمادهٔ تحویل**

## چرخهٔ اجراشده

`PROJECT → SNAPSHOT → OBSERVATION → ANALYSIS → DEPENDENCY GRAPH → ARCHITECTURE MODEL → KNOWLEDGE → INSIGHT → RECOMMENDATION → DECISION → TASK CONTEXT → AGENT`

چرخهٔ تغییر نیز به‌صورت `CHANGE DETECTION → AFFECTED AREA → INCREMENTAL ANALYSIS → KNOWLEDGE UPDATE → NEW CONTEXT` اجرا شده است.

## اجزای تحویل‌شده

- Bounded Context مستقل `apps/projectIntelligence` با Clean Architecture، DDD و ports/adapters.
- Snapshot تغییرناپذیر و versioned همراه File Tree/metadata/hash، Git state، environment، analysis version و SHA-256.
- Workspace boundary فقط‌خواندنی با جلوگیری از traversal، absolute/drive path، symlink escape، secret exposure و اسکن محتوایی خروجی‌ها/cache/dependencies.
- ۹ Analyzer پلاگینی: Filesystem، Language، Framework، Dependency/Symbol، Architecture، Git، Test، Documentation و Configuration.
- dependency graph داخلی/خارجی، cycle، unused candidate، coupling، layer/direction/violation و symbol graph.
- Git branch/commit/count/status/contributors/recent changes/frequency/hot files بدون تغییر history.
- Analyzer registry، نتیجهٔ استاندارد، failure isolation و ثبت `PARTIAL/FAILED`.
- Change/Rename detection، استفادهٔ مجدد از hash/content فایل‌های بدون تغییر و cache اختصاصی هر Analyzer برای re-analysis انتخابی.
- Knowledge versioning و Graph شامل Project/File/Test/Class/Function/Dependency و edgeهای `CONTAINS/IMPORTS`.
- Project Health با breakdown و evidence؛ Technical Debt و اختلاف code/documentation.
- Insight، Recommendation و Decision کاملاً evidence-based و explainable؛ تغییرات اثرگذار نیازمند Human Review هستند.
- Context Builder وابسته به Task و token budget با اولویت فایل مرتبط، وابستگی، معماری، تغییر، تست و docs؛ جلوگیری از ورود کل Workspace و secretها.
- Resume Generator و Agent Context Contract tenant-bound و version-linked.
- Project State کامل: `INITIALIZING/SCANNING/ANALYZING/READY/CHANGED/STALE/ERROR`.
- ۲۱ جدول tenant-scoped شامل ۱۷ entity مفهومی و Job/Audit/Event/Cache.
- immutable artifact storage، integrity verification، idempotency، atomic claim، post-commit queue و transient retry/backoff.
- Eventها، Audit، Metrics، Permissionها، Rate limit، Tenant Isolation و REST API کامل.
- مستندات API، operations/recovery/security و release notes.

## نتایج نهایی تست و کیفیت

- تست اختصاصی فاز ۱۷: **15/15 موفق**
- تست تجمعی Backend: **2278/2278 موفق** در **44.438 ثانیه**
- Ruff Check کل Repository: **موفق**
- Ruff Format: **728 فایل منطبق**
- Mypy کل Repository: **686 فایل بدون خطا**
- Mypy فاز ۱۷ بدون ignore: **57 فایل بدون خطا**
- Django System Check: **بدون مشکل**
- Migration Drift: **بدون تغییر**
- Migration رفت و برگشت تازه: **21/21 جدول ایجاد و 21/21 جدول حذف شد**
- `pip check`، `compileall` و `git diff --check`: **موفق**
- بررسی secret/placeholder و پاک‌سازی artifact/cache: پیش از بسته‌بندی نهایی انجام می‌شود.

## مستندات

- مشخصات مرجع: `docs/Phases/Phase17.md`
- گزارش اجرا: `docs/Phases/Phase17Report.md`
- API: `docs/api/projectIntelligencePlatform.md`
- Runbook: `docs/operations/projectIntelligencePlatform.md`
- Release: `docs/releases/Phase17.md`

## راه‌اندازی Worker

```bash
cd backend
python manage.py migrate
celery -A config worker -l INFO -Q project-intelligence.analysis
```

در Production، workspace باید read-only mount شود و artifact storage پایدار/رمزشده، محدودیت CPU/RAM/time، queue monitoring و backup هماهنگ SQL/artifact مطابق Runbook تنظیم شود.

## Archive

فایل نهایی `Tekarai-Phase17-complete.zip` و checksum استاندارد آن `Tekarai-Phase17-complete.zip.sha256` است. Digest در sidecar نگهداری می‌شود تا self-reference باعث تغییر hash خود آرشیو نشود.
