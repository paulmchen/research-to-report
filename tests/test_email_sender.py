import json
import os
import pytest
from unittest.mock import patch, MagicMock, call


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


def _make_composio_mock(response: dict):
    """Build a fully-mocked Composio client that returns the given execute response."""
    mock_account = MagicMock()
    mock_account.toolkit.slug = "gmail"
    mock_account.status = "ACTIVE"
    mock_account.id = "acct-123"
    mock_account.user_id = "user-456"

    mock_accounts_list = MagicMock()
    mock_accounts_list.items = [mock_account]

    mock_composio = MagicMock()
    mock_composio._client.connected_accounts.list.return_value = mock_accounts_list
    mock_composio.tools.execute.return_value = response
    return mock_composio, mock_account


def test_send_via_composio_execute_call(tmp_path):
    """_send_via_composio pre-populates _tool_schemas then calls tools.execute()
    so that substitute_file_uploads converts the attachment path correctly."""
    from delivery.email_sender import _send_via_composio

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    mock_composio, mock_account = _make_composio_mock(
        {"successful": True, "data": {"id": "msg-789"}, "error": None}
    )

    with patch("delivery.email_sender.Composio", return_value=mock_composio):
        result = _send_via_composio(
            to_list=["a@b.com", "b@b.com"],
            cc_list=["cc@b.com"],
            subject="Research Report: AI trends",
            body="Please find attached...",
            pdf_paths=[pdf_path],
            api_key="fake-key",
        )

    # Schema pre-population: retrieve must have been called to fetch the tool schema
    mock_composio._client.tools.retrieve.assert_called_once_with(tool_slug="GMAIL_SEND_EMAIL")

    mock_composio.tools.execute.assert_called_once_with(
        slug="GMAIL_SEND_EMAIL",
        arguments={
            "recipient_email": "a@b.com",
            "extra_recipients": ["b@b.com"],
            "cc": ["cc@b.com"],
            "subject": "Research Report: AI trends",
            "body": "Please find attached...",
            "attachment": pdf_path,
        },
        connected_account_id="acct-123",
        user_id="user-456",
    )
    assert result == {"id": "msg-789"}


def test_send_via_composio_raises_on_failed_response(tmp_path):
    """_send_via_composio raises EmailError when execute() returns successful=False."""
    from delivery.email_sender import _send_via_composio, EmailError

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    mock_composio, _ = _make_composio_mock(
        {"successful": False, "data": {}, "error": "quota exceeded"}
    )

    with patch("delivery.email_sender.Composio", return_value=mock_composio):
        with pytest.raises(EmailError, match="ERR-EML-002"):
            _send_via_composio(
                to_list=["a@b.com"], cc_list=[],
                subject="s", body="b",
                pdf_paths=[pdf_path], api_key="fake-key",
            )


def test_send_via_composio_raises_when_no_gmail_account(tmp_path):
    """_send_via_composio raises EmailError when no active Gmail account is found."""
    from delivery.email_sender import _send_via_composio, EmailError

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    mock_composio = MagicMock()
    mock_accounts_list = MagicMock()
    mock_accounts_list.items = []  # no connected accounts
    mock_composio._client.connected_accounts.list.return_value = mock_accounts_list

    with patch("delivery.email_sender.Composio", return_value=mock_composio):
        with pytest.raises(EmailError, match="ERR-AUTH-008"):
            _send_via_composio(
                to_list=["a@b.com"], cc_list=[],
                subject="s", body="b",
                pdf_paths=[pdf_path], api_key="fake-key",
            )


def test_send_report_email_uses_title_for_subject_when_provided(tmp_path):
    """When a title is supplied, the email subject and body must use it, not the raw topic."""
    from delivery.email_sender import send_report_email

    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with patch("delivery.email_sender._send_via_composio") as mock_send:
        mock_send.return_value = {"id": "msg-1"}
        send_report_email(
            pdf_paths=[pdf_path],
            topic="Conduct a comprehensive industry research report on Agentic AI in manufacturing 2026-2027",
            title="Agentic AI in Manufacturing 2026-2027",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-title-01",
        )

    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["subject"] == "Research Report: Agentic AI in Manufacturing 2026-2027"
    assert "Agentic AI in Manufacturing 2026-2027" in call_kwargs["body"]
    assert "Conduct a comprehensive" not in call_kwargs["subject"]


def test_send_report_email_falls_back_to_topic_when_no_title(tmp_path):
    """When no title is given, the email subject must use the raw topic."""
    from delivery.email_sender import send_report_email

    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with patch("delivery.email_sender._send_via_composio") as mock_send:
        mock_send.return_value = {"id": "msg-2"}
        send_report_email(
            pdf_paths=[pdf_path], topic="AI trends",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-title-02",
        )

    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["subject"] == "Research Report: AI trends"


def test_send_via_composio_raises_on_missing_api_key(tmp_path):
    """_send_via_composio raises EmailError when no API key is available."""
    from delivery.email_sender import _send_via_composio, EmailError

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("COMPOSIO_API_KEY", None)
        with pytest.raises(EmailError, match="ERR-AUTH-008"):
            _send_via_composio(
                to_list=["a@b.com"], cc_list=[],
                subject="s", body="b",
                pdf_paths=[pdf_path], api_key=None,
            )
