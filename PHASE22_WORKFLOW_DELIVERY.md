# فاز ۲۲ — گردش کار نگهداری (Workflow)

این فاز پنج قابلیت گردش کار را روی سیستم CMMS اضافه می‌کند؛ کاملاً هم‌راستا با
معماری DDD موجود، رابط فارسی، و با پوشش تست در هر لایه.

## ۵ قابلیت تحویل‌شده

1. **تاریخچه و تایم‌لاین درخواست کار** — هر رویداد گردش کار (ثبت، ارجاع، سپردن،
   تغییر وضعیت، ارسال برای تأیید، تأیید، رد) در جدول `WorkOrderHistory` ثبت و در
   پنل جزئیات درخواست کار به‌صورت تایم‌لاین فارسی نمایش داده می‌شود.
2. **مرحله‌ی تأیید مدیر** — تکنسین کار را «برای تأیید» ارسال می‌کند
   (`inProgress → pendingApproval`)؛ تکمیل یا بازگشت فقط از مسیر
   endpointهای `approve`/`reject` که دسترسی `maintenance.workorder.approve`
   را الزام می‌کنند، امکان‌پذیر است.
3. **SLA و نشان تأخیر** — مهلت بر اساس اولویت از زمان ثبت محاسبه می‌شود
   (بحرانی ۴، بالا ۲۴، عادی ۷۲، پایین ۱۶۸ ساعت). فیلدهای `slaDueAt`/`overdue`
   در DTO و نشان «تأخیر» در UI.
4. **تخصیص خودکار** — دکمه‌ی «تخصیص خودکار» (یا `{auto:true}` در endpoint
   تخصیص) کار را به کم‌کارترین تکنسین می‌سپارد.
5. **اعلان‌ها** — رویدادهای دامنه از طریق dispatcher مشترک به موتور اعلان‌های
   موجود (`apps/notifications`) می‌رسند و بر اساس نقش به تکنسین/مدیر تحویل
   می‌شوند. افزودن یک اعلان جدید = یک ردیف پیکربندی در
   `eventConsumer.NOTIFICATION_EVENT_ROUTES` (بدون تغییر موتور).

## ماشین وضعیت نهایی درخواست کار

```
submitted → routed → assigned → inProgress → (onHold | pendingApproval | cancelled)
onHold → (inProgress | cancelled)
pendingApproval → cancelled            (از endpoint عمومی status)
pendingApproval → completed            (فقط از endpoint approve)
pendingApproval → inProgress           (فقط از endpoint reject)
```

## Endpointهای جدید بک‌اند

| متد | مسیر | دسترسی |
|-----|------|--------|
| POST | `/api/v1/maintenance/work-orders/{id}/approve` | `maintenance.workorder.approve` |
| POST | `/api/v1/maintenance/work-orders/{id}/reject`  | `maintenance.workorder.approve` |
| GET  | `/api/v1/maintenance/work-orders/{id}/history` | `maintenance.workorder.view` |
| POST | `/api/v1/maintenance/work-orders/{id}/assign` با `{auto:true}` | `maintenance.workorder.assign` |

## نگاشت رویداد → اعلان (بر اساس نقش)

| رویداد دامنه | گیرنده (نقش) | نوع اعلان |
|--------------|---------------|-----------|
| `workOrderAssigned` | maintenanceTechnician | `maintenance.workOrderAssigned` |
| `workOrderSubmittedForApproval` | maintenanceManager | `maintenance.workOrderSubmittedForApproval` |
| `workOrderApproved` | maintenanceTechnician | `maintenance.workOrderApproved` |
| `workOrderRejected` | maintenanceTechnician | `maintenance.workOrderRejected` |

> نکته: payload درخواست کار فقط نام نمایشی تکنسین را دارد (نه شناسه‌ی کاربر)،
> بنابراین گیرندگان بر اساس **نقش** هدف‌گذاری می‌شوند.

## تست‌ها

- **بک‌اند:** کل سوئیت **۲۳۱۷ تست OK**.
  - `testPhase21MaintenanceApi.py` — کلاس `WorkOrderWorkflowTests` (تأیید/رد،
    SLA/overdue، تخصیص خودکار، تایم‌لاین) و به‌روزرسانی lifecycle.
  - `testPhase22WorkflowNotifications.py` — ۵ تست end-to-end یکپارچگی
    گردش‌کار→اعلان (assign/submit-for-approval/approve/reject + عدم دریافت
    اشتباه توسط مدیر).
- **فرانت‌اند:** `npm run typecheck` سبز، `npm run test` (۱۵ تست) سبز،
  `npm run build` موفق.

## اجرای محلی (ویندوز / PowerShell)

```powershell
cd C:\Users\Mitra\Desktop\Tekarai
powershell.exe -ExecutionPolicy Bypass -File .\run_dev.ps1 -UseSqlite
```

سپس آدرس چاپ‌شده‌ی فرانت‌اند (مثلاً http://localhost:5173) را در مرورگر باز کنید.
