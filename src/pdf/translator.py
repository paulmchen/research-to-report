"""
translate_pdf.py — Generate translated PDF versions of a research report.

Library API:
    generate_translation(data, language, output_dir, model) -> str

CLI (translate an arbitrary existing PDF):
    python src/translate_pdf.py <input.pdf> [output_dir] [--lang zh-CN|zh-TW]
"""
import os
import re
import sys

import litellm
import pypdf
from dotenv import load_dotenv
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

load_dotenv()

SUPPORTED_LANGUAGES = {"en", "zh-CN", "zh-TW"}

_LANGUAGE_LABELS = {
    "zh-CN": {"report": "研究报告", "translation_note": "简体中文译本", "page": "第 {n} 页"},
    "zh-TW": {"report": "研究報告", "translation_note": "繁體中文譯本", "page": "第 {n} 頁"},
}

# ── Palette ───────────────────────────────────────────────────────────────────
_NAVY  = HexColor('#1B3A6B')
_BLUE  = HexColor('#2E86AB')
_DARK  = HexColor('#1A1A2E')
_GREY  = HexColor('#6B7280')
_LGREY = HexColor('#F0F4F8')
_WHITE = colors.white

_FONT_DIR = r'C:\Windows\Fonts'
_FONTS_REGISTERED = False


def _register_chinese_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont('ZH',   os.path.join(_FONT_DIR, 'msyh.ttc'),   subfontIndex=0))
    pdfmetrics.registerFont(TTFont('ZH-B', os.path.join(_FONT_DIR, 'msyhbd.ttc'), subfontIndex=0))
    _FONTS_REGISTERED = True


def _zh_styles() -> dict:
    return {
        'cover_title': ParagraphStyle(
            'ZHCoverTitle', fontName='ZH-B', fontSize=22, leading=34,
            textColor=_WHITE, alignment=TA_CENTER,
        ),
        'cover_subtitle': ParagraphStyle(
            'ZHCoverSub', fontName='ZH', fontSize=13, leading=20,
            textColor=HexColor('#BFD7ED'), alignment=TA_CENTER,
        ),
        'cover_date': ParagraphStyle(
            'ZHCoverDate', fontName='ZH', fontSize=9, leading=14,
            textColor=_GREY, alignment=TA_CENTER,
        ),
        'h1': ParagraphStyle(
            'ZHH1', fontName='ZH-B', fontSize=17, leading=26,
            textColor=_NAVY, spaceBefore=16, spaceAfter=4,
        ),
        'h2': ParagraphStyle(
            'ZHH2', fontName='ZH-B', fontSize=13, leading=20,
            textColor=_NAVY, spaceBefore=12, spaceAfter=3,
        ),
        'h3': ParagraphStyle(
            'ZHH3', fontName='ZH-B', fontSize=11, leading=17,
            textColor=_BLUE, spaceBefore=8, spaceAfter=2,
        ),
        'h4': ParagraphStyle(
            'ZHH4', fontName='ZH-B', fontSize=10, leading=15,
            textColor=_GREY, spaceBefore=6, spaceAfter=2,
        ),
        'body': ParagraphStyle(
            'ZHBody', fontName='ZH', fontSize=10, leading=17,
            textColor=_DARK, alignment=TA_JUSTIFY, spaceAfter=5,
        ),
        'bullet': ParagraphStyle(
            'ZHBullet', fontName='ZH', fontSize=10, leading=17,
            textColor=_DARK, leftIndent=12, spaceAfter=3,
        ),
        'th': ParagraphStyle(
            'ZHTH', fontName='ZH-B', fontSize=9, leading=14,
            textColor=_WHITE, alignment=TA_LEFT,
        ),
        'td': ParagraphStyle(
            'ZHTD', fontName='ZH', fontSize=9, leading=14,
            textColor=_DARK, alignment=TA_LEFT,
        ),
    }


# ── Inline markdown → ReportLab XML ──────────────────────────────────────────
def _inline(text: str) -> str:
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<i>\1</i>', text)
    text = re.sub(r'`([^`]+)`', r'<font name="Courier">\1</font>', text)
    return text


def _parse_table(table_lines: list, s: dict):
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip('|').split('|')]
        if all(re.match(r'^[-: ]+$', c) for c in cells if c.strip()):
            continue
        rows.append(cells)
    if not rows:
        return None
    col_count = max(len(r) for r in rows)
    col_w = (6.5 * inch) / col_count
    data = []
    for ri, row in enumerate(rows):
        padded = row + [''] * (col_count - len(row))
        st = s['th'] if ri == 0 else s['td']
        data.append([Paragraph(_inline(c), st) for c in padded])
    tbl = Table(data, colWidths=[col_w] * col_count, repeatRows=1)
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
    return tbl


