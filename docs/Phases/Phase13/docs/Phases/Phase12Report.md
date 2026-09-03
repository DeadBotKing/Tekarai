# Phase 12 — Notifications & Communication Foundation — Implementation Report

تاریخ: 2026-08-31 · سند منبع: `docs/Phases/Phase12.md` (بخش‌های 12.0–12.52)

## 1. هدف و رویکرد

فاز ۱۲ یک **زیرساخت Enterprise برای Notification** می‌سازد که از یک هستهٔ یکپارچه
In-App / Email / Push / SMS / Webhook را پوشش دهد، کاملاً Event-Driven باشد و
افزودن کانال جدید بدون تغییر Core ممکن باشد.

فاز ۹ یک اپ `notifications` تک‌گیرنده (یک ردیف نوتیفیکیشن به‌ازای هر گیرنده)
پیاده کرده بود. فاز ۱۲ **بدون شکستن** آن، مدل canonical چندگیرنده را اضافه
می‌کند: یک `Notification` که به چند `NotificationRecipient` فن‌اوت می‌شود و وضعیت
خواندن روی خود گیرنده است (§12.8 — صراحتاً `Notification.isRead` ممنوع است).

## 2. لایه‌بندی (DDD / Clean Architecture)

```
Presentation (views/phase12Views.py → routes)
   → Application (services/phase12Services.py + commands/phase12Commands.py)
       → Domain (entities/phase12Records.py + valueObjects/phase12Types.py + repositories ports)
← Infrastructure (models, repositoriesImpl, channels/webhookChannel, container)
```

- **Domain بدون هیچ import جنگو/Redis/Channels**؛ منطق کسب‌وکار فقط اینجا و در
  لایهٔ application است.
- View/Serializer فقط اعتبارسنجی ورودی و پاکت پاسخ؛ هیچ منطق و ORM ندارد.
- Repositoryها Protocol هستند (پورت)؛ پیاده‌سازی Django در infrastructure.
- همهٔ کوئری‌ها صریحاً `tenantId` دارند (§12.25 ایزولاسیون چندمستأجری).

## 3. موجودیت‌های دامنه (Domain)

| موجودیت | بخش | نقش |
|---|---|---|
| `BroadcastNotification` | §12.3 | یک نوتیفیکیشن، چند گیرنده؛ بدون پرچم خواندن |
| `NotificationRecipient` | §12.7/§12.8 | وضعیت مستقل UNREAD/READ/ARCHIVED/DISMISSED |
| `RecipientDelivery` | §12.14/§12.15 | تحویل یک کانال به یک گیرنده + ماشین وضعیت |
| `DeliveryAttempt` | §12.16 | هر تلاش ارسال (attemptNumber/provider/error/...) |
| `NotificationRule` | §12.24 | قاعدهٔ WHEN/IF/THEN با شرط و استراتژی گیرنده |
| `InboundNotificationEvent` | §12.38 | پوشش idempotent رویداد ورودی از Event Bus |
| `RetryPolicy` (VO) | §12.17 | backoff نمایی قابل‌تنظیم (maxAttempts/delay/cap) |
| `QuietHours` (VO) | §12.21 | پنجرهٔ سکوت روزانه (عبور از نیمه‌شب) |

ثابت‌ها: وضعیت‌های تحویل (PENDING/QUEUED/PROCESSING/SENT/DELIVERED/FAILED/CANCELLED/
EXPIRED/DEAD_LETTER)، شدت (INFO/WARNING/ERROR/CRITICAL) مجزا از اولویت
(§12.6)، مسیریابی کانال بر اساس اولویت (§12.5)، کانال جدید **WEBHOOK** (§12.12).

## 4. ماشین وضعیت تحویل و Retry

- تفاوت **SENT** (provider قبول کرد) و **DELIVERED** (رسید به مقصد) حفظ شد.
- هر تلاش ناموفق یک `DeliveryAttempt` ثبت می‌کند؛ اگر `attemptCount` به
  `maxAttempts` برسد وضعیت به **DEAD_LETTER** می‌رود (§12.18) و برای Operations
  قابل فهرست/Retry دستی است.
- بین تلاش‌ها `nextAttemptAt` با backoff نمایی محاسبه می‌شود (هیچ عددی در محل
  فراخوانی hard-code نیست؛ `RetryPolicy` قابل‌تزریق است).

## 5. داده و پایگاه‌داده (§12.47/§12.48/§12.49)

migration `0002_phase12_broadcast` شش جدول جدید می‌سازد:

