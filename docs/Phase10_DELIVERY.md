# Phase 10 — Communication Platform: Implementation & Delivery Notes

سند تحویل فاز ۱۰ (Communication Platform) روی‌روی بستر فاز ۸. این سند پیاده‌سازی
انجام‌شده را به ۷۵ بخش سند `docs/Phases/Phase10.md` نگاشت می‌دهد و قراردادهای
معماری، دامنه، API، رویداد و تست را مستند می‌کند.

اصول حاکم (§1): DDD / Clean Architecture / Modular Monolith / Event Driven /
API First / Security First / Multi-Tenant / Audit First / Provider Agnostic /
Real-Time Ready.

---

## 1. لایه‌بندی و مرز معماری (§1، §2، §61–§66، §71، §74)

فاز ۱۰ به‌صورت یک **افزونه (extension)** روی بستر فاز ۸ پیاده شد، بدون آن‌که
به جدول‌ها یا رفتارهای تثبیت‌شدهٔ فاز ۸ دست‌زده شود (۴۵۷ تست قبلی همچنان سبزند).

| لایه | فایل‌های جدید فاز ۱۰ |
| --- | --- |
| domain / valueObjects | `domain/valueObjects/phase10Types.py` |
| domain / entities | `domain/entities/phase10Records.py` |
| domain / services | `domain/services/meetingPermissions.py` |
| domain / repositories (port) | `domain/repositories/phase10Repositories.py` |
| application / commands | `application/commands/phase10Commands.py` |
| application / dto | `application/dto/phase10Dtos.py` |
| application / useCases | `application/useCases/phase10UseCases.py` |
| infrastructure / persistence | ۵ مدل در `infrastructure/models.py` + `migrations/0002_phase10_communication.py` |
| infrastructure / repositories | `infrastructure/repositories/phase10RepositoriesImpl.py` |
| infrastructure / providers | `infrastructure/services/callProviderImpl.py` (WebRTC) |
| presentation / REST | `presentation/api/views/phase10Views.py` + مسیرها در `urls/communicationRoutes.py` |

قواعد سخت (§74) رعایت شده‌اند:

- هیچ منطق تجاری در `models.py` / `views.py` / `serializers.py` / `consumers.py`
  نیست؛ ویوها نازک‌اند (احراز → مجوز → فراخوانی use case → پاسخ، §64).
- لایهٔ domain هیچ import‌ای از Django ORM / Redis / Channels / WebRTC ندارد.
- فایل در DB ذخیره نمی‌شود؛ پیاده‌سازی‌ها فقط `reference` نگه می‌دارند (§16، §32).
- Presence فقط در Redis/کش کش زندگی می‌کند و منبع حقیقت نیست (§17، §67).
- همهٔ repositoryهای جدید `tenantId` را به‌صورت صریح در کویری اعمال می‌کنند
  (§41)؛ تست جداسازی بین‌مستأجری وجود دارد.
- رویداد‌ها فقط درون تراکنش با Outbox منتشر می‌شوند (§65، §66).
- تاریخچهٔ پیام با Cursor (`before`/`after`) است؛ Offset برای history حجیم ممنوع (§53).

---

## 2. مدل دامنه (§4–§5، §9، §11، §23، §27–§29، §32–§35)

موجودیت‌های جدید فاز ۱۰ (هرکدام Aggregate/Entity خالص دامنه):

- **MessageRevision** (§11): `id, messageId, previousBody, newBody, editedBy,
  editedAt`. هنگام ویرایش پیام به‌صورت خودکار یک رکورد ساخته می‌شود
  (تزریق `revisionRepository` به `EditMessageUseCase`)؛ بدنه‌ها هرگز بازنویسی
  مخرب ندارند (Compliance/Audit).
- **MeetingTranscript** (§34): `id, meetingId, language, status
  (PENDING|PROCESSING|READY|FAILED), contentReference, createdAt, updatedAt`.
  مستقل از Recording است؛ چرخه‌عمر با متدهای `request → transitionTo → READY`.
- **TranscriptSegment** (§35): `id, transcriptId, speakerId, startTimeSeconds,
  endTimeSeconds, text, confidence, sequence`؛ اعتبارسنجی دامنه برای ترتیب زمان
  و بازهٔ confidence.
- **UserBlock** (§70): `id, tenantId, blockerId, blockedUserId, scopes[],
  status (ACTIVE|REMOVED), reason, createdAt, liftedAt`؛ با `covers(scope)` و
  `lift(now)`.
- **CapabilityOverride** (§30): override دانه‌ای قابلیت جلسه برای یک کاربر در
  یک جلسه (`meetingId, userId, capability, granted, tenantId`).

نقش‌های جلسه (§29): `HOST, CO_HOST, PARTICIPANT, GUEST`.
قابلیت‌ها (§30): `CAN_JOIN, CAN_SPEAK, CAN_VIDEO, CAN_SHARE_SCREEN, CAN_RECORD,
CAN_CHAT, CAN_INVITE, CAN_REMOVE_PARTICIPANT, CAN_END_MEETING`.
سرویس دامنه `meetingPermissions` (§46) ماتریس نقش→قابلیت را به‌صورت خالص پیاده
می‌کند: برگزارکننده همیشه HOST است؛ ضبط/حذف/پایان نیاز به جلسهٔ زنده دارند.

