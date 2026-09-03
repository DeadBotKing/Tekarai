# Phase 08 — Manifest (جز به جز)

بازسازی و ممیزی کامل فاز ۸ بر اساس `docs/Phases/Phase8.md` — هر فایل با تأیید AST و تست.

**جمع کل: 12860 خط در 71 فایل**

ممیزهای انجام‌شده:
- ✅ هر ۱۵ جدول §26 (۱۷ مدل با Outbox و Letters) + ایندکس‌های §27
- ✅ هر ۲۰ سرویس §35 (با نام UseCase — سند صراحتاً اجازه تغییر نام داده)
- ✅ کاتالوگ رویداد §9 کامل: ۲۵ رویداد یکپارچه شامل MessageRead و AITranscriptionCompleted
- ✅ ۴۱ کامند / ۱۳ کوئری / ۵۰ یوزکیس / ۵۳ فکتوری کانتینر — همه سیم‌کشی‌شده
- ✅ ۳۸۶ تست سبز + تست زنده REST و WS روی daphne واقعی

### Domain (§3–§16)

| فایل | خطوط |
|---|---|
| `apps/communication/domain/__init__.py` | 0 |
| `apps/communication/domain/entities/__init__.py` | 0 |
| `apps/communication/domain/entities/call.py` | 211 |
| `apps/communication/domain/entities/conversation.py` | 190 |
| `apps/communication/domain/entities/meeting.py` | 258 |
| `apps/communication/domain/entities/message.py` | 341 |
| `apps/communication/domain/entities/officialLetter.py` | 150 |
| `apps/communication/domain/entities/participant.py` | 207 |
| `apps/communication/domain/entities/recording.py` | 119 |
| `apps/communication/domain/policies/__init__.py` | 0 |
| `apps/communication/domain/repositories/__init__.py` | 0 |
| `apps/communication/domain/repositories/communicationRepositories.py` | 387 |
| `apps/communication/domain/services/__init__.py` | 0 |
| `apps/communication/domain/services/communicationRules.py` | 185 |
| `apps/communication/domain/valueObjects/__init__.py` | 0 |
| `apps/communication/domain/valueObjects/communicationTypes.py` | 265 |
| **جمع Domain (§3–§16)** | **2313** |

### Application (§24–§25/§28/§35)

| فایل | خطوط |
|---|---|
| `apps/communication/application/__init__.py` | 0 |
| `apps/communication/application/commands/__init__.py` | 0 |
| `apps/communication/application/commands/communicationCommands.py` | 288 |
| `apps/communication/application/dto/__init__.py` | 0 |
| `apps/communication/application/dto/communicationDtos.py` | 185 |
| `apps/communication/application/queries/__init__.py` | 0 |
| `apps/communication/application/queries/communicationQueries.py` | 79 |
| `apps/communication/application/services/__init__.py` | 0 |
| `apps/communication/application/services/communicationSupport.py` | 142 |
| `apps/communication/application/useCases/__init__.py` | 0 |
| `apps/communication/application/useCases/callUseCases.py` | 362 |
| `apps/communication/application/useCases/conversationUseCases.py` | 811 |
| `apps/communication/application/useCases/meetingUseCases.py` | 819 |
| `apps/communication/application/useCases/messageUseCases.py` | 700 |
| `apps/communication/application/useCases/presenceAndAiUseCases.py` | 219 |
| **جمع Application (§24–§25/§28/§35)** | **3605** |

### Infrastructure (§26–§29/§36/§39)

| فایل | خطوط |
|---|---|
| `apps/communication/infrastructure/__init__.py` | 0 |
| `apps/communication/infrastructure/container.py` | 883 |
| `apps/communication/infrastructure/metrics/__init__.py` | 0 |
| `apps/communication/infrastructure/metrics/communicationMetrics.py` | 99 |
| `apps/communication/infrastructure/migrations/0001_phase8_communication.py` | 338 |
| `apps/communication/infrastructure/migrations/__init__.py` | 0 |
| `apps/communication/infrastructure/models.py` | 403 |
| `apps/communication/infrastructure/realtime/__init__.py` | 0 |
| `apps/communication/infrastructure/realtime/realtimeInfra.py` | 215 |
| `apps/communication/infrastructure/repositories/__init__.py` | 0 |
| `apps/communication/infrastructure/repositories/communicationRepositoriesImpl.py` | 1150 |
| `apps/communication/infrastructure/services/__init__.py` | 0 |
| `apps/communication/infrastructure/services/aiServicesImpl.py` | 53 |
| `apps/communication/infrastructure/services/userDirectoryImpl.py` | 24 |
| **جمع Infrastructure (§26–§29/§36/§39)** | **3165** |

### Presentation (§8/§30)

| فایل | خطوط |
|---|---|
| `apps/communication/presentation/__init__.py` | 0 |
| `apps/communication/presentation/api/__init__.py` | 0 |
| `apps/communication/presentation/api/serializers/__init__.py` | 0 |
| `apps/communication/presentation/api/serializers/communicationSerializers.py` | 139 |
| `apps/communication/presentation/api/urls/__init__.py` | 0 |
| `apps/communication/presentation/api/urls/communicationRoutes.py` | 159 |
| `apps/communication/presentation/api/views/__init__.py` | 0 |
| `apps/communication/presentation/api/views/communicationViews.py` | 816 |
| `apps/communication/presentation/ws/__init__.py` | 0 |
| `apps/communication/presentation/ws/communicationConsumer.py` | 286 |
| `apps/communication/presentation/ws/routing.py` | 13 |
| **جمع Presentation (§8/§30)** | **1413** |

### Tests (§38)

| فایل | خطوط |
|---|---|
| `tests/unit/testPhase8Domain.py` | 275 |
| `tests/application/testPhase8UseCases.py` | 631 |
| `tests/integration/testPhase8ApiContract.py` | 271 |
| `tests/integration/testPhase8WebsocketGateway.py` | 226 |
| `tests/support/phase8Helpers.py` | 81 |
| **جمع Tests (§38)** | **1484** |

### Config & Integration

| فایل | خطوط |
|---|---|
| `config/asgi.py` | 30 |
| `config/urls.py` | 30 |
| `config/settings/base.py` | 269 |
| `config/settings/production.py` | 103 |
| `requirements/base.txt` | 19 |
| `apps/identity/application/services/principalDirectory.py` | 48 |
| **جمع Config & Integration** | **499** |

### Docs

| فایل | خطوط |
|---|---|
| `../docs/Phases/Phase8Report.md` | 146 |
| `../docs/adr/ADR-023-Realtime-Transport-Channels.md` | 70 |
| `../docs/api/COMMUNICATION_API.md` | 92 |
| `../docs/operations/Phase8Runbook.md` | 73 |
| **جمع Docs** | **381** |