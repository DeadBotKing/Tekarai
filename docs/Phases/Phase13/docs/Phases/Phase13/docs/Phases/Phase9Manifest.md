# فاز ۹ — مانیفست (جز به جز)

ساخت کامل پلتفرم اعلان‌ها بر اساس `docs/Phases/Phase9.md` — هر فایل با تست و ممیزی معماری (قوانین RULE A–F، قرارداد کانتینری، واژگان bounded context).

**جمع کل: ۹٬۴۲۷ خط در ۶۹ فایل پایتون** + ۴ فایل تست (۱٬۵۵۶ خط، ۷۱ تست) + ۵ سند.

ممیزهای انجام‌شده:
- ✅ هر ۱۲ جدول §36 (الگوها: templates + templateVersions + policyChannels) با ایندکس‌های §37
- ✅ هر ۱۵ سرویس §38 با نام دقیق سند + سرویس‌های خواندن/ادمین
- ✅ ۱۱ گام worker §32 به‌ترتیب و idempotent
- ✅ ۲۹ اندپوینت REST §40 + WebSocket §41 + ثبت OpenAPI
- ✅ ۴۵۷ تست سبز (۷۱ تست جدید فاز ۹؛ صفر رگرسیون فازهای ۶–۸)
- ✅ مصرف Outbox فاز ۸ (§30) با جدول مسیریابی config-driven
- ✅ retry نمایی ۳۰ث → ۲د → ۱۰د با سقف ۶۰۰ث؛ خطاهای دائمی هرگز retry نمی‌شوند

### Domain (§3–§29)

| فایل | خطوط |
|---|---|
| `apps/notifications/domain/valueObjects/notificationTypes.py` | 288 |
| `apps/notifications/domain/entities/notification.py` | 217 |
| `apps/notifications/domain/entities/notificationDelivery.py` | 123 |
| `apps/notifications/domain/entities/notificationDevice.py` | 70 |
| `apps/notifications/domain/entities/notificationDigest.py` | 159 |
| `apps/notifications/domain/entities/notificationPolicy.py` | 106 |
| `apps/notifications/domain/entities/notificationPreference.py` | 111 |
| `apps/notifications/domain/entities/notificationTemplate.py` | 97 |
| `apps/notifications/domain/repositories/notificationRepositories.py` | 244 |
| `apps/notifications/domain/services/notificationRules.py` | 170 |

### Application (§38)

| فایل | خطوط |
|---|---|
| `application/commands/notificationCommands.py` | 222 |
| `application/queries/notificationQueries.py` | 71 |
| `application/dto/notificationDtos.py` | 334 |
| `application/services/notificationSupport.py` | 102 |
| `application/services/createNotification.py` | 271 |
| `application/services/resolveRecipients.py` | 79 |
| `application/services/resolvePolicyAndPreferences.py` | 162 |
| `application/services/renderNotificationContent.py` | 121 |
| `application/services/dispatchNotification.py` | 426 |
| `application/services/retryAndAdminServices.py` | 331 |
| `application/services/digestServices.py` | 138 |
| `application/services/scheduleAndExpiryServices.py` | 264 |
| `application/services/notificationReceiptServices.py` | 257 |
| `application/services/preferenceAndDeviceServices.py` | 333 |

### Infrastructure (§12/§13/§30/§31/§36–§39/§41/§44)

| فایل | خطوط |
|---|---|
| `infrastructure/models.py` (۱۲ جدول §36) | 397 |
| `infrastructure/migrations/0001_phase9_notifications.py` | 291 |
| `infrastructure/repositories/notificationRepositoriesImpl.py` | 870 |
| `infrastructure/providers/channelProviders.py` (§13/§48) | 234 |
| `infrastructure/channels/deliveryChannels.py` (§12/§47) | 252 |
| `infrastructure/queue/notificationQueue.py` (§31) | 33 |
| `infrastructure/eventConsumer.py` (§30) | 189 |
| `infrastructure/realtime/notificationRealtime.py` (§41) | 61 |
| `infrastructure/metrics/notificationMetrics.py` (§44) | 107 |
| `infrastructure/services/notificationDirectories.py` (§9/§12) | 131 |
| `infrastructure/container.py` | 536 |
| `management/commands/seedNotifications.py` | 309 |
| `management/commands/runNotificationWorker.py` | 68 |

### Presentation (§40/§41)

| فایل | خطوط |
|---|---|
| `presentation/api/serializers/notificationSerializers.py` | 114 |
| `presentation/api/views/notificationViews.py` (۲۹ اندپوینت + OpenAPI) | 855 |
| `presentation/api/urls/notificationRoutes.py` | 101 |
| `presentation/ws/notificationsConsumer.py` | 137 |
| `presentation/ws/routing.py` | 13 |

### تست‌ها (§49)

| فایل | تست | خطوط |
|---|---|---|
| `tests/unit/testPhase9Domain.py` | 32 | 457 |
| `tests/application/testPhase9UseCases.py` | 19 | 665 |
| `tests/integration/testPhase9ApiContract.py` | 15 | 320 |
| `tests/integration/testPhase9WebsocketGateway.py` | 5 | 114 |
| `tests/support/phase9Helpers.py` | — | 108 |

### تغییرات فراساحتی (مستند در Report §2)

- `config/settings/base.py` · `config/urls.py` · `config/asgi.py` — نصب کانتکست
- `apps/identity/application/services/permissionCatalog.py` — `notification.send/manage`
- `apps/identity/application/services/profileDirectory.py` — قرارداد خواندن پروفایل (RULE E/F)
- `apps/communication/application/services/participantDirectory.py` — قرارداد خواندن اعضا
- `apps/sharedKernel/infrastructure/djangoPorts.py` — رجیستری مشترک dispatcher (یادداشت تکاملی فاز ۹)
- تست‌های معماری: رجیستر گشودن `notifications` + واژگان + hookهای فریمورک

### اسناد

- `docs/Phases/Phase9Report.md` · `docs/Phases/Phase9Manifest.md` (این فایل)
- `docs/adr/ADR-024-Notification-Delivery-Architecture.md`
- `docs/api/NOTIFICATION_API.md`
- `docs/operations/Phase9Runbook.md`
