import pytest
from unittest.mock import patch


def test_approval_y_returns_approved():
    from delivery.approval import request_approval
    with patch("builtins.input", return_value="y"):
        decision = request_approval("AI trends", ["a@b.com"], [], ["/tmp/report.pdf"])
    assert decision == "approved"


def test_approval_n_returns_declined():
    from delivery.approval import request_approval
    with patch("builtins.input", return_value="n"):
        decision = request_approval("AI trends", ["a@b.com"], [], ["/tmp/report.pdf"])
    assert decision == "declined"


def test_approval_invalid_then_y():
    from delivery.approval import request_approval
    with patch("builtins.input", side_effect=["x", "y"]):
        decision = request_approval("AI trends", ["a@b.com"], [], ["/tmp/report.pdf"])
    assert decision == "approved"


def test_approval_edit_then_y(tmp_path):
    from delivery.approval import request_approval
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"fake pdf")
    with patch("builtins.input", side_effect=["edit", "y"]), \
         patch("delivery.approval.open_pdf_viewer"):
        decision = request_approval("AI trends", ["a@b.com"], [], [pdf_path])
    assert decision == "approved"