def _md_to_flowables(text: str, s: dict) -> list:
    out = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped:
            out.append(Spacer(1, 0.07 * inch)); i += 1; continue
        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            out.append(HRFlowable(width='100%', thickness=0.5, color=_GREY,
                                  spaceBefore=4, spaceAfter=4)); i += 1; continue
        if stripped.startswith('#### '):
            out.append(Paragraph(_inline(stripped[5:]), s['h4'])); i += 1; continue
        if stripped.startswith('### '):
            out.append(Paragraph(_inline(stripped[4:]), s['h3'])); i += 1; continue
        if stripped.startswith('## '):
            out.append(Paragraph(_inline(stripped[3:]), s['h2'])); i += 1; continue
        if stripped.startswith('# '):
            out.append(Paragraph(_inline(stripped[2:]), s['h1']))
            out.append(HRFlowable(width='100%', thickness=1, color=_BLUE, spaceAfter=4))
            i += 1; continue
        if stripped.startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i].strip()); i += 1
            tbl = _parse_table(table_lines, s)
            if tbl:
                out.append(Spacer(1, 0.06 * inch))
                out.append(tbl)
                out.append(Spacer(1, 0.06 * inch))
            continue
        if re.match(r'^[-*]\s+', stripped):
            out.append(Paragraph(f'• {_inline(re.sub(r"^[-*]\\s+", "", stripped))}', s['bullet']))
            i += 1; continue
        if re.match(r'^\d+\.\s+', stripped):
            out.append(Paragraph(_inline(stripped), s['bullet'])); i += 1; continue
        out.append(Paragraph(_inline(stripped), s['body'])); i += 1
    return out


# ── Translation ────────────────────────────────────────────────────────────────
def _translate(text: str, language: str, model: str) -> str:
    """Translate markdown text to zh-CN or zh-TW, preserving formatting."""
    if language == "zh-CN":
        target = "Simplified Chinese (简体中文), as used in mainland China"
    else:
        target = "Traditional Chinese (繁體中文), as used in Taiwan"

    prompt = (
        f"You are a professional translator. Translate the following English report to "
        f"{target}. Rules:\n"
        f"- Preserve ALL markdown formatting exactly: # headings, **bold**, *italic*, "
        f"bullet lists (- item), numbered lists, and table syntax (|col|col|)\n"
        f"- Translate all text to Chinese; keep numbers, percentages, dates as-is\n"
        f"- Output ONLY the translated markdown, no preamble or explanation\n\n"
        f"{text}"
    )
    response = litellm.completion(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=8096,
    )
    return response.choices[0].message.content.strip()


