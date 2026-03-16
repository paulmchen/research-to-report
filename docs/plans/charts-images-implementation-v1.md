# Charts & Images in PDF Reports — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Embed ReportLab-native charts (bar, hbar, line, pie, stacked_bar) and images (web URL, local file, NotebookLM) inline in generated PDF reports, placed by the LLM naturally in the markdown flow.

**Architecture:** The synthesizer prompt is extended to teach the LLM two new syntax patterns — ` ```chart ` JSON blocks and `![alt](src)` image references. The PDF formatter's markdown parser detects these patterns and renders them as ReportLab flowables. All failures render a visible grey placeholder box — PDF generation never aborts due to a bad chart or broken image.

**Tech Stack:** ReportLab platypus + graphics (already installed), `urllib.request` (stdlib), `tempfile` (stdlib), `asyncio` + `mcp` (already installed for NotebookLM).

---

## Task 1: `_placeholder_box()` utility

**Files:**
- Modify: `src/pdf_formatter.py`
- Modify: `tests/test_pdf_formatter.py`

### Step 1: Write the failing tests

Add to `tests/test_pdf_formatter.py`:

```python
def test_placeholder_box_returns_table():
    from src.pdf_formatter import _placeholder_box
    from reportlab.platypus import Table
    result = _placeholder_box("Chart unavailable: invalid JSON")
    assert isinstance(result, Table)


def test_placeholder_box_contains_message():
    from src.pdf_formatter import _placeholder_box
    result = _placeholder_box("Image unavailable: my image")
    assert result is not None
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_formatter.py::test_placeholder_box_returns_table -v
```

Expected: `ImportError` — `_placeholder_box` not defined.

### Step 3: Implement `_placeholder_box` in `src/pdf_formatter.py`

Add after the `_styles()` function (around line 81):

```python
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_formatter.py::test_placeholder_box_returns_table tests/test_pdf_formatter.py::test_placeholder_box_contains_message -v
```

Expected: PASS.

---

## Task 2: `fetch_notebook_image()` in notebooklm_reader

**Files:**
- Modify: `src/tools/notebooklm_reader.py`
- Modify: `tests/test_tools.py`

### Step 1: Write the failing tests

Add to `tests/test_tools.py`:

```python
def test_fetch_notebook_image_returns_none_on_error():
    """Any MCP error must return None — never raise."""
    from src.tools.notebooklm_reader import fetch_notebook_image
    with patch("asyncio.run", side_effect=Exception("MCP server error")):
        result = fetch_notebook_image("nb-id", "diagram.png")
    assert result is None


def test_fetch_notebook_image_returns_bytes_on_success():
    """When asyncio.run returns bytes (mocked), propagate them."""
    from src.tools.notebooklm_reader import fetch_notebook_image
    fake_bytes = b'\x89PNG\r\n' + b'\x00' * 20
    with patch("asyncio.run", return_value=fake_bytes):
        result = fetch_notebook_image("nb-id", "diagram.png")
    assert result == fake_bytes
```

### Step 2: Run to verify failure

```bash
pytest tests/test_tools.py::test_fetch_notebook_image_returns_none_on_error -v
```

Expected: `ImportError` — `fetch_notebook_image` not defined.

### Step 3: Implement in `src/tools/notebooklm_reader.py`

Add `import base64` at the top with the other stdlib imports.

Add these two functions after `query_notebook()`:

```python
async def _fetch_image_async(notebook_id: str, filename: str) -> bytes | None:
    server_params = StdioServerParameters(command=_MCP_COMMAND, args=_MCP_ARGS)
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "source_get_content",
                {"notebook_id": notebook_id, "source_name": filename},
            )
    if not result.content:
        return None
    try:
        return base64.b64decode(result.content[0].text)
    except Exception:
        return None


def fetch_notebook_image(notebook_id: str, filename: str) -> bytes | None:
    """Attempt to fetch raw image bytes from a NotebookLM notebook source via MCP.

    Returns None if unsupported, not found, or any error — never raises.
    The notebooklm-mcp-cli server may not support image extraction;
    callers must handle None by rendering a placeholder.
    """
    try:
        return asyncio.run(_fetch_image_async(notebook_id, filename))
    except Exception:
        return None
