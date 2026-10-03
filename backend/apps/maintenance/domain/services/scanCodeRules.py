"""Scanned text → what the technician actually pointed the camera at.

A label in the field is never just a UUID. It can be:

* the QR this system prints — an absolute deep link
  (``https://plant.local/app/maintenance/devices/<uuid>/profile``);
* the same link relative, if the QR was produced by an older build;
* a bare UUID, when the label was printed by a label writer;
* the plant's own business code (``PUMP-204``), printed as Code 128 — the
  most common case on equipment that already had labels before this system;
* a vendor's serial number sticker, scanned as EAN/Code 39.

So the parser's job is to classify, not to validate: it returns *what to look
up and how*, and the repository decides whether anything matches. Guessing
wrong here is cheap (a 404); refusing to parse is expensive (a technician
standing at a machine, unable to open it).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    SCAN_TARGET_DEVICE,
    SCAN_TARGET_LOCATION,
    SCAN_TARGET_SPARE_PART,
    SCAN_TARGET_WORK_ORDER,
)

#: Deep links this system prints. The ``app/`` prefix is optional because the
#: router mounts the same pages with and without it in demo mode.
_DEVICE_LINK = re.compile(
    r"/(?:app/)?maintenance/devices/(?P<id>[0-9a-fA-F-]{8,36})(?:/|$|\?|#)"
)
_WORK_ORDER_LINK = re.compile(
    r"/(?:app/)?maintenance/work-orders/(?P<id>[0-9a-fA-F-]{8,36})(?:/|$|\?|#)"
)
_PART_LINK = re.compile(
    r"/(?:app/)?maintenance/spare-parts/(?P<id>[0-9a-fA-F-]{8,36})(?:/|$|\?|#)"
)
_LOCATION_LINK = re.compile(
    r"/(?:app/)?maintenance/locations/(?P<id>[0-9a-fA-F-]{8,36})(?:/|$|\?|#)"
)

#: ``tekarai://device/<id>`` — the compact form for 1D symbologies that cannot
#: carry a whole URL without becoming a 30 cm barcode.
_SCHEME = re.compile(
    r"^tekarai://(?P<kind>device|work-?order|part|sparepart|location)/(?P<id>[^/?#]+)$",
    re.IGNORECASE,
)

_PREFIX_TO_KIND = {
    "device": SCAN_TARGET_DEVICE,
    "workorder": SCAN_TARGET_WORK_ORDER,
    "work-order": SCAN_TARGET_WORK_ORDER,
    "part": SCAN_TARGET_SPARE_PART,
    "sparepart": SCAN_TARGET_SPARE_PART,
    "location": SCAN_TARGET_LOCATION,
}

#: Printed business codes are upper-case ASCII with dashes/dots/underscores.
#: Anything with whitespace or Persian text is a human typing a name, not a
#: scanner — those go to the search path, not the code path.
_BUSINESS_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-/]{1,59}$")

MAX_SCAN_LENGTH = 512


@dataclass(frozen=True)
class ScanIntent:
    """How to resolve a scan: by id, by business code, or not at all."""

    #: ``""`` means "unknown — try every kind in priority order".
    kind: str
    #: Parsed UUID when the text carried one.
    entityId: uuid.UUID | None
    #: Normalised business code when the text carried one.
    code: str
    raw: str

    @property
    def isEmpty(self) -> bool:
        return self.entityId is None and not self.code


def _asUuid(text: str) -> uuid.UUID | None:
    candidate = text.strip().strip("{}")
    try:
        return uuid.UUID(candidate)
    except (ValueError, AttributeError, TypeError):
        return None


def parseScan(text: str) -> ScanIntent:
    """Classify scanned (or typed) text. Never raises — empty intent instead."""
    raw = (text or "").strip()
    if not raw or len(raw) > MAX_SCAN_LENGTH:
        return ScanIntent(kind="", entityId=None, code="", raw=raw)

    scheme = _SCHEME.match(raw)
    if scheme:
        kind = _PREFIX_TO_KIND[scheme.group("kind").lower().replace("_", "-")]
        identifier = scheme.group("id")
        parsed = _asUuid(identifier)
        return ScanIntent(
            kind=kind,
            entityId=parsed,
            code="" if parsed else identifier.strip().upper(),
            raw=raw,
        )

    for pattern, kind in (
        (_DEVICE_LINK, SCAN_TARGET_DEVICE),
        (_WORK_ORDER_LINK, SCAN_TARGET_WORK_ORDER),
        (_PART_LINK, SCAN_TARGET_SPARE_PART),
        (_LOCATION_LINK, SCAN_TARGET_LOCATION),
    ):
        match = pattern.search(raw)
        if match:
            parsed = _asUuid(match.group("id"))
            if parsed is not None:
                return ScanIntent(kind=kind, entityId=parsed, code="", raw=raw)

    bare = _asUuid(raw)
    if bare is not None:
        # A naked UUID: the kind is unknown, the repository probes each table.
        return ScanIntent(kind="", entityId=bare, code="", raw=raw)

    if _BUSINESS_CODE.match(raw):
        return ScanIntent(kind="", entityId=None, code=raw.strip().upper(), raw=raw)

    return ScanIntent(kind="", entityId=None, code="", raw=raw)


__all__ = ["MAX_SCAN_LENGTH", "ScanIntent", "parseScan"]
