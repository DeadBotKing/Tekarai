"""Permit-to-work vocabulary: types, lifecycle, energy sources, risk.

A permit to work is the document that says *this* work, on *this* equipment,
by *these* people, between *these* times, under *these* controls, is
authorised. In a real plant it is a legal record: when something goes wrong
the permit is the first thing an investigator asks for. Everything in this
module is therefore a controlled value, never free text — a permit whose
type is a typo cannot be audited, and a status outside this list cannot be
reasoned about by the guards in ``permitRules``.

Two choices here are worth stating plainly.

**``expired`` is a status, not a flag.** A permit that ran past its window
is not "still approved but ignore it"; it is dead, and restarting work needs
a new permit. Whether a permit *has* expired is always computed from the
clock (see ``evaluatePermitValidity``) — a stored boolean would be wrong
every moment between the scheduled scan and the next one.

**``suspended`` exists.** Work stops for alarms, shift ends, weather and
changed conditions far more often than it is cancelled, and a crew that has
to cancel and re-raise a permit to pause for an hour will instead just keep
working on a permit that no longer describes reality.
"""

from __future__ import annotations

# --- Lifecycle -------------------------------------------------------------

PERMIT_DRAFT = "draft"
PERMIT_SUBMITTED = "submitted"
PERMIT_APPROVED = "approved"  # authorised/issued, work not yet started
PERMIT_ACTIVE = "active"  # accepted by the performer, work in progress
PERMIT_SUSPENDED = "suspended"
PERMIT_COMPLETED = "completed"  # work finished, awaiting isolation removal
PERMIT_CLOSED = "closed"
PERMIT_REJECTED = "rejected"
PERMIT_CANCELLED = "cancelled"
PERMIT_EXPIRED = "expired"

PERMIT_STATUSES = (
    PERMIT_DRAFT,
    PERMIT_SUBMITTED,
    PERMIT_APPROVED,
    PERMIT_ACTIVE,
    PERMIT_SUSPENDED,
    PERMIT_COMPLETED,
    PERMIT_CLOSED,
    PERMIT_REJECTED,
    PERMIT_CANCELLED,
    PERMIT_EXPIRED,
)

#: Nothing further happens to these. Guarded in ``guardTransition``.
TERMINAL_PERMIT_STATUSES = (
    PERMIT_CLOSED,
    PERMIT_REJECTED,
    PERMIT_CANCELLED,
    PERMIT_EXPIRED,
)

#: Statuses where work is authorised to be happening on the equipment right
#: now. The question "is anybody working on this machine?" is answered with
#: this tuple, so it must not quietly grow.
WORK_IN_PROGRESS_STATUSES = (PERMIT_ACTIVE, PERMIT_SUSPENDED)

#: Statuses where the permit still constrains the equipment — it is issued
#: or in use. Used to stop two conflicting permits on one asset.
LIVE_PERMIT_STATUSES = (
    PERMIT_APPROVED,
    PERMIT_ACTIVE,
    PERMIT_SUSPENDED,
    PERMIT_COMPLETED,
)

#: Statuses whose validity window the expiry scan has to look at. A draft has
#: no authority to lapse, and a terminal permit has already stopped. Note
#: that ``completed`` is excluded: the work is finished, so the window
#: running out no longer endangers anyone — only closure is outstanding.
EXPIRY_REVIEW_STATUSES = (
    PERMIT_APPROVED,
    PERMIT_ACTIVE,
    PERMIT_SUSPENDED,
)