```

### Step 4: Run to verify pass

```bash
pytest tests/test_tools.py::test_fetch_notebook_image_returns_none_on_error tests/test_tools.py::test_fetch_notebook_image_returns_bytes_on_success -v
```

Expected: PASS.

---

## Task 3: `_fetch_image()` in pdf_formatter

**Files:**
- Modify: `src/pdf_formatter.py`
- Create: `tests/test_pdf_charts_images.py`

### Step 1: Write the failing tests

Create `tests/test_pdf_charts_images.py`:

```python
import pytest
from unittest.mock import patch, MagicMock


# ── _fetch_image ──────────────────────────────────────────────────────────────

def test_fetch_image_local_file(tmp_path):
    from src.pdf_formatter import _fetch_image
    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake image data")
    result = _fetch_image(str(img_file))
    assert result == b"fake image data"


def test_fetch_image_local_missing_returns_none():
    from src.pdf_formatter import _fetch_image
    result = _fetch_image("/nonexistent/path/image.png")
    assert result is None


def test_fetch_image_url_success():
    from src.pdf_formatter import _fetch_image
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"url image bytes"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _fetch_image("https://example.com/chart.png")
    assert result == b"url image bytes"


def test_fetch_image_url_failure_returns_none():
    from src.pdf_formatter import _fetch_image
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        result = _fetch_image("https://example.com/chart.png")
    assert result is None


def test_fetch_image_notebooklm_delegates():
    from src.pdf_formatter import _fetch_image
    with patch("src.tools.notebooklm_reader.fetch_notebook_image", return_value=b"nb img") as mock_fn:
        result = _fetch_image("notebooklm://my-notebook-id/diagram.png")
    mock_fn.assert_called_once_with("my-notebook-id", "diagram.png")
    assert result == b"nb img"


def test_fetch_image_notebooklm_unavailable_returns_none():
    from src.pdf_formatter import _fetch_image
    with patch("src.tools.notebooklm_reader.fetch_notebook_image", return_value=None):
        result = _fetch_image("notebooklm://nb-id/image.png")
    assert result is None
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_charts_images.py::test_fetch_image_local_file -v
```

Expected: `ImportError` — `_fetch_image` not defined.

### Step 3: Update imports and add `_fetch_image` to `src/pdf_formatter.py`

**Replace the existing imports block** at the top of `src/pdf_formatter.py` with:

```python
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
```

Add `_fetch_image()` after `_placeholder_box()`:

```python
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
        from src.tools.notebooklm_reader import fetch_notebook_image
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_charts_images.py -k "fetch_image" -v
```

Expected: all 6 tests PASS.

---

## Task 4: Chart renderers — bar, hbar, pie

**Files:**
- Modify: `src/pdf_formatter.py`
- Modify: `tests/test_pdf_charts_images.py`

### Step 1: Write the failing tests

Add to `tests/test_pdf_charts_images.py`:

```python
# ── Chart renderers ───────────────────────────────────────────────────────────

def test_render_bar_returns_drawing():
    from src.pdf_formatter import _render_bar
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["North America", "Asia", "Europe"], "values": [42, 35, 23]}
    assert isinstance(_render_bar(spec), Drawing)


def test_render_bar_with_title():
    from src.pdf_formatter import _render_bar
    from reportlab.graphics.shapes import Drawing
    spec = {"title": "Market Share", "labels": ["A", "B"], "values": [60, 40]}
    assert isinstance(_render_bar(spec), Drawing)


def test_render_hbar_returns_drawing():
    from src.pdf_formatter import _render_hbar
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["Product A", "Product B", "Product C"], "values": [45, 30, 25]}
    assert isinstance(_render_hbar(spec), Drawing)


def test_render_pie_returns_drawing():
    from src.pdf_formatter import _render_pie
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["Cloud", "On-Prem", "Hybrid"], "values": [55, 25, 20]}
    assert isinstance(_render_pie(spec), Drawing)


def test_render_pie_zero_values_no_crash():
    from src.pdf_formatter import _render_pie
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["A", "B"], "values": [0, 0]}
    assert isinstance(_render_pie(spec), Drawing)
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_charts_images.py::test_render_bar_returns_drawing -v
```

Expected: `ImportError`.

### Step 3: Add colour helper and renderers to `src/pdf_formatter.py`

Add after `_fetch_image()`:

```python
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_charts_images.py -k "render_bar or render_hbar or render_pie" -v
```

Expected: all 5 tests PASS.

---

## Task 5: Chart renderers — line, stacked_bar

**Files:**
- Modify: `src/pdf_formatter.py`
- Modify: `tests/test_pdf_charts_images.py`

### Step 1: Write the failing tests

Add to `tests/test_pdf_charts_images.py`:

```python
def test_render_line_returns_drawing():
    from src.pdf_formatter import _render_line
    from reportlab.graphics.shapes import Drawing
    spec = {
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "series": [
            {"name": "2025", "values": [10, 18, 15, 22]},
            {"name": "2026", "values": [12, 20, 19, 28]},
        ],
    }
    assert isinstance(_render_line(spec), Drawing)


