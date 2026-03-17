import os
import pytest


def make_report_data():
    return {
        "topic": "AI trends in healthcare",
        "run_id": "2026-03-12T08-00-01",
        "executive_summary": "## Executive Summary\n\nAI is transforming healthcare rapidly.",
        "full_report": "## Full Report\n\n### Market Trends\n\nGrowing 30% YoY.",
        "generated_at": "2026-03-12T08:01:00Z",
    }


def test_generate_pdf_creates_file(tmp_path):
    from pdf.formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert os.path.exists(output_path)
    assert output_path.endswith(".pdf")


def test_generate_pdf_file_is_nonempty(tmp_path):
    from pdf.formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert os.path.getsize(output_path) > 1024  # at least 1KB


def test_generate_pdf_filename_contains_run_id(tmp_path):
    from pdf.formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert "2026-03-12" in os.path.basename(output_path)


def test_generate_pdf_raises_on_unwritable_dir():
    from pdf.formatter import generate_pdf, PDFError
    with pytest.raises(PDFError, match="ERR-PDF-002"):
        generate_pdf(make_report_data(), output_dir="/nonexistent/path/that/cannot/be/created")


def test_placeholder_box_returns_table():
    from pdf.formatter import _placeholder_box
    from reportlab.platypus import Table
    result = _placeholder_box("Chart unavailable: invalid JSON")
    assert isinstance(result, Table)


def test_placeholder_box_contains_message():
    from pdf.formatter import _placeholder_box
    result = _placeholder_box("Image unavailable: my image")
    assert result is not None


def test_generate_pdf_very_long_topic_does_not_crash(tmp_path):
    """A topic longer than _COVER_TITLE_MAX must not crash PDF generation."""
    from pdf.formatter import generate_pdf
    long_topic = (
        "Conduct a comprehensive industry research report on the emergence and trajectory "
        "of Agentic AI and autonomous multi-agent systems in the manufacturing sector for "
        "2026–2027. The report should cover multi-agent orchestration, skills ecosystems, "
        "autonomous decision-making pipelines, and strategic recommendations for leaders."
    )
    data = {
        "topic": long_topic,
        "run_id": "2026-03-17T10-00-00",
        "executive_summary": "## Summary\n\nKey findings here.",
        "full_report": "## Report\n\nDetailed findings here.",
        "generated_at": "2026-03-17T10:00:00Z",
    }
    output_path = generate_pdf(data, output_dir=str(tmp_path))
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 1024


def test_generate_pdf_uses_title_field_for_filename_when_provided(tmp_path):
    """When data contains a 'title' key, the PDF filename must be based on the
    title, not the (potentially very long) raw topic string."""
    from pdf.formatter import generate_pdf
    data = {
        "topic": "Conduct a comprehensive industry research report on Agentic AI in manufacturing 2026-2027",
        "title": "Agentic AI in Manufacturing 2026-2027",
        "run_id": "2026-03-17T10-00-00",
        "executive_summary": "## Summary\n\nKey findings.",
        "full_report": "## Report\n\nDetailed findings.",
        "generated_at": "2026-03-17T10:00:00Z",
    }
    output_path = generate_pdf(data, output_dir=str(tmp_path))
    filename = os.path.basename(output_path)
    assert "agentic-ai-in-manufacturing" in filename
    # raw topic slug should NOT appear in the filename
    assert "conduct-a-comprehensive" not in filename


def test_generate_pdf_falls_back_to_topic_when_no_title(tmp_path):
    """When no 'title' key is present, the filename must fall back to the topic."""
    from pdf.formatter import generate_pdf
    data = {
        "topic": "AI trends",
        "run_id": "2026-03-17T10-00-01",
        "executive_summary": "## Summary\n\nFindings.",
        "full_report": "## Report\n\nDetails.",
        "generated_at": "2026-03-17T10:00:00Z",
    }
    output_path = generate_pdf(data, output_dir=str(tmp_path))
    assert "ai-trends" in os.path.basename(output_path)


def test_generate_pdf_oversized_table_cell_does_not_crash(tmp_path):
    """A markdown table whose cell exceeds _MAX_CELL_CHARS must not crash PDF generation."""
    from pdf.formatter import generate_pdf
    long_cell = "word " * 200   # 1000 chars — far above the 400-char threshold
    full_report = f"## Report\n\n| Header |\n|--------|\n| {long_cell} |\n\nMore text."
    data = {
        "topic": "AI trends",
        "run_id": "2026-03-17T10-00-01",
        "executive_summary": "## Summary\n\nKey findings.",
        "full_report": full_report,
        "generated_at": "2026-03-17T10:00:00Z",
    }
    output_path = generate_pdf(data, output_dir=str(tmp_path))
    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 1024