ثابت‌های حضور/پیام برای تکمیل قراردادها: presence شامل `INVISIBLE` (§17، حریم
خصوصی — برای دیگران OFFLINE دیده می‌شود) و انواع پیام/تماس مطابق §9/§23.

---

## 3. سیاست Block (§69، §70)

تابع سیاست دامنه-کاربرد `assertNotBlocked(blockRepository, tenantId, senderId,
recipientId, scope)` دوطرفه عمل می‌کند: اگر هر دو طرف در scope مذکور بلاک باشند،
`BusinessRuleViolationError(ruleId="PHASE10-BR_UserBlock")` پرتاب می‌شود.

- پیام مستقیم (DIRECT): در `SendMessageUseCase` با scope `DIRECT_MESSAGE`.
- تماس مستقیم: در `StartCallUseCase` با scope `CALL`.
- دعوت به جلسه: در `CreateMeetingUseCase` هنگام افزودن مدعو با scope
  `MEETING_INVITATION`.

تزریق به‌صورت پارامتر اختیاری `blockRepository=None` انجام شده تا سیم‌کشی فاز ۸
بدون تغییر بماند؛ container فاز ۱۰ پیاده‌سازی واقعی را تزریق می‌کند.

---

## 4. سرویس‌های کاربردی (use caseها) (§45)

- `ListMessageRevisionsUseCase` — تاریخچهٔ ویرایش پیام (مجوز: عضویت در مکالمه).
- `RequestTranscriptUseCase` — درخواست رونوشت برای جلسه (idempotent: یک جلسه یک
  رونوشت فعال دارد)؛ `requiredAction="meeting.manage"`.
- `CompleteTranscriptUseCase` — تثبیت رونوشت با `contentReference` و سگمنت‌ها،
  انتشار `TranscriptReady` (ادغام AI/نوتیفیکیشن، §36/§38).
- `GetTranscriptUseCase` — واکشی رونوشت و سگمنت‌ها برای مجازها.
- `SetMeetingCapabilityUseCase` / `CheckMeetingCapabilityUseCase` — override و
  محاسبهٔ قابلیت مؤثر (ماتریس نقش + override).
- `BlockUserUseCase` / `UnblockUserUseCase` / `ListBlocksUseCase` — بلاک کاربر
  (idempotent، با رویداد `userBlocked`/`userBlockLifted`).
- `CreateCallSessionUseCase` / `JoinCallSessionUseCase` — bootstrap provider-
  agnostic تماس (§25)؛ WebRTC پیاده‌سازی پیش‌فرض پشت پورت `CallProvider` است
  (Twilio/Agora/Jitsi بدون تغییر دامنه در آینده).

مجوزها با کدهای action فاز ۸ هم‌تراز شدند (`meeting.manage`, `recording.manage`)
تا با کاتالوگ مجوز و گرانت‌های `conversation.create/conversation.moderate/
letter.*` بخوانند.

---

## 5. قرارداد REST (§48) — زیر `/api/v1/communication`

| متد | مسیر | عمل | مجوز |
| --- | --- | --- | --- |
| GET | `messages/{messageId}/revisions` | تاریخچهٔ ویرایش (§11) | عضو مکالمه |
| POST | `meetings/{meetingId}/transcript` | درخواست رونوشت (idempotent) | `meeting.manage` |
| GET | `meetings/{meetingId}/transcript` | واکشی رونوشت | عضو/برگزارکننده |
| POST | `transcripts/{transcriptId}/complete` | تثبیت رونوشت + سگمنت | `meeting.manage` |
| POST | `meetings/{meetingId}/capabilities` | تنظیم override قابلیت | `meeting.manage` |
| GET | `meetings/{meetingId}/capabilities?userId&capability` | قابلیت مؤثر | احراز هویت |
| GET | `blocks` | فهرست بلاک‌ها | احراز هویت |
| POST | `blocks` | بلاک کاربر | احراز هویت |
| DELETE | `blocks/{blockedUserId}` | رفع بلاک | احراز هویت |
| POST | `call-sessions` | ساخت نشست تماس (provider-agnostic) | احراز هویت |

ترتیب مسیر‌ها در `communicationRoutes.py` طوری است که مسیرهای خاص فاز ۱۰
(`.../transcript`, `.../capabilities`, `transcripts/.../complete`, `blocks/...`)
**قبل از** مسیر عمومی `meetings/{meetingId}/{action}` ثبت شده‌اند تا بلعیده
نشوند. همهٔ endpointها در `registerCommunicationEndpoints()` برای OpenAPI
ثبت شده‌اند (§48).

---

## 6. رویداد‌ها و Outbox (§44، §50، §65، §66)