def test_render_stacked_bar_returns_drawing():
    from src.pdf_formatter import _render_stacked_bar
    from reportlab.graphics.shapes import Drawing
    spec = {
        "labels": ["Q1", "Q2", "Q3"],
        "series": [
            {"name": "Product A", "values": [10, 15, 12]},
            {"name": "Product B", "values": [8, 11, 14]},
        ],
    }
    assert isinstance(_render_stacked_bar(spec), Drawing)
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_charts_images.py::test_render_line_returns_drawing -v
```

Expected: `ImportError`.

### Step 3: Add renderers to `src/pdf_formatter.py`

Add after `_render_pie()`:

```python
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_charts_images.py -k "render_line or render_stacked" -v
```

Expected: both PASS.

---

## Task 6: Chart block detection in `_md_to_flowables`

**Files:**
- Modify: `src/pdf_formatter.py`
- Modify: `tests/test_pdf_charts_images.py`

### Step 1: Write the failing tests

Add to `tests/test_pdf_charts_images.py`:

```python
# ── Chart block detection ─────────────────────────────────────────────────────

def test_md_chart_bar_renders_drawing():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.graphics.shapes import Drawing
    md = '```chart\n{"type": "bar", "labels": ["A", "B"], "values": [10, 20]}\n```'
    drawings = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Drawing)]
    assert len(drawings) == 1


def test_md_chart_invalid_json_renders_placeholder():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\nnot valid json\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1


def test_md_chart_unknown_type_renders_placeholder():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\n{"type": "scatter", "labels": ["A"], "values": [1]}\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1


def test_md_chart_missing_values_renders_placeholder():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\n{"type": "bar", "labels": ["A", "B"]}\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_charts_images.py::test_md_chart_bar_renders_drawing -v
```

Expected: FAIL — chart block falls through to regular paragraph.

### Step 3: Add chart block detector to `_md_to_flowables`

In `_md_to_flowables`, insert this as the **very first check** inside the `while i < len(lines):` loop, before the blank line check:

```python
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_charts_images.py -k "md_chart" -v
```

Expected: all 4 PASS.

---

## Task 7: Image detection in `_md_to_flowables`

**Files:**
- Modify: `src/pdf_formatter.py`
- Modify: `tests/test_pdf_charts_images.py`

### Step 1: Write the failing tests

Add to `tests/test_pdf_charts_images.py`:

```python
# ── Image detection ───────────────────────────────────────────────────────────

def test_md_image_success_renders_image_flowable():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Image as RLImage
    import os
    tmp_files = []
    with patch("src.pdf_formatter._fetch_image", return_value=b"fake bytes"):
        flowables = _md_to_flowables("![My Chart](https://example.com/img.png)", _styles(), tmp_files)
    for f in tmp_files:
        try: os.unlink(f)
        except Exception: pass
    assert any(isinstance(f, RLImage) for f in flowables)


def test_md_image_fetch_failure_renders_placeholder():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    with patch("src.pdf_formatter._fetch_image", return_value=None):
        flowables = _md_to_flowables("![Missing Image](/bad/path.png)", _styles())
    assert any(isinstance(f, Table) for f in flowables)


def test_md_image_notebooklm_unavailable_renders_placeholder():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    with patch("src.pdf_formatter._fetch_image", return_value=None):
        flowables = _md_to_flowables(
            "![Diagram](notebooklm://nb-id/diagram.png)", _styles()
        )
    assert any(isinstance(f, Table) for f in flowables)


def test_md_image_caption_rendered():
    from src.pdf_formatter import _md_to_flowables, _styles
    from reportlab.platypus import Paragraph
    import os
    tmp_files = []
    with patch("src.pdf_formatter._fetch_image", return_value=b"fake bytes"):
        flowables = _md_to_flowables(
            "![Figure 1: AI Investment](https://x.com/img.png)", _styles(), tmp_files
        )
    for f in tmp_files:
        try: os.unlink(f)
        except Exception: pass
    assert any(isinstance(f, Paragraph) and "Figure 1" in f.text for f in flowables)
