# تحویل فاز ۱۸ — GUI Architecture & Application Interface Platform

نسخه: **Tekarai 0.18.0**  
وضعیت: **پیاده‌سازی‌شده، تست‌شده و آمادهٔ بسته‌بندی**

## خروجی اصلی

پوشهٔ `frontend-web/` که در فازهای قبلی Placeholder بود، اکنون به یک SPA
عمومی و قابل توسعه با React 19، TypeScript و Vite تبدیل شده است. این UI برای
صنعت خاص Hardcode نشده و از طریق Configuration، Permission، Tenant و Feature
Flag برای Domainهای مختلف قابل توسعه است.

## اجزای پیاده‌سازی‌شده

- Application Shell با Authentication، Tenant Context، Permission Context،
  Navigation، Global Search، Notification Center، Theme، Localization و
  Application Settings.
- Routing محافظت‌شده و Permission-aware با مسیرهای Dashboard، Projects، Tasks،
  Documents، Reports، Project Intelligence، Administration، Audit، Settings و
  resourceهای Organization/Devices.
- Design System مستقل با Design Tokenهای متمرکز، Light/Dark، RTL/LTR،
  Responsive layout، Focus state، Reduced motion و Inline SVG Icons.
- Componentهای Primitive/Composite/Feature: Button، Input، Select، TextArea،
  Badge، Progress، Card، Modal، Drawer، DataTable، Chart، Timeline، Activity
  Feed، File Upload، Document Viewer، Permission Guard و Error Boundary.
- DataTable Generic با Sort، Filter/Search، Pagination، Column Visibility،
  Selection، Bulk-action slot، Export، Loading، Empty و Error state.
- فرم Schema-driven با validation سطح Field، Error، Submit/Loading و
  Accessibility.
- API Client مرکزی با API Version، Standard Envelope، Stable Errors، Bearer
  Token، Tenant Header، Timeout، Retry محدود، Refresh همزمان‌سازی‌شده،
  GET de-duplication، Cancellation، Upload Progress و Tenant-aware Cache.
- سرویس‌های Feature برای Project، Task، Document، Report، Notification و
  Project Intelligence؛ هیچ Componentی مستقیماً به ORM/Database متصل نیست.
- Dashboard Widget-based، پروژه‌ها، وظایف List/Board/Timeline/Calendar، اسناد
  و Upload/Viewer، Reports، Administration، Audit و Settings.
- Project Intelligence UI شامل Health Breakdown، Architecture، Dependency،
  Change، Insight، Recommendation و Agent Context.
- Localization زبان‌های English، فارسی و Deutsch و تغییر جهت خودکار سند.
- Feature Flag و Permission-based Rendering؛ Backend همچنان Source of Truth
  امنیت است.
- Optional Realtime transport برای WebSocket با reconnect backoff؛ بدون
  Business Logic در transport.
- Observability با redaction کلیدهای حساس و Error/Network handling استاندارد.

## مستندات

- ADR انتخاب فناوری: `docs/adr/ADR-025-FrontendTechnology.md`
- قرارداد Frontend/Backend: `docs/api/GUI_PLATFORM.md`
- Runbook عملیاتی: `docs/operations/guiPlatform.md`
- Release notes: `docs/releases/Phase18.md`
- مشخصات مرجع: `docs/Phases/Phase18.md`
- راهنمای Frontend: `frontend-web/README.md`

## نتایج تست

- TypeScript project build: **موفق**
- Unit/Component/Contract tests: **موفق — ۷ فایل، ۱۵ تست**
- Coverage run: **موفق — 54.03% statements، 54.61% branches**
- Vite production build: **موفق**
- Playwright E2E روی Chromium Desktop و Mobile: **۶ تست اجراشده موفق، ۲ مورد تکراری skip**
- npm audit: **بدون آسیب‌پذیری**

حالت Demo فقط برای بازبینی مستقل UI است. در Production باید
`VITE_DEMO_MODE=false` تنظیم شود و Backend واقعی با Authentication،
Authorization و Tenant Isolation فعال ارائه شود.
