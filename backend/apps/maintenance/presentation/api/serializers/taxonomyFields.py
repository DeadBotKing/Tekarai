"""Open vocabularies — a canonical catalogue plus operator-defined values.

Phase 26.1. The registry dropdowns (location kind, PM discipline, personnel
specialty, assignment role, criticality) ship with a canonical catalogue, but a
plant always has a word of its own: a hall the operators call «سوله», a
discipline named «جوشکاری». Forcing those into "other" destroys the reporting
value, so the field accepts any short, printable label and stores it verbatim.

What stays enforced:

* a value is non-empty once trimmed;
* inner whitespace is collapsed, so «سوله   ۳» and «سوله ۳» are one value;
* no control characters (they break CSV/Excel exports);
* the length fits the database column;
* a case-insensitive match against the canonical catalogue is snapped back to
  the canonical code, so "Site" never becomes a second entry next to "site".
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rest_framework import serializers

#: C0/C1 control characters — never legitimate inside a label.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class OpenVocabularyField(serializers.CharField):
    """A ``CharField`` that prefers canonical codes but accepts new labels."""

    def __init__(self, canonical: Iterable[str] = (), **kwargs: object) -> None:
        self.canonical: tuple[str, ...] = tuple(canonical)
        kwargs.setdefault("max_length", 24)
        kwargs.setdefault("trim_whitespace", True)
        super().__init__(**kwargs)  # type: ignore[arg-type]

    def to_internal_value(self, data: object) -> str:
        value = super().to_internal_value(data)
        value = " ".join(value.split())
        if not value:
            if self.allow_blank:
                return ""
            self.fail("blank")
        if CONTROL_CHARACTERS.search(value):
            raise serializers.ValidationError(
                "Value must not contain control characters.",
            )
        lowered = value.casefold()
        for code in self.canonical:
            if code.casefold() == lowered:
                return code
        return value


def openVocabulary(
    canonical: Iterable[str],
    *,
    maxLength: int = 24,
    default: str | None = None,
    required: bool = True,
    allowBlank: bool = False,
) -> OpenVocabularyField:
    """Build an :class:`OpenVocabularyField` with the usual registry defaults."""

    options: dict[str, object] = {"max_length": maxLength, "allow_blank": allowBlank}
    if default is not None:
        options["default"] = default
        options["required"] = False
    else:
        options["required"] = required
    return OpenVocabularyField(canonical, **options)
