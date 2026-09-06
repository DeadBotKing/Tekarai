# Phase 13-Z — Public API, Async Agent Execution, Migration & Release

**فاز:** 13 — AI Platform & Intelligence Foundation  
**زیر‌فاز:** Z از A تا Z  
**وضعیت:** IMPLEMENTED  
**تاریخ:** 2026-09-06  
**سند مادر:** [`../Phase13.md`](../Phase13.md) (§38 تا §54)  
**پیش‌نیاز:** [Y](Phase13-Y.md) — `GATE_Y=GREEN`  
**گزارش اجرا:** [Phase13-Z-ExecutionReport.md](Phase13-Z-ExecutionReport.md)

---

## ۱. هدف

Z مرز عمومی و قابل انتشار Foundation ساخته‌شده در A تا Y را تکمیل می‌کند:

1. REST API نسخه‌دار زیر `/api/v1/ai/`؛
2. Composition Root مستقل از View؛
3. اجرای هم‌زمان و ناهم‌زمان Agent؛
4. صف Pull برای تأیید انسانی و Dual Control؛
5. اتصال Worker فاز P به `AGENT_RUN`؛
6. کنترل مجوز زنده در زمان Worker، نه اعتماد به Snapshot؛
7. گیت Migration/Configuration/Release؛
8. تست عمودی HTTP → Application → Domain → ORM → Provider Test؛
9. مستندات عملیات، Rollback و Release.

## ۲. تصمیم‌های نهایی معماری

### Z-D1 — API فقط Application Layer را صدا می‌زند

View هیچ Model، Repository یا Provider SDK را import نمی‌کند. مسیر رسمی:

```text
DRF View → Input Serializer → infrastructure.container
         → Application Service → Domain → Port → Adapter/Repository
```

### Z-D2 — Tenant هرگز از Body یا Query دریافت نمی‌شود

`tenantId` فقط از `RequestContext` احراز‌شده می‌آید. همهٔ Storeها دوباره همان
Tenant را در Query اعمال می‌کنند؛ شناسهٔ Tenant دیگر مانند Not Found رفتار می‌کند.

### Z-D3 — Async یک Contract مستقل نیست

`mode=ASYNC` همان `RunAgentCommand` فاز Y را از طریق Job نوع `AGENT_RUN` اجرا
می‌کند. Worker هیچ مسیر ویژه‌ای برای دور زدن Gatekeeper، Audit یا Tool Chain ندارد.

### Z-D4 — مجوز در Worker دوباره بررسی می‌شود

Job فقط هویت Actor را نگه می‌دارد. `SharedGateAgentPermissionChecker` هنگام اجرای
واقعی، Permission Gate هویت را دوباره می‌خواند. لغو نقش میان Submit و Execute
بلافاصله مؤثر است.

### Z-D5 — Idempotency برای Async اجباری است

درخواست Async بدون `idempotencyKey` یا Header `Idempotency-Key` با 400 رد می‌شود.
کلید در Tenant scope است و Payload متفاوت با کلید یکسان Conflict می‌سازد.

### Z-D6 — دادهٔ صف حداقلی و پاک‌سازی‌شده است

ورودی Agent پیش از ذخیره در `aiJobs` با تعریف مشترک O/X/Y پاک‌سازی می‌شود.
Job API هیچ‌وقت `payload` را برنمی‌گرداند؛ فقط وضعیت و `resultSummary` محدود را
نمایش می‌دهد.

### Z-D7 — تأیید انسانی Pull Queue است

مسیر `/approvals` صف Tenant-scoped تأیید است. تخصیص خودکار Approver یا ارسال
اعلان عمومی انجام نمی‌شود، چون پلتفرم در Phase 13 قرارداد سازمانیِ «چه کسی
Approver این Agent است» ندارد. افزودن Notification بدون این Policy می‌توانست
داده را برای گیرندهٔ اشتباه آشکار کند. اتصال Event/Notification پس از تعریف
Approval Assignment Policy انجام می‌شود؛ Polling API، Audit و Dual Control اکنون
کامل و قابل اتکا هستند.

### Z-D8 — Fake Provider فقط Opt-in است

`DETERMINISTIC` در Testing فعال است. Production تا تعیین صریح Provider و Model
Fail-closed باقی می‌ماند و Readiness سبز نمی‌شود.

### Z-D9 — ابزار بدون Runner اجرا نمی‌شود

