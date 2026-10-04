"""seedDemo — populate the platform tenant with believable Persian demo data.

First-run experience matters: an empty CMMS tells the operator nothing.
This command seeds locations, personnel, spare parts, devices, PM plans,
executions and work orders (with labour + part consumption) so every page —
dashboard, registry, calendar, cost report — has real content on day one.

Idempotent by business codes: re-running updates nothing and reports what
already exists. Only touches the ``platform`` tenant (§75: no real secrets,
no cross-tenant writes).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.maintenance.domain.services.iranHolidays import IRAN_OFFICIAL_SOLAR_HOLIDAYS
from apps.maintenance.domain.services.jalaliCalendar import jalaliMonthLength, jalaliToDate
from apps.maintenance.infrastructure.models import (
    CalendarHolidayModel,
    DeviceModel,
    MaintenanceLocationModel,
    MaintenancePersonnelModel,
    PmExecutionModel,
    PmPlanModel,
    SparePartModel,
    WorkOrderLabourEntryModel,
    WorkOrderModel,
    WorkOrderPartUsageModel,
    WorkCalendarModel,
    WorkShiftModel,
)
from apps.tenancy.infrastructure.models import TenantModel

TENANT_CODE = "platform"

LOCATIONS = [
    {"code": "SITE-01", "name": "سایت اصلی تولید", "kind": "site", "parent": None},
    {"code": "BLD-A", "name": "ساختمان A — تولید", "kind": "building", "parent": "SITE-01"},
    {"code": "HALL-1", "name": "سالن تولید شماره ۱", "kind": "hall", "parent": "BLD-A"},
    {"code": "LINE-1", "name": "خط تولید ۱", "kind": "line", "parent": "HALL-1"},
    {"code": "LINE-2", "name": "خط تولید ۲", "kind": "line", "parent": "HALL-1"},
    {"code": "SYS-HYD1", "name": "سیستم هیدرولیک خط ۱", "kind": "system", "parent": "LINE-1"},
    {"code": "SYS-COOL1", "name": "سیستم خنک‌کاری خط ۱", "kind": "system", "parent": "LINE-1"},
    {"code": "BLD-B", "name": "ساختمان B — ابنیه‌فنی", "kind": "building", "parent": "SITE-01"},
    {"code": "BOILER", "name": "موتورخانه مرکزی", "kind": "room", "parent": "BLD-B"},
]

PERSONNEL = [
    {"code": "TEC-001", "fullName": "مهندس رضا کریمی", "specialty": "mechanical", "unit": "نگهداری مکانیک"},
    {"code": "TEC-002", "fullName": "مهندس نگار احمدی", "specialty": "electrical", "unit": "برق و ابزاردقیق"},
    {"code": "TEC-003", "fullName": "استاد حسین مرادی", "specialty": "mechanical", "unit": "نگهداری مکانیک"},
    {"code": "TEC-004", "fullName": "مهندس سارا موسوی", "specialty": "instrument", "unit": "ابزاردقیق"},
    {"code": "TEC-005", "fullName": "استاد محمد جعفری", "specialty": "general", "unit": "خدمات عمومی"},
    {"code": "SUP-001", "fullName": "مهندس امیر نیک‌فر", "specialty": "mechanical", "unit": "سرپرست نگهداری"},
]

SPARE_PARTS = [
    {"code": "BRG-6205", "name": "بلبرینگ ۶۲۰۵ روانکار", "unit": "عدد", "onHand": "24", "minimum": "8", "cost": "185000"},
    {"code": "BLT-A52", "name": "تسمه A52", "unit": "عدد", "onHand": "12", "minimum": "6", "cost": "240000"},
    {"code": "FLTR-20", "name": "فیلتر روغن ۲۰ میکرون", "unit": "عدد", "onHand": "30", "minimum": "10", "cost": "95000"},
    {"code": "SIL-15H", "name": "سیل هیدرولیک ۱۵", "unit": "عدد", "onHand": "6", "minimum": "4", "cost": "620000"},
    {"code": "CPL-J40", "name": "کوپلینگ انعطاف‌پذیر J40", "unit": "عدد", "onHand": "4", "minimum": "2", "cost": "1450000"},
    {"code": "GSK-P8", "name": "واشر درپوش پمپ", "unit": "عدد", "onHand": "5", "minimum": "12", "cost": "45000"},
]

DEVICES = [
    {"code": "PRS-101", "name": "پرس هیدرولیک خط ۱", "department": "production", "status": "operational", "location": "LINE-1", "criticality": "high", "interval": 30, "manufacturer": "ماشین‌سازی تبریز", "model": "HP-320", "cost": "2500000000", "hours": "14200", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "PRS-102", "name": "پرس هیدرولیک خط ۲", "department": "production", "status": "operational", "location": "LINE-2", "criticality": "high", "interval": 30, "manufacturer": "ماشین‌سازی تبریز", "model": "HP-320", "cost": "2500000000", "hours": "12850", "costCenter": "CC-1200", "costCenterName": "تولید — خط ۲"},
    {"code": "CNC-201", "name": "تراش CNC شماره ۱", "department": "production", "status": "underMaintenance", "location": "LINE-1", "criticality": "critical", "interval": 21, "manufacturer": "هیدن‌هاین", "model": "C640", "cost": "7400000000", "hours": "22100", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "MLD-205", "name": "دستگاه تزریق پلاستیک", "department": "production", "status": "operational", "location": "LINE-2", "criticality": "high", "interval": 45, "manufacturer": "کروس‌مافو", "model": "GX-900", "cost": "5100000000", "hours": "18900", "costCenter": "CC-1200", "costCenterName": "تولید — خط ۲"},
    {"code": "CON-310", "name": "نوارنقاله انتقال مواد", "department": "production", "status": "operational", "location": "LINE-1", "criticality": "medium", "interval": 60, "manufacturer": "سنگین‌فلز", "model": "CV-1200", "cost": "860000000", "hours": "26000", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "PMP-410", "name": "پمپ آب خنک‌کاری موتورخانه", "department": "utilities", "status": "operational", "location": "BOILER", "criticality": "high", "interval": 30, "manufacturer": "پمپ‌راد", "model": "CR-90", "cost": "1180000000", "hours": "31000", "costCenter": "CC-2100", "costCenterName": "تأسیسات"},
    {"code": "BLR-420", "name": "بویلر بخار ۳ تن", "department": "utilities", "status": "operational", "location": "BOILER", "criticality": "critical", "interval": 14, "manufacturer": "ماشین‌سازی اراک", "model": "WS-3000", "cost": "9200000000", "hours": "28400", "costCenter": "CC-2100", "costCenterName": "تأسیسات"},
    {"code": "GEN-450", "name": "دیزل ژنراتور اضطراری", "department": "utilities", "status": "outOfService", "location": "BLD-B", "criticality": "high", "interval": 30, "manufacturer": "کامینز", "model": "S6.7-G7", "cost": "3400000000", "hours": "3100", "costCenter": "CC-2200", "costCenterName": "برق اضطراری"},
]

#: Sub-assemblies and components, filed under the machines they belong to.
#: These complete the equipment half of the chain — تجهیز اصلی ← زیرتجهیز ←
#: قطعه — which the location tree alone cannot express.
SUB_ASSETS = [
    {"code": "PRS-101-MTR", "name": "الکتروموتور پرس خط ۱", "department": "production", "status": "operational", "location": "SYS-HYD1", "criticality": "high", "interval": 90, "manufacturer": "موتوژن", "model": "3GB-132", "cost": "180000000", "hours": "14200", "level": "subEquipment", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "PRS-101-PMP", "name": "پمپ هیدرولیک پرس خط ۱", "department": "production", "status": "operational", "location": "SYS-HYD1", "criticality": "high", "interval": 60, "manufacturer": "بوش رکسروت", "model": "A10VSO", "cost": "320000000", "hours": "14200", "level": "subEquipment", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "PRS-101-BRG", "name": "یاتاقان محور اصلی پرس", "department": "production", "status": "operational", "location": "SYS-HYD1", "criticality": "medium", "interval": 180, "manufacturer": "SKF", "model": "6205-2RS", "cost": "1850000", "hours": "14200", "level": "component", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
    {"code": "CNC-201-SPN", "name": "اسپیندل تراش CNC", "department": "production", "status": "operational", "location": "LINE-1", "criticality": "critical", "interval": 120, "manufacturer": "هیدن‌هاین", "model": "SP-400", "cost": "940000000", "hours": "22100", "level": "subEquipment", "costCenter": "CC-1100", "costCenterName": "تولید — خط ۱"},
]

DEVICES = DEVICES + SUB_ASSETS

#: child code → parent code.
ASSET_PARENTS = {
    "PRS-101-MTR": "PRS-101",
    "PRS-101-PMP": "PRS-101",
    "PRS-101-BRG": "PRS-101-MTR",
    "CNC-201-SPN": "CNC-201",
}

PM_PLANS = [
    {"device": "PRS-101", "title": "تعویض روغن و سرویس هیدرولیک", "discipline": "mechanical", "every": 1, "unit": "month", "minutes": 180, "responsible": "مهندس رضا کریمی"},
    {"device": "PRS-102", "title": "تعویض روغن و سرویس هیدرولیک", "discipline": "mechanical", "every": 1, "unit": "month", "minutes": 180, "responsible": "مهندس رضا کریمی"},
    {"device": "CNC-201", "title": "کالیبراسیون محورها و سرویس ابزاردقیق", "discipline": "instrument", "every": 2, "unit": "week", "minutes": 240, "responsible": "مهندس سارا موسوی"},
    {"device": "MLD-205", "title": "سرویس گرم‌خانه و برق‌کنترل", "discipline": "electrical", "every": 2, "unit": "month", "minutes": 120, "responsible": "مهندس نگار احمدی"},
    {"device": "BLR-420", "title": "بازرسی ایمنی بویلر (قانونی)", "discipline": "general", "every": 2, "unit": "week", "minutes": 150, "responsible": "مهندس سارا موسوی"},
    {"device": "PMP-410", "title": "تست ارتعاش و محرک پمپ", "discipline": "mechanical", "every": 1, "unit": "month", "minutes": 90, "responsible": "استاد حسین مرادی"},
    {"device": "GEN-450", "title": "تست بار و سرویس موتور ژنراتور", "discipline": "general", "every": 1, "unit": "month", "minutes": 60, "responsible": "استاد محمد جعفری"},
]

WORK_ORDERS = [
    {"device": "CNC-201", "title": "لرزش غیرعادی اسپیندل در دور بالا", "type": "corrective", "priority": "high", "status": "inProgress", "tech": "مهندس سارا موسوی", "daysAgo": 1},
    {"device": "PMP-410", "title": "افت فشار لوله خروجی پمپ خنک‌کاری", "type": "corrective", "priority": "high", "status": "submitted", "tech": "مهندس رضا کریمی", "daysAgo": 0},
    {"device": "CON-310", "title": "توقف نوارنقاله — بررسی الکتروموتور", "type": "corrective", "priority": "normal", "status": "assigned", "tech": "استاد حسین مرادی", "daysAgo": 2},
    {"device": "BLR-420", "title": "بازرسی دوره‌ای شیراطمینان بویلر", "type": "preventive", "priority": "normal", "status": "scheduled", "tech": "مهندس سارا موسوی", "daysAgo": -3},
    {"device": "PRS-101", "title": "سرویس ماهانه‌ی هیدرولیک پرس ۱", "type": "preventive", "priority": "normal", "status": "completed", "tech": "مهندس رضا کریمی", "daysAgo": 6, "downtime": 120, "hours": "2.5", "labourRate": "350000", "parts": [("FLTR-20", "2"), ("GSK-P8", "1")], "finished": 6},
    {"device": "MLD-205", "title": "تعویض المنت‌های گرمایش سیلندر", "type": "corrective", "priority": "high", "status": "completed", "tech": "مهندس نگار احمدی", "daysAgo": 9, "downtime": 240, "hours": "4", "labourRate": "350000", "parts": [], "finished": 9},
    {"device": "GEN-450", "title": "تست عملیات دیزل ژنراتور ماه گذشته", "type": "preventive", "priority": "low", "status": "completed", "tech": "استاد محمد جعفری", "daysAgo": 15, "downtime": 60, "hours": "1.25", "labourRate": "300000", "parts": [("FLTR-20", "1")], "finished": 15},
    {"device": "PRS-102", "title": "صدای غیرعادی از پمپ اصلی هنگام بار", "type": "corrective", "priority": "normal", "status": "completed", "tech": "استاد حسین مرادی", "daysAgo": 20, "downtime": 300, "hours": "5.5", "labourRate": "320000", "parts": [("BRG-6205", "2"), ("SIL-15H", "1")], "finished": 20},
    {"device": "MLD-205", "title": "ریزش مواد از سیلندر تزریق", "type": "corrective", "priority": "normal", "status": "completed", "tech": "مهندس نگار احمدی", "daysAgo": 34, "downtime": 180, "hours": "3", "labourRate": "350000", "parts": [("GSK-P8", "2")], "finished": 34},
    {"device": "BLR-420", "title": "راه‌اندازی پس از توقف سالانه", "type": "coordinating", "priority": "high", "status": "completed", "tech": "مهندس امیر نیک‌فر", "daysAgo": 55, "downtime": 960, "hours": "12", "labourRate": "400000", "parts": [("SIL-15H", "1"), ("GSK-P8", "3")], "finished": 55},
]

WO_STATUS_DEPARTMENT = {"production": "production", "utilities": "utilities"}


class Command(BaseCommand):
    help = "Seed believable Persian demo data (devices, parts, PM, work orders) for the platform tenant."

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        tenant = TenantModel.objects.filter(code=TENANT_CODE, deletedAt__isnull=True).first()
        if tenant is None:
            self.stderr.write(f"Tenant «{TENANT_CODE}» not found — run bootstrapPlatform first.")
            return
        tenantId = tenant.id

        now = timezone.now()
        today = now.date()
        created: dict[str, int] = {"locations": 0, "personnel": 0, "spareParts": 0, "devices": 0, "pmPlans": 0, "workOrders": 0}

        # -- Locations (parent chain materialised for display) ------------------
        locationIds: dict[str, uuid.UUID] = {}
        locationPaths: dict[str, str] = {}
        for row in LOCATIONS:
            parentCode = row["parent"]
            parentId = locationIds.get(parentCode) if parentCode else None
            path = f"{locationPaths[parentCode]} / {row['name']}" if parentCode else row["name"]
            _, wasCreated = MaintenanceLocationModel.objects.get_or_create(
                tenantId=tenantId,
                code=row["code"],
                defaults={
                    "id": uuid.uuid4(),
                    "name": row["name"],
                    "kind": row["kind"],
                    "parentId": parentId,
                    "path": path,
                    "createdAt": now,
                },
            )
            record = MaintenanceLocationModel.objects.get(tenantId=tenantId, code=row["code"])
            locationIds[row["code"]] = record.id
            locationPaths[row["code"]] = record.path or path
            created["locations"] += int(wasCreated)

        # -- Personnel ------------------------------------------------------------
        for row in PERSONNEL:
            _, wasCreated = MaintenancePersonnelModel.objects.get_or_create(
                tenantId=tenantId,
                personnelCode=row["code"],
                defaults={
                    "id": uuid.uuid4(),
                    "fullName": row["fullName"],
                    "specialty": row["specialty"],
                    "unit": row["unit"],
                    "createdAt": now,
                },
            )
            created["personnel"] += int(wasCreated)

        # -- Spare parts -----------------------------------------------------------
        partIds: dict[str, uuid.UUID] = {}
        partCosts: dict[str, str] = {}
        for row in SPARE_PARTS:
            _, wasCreated = SparePartModel.objects.get_or_create(
                tenantId=tenantId,
                code=row["code"],
                defaults={
                    "id": uuid.uuid4(),
                    "name": row["name"],
                    "unit": row["unit"],
                    "quantityOnHand": row["onHand"],
                    "minimumStock": row["minimum"],
                    "unitCost": row["cost"],
                },
            )
            record = SparePartModel.objects.get(tenantId=tenantId, code=row["code"])
            partIds[row["code"]] = record.id
            partCosts[row["code"]] = str(record.unitCost)
            created["spareParts"] += int(wasCreated)

        # -- Devices ----------------------------------------------------------------
        deviceIds: dict[str, uuid.UUID] = {}
        deviceMeta: dict[str, dict[str, str]] = {}
        for row in DEVICES:
            lastPm = today - timedelta(days=row["interval"] - 3)  # due «soon»
            _, wasCreated = DeviceModel.objects.get_or_create(
                tenantId=tenantId,
                code=row["code"],
                defaults={
                    "id": uuid.uuid4(),
                    "name": row["name"],
                    "location": locationPaths.get(row["location"], ""),
                    "locationId": locationIds.get(row["location"]),
                    # The cached path must be seeded too: the transfer ledger
                    # copies it as the move's origin, so leaving it blank
                    # makes every first transfer look like it came from
                    # nowhere.
                    "locationPath": locationPaths.get(row["location"], ""),
                    "department": row["department"],
                    "status": row["status"],
                    "pmIntervalDays": row["interval"],
                    "lastPmDate": lastPm,
                    "criticality": row["criticality"],
                    "manufacturer": row["manufacturer"],
                    "modelNumber": row["model"],
                    "purchaseCost": row["cost"],
                    "runningHours": row["hours"],
                    "installedOn": date(2021, 3, 21),
                    "commissionedOn": date(2021, 4, 10),
                    "assetLevel": row.get("level", "mainEquipment"),
                    "costCenterCode": row.get("costCenter", ""),
                    "costCenterName": row.get("costCenterName", ""),
                },
            )
            record = DeviceModel.objects.get(tenantId=tenantId, code=row["code"])
            deviceIds[row["code"]] = record.id
            deviceMeta[row["code"]] = {"department": record.department, "name": record.name}
            created["devices"] += int(wasCreated)

        # Backfill the cached location path on rows seeded before it was set.
        for code, locationCode in ((row["code"], row["location"]) for row in DEVICES):
            path = locationPaths.get(locationCode, "")
            if path:
                DeviceModel.objects.filter(
                    tenantId=tenantId, code=code, locationPath=""
                ).update(locationPath=path)

        # Backfill the cost centre on rows seeded before the column existed.
        # Only ever fills a blank, so a tenant's own value is never clobbered.
        for row in DEVICES:
            if not row.get("costCenter"):
                continue
            DeviceModel.objects.filter(
                tenantId=tenantId, code=row["code"], costCenterCode=""
            ).update(
                costCenterCode=row["costCenter"],
                costCenterName=row.get("costCenterName", ""),
            )

        # -- Asset hierarchy: sub-assemblies under their machines ---------------------
        # Done in a second pass so every parent id already exists. Without
        # this the demo shows a flat equipment list and the hierarchy page
        # has nothing below the location tree to draw.
        for childCode, parentCode in ASSET_PARENTS.items():
            childId = deviceIds.get(childCode)
            parentId = deviceIds.get(parentCode)
            if childId is None or parentId is None or childId == parentId:
                continue
            DeviceModel.objects.filter(id=childId, parentDeviceId__isnull=True).update(
                parentDeviceId=parentId
            )

        # -- Work calendar, holidays and shifts (Phase 28) ---------------------------
        # A Jalali date picker is not a schedule. The demo therefore carries a
        # real working pattern: a site calendar, the fixed-date Iranian public
        # holidays for 1405, and a three-shift rotation to give capacity a
        # number.
        #
        # Only the *fixed* Jalali holidays are seeded. The lunar ones (عید فطر,
        # تاسوعا, عاشورا …) move against the solar calendar every year and need
        # a Hijri conversion this product deliberately does not carry; they are
        # entered per-year from the calendar screen.
        calendar, calendarCreated = WorkCalendarModel.objects.get_or_create(
            tenantId=tenantId,
            code="CAL-MAIN",
            deletedAt__isnull=True,
            defaults={
                "name": "تقویم کاری سایت اصلی",
                "locationId": locationIds.get("SITE-01"),
                "timezone": "Asia/Tehran",
                "weekendDays": "4",  # جمعه
                "rollPolicy": "forward",
                "isDefault": True,
                "active": True,
                "note": "هفتهٔ کاری شنبه تا پنجشنبه، جمعه تعطیل.",
                "createdAt": now,
            },
        )

        # The official solar list lives in the domain so `seedIranHolidays`
        # (production-safe) and this demo seeder cannot drift apart.
        jalaliYear = 1405
        holidayCreated = 0
        for jMonth, jDay, title in IRAN_OFFICIAL_SOLAR_HOLIDAYS:
            if jDay > jalaliMonthLength(jalaliYear, jMonth):
                continue
            iso = jalaliToDate(jalaliYear, jMonth, jDay).isoformat()
            _, made = CalendarHolidayModel.objects.get_or_create(
                tenantId=tenantId,
                calendarId=calendar.id,
                onDate=date.fromisoformat(iso),
                deletedAt__isnull=True,
                defaults={
                    "name": title,
                    "kind": "official",
                    "recursAnnually": True,
                    "jalaliMonth": jMonth,
                    "jalaliDay": jDay,
                    "createdAt": now,
                },
            )
            holidayCreated += int(made)

        SHIFTS = [
            ("SH-A", "شیفت صبح", "morning", time(6, 0), time(14, 0), 4),
            ("SH-B", "شیفت عصر", "evening", time(14, 0), time(22, 0), 3),
            ("SH-C", "شیفت شب", "night", time(22, 0), time(6, 0), 2),
        ]
        shiftCreated = 0
        for code, title, kind, startAt, endAt, crew in SHIFTS:
            _, made = WorkShiftModel.objects.get_or_create(
                tenantId=tenantId,
                calendarId=calendar.id,
                code=code,
                deletedAt__isnull=True,
                defaults={
                    "name": title,
                    "kind": kind,
                    "startTime": startAt,
                    "endTime": endAt,
                    "weekdays": "",  # every day the calendar is open
                    "headcount": crew,
                    "active": True,
                    "createdAt": now,
                },
            )
            shiftCreated += int(made)

        # -- PM plans + one execution each -------------------------------------------
        planIds: dict[str, uuid.UUID] = {}
        for row in PM_PLANS:
            deviceCode = row["device"]
            deviceId = deviceIds.get(deviceCode)
            if deviceId is None:
                continue
            plan, wasCreated = PmPlanModel.objects.get_or_create(
                tenantId=tenantId,
                deviceId=deviceId,
                title=row["title"],
                defaults={
                    "id": uuid.uuid4(),
                    "discipline": row["discipline"],
                    "description": f"سرویس دوره‌ای «{deviceMeta[deviceCode]['name']}» طبق دستور سازنده.",
                    "checklist": "بازرسی ظاهری؛ گرفتن ایمنی؛ سرویس اصلی؛ تست و تحویل؛ ثبت در تایم‌لاین",
                    "frequencyEvery": row["every"],
                    "frequencyUnit": row["unit"],
                    "estimatedMinutes": row["minutes"],
                    "responsibleName": row["responsible"],
                    "lastExecutedOn": today - timedelta(days=10),
                    "createdAt": now,
                },
            )
            planIds[f"{deviceCode}:{row['title']}"] = plan.id
            created["pmPlans"] += int(wasCreated)
            if wasCreated:
                PmExecutionModel.objects.create(
                    id=uuid.uuid4(),
                    tenantId=tenantId,
                    planId=plan.id,
                    deviceId=deviceId,
                    discipline=plan.discipline,
                    performedOn=today - timedelta(days=10),
                    dueOn=today - timedelta(days=10),
                    onTime=True,
                    performedByName=row["responsible"],
                    durationMinutes=row["minutes"],
                    findings="سرویس با موفقیت انجام شد.",
                    createdAt=now,
                )

        # -- Work orders (with labour + parts for the cost report) --------------------
        for row in WORK_ORDERS:
            deviceCode = row["device"]
            deviceId = deviceIds.get(deviceCode)
            if deviceId is None:
                continue
            orderKey = {"tenantId": tenantId, "deviceId": deviceId, "title": row["title"]}
            existing = WorkOrderModel.objects.filter(**orderKey, deletedAt__isnull=True).first()
            if existing is not None:
                continue
            started = now - timedelta(days=row["daysAgo"]) if row["daysAgo"] >= 0 else now - timedelta(days=0)
            finished = row.get("finished")
            closedAt = now - timedelta(days=finished) if finished is not None else None
            downtime = row.get("downtime", 0)
            hours = row.get("hours", "0")
            rate = row.get("labourRate", "0")
            order = WorkOrderModel.objects.create(
                id=uuid.uuid4(),
                tenantId=tenantId,
                deviceId=deviceId,
                title=row["title"],
                description=f"ثبت‌شده از {WO_STATUS_DEPARTMENT.get(deviceMeta[deviceCode]['department'], 'تولید')} برای «{deviceMeta[deviceCode]['name']}».",
                orderType=row["type"],
                priority=row["priority"],
                status=row["status"],
                department=deviceMeta[deviceCode]["department"],
                requestedByName="اپراتور خط",
                assignedToName=row["tech"],
                createdAt=started,
                closedAt=closedAt,
                downtimeMinutes=int(downtime),
                labourHours=hours,
                failureReportedAt=started if row["type"] == "corrective" else None,
                repairStartedAt=started + timedelta(hours=1) if closedAt else None,
                repairFinishedAt=closedAt - timedelta(minutes=int(downtime or 0)) if closedAt and downtime else (closedAt if closedAt else None),
                returnedToServiceAt=closedAt,
                resolutionNote="رسیدگی و رفع عیب انجام شد." if closedAt else "",
                pmPlanId=planIds.get(f"{deviceCode}:{'سرویس ماهانه‌ی هیدرولیک پرس ۱'}") if row["type"] == "preventive" else None,
            )
            created["workOrders"] += 1
            if closedAt:
                WorkOrderLabourEntryModel.objects.create(
                    id=uuid.uuid4(),
                    tenantId=tenantId,
                    workOrderId=order.id,
                    technicianName=row["tech"],
                    hours=hours,
                    hourlyRate=rate,
                    workedAt=closedAt - timedelta(hours=float(hours)),
                    note="ثبت خودکار نمایشی",
                )
                order.labourCost = float(hours) * float(rate)
                partsTotal = 0.0
                for partCode, quantity in row.get("parts", []):
                    partId = partIds.get(partCode)
                    if partId is None:
                        continue
                    partRow = SparePartModel.objects.get(tenantId=tenantId, code=partCode)
                    partsTotal += float(quantity) * float(partRow.unitCost)
                    WorkOrderPartUsageModel.objects.create(
                        id=uuid.uuid4(),
                        tenantId=tenantId,
                        workOrderId=order.id,
                        partId=partRow.id,
                        partCode=partRow.code,
                        partName=partRow.name,
                        unit=partRow.unit,
                        quantity=quantity,
                        unitCost=partRow.unitCost,
                        note="مصرف نمایشی",
                        consumedAt=closedAt,
                    )
                order.partsCost = partsTotal
                order.save(update_fields=["labourCost", "partsCost"])

        summary = ", ".join(f"{key}={value}" for key, value in created.items())
        self.stdout.write(self.style.SUCCESS(f"Demo seed done for tenant «{TENANT_CODE}» → {summary}"))
