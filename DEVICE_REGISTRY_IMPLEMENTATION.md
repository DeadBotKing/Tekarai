# رجیستری ماشین‌آلات و تجهیزات (فاز ۲۶)

این سند دقیقاً آنچه را که کد شده و تست شده توضیح می‌دهد — نه بیشتر.

## ۱) خلاصه

بخش «ماشین یا دستگاه» به‌صورت یک **دیتابیس واقعی تجهیزات** پیاده شد: مدل دیتابیسی + API +
رابط کاربری فارسی/راست‌به‌چپ. هر دستگاه یک «پرونده» دارد که مشخصات فنی، برنامه‌های PM در هفت
دیسیپلین، لیست قطعات (BOM)، محل استقرار (سایت/ساختمان/محوطه/اتاق)، بهره‌بردار و مسئول دستگاه،
پرسنل نت و شاخص‌های تحلیلی را نگه می‌دارد.

## ۲) بک‌اند (Django)

- **۷ مدل جدید** در `apps/maintenance/infrastructure/models.py` + مهاجرت
  `infrastructure/migrations/0007_assetRegistry.py`:
  محل استقرار، پرسنل نت، مشخصات فنی، برنامه PM، اجرای PM، اقلام BOM، انتساب افراد به دستگاه.
- **دامنه**: `domain/entities/assetRegistry.py`، `domain/entities/device.py` (فیلدهای شناسنامه)،
  `domain/valueObjects/maintenanceState.py` (هفت دیسیپلین، سطح بحرانیت، واحد تناوب)،
  `domain/services/maintenanceAnalytics.py` (MTBF، MTTR، دسترس‌پذیری، انطباق PM، هزینه).
- **کاربرد‌ها**: `application/useCases/registryUseCases.py` (۱۰۸۴ خط) و
  `application/dto/registryDtos.py`.
- **API**: `presentation/api/views/registryViews.py` (۱۶ ویو) و ۱۸ مسیر در
  `urls/maintenanceRoutes.py` با پیشوند `/api/v1/maintenance`:

  | متد | مسیر |
  | --- | --- |
  | GET/POST | `/locations` |
  | PATCH/DELETE | `/locations/<uuid>` |
  | GET/POST | `/personnel` |
  | PATCH/DELETE | `/personnel/<uuid>` |
  | GET | `/devices/<uuid>/profile` |
  | PATCH | `/devices/<uuid>/nameplate` |
  | PUT | `/devices/<uuid>/specifications` |
  | GET/POST | `/devices/<uuid>/pm-plans` |
  | PATCH/DELETE | `/pm-plans/<uuid>` |
  | POST | `/pm-plans/<uuid>/executions` |
  | POST | `/devices/<uuid>/bom` |
  | DELETE | `/devices/<uuid>/bom/<partId>` |
  | PUT | `/devices/<uuid>/assignments` |
  | GET | `/devices/<uuid>/analytics` |
  | GET | `/analytics/fleet` |
  | GET | `/analytics/parts/<partId>` |
  | PATCH | `/work-orders/<uuid>/closure` |

- **مجوزها**: `maintenance.device.view | list | manage`.

## ۳) فرانت‌اند (React + TypeScript)

