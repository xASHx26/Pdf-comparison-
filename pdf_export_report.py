"""
pdf_export_report.py
--------------------
Generates a highlighted PDF comparison report using reportlab.

Each difference is shown as a two-column side-by-side table row:
  - Red   background → DATA_MISMATCH / MISSING / EXTRA
  - Yellow background → FORMAT_DIFF / LABEL_DIFF
  - Green  background → matching lines (when show_matches=True)

Bordered boxes are drawn around each difference block for easy scanning.
"""

import os
from datetime import datetime
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG_HEADER   = colors.HexColor("#0f3460")
C_BG_DATA     = colors.HexColor("#fdecea")   # light red
C_BG_FORMAT   = colors.HexColor("#fff8e1")   # light yellow
C_BG_MATCH    = colors.HexColor("#e8f5e9")   # light green
C_BG_ROW_HDR  = colors.HexColor("#1a1a2e")
C_BORDER_DATA = colors.HexColor("#ef5350")
C_BORDER_FMT  = colors.HexColor("#ffc107")
C_BORDER_OK   = colors.HexColor("#4caf50")
C_TEXT_DARK   = colors.HexColor("#1a1a2e")
C_TEXT_LIGHT  = colors.HexColor("#ffffff")
C_TEXT_MUTED  = colors.HexColor("#546e7a")
C_STRIPE_EVEN = colors.HexColor("#f9f9fb")
C_STRIPE_ODD  = colors.HexColor("#ffffff")

# ── Type labels ───────────────────────────────────────────────────────────────
_TYPE_LABEL = {
    "DATA_MISMATCH": "DATA MISMATCH",
    "MISSING_IN_B":  "MISSING IN PDF-B",
    "EXTRA_IN_B":    "EXTRA IN PDF-B",
    "FORMAT_DIFF":   "FORMAT DIFFERENCE",
    "LABEL_DIFF":    "LABEL DIFFERENCE",
}

_CATEGORY_COLORS = {
    "DATA":   (C_BG_DATA,   C_BORDER_DATA),
    "FORMAT": (C_BG_FORMAT, C_BORDER_FMT),
}


# ─────────────────────────────────────────────────────────────────────────────
# Style helpers
# ─────────────────────────────────────────────────────────────────────────────

def _styles():
    base = getSampleStyleSheet()

    def _s(name, **kw) -> ParagraphStyle:
        return ParagraphStyle(name, **kw)

    return {
        "title": _s("rpt_title",
                    fontName="Helvetica-Bold",
                    fontSize=18, textColor=C_TEXT_LIGHT,
                    alignment=TA_CENTER, spaceAfter=4),
        "subtitle": _s("rpt_sub",
                       fontName="Helvetica",
                       fontSize=9, textColor=colors.HexColor("#90caf9"),
                       alignment=TA_CENTER, spaceAfter=0),
        "meta": _s("rpt_meta",
                   fontName="Helvetica",
                   fontSize=9, textColor=C_TEXT_MUTED,
                   spaceAfter=2),
        "section": _s("rpt_sec",
                      fontName="Helvetica-Bold",
                      fontSize=11, textColor=C_BG_HEADER,
                      spaceBefore=12, spaceAfter=4),
        "cell": _s("rpt_cell",
                   fontName="Helvetica",
                   fontSize=8, textColor=C_TEXT_DARK,
                   leading=11, wordWrap="CJK"),
        "cell_miss": _s("rpt_cell_miss",
                        fontName="Helvetica-Oblique",
                        fontSize=8, textColor=C_TEXT_MUTED,
                        leading=11),
        "badge": _s("rpt_badge",
                    fontName="Helvetica-Bold",
                    fontSize=7, textColor=C_TEXT_LIGHT,
                    alignment=TA_CENTER),
        "summary_val": _s("rpt_sumval",
                          fontName="Helvetica-Bold",
                          fontSize=12, textColor=C_TEXT_DARK,
                          alignment=TA_CENTER),
        "summary_lbl": _s("rpt_sumlbl",
                          fontName="Helvetica",
                          fontSize=8, textColor=C_TEXT_MUTED,
                          alignment=TA_CENTER),
    }


def _para(text: str, style: ParagraphStyle) -> Paragraph:
    """Safe paragraph — escapes < > & for reportlab."""
    safe = (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))
    return Paragraph(safe, style)