#: Legal moves. Everything not listed is refused, including every move out
#: of a terminal status.
PERMIT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    PERMIT_DRAFT: (PERMIT_SUBMITTED, PERMIT_CANCELLED),
    PERMIT_SUBMITTED: (PERMIT_APPROVED, PERMIT_REJECTED, PERMIT_CANCELLED),
    # An approved permit that is never started still expires: the window it
    # was assessed against has passed and the conditions may have changed.
    PERMIT_APPROVED: (PERMIT_ACTIVE, PERMIT_CANCELLED, PERMIT_EXPIRED),
    PERMIT_ACTIVE: (PERMIT_SUSPENDED, PERMIT_COMPLETED, PERMIT_CANCELLED),
    PERMIT_SUSPENDED: (PERMIT_ACTIVE, PERMIT_COMPLETED, PERMIT_CANCELLED),
    # Completion is "tools down". Closure is the separate act of removing
    # isolations and handing the equipment back, and it is the only route
    # out — a finished job cannot be cancelled retroactively.
    PERMIT_COMPLETED: (PERMIT_CLOSED,),
    PERMIT_CLOSED: (),
    PERMIT_REJECTED: (),
    PERMIT_CANCELLED: (),
    PERMIT_EXPIRED: (),
}

PERMIT_STATUS_LABELS_FA: dict[str, str] = {
    PERMIT_DRAFT: "پیش‌نویس",
    PERMIT_SUBMITTED: "در انتظار تأیید",
    PERMIT_APPROVED: "صادرشده",
    PERMIT_ACTIVE: "در حال اجرا",
    PERMIT_SUSPENDED: "معلق",
    PERMIT_COMPLETED: "کار تمام‌شده",
    PERMIT_CLOSED: "بسته‌شده",
    PERMIT_REJECTED: "ردشده",
    PERMIT_CANCELLED: "لغوشده",
    PERMIT_EXPIRED: "منقضی",
}

# --- Permit types ----------------------------------------------------------

PERMIT_HOT_WORK = "hotWork"
PERMIT_CONFINED_SPACE = "confinedSpace"
PERMIT_ELECTRICAL = "electrical"
PERMIT_WORK_AT_HEIGHT = "workAtHeight"
PERMIT_EXCAVATION = "excavation"
PERMIT_LINE_BREAKING = "lineBreaking"
PERMIT_RADIOGRAPHY = "radiography"
PERMIT_GENERAL = "general"

PERMIT_TYPES = (
    PERMIT_HOT_WORK,
    PERMIT_CONFINED_SPACE,
    PERMIT_ELECTRICAL,
    PERMIT_WORK_AT_HEIGHT,
    PERMIT_EXCAVATION,
    PERMIT_LINE_BREAKING,
    PERMIT_RADIOGRAPHY,
    PERMIT_GENERAL,
)

PERMIT_TYPE_LABELS_FA: dict[str, str] = {
    PERMIT_HOT_WORK: "کار گرم",
    PERMIT_CONFINED_SPACE: "فضای بسته",
    PERMIT_ELECTRICAL: "برق و قفل‌گذاری",
    PERMIT_WORK_AT_HEIGHT: "کار در ارتفاع",
    PERMIT_EXCAVATION: "خاک‌برداری",
    PERMIT_LINE_BREAKING: "بازکردن خط",
    PERMIT_RADIOGRAPHY: "پرتونگاری",
    PERMIT_GENERAL: "عمومی",
}

#: Types that cannot be issued without a verified isolation register. These
#: are the jobs where stored energy is the thing that kills: a machine that
#: can restart, a circuit that can be re-energised, a line that still holds
#: pressure. ``workAtHeight`` and ``radiography`` are dangerous too, but
#: their controls are barriers and dosimetry rather than isolation, so
#: demanding an isolation register there would train people to enter a fake
#: one — the worst possible outcome for a safety control.
TYPES_REQUIRING_ISOLATION = (
    PERMIT_ELECTRICAL,
    PERMIT_CONFINED_SPACE,
    PERMIT_LINE_BREAKING,
)

