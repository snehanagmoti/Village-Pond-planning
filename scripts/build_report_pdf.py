"""Render Final_Technical_Report.md as a polished, linked A4 PDF."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Final_Technical_Report.md"
OUTPUT = ROOT / "output" / "pdf" / "Village_Pond_Planning_Final_Technical_Report.pdf"

NAVY = colors.HexColor("#0B1F33")
BLUE = colors.HexColor("#0B6E99")
CYAN = colors.HexColor("#27A8C7")
PALE = colors.HexColor("#EAF5F8")
INK = colors.HexColor("#172331")
MUTED = colors.HexColor("#526272")
LINE = colors.HexColor("#CAD8E0")
WHITE = colors.white


def register_fonts() -> tuple[str, str, str]:
    candidates = [
        Path("C:/Windows/Fonts/aptos.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/aptosbd.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ]
    mono_candidates = [
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("C:/Windows/Fonts/cour.ttf"),
    ]
    regular = next((path for path in candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    mono = next((path for path in mono_candidates if path.exists()), None)
    if regular and bold:
        pdfmetrics.registerFont(TTFont("ReportSans", str(regular)))
        pdfmetrics.registerFont(TTFont("ReportSans-Bold", str(bold)))
        pdfmetrics.registerFontFamily(
            "ReportSans",
            normal="ReportSans",
            bold="ReportSans-Bold",
        )
        regular_name, bold_name = "ReportSans", "ReportSans-Bold"
    else:
        regular_name, bold_name = "Helvetica", "Helvetica-Bold"
    if mono:
        pdfmetrics.registerFont(TTFont("ReportMono", str(mono)))
        mono_name = "ReportMono"
    else:
        mono_name = "Courier"
    return regular_name, bold_name, mono_name


REGULAR, BOLD, MONO = register_fonts()


def inline_markup(value: str) -> str:
    text = escape(value.strip())
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(
        r"`([^`]+)`",
        rf'<font name="{MONO}" size="8.2">\1</font>',
        text,
    )
    text = re.sub(
        r"(?<![\"'=])(https?://[^\s<]+)",
        r'<link href="\1" color="#0B6E99">\1</link>',
        text,
    )
    return text


def report_styles():
    base = getSampleStyleSheet()
    body = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontName=REGULAR,
        fontSize=9.1,
        leading=12.1,
        textColor=INK,
        spaceAfter=6,
        alignment=TA_LEFT,
        allowWidows=0,
        allowOrphans=0,
    )
    return {
        "body": body,
        "small": ParagraphStyle(
            "Small",
            parent=body,
            fontSize=7.8,
            leading=10.2,
            textColor=MUTED,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=body,
            fontName=BOLD,
            fontSize=7.8,
            leading=10.2,
            textColor=WHITE,
        ),
        "h1": ParagraphStyle(
            "Heading1",
            parent=base["Heading1"],
            fontName=BOLD,
            fontSize=15.2,
            leading=18,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "Heading2",
            parent=base["Heading2"],
            fontName=BOLD,
            fontSize=11.2,
            leading=14,
            textColor=BLUE,
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "Heading3",
            parent=base["Heading3"],
            fontName=BOLD,
            fontSize=9.6,
            leading=12,
            textColor=INK,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontName=BOLD,
            fontSize=28,
            leading=32,
            textColor=WHITE,
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "cover_subtitle": ParagraphStyle(
            "CoverSubtitle",
            parent=body,
            fontName=REGULAR,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#D9F2F7"),
        ),
        "cover_meta": ParagraphStyle(
            "CoverMeta",
            parent=body,
            fontSize=10.5,
            leading=15,
            textColor=INK,
        ),
        "toc_title": ParagraphStyle(
            "TocTitle",
            parent=base["Title"],
            fontName=BOLD,
            fontSize=21,
            leading=25,
            textColor=NAVY,
            alignment=TA_LEFT,
            spaceAfter=14,
        ),
        "code": ParagraphStyle(
            "Code",
            parent=base["Code"],
            fontName=MONO,
            fontSize=7.5,
            leading=9.5,
            textColor=INK,
            leftIndent=7,
            rightIndent=7,
            borderColor=LINE,
            borderWidth=0.5,
            borderPadding=7,
            backColor=colors.HexColor("#F4F8FA"),
            spaceBefore=3,
            spaceAfter=8,
        ),
    }


STYLES = report_styles()


class ReportDocument(BaseDocTemplate):
    def __init__(self, filename: str):
        super().__init__(
            filename,
            pagesize=A4,
            rightMargin=17 * mm,
            leftMargin=17 * mm,
            topMargin=20 * mm,
            bottomMargin=18 * mm,
            title="AI-based Village Pond Planning System - Final Technical Report",
            author="Sneha Nagmoti",
            subject="Assignment 1 final technical report",
            creator="Village Pond Planning report generator",
        )
        content_frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="content",
        )
        full_frame = Frame(0, 0, A4[0], A4[1], leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="cover")
        self.addPageTemplates(
            [
                PageTemplate(id="Cover", frames=[full_frame], onPage=draw_cover_page),
                PageTemplate(id="Content", frames=[content_frame], onPage=draw_content_page),
            ]
        )

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in {"Heading1", "Heading2"}:
            level = 0 if flowable.style.name == "Heading1" else 1
            title = flowable.getPlainText()
            key = f"section-{self.seq.nextf('section')}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=level, closed=False)
            self.notify("TOCEntry", (level, title, self.page, key))


def draw_cover_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, width, height, stroke=0, fill=1)
    canvas.setFillColor(BLUE)
    canvas.rect(0, height - 20 * mm, width, 20 * mm, stroke=0, fill=1)
    canvas.setFillColor(CYAN)
    canvas.circle(width - 28 * mm, height - 62 * mm, 22 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.HexColor("#16415C"))
    canvas.circle(width - 15 * mm, height - 83 * mm, 13 * mm, stroke=0, fill=1)
    canvas.setStrokeColor(colors.HexColor("#2B536D"))
    canvas.setLineWidth(0.6)
    for offset in range(0, 8):
        y = 28 * mm + offset * 7 * mm
        canvas.bezier(0, y, 45 * mm, y + 10 * mm, 105 * mm, y - 8 * mm, width, y + 4 * mm)
    canvas.restoreState()


def draw_content_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(CYAN)
    canvas.setLineWidth(1.2)
    canvas.line(doc.leftMargin, height - 13 * mm, width - doc.rightMargin, height - 13 * mm)
    canvas.setFont(BOLD, 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, height - 10 * mm, "AI-BASED VILLAGE POND PLANNING SYSTEM")
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(doc.leftMargin, 12 * mm, width - doc.rightMargin, 12 * mm)
    canvas.setFont(REGULAR, 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 8 * mm, "Screening prototype - field and engineering verification required")
    canvas.drawRightString(width - doc.rightMargin, 8 * mm, f"Page {doc.page}")
    canvas.restoreState()


def cover_story():
    title_box = Table(
        [[
            Paragraph("AI-based Village Pond<br/>Planning System", STYLES["cover_title"]),
        ]],
        colWidths=[136 * mm],
    )
    title_box.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    meta = Table(
        [
            [Paragraph("FINAL TECHNICAL REPORT", STYLES["h2"])],
            [Paragraph("Assignment 1 | Phase 3 submission", STYLES["cover_meta"])],
            [Paragraph("Student: <b>Sneha Nagmoti</b>", STYLES["cover_meta"])],
            [Paragraph("Date: 28 August 2026", STYLES["cover_meta"])],
            [Paragraph("github.com/snehanagmoti/Village-Pond-planning", STYLES["cover_meta"])],
        ],
        colWidths=[136 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F8FA")),
                ("BOX", (0, 0), (-1, -1), 0.8, CYAN),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return [
        Spacer(1, 74 * mm),
        Table([[title_box]], colWidths=[A4[0] - 50 * mm], hAlign="LEFT", style=[("LEFTPADDING", (0, 0), (-1, -1), 25 * mm)]),
        Spacer(1, 23 * mm),
        Table([[meta]], colWidths=[A4[0] - 50 * mm], hAlign="LEFT", style=[("LEFTPADDING", (0, 0), (-1, -1), 25 * mm)]),
        NextPageTemplate("Content"),
        PageBreak(),
    ]


def table_from_rows(rows: list[list[str]], available_width: float):
    column_count = max(len(row) for row in rows)
    normalized = [row + [""] * (column_count - len(row)) for row in rows]
    paragraph_rows = []
    for row_index, row in enumerate(normalized):
        style = STYLES["table_header"] if row_index == 0 else STYLES["small"]
        paragraph_rows.append([Paragraph(inline_markup(cell), style) for cell in row])
    if column_count == 2:
        first_share = 0.34 if len(rows) > 8 else 0.42
        widths = [available_width * first_share, available_width * (1 - first_share)]
    else:
        widths = [available_width / column_count] * column_count
    table = Table(paragraph_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BLUE),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), BOLD),
                ("GRID", (0, 0), (-1, -1), 0.45, LINE),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F5F9FA")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def parse_markdown(text: str, available_width: float):
    lines = text.splitlines()
    start = next((index for index, line in enumerate(lines) if line.startswith("## 1. ")), 0)
    lines = lines[start:]
    story = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            story.append(Preformatted("\n".join(code_lines), STYLES["code"]))
            index += 1
            continue
        if line.startswith("|") and index + 1 < len(lines) and re.match(r"^\|?\s*:?-+", lines[index + 1]):
            rows = []
            rows.append([cell.strip() for cell in line.strip("|").split("|")])
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append([cell.strip() for cell in lines[index].strip().strip("|").split("|")])
                index += 1
            story.append(table_from_rows(rows, available_width))
            story.append(Spacer(1, 7))
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1)) - 1
            title = heading.group(2)
            if level == 1 and title.startswith("12. "):
                story.append(PageBreak())
            style = STYLES[{1: "h1", 2: "h2", 3: "h3"}.get(level, "h3")]
            story.append(Paragraph(inline_markup(title), style))
            index += 1
            continue
        if re.match(r"^\d+\.\s+", line):
            items = []
            while index < len(lines) and re.match(r"^\d+\.\s+", lines[index].strip()):
                value = re.sub(r"^\d+\.\s+", "", lines[index].strip())
                index += 1
                while index < len(lines):
                    continuation = lines[index].strip()
                    if not continuation or re.match(r"^\d+\.\s+", continuation):
                        break
                    if continuation.startswith(("#", "```", "|", "- ")):
                        break
                    value += " " + continuation
                    index += 1
                items.append(ListItem(Paragraph(inline_markup(value), STYLES["body"]), leftIndent=14))
            story.append(ListFlowable(items, bulletType="1", start="1", leftIndent=18, bulletFontName=BOLD, bulletFontSize=8.5, spaceAfter=6))
            continue
        if line.lstrip().startswith("- "):
            items = []
            while index < len(lines) and lines[index].lstrip().startswith("- "):
                value = lines[index].lstrip()[2:]
                items.append(ListItem(Paragraph(inline_markup(value), STYLES["body"]), leftIndent=12))
                index += 1
            story.append(ListFlowable(items, bulletType="bullet", bulletChar="-", leftIndent=17, bulletFontName=BOLD, bulletFontSize=8, spaceAfter=6))
            continue
        paragraph_lines = [line.strip()]
        index += 1
        while index < len(lines):
            candidate = lines[index].rstrip()
            if not candidate:
                break
            if candidate.startswith(("##", "```", "|")) or candidate.lstrip().startswith("- ") or re.match(r"^\d+\.\s+", candidate.strip()):
                break
            paragraph_lines.append(candidate.strip())
            index += 1
        paragraph_text = " ".join(paragraph_lines)
        if paragraph_text.startswith("`") and paragraph_text.endswith("`") and paragraph_text.count("`") == 2:
            story.append(
                KeepTogether(
                    [
                        Table(
                            [[Paragraph(inline_markup(paragraph_text), STYLES["body"])]],
                            colWidths=[available_width],
                            style=TableStyle(
                                [
                                    ("BACKGROUND", (0, 0), (-1, -1), PALE),
                                    ("BOX", (0, 0), (-1, -1), 0.7, CYAN),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                                ]
                            ),
                        )
                    ]
                )
            )
            story.append(Spacer(1, 5))
        else:
            story.append(Paragraph(inline_markup(paragraph_text), STYLES["body"]))
    return story


def build_report():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = ReportDocument(str(OUTPUT))
    story = cover_story()
    story.append(Paragraph("Contents", STYLES["toc_title"]))
    toc = TableOfContents()
    toc.levelStyles = [
        ParagraphStyle(
            "TOC1",
            fontName=BOLD,
            fontSize=9.3,
            leading=12,
            leftIndent=0,
            firstLineIndent=0,
            textColor=NAVY,
            spaceBefore=3,
        ),
        ParagraphStyle(
            "TOC2",
            fontName=REGULAR,
            fontSize=8.3,
            leading=10.5,
            leftIndent=12,
            firstLineIndent=0,
            textColor=MUTED,
        ),
    ]
    story.extend([toc, PageBreak()])
    story.extend(parse_markdown(SOURCE.read_text(encoding="utf-8"), document.width))
    document.multiBuild(story)
    print(f"Created {OUTPUT}")


if __name__ == "__main__":
    build_report()
