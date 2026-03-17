import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Image, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)


class PDFError(Exception):
    pass


# ── Palette ───────────────────────────────────────────────────────────────────
_NAVY  = HexColor('#1B3A6B')
_BLUE  = HexColor('#2E86AB')
_DARK  = HexColor('#1A1A2E')
_GREY  = HexColor('#6B7280')
_LGREY = HexColor('#F0F4F8')
_WHITE = colors.white


# ── Styles ────────────────────────────────────────────────────────────────────
def _styles() -> dict:
    return {
        'cover_title': ParagraphStyle(
            'CoverTitle',
            fontName='Helvetica-Bold', fontSize=22, leading=30,
            textColor=_WHITE, alignment=TA_CENTER,
        ),
        'cover_subtitle': ParagraphStyle(
            'CoverSubtitle',
            fontName='Helvetica', fontSize=13, leading=18,
            textColor=HexColor('#BFD7ED'), alignment=TA_CENTER,
        ),
        'cover_date': ParagraphStyle(
            'CoverDate',
            fontName='Helvetica', fontSize=9, leading=13,
            textColor=_GREY, alignment=TA_CENTER,
        ),
        'h1': ParagraphStyle(
            'RH1', fontName='Helvetica-Bold', fontSize=17, leading=24,
            textColor=_NAVY, spaceBefore=16, spaceAfter=4,
        ),
        'h2': ParagraphStyle(
            'RH2', fontName='Helvetica-Bold', fontSize=13, leading=18,
            textColor=_NAVY, spaceBefore=12, spaceAfter=3,
        ),
        'h3': ParagraphStyle(
            'RH3', fontName='Helvetica-BoldOblique', fontSize=11, leading=15,
            textColor=_BLUE, spaceBefore=8, spaceAfter=2,
        ),
        'h4': ParagraphStyle(
            'RH4', fontName='Helvetica-Bold', fontSize=10, leading=14,
            textColor=_GREY, spaceBefore=6, spaceAfter=2,
        ),
        'body': ParagraphStyle(
            'RBody', fontName='Helvetica', fontSize=10, leading=15,
            textColor=_DARK, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        'bullet': ParagraphStyle(
            'RBullet', fontName='Helvetica', fontSize=10, leading=15,
            textColor=_DARK, leftIndent=12, firstLineIndent=0, spaceAfter=3,
        ),
        'th': ParagraphStyle(
            'RTH', fontName='Helvetica-Bold', fontSize=9, leading=13,
            textColor=_WHITE, alignment=TA_LEFT,
        ),
        'td': ParagraphStyle(
            'RTD', fontName='Helvetica', fontSize=9, leading=13,
            textColor=_DARK, alignment=TA_LEFT,
        ),
    }


def _placeholder_box(msg: str) -> Table:
    """Grey placeholder box rendered when a chart or image cannot be loaded."""
    style = ParagraphStyle(
        'Placeholder', fontName='Helvetica-Oblique', fontSize=9, leading=13,
        textColor=_GREY, alignment=TA_CENTER,
    )
    tbl = Table([[Paragraph(msg, style)]], colWidths=[6.5 * inch])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _LGREY),
        ('BOX',           (0, 0), (-1, -1), 0.5, _GREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    return tbl


def _fetch_image(src: str) -> bytes | None:
    """Fetch image bytes from a notebooklm:// URI, web URL, or local file path.
    Returns None on any error — callers render a placeholder instead.
    """
    if src.startswith("notebooklm://"):
        path = src[len("notebooklm://"):]
        parts = path.split("/", 1)
        if len(parts) != 2:
            return None
        notebook_id, filename = parts
        from tools.notebooklm_reader import fetch_notebook_image
        return fetch_notebook_image(notebook_id, filename)

    if src.startswith("http://") or src.startswith("https://"):
        try:
            with urllib.request.urlopen(src, timeout=10) as resp:
                return resp.read()
        except Exception:
            return None

    # Local file path
    try:
        with open(src, "rb") as f:
            return f.read()
    except Exception:
        return None


def _chart_colors() -> list:
    return [_NAVY, _BLUE, HexColor('#E63946'), HexColor('#2A9D8F'),
            HexColor('#E9C46A'), HexColor('#F4A261'), HexColor('#264653')]


def _render_bar(spec: dict) -> Drawing:
    labels = spec["labels"]
    values = spec["values"]
    title  = spec.get("title", "")
    drawing = Drawing(450, 220)
    chart = VerticalBarChart()
    chart.x, chart.y = 50, 30
    chart.width, chart.height = 370, 150
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.bars[0].fillColor = _NAVY
    chart.valueAxis.valueMin = 0
    chart.categoryAxis.labels.angle = 30 if len(labels) > 4 else 0
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    drawing.add(chart)
    if title:
        drawing.add(String(225, 210, title, fontSize=10, fillColor=_DARK, textAnchor='middle'))
    return drawing


def _render_hbar(spec: dict) -> Drawing:
    labels = spec["labels"]
    values = spec["values"]
    title  = spec.get("title", "")
    h = max(180, len(labels) * 25 + 60)
    drawing = Drawing(450, h)
    chart = HorizontalBarChart()
    chart.x, chart.y = 120, 30
    chart.width = 300
    chart.height = max(120, len(labels) * 20)
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.bars[0].fillColor = _NAVY
    chart.valueAxis.valueMin = 0
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    drawing.add(chart)
    if title:
        drawing.add(String(225, h - 10, title, fontSize=10, fillColor=_DARK, textAnchor='middle'))
    return drawing


def _render_pie(spec: dict) -> Drawing:
    labels = spec["labels"]
    values = spec["values"]
    title  = spec.get("title", "")
    total  = sum(values) or 1
    drawing = Drawing(450, 220)
    pie = Pie()
    pie.x, pie.y = 120, 20
    pie.width = pie.height = 160
    pie.data   = values
    pie.labels = [f"{l}\n{v / total * 100:.0f}%" for l, v in zip(labels, values)]
    pie.sideLabels = True
    clrs = _chart_colors()
    for i in range(len(values)):
        pie.slices[i].fillColor = clrs[i % len(clrs)]
    drawing.add(pie)
    if title:
        drawing.add(String(225, 210, title, fontSize=10, fillColor=_DARK, textAnchor='middle'))
    return drawing


def _render_line(spec: dict) -> Drawing:
    labels      = spec["labels"]
    series_data = spec["series"]   # [{name, values}]
    title       = spec.get("title", "")
    drawing = Drawing(450, 220)
    chart = HorizontalLineChart()
    chart.x, chart.y = 60, 30
    chart.width, chart.height = 360, 150
    chart.data = [s["values"] for s in series_data]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    clrs = _chart_colors()
    for i in range(len(series_data)):
        chart.lines[i].strokeColor = clrs[i % len(clrs)]
        chart.lines[i].strokeWidth = 2
    drawing.add(chart)
    if title:
        drawing.add(String(225, 210, title, fontSize=10, fillColor=_DARK, textAnchor='middle'))
    return drawing


def _render_stacked_bar(spec: dict) -> Drawing:
    """Rendered as grouped bars — ReportLab VerticalBarChart has no native
    stacked mode. Each series gets its own coloured bars side by side."""
    labels      = spec["labels"]
    series_data = spec["series"]   # [{name, values}]
    title       = spec.get("title", "")
    drawing = Drawing(450, 220)
    chart = VerticalBarChart()
    chart.x, chart.y = 50, 30
    chart.width, chart.height = 370, 150
    chart.data = [s["values"] for s in series_data]
    chart.categoryAxis.categoryNames = labels
    chart.valueAxis.valueMin = 0
    chart.categoryAxis.labels.angle = 30 if len(labels) > 4 else 0
    chart.categoryAxis.labels.fontSize = 8
    chart.valueAxis.labels.fontSize = 8
    clrs = _chart_colors()
    for i in range(len(series_data)):
        chart.bars[i].fillColor = clrs[i % len(clrs)]
    drawing.add(chart)
    if title:
        drawing.add(String(225, 210, title, fontSize=10, fillColor=_DARK, textAnchor='middle'))
    return drawing


def _slug(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    if len(slug) <= 40:
        return slug
    truncated = slug[:40]
    last_dash = truncated.rfind('-')
    return truncated[:last_dash] if last_dash > 0 else truncated


def _inline_md(text: str) -> str:
    """Escape HTML, then convert inline markdown to ReportLab XML tags."""
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # Bold: **text** → <b>text</b>
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    # Italic: *text* (not **, not inside word boundaries) → <i>text</i>
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    # Inline code: `text` → <font name="Courier">text</font>
    text = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', text)
    return text


def _parse_md_table(table_lines: list, s: dict) -> list:
    """Parse a block of markdown table lines into a list of flowables.

    Normally returns [Spacer, Table, Spacer].
    Falls back to body-paragraph flowables when any cell exceeds
    _MAX_CELL_CHARS, preventing a ReportLab LayoutError that occurs when a
    single cell's Paragraph is taller than the available page frame.
    """
    _MAX_CELL_CHARS = 400

    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip('|').split('|')]
        # Skip separator rows like |---|:---|:---:|
        if all(re.match(r'^[-: ]+$', c) for c in cells if c.strip()):
            continue
        rows.append(cells)

    if not rows:
        return []

    col_count = max(len(r) for r in rows)

    # If any cell is too long to fit inside a table row without overflowing a
    # page frame, render the table as structured body text instead.
    if any(len(cell) > _MAX_CELL_CHARS
           for row in rows
           for cell in (row + [''] * (col_count - len(row)))):
        out = [Spacer(1, 0.06 * inch)]
        for ri, row in enumerate(rows):
            padded = row + [''] * (col_count - len(row))
            style = s['h4'] if ri == 0 else s['body']
            for cell in padded:
                if cell:
                    out.append(Paragraph(_inline_md(cell), style))
        out.append(Spacer(1, 0.06 * inch))
        return out

    col_width = (6.5 * inch) / col_count
    data = []
    for ri, row in enumerate(rows):
        # Pad short rows
        padded = row + [''] * (col_count - len(row))
        style = s['th'] if ri == 0 else s['td']
        data.append([Paragraph(_inline_md(c), style) for c in padded])

    tbl = Table(data, colWidths=[col_width] * col_count, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1,  0), _NAVY),
        ('ROWBACKGROUNDS',(0, 1), (-1, -1), [_WHITE, _LGREY]),
        ('GRID',          (0, 0), (-1, -1), 0.4, _GREY),
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (-1, -1), 6),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 0.06 * inch), tbl, Spacer(1, 0.06 * inch)]


