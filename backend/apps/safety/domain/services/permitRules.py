"""The safety rules of a permit to work. Pure: no ORM, no clock of its own.

This module is the reason the feature exists. A permit system that records
who clicked what is paperwork; a permit system that *refuses* is a control.
Every guard below is a refusal, and each one corresponds to a way people are
actually hurt:

* **Segregation of duties** — the person who wants the work done may not be
  the person who authorises it. This is the single oldest control in
  permit-to-work and the one most often quietly bypassed, because the
  requester is usually the most senior person on site and it is faster.
* **No issue with unconfirmed mandatory precautions** — the checklist is the
  assessment. Issuing against an unticked box means nobody checked.
* **No issue of an isolation-class permit without a verified isolation
  register** — stored energy is what kills during maintenance. Applied is
  not enough; applied *and independently verified* is the control.
* **Two-person rule above high risk** — one competent person cannot catch
  their own mistake. The verifier must not be the applier.
* **Expiry is computed, never stored** — a permit's validity is a function
  of the clock. A stored flag is wrong every moment between the scan that
  set it and the next one, and "wrong" here means work proceeding under a
  permit that lapsed.
* **No closure with live isolations** — handing equipment back with locks
  still on, or claiming closure while a lock is unaccounted for, is how a
  machine is started on someone.

``now`` is always injected so the API, the scheduled scan and the tests
agree on one answer, and so a test can age a permit without sleeping.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from apps.safety.domain.valueObjects.permitState import (
    PERMIT_ACTIVE,
    PERMIT_APPROVED,
    PERMIT_STATUS_LABELS_FA,
    PERMIT_TRANSITIONS,
    RISK_LEVELS_REQUIRING_SEPARATE_VERIFIER,
    TERMINAL_PERMIT_STATUSES,
    maxValidityHoursFor,
    requiresIsolation,
)

#: Identity accepted in either form. The guards compare as strings on
#: purpose: the same person arriving once as a ``UUID`` from the ORM and
#: once as a ``str`` from JSON must still be recognised as one person, or
#: the self-approval rule silently stops working.
PersonId = str | uuid.UUID | None


class PermitRuleViolation(Exception):
    """A permit action the rules refuse.

    Carries a Persian ``message`` for the person at the keyboard and a
    stable ``code`` for the API and the tests, so wording can be improved
    without breaking either.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- Lightweight views of the related rows ---------------------------------
#
# The guards take plain snapshots rather than ORM rows: the rules must be
# testable without a database, and must not be able to trigger a lazy query
# in the middle of a safety decision.


@dataclass(frozen=True)
class PrecautionSnapshot:
    code: str
    text: str
    isMandatory: bool
    confirmed: bool


@dataclass(frozen=True)
class IsolationSnapshot:
    pointCode: str
    description: str
    appliedById: str = ""
    verifiedById: str = ""
    removedById: str = ""

    @property
    def isApplied(self) -> bool:
        return bool(self.appliedById) and not self.removedById

    @property
    def isVerified(self) -> bool:
        return bool(self.verifiedById) and not self.removedById

    @property
    def isRemoved(self) -> bool:
        return bool(self.removedById)


@dataclass(frozen=True)
class PermitValidity:
    """Where a permit sits relative to its own time window."""

    hasStarted: bool
    isExpired: bool
    isWithinWindow: bool
    minutesUntilStart: int
    minutesRemaining: int
    #: True while the permit is live and inside the last hour of its window.
    #: Drives the "about to lapse" warning, which is the point at which a
    #: crew can still extend in an orderly way instead of being stopped.
    isExpiringSoon: bool


@dataclass(frozen=True)
class GuardReport:
    """Why a permit cannot be issued, in full.

    Deliberately collects *every* blocker rather than raising on the first.
    A permit office that is told one missing item at a time will make one
    trip per item; the useful answer is the whole list.
    """

    blockers: list[str] = field(default_factory=list)

    @property
    def isSatisfied(self) -> bool:
        return not self.blockers


