"""Render the markdown documents in docs/ to PDF (ReportLab, no external tools).

Supports the subset used by this project: headings, paragraphs, bold and italic
inline, bullet lists, pipe tables, images, horizontal rules and a leading
"key numbers" strip written as ``!!! label | value`` lines.
"""
from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, Image, ListFlowable,
                                ListItem, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

INK = colors.HexColor("#101418")
INK2 = colors.HexColor("#3c4855")
MUTED = colors.HexColor("#6b7683")
RULE = colors.HexColor("#d8dee4")
ACCENT = colors.HexColor("#1f5fa8")
POS = colors.HexColor("#0a7d0a")
NEG = colors.HexColor("#b8322f")


def _styles(base_size: float):
    s = base_size
    return {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=s + 6.5, leading=s + 8.5,
                             textColor=INK, spaceAfter=2),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=s + 1.2, leading=s + 3.4,
                             textColor=INK, spaceBefore=7, spaceAfter=2.5),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=s - 0.5, leading=s + 1.5,
                             textColor=ACCENT, spaceBefore=5, spaceAfter=1.5),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=s, leading=s * 1.40,
                               textColor=INK2, alignment=TA_LEFT, spaceAfter=3.5),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=s - 1.4, leading=s * 1.25,
                                textColor=MUTED, spaceAfter=2),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=s - 1.2, leading=s * 1.2, textColor=INK2),
        "cellh": ParagraphStyle("cellh", fontName="Helvetica-Bold", fontSize=s - 1.4, leading=s * 1.2, textColor=MUTED),
        "kpi_v": ParagraphStyle("kpi_v", fontName="Helvetica-Bold", fontSize=s + 4, leading=s + 5, textColor=INK),
        "kpi_l": ParagraphStyle("kpi_l", fontName="Helvetica", fontSize=s - 1.6, leading=s, textColor=MUTED),
    }


def _inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier">\1</font>', text)
    return text


def markdown_to_pdf(md_path: Path, pdf_path: Path, base_size: float = 8.6,
                    margin: float = 14 * mm, columns: int = 1, title: str | None = None,
                    footer: str = "ETF portfolio construction & risk attribution") -> Path:
    st = _styles(base_size)
    md = md_path.read_text(encoding="utf-8")
    flow: list = []
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("!!! "):                       # key-number strip
            cells, j = [], i
            while j < len(lines) and lines[j].startswith("!!! "):
                label, _, value = lines[j][4:].partition("|")
                cells.append((label.strip(), value.strip()))
                j += 1
            data = [[Paragraph(_inline(v), st["kpi_v"]) for _, v in cells],
                    [Paragraph(_inline(l), st["kpi_l"]) for l, _ in cells]]
            t = Table(data, colWidths=[None] * len(cells))
            t.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.5, RULE), ("LEFTPADDING", (1, 0), (-1, -1), 7),
            ]))
            flow += [t, Spacer(1, 5)]
            i = j
            continue
        if ln.startswith("|"):                          # table
            rows, j = [], i
            while j < len(lines) and lines[j].startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                j += 1
            head = [Paragraph(_inline(c), st["cellh"]) for c in rows[0]]
            body = [[Paragraph(_inline(c), st["cell"]) for c in r] for r in rows[1:]]
            t = Table([head] + body, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
                ("LINEBELOW", (0, 1), (-1, -2), 0.3, colors.HexColor("#edf0f3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]))
            flow += [Spacer(1, 2), t, Spacer(1, 5)]
            i = j
            continue
        if ln.startswith("- "):                         # bullets
            items, j = [], i
            while j < len(lines) and lines[j].startswith("- "):
                items.append(ListItem(Paragraph(_inline(lines[j][2:]), st["body"]), leftIndent=9))
                j += 1
            flow.append(ListFlowable(items, bulletType="bullet", start="•", bulletFontSize=base_size - 2,
                                     leftIndent=9, bulletOffsetY=-0.5))
            flow.append(Spacer(1, 2))
            i = j
            continue
        m = re.fullmatch(r"!\[(.*?)\]\((.+?)\)", ln.strip())
        if m:
            alt, _, scale = m.group(1).partition("|")     # ![caption|0.7](figures/x.png)
            path = (md_path.parent / m.group(2)).resolve()
            if path.exists():
                from PIL import Image as PILImage
                with PILImage.open(path) as im:
                    w, h = im.size
                avail = (A4[0] - 2 * margin) / columns * (float(scale) if scale else 1.0)
                flow += [Image(str(path), width=avail, height=avail * h / w, hAlign="LEFT")]
                if alt:
                    flow.append(Paragraph(_inline(alt), st["small"]))
                flow.append(Spacer(1, 4))
            i += 1
            continue
        if ln.startswith("---"):
            flow += [Spacer(1, 2), HRFlowable(width="100%", thickness=0.6, color=RULE), Spacer(1, 4)]
            i += 1
            continue
        if ln.startswith("### "):
            flow.append(Paragraph(_inline(ln[4:]), st["h3"]))
        elif ln.startswith("## "):
            flow.append(Paragraph(_inline(ln[3:]), st["h2"]))
        elif ln.startswith("# "):
            flow.append(Paragraph(_inline(ln[2:]), st["h1"]))
        elif ln.startswith("> "):
            flow.append(Paragraph(_inline(ln[2:]), st["small"]))
        elif ln.strip() == "<pagebreak>":
            flow.append(PageBreak())
        else:
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^[#\-|>!]", lines[i + 1]):
                i += 1
                para.append(lines[i])
            flow.append(Paragraph(_inline(" ".join(para)), st["body"]))
        i += 1

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(str(pdf_path), pagesize=A4, leftMargin=margin, rightMargin=margin,
                          topMargin=margin, bottomMargin=margin - 3 * mm,
                          title=title or md_path.stem.replace("_", " ").title(), author="Sasmitha Jayakody")
    width = (A4[0] - 2 * margin - (columns - 1) * 7 * mm) / columns
    frames = [Frame(margin + k * (width + 7 * mm), margin - 3 * mm, width,
                    A4[1] - 2 * margin + 3 * mm, id=f"c{k}", leftPadding=0, rightPadding=0,
                    topPadding=0, bottomPadding=0) for k in range(columns)]

    def draw_footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.6)
        canvas.setFillColor(MUTED)
        canvas.drawString(margin, margin - 6.5 * mm, footer)
        canvas.drawRightString(A4[0] - margin, margin - 6.5 * mm, f"page {canvas.getPageNumber()}")
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="body", frames=frames, onPage=draw_footer)])
    doc.build(flow)
    return pdf_path
