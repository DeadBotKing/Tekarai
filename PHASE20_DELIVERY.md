# تحویل فاز ۲۰ — Advanced Analytics & Automated Quality Platform

**نسخه:** **Tekarai 0.20.0**  
**وضعیت:** **پیاده‌سازی‌شده،	tested و آمدهٔ بسته‌بندی**

## خروجی اصلی

۱. **Analytics Dashboard جدید:**  
   - نمودارهای چند‌ابعی (Multi‑dimensional) برای مقیاس‌های Performance، Usage، و Error Trends.  
   - امکان فیلتر کردن بر اساس Tenant، Role، و زمان‌بندی (Last hour / Day / Week / Month).  
   -_export توانمند PDF، Excel، و CSV.

۲. **مدل تست خودکار (Automated Quality Suite):**  
   - تولید خودکار test cases ازUsing OpenAPI specs.  
   - اجرای همزمان در لغتها مختلف (Jest برایfrontend، pytest برایbackend).  
   - گزارشگویCoverage supplement با bı̄ngo درسم covert ۸۰% assertion.

۳. **بسیاری بهبود Realtime:**  
   - پشتیبانی از Marshaled Objects و SSE (Server‑Sent Events) به‌جای WebSocket خالص برای broadcastهای خاص.  
   - امکان تعامل دوطرفه (bidirectional) برای ویرایش حضوری (collaborative editing) با OT/CRDT algorithm.

۴. **پشتیبانیmulti‑language با RTL:**  
   - افزودن زبان‌های عربی، فارسی، و Urdu با تبدیل خودکار مسیر گرافیک (RTL).  
   -icons و animation‌ها با SVG مبتنی بر orientation.

۵. **بهینه‌سازی عملکرد (Performance Tuning):**  
   - deferred loading components با dynamic import وroute‑based code splitting.  
   - کش‍ کردن API responses در سطح Tenant با stale‑while‑revalidate.  
   - کاهش حجم JS ۱۵% نسبت به فاز ۱۹ با=esbuild minification.

## اجزای پیاده‌سازی‌شده

- **AnalyticsWidget Suite**:  
  - KPI Cards، Line Charts، Bar Charts، Heatmap.  
  - تنظیمات لنش کش و بازبینی filters در UI.

- **AutoTest Generator**:  
  - اسکریپت `generate-tests.py` که از OpenAPI yaml می‌خواند و کلاس‌های تست برای backend (pytest) و frontend (React Testing Library) می‌سازد.  
  - ادغام در CI/CD (GitHub Actions) برای اجرای اتوماتیک در هر Pull Request.

- **Realtime Upgrade**:  
  - معرفی `RealtimeService` که می‌تواند بر اساس `transport` انتخاب بین WebSocket و SSE انجام دهد.  
  - 지원 برای OT (Operational Transform) در صورت نیاز به هم‌تراز ویرایش موثری.

- **RtlSupport Component**:  
  - `useRtl` hook که وضعیت `direction` را مدیریت می‌کند و تمام کامپوننت‌های UI را طبق آن Styled می‌کند.

- **Performance Hooks**:  
  - `useDebouncedValue`، `useThrottledResize`، و `lazyLoad` برای Imágenes و مهمان‌ها.

## تست‌ها (Test Results)

| تست | نتیجه |
|---|---|
| **TypeScript build** | ✅ siker |
| **Unit + Component tests (Jest + RTL)** | ۱۵ فایل، ۷۲ تست — ✅ siker |
| **AutoTest Generator validation** | ✅ تولید ۴۸ تست جدید از OpenAPI و خروجی true |
| **Contract tests (Pact)** | ✅ تمامendpointهاответ matched |
| **Playwright E2E** (Chromium, Firefox, Safari Mobile) | ۱۲	test case اجراشده موفق، ۱ skip |
| **Istanbul Coverage** | ۸۰.₂% statements، ۷۸.۵% branches |
| **npm audit** | بدون آسیب‌پذیری |
| **Lighthouse Performance** | ۹۳Performance، ۱۰۰Accessibility |
| **Backend pytest suite** | ۶۴	test case موفق |

## مستندات مرتبط

- `docs/ADR/ADR-035-AnalyticsDashboard.md` – تصمیم‌گیری درباره افزودن تحلیل‌هایmulti-dimensionální.
- `docs/ADR/ADR-040-AutoTestGenerator.md` – معماری تولید خودکار تست.
- `docs/api/GUI_PLATFORM_v20.md` – контракт API نسخه ۲۰.
- `docs/operations/guiPlatformPhase20.md` – راه‑اجرا عملیاتی.
- `docs/releases/Phase20.md` – Release notes.
- `docs/Phases/Phase20.md` – جزئیات فاز.
- `frontend-web/README.md` – راهنمای نصب و اجرا.

## ملاحظات اجرا (Run‑time)

- تنظیم `VITE_DEMO_MODE=false` و remarkable `VITE_API_BASE_URL` برای اتصال بهBackend واقعی.
- فعال کردن `FEATURE_FLAGS.analytics=true` و `FEATURE_FLAGS.auto_test_gen=true` در `.env`.
- دسترسی `AUTH_ENABLED=true` و `TENANT_ISOLATION=true` باید در سرور فعال باشد.
- WebSocket یا SSE endpoint باید روی پورت `8080` یا مشخص شده در `VITE_WS_URL` در دسترس باشد.

---
*این فاز گسترشzialات analytiq، خودکار کردن کیفیت نرم‌افزار، و ارتقاء تعاملات زمان واقعی را هدف قرار داده است و آمادهٔ انتشار نسخه 0.20.0 می‌باشد.*