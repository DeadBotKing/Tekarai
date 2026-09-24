# فاز ۲۴ — تاریخچه‌ی کامل دستگاه (Timeline)

## چه چیزی اضافه شد؟
یک **خط زمانی واحد (Timeline)** برای هر دستگاه که همه‌ی رویدادهای آن را به‌ترتیب زمانی (جدیدترین بالا) نشان می‌دهد:

- **ثبت دستگاه** (registered)
- **ویرایش مشخصات دستگاه** (updated)
- **تغییر وضعیت دستگاه** (statusChanged) — با نمایش وضعیت قبلی و جدید
- **ثبت نگهداری پیشگیرانه/PM** (pmCompleted) — با تاریخ انجام
- **ثبت درخواست کار مرتبط** (workOrderRaised)
- **بسته‌شدن درخواست کار مرتبط** (workOrderClosed)

هر رویداد شامل **نام انجام‌دهنده (actor)**، **زمان دقیق** و توضیح فارسی است. رویدادهای درخواست‌های کار، اولویت و نوع کار را هم به‌صورت برچسب نشان می‌دهند و دکمه‌ی «مشاهده درخواست کار» دارند.

## چرا به این شکل ساخته شد؟ (تصمیم معماری)
دامنه‌ی دستگاه فقط «وضعیت فعلی» و «آخرین PM» را نگه می‌داشت و رویدادها فقط dispatch می‌شدند و **ذخیره نمی‌شدند**؛ بنابراین تاریخچه‌ی تغییرات و PMهای گذشته قابل بازیابی نبود. برای یک تایم‌لاین واقعاً «کامل»، دقیقاً با الگوی `WorkOrderHistory` (فاز ۲۲) یک جدول append-only به نام `DeviceHistory` ساخته شد و همه‌ی UseCaseهای دستگاه در هر عملیات یک ردیف تاریخچه می‌نویسند. سپس تایم‌لاین، تاریخچه‌ی دستگاه را با رویدادهای درخواست‌های کار همان دستگاه ادغام و بر اساس زمان مرتب می‌کند.

## تغییرات بک‌اند (Django · DDD)
- **دامنه:** `domain/entities/deviceHistory.py` (`DeviceHistoryEntry` + کدهای اکشن ثابت).
- **زیرساخت:** `infrastructure/models.py` → مدل `DeviceHistoryModel` (جدول `DeviceHistory`) + migration `0004_devicehistorymodel`.
- **مخزن:** `infrastructure/repositories/deviceHistoryRepositoryImpl.py` + Protocol `DeviceHistoryRepository`.
- **سرویس:** `application/services/deviceHistory.py` (`recordDeviceHistory` — تک‌نقطه‌ی نوشتن تاریخچه، actor از context).
- **UseCaseها:** `application/useCases/deviceUseCases.py` — Register/Update/ChangeStatus/RecordPm حالا تاریخچه می‌نویسند؛ `GetDeviceTimelineUseCase` تاریخچه‌ی دستگاه + WOها را ادغام می‌کند.
- **DTO/Query:** `DeviceTimelineDto`/`DeviceTimelineItemDto` و `GetDeviceTimelineQuery`.
- **API:** `GET /api/v1/maintenance/devices/{id}/timeline` (دسترسی `maintenance.device.view`).
- **Container:** ثبت `deviceHistoryRepository` و `getDeviceTimelineUseCase`.

## تغییرات فرانت (React · TS · فارسی/RTL)
- `src/pages/DeviceTimelinePage.tsx` — صفحه‌ی تایم‌لاین با کارت مشخصات دستگاه + خط زمانی.
- مسیر `/app/maintenance/devices/:deviceId/timeline` در `AppRouter`.
- دکمه‌ی «تاریخچه» روی هر ردیف دستگاه در صفحه‌ی دستگاه‌ها (با دسترسی `maintenance.device.view`).
- سرویس: متد `getDeviceTimeline` + تایپ‌ها + endpoint در `endpoints.ts`.
- i18n فارسی کامل (`cmms.timeline.*`) و CSS تایم‌لاین در `globals.css`.

## تست‌ها (همه سبز)
- **بک‌اند:** `tests/integration/testPhase24DeviceTimeline.py` — ۸ تست (احراز هویت، ثبت شدن رویدادها، from/to وضعیت، رویدادهای WO، مرتب‌سازی، جداسازی بین دستگاه‌ها، ۴۰۴).
- **کل سوئیت بک‌اند:** `python manage.py test --settings=config.settings.testing` → **۲۳۳۳ تست OK** (بدون regression).
- **فرانت:** `npm run typecheck` سبز · `npm run test` ۱۵ تست سبز · `npm run build` موفق.
- **Smoke زنده:** ثبت دستگاه → تغییر وضعیت → PM → درخواست کار → تایم‌لاین درست بازگشت (۴ رویداد، مرتب، با actor).

## نحوه‌ی اجرا روی ویندوز (PowerShell)
```powershell
# بک‌اند
cd C:\Users\Mitra\Desktop\Tekarai\backend
python manage.py migrate                 # migration جدید 0004_devicehistorymodel اعمال می‌شود
python manage.py runserver 0.0.0.0:8000

# فرانت (پنجره‌ی دیگر)
cd C:\Users\Mitra\Desktop\Tekarai\frontend-web
npm install
npm run dev
```
سپس در مرورگر: صفحه‌ی **دستگاه‌ها** → روی هر دستگاه دکمه‌ی **«تاریخچه»** → صفحه‌ی تایم‌لاین.

> نکته: چون رویدادها از این پس ذخیره می‌شوند، تایم‌لاینِ دستگاه‌هایی که **بعد از** این به‌روزرسانی ثبت/ویرایش می‌شوند کامل است؛ برای دستگاه‌های قدیمی، درخواست‌های کارِ موجود همچنان روی تایم‌لاین نمایش داده می‌شوند.