| فایل | خط | نقش |
| --- | --- | --- |
| `src/pages/EquipmentRegistryPage.tsx` | ۶۰۶ | فهرست همه ماشین‌آلات + افزودن دستگاه جدید |
| `src/pages/DeviceProfilePage.tsx` | ۱۴۵۸ | پرونده دستگاه با ۷ تب و مودال‌های CRUD |
| `src/pages/MaintenanceLocationsPage.tsx` | ۳۰۷ | درخت سایت/ساختمان/محوطه/اتاق با CRUD |
| `src/pages/MaintenancePersonnelPage.tsx` | ۳۸۸ | دایرکتوری پرسنل نت با CRUD |
| `src/pages/FleetAnalyticsPage.tsx` | ۲۸۹ | مقایسه شاخص‌های کل ناوگان |
| `src/features/maintenance/registryService.ts` | ۱۰۲۱ | کلاینت API + نگاشت DTOها |
| `src/features/maintenance/registryDemoData.ts` | ۱۰۹۹ | فروشگاه داده آفلاین (حالت demo) |
| `src/tests/equipmentRegistry.test.tsx` | ۲۶۵ | ۸ تست vitest |
| `src/shared/components/CreatableSelect.tsx` | ۲۱۶ | منوی کشویی با افزودن مورد جدید |
| `src/features/maintenance/optionCatalog.ts` | ۱۳۸ | کاتالوگ مقادیر دلخواه + ادغام فهرست |
| `src/tests/creatableOptions.test.tsx` | ۱۶۵ | ۸ تست vitest برای منوهای باز |

هفت تب پرونده دستگاه: شناسنامه، مشخصات فنی، برنامه‌های PM، قطعات، محل استقرار و بهره‌بردار،
پرسنل نت، شاخص‌ها و تحلیل.

مسیرها: `/app/maintenance/registry`، `/app/maintenance/devices/:deviceId/profile`،
`/app/maintenance/locations`، `/app/maintenance/personnel`، `/app/maintenance/fleet`.
هر پنج مسیر در `app/router/AppRouter.tsx` و منوی کناری (`app/configuration/navigation.ts`) ثبت شده‌اند.

۲۴۷+ کلید فارسی در `core/localization/i18n.ts` اضافه شد؛ کلاس‌های CSS رجیستری در
`src/styles/globals.css`.

## ۳.۵) منوهای کشویی باز — افزودن مورد جدید در زمان اجرا (فاز ۲۶.۱)

هر منوی کشویی تاکسونومی یک گزینهٔ «＋ افزودن مورد جدید…» در انتها دارد. با انتخاب آن،
همان‌جا یک کادر متنی باز می‌شود، مقدار دلخواه (مثلاً «سوله» یا «جوشکاری») نوشته و با ✓ ثبت
می‌شود؛ بلافاصله انتخاب می‌شود و به API می‌رود.

مقدار جدید از سه مسیر در فهرست باقی می‌ماند:

| مسیر | توضیح |
| --- | --- |
| رکورد ذخیره‌شده | API مقدار را عیناً ذخیره می‌کند |
| کاربران دیگر | `mergeOptions` مقادیر موجود در ردیف‌های بارگذاری‌شده را به فهرست برمی‌گرداند |
| همین مرورگر | کاتالوگ محلی (`localStorage`) پیش از اولین ذخیره |

**منوهایی که باز شدند:** نوع مکان، تخصص پرسنل، دیسیپلین PM، دپارتمان دستگاه (و ارجاع
دستور کار)، نقش انتساب فرد، سطح بحرانیت.

**منوهایی که عمداً بسته ماندند:** واحد تناوب PM (محاسبهٔ تاریخ سررسید به آن وابسته است)،
وضعیت دستگاه و وضعیت دستور کار (ماشین حالت و قوانین گذار).

**اعتبارسنجی (هم در UI و هم در API):** خالی نباشد، حداکثر ۲۴ نویسه، بدون نویسهٔ کنترلی،
فاصله‌های داخلی یکسان‌سازی می‌شود، و مقدار هم‌ارزِ یک کد استاندارد (مثلاً `Site`) به همان کد
استاندارد (`site`) نگاشت می‌شود تا فهرست دوتایی نشود.

**تغییرات بک‌اند:** `OpenVocabularyField` در
`presentation/api/serializers/taxonomyFields.py`، بازکردن شش `ChoiceField`، آزادسازی دو
value object (`MaintenanceDepartment`, `EquipmentCriticality`) به اعتبارسنجی شکلی، و مهاجرت
`0008_openTaxonomies.py` که ستون‌ها را به ۲۴ نویسه می‌رساند و دو CHECK constraint بستهٔ
دیتابیس را به «خالی نباشد» تبدیل می‌کند.

