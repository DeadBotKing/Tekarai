"""Persian display labels for maintenance report exports (Phase 23).

The web UI is Persian-only; the exported Excel/CSV files must match. These
maps mirror the frontend i18n keys (cmms.woStatus.*, cmms.type.*, etc.) so a
downloaded report reads exactly like the on-screen one. Unknown codes fall
back to the raw value rather than raising.
"""

from __future__ import annotations

WO_STATUS_FA: dict[str, str] = {
    "submitted": "ثبت‌شده",
    "routed": "ارجاع به واحد",
    "assigned": "سپرده‌شده",
    "inProgress": "در حال انجام",
    "onHold": "معلق",
    "pendingApproval": "در انتظار تأیید",
    "completed": "تکمیل‌شده",
    "cancelled": "لغوشده",
}

WO_TYPE_FA: dict[str, str] = {
    "corrective": "اصلاحی",
    "preventive": "پیشگیرانه",
    "inspection": "بازرسی",
}

PRIORITY_FA: dict[str, str] = {
    "low": "کم",
    "normal": "عادی",
    "high": "زیاد",
    "critical": "بحرانی",
}

DEPARTMENT_FA: dict[str, str] = {
    "general": "عمومی",
    "electrical": "برق",
    "mechanical": "مکانیک",
    "facilities": "تأسیسات",
    "instrumentation": "ابزار دقیق",
}

DEVICE_STATUS_FA: dict[str, str] = {
    "operational": "آماده به کار",
    "underMaintenance": "در حال تعمیر",
    "outOfService": "خارج از سرویس",
    "retired": "بازنشسته",
}


def statusLabel(code: str) -> str:
    return WO_STATUS_FA.get(code, code)


def typeLabel(code: str) -> str:
    return WO_TYPE_FA.get(code, code)


def priorityLabel(code: str) -> str:
    return PRIORITY_FA.get(code, code)


def departmentLabel(code: str) -> str:
    return DEPARTMENT_FA.get(code, code)


def deviceStatusLabel(code: str) -> str:
    return DEVICE_STATUS_FA.get(code, code)


def formatDateTime(isoValue: str) -> str:
    """ISO timestamp → 'YYYY-MM-DD HH:MM' (report-friendly, no timezone noise)."""
    if not isoValue:
        return ""
    from datetime import datetime

    try:
        parsed = datetime.fromisoformat(isoValue)
    except ValueError:
        return isoValue
    return parsed.strftime("%Y-%m-%d %H:%M")


def formatDate(isoValue: str) -> str:
    if not isoValue:
        return ""
    return isoValue[:10]


# Column headers shared by the CSV and Excel work-order tables.
WORK_ORDER_COLUMNS: list[str] = [
    "عنوان",
    "نوع",
    "اولویت",
    "وضعیت",
    "واحد",
    "درخواست‌دهنده",
    "تکنسین",
    "تاریخ ثبت",
    "مهلت SLA",
    "تأخیر",
    "تاریخ بستن",
    "یادداشت رفع عیب",
]