def _md_to_flowables(text: str, s: dict, _tmp_files: list | None = None) -> list:
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ── Fenced chart block ────────────────────────────────────────────
        if stripped == '```chart' or stripped.startswith('```chart '):
            block_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                block_lines.append(lines[i])
                i += 1
            i += 1  # skip closing ```
            _RENDERERS = {
                'bar':         _render_bar,
                'hbar':        _render_hbar,
                'line':        _render_line,
                'pie':         _render_pie,
                'stacked_bar': _render_stacked_bar,
            }
            try:
                spec = json.loads('\n'.join(block_lines))
                chart_type = spec.get('type', '')
                if chart_type not in _RENDERERS:
                    out.append(_placeholder_box(
                        f"Chart unavailable: unknown type '{chart_type}'"
                    ))
                else:
                    try:
                        drawing = _RENDERERS[chart_type](spec)
                        out.append(Spacer(1, 0.08 * inch))
                        out.append(drawing)
                        out.append(Spacer(1, 0.08 * inch))
                    except KeyError as e:
                        out.append(_placeholder_box(
                            f"Chart unavailable: missing field {e}"
                        ))
                    except Exception as e:
                        out.append(_placeholder_box(f"Chart unavailable: {e}"))
            except json.JSONDecodeError as e:
                out.append(_placeholder_box(
                    f"Chart unavailable: invalid JSON — {e}"
                ))
            continue

        # Blank line
        if not stripped:
            out.append(Spacer(1, 0.07 * inch))
            i += 1
            continue

        # Horizontal rule  (--- or *** or ___)
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            out.append(HRFlowable(width='100%', thickness=0.5, color=_GREY,
                                  spaceBefore=4, spaceAfter=4))
            i += 1
            continue

        # H4 (must check before H3)
        if stripped.startswith('#### '):
            out.append(Paragraph(_inline_md(stripped[5:]), s['h4']))
            i += 1
            continue

        # H3
        if stripped.startswith('### '):
            out.append(Paragraph(_inline_md(stripped[4:]), s['h3']))
            i += 1
            continue

        # H2
        if stripped.startswith('## '):
            out.append(Paragraph(_inline_md(stripped[3:]), s['h2']))
            i += 1
            continue

        # H1
        if stripped.startswith('# '):
            out.append(Paragraph(_inline_md(stripped[2:]), s['h1']))
            out.append(HRFlowable(width='100%', thickness=1, color=_BLUE, spaceAfter=4))
            i += 1
            continue

        # Markdown table — collect all consecutive table lines
        if stripped.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip())
                i += 1
            out.extend(_parse_md_table(table_lines, s))
            continue

        # Bullet list (- or *)
        if re.match(r'^[-*]\s+', stripped):
            content = re.sub(r'^[-*]\s+', '', stripped)
            out.append(Paragraph(f'• {_inline_md(content)}', s['bullet']))
            i += 1
            continue

        # Numbered list
        if re.match(r'^\d+\.\s+', stripped):
            out.append(Paragraph(_inline_md(stripped), s['bullet']))
            i += 1
            continue

        # ── Image: ![alt](src) ────────────────────────────────────────────
        img_match = re.match(r'^!\[([^\]]*)\]\(([^)]+)\)$', stripped)
        if img_match:
            alt = img_match.group(1)
            src = img_match.group(2)
            img_bytes = _fetch_image(src)
            if img_bytes is not None:
                parsed = urllib.parse.urlparse(src)
                ext = os.path.splitext(parsed.path)[1] or '.png'
                try:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                    tmp.write(img_bytes)
                    tmp.close()
                    if _tmp_files is not None:
                        _tmp_files.append(tmp.name)
                    img_flow = Image(tmp.name, width=6.5 * inch)
                    img_flow.hAlign = 'CENTER'
                    out.append(Spacer(1, 0.1 * inch))
                    out.append(img_flow)
                    if alt:
                        caption_style = ParagraphStyle(
                            'ImgCaption', fontName='Helvetica-Oblique', fontSize=9,
                            leading=13, textColor=_GREY, alignment=TA_CENTER,
                        )
                        out.append(Paragraph(alt, caption_style))
                    out.append(Spacer(1, 0.1 * inch))
                except Exception:
                    out.append(_placeholder_box(f'Image unavailable: {alt or src}'))
            else:
                out.append(_placeholder_box(f'Image unavailable: {alt or src}'))
            i += 1
            continue

        # Regular paragraph
        out.append(Paragraph(_inline_md(stripped), s['body']))
        i += 1

    return out