# ── PDF builder ────────────────────────────────────────────────────────────────
def _build_chinese_pdf(topic: str, zh_exec: str, zh_report: str,
                       language: str, out_path: str) -> str:
    _register_chinese_fonts()
    s = _zh_styles()
    labels = _LANGUAGE_LABELS[language]

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(_NAVY)
        canvas.setLineWidth(0.4)
        canvas.line(inch, 0.68 * inch, letter[0] - inch, 0.68 * inch)
        canvas.setFont('ZH', 7.5)
        canvas.setFillColor(_GREY)
        short = topic if len(topic) <= 65 else topic[:62] + '...'
        canvas.drawString(inch, 0.48 * inch, short)
        canvas.drawRightString(letter[0] - inch, 0.48 * inch,
                               labels["page"].format(n=doc.page))
        canvas.restoreState()

    cover_tbl = Table(
        [[Paragraph(topic, s['cover_title'])],
         [Spacer(1, 0.15 * inch)],
         [Paragraph(labels["report"], s['cover_subtitle'])]],
        colWidths=[6.5 * inch],
    )
    cover_tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), _NAVY),
        ('TOPPADDING',    (0, 0), (-1,  0), 32),
        ('BOTTOMPADDING', (0, 2), (-1,  2), 32),
        ('LEFTPADDING',   (0, 0), (-1, -1), 28),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 28),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))

    story = [
        Spacer(1, 1.8 * inch),
        cover_tbl,
        Spacer(1, 0.35 * inch),
        Paragraph(labels["translation_note"], s['cover_date']),
        PageBreak(),
    ]

    # Executive Summary section
    exec_title = "执行摘要" if language == "zh-CN" else "執行摘要"
    full_title  = "完整报告" if language == "zh-CN" else "完整報告"

    story.append(Paragraph(exec_title, s['h1']))
    story.append(HRFlowable(width='100%', thickness=2, color=_NAVY, spaceAfter=8))
    story.extend(_md_to_flowables(_strip_leading_h1(zh_exec), s))
    story.append(PageBreak())

    story.append(Paragraph(full_title, s['h1']))
    story.append(HRFlowable(width='100%', thickness=2, color=_NAVY, spaceAfter=8))
    story.extend(_md_to_flowables(_strip_leading_h1(zh_report), s))

    doc = SimpleDocTemplate(
        out_path, pagesize=letter,
        leftMargin=inch, rightMargin=inch,
        topMargin=0.85 * inch, bottomMargin=0.85 * inch,
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return out_path


def _strip_leading_h1(text: str) -> str:
    lines = text.lstrip('\n').splitlines()
    if lines and lines[0].startswith('# '):
        return '\n'.join(lines[1:])
    return text


def _slug(text: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    if len(slug) <= 40:
        return slug
    truncated = slug[:40]
    last_dash = truncated.rfind('-')
    return truncated[:last_dash] if last_dash > 0 else truncated


# ── Public library API ────────────────────────────────────────────────────────
def generate_translation(data: dict, language: str, output_dir: str,
                         model: str = 'claude-sonnet-4-6') -> str:
    """
    Translate a report to Chinese and write a PDF.

    :param data: same dict as generate_pdf — keys: topic, run_id,
                 executive_summary, full_report
    :param language: 'zh-CN' or 'zh-TW'
    :param output_dir: directory to write the PDF
    :param model: LiteLLM model string
    :return: path to the generated PDF
    """
    if language not in ("zh-CN", "zh-TW"):
        raise ValueError(f"Unsupported language: {language}. Use zh-CN or zh-TW.")

    topic   = data["topic"]
    run_id  = data["run_id"]
    exec_md = data.get("executive_summary", "")
    full_md = data.get("full_report", "")

    filename = f'{_slug(topic)}-{run_id[:10]}-{language}.pdf'
    out_path = os.path.join(output_dir, filename)
    os.makedirs(output_dir, exist_ok=True)

    print(f"  Translating Executive Summary to {language}...")
    zh_exec = _translate(exec_md, language, model)

    print(f"  Translating Full Report to {language}...")
    zh_full = _translate(full_md, language, model)

    print(f"  Generating {language} PDF...")
    return _build_chinese_pdf(topic, zh_exec, zh_full, language, out_path)


# ── CLI (translate an arbitrary existing PDF file) ────────────────────────────
def _translate_existing_pdf(input_pdf: str, output_dir: str = None,
                             language: str = 'zh-TW',
                             model: str = 'claude-sonnet-4-6') -> str:
    """Extract text from an existing PDF and produce a translated PDF."""
    if not os.path.exists(input_pdf):
        raise FileNotFoundError(f'Input PDF not found: {input_pdf}')

    output_dir = output_dir or os.path.dirname(os.path.abspath(input_pdf))
    os.makedirs(output_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(input_pdf))[0]
    out_path = os.path.join(output_dir, f'{base}-{language}.pdf')

    print(f'Extracting text from: {input_pdf}')
    reader = pypdf.PdfReader(input_pdf)
    raw_text = '\n\n'.join(
        p.extract_text().strip() for p in reader.pages if p.extract_text()
    )
    print(f'Extracted {len(raw_text)} characters')

    print(f'Translating to {language}...')
    zh_text = _translate(raw_text, language, model)

    first_line = zh_text.splitlines()[0].lstrip('# ').strip()
    title = first_line or base

    print(f'Generating PDF: {out_path}')
    _build_chinese_pdf(title, '', zh_text, language, out_path)
    print(f'Done: {out_path}')
    return out_path


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Translate a PDF to Chinese')
    parser.add_argument('input_pdf', help='Path to the input PDF')
    parser.add_argument('output_dir', nargs='?', default=None,
                        help='Output directory (default: same as input)')
    parser.add_argument('--lang', default='zh-TW', choices=['zh-CN', 'zh-TW'],
                        help='Target language (default: zh-TW)')
    args = parser.parse_args()
    _translate_existing_pdf(args.input_pdf, args.output_dir, args.lang)