EXPIRY_WARNING_MINUTES = 60


def evaluatePermitValidity(
    *,
    validFrom: datetime | None,
    validTo: datetime | None,
    now: datetime,
) -> PermitValidity:
    """Place ``now`` against the permit's window.

    A permit with no window is treated as not started and not expired: it is
    a draft that has not been given times yet, and calling that "expired"
    would hide it from the person who still has to fill it in.
    """
    if validFrom is None or validTo is None:
        return PermitValidity(
            hasStarted=False,
            isExpired=False,
            isWithinWindow=False,
            minutesUntilStart=0,
            minutesRemaining=0,
            isExpiringSoon=False,
        )

    hasStarted = now >= validFrom
    isExpired = now > validTo
    minutesUntilStart = max(0, int((validFrom - now).total_seconds() // 60))
    minutesRemaining = max(0, int((validTo - now).total_seconds() // 60))
    return PermitValidity(
        hasStarted=hasStarted,
        isExpired=isExpired,
        isWithinWindow=hasStarted and not isExpired,
        minutesUntilStart=minutesUntilStart,
        minutesRemaining=minutesRemaining,
        isExpiringSoon=hasStarted and not isExpired and minutesRemaining <= EXPIRY_WARNING_MINUTES,
    )


def guardTransition(current: str, target: str) -> None:
    """Refuse any move the lifecycle does not allow."""
    if current == target:
        raise PermitRuleViolation(
            "permit.transition.noop",
            f"مجوز هم‌اکنون در وضعیت «{PERMIT_STATUS_LABELS_FA.get(current, current)}» است.",
        )
    if current in TERMINAL_PERMIT_STATUSES:
        raise PermitRuleViolation(
            "permit.transition.terminal",
            f"مجوز «{PERMIT_STATUS_LABELS_FA.get(current, current)}» است و تغییر نمی‌کند؛ "
            "برای ادامه کار مجوز جدید صادر کنید.",
        )
    allowed = PERMIT_TRANSITIONS.get(current, ())
    if target not in allowed:
        raise PermitRuleViolation(
            "permit.transition.illegal",
            f"تغییر وضعیت از «{PERMIT_STATUS_LABELS_FA.get(current, current)}» به "
            f"«{PERMIT_STATUS_LABELS_FA.get(target, target)}» مجاز نیست.",
        )


def guardValidityWindow(
    *,
    permitType: str,
    validFrom: datetime | None,
    validTo: datetime | None,
) -> None:
    """A permit must name a sane, bounded window before it can be authorised.

    The cap per type is not bureaucracy. A permit's controls are true for as
    long as the conditions they were assessed against hold: a gas test is
    not evidence about tomorrow, and a fire watch rostered for a shift is
    not watching the next one. An open-ended permit is an unassessed one.
    """
    if validFrom is None or validTo is None:
        raise PermitRuleViolation(
            "permit.window.missing", "بازه اعتبار مجوز (از/تا) باید مشخص باشد."
        )
    if validTo <= validFrom:
        raise PermitRuleViolation(
            "permit.window.inverted", "پایان اعتبار مجوز باید بعد از شروع آن باشد."
        )
    maxHours = maxValidityHoursFor(permitType)
    if validTo - validFrom > timedelta(hours=maxHours):
        raise PermitRuleViolation(
            "permit.window.tooLong",
            f"بیشترین مدت مجاز برای این نوع مجوز {maxHours} ساعت است؛ "
            "برای ادامه کار مجوز بعدی صادر کنید.",
        )


def guardSegregationOfDuties(*, requesterId: PersonId, approverId: PersonId) -> None:
    """The requester may not authorise their own permit.

    The oldest control in permit-to-work, and the first one bypassed under
    time pressure — usually by the most senior person on site, who is both
    the one who wants the job done and the one holding the authority to
    sign. Enforced in code rather than in a procedure document for exactly
    that reason.
    """
    if requesterId and approverId and str(requesterId) == str(approverId):
        raise PermitRuleViolation(
            "permit.approval.selfApproval",
            "درخواست‌کننده نمی‌تواند مجوز خودش را تأیید کند؛ "
            "تأیید باید توسط فرد دیگری انجام شود.",
        )


def guardIsolationVerifier(
    *, appliedById: PersonId, verifiedById: PersonId, riskLevel: str
) -> None:
    """Above high risk, the verifier must not be the applier.

    One competent person cannot independently check their own work. Below
    high risk the same person is accepted, because demanding a second body
    for every low-risk isolation in a small plant produces a signature that
    nobody actually witnessed — a worse outcome than an honest single
    signature.
    """
    if riskLevel not in RISK_LEVELS_REQUIRING_SEPARATE_VERIFIER:
        return
    if appliedById and verifiedById and str(appliedById) == str(verifiedById):
        raise PermitRuleViolation(
            "permit.isolation.selfVerification",
            "در کارهای با ریسک زیاد، تأییدکننده‌ی قفل‌گذاری باید فردی غیر از "
            "اجراکننده‌ی آن باشد.",
        )


def evaluateIssueReadiness(
    *,
    permitType: str,
    precautions: list[PrecautionSnapshot],
    isolations: list[IsolationSnapshot],
) -> GuardReport:
    """Everything standing between this permit and authorisation.

    Returns the full list rather than the first problem — see
    ``GuardReport``.
    """
    blockers: list[str] = []

    missing = [x for x in precautions if x.isMandatory and not x.confirmed]
    for item in missing:
        blockers.append(f"اقدام احتیاطی تأییدنشده: {item.text}")

    if requiresIsolation(permitType):
        live = [x for x in isolations if not x.isRemoved]
        if not live:
            blockers.append(
                "برای این نوع مجوز، ثبت حداقل یک نقطه جداسازی (قفل‌گذاری) الزامی است."
            )
        for point in live:
            if not point.isApplied:
                blockers.append(f"نقطه جداسازی اجرا نشده: {point.pointCode}")
            elif not point.isVerified:
                blockers.append(f"نقطه جداسازی تأیید نشده: {point.pointCode}")

    return GuardReport(blockers=blockers)


def guardApproval(
    *,
    currentStatus: str,
    permitType: str,
    riskLevel: str,
    requesterId: PersonId,
    approverId: PersonId,
    validFrom: datetime | None,
    validTo: datetime | None,
    precautions: list[PrecautionSnapshot],
    isolations: list[IsolationSnapshot],
    now: datetime,
) -> None:
    """Every check that must pass before a permit is authorised.

    Ordered so the most fundamental refusal is reported first: a permit in
    the wrong state, then who is signing, then the window, then the
    controls. Someone reading the error should learn the biggest problem,
    not an incidental one.
    """
    guardTransition(currentStatus, PERMIT_APPROVED)
    guardSegregationOfDuties(requesterId=requesterId, approverId=approverId)
    guardValidityWindow(permitType=permitType, validFrom=validFrom, validTo=validTo)

    # Authorising a permit whose window has already closed produces a
    # document that is dead on arrival and invites someone to work under it
    # anyway because "it is signed".
    if validTo is not None and now > validTo:
        raise PermitRuleViolation(
            "permit.window.alreadyPast",
            "بازه اعتبار این مجوز گذشته است؛ بازه را اصلاح کنید یا مجوز جدید بسازید.",
        )

    report = evaluateIssueReadiness(
        permitType=permitType, precautions=precautions, isolations=isolations
    )
    if not report.isSatisfied:
        raise PermitRuleViolation(
            "permit.issue.notReady",
            "مجوز آماده صدور نیست — " + "؛ ".join(report.blockers),
        )

    # Risk-tier two-person rule, applied to the register as a whole.
    if riskLevel in RISK_LEVELS_REQUIRING_SEPARATE_VERIFIER:
        for point in isolations:
            if point.isRemoved:
                continue
            guardIsolationVerifier(
                appliedById=point.appliedById,
                verifiedById=point.verifiedById,
                riskLevel=riskLevel,
            )


def guardActivation(
    *,
    currentStatus: str,
    validFrom: datetime | None,
    validTo: datetime | None,
    now: datetime,
) -> None:
    """Work may only start inside the window the permit was assessed for.

    Both ends matter. Starting late is the obvious case; starting *early*
    is the quieter one — the isolations may not be in place yet and the
    area may still be occupied by the shift that is handing over.
    """
    guardTransition(currentStatus, PERMIT_ACTIVE)
    validity = evaluatePermitValidity(validFrom=validFrom, validTo=validTo, now=now)
    if validity.isExpired:
        raise PermitRuleViolation(
            "permit.activate.expired",
            "بازه اعتبار این مجوز گذشته است؛ شروع کار با آن مجاز نیست.",
        )
    if not validity.hasStarted:
        raise PermitRuleViolation(
            "permit.activate.notYetValid",
            f"شروع اعتبار این مجوز هنوز نرسیده است "
            f"({validity.minutesUntilStart} دقیقه مانده).",
        )


def guardResume(
    *,
    currentStatus: str,
    validFrom: datetime | None,
    validTo: datetime | None,
    now: datetime,
) -> None:
    """Resuming suspended work is a fresh start and gets the same checks.

    A permit suspended at the end of a shift and resumed the next morning
    may well have lapsed overnight; treating resume as a bookkeeping flip
    would let work restart under a dead permit.
    """
    guardTransition(currentStatus, PERMIT_ACTIVE)
    validity = evaluatePermitValidity(validFrom=validFrom, validTo=validTo, now=now)
    if validity.isExpired:
        raise PermitRuleViolation(
            "permit.resume.expired",
            "بازه اعتبار این مجوز در مدت تعلیق گذشته است؛ "
            "برای ادامه کار مجوز جدید صادر کنید.",
        )


def guardClosure(*, currentStatus: str, isolations: list[IsolationSnapshot]) -> None:
    """Equipment is not handed back while anything is still isolated.

    Closing a permit means the machine can be run. Every lock and tag the
    permit applied must be accounted for and removed first — a permit
    closed over a forgotten lock is how equipment is started with someone
    still inside it, and how a plant spends a shift hunting for the owner
    of an orphan padlock.
    """
    from apps.safety.domain.valueObjects.permitState import PERMIT_CLOSED

    guardTransition(currentStatus, PERMIT_CLOSED)
    stillIsolated = [x for x in isolations if not x.isRemoved]
    if stillIsolated:
        names = "، ".join(x.pointCode for x in stillIsolated)
        raise PermitRuleViolation(
            "permit.close.isolationsLive",
            f"این نقاط جداسازی هنوز برداشته نشده‌اند: {names}. "
            "تا بازگرداندن همه قفل‌ها، مجوز بسته نمی‌شود.",
        )


def guardIsolationRemoval(*, permitStatus: str) -> None:
    """Locks come off when the work has stopped, not while it is running.

    Removing an isolation on an active permit re-energises equipment people
    are still working on. Removal is allowed once the work is completed, or
    if the permit was cancelled or rejected before it ever ran.
    """
    from apps.safety.domain.valueObjects.permitState import (
        PERMIT_CANCELLED,
        PERMIT_COMPLETED,
        PERMIT_DRAFT,
        PERMIT_REJECTED,
        PERMIT_SUBMITTED,
    )

    allowed = (
        PERMIT_COMPLETED,
        PERMIT_CANCELLED,
        PERMIT_REJECTED,
        PERMIT_DRAFT,
        PERMIT_SUBMITTED,
    )
    if permitStatus not in allowed:
        raise PermitRuleViolation(
            "permit.isolation.removalBlocked",
            "تا زمانی که کار در جریان است، برداشتن قفل مجاز نیست؛ "
            "ابتدا پایان کار را ثبت کنید.",
        )
