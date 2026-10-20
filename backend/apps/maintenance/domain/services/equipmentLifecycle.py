"""Explainable, advisory equipment-lifecycle analysis.

This module deliberately contains no ORM, HTTP, or provider-specific AI code.
It aggregates dated corrective work orders, technician-confirmed repair scopes,
part-impact snapshots, trusted gauge readings, and same-tenant retirement
cohorts. A part count never becomes a major-repair count by itself.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Iterable

REPAIR_SCOPE_UNCLASSIFIED = "unclassified"
REPAIR_SCOPE_MINOR = "minor"
REPAIR_SCOPE_MAJOR = "major"
REPAIR_SCOPE_OVERHAUL = "overhaul"
REPAIR_SCOPES = (
    REPAIR_SCOPE_UNCLASSIFIED,
    REPAIR_SCOPE_MINOR,
    REPAIR_SCOPE_MAJOR,
    REPAIR_SCOPE_OVERHAUL,
)

PART_IMPACT_UNKNOWN = "unknown"
PART_IMPACT_MINOR = "minor"
PART_IMPACT_MAJOR = "major"
PART_LIFECYCLE_IMPACTS = (PART_IMPACT_UNKNOWN, PART_IMPACT_MINOR, PART_IMPACT_MAJOR)

PERFORMANCE_ROLE_NONE = "none"
PERFORMANCE_ROLE_HIGHER_IS_BETTER = "higherIsBetter"
PERFORMANCE_ROLE_LOWER_IS_BETTER = "lowerIsBetter"
PERFORMANCE_ROLES = (
    PERFORMANCE_ROLE_NONE,
    PERFORMANCE_ROLE_HIGHER_IS_BETTER,
    PERFORMANCE_ROLE_LOWER_IS_BETTER,
)

CORRECTIVE_ORDER_TYPE = "corrective"
CANCELLED_ORDER_STATUS = "cancelled"
TRUSTED_REPAIR_STATUSES = frozenset({"completed", "pendingApproval"})


@dataclass(frozen=True)
class LifecycleWorkOrder:
    id: str
    orderType: str
    status: str
    repairScope: str
    createdAt: datetime
    downtimeMinutes: int = 0
    labourHours: Decimal = Decimal("0")
    repeatFailure: bool = False
    title: str = ""
    description: str = ""
    failureSymptom: str = ""
    rootCause: str = ""
    actionTaken: str = ""


@dataclass(frozen=True)
class LifecyclePartUse:
    workOrderId: str
    partCode: str
    partName: str
    quantity: Decimal
    lifecycleImpact: str = PART_IMPACT_UNKNOWN


@dataclass(frozen=True)
class LifecyclePerformancePoint:
    id: str
    name: str
    unit: str
    role: str
    minimumValue: Decimal | None = None
    maximumValue: Decimal | None = None


@dataclass(frozen=True)
class LifecycleMeterReading:
    meterPointId: str
    value: Decimal
    capturedAt: datetime


@dataclass(frozen=True)
class EquipmentLifecycleSnapshot:
    workOrders: tuple[LifecycleWorkOrder, ...] = ()
    partUses: tuple[LifecyclePartUse, ...] = ()
    performancePoints: tuple[LifecyclePerformancePoint, ...] = ()
    performanceReadings: tuple[LifecycleMeterReading, ...] = ()
    retiredPeerMajorRepairCounts: tuple[int, ...] = ()
    cohortType: str = "none"
    cohortLabel: str = ""
    modelNumber: str = ""
    assetType: str = ""


@dataclass(frozen=True)
class RepairScopeSuggestion:
    suggestedScope: str
    confidence: str
    reasons: tuple[str, ...]
    requiresHumanConfirmation: bool = True


_OVERHAUL_PHRASES = (
    "اورهال",
    "بازسازی کامل",
    "تعمیر اساسی کامل",
    "full overhaul",
    "complete rebuild",
    "تعمیر کامل مجموعه",
)
_MAJOR_PHRASES = (
    "تعمیر اساسی",
    "تعویض موتور",
    "تعویض گیربکس",
    "تعویض روتور",
    "تعویض استاتور",
    "تعویض شفت",
    "بازسازی موتور",
    "تعویض مجموعه پمپ",
    "major repair",
    "gearbox replacement",
    "motor replacement",
    "rotor replacement",
    "shaft replacement",
)
_MINOR_PHRASES = (
    "بلبرینگ",
    "یاتاقان",
    "فیلتر",
    "روغن کاری",
    "روانکاری",
    "تسمه",
    "واشر",
    "فیوز",
    "کاسه نمد",
    "bearing",
    "filter",
    "lubricant",
    "belt",
    "gasket",
    "fuse",
    "seal",
)


def suggestRepairScope(
    *,
    title: str = "",
    description: str = "",
    failureSymptom: str = "",
    rootCause: str = "",
    actionTaken: str = "",
    partUses: Iterable[LifecyclePartUse] = (),
) -> RepairScopeSuggestion:
    """Suggest a scope from explicit work text and part metadata.

    Severity is never inferred from the quantity or number of parts. Text and
    inventory classifications are evidence only; the caller must persist a
    technician's explicit choice before the scope affects lifecycle counts.
    """
    text = " ".join(
        str(value or "")
        for value in (title, description, failureSymptom, rootCause, actionTaken)
    ).casefold()
    uses = tuple(partUses)
    majorParts = tuple(use for use in uses if use.lifecycleImpact == PART_IMPACT_MAJOR)
    minorParts = tuple(use for use in uses if use.lifecycleImpact == PART_IMPACT_MINOR)
    minorText = any(phrase in text for phrase in _MINOR_PHRASES)

    if any(phrase in text for phrase in _OVERHAUL_PHRASES):
        return RepairScopeSuggestion(
            suggestedScope=REPAIR_SCOPE_OVERHAUL,
            confidence="high",
            reasons=("شرح کار شامل نشانهٔ صریح بازسازی/اورهال کامل است.",),
        )
    if any(phrase in text for phrase in _MAJOR_PHRASES):
        reasons = ["شرح کار شامل نشانهٔ صریح تعمیر اساسی یا تعویض یک مجموعهٔ اصلی است."]
        if minorParts:
            reasons.append("قطعات کوچک ثبت‌شده جداگانه شمرده شده‌اند و شدت تعمیر را افزایش نمی‌دهند.")
        return RepairScopeSuggestion(
            suggestedScope=REPAIR_SCOPE_MAJOR,
            confidence="high",
            reasons=tuple(reasons),
        )
    if majorParts:
        names = ", ".join(dict.fromkeys(use.partName or use.partCode for use in majorParts[:4]))
        return RepairScopeSuggestion(
            suggestedScope=REPAIR_SCOPE_MAJOR,
            confidence="medium",
            reasons=(
                f"قطعه/قطعات با اثر عمر «اصلی» ثبت شده‌اند: {names or 'بدون نام'}.",
                "مصرف قطعه فقط قرینهٔ پیشنهاد است؛ تأیید تکنسین لازم است.",
            ),
        )
    if minorParts or minorText:
        names = ", ".join(dict.fromkeys(use.partName or use.partCode for use in minorParts[:4]))
        reasons = []
        if minorText:
            reasons.append("شرح کار به بلبرینگ/یاتاقان یا قطعهٔ مصرفی کوچک اشاره می‌کند.")
        if minorParts:
            reasons.append(f"قطعات کم‌اثر ثبت‌شده: {names or 'قطعهٔ مصرفی'}.")
        reasons.append("تعداد قطعات مصرفی به‌تنهایی تعمیر اساسی محسوب نمی‌شود.")
        return RepairScopeSuggestion(
            suggestedScope=REPAIR_SCOPE_MINOR,
            confidence="medium" if minorParts and not minorText else "low",
            reasons=tuple(reasons),
        )

    return RepairScopeSuggestion(
        suggestedScope=REPAIR_SCOPE_UNCLASSIFIED,
        confidence="low",
        reasons=(
            "شرح کار و طبقه‌بندی قطعات برای تشخیص شدت تعمیر شواهد کافی ندارند.",
            "تا ثبت/تأیید تکنسین، این رویداد در شمار تعمیر اساسی قرار نمی‌گیرد.",
        ),
    )


def _round(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _average(values: Iterable[Decimal]) -> float | None:
    sequence = tuple(float(value) for value in values)
    return statistics.fmean(sequence) if sequence else None


def _frequencyTrend(recentCount: int, previousCount: int, *, hasEvidence: bool) -> str:
    if not hasEvidence:
        return "insufficientData"
    if recentCount >= previousCount + 2:
        return "increasing"
    if previousCount >= recentCount + 2:
        return "decreasing"
    return "stable"


def _performanceSignals(
    points: tuple[LifecyclePerformancePoint, ...],
    readings: tuple[LifecycleMeterReading, ...],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    readingsByPoint: dict[str, list[LifecycleMeterReading]] = {}
    for reading in readings:
        readingsByPoint.setdefault(reading.meterPointId, []).append(reading)

    for point in points:
        if point.role not in {
            PERFORMANCE_ROLE_HIGHER_IS_BETTER,
            PERFORMANCE_ROLE_LOWER_IS_BETTER,
        }:
            continue
        series = sorted(readingsByPoint.get(point.id, ()), key=lambda item: item.capturedAt)
        row: dict[str, object] = {
            "meterPointId": point.id,
            "name": point.name,
            "unit": point.unit,
            "role": point.role,
            "readingCount": len(series),
            "baselineValue": None,
            "recentAverage": None,
            "retentionPercent": None,
            "changePercent": None,
            "trend": "insufficientData",
            "lastReadingAt": series[-1].capturedAt.isoformat() if series else "",
            "configuredMinimum": float(point.minimumValue) if point.minimumValue is not None else None,
            "configuredMaximum": float(point.maximumValue) if point.maximumValue is not None else None,
        }
        if len(series) < 2:
            result.append(row)
            continue

        windowSize = min(3, len(series) // 2)
        baseline = _average(item.value for item in series[:windowSize])
        current = _average(item.value for item in series[-windowSize:])
        row["baselineValue"] = _round(baseline)
        row["recentAverage"] = _round(current)
        if baseline is None or current is None:
            result.append(row)
            continue

        # A zero baseline cannot form a ratio. Do not invent a percentage.
        if point.role == PERFORMANCE_ROLE_HIGHER_IS_BETTER:
            retention = current / baseline * 100 if baseline != 0 else None
        elif current == 0:
            # For a lower-is-better metric, reaching zero is the best possible
            # observed value; the exact ratio is undefined, so leave it unknown.
            retention = None
        else:
            retention = baseline / current * 100 if baseline != 0 else None
        if retention is None:
            row["trend"] = "insufficientData"
            result.append(row)
            continue

        change = retention - 100.0
        row["retentionPercent"] = _round(retention)
        row["changePercent"] = _round(change)
        # A one-percentage-point band is a display convention only; no safety
        # or retirement decision is derived from this classification.
        row["trend"] = (
            "declining" if change < -1.0 else "improving" if change > 1.0 else "stable"
        )
        result.append(row)
    return result


def analyzeEquipmentLifecycle(
    snapshot: EquipmentLifecycleSnapshot,
    *,
    asOf: datetime,
    deviceId: str,
) -> dict[str, object]:
    """Return evidence, data gaps, and advisory trends for one device."""
    cutoffRecent = asOf - timedelta(days=180)
    cutoffPrevious = cutoffRecent - timedelta(days=180)
    corrective = tuple(
        order
        for order in snapshot.workOrders
        if order.orderType == CORRECTIVE_ORDER_TYPE
        and order.status != CANCELLED_ORDER_STATUS
        and order.createdAt <= asOf
    )
    recent = tuple(order for order in corrective if order.createdAt >= cutoffRecent)
    previous = tuple(
        order for order in corrective if cutoffPrevious <= order.createdAt < cutoffRecent
    )
    confirmedMajor = tuple(
        order
        for order in corrective
        if order.repairScope in {REPAIR_SCOPE_MAJOR, REPAIR_SCOPE_OVERHAUL}
    )
    overhauls = tuple(order for order in corrective if order.repairScope == REPAIR_SCOPE_OVERHAUL)
    minorRepairs = tuple(order for order in corrective if order.repairScope == REPAIR_SCOPE_MINOR)
    unclassified = tuple(
        order for order in corrective if order.repairScope == REPAIR_SCOPE_UNCLASSIFIED
    )

    partUses = tuple(snapshot.partUses)
    minorPartUses = tuple(use for use in partUses if use.lifecycleImpact == PART_IMPACT_MINOR)
    majorPartUses = tuple(use for use in partUses if use.lifecycleImpact == PART_IMPACT_MAJOR)
    unknownPartUses = tuple(
        use for use in partUses if use.lifecycleImpact not in {PART_IMPACT_MINOR, PART_IMPACT_MAJOR}
    )

    recentDowntime = sum(max(0, int(order.downtimeMinutes or 0)) for order in recent)
    previousDowntime = sum(max(0, int(order.downtimeMinutes or 0)) for order in previous)
    periodMinutes = 180 * 24 * 60
    recentAvailability = max(0.0, 100.0 - recentDowntime / periodMinutes * 100.0)
    previousAvailability = max(0.0, 100.0 - previousDowntime / periodMinutes * 100.0)
    availabilityChange = recentAvailability - previousAvailability
    availabilityTrend = (
        "declining" if availabilityChange < -0.5 else "improving" if availabilityChange > 0.5 else "stable"
    )

    recentRate = len(recent) / 180.0
    previousRate = len(previous) / 180.0
    failureTrend = _frequencyTrend(
        len(recent), len(previous), hasEvidence=bool(recent or previous)
    )
    recentMajor = tuple(
        order for order in recent if order.repairScope in {REPAIR_SCOPE_MAJOR, REPAIR_SCOPE_OVERHAUL}
    )
    previousMajor = tuple(
        order for order in previous if order.repairScope in {REPAIR_SCOPE_MAJOR, REPAIR_SCOPE_OVERHAUL}
    )
    classifiedWindow = tuple(
        order for order in (*recent, *previous) if order.repairScope != REPAIR_SCOPE_UNCLASSIFIED
    )
    majorRepairTrend = _frequencyTrend(
        len(recentMajor), len(previousMajor), hasEvidence=bool(classifiedWindow)
    )

    recentRepairHours = [
        float(order.labourHours)
        for order in recent
        if order.labourHours is not None and float(order.labourHours) >= 0
    ]
    performanceSignals = _performanceSignals(snapshot.performancePoints, snapshot.performanceReadings)
    validPerformance = [
        row for row in performanceSignals if isinstance(row.get("retentionPercent"), (int, float))
    ]
    combinedRetention = (
        statistics.median(float(row["retentionPercent"]) for row in validPerformance)
        if validPerformance
        else None
    )
    performanceTrend = (
        "declining"
        if combinedRetention is not None and combinedRetention < 99.0
        else "improving"
        if combinedRetention is not None and combinedRetention > 101.0
        else "stable"
        if combinedRetention is not None
        else "insufficientData"
    )

    peerCounts = tuple(
        max(0, int(count))
        for count in snapshot.retiredPeerMajorRepairCounts
        if int(count) > 0
    )
    if len(peerCounts) >= 3:
        typicalAtRetirement = float(statistics.median(peerCounts))
        estimatedRemaining = max(0.0, typicalAtRetirement - len(confirmedMajor))
        estimateStatus = "estimated"
    else:
        typicalAtRetirement = None
        estimatedRemaining = None
        estimateStatus = "insufficientData"

    declineSignals = []
    if performanceTrend == "declining":
        declineSignals.append("performance")
    if majorRepairTrend == "increasing":
        declineSignals.append("confirmedMajorRepairFrequency")
    if availabilityTrend == "declining":
        declineSignals.append("availability")

    if estimateStatus == "estimated" and estimatedRemaining == 0:
        condition = "retirementReview"
    elif len(declineSignals) >= 2:
        condition = "declining"
    elif declineSignals:
        condition = "watch"
    elif not corrective and not snapshot.performanceReadings:
        condition = "insufficientData"
    else:
        condition = "stable"

    readingCount = sum(int(row["readingCount"]) for row in performanceSignals)
    if len(peerCounts) >= 8 and readingCount >= 12 and len(confirmedMajor) >= 3:
        confidence = "high"
        confidenceReason = "همتای دارای تعمیر اساسیِ تأییدشده، قرائت عملکرد و سابقهٔ انسانیِ طبقه‌بندی‌شده در حجم مناسب موجود است."
    elif len(peerCounts) >= 3 or (readingCount >= 6 and len(corrective) >= 3):
        confidence = "medium"
        confidenceReason = "برآورد بر پایهٔ بخشی از شواهد است؛ تعداد نمونه یا پوشش تاریخچه محدود است."
    elif corrective or readingCount:
        confidence = "low"
        confidenceReason = "دادهٔ موجود برای جهت‌گیری مفید است، اما برای برآورد عمر عددی کافی نیست."
    else:
        confidence = "insufficient"
        confidenceReason = "هنوز سابقهٔ قابل اتکای تعمیر یا قرائت عملکرد برای تحلیل ثبت نشده است."

    indicators: list[dict[str, str]] = []
    if confirmedMajor:
        indicators.append(
            {
                "code": "confirmedMajorRepairs",
                "severity": "info",
                "detail": f"{len(confirmedMajor)} تعمیر اساسی/اورهال با تأیید تکنسین ثبت شده است.",
            }
        )
    if unknownPartUses:
        indicators.append(
            {
                "code": "unclassifiedPartImpact",
                "severity": "info",
                "detail": f"اثر عمر {len(unknownPartUses)} ردیف مصرف قطعه هنوز طبقه‌بندی نشده است.",
            }
        )
    if performanceTrend == "declining":
        indicators.append(
            {
                "code": "performanceDeclining",
                "severity": "warning",
                "detail": f"میانهٔ سیگنال‌های عملکرد {abs(combinedRetention - 100.0):.1f}% پایین‌تر از مبنای همان سیگنال است.",
            }
        )
    if majorRepairTrend == "increasing":
        indicators.append(
            {
                "code": "majorRepairFrequencyIncreasing",
                "severity": "warning",
                "detail": f"تعمیرات اساسی/اورهالِ تأییدشده در ۱۸۰ روز اخیر {len(recentMajor)} و در ۱۸۰ روز قبل {len(previousMajor)} مورد بوده است.",
            }
        )
    if failureTrend == "increasing":
        indicators.append(
            {
                "code": "correctiveFrequencyIncreasing",
                "severity": "info",
                "detail": f"تعداد کل دستورکارهای اصلاحی در ۱۸۰ روز اخیر {len(recent)} و در ۱۸۰ روز قبل {len(previous)} بوده است؛ این شمارش شامل تعمیرات کوچک هم می‌شود و به‌تنهایی نشانهٔ تعمیر اساسی نیست.",
            }
        )
    if availabilityTrend == "declining":
        indicators.append(
            {
                "code": "availabilityDeclining",
                "severity": "warning",
                "detail": f"دسترس‌پذیری محاسبه‌شده از توقف ثبت‌شده {abs(availabilityChange):.2f} واحد درصد کاهش یافته است.",
            }
        )
    if estimateStatus == "estimated":
        indicators.append(
            {
                "code": "retirementCohortEstimate",
                "severity": "warning" if estimatedRemaining == 0 else "info",
                "detail": f"میانهٔ {len(peerCounts)} دستگاه مشابهِ بازنشسته: {typicalAtRetirement:g} تعمیر اساسی/اورهالِ تأییدشده تا بازنشستگی؛ تعمیرات کوچک در این شمارش نیستند.",
            }
        )
    if not validPerformance:
        indicators.append(
            {
                "code": "performanceDataInsufficient",
                "severity": "info",
                "detail": "برای سنجش افت عملکرد، کنتور gauge با نقش عملکردی و دست‌کم دو قرائت معتبر لازم است.",
            }
        )
    if estimateStatus == "insufficientData":
        indicators.append(
            {
                "code": "retirementCohortInsufficient",
                "severity": "info",
                "detail": f"برای تخمین عمر باقیمانده حداقل ۳ تجهیز بازنشستهٔ مشابه با سابقهٔ تعمیر اساسیِ انسانی و کامل لازم است؛ نمونهٔ قابل‌مقایسهٔ فعلی {len(peerCounts)} است.",
            }
        )

    if estimateStatus == "estimated":
        summary = (
            f"{len(corrective)} رویداد تعمیر اصلاحی ثبت شده؛ {len(confirmedMajor)} مورد از شدت اساسی/اورهال به‌تأیید تکنسین رسیده است. "
            f"در گروه مرجع {len(peerCounts)} تجهیز مشابه با سابقهٔ کامل و تعمیر اساسیِ تأییدشده، میانهٔ تعداد تعمیرات اساسی/اورهال تا بازنشستگی {typicalAtRetirement:g} بوده؛ "
            f"برآورد باقیمانده {estimatedRemaining:g} رویداد اساسی است. تعمیرات کوچک و مصرفی در این برآورد اثری ندارند. این فقط پیشنهاد بازبینی است، نه دستور خروج از سرویس."
        )
    elif combinedRetention is not None:
        summary = (
            f"{len(corrective)} رویداد تعمیر اصلاحی ثبت شده؛ {len(confirmedMajor)} تعمیر اساسی/اورهال تأیید شده است. "
            f"میانهٔ سیگنال‌های عملکردِ پیکربندی‌شده {combinedRetention:.1f}% از مبنای هر سیگنال است. "
            "برای تخمین عمر عددی، نمونهٔ کافی از دستگاه‌های مشابهِ بازنشسته موجود نیست."
        )
    elif corrective:
        summary = (
            f"{len(corrective)} رویداد تعمیر اصلاحی ثبت شده؛ {len(confirmedMajor)} تعمیر اساسی/اورهال تأیید شده و "
            f"{len(unclassified)} رویداد هنوز طبقه‌بندی نشده است. قطعات کوچک/مصرفی به‌تنهایی تعمیر اساسی محسوب نمی‌شوند. "
            "قرائت عملکردی یا گروه مرجع کافی برای تخمین عمر باقیمانده در دسترس نیست."
        )
    else:
        summary = (
            "برای این تجهیز هنوز سابقهٔ اصلاحی و قرائت عملکرد کافی ثبت نشده است. "
            "تحلیل عددی عمر مفید عمداً نمایش داده نمی‌شود تا قطعیت ساختگی ایجاد نشود."
        )

    return {
        "deviceId": str(deviceId),
        "generatedAt": asOf.isoformat(),
        "advisoryOnly": True,
        "analysisMethod": "explainable-maintenance-trend-v1",
        "condition": condition,
        "confidence": confidence,
        "confidenceReason": confidenceReason,
        "summary": summary,
        "events": {
            "correctiveCount": len(corrective),
            "completedCorrectiveCount": sum(order.status == "completed" for order in corrective),
            "majorRepairCount": len(confirmedMajor),
            "overhaulCount": len(overhauls),
            "minorRepairCount": len(minorRepairs),
            "unclassifiedRepairCount": len(unclassified),
            "minorPartUseCount": len(minorPartUses),
            "majorPartUseCount": len(majorPartUses),
            "unclassifiedPartUseCount": len(unknownPartUses),
            "minorPartQuantity": _round(sum(float(use.quantity) for use in minorPartUses), 3),
            "majorPartQuantity": _round(sum(float(use.quantity) for use in majorPartUses), 3),
        },
        "reliability": {
            "recentWindowDays": 180,
            "recentCorrectiveCount": len(recent),
            "previousCorrectiveCount": len(previous),
            "recentCorrectiveRatePerDay": _round(recentRate, 4),
            "previousCorrectiveRatePerDay": _round(previousRate, 4),
            "failureFrequencyTrend": failureTrend,
            "recentMajorRepairCount": len(recentMajor),
            "previousMajorRepairCount": len(previousMajor),
            "majorRepairFrequencyTrend": majorRepairTrend,
            "recentAvailabilityPercent": _round(recentAvailability),
            "previousAvailabilityPercent": _round(previousAvailability),
            "availabilityChangePercentagePoints": _round(availabilityChange),
            "availabilityTrend": availabilityTrend,
            "recentDowntimeHours": _round(recentDowntime / 60.0),
            "previousDowntimeHours": _round(previousDowntime / 60.0),
            "averageRepairLabourHours": _round(statistics.fmean(recentRepairHours))
            if recentRepairHours
            else None,
            "repeatFailureCount": sum(order.repeatFailure for order in corrective),
        },
        "performance": {
            "signals": performanceSignals,
            "overallRetentionPercent": _round(combinedRetention),
            "trend": performanceTrend,
            "validReadingCount": readingCount,
            "configuredSignalCount": len(performanceSignals),
        },
        "lifeEstimate": {
            "status": estimateStatus,
            "cohortType": snapshot.cohortType,
            "cohortLabel": snapshot.cohortLabel,
            "peerCount": len(peerCounts),
            "typicalMajorRepairsAtRetirement": _round(typicalAtRetirement, 1),
            "estimatedRemainingMajorRepairs": _round(estimatedRemaining, 1),
            "currentMajorRepairCount": len(confirmedMajor),
            "reason": "same-tenant-retired-asset-cohort"
            if estimateStatus == "estimated"
            else "fewer-than-three-retired-peers-with-repair-history",
        },
        "indicators": indicators,
        "limitations": [
            "همهٔ دستورکارهای اصلاحیِ غیرلغوشده به‌عنوان رویداد تعمیر شمرده می‌شوند.",
            "تعمیر اساسی فقط از طبقه‌بندی ثبت/تأییدشدهٔ انسانی شمرده می‌شود؛ مصرف قطعه جایگزین آن نیست.",
            "روند عملکرد فقط از نقاط gauge که نقش عملکردی برایشان تعریف شده و قرائت معتبر دارند محاسبه می‌شود.",
            "مقایسهٔ عمر فقط با حداقل ۳ تجهیز بازنشستهٔ مشابه با سابقهٔ اصلاحیِ طبقه‌بندی‌شده و دست‌کم یک تعمیر اساسی/اورهال تأییدشده ساخته می‌شود؛ تعمیر کوچک/مصرفی در شمار عمرِ اساسی نیست و آستانهٔ ثابت تعداد تعمیر وجود ندارد.",
            "خروجی advisory است و هر تصمیم توقف، تغییر وضعیت یا بازنشستگی نیازمند تأیید مسئول است.",
        ],
    }
