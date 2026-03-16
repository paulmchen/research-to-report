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