رجیستری X می‌تواند Definition را Resolve کند؛ اما نبود Runner ثبت‌شده باعث
Fail-closed می‌شود. API یا Agent هیچ callable دلخواهی از Payload نمی‌سازد.

## ۳. Permission Matrix

| Action | Permission |
|---|---|
| خواندن Agent/Run/Step/Job | `ai.agent.read` |
| ثبت، Versioning و Lifecycle | `ai.agent.manage` |
| اجرای Sync/Async و Cancel Job | `ai.agent.run` |
| Approval/Reject تعریف و اجرای Agent | `ai.agent.approve` |
| اجرای Tool از زنجیره X | `ai.tool.invoke` |

Platform Admin همه را دارد؛ Tenant Admin همهٔ Actionهای AI را دارد؛ Member فقط
`read` و `run` دارد. Permission تعریف‌شده در خود Agent همچنان یک Gate دوم است.

## ۴. API Contract

تمام پاسخ‌ها Envelope استاندارد Phase 6 دارند:

```json
{"success": true, "data": {}, "meta": {"correlationId": "..."}, "errors": []}
```

### ۴.۱ Registry

| Method | Path | نتیجه |
|---|---|---|
| `GET` | `/api/v1/ai/agents` | فهرست Tenant؛ filter: `status`, `limit` |
| `POST` | `/api/v1/ai/agents` | Definition نسخه‌ای در DRAFT |
| `GET` | `/agents/{code}/versions/{version}` | Descriptor امن؛ بدون Instructions |
| `POST` | `/agents/{code}/versions` | ساخت نسخهٔ بعدی از Overrides |
| `POST` | `/agents/{code}/versions/{version}/{action}` | `submit/approve/reject/suspend/resume/retire` |

### ۴.۲ Execution

| Method | Path | نتیجه |
|---|---|---|
| `POST` | `/agents/{code}/runs` | Sync=201/202، Async=202 |
| `GET` | `/runs` | filter: `agentCode`, `status`, `limit` |
| `GET` | `/runs/{runId}` | Run Descriptor |
| `GET` | `/runs/{runId}/steps` | Trace ترتیبی Model/Tool |

نمونهٔ Async:

```json
{
  "mode": "ASYNC",
  "idempotencyKey": "invoice-analysis-42",
  "input": {"task": "analyze", "documentId": "..."},
  "priority": 5
}
```

### ۴.۳ Approval

| Method | Path | نتیجه |
|---|---|---|
| `GET` | `/approvals?decision=PENDING` | صف تأیید Tenant |
| `GET` | `/approvals/{id}` | وضعیت و Remaining |
| `POST` | `/approvals/{id}/grant` | تأیید؛ Self-approval ممنوع |
| `POST` | `/approvals/{id}/deny` | رد با Reason |

### ۴.۴ Job و Release

| Method | Path | نتیجه |
|---|---|---|
| `GET` | `/jobs` | به‌طور پیش‌فرض فقط `AGENT_RUN` |
| `GET` | `/jobs/{id}` | Status و Result Summary؛ بدون Payload |
| `POST` | `/jobs/{id}/cancel` | Cancel قبل از Settlement |
| `GET` | `/release/readiness` | 200 آماده، 503 Fail-closed |

## ۵. HTTP و Error Semantics

- `201`: Definition یا Run هم‌زمان ایجاد شد؛
- `202`: Job پذیرفته شد یا Run منتظر Approval است؛
- `400`: Serializer/Query/Idempotency نامعتبر؛
- `401`: Session معتبر نیست؛
- `403`: Action Permission یا Tenant Context وجود ندارد؛
- `404`: منبع در Tenant فعلی وجود ندارد؛
- `409/422/429/503`: کد پایدار Domain طبق `AI_*`؛
- Readiness ناموفق عمداً `503` می‌دهد.

## ۶. Async State Mapping

```text
HTTP 202 → AIJob(PENDING)
worker claim → AIJob(RUNNING)
AgentApplicationService.runAgent
  ├─ COMPLETED/DENIED/PENDING-APPROVAL = business result → Job SUCCEEDED
  └─ transport/provider error retryable → Job retry/backoff/dead
```

Approval-required یک شکست Transport نیست؛ Retry خودکار باعث ساخت Run و اعلان
تکراری می‌شد. Client پس از Grant همان Input را با `approvalId` دوباره Submit
می‌کند.

## ۷. پیکربندی Release

```text
aiAgentDefaultProvider
aiAgentDefaultModel
aiAgentAllowDeterministicProvider=false
```

