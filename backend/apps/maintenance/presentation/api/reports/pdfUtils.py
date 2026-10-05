"""Shared Persian-aware PDF helpers for maintenance report exports.

reportlab draws glyphs left-to-right with no shaping engine, so every piece of
Persian text must go through ``arabic_reshaper`` (glyph joins) and
``python-bidi`` (visual ordering) before it is drawn. Tables are built RTL by
reversing the column order. The bundled Vazirmatn TTFs keep rendering identical
on every machine (no system-font dependency).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONTS_DIR = Path(__file__).resolve().with_name("fonts")
_registered = False

FONT = "Vazirmatn"
FONT_BOLD = "Vazirmatn-Bold"

INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#5f6b7d")
HAIR = colors.HexColor("#e4e9f1")
HEADER_BG = colors.HexColor("#155cda")
STRIPE = colors.HexColor("#f4f7fc")


def registerFonts() -> None:
    global _registered
    if _registered:
        return
    pdfmetrics.registerFont(TTFont(FONT, str(_FONTS_DIR / "Vazirmatn-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(_FONTS_DIR / "Vazirmatn-Bold.ttf")))
    _registered = True


def fa(value: object) -> str:
    """Shape + bidi-order one cell/heading of Persian text."""
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(text))


def _styles() -> tuple[ParagraphStyle, ParagraphStyle, ParagraphStyle, ParagraphStyle]:
    title = ParagraphStyle(
        "faTitle",
        fontName=FONT_BOLD,
        fontSize=15,
        leading=21,
        alignment=2,
        textColor=INK,
    )
    subtitle = ParagraphStyle(
        "faSubtitle",
        fontName=FONT,
        fontSize=9.5,
        leading=14,
        alignment=2,
        textColor=MUTED,
    )
    header = ParagraphStyle(
        "faHeader",
        fontName=FONT_BOLD,
        fontSize=8.5,
        leading=12,
        alignment=2,
        textColor=colors.white,
    )
    cell = ParagraphStyle(
        "faCell",
        fontName=FONT,
        fontSize=8,
        leading=12,
        alignment=2,
        textColor=INK,
    )
    return title, subtitle, header, cell


def buildPersianTablePdf(
    *,
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    subtitle: str = "",
    wide: bool | None = None,
) -> bytes:
    """Render a single RTL data table as a polished A4 PDF.

    ``wide`` forces landscape orientation; when omitted it is chosen
    automatically from the column count.
    """
    registerFonts()
    titleStyle, subtitleStyle, headerStyle, cellStyle = _styles()
    if wide is None:
        wide = len(columns) > 7
    pageSize = landscape(A4) if wide else A4
    margin = 12 * mm

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=pageSize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=title,
        author="Tekarai",
        rtl=True,
    )

    story: list = [Paragraph(fa(title), titleStyle)]
    if subtitle:
        story.append(Paragraph(fa(subtitle), subtitleStyle))
    story.append(Spacer(1, 6 * mm))

    # RTL reading means the *first* column belongs on the rightmost side.
    tableData: list[list[Paragraph]] = [
        [Paragraph(fa(col), headerStyle) for col in reversed(columns)]
    ]
    for row in rows:
        tableData.append([Paragraph(fa(value), cellStyle) for value in reversed(row)])

    usable = doc.width
    colCount = max(len(columns), 1)
    table = Table(
        tableData,
        colWidths=[usable / colCount] * colCount,
        repeatRows=1,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
                ("GRID", (0, 0), (-1, -1), 0.4, HAIR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    0.8,
                    colors.HexColor("#0f47ad"),
                ),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def buildPersianInfoGrid(headerPairs: list[tuple[str, object]], columns: int = 2) -> Table:
    """Small label/value grid (device info blocks) drawn right-to-left."""
    registerFonts()
    _, _, _, cellStyle = _styles()
    labelStyle = ParagraphStyle(
        "faLabel", parent=cellStyle, fontName=FONT_BOLD, textColor=MUTED, fontSize=7.5
    )
    cells: list[Paragraph] = []
    for label, value in headerPairs:
        cells.append(Paragraph(fa(label), labelStyle))
        cells.append(Paragraph(fa(value), cellStyle))
    rowSpan = columns * 2
    dataRows = [cells[i : i + rowSpan] for i in range(0, len(cells), rowSpan)]
    for row in dataRows:
        while len(row) < rowSpan:
            row.append(Paragraph("", cellStyle))
        row.reverse()
    colCount = rowSpan
    width = 210 * mm - 24 * mm
    tableWidth = width
    table = Table(
        dataRows,
        colWidths=[tableWidth / colCount] * colCount,
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fbfcfe")),
                ("BOX", (0, 0), (-1, -1), 0.6, HAIR),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, HAIR),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table
