# افزودن «گفت‌وگو» (چت) به برنامه — گزارش پیاده‌سازی

تاریخ: ۱۴۰۴/۰۷/۰۴ (۲۶ سپتامبر ۲۰۲۶)

## ۱) خلاصهٔ صادقانهٔ کاری که انجام شد

بک‌اند چت **از قبل در پروژه وجود داشت** (اپ `backend/apps/communication` با ۵۸ مسیر REST،
مدل‌های مکالمه/پیام/مشارکت و یک گیت‌وی وب‌سوکت). چیزی که وجود نداشت، **رابط کاربری** بود:
هیچ صفحه‌ای، هیچ سرویسی و حتی هیچ endpoint ارتباطی در `endpoints.ts` ثبت نشده بود.

کار این فاز = **ساخت کامل لایهٔ فرانت فارسی/راست‌به‌چپ و وصل کردن آن به همان API موجود**.
هیچ فایلی در بک‌اند تغییر نکرد.

## ۲) فایل‌های ساخته‌شده و تغییر‌یافته

| فایل | وضعیت | خطوط | نقش |
|---|---|---|---|
| `frontend-web/src/pages/ChatPage.tsx` | جدید | ۹۸۹ | صفحهٔ گفت‌وگو: فهرست مکالمه‌ها، رشتهٔ پیام، نوشتن، پاسخ، ویرایش، حذف، واکنش، اعضا، بایگانی، جست‌وجو |
| `frontend-web/src/features/communication/chatService.ts` | جدید | ۲۲۳ | کلاینت REST روی `/api/v1/communication/**` + نگاشت DTO به تایپ‌های دامنه |
| `frontend-web/src/features/communication/chatDemoData.ts` | جدید | ۳۴۷ | دادهٔ نمونهٔ فارسی + فروشگاه درون‌حافظه با ماندگاری `localStorage` برای حالت دمو |
| `frontend-web/src/features/communication/useChatRealtime.ts` | جدید | ۱۲۸ | هوک وب‌سوکت `ws/communication/` (subscribe / typing / رویدادها) |
| `frontend-web/src/styles/chat.css` | جدید | ۴۶۵ | استایل RTL پیام‌رسان (حباب‌های چپ/راست، واکنش‌ها، کامپوزر، واکنش‌گرا) |
| `frontend-web/src/tests/chat.test.tsx` | جدید | ۲۲۸ | ۸ تست: نگاشت داده، مسیرهای API، فروشگاه آفلاین، رندر صفحه، ناوبری |
| `frontend-web/src/core/api/endpoints.ts` | ویرایش | +۱۷ کلید | ثبت مسیرهای communication |
| `frontend-web/src/shared/types/domain.ts` | ویرایش | +۱۰۴ | تایپ‌های `Conversation`, `ChatMessage`, `ConversationParticipant`, … |
| `frontend-web/src/core/localization/i18n.ts` | ویرایش | +۶۹ کلید | همهٔ متن‌های فارسی چت (`chat.*`, `nav.chat`) |
| `frontend-web/src/app/router/AppRouter.tsx` | ویرایش | +۲ | مسیر `/app/chat` |
| `frontend-web/src/app/configuration/navigation.ts` | ویرایش | +۸ | گروه ناوبری «گفت‌وگو» |
| `frontend-web/src/shared/components/Icon.tsx` | ویرایش | +۳ آیکون | `message`, `hash`, `archive` |
| `frontend-web/src/app/App.tsx` | ویرایش | +۱ | import استایل چت |

## ۳) قابلیت‌هایی که واقعاً کد شده‌اند

**فهرست مکالمه‌ها (ستون راست)**
- سه نوع مکالمه: دونفره (DIRECT)، گروه (GROUP)، کانال (CHANNEL) با آیکون و برچسب فارسی
- شمارندهٔ پیام خوانده‌نشده، پیش‌نمایش آخرین پیام، ساعت آخرین فعالیت
- جست‌وجوی زندهٔ مکالمه‌ها + سوئیچ «نمایش بایگانی»

**رشتهٔ پیام**
- حباب‌های راست/چپ بر اساس فرستنده، آواتار، نام فرستنده، جداکنندهٔ تاریخ (تقویم فارسی)
- ارسال با دکمه یا Enter (و Shift+Enter برای خط جدید) به‌صورت خوش‌بینانه (optimistic) با حالت‌های «در حال ارسال…» و «ارسال نشد»
- پاسخ به پیام (نقل‌قول بالای حباب + نوار پاسخ در کامپوزر)
- ویرایش پیام خودم (با برچسب «ویرایش‌شده»)، حذف پیام خودم (با دیالوگ تأیید و نمایش «این پیام حذف شده است.»)
- واکنش‌ها: ۶ ایموجی سریع، شمارش گروهی، برداشتن واکنش با کلیک دوباره
- علامت‌گذاری خوانده‌شدن هنگام باز کردن مکالمه (`POST conversations/<id>/read`)
- جست‌وجو در پیام‌ها (`GET messages/search?q=`) با پنل نتایج