#: Longest validity window allowed per type, in hours. Hot work and confined
#: space are shift-bound by practice everywhere: conditions (gas readings,
#: who is watching the hole) stop being true after a few hours, and a permit
#: that outlives its assessment is a permit nobody re-checked.
MAX_VALIDITY_HOURS_BY_TYPE: dict[str, int] = {
    PERMIT_HOT_WORK: 12,
    PERMIT_CONFINED_SPACE: 12,
    PERMIT_RADIOGRAPHY: 12,
    PERMIT_ELECTRICAL: 24,
    PERMIT_LINE_BREAKING: 24,
    PERMIT_EXCAVATION: 72,
    PERMIT_WORK_AT_HEIGHT: 24,
    PERMIT_GENERAL: 24,
}

DEFAULT_MAX_VALIDITY_HOURS = 24


def maxValidityHoursFor(permitType: str) -> int:
    """Longest window this type of permit may be written for."""
    return MAX_VALIDITY_HOURS_BY_TYPE.get(permitType, DEFAULT_MAX_VALIDITY_HOURS)


def requiresIsolation(permitType: str) -> bool:
    """Whether this type may not be issued without verified isolations."""
    return permitType in TYPES_REQUIRING_ISOLATION


# --- Risk ------------------------------------------------------------------

RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_CRITICAL = "critical"

RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL)

RISK_LABELS_FA: dict[str, str] = {
    RISK_LOW: "کم",
    RISK_MEDIUM: "متوسط",
    RISK_HIGH: "زیاد",
    RISK_CRITICAL: "بحرانی",
}

#: Above this, one person may not both apply an isolation and verify it.
#: The two-person rule is the control that catches the mistake a single
#: competent person cannot catch in their own work.
RISK_LEVELS_REQUIRING_SEPARATE_VERIFIER = (RISK_HIGH, RISK_CRITICAL)


# --- Energy sources (for the isolation register) ---------------------------

ENERGY_ELECTRICAL = "electrical"
ENERGY_MECHANICAL = "mechanical"
ENERGY_HYDRAULIC = "hydraulic"
ENERGY_PNEUMATIC = "pneumatic"
ENERGY_CHEMICAL = "chemical"
ENERGY_THERMAL = "thermal"
ENERGY_GRAVITY = "gravity"
ENERGY_RADIATION = "radiation"

ENERGY_TYPES = (
    ENERGY_ELECTRICAL,
    ENERGY_MECHANICAL,
    ENERGY_HYDRAULIC,
    ENERGY_PNEUMATIC,
    ENERGY_CHEMICAL,
    ENERGY_THERMAL,
    ENERGY_GRAVITY,
    ENERGY_RADIATION,
)

ENERGY_LABELS_FA: dict[str, str] = {
    ENERGY_ELECTRICAL: "الکتریکی",
    ENERGY_MECHANICAL: "مکانیکی",
    ENERGY_HYDRAULIC: "هیدرولیک",
    ENERGY_PNEUMATIC: "پنوماتیک",
    ENERGY_CHEMICAL: "شیمیایی",
    ENERGY_THERMAL: "حرارتی",
    ENERGY_GRAVITY: "ثقلی",
    ENERGY_RADIATION: "پرتو",
}


# --- Standard precautions seeded per permit type ---------------------------
#
# The checklist a permit is issued against. Offering the right list for the
# type is the difference between a control and a formality: a blank box
# gets ticked, a named hazard gets thought about. ``True`` marks a
# precaution as mandatory — the permit cannot be issued until it is
# confirmed.

