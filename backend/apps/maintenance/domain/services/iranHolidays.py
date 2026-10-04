"""Iran's official **solar** public holidays, as fixed Jalali month/day pairs.

Only the solar (Jalali-fixed) holidays live here, and that is deliberate. The
Iranian official calendar has two kinds of public holiday:

* **Solar** — pinned to a Jalali date (نوروز is always ۱ فروردین, پیروزی انقلاب
  always ۲۲ بهمن). These recur forever and can be computed, so they belong in
  code.
* **Lunar / Hijri qamari** — عاشورا, عید فطر, اربعین and the rest. These move
  roughly eleven days earlier against the solar year and their exact date is
  announced per year on moon sighting. They are *not* computable, so hardcoding
  them would be wrong by next year. They are entered per year from the
  holidays screen.

Shipping half the list with an honest boundary beats shipping a full list that
silently rots.

EVOLUTION NOTE (Phase 28.1): extracted from `seedDemo` so a real tenant can
load official holidays without also importing demo devices and locations.
"""

from __future__ import annotations

__all__ = ["IRAN_OFFICIAL_SOLAR_HOLIDAYS"]

# (jalaliMonth, jalaliDay, name)
IRAN_OFFICIAL_SOLAR_HOLIDAYS: tuple[tuple[int, int, str], ...] = (
    (1, 1, "نوروز"),
    (1, 2, "نوروز"),
    (1, 3, "نوروز"),
    (1, 4, "نوروز"),
    (1, 12, "روز جمهوری اسلامی"),
    (1, 13, "روز طبیعت"),
    (3, 14, "رحلت امام خمینی"),
    (3, 15, "قیام ۱۵ خرداد"),
    (11, 22, "پیروزی انقلاب اسلامی"),
    (12, 29, "ملی‌شدن صنعت نفت"),
)