# ─────────────────────────────────────────────────────────────────────────────
# Header banner
# ─────────────────────────────────────────────────────────────────────────────

def _build_header(s, pdf_a: str, pdf_b: str, mode: str, now: str) -> list:
    content = []

    header_table = Table(
        [[
            _para("PDF COMPARISON REPORT", s["title"]),
        ]],
        colWidths=["100%"],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_BG_HEADER),
        ("TOPPADDING",  (0, 0), (-1, -1), 18),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
        ("ROUNDEDCORNERS", [6]),
    ]))
    content.append(header_table)
    content.append(Spacer(1, 4))

    subtitle_table = Table(
        [[
            _para(f"Generated: {now}  |  Mode: {mode.upper()}  |  "
                  f"A: {os.path.basename(pdf_a)}  |  B: {os.path.basename(pdf_b)}",
                  s["subtitle"]),
        ]],
        colWidths=["100%"],
    )
    subtitle_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_BG_HEADER),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("LEFTPADDING",  (0, 0), (-1, -1), 12),
    ]))
    content.append(subtitle_table)
    content.append(Spacer(1, 10))
    return content


# ─────────────────────────────────────────────────────────────────────────────
# Summary cards
# ─────────────────────────────────────────────────────────────────────────────

def _build_summary(s, diffs: list, mode: str) -> list:
    data_count   = sum(1 for d in diffs if d["category"] == "DATA")
    format_count = sum(1 for d in diffs if d["category"] == "FORMAT")
    total        = len(diffs)

    def _card(val, label, bg, fg=C_TEXT_DARK):
        return Table(
            [[_para(str(val), ParagraphStyle(
                "cv", fontName="Helvetica-Bold", fontSize=22,
                textColor=fg, alignment=TA_CENTER))],
             [_para(label, ParagraphStyle(
                "cl", fontName="Helvetica", fontSize=8,
                textColor=fg, alignment=TA_CENTER))]],
            colWidths=[4.5 * cm],
        ), bg

    cards = [
        ("Total Differences", total,  colors.HexColor("#e3eaf5"), C_TEXT_DARK),
        ("Data Differences",  data_count,  colors.HexColor("#fdecea"), C_BORDER_DATA),
    ]
    if mode == "full":
        cards.append(("Format Differences", format_count,
                       colors.HexColor("#fff8e1"), colors.HexColor("#f57f17")))

    card_cells = []
    for label, val, bg, fg in cards:
        t = Table(
            [[_para(str(val), ParagraphStyle("vcv", fontName="Helvetica-Bold",
                                             fontSize=22, textColor=fg,
                                             alignment=TA_CENTER))],
             [_para(label, ParagraphStyle("vcl", fontName="Helvetica",
                                          fontSize=8, textColor=fg,
                                          alignment=TA_CENTER))]],
            colWidths=[4.5 * cm],
        )
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("TOPPADDING",    (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("BOX",           (0, 0), (-1, -1), 1, fg),
            ("ROUNDEDCORNERS", [4]),
        ]))
        card_cells.append(t)

    row_table = Table([card_cells],
                      colWidths=[5 * cm] * len(card_cells),
                      hAlign="LEFT")
    row_table.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [_para("SUMMARY", s["section"]), row_table, Spacer(1, 12)]


# ─────────────────────────────────────────────────────────────────────────────
# Differences section
# ─────────────────────────────────────────────────────────────────────────────

def _badge(text: str, bg: colors.Color, s) -> Table:
    """Small coloured badge for the diff-type label."""
    t = Table([[_para(text, s["badge"])]], colWidths=[4.5 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [3]),
    ]))
    return t