رویداد‌های دامنهٔ جدید: `transcriptRequested`, `transcriptProcessing`,
`transcriptReady`, `userBlocked`, `userBlockLifted`؛ و رویداد ادغامی (integration)
`CommunicationTranscriptReadyV1` با نسخه‌گذاری و `tenantId`. رویداد‌های فاز ۸
(CallStarted، MeetingCreated، MessageEdited، ...) بدون تغییر به مسیر Outbox می‌روند.
قرارداد رویداد WebSocket نسخه‌دار است: `{type, version, tenantId, ..., payload}`
(§50).

---

## 7. WebSocket / Real-time (§20، §21، §49)

فاز ۸ یک consumer نازک (`presentation/ws/communicationConsumer.py`) دارد که فقط
اتصال/احراز/اشتراک/دریافت/ارسال را بر عهده دارد و منطق را به use case واگذار
می‌کند (§21). فاز ۱۰ منطق تجاری جدیدی به consumer اضافه نکرد؛ نشست‌های تماس از
طریق REST/use case bootstrap می‌شوند و سیگنالینگ رسانه از همان کانال موجود انجام
می‌شود. اتصال و حضور WebSocket مشمول rate limit است (§68).

---

## 8. Rate limiting (§68)

شش scope در `API_RATE_LIMIT_POLICIES` (settings) و در دکوریتور `enforceRateLimit`
اعمال شده‌اند:

| scope | (limit, window s) | نقطهٔ اعمال |
| --- | --- | --- |
| `communication:sendMessage` | 30 / 60 | ارسال پیام (REST + WS هم‌مسیر) |
| `communication:createConversation` | 20 / 300 | ساخت مکالمه/کانال |
| `communication:callStart` | 10 / 60 | شروع تماس / نشست |
| `communication:meetingCreate` | 20 / 300 | ساخت جلسه |
| `communication:wsConnection` | 30 / 60 | اتصال WebSocket |
| `communication:presenceUpdate` | 120 / 60 | به‌روزرسانی حضور |

---

## 9. تست‌ها (§58، §59)

۳۷ تست جدید فاز ۱۰ (همه سبز):

- `tests/unit/testPhase10Domain.py` (۱۷ تست): ماتریس مجوزهای جلسه، چرخه‌عمر
  رونوشت، اعتبارسنجی سگمنت/revision، بلاک کاربر.
- `tests/application/testPhase10UseCases.py` (۱۱ تست): جریان رونوشت +
  idempotency، override قابلیت، قابلیت ناشناخته، بلاک/لیست/رفع‌بلاک + idempotency،
  ثبت revision هنگام edit، رد پیام DIRECT پس از بلاک، **رد تماس مستقیم و دعوت
  جلسه پس از بلاک**، جداسازی بین‌مستأجری.
- `tests/integration/testPhase10ApiContract.py` (۹ تست): قرارداد REST واقعی
  (بلاک، capability، رونوشت complete، revisions)، تست‌های امنیتی ۴۰۱، حریم
  خصوصی INVISIBLE، و اعمال واقعی rate limit (429).

اجرای کامل:

```
cd backend
./venv/bin/python manage.py test --settings=config.settings.testing
# Ran 494 tests ... OK  (457 پایه + 37 جدید)
```

تست‌های امنیتی §59 پوشش می‌دهند: دسترسی بین‌مستأجری، دسترسی کاربر بیگانه به
مکالمه خصوصی، و دسترسی بدون توکن به endpointهای جدید (401).

---

## 10. مهاجرت پایگاه‌داده (§42، §43)

مهاجرت `0002_phase10_communication.py` پنج جدول جدید می‌سازد (بدون AlterField):

- `communicationMessageRevisions`
- `communicationMeetingTranscripts`
- `communicationTranscriptSegments`
- `communicationUserBlocks`
- `communicationMeetingCapabilityOverrides`

شاخص‌ها روی `tenantId` و کلیدهای دسترسی (messageId, meetingId, blocker/blocked,
meeting+user+capability) تنظیم شده‌اند. تنها drift باقی‌ماندهٔ `makemigrations`
مربوط به `channelprofilemodel.conversationId` است که از فاز ۹ وجود داشته و عمداً
دست‌نخورده مانده است.

---

## 11. نقشهٔ بخش‌ها (§75 خروجی نهایی)

موارد §75 به این صورت تحویل شده‌اند: مدل دامنه (§2)، قواعد تجاری و ماتریس مجوز
(§2/§30/§46)، قرارداد REST (§5 این سند)، رویداد/Outbox (§6)، انتزاع ارائه‌دهنده
(§4، `CallProvider` + WebRTC)، مشخصات جلسه/ضبط/رونوشت (§2)، نرخ محدودیت (§8)،
مدل امنیتی/چندمستأجری (§3/§9 + تست‌ها)، و استراتژی تست (§9). یکپارچگی AI
(§36/§37) و نوتیفیکیشن (§38) از طریق رویداد `TranscriptReady` و پورت‌های خنثی
انجام می‌شود؛ دامنه هرگز به ارائه‌دهندهٔ مشخص (OpenAI و…) وابسته نیست (§71).

انجام‌شده روی بستر فاز ۸ بدون شکست تست‌های قبلی؛ هیچ منطق تجاری مهمی خارج از
مرزهای domain/application قرار نگرفته است.