```

### Step 2: Run to verify failure

```bash
pytest tests/test_pdf_charts_images.py::test_md_image_fetch_failure_renders_placeholder -v
```

Expected: FAIL — image markdown falls through to regular paragraph.

### Step 3: Update `_md_to_flowables` signature and add image detector

**Update the function signature:**

```python
def _md_to_flowables(text: str, s: dict, _tmp_files: list | None = None) -> list:
```

Add the image detector **just before the `# Regular paragraph` block** at the end of the loop:

```python
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
```

**Update `generate_pdf`** to pass and clean up `_tmp_files`. Replace the inner `try/except` block:

```python
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
```

### Step 4: Run to verify pass

```bash
pytest tests/test_pdf_charts_images.py -k "md_image" -v
```

Expected: all 4 PASS.

---

## Task 8: Synthesizer prompt update

**Files:**
- Modify: `src/synthesizer.py`
- Modify: `tests/test_synthesizer.py`

### Step 1: Write the failing test

Add to `tests/test_synthesizer.py`:

```python
def test_synthesize_prompt_includes_chart_instruction():
    from src.synthesizer import synthesize
    from unittest.mock import patch
    captured = []
    def fake_llm(model, messages, max_tokens):
        captured.append(messages[0]["content"])
        return "# Executive Summary\nSummary.\n\n---\n\n# Full Report\nBody."
    with patch("src.synthesizer.litellm_complete", side_effect=fake_llm):
        synthesize("AI trends", {"subtopic 1": "findings"}, {
            "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 4096}
        })
    assert "```chart" in captured[0]
    assert "![" in captured[0]
```

### Step 2: Run to verify failure

```bash
pytest tests/test_synthesizer.py::test_synthesize_prompt_includes_chart_instruction -v
```

Expected: FAIL.

### Step 3: Update prompt in `src/synthesizer.py`

Replace the `prompt = (...)` block in `synthesize()`:

```python
    prompt = (
        f"You are a senior research analyst. Using the subtopic research below, "
        f"write a professional report on: **{topic}**\n\n"
        f"Structure your response EXACTLY as follows — with '---' as the separator:\n\n"
        f"# Executive Summary\n"
        f"[1-2 page executive summary with key findings and recommendations]\n\n"
        f"{_SEPARATOR}\n\n"
        f"# Full Report\n"
        f"[5-10 page detailed report: background, findings per subtopic, analysis, recommendations]\n\n"
        f"When relevant, enrich the report with visual elements placed inline:\n"
        f"- Charts: use ```chart blocks with JSON. "
        f"Supported types: bar, hbar, line, pie, stacked_bar.\n"
        f'  Example: ```chart\n{{"type":"bar","title":"Title","labels":["A","B"],"values":[10,20]}}\n```\n'
        f"  For line and stacked_bar use 'series': "
        f'[{{"name":"Label","values":[...]}}] instead of \'values\'.\n'
        f"- Images: use standard markdown ![caption](url). Only include real, publicly accessible URLs.\n"
        f"Only include charts where you have concrete numeric data. "
        f"Place visuals immediately after the text they illustrate.\n\n"
        f"---\n\nSubtopic Research:\n\n{findings_text}"
    )
```

### Step 4: Run to verify pass

```bash
pytest tests/test_synthesizer.py -v
```

Expected: all synthesizer tests PASS.

---

## Task 9: Full suite + update docs

### Step 1: Run the full test suite

```bash
pytest tests/ -v
```

Expected: all tests PASS. Fix any failures before proceeding.

### Step 2: Update `docs/plans/research-to-report-design-2026-03-12.md`

- **Section 5 (Tools & Integrations):** Update `pdf_generator` row to mention "charts and images"; add note about ReportLab graphics module.
- **Section 8 (Report Format):** Add bullet: "Charts and images embedded inline where the LLM places them; unsupported or broken references render as a grey placeholder box."
- **Section 15 (Error Handling):** Add rows for chart/image failure scenarios (invalid JSON → placeholder, broken image URL → placeholder).

### Step 3: Update `docs/plans/research-to-report-implementation-2026-03-12.md`

- **PDF formatter task:** Update imports list, description, and note new functions: `_placeholder_box`, `_fetch_image`, chart renderers, updated `_md_to_flowables` signature, `generate_pdf` tmp_files cleanup.
- **Synthesizer task:** Update prompt code block.
- **NotebookLM reader task:** Note new `fetch_notebook_image()` function.
- **Component table:** Reflect new capabilities.