def _build_differences(s, diffs: list, pdf_a: str, pdf_b: str) -> list:
    import os
    content: list = []

    if not diffs:
        no_diff = Table(
            [[_para("✔  No differences found between the two PDFs.", s["meta"])]],
            colWidths=["100%"],
        )
        no_diff.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_BG_MATCH),
            ("BOX",        (0, 0), (-1, -1), 1.5, C_BORDER_OK),
            ("TOPPADDING", (0, 0), (-1, -1), 14),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ]))
        content.append(no_diff)
        return content

    content.append(_para("DIFFERENCES", s["section"]))

    # column header row
    col_hdr = Table(
        [[
            _para("#", ParagraphStyle("ch", fontName="Helvetica-Bold",
                                      fontSize=8, textColor=C_TEXT_LIGHT,
                                      alignment=TA_CENTER)),
            _para("Type", ParagraphStyle("ch", fontName="Helvetica-Bold",
                                         fontSize=8, textColor=C_TEXT_LIGHT)),
            _para(f"PDF A (Reference): {os.path.basename(pdf_a)}", ParagraphStyle(
                "ch", fontName="Helvetica-Bold",
                fontSize=8, textColor=C_TEXT_LIGHT)),
            _para(f"PDF B (Comparison): {os.path.basename(pdf_b)}", ParagraphStyle(
                "ch", fontName="Helvetica-Bold",
                fontSize=8, textColor=C_TEXT_LIGHT)),
        ]],
        colWidths=[1.0 * cm, 4.5 * cm, 9.5 * cm, 9.5 * cm],
    )
    col_hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), C_BG_ROW_HDR),
        ("TOPPADDING",    (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    content.append(col_hdr)

    for i, d in enumerate(diffs):
        bg, border = _CATEGORY_COLORS.get(d["category"], (C_BG_DATA, C_BORDER_DATA))
        bg_stripe   = C_STRIPE_EVEN if i % 2 == 0 else C_STRIPE_ODD

        label   = _TYPE_LABEL.get(d["type"], d["type"])
        text_a  = d.get("line_a") or ""
        text_b  = d.get("line_b") or ""

        cell_a = (_para(text_a, s["cell"])
                  if text_a else _para("⟨ not present ⟩", s["cell_miss"]))
        cell_b = (_para(text_b, s["cell"])
                  if text_b else _para("⟨ not present ⟩", s["cell_miss"]))

        extra_lines = []
        if "similarity" in d:
            extra_lines.append(
                _para(f"Similarity: {d['similarity']}%", s["cell_miss"])
            )

        row_data = [[
            _para(str(i + 1), ParagraphStyle(
                "rn", fontName="Helvetica-Bold", fontSize=8,
                textColor=C_TEXT_MUTED, alignment=TA_CENTER)),
            _badge(label, border, s),
            cell_a,
            cell_b,
        ]]

        row_table = Table(
            row_data,
            colWidths=[1.0 * cm, 4.5 * cm, 9.5 * cm, 9.5 * cm],
        )
        row_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), bg),
            ("BACKGROUND",    (0, 0), (0, 0),   bg_stripe),   # # cell lighter
            ("BOX",           (0, 0), (-1, -1), 1.2, border),
            ("LINEBELOW",     (0, 0), (-1, -1), 0.5,
             colors.HexColor("#e0e0e0")),
            ("TOPPADDING",    (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("GRID",          (2, 0), (3, 0),   0.5,
             colors.HexColor("#e0e0e0")),
        ]))
        content.append(row_table)

        if extra_lines:
            extra_table = Table(
                [["", ""] + [e] for e in extra_lines],
                colWidths=[5.5 * cm, "*"],
            )
            extra_table.setStyle(TableStyle([
                ("BACKGROUND",  (0, 0), (-1, -1), bg),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("BOX",         (0, 0), (-1, -1), 1.2, border),
            ]))
            content.append(extra_table)

    return content


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def export_pdf_report(
    diffs: list,
    pdf_a: str,
    pdf_b: str,
    mode: str,
    output_path: Optional[str] = None,
) -> str:
    """
    Build a highlighted PDF comparison report and save it to *output_path*.
    If *output_path* is None, a timestamped name is generated in the current
    working directory.

    Returns the final file path.
    """
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"pdf_compare_{ts}_highlighted.pdf"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s   = _styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title="PDF Comparison Report",
        author="PDF Comparison Tool",
    )

    story = []
    story += _build_header(s, pdf_a, pdf_b, mode, now)
    story += _build_summary(s, diffs, mode)
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 6))
    story += _build_differences(s, diffs, pdf_a, pdf_b)

    # footer note
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5,
                             color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 4))
    story.append(_para(
        f"Generated by PDF Comparison Tool  •  {now}",
        ParagraphStyle("footer", fontName="Helvetica", fontSize=7,
                       textColor=C_TEXT_MUTED, alignment=TA_CENTER)
    ))

    doc.build(story)
    return output_path