def _strip_leading_h1(text: str) -> str:
    """Remove the first line if it is an H1 heading (already added as section title)."""
    lines = text.lstrip('\n').splitlines()
    if lines and lines[0].startswith('# '):
        return '\n'.join(lines[1:])
    return text


def _cover(topic: str, timestamp: str, s: dict) -> list:
    """Navy Table header — self-sizing, so long titles never overlap."""
    tbl = Table(
        [
            [Paragraph(topic, s['cover_title'])],
            [Spacer(1, 0.15 * inch)],
            [Paragraph('Research Report', s['cover_subtitle'])],
        ],
        colWidths=[6.5 * inch],
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _NAVY),
        ('TOPPADDING',    (0, 0), (-1,  0), 32),
        ('BOTTOMPADDING', (0, 2), (-1,  2), 32),
        ('LEFTPADDING',   (0, 0), (-1, -1), 28),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 28),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return [
        Spacer(1, 1.8 * inch),
        tbl,
        Spacer(1, 0.35 * inch),
        Paragraph(f'Generated: {timestamp}', s['cover_date']),
        PageBreak(),
    ]


def _make_footer(timestamp: str, report_title: str):
    short = report_title if len(report_title) <= 65 else report_title[:62] + '...'

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_NAVY)
        canvas.setLineWidth(0.4)
        canvas.line(inch, 0.68 * inch, letter[0] - inch, 0.68 * inch)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(_GREY)
        canvas.drawString(inch, 0.48 * inch, short)
        canvas.drawRightString(letter[0] - inch, 0.48 * inch, f'Page {doc.page}')
        canvas.restoreState()

    return _footer