علاوه بر آن `AI_AGENT_*`، `AI_QUEUE_*`، `AI_AUDIT_*` و Provider Adapterهای L
باید معتبر باشند. هیچ Credential در Readiness، Log، API یا Archive چاپ نمی‌شود.

## ۸. Migration

Z جدول جدیدی نیاز ندارد؛ Migrationهای `0001` تا `0012_agentPlatform` همان Schema
نهایی‌اند. این یک تصمیم مثبت است، نه حذف کار: API فقط Application Contract موجود
را معرفی می‌کند. Gateهای اجباری:

```bash
python manage.py migrate --plan
python manage.py makemigrations --check
python manage.py checkPhase13Release
```

Migration drift موجود در app دیگری (`communication.0005`) متعلق به baseline پیش
از Z است و در گزارش جدا ثبت شده؛ AI migration graph drift ندارد.

## ۹. Readiness

Command و API موارد زیر را بدون Secret گزارش می‌کنند:

- Agent/Queue/Audit enabled؛
- هیچ AI Migration معوق نباشد؛
- حداقل یک Provider پیکربندی شده باشد؛
- Default Provider و Default Model صریح باشند.

Production در صورت شکست هرکدام Release-ready نیست.

## ۱۰. Deployment

1. Backup از DB و Secret store؛
2. نصب Dependencyها؛
3. `check --deploy`؛
4. `migrate --plan` و بازبینی؛
5. `migrate`؛
6. تنظیم Provider/Model بدون چاپ Secret؛
7. `checkPhase13Release`؛
8. Deploy API؛
9. Deploy حداقل یک `runAiWorker`؛
10. Smoke: login، readiness، list agents، یک deterministic/provider sandbox run؛
11. مشاهدهٔ Queue depth/error و Audit chain.

## ۱۱. Rollback

- ابتدا API جدید و Worker Agent را Drain/Disable کنید؛
- `AI_AGENT_ENABLED=false` و سپس worker را متوقف کنید؛
- Jobهای Running تا پایان Lease دست‌نخورده می‌مانند؛
- Code rollback انجام شود؛
- Migration 0012 فقط در صورت تأیید DBA و نبود دادهٔ مورد نیاز Down migrate شود؛
- Audit ledger حذف یا بازنویسی نمی‌شود؛
- پس از rollback، `check` و endpointهای Phase 1–12 Smoke شوند.

## ۱۲. تست پذیرش

- Authentication و Action Permission؛
- Envelope و Validation؛
- Registry lifecycle؛
- Tenant isolation با Foreign row واقعی؛
- Sync deterministic run و Step persistence؛
- Async idempotency و Worker settlement؛
- Redaction راز در Job؛
- عدم نمایش Job payload؛
- High-risk approval با کاربر دوم و Resume؛
- Readiness و AI migration state؛
- Suite کامل Regression، Ruff، Format، Mypy و Secret scan.

## ۱۳. فایل‌های خروجی

- `apps/ai/presentation/api/{serializers.py,views.py,urls.py}`
- `apps/ai/infrastructure/{container.py,agentRuntime.py}`
- `apps/ai/application/services/agentJobService.py`
- `apps/ai/management/commands/checkPhase13Release.py`
- `backend/release_phase13.{sh,ps1}`
- `tests/integration/testPhase13ReleaseApiContract.py`
- تغییر Queue vocabulary، Worker، URL root، Settings و Permission Catalogue
- این قرارداد و گزارش اجرای Z

## ۱۴. معیار Done

- [x] API فقط Application را صدا می‌زند؛
- [x] Tenant از Context می‌آید؛
- [x] Sync و Async Agent قابل استفاده‌اند؛
- [x] `AGENT_RUN` Handler در Worker ثبت است؛
- [x] Async idempotent و ورودی صف redacted است؛
- [x] Approval Queue و Dual Control از API قابل استفاده‌اند؛
- [x] Permissionها در Catalogue و Role preset ثبت شده‌اند؛
- [x] Production provider fail-closed است؛
- [x] Readiness API/Command وجود دارد؛
- [x] Migration plan و rollback ثبت شده؛
- [x] تست عمودی بدون Internet/API key وجود دارد؛
- [x] Documentation و Release checklist کامل است.

## ۱۵. Gate

با سبز شدن شواهد گزارش اجرا:

`GATE_Z=GREEN — PHASE_13=COMPLETE`
