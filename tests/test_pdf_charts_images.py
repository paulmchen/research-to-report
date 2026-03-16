import pytest
from unittest.mock import patch, MagicMock


# ── _fetch_image ──────────────────────────────────────────────────────────────

def test_fetch_image_local_file(tmp_path):
    from pdf.formatter import _fetch_image
    img_file = tmp_path / "test.png"
    img_file.write_bytes(b"fake image data")
    result = _fetch_image(str(img_file))
    assert result == b"fake image data"


def test_fetch_image_local_missing_returns_none():
    from pdf.formatter import _fetch_image
    result = _fetch_image("/nonexistent/path/image.png")
    assert result is None


def test_fetch_image_url_success():
    from pdf.formatter import _fetch_image
    mock_resp = MagicMock()
    mock_resp.read.return_value = b"url image bytes"
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _fetch_image("https://example.com/chart.png")
    assert result == b"url image bytes"


def test_fetch_image_url_failure_returns_none():
    from pdf.formatter import _fetch_image
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        result = _fetch_image("https://example.com/chart.png")
    assert result is None


def test_fetch_image_notebooklm_delegates():
    from pdf.formatter import _fetch_image
    with patch("tools.notebooklm_reader.fetch_notebook_image", return_value=b"nb img") as mock_fn:
        result = _fetch_image("notebooklm://my-notebook-id/diagram.png")
    mock_fn.assert_called_once_with("my-notebook-id", "diagram.png")
    assert result == b"nb img"


def test_fetch_image_notebooklm_unavailable_returns_none():
    from pdf.formatter import _fetch_image
    with patch("tools.notebooklm_reader.fetch_notebook_image", return_value=None):
        result = _fetch_image("notebooklm://nb-id/image.png")
    assert result is None


# ── Chart renderers ───────────────────────────────────────────────────────────

def test_render_bar_returns_drawing():
    from pdf.formatter import _render_bar
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["North America", "Asia", "Europe"], "values": [42, 35, 23]}
    assert isinstance(_render_bar(spec), Drawing)


def test_render_bar_with_title():
    from pdf.formatter import _render_bar
    from reportlab.graphics.shapes import Drawing
    spec = {"title": "Market Share", "labels": ["A", "B"], "values": [60, 40]}
    assert isinstance(_render_bar(spec), Drawing)


def test_render_hbar_returns_drawing():
    from pdf.formatter import _render_hbar
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["Product A", "Product B", "Product C"], "values": [45, 30, 25]}
    assert isinstance(_render_hbar(spec), Drawing)


def test_render_pie_returns_drawing():
    from pdf.formatter import _render_pie
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["Cloud", "On-Prem", "Hybrid"], "values": [55, 25, 20]}
    assert isinstance(_render_pie(spec), Drawing)


def test_render_pie_zero_values_no_crash():
    from pdf.formatter import _render_pie
    from reportlab.graphics.shapes import Drawing
    spec = {"labels": ["A", "B"], "values": [0, 0]}
    assert isinstance(_render_pie(spec), Drawing)


def test_render_line_returns_drawing():
    from pdf.formatter import _render_line
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
    from pdf.formatter import _render_stacked_bar
    from reportlab.graphics.shapes import Drawing
    spec = {
        "labels": ["Q1", "Q2", "Q3"],
        "series": [
            {"name": "Product A", "values": [10, 15, 12]},
            {"name": "Product B", "values": [8, 11, 14]},
        ],
    }
    assert isinstance(_render_stacked_bar(spec), Drawing)


# ── Chart block detection ─────────────────────────────────────────────────────

def test_md_chart_bar_renders_drawing():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.graphics.shapes import Drawing
    md = '```chart\n{"type": "bar", "labels": ["A", "B"], "values": [10, 20]}\n```'
    drawings = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Drawing)]
    assert len(drawings) == 1


def test_md_chart_invalid_json_renders_placeholder():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\nnot valid json\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1


def test_md_chart_unknown_type_renders_placeholder():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\n{"type": "scatter", "labels": ["A"], "values": [1]}\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1


def test_md_chart_missing_values_renders_placeholder():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    md = '```chart\n{"type": "bar", "labels": ["A", "B"]}\n```'
    tables = [f for f in _md_to_flowables(md, _styles()) if isinstance(f, Table)]
    assert len(tables) == 1


# ── Image detection ───────────────────────────────────────────────────────────

def test_md_image_success_renders_image_flowable():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Image as RLImage
    import os
    tmp_files = []
    with patch("pdf.formatter._fetch_image", return_value=b"fake bytes"):
        flowables = _md_to_flowables("![My Chart](https://example.com/img.png)", _styles(), tmp_files)
    for f in tmp_files:
        try: os.unlink(f)
        except Exception: pass
    assert any(isinstance(f, RLImage) for f in flowables)


def test_md_image_fetch_failure_renders_placeholder():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    with patch("pdf.formatter._fetch_image", return_value=None):
        flowables = _md_to_flowables("![Missing Image](/bad/path.png)", _styles())
    assert any(isinstance(f, Table) for f in flowables)


def test_md_image_notebooklm_unavailable_renders_placeholder():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Table
    with patch("pdf.formatter._fetch_image", return_value=None):
        flowables = _md_to_flowables(
            "![Diagram](notebooklm://nb-id/diagram.png)", _styles()
        )
    assert any(isinstance(f, Table) for f in flowables)


def test_md_image_caption_rendered():
    from pdf.formatter import _md_to_flowables, _styles
    from reportlab.platypus import Paragraph
    import os
    tmp_files = []
    with patch("pdf.formatter._fetch_image", return_value=b"fake bytes"):
        flowables = _md_to_flowables(
            "![Figure 1: AI Investment](https://x.com/img.png)", _styles(), tmp_files
        )
    for f in tmp_files:
        try: os.unlink(f)
        except Exception: pass
    assert any(isinstance(f, Paragraph) and "Figure 1" in f.text for f in flowables)