STANDARD_PRECAUTIONS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    PERMIT_HOT_WORK: (
        ("fireWatch", "آتش‌نشان ناظر تعیین و حاضر است", True),
        ("extinguisher", "خاموش‌کننده مناسب در محل موجود است", True),
        ("combustiblesRemoved", "مواد قابل‌اشتعال تا شعاع ۱۱ متر برداشته شده", True),
        ("gasTest", "تست گاز انجام و نتیجه مجاز است", True),
        ("openingsCovered", "درزها و بازشوها پوشانده شده‌اند", False),
        ("postWatch", "پایش پس از کار تا ۶۰ دقیقه برنامه‌ریزی شده", True),
    ),
    PERMIT_CONFINED_SPACE: (
        ("atmosphereTest", "تست اتمسفر (اکسیژن، گاز سمی، قابل‌اشتعال) انجام شده", True),
        ("continuousMonitoring", "پایش پیوسته اتمسفر برقرار است", True),
        ("ventilation", "تهویه اجباری برقرار است", True),
        ("standbyPerson", "نگهبان دهانه تعیین و مستقر است", True),
        ("rescuePlan", "طرح و تجهیزات نجات آماده است", True),
        ("entryLog", "دفتر ورود و خروج نفرات برقرار است", True),
    ),
    PERMIT_ELECTRICAL: (
        ("deEnergised", "مدار بی‌برق شده است", True),
        ("lockApplied", "قفل و برچسب روی کلید اصلی نصب شده", True),
        ("absenceOfVoltageTest", "تست عدم وجود ولتاژ انجام شده", True),
        ("earthing", "اتصال زمین موقت نصب شده", True),
        ("storedEnergy", "انرژی ذخیره (خازن‌ها) تخلیه شده", True),
        ("ppe", "تجهیزات حفاظت فردی آرک‌فلش استفاده می‌شود", True),
    ),
    PERMIT_WORK_AT_HEIGHT: (
        ("fallArrest", "سیستم مهار سقوط نصب و بازرسی شده", True),
        ("anchorPoint", "نقطه اتکای مطمئن تعیین شده", True),
        ("scaffoldInspected", "داربست بازرسی و برچسب‌گذاری شده", True),
        ("exclusionZone", "محدوده زیر کار مسدود شده", True),
        ("weather", "شرایط جوی بررسی و مناسب است", False),
    ),
    PERMIT_EXCAVATION: (
        ("undergroundServices", "استعلام تأسیسات زیرزمینی انجام شده", True),
        ("shoring", "حائل‌گذاری یا شیب‌دار کردن دیواره انجام شده", True),
        ("accessEgress", "راه ورود و خروج ایمن فراهم است", True),
        ("barriers", "حصار و علائم هشدار نصب شده", True),
    ),
    PERMIT_LINE_BREAKING: (
        ("depressurised", "خط تخلیه فشار شده است", True),
        ("drained", "خط تخلیه و شست‌وشو شده است", True),
        ("blinded", "بلایند/اسپید نصب شده است", True),
        ("contentIdentified", "محتوای خط شناسایی و اعلام شده", True),
        ("ppeChemical", "تجهیزات حفاظت شیمیایی مناسب استفاده می‌شود", True),
    ),
    PERMIT_RADIOGRAPHY: (
        ("areaCordoned", "محدوده پرتوگیری حصارکشی و علامت‌گذاری شده", True),
        ("dosimeters", "دزیمتر برای نفرات تأمین شده", True),
        ("rpSupervisor", "مسئول فیزیک بهداشت حاضر است", True),
        ("areaCleared", "تخلیه نفرات غیرمرتبط انجام شده", True),
    ),
    PERMIT_GENERAL: (
        ("hazardsReviewed", "ارزیابی مخاطرات کار انجام و تشریح شده", True),
        ("ppe", "تجهیزات حفاظت فردی لازم تعیین و تأمین شده", True),
        ("toolboxTalk", "جلسه توجیهی ایمنی با گروه برگزار شده", True),
        ("areaSecured", "محل کار ایمن و علامت‌گذاری شده", False),
    ),
}


def standardPrecautionsFor(permitType: str) -> tuple[tuple[str, str, bool], ...]:
    """The checklist this type of permit is issued against.

    Falls back to the general list rather than returning nothing: a permit
    type nobody anticipated must still carry a hazard review, not an empty
    checklist that can be issued with no thought at all.
    """
    return STANDARD_PRECAUTIONS.get(permitType, STANDARD_PRECAUTIONS[PERMIT_GENERAL])
