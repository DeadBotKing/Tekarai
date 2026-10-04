"""Vocabulary for workforce performance reviews (ارزیابی عملکرد) — Phase 29.

Constants only: no logic, no ORM. The scoring arithmetic lives in
``domain/services/performanceReviewRules.py`` and reads from here, so the
rater roster and the weights can be inspected in one place.
"""

from __future__ import annotations

# -- score scale ------------------------------------------------------------
# 0..100 rather than 1..5, because the whole point of the engine is to measure
# *how far* a rater sits from the consensus, and a five-point scale is too
# coarse for that distance to mean anything.
SCORE_MIN = 0
SCORE_MAX = 100

# -- review cycle status ----------------------------------------------------
CYCLE_DRAFT = "draft"
CYCLE_OPEN = "open"
CYCLE_CLOSED = "closed"
CYCLE_STATUSES = (CYCLE_DRAFT, CYCLE_OPEN, CYCLE_CLOSED)

#: An appraisal period longer than this is almost certainly a typo in a date
#: field rather than a real review window, and it would drag in years of work
#: orders when the system half is computed.
MAX_CYCLE_DAYS = 400

#: Dates are stored as Gregorian. Anything earlier than this is not a real
#: review period, it is a Jalali year (1404, 1405…) typed into a Gregorian
#: field — a mistake that is otherwise invisible until the date is displayed.
MIN_CYCLE_GREGORIAN_YEAR = 1900


# -- Why a rater's weight moved -------------------------------------------------
# Codes, not sentences: the appraisal is read in Persian, and the domain layer
# has no business choosing wording. The UI translates these; anything appended
# after a colon is a percentage the UI interpolates.
REASON_FULL_WEIGHT = "fullWeight"
REASON_DAMPED_ABOVE = "dampedAbove"
REASON_DAMPED_BELOW = "dampedBelow"
REASON_UNRELIABLE = "unreliable"
REASON_CODES = (
    REASON_FULL_WEIGHT,
    REASON_DAMPED_ABOVE,
    REASON_DAMPED_BELOW,
    REASON_UNRELIABLE,
)

# -- rater roles ------------------------------------------------------------
ROLE_TECHNICAL_MANAGER = "technicalManager"
ROLE_PRODUCTION_MANAGER = "productionManager"
ROLE_UNIT_HEAD = "unitHead"
ROLE_UNIT_SUPERVISOR = "unitSupervisor"
ROLE_QA_MANAGER = "qaManager"
ROLE_HSE_UNIT = "hseUnit"
ROLE_HR_MANAGER = "hrManager"
ROLE_LAB_MANAGER = "labManager"
ROLE_PLANNING_MANAGER = "planningManager"
ROLE_WAREHOUSE_MANAGER = "warehouseManager"

RATER_ROLES = (
    ROLE_TECHNICAL_MANAGER,
    ROLE_PRODUCTION_MANAGER,
    ROLE_UNIT_HEAD,
    ROLE_UNIT_SUPERVISOR,
    ROLE_QA_MANAGER,
    ROLE_HSE_UNIT,
    ROLE_HR_MANAGER,
    ROLE_LAB_MANAGER,
    ROLE_PLANNING_MANAGER,
    ROLE_WAREHOUSE_MANAGER,
)

# Relative, not percentages — they are renormalised over whoever actually
# rated, so a missing rater never silently shrinks someone's total. The
# ordering reflects proximity to the technician's daily work: the people who
# watch the work happen outrank the people who see its paperwork.
DEFAULT_ROLE_WEIGHTS: dict[str, int] = {
    ROLE_TECHNICAL_MANAGER: 18,
    ROLE_UNIT_HEAD: 16,
    ROLE_PRODUCTION_MANAGER: 14,
    ROLE_UNIT_SUPERVISOR: 14,
    ROLE_QA_MANAGER: 9,
    ROLE_HSE_UNIT: 9,
    ROLE_HR_MANAGER: 8,
    ROLE_LAB_MANAGER: 5,
    ROLE_PLANNING_MANAGER: 5,
    ROLE_WAREHOUSE_MANAGER: 4,
}

# -- system score -----------------------------------------------------------
# Share of the final mark that comes from measured work rather than opinion.
# 30 is deliberate: high enough that the record matters, low enough that a
# technician assigned nothing but easy jobs cannot coast on statistics.
DEFAULT_SYSTEM_WEIGHT_PERCENT = 30
MIN_SYSTEM_WEIGHT_PERCENT = 0
MAX_SYSTEM_WEIGHT_PERCENT = 100

# What the measured half is built from, and how much each part counts.
SYSTEM_METRIC_WEIGHTS: dict[str, int] = {
    "pmCompliance": 35,  # PM executions finished on time ÷ PM executions due
    "onTimeCompletion": 30,  # work orders closed by their due date
    "completionRate": 20,  # assigned work actually finished
    "reworkPenalty": 15,  # repeat failures on a device this person just fixed
}

# -- bias damping -----------------------------------------------------------
# Below this many human raters there is no consensus to measure a rater
# against, so damping is switched off entirely rather than guessed at. With
# three scores the median is one person's opinion and the spread is noise;
# damping there would amplify bias instead of removing it.
MIN_RATERS_FOR_DAMPING = 4

# How far from the consensus a rater may sit before their weight starts to
# fall, measured in robust standard deviations. 1.5 keeps honest disagreement
# intact — the goal is to damp the score that is out on its own, not to punish
# anyone who fails to match the median exactly.
DEFAULT_DAMPING_TOLERANCE = 1.5

# A damped rater never vanishes completely. Silencing a dissenter outright
# would make the engine impossible to audit and would let a colluding
# majority erase the one honest rater, so the floor keeps every voice in.
MIN_DAMPING_FACTOR = 0.15

# Scales a median absolute deviation to the standard deviation of a normal
# distribution, so the tolerance above can be read in familiar units.
MAD_TO_SIGMA = 1.4826

# With an unusually tight consensus the MAD collapses toward zero and every
# ordinary disagreement looks like an outlier. The floor stops a two-point
# difference from being treated as a scandal.
MIN_SPREAD = 4.0

# -- rater reliability (learned across cycles) ------------------------------
# A rater who is repeatedly far from the consensus loses standing over time,
# independently of any single cycle. New raters start at full trust: suspicion
# has to be earned by evidence, not assumed.
DEFAULT_RELIABILITY = 1.0
MIN_RELIABILITY = 0.40
# How many past cycles of history are needed before reliability moves at all.
MIN_CYCLES_FOR_RELIABILITY = 2