**اعضا و مدیریت مکالمه**
- مودال اعضا با نقش‌ها (مالک/مدیر/ناظر/عضو/مهمان)، افزودن عضو، حذف عضو با تأیید
- بایگانی مکالمه با تأیید

**ساخت مکالمهٔ جدید**
- دونفره: انتخاب مخاطب از فهرست کاربران
- گروه: نام، توضیح، انتخاب چندتایی اعضا
- کانال: نام، توضیح، شناسه (اعتبارسنجی `^[a-z0-9_-]{2,64}$` همانند بک‌اند)، موضوع، سطح دسترسی (عمومی/خصوصی/محدود)

**بی‌درنگ (Realtime)**
- اتصال به `ws/communication/` با `?token=` فقط وقتی `VITE_REALTIME_ENABLED=true` و حالت دمو خاموش باشد
- `subscribe`/`unsubscribe` روی مکالمهٔ باز، ارسال `typing` با تایمر ۲ ثانیه‌ای، نمایش «در حال نوشتن…»
- رویدادهای `message.created/edited/deleted/reaction*` رشتهٔ باز را تازه می‌کنند و برای مکالمه‌های دیگر فقط نشان خوانده‌نشده را بالا می‌برند
- نشانگر وضعیت در هدر: «برخط» / «نابرخط» / «بی‌درنگ غیرفعال»

## ۴) نگاشت دقیق به API بک‌اند (بدون تغییر در بک‌اند)

| عملیات UI | فراخوانی |
|---|---|
| فهرست مکالمه‌ها | `GET communication/conversations[?includeArchived=true]` |
| ساخت مکالمه | `POST communication/conversations` با `kind=direct|group|channel` |
| بایگانی | `POST communication/conversations/<id>/archive` |
| اعضا | `GET/POST communication/conversations/<id>/participants`، `DELETE …/participants/<userId>` |
| پیام‌ها | `GET communication/conversations/<id>/messages?limit=50[&beforeId=]` |
| ارسال | `POST communication/conversations/<id>/messages` (`body`, `messageType=TEXT`, `replyToId?`, `clientRequestId?`) |
| ویرایش/حذف | `PATCH` / `DELETE communication/messages/<id>` |
| واکنش | `POST communication/messages/<id>/reactions` · `DELETE …/reactions?reaction=<emoji>` |
| خوانده‌شدن | `POST communication/conversations/<id>/read` با `{uptoMessageId}` |
| جست‌وجو | `GET communication/messages/search?q=` |
| فهرست کاربران | `GET users?search=&pageSize=50` (اپ identity) |
| وب‌سوکت | `ws/communication/?token=<accessToken>` |

## ۵) نتایج تست (اجرا شده در همین محیط)

```
npx tsc -b --force              → بدون خطا
npx vitest run                  → Test Files 11 passed (11) | Tests 45 passed (45)
   از این تعداد، chat.test.tsx  → 8 passed
npm run build                   → ✓ built in 3.19s (dist/assets/index-*.js 629.17 kB)
```

تست‌های بک‌اند اجرا **نشد** چون در این فاز هیچ فایل بک‌اندی تغییر نکرد.

## ۶) محدودیت‌ها — آنچه ساخته نشده است

این موارد در API بک‌اند وجود دارند ولی در این UI پیاده نشده‌اند:

- پیوست فایل (`attachments/preflight`)، تماس صوتی/تصویری و جلسه (meeting/call)
- فوروارد پیام، پین پیام، بلاک کاربر، نامهٔ رسمی و سیاست‌های فاز ۱۱
- ترد (threadRootId) به‌صورت پنل جدا؛ فعلاً پاسخ به‌صورت نقل‌قول درون همان رشته است
- بارگذاری تدریجی پیام‌های قدیمی با اسکرول (سرویس `beforeId` را پشتیبانی می‌کند ولی دکمهٔ «بیشتر» در UI نیست)
- حضور (presence) و رسید تحویل تک‌تک کاربران

## ۷) اجرا روی ویندوز

```powershell
cd C:\Users\Mitra\Desktop\Tekarai\frontend-web
npm install
$env:VITE_DEMO_MODE="true"; npm run dev      # حالت دمو، بدون نیاز به بک‌اند
```
سپس در منوی راست، گروه **گفت‌وگو** → صفحهٔ `/app/chat`.

برای اتصال به بک‌اند واقعی به‌جای دمو:
```powershell
$env:VITE_DEMO_MODE="false"
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"
$env:VITE_REALTIME_ENABLED="true"   # فقط اگر سرور ASGI/Channels بالا باشد
npm run dev
```