def generate_pdf(data: dict, output_dir: str) -> str:
    # Reject POSIX-style absolute paths on Windows (no drive letter)
    drive, _ = os.path.splitdrive(output_dir)
    if not drive and output_dir.startswith('/'):
        raise PDFError(f'[ERR-PDF-002] Output directory not writable: {output_dir}')

    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        raise PDFError(f'[ERR-PDF-002] Output directory not writable: {output_dir} — {e}')

    topic     = data['topic']
    run_id    = data['run_id']
    timestamp = data.get('generated_at', datetime.now(timezone.utc).isoformat())
    filename  = f'{_slug(topic)}-{run_id[:10]}.pdf'
    out_path  = os.path.join(output_dir, filename)

    s = _styles()

    tmp_files: list[str] = []
    try:
        doc = SimpleDocTemplate(
            out_path, pagesize=letter,
            leftMargin=inch, rightMargin=inch,
            topMargin=0.85 * inch, bottomMargin=0.85 * inch,
        )
        story = _cover(topic, timestamp, s)

        story.append(Paragraph('Executive Summary', s['h1']))
        story.append(HRFlowable(width='100%', thickness=2, color=_NAVY, spaceAfter=8))
        story.extend(_md_to_flowables(
            _strip_leading_h1(data.get('executive_summary', '')), s, tmp_files))
        story.append(PageBreak())

        story.append(Paragraph('Full Report', s['h1']))
        story.append(HRFlowable(width='100%', thickness=2, color=_NAVY, spaceAfter=8))
        story.extend(_md_to_flowables(
            _strip_leading_h1(data.get('full_report', '')), s, tmp_files))

        doc.build(story, onFirstPage=_make_footer(timestamp, topic),
                  onLaterPages=_make_footer(timestamp, topic))

    except OSError as e:
        raise PDFError(f'[ERR-PDF-002] Output directory not writable: {out_path} — {e}')
    except Exception as e:
        raise PDFError(f'[ERR-PDF-001] PDF generation failed: {e}')
    finally:
        for f in tmp_files:
            try:
                os.unlink(f)
            except Exception:
                pass

    return out_path