**اصلاح یک ناهماهنگی واقعی:** فرانت‌اند برای بالاترین سطح بحرانیت `critical` می‌فرستاد در حالی
که بک‌اند `vital` را می‌پذیرد؛ در حالت متصل به API این درخواست ۴۰۰ می‌گرفت. واژگان فرانت‌اند
با بک‌اند هم‌تراز شد (`vital | high | medium | low`) و فهرست انواع مکان از ۴ به ۷ مورد
استاندارد بک‌اند رسید.

## ۴) هفت دیسیپلین PM

مکانیک، برق، ابزار دقیق، عمومی، هیدرولیک، پنوماتیک، تأسیسات — هم در `MaintenanceDepartment`
بک‌اند و هم در `MAINTENANCE_DEPARTMENTS` فرانت‌اند، با برچسب فارسی.

## ۵) نتیجه تست‌ها (اجرا شده روی همین بستهٔ ZIP پس از استخراج)

```
backend : pip install -r backend/requirements/testing.txt
          python3 manage.py test --settings=config.settings.testing
          Ran 2393 tests in 71.428s → OK

frontend: npm ci --ignore-scripts
          npx tsc -b --force  → بدون خطا
          npm run test        → 10 files / 37 tests passed
          npm run build       → ✓ built in 3.13s
```

تست‌های فاز ۲۶ به‌تنهایی: `tests.unit.testPhase26Analytics` + `tests.integration.testPhase26AssetRegistry`
→ `Ran 38 tests → OK`؛ واژگان باز: `tests.integration.testPhase26OpenTaxonomies` → `Ran 12 tests → OK`.

### دو نکتهٔ مهم برای اجرای محلی

۱. **حتماً نسخه‌های پین‌شده را نصب کنید**: `pip install -r backend/requirements/testing.txt`
   (Django 6.1، channels 4.3.2). با نصب بدون پین (مثلاً Django 6.1.1) تست قدیمی
   `tests.integration.testPhase8WebsocketGateway.testSubscribeTypingReadAndSend` خطای
   `asyncio.CancelledError` می‌دهد؛ این تست به فاز ۲۶ ربطی ندارد و روی کد اصلی (بدون تغییرات این فاز)
   هم با نسخهٔ بدون پین خطا می‌دهد.

۲. **پوشهٔ `.git` در این ZIP نیست** (برای کاهش حجم). چهار تست
   `tests.architecture.testRepositoryHygiene.GitIgnorePolicyTests` دستور `git check-ignore` را صدا می‌زنند
   و بدون مخزن گیت شکست می‌خورند. کافی است یک‌بار در ریشهٔ پروژه `git init` بزنید
   (یا فایل‌ها را داخل کلون موجود باز کنید) تا هر ۴ تست سبز شوند.

## ۶) نکته‌ها و محدودیت‌ها

- در حالت `VITE_DEMO_MODE=true` (پیش‌فرض dev) داده‌ها در حافظه مرورگر نگه‌داری می‌شوند؛
  در حالت متصل، همان صفحات روی API واقعی بالا کار می‌کنند.
- با باز شدن واژگان، تست قدیمی `testInvalidDepartmentIsRejected` (فاز ۲۱) دیگر معتبر نبود و با
  تستی جایگزین شد که قرارداد جدید را می‌سنجد: برچسب دلخواه پذیرفته می‌شود، ورودی بی‌شکل رد می‌شود.
- مودال «مشخصات کامل» قدیمی در صفحه دستگاه‌ها که فقط سمت‌کلاینت بود حذف شد و جای آن دکمه
  «پرونده دستگاه» به صفحه واقعی رجیستری می‌رود.
- تست‌های e2e پلی‌رایت اجرا نشده‌اند (نیاز به مرورگر) و `ruff` در این محیط نصب نیست.
