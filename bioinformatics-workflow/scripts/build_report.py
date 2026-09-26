#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["reportlab", "matplotlib"]
# ///
"""Build the cumulative stage report PDF for an analysis project.

Usage: build_report.py [--project-dir DIR] [--through N]

Reads analysis_checkpoint.json, then renders every completed stage file up to
stage N (default: the latest completed stage), plus the literature reviews
consulted, into reports/stage_0N_report.pdf. Figures come from the
![caption](path) images in the stage files, resolved relative to each file.

Each stage starts on its own page under a banner, with a running header naming
the stage and a PDF bookmark. Stages without figures are fine.

Prints the absolute PDF path on the last stdout line. Exits 2 if the PDF was
written but a stage or figure file it references is missing, so the caller
fixes it before presenting the report.
"""
import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import matplotlib
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, HRFlowable, Image, KeepTogether, PageBreak,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

# DejaVu ships with matplotlib and covers Greek/math symbols (Δ, β, ≥, →) that the
# built-in PDF fonts lack.
FONT_DIR = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
for name, file in [("Body", "DejaVuSans.ttf"), ("Body-Bold", "DejaVuSans-Bold.ttf"),
                   ("Body-Italic", "DejaVuSans-Oblique.ttf"),
                   ("Body-BoldItalic", "DejaVuSans-BoldOblique.ttf"),
                   ("Mono", "DejaVuSansMono.ttf")]:
    pdfmetrics.registerFont(TTFont(name, os.path.join(FONT_DIR, file)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold",
                              italic="Body-Italic", boldItalic="Body-BoldItalic")

BASE = getSampleStyleSheet()
STYLES = {
    "title": ParagraphStyle("t", parent=BASE["Title"], fontName="Body-Bold", fontSize=22, leading=27),
    "h1": ParagraphStyle("h1", parent=BASE["Heading1"], fontName="Body-Bold", fontSize=16, leading=20, spaceBefore=6, spaceAfter=8),
    "h2": ParagraphStyle("h2", parent=BASE["Heading2"], fontName="Body-Bold", fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4),
    "h3": ParagraphStyle("h3", parent=BASE["Heading3"], fontName="Body-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3),
    "p": ParagraphStyle("p", parent=BASE["BodyText"], fontName="Body", fontSize=9.5, leading=13.5, spaceAfter=5),
    "cell": ParagraphStyle("cell", parent=BASE["BodyText"], fontName="Body", fontSize=8, leading=10.5),
    "cellh": ParagraphStyle("cellh", parent=BASE["BodyText"], fontName="Body-Bold", fontSize=8, leading=10.5),
    "code": ParagraphStyle("code", parent=BASE["Code"], fontName="Mono", fontSize=7.5, leading=9.5,
                           backColor=colors.HexColor("#f3f4f6"), borderPadding=4, spaceAfter=8),
    "caption": ParagraphStyle("cap", parent=BASE["BodyText"], fontName="Body-Italic", fontSize=8.5, leading=11,
                              textColor=colors.HexColor("#444444"), spaceAfter=10),
    "quote": ParagraphStyle("q", parent=BASE["BodyText"], fontName="Body-Italic", fontSize=9.5, leading=13.5,
                            leftIndent=14, textColor=colors.HexColor("#444444")),
    "banner": ParagraphStyle("b", parent=BASE["BodyText"], fontName="Body-Bold", fontSize=20, leading=25,
                             textColor=colors.white),
    "banner_sub": ParagraphStyle("bs", parent=BASE["BodyText"], fontName="Body", fontSize=9, leading=12,
                                 textColor=colors.HexColor("#dbeafe")),
    "meta": ParagraphStyle("m", parent=BASE["BodyText"], fontName="Body", fontSize=10, leading=14, spaceAfter=6),
}

PAGE_W, PAGE_H = letter
MARGIN = 0.75 * inch
CONTENT_W = PAGE_W - 2 * MARGIN
CONTENT_H = PAGE_H - 2 * MARGIN


class SectionMarker(Flowable):
    """Zero-size flowable: sets the running-header label and adds a PDF bookmark."""

    def __init__(self, label, key):
        super().__init__()
        self.label, self.key = label, key
        self.width = self.height = 0

    def draw(self):
        self.canv._section_label = self.label
        self.canv.bookmarkPage(self.key)
        self.canv.addOutlineEntry(self.label, self.key, 0)


def stage_banner(stage, total):
    """Dark full-width band that opens each stage."""
    bits = [f"Status: {stage['status']}"]
    if stage.get("completed_at"):
        bits.append(f"completed {stage['completed_at']}")
    bits.append("plan deviation logged" if stage.get("plan_deviation") else "no plan deviation")
    t = Table([[Paragraph(f"STAGE {stage['id']} OF {total}", STYLES["banner_sub"])],
               [Paragraph(inline(stage["name"]), STYLES["banner"])],
               [Paragraph(" · ".join(escape(b) for b in bits), STYLES["banner_sub"])]],
              colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1e3a8a")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                           ("TOPPADDING", (0, 0), (-1, 0), 10), ("BOTTOMPADDING", (0, -1), (-1, -1), 10)]))
    return [t, Spacer(1, 12)]


def inline(text):
    """Markdown inline spans -> reportlab paragraph markup."""
    text = escape(text)
    text = re.sub(r"`([^`]+)`", r'<font name="Mono" size="8.5">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)  # links: keep the text
    return text


def figure(path, caption, warnings, source):
    if not os.path.isfile(path):
        warnings.append(f"{source}: figure not found: {path}")
        return [Paragraph(f"[missing figure: {escape(path)}]", STYLES["p"])]
    w, h = ImageReader(path).getSize()
    scale = min(CONTENT_W / w, CONTENT_H * 0.6 / h, 2.0)
    img = Image(path, width=w * scale, height=h * scale)
    parts = [img] + ([Paragraph(inline(caption), STYLES["caption"])] if caption else [Spacer(1, 8)])
    return [KeepTogether(parts)]


def table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows
             if not re.match(r"^\s*\|?[\s:|-]+\|?\s*$", r)]
    ncol = max(len(r) for r in cells)
    data = [[Paragraph(inline(c), STYLES["cellh" if i == 0 else "cell"]) for c in r + [""] * (ncol - len(r))]
            for i, r in enumerate(cells)]
    t = Table(data, colWidths=[CONTENT_W / ncol] * ncol, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 8)]


def markdown_to_flowables(md_path, warnings, demote=0, skip_stage_title=False):
    """Render one markdown file. Returns the flowables."""
    base = os.path.dirname(md_path)
    lines = open(md_path, encoding="utf-8").read().splitlines()
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append(Paragraph(inline(" ".join(s.strip() for s in para)), STYLES["p"]))
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush()
            i += 1
            block = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.extend(textwrap.wrap(lines[i], 100, drop_whitespace=False,
                                           replace_whitespace=False) or [""])
                i += 1
            html = "<br/>".join(escape(b).replace(" ", "&nbsp;") for b in block)
            out.append(Paragraph(html, STYLES["code"]))
        elif re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", stripped):
            flush()
            alt, src = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", stripped).groups()
            out.extend(figure(os.path.normpath(os.path.join(base, src)), alt, warnings, md_path))
        elif stripped.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.extend(table(rows))
            continue
        elif m := re.match(r"^(#{1,6})\s+(.*)$", stripped):
            flush()
            if skip_stage_title and re.match(r"^#\s+Stage\s+\d+", stripped):
                i += 1
                continue
            level = min(len(m.group(1)) + demote, 3)
            out.append(Paragraph(inline(m.group(2)), STYLES[f"h{level}"]))
        elif re.match(r"^(-{3,}|\*{3,})$", stripped):
            flush()
            out.append(HRFlowable(width="100%", color=colors.HexColor("#9ca3af"), spaceBefore=4, spaceAfter=6))
        elif m := re.match(r"^(\s*)([-*]|\d+[.)])\s+(.*)$", line):
            flush()
            indent = len(m.group(1).replace("\t", "    ")) // 2
            bullet = "•" if m.group(2) in "-*" else m.group(2)
            style = ParagraphStyle("li", parent=STYLES["p"], leftIndent=14 + 14 * indent,
                                   bulletIndent=2 + 14 * indent, spaceAfter=2)
            out.append(Paragraph(inline(m.group(3)), style, bulletText=bullet))
        elif stripped.startswith(">"):
            flush()
            out.append(Paragraph(inline(stripped.lstrip("> ")), STYLES["quote"]))
        elif not stripped:
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    return out


def page_furniture(canvas, doc):
    """Runs at page end, after the page's section marker has set the label."""
    canvas.saveState()
    canvas.setFont("Body", 7.5)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawString(MARGIN, 0.45 * inch, doc.title)
    canvas.drawRightString(PAGE_W - MARGIN, 0.45 * inch, f"Page {doc.page}")
    label = getattr(canvas, "_section_label", "")
    if label:
        canvas.setFont("Body-Bold", 8)
        canvas.setFillColor(colors.HexColor("#1e3a8a"))
        canvas.drawString(MARGIN, PAGE_H - 0.5 * inch, label)
        canvas.setStrokeColor(colors.HexColor("#1e3a8a"))
        canvas.line(MARGIN, PAGE_H - 0.55 * inch, PAGE_W - MARGIN, PAGE_H - 0.55 * inch)
    canvas.restoreState()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", default=".")
    ap.add_argument("--through", type=int, help="last stage id to include (default: latest complete)")
    args = ap.parse_args()

    root = os.path.abspath(args.project_dir)
    with open(os.path.join(root, "analysis_checkpoint.json"), encoding="utf-8") as f:
        ck = json.load(f)

    complete = [s for s in ck["stages"] if s["status"] == "complete"]
    if not complete:
        sys.exit("No completed stages in analysis_checkpoint.json.")
    through = args.through or max(s["id"] for s in complete)
    stages = sorted((s for s in complete if s["id"] <= through), key=lambda s: s["id"])

    os.makedirs(os.path.join(root, "reports"), exist_ok=True)
    out_path = os.path.join(root, "reports", f"stage_{through:02d}_report.pdf")
    title = f"{ck['project_name']} — analysis report through stage {through}"

    warnings, story = [], []
    story += [Spacer(1, 1.2 * inch), Paragraph(escape(ck["project_name"]), STYLES["title"]),
              Paragraph(f"Analysis report through stage {through}", STYLES["h2"]), Spacer(1, 14),
              Paragraph(f"<b>Objective:</b> {inline(ck['objective'])}", STYLES["meta"]),
              Paragraph(f"<b>Data:</b> {inline(ck['data_description'])}", STYLES["meta"]),
              Paragraph(f"<b>Generated:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}", STYLES["meta"]),
              Spacer(1, 10)]
    rows = [["Stage", "Name", "Summary"]] + [[str(s["id"]), s["name"], s["summary"]] for s in stages]
    for s in stages:
        if s.get("plan_deviation"):
            rows.append(["", "Deviation", f"Stage {s['id']}: {s['plan_deviation']}"])
    t = Table([[Paragraph(inline(c), STYLES["cellh" if r == 0 else "cell"]) for c in row]
               for r, row in enumerate(rows)], colWidths=[0.65 * inch, 1.6 * inch, CONTENT_W - 2.25 * inch], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e5e7eb")),
                           ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9ca3af")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [t]

    total = len(ck["stages"])
    for s in stages:
        path = os.path.join(root, s["file"])
        story += [PageBreak(), SectionMarker(f"Stage {s['id']}: {s['name']}", f"stage_{s['id']}")]
        story += stage_banner(s, total)
        if not os.path.isfile(path):
            warnings.append(f"stage {s['id']}: stage file not found: {s['file']}")
            story.append(Paragraph(f"[missing stage file: {escape(s['file'])}]", STYLES["p"]))
            continue
        story += markdown_to_flowables(path, warnings, skip_stage_title=True)

    reviews = [r for r in ck.get("literature_reviews", []) if r["stage"] <= through
               and os.path.isfile(os.path.join(root, r["file"]))]
    if reviews:
        story += [PageBreak(), SectionMarker("Appendix: literature reviews", "appendix"),
                  Paragraph("Appendix: literature reviews consulted", STYLES["h1"])]
        for r in reviews:
            story += markdown_to_flowables(os.path.join(root, r["file"]), warnings, demote=1) + [Spacer(1, 12)]

    doc = BaseDocTemplate(out_path, pagesize=letter, title=title, author="bioinformatics-workflow")
    frame = Frame(MARGIN, MARGIN, CONTENT_W, CONTENT_H, id="body", leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPageEnd=page_furniture)])
    doc.build(story)

    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    print(out_path)
    sys.exit(2 if warnings else 0)


if __name__ == "__main__":
    main()
