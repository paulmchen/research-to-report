# Charts & Images in PDF Reports — Design Document

**Date:** 2026-03-14
**Status:** Approved
**Feature:** Embed ReportLab-native charts and images (web URL / local file / NotebookLM) inline in generated PDF reports.

---

## 1. Overview

Extend the PDF generation pipeline to support two new inline content types that the LLM synthesizer can place anywhere in its markdown output:

- **Charts** — rendered natively by ReportLab (bar, horizontal bar, line, pie, stacked bar)
- **Images** — sourced from web URLs, local file paths, or NotebookLM notebook sources

No new dependencies. `urllib.request` (stdlib) handles URL downloads. ReportLab is already installed.

---

## 2. Approach

The LLM (synthesizer) decides placement inline in the markdown narrative. The PDF formatter detects the special syntax and renders the appropriate flowable. All failures are non-fatal — a visible grey placeholder box is rendered instead so the reader knows something was intended.

Three files change:

| File | Change |
|---|---|
| `src/synthesizer.py` | Prompt extended with chart/image syntax instructions |
| `src/pdf_formatter.py` | Markdown parser extended with chart and image detectors + renderers |
| `src/tools/notebooklm_reader.py` | New `fetch_notebook_image()` function |

---

## 3. Syntax

### Charts — fenced code block

````markdown
```chart
{
  "type": "bar",
  "title": "Global AI Investment by Region (2026)",
  "labels": ["North America", "Asia", "Europe"],
  "values": [42, 35, 23],
  "x_label": "Region",
  "y_label": "USD Billion"
}
```
````

**Supported types and required fields:**

| Type | Required fields | Notes |
|---|---|---|
| `bar` | `labels`, `values` | Vertical bar chart |
| `hbar` | `labels`, `values` | Horizontal bar chart |
| `line` | `labels`, `series` | Multi-series; `series: [{name, values}]` |
| `pie` | `labels`, `values` | Percentage labels auto-computed |
| `stacked_bar` | `labels`, `series` | Multi-series; `series: [{name, values}]` |

**Optional fields (all types):** `title`, `x_label`, `y_label`

### Images — standard markdown image syntax

```markdown
![caption](https://example.com/image.png)          # web URL
![caption](./reports/my-diagram.png)               # local file path
![caption](notebooklm://notebook-id/filename.png)  # NotebookLM source
```

Images auto-fit to page width (max 6.5 inches), aspect ratio preserved.

---

## 4. Component Design

### 4.1 `src/synthesizer.py`

Append the following instruction to the existing synthesis prompt:

```
When relevant, enrich the report with:
- Charts: use ```chart blocks with JSON (types: bar, hbar, line, pie, stacked_bar)
- Images: use standard markdown ![caption](url-or-path)
Place them inline where they best support the narrative.
Only include charts where you have concrete data to back them up.
```

### 4.2 `src/pdf_formatter.py`

**New detectors in `_md_to_flowables()`** (checked before existing line handlers):

1. **Fenced block detector** — collects lines between ` ```chart ` and ` ``` `, parses JSON, dispatches to chart renderer. Invalid JSON or unknown type → `_placeholder_box(msg)`.

2. **Image detector** — matches `![alt](src)` lines, resolves URI, fetches bytes, writes to temp file, returns `reportlab.platypus.Image(tmp, width=6.5*inch)` with aspect ratio preserved. Any failure → `_placeholder_box(msg)`.

**New private functions:**

```
_render_bar(spec: dict)          → Drawing
_render_hbar(spec: dict)         → Drawing
_render_line(spec: dict)         → Drawing
_render_pie(spec: dict)          → Drawing
_render_stacked_bar(spec: dict)  → Drawing
_fetch_image(src: str)           → bytes | None   (URL / local / notebooklm://)
_placeholder_box(msg: str)       → Table          (grey box with warning caption)
```

**ReportLab imports to add:**
```python
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.platypus import Image
```

### 4.3 `src/tools/notebooklm_reader.py`

New function:

```python
def fetch_notebook_image(notebook_id: str, filename: str) -> bytes | None:
    """
    Attempt to fetch raw image bytes for a named source file from a NotebookLM notebook
    via the notebooklm-mcp-cli MCP server (source_get_content tool).
    Returns None if unsupported, not found, or any error — caller renders placeholder.
    """
```

**Honest constraint:** `notebooklm-mcp-cli` uses Chrome browser automation. Whether `source_get_content` can return raw image bytes is untested and may not be supported. The function must never raise — it returns `None` on any failure.

---

## 5. URI Resolution in `_fetch_image()`

```
notebooklm://notebook-id/filename.png
  → calls fetch_notebook_image(notebook_id, filename)
  → returns bytes or None

https://... or http://...
  → urllib.request.urlopen(url, timeout=10)
  → returns bytes or None on any error

anything else
  → treated as local file path
  → open(path, "rb").read() or None if not found
```

---

## 6. Error Handling

All failures are non-fatal. PDF generation always completes.

| Scenario | Result |
|---|---|
| Invalid chart JSON | Placeholder: "Chart unavailable: invalid JSON" |
| Unknown chart type | Placeholder: "Chart unavailable: unknown type 'xxx'" |
| Chart missing required fields | Placeholder: "Chart unavailable: missing 'values'" |
| Image URL unreachable / timeout | Placeholder: "Image unavailable: [alt text]" |
| Local image file not found | Placeholder: "Image unavailable: [alt text]" |
| NotebookLM image unsupported/missing | Placeholder: "Image unavailable: [alt text]" |
| Image too large | Resized to fit 6.5-inch page width, aspect ratio preserved |

---

## 7. Testing

All tests are unit tests — zero API calls, all external calls mocked.

| Test | Coverage |
|---|---|
| `test_chart_bar` | Bar chart JSON → `Drawing` returned |
| `test_chart_hbar` | Horizontal bar chart → `Drawing` returned |
| `test_chart_line_multiseries` | Line chart with `series` → correct drawing |
| `test_chart_pie` | Pie chart → correct drawing |
| `test_chart_stacked_bar` | Stacked bar with `series` → correct drawing |
| `test_chart_invalid_json` | Malformed JSON → placeholder box, no exception |
| `test_chart_unknown_type` | `"type": "scatter"` → placeholder box |
| `test_chart_missing_fields` | Missing `values` → placeholder box |
| `test_image_local` | Local PNG path → `Image` flowable |
| `test_image_url` | Mock `urllib` → `Image` flowable |
| `test_image_missing_local` | Bad path → placeholder box |
| `test_image_url_timeout` | Mock `urllib` timeout → placeholder box |
| `test_image_notebooklm_unavailable` | `fetch_notebook_image` returns `None` → placeholder box |
| `test_image_notebooklm_success` | `fetch_notebook_image` returns bytes → `Image` flowable |