- `notifications` (broadcast؛ جدول مفهومی §12.47)
- `notificationRecipients` (وضعیت خواندن؛ ایندکس ترکیبی inbox)
- `notificationDeliveries` (تحویل کانال‌محور؛ ایندکس اسکن retry)
- `notificationAttempts` (تاریخچهٔ تلاش‌ها)
- `notificationRules` (قواعد WHEN/IF/THEN)
- `notificationEvents` (لاگ idempotent رویداد)

ایندکس‌های ترکیبی مطابق الگوی کوئری:
`(tenantId, userId, recipientState, createdAt)` برای صندوق/unread و
`(deliveryStatus, nextAttemptAt)` برای worker اسکن retry.
Constraintها: یکتایی `(notification, recipient, channel)`، یکتایی
`(delivery, attemptNumber)`، یکتایی idempotency `(tenant, idempotencyKey)` و
یکتایی `(tenant, eventId)`.

جدول‌های فاز ۹ (`notificationsNotifications`, `notificationsDeliveries`,
templates, preferences, policies, devices, schedules, digests) بدون تغییر باقی
ماندند؛ فاز ۱۲ کاملاً افزایشی است.

## 6. کانال‌ها و Providerها

- کانال **WEBHOOK** با `WebhookDeliveryChannel` و `WebhookProviderPort` اضافه
  شد؛ provider پیش‌فرض فقط لاگ می‌گیرد (بدون شبکه در تست/توسعه) و یک provider
  واقعی HTTP بدون تغییر application قابل‌تزریق است. نبود URL خطای دائمی
  (`WEBHOOK_URL_MISSING`) می‌دهد.
- Core به هیچ provider خاصی وابسته نیست (§12.31/§12.32/§12.33) — همان الگوی
  Adapter فاز ۹.

## 7. Event-Driven، Idempotency و Outbox/Queue

- `EventIntakeService` نقطهٔ ورود از Event Bus است؛ با `eventId` دوباره‌پردازش
  را خنثی می‌کند (§12.38)، قواعد فعال را ارزیابی می‌کند و نوتیفیکیشن می‌سازد.
- ارسال خارجی هرگز HTTP request را بلاک نمی‌کند (§12.40): deliveryها در وضعیت
  QUEUED ساخته می‌شوند و worker (`processDue` / `runNotificationWorker` فاز ۹)
  آن‌ها را پردازش می‌کند.
- رویدادهای دامنه (notificationCreated / Read / retryScheduled / deadLettered)
  از طریق dispatcher پخش و برای in-app از طریق Channels realtime push می‌شوند.

## 8. API (§12.29)

زیر `/api/v1/notifications`:

- `POST/GET broadcasts` — ساخت چندگیرنده / صندوق گیرندهٔ فراخوان
- `GET broadcasts/unread-count`
- `POST broadcasts/{id}/read|unread|archive|dismiss`
- `GET deliveries` (با `?deadLetterOnly=1` یا `?notificationId=`)
- `POST deliveries/{id}/retry`
- `POST rules` — تعریف قاعده
- `POST events` — ورود idempotent رویداد

همه با احراز هویت؛ درخواست بدون توکن 401 می‌گیرد (§12.26).

## 9. تست‌ها

مجموعاً **51 تست جدید**، همگی سبز؛ کل مجموعه **622 تست OK**:

- `tests/unit/testPhase12Domain.py` — 28 تست (فن‌اوت، وضعیت گیرنده، ماشین
  تحویل، backoff/dead-letter، quiet hours، مسیریابی اولویت، قواعد، idempotency)
- `tests/application/testPhase12UseCases.py` — 15 تست (سرویس‌ها روی DB واقعی،
  ایزولاسیون tenant، retry/dead-letter، قواعد و رویداد، webhook)
- `tests/integration/testPhase12ApiContract.py` — 8 تست (HTTP کامل، 401، 400،
  retry، رویداد idempotent)

`ruff check` روی همهٔ فایل‌های جدید: **All checks passed**. مهاجرت‌ها بدون drift.

## 11. نکات تکاملی برای فازهای بعد

- Template versioning/localization و preference hierarchy در فاز ۹ موجود است و
  از طریق سرویس‌های همان اپ قابل استفادهٔ مدل broadcast است.
- اتصال واقعی Event Bus بین دامنه‌های کسب‌وکار و `EventIntakeService` با
  Transactional Outbox در فازهای یکپارچه‌سازی تکمیل می‌شود (پورت آماده است).
