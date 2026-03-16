import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_send_email_calls_composio(tmp_path):
    from delivery.email_sender import send_report_email
    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 fake content")

    with patch("delivery.email_sender._send_via_composio") as mock_send:
        mock_send.return_value = {"id": "msg123", "threadId": "thread456"}
        result = send_report_email(
            pdf_paths=[pdf_path], topic="AI trends",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-001",
        )
    mock_send.assert_called_once()
    assert result["id"] == "msg123"


def test_send_email_prevents_duplicate(tmp_path):
    from delivery.email_sender import send_report_email, EmailError
    audit_log = str(tmp_path / "audit.log")
    with open(audit_log, "w") as f:
        f.write(json.dumps({"event": "EMAIL_SENT", "run_id": "run-001"}) + "\n")

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with pytest.raises(EmailError, match="ERR-EML-004"):
        send_report_email(
            pdf_paths=[pdf_path], topic="AI trends",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-001",
        )


def test_send_email_raises_on_missing_recipients(tmp_path):
    from delivery.email_sender import send_report_email, EmailError
    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with pytest.raises(EmailError, match="ERR-EML-005"):
        send_report_email(
            pdf_paths=[pdf_path], topic="AI trends",
            to_list=[], cc_list=[],
            audit_log_path=audit_log, run_id="run-002",
        )
