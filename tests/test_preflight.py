import pytest
import os
from unittest.mock import patch, MagicMock


def make_cfg(model="claude-sonnet-4-6", recipients=None, notebook_ids=None):
    return {
        "user_email": "test@example.com",
        "output_dir": "/tmp/reports_test",
        "agent": {"default_model": model, "max_tokens": 8096},
        "email": {"default_recipients": recipients or ["test@example.com"], "default_cc": []},
        "schedule": {"enabled": False, "cron": "0 8 * * MON", "timezone": "America/New_York", "topics": []},
        "notebooklm": {"notebook_ids": notebook_ids or []},
        "timeouts": {"sub_agent_sec": 120, "synthesis_sec": 180,
                     "pdf_generation_sec": 60, "email_delivery_sec": 30, "total_run_sec": 600},
        "logging": {"level": "INFO", "log_to_file": False,
                    "log_file": "/tmp/agent.log", "max_file_size_mb": 1, "backup_count": 1},
        "audit": {"enabled": True, "log_file": "/tmp/audit.log", "format": "json"},
    }


def test_preflight_passes_with_all_mocked(tmp_path):
    from run.preflight import run_preflight, PreflightError
    cfg = make_cfg()
    cfg["output_dir"] = str(tmp_path / "reports")
    with patch("run.preflight.check_network", return_value=None), \
         patch("run.preflight.check_api_keys", return_value=None), \
         patch("run.preflight.check_output_dirs", return_value=None):
        run_preflight(cfg)  # should not raise


def test_invalid_email_raises_eml003():
    from run.preflight import validate_emails, PreflightError
    with pytest.raises(PreflightError, match="ERR-EML-003"):
        validate_emails(["not-an-email"])


def test_valid_emails_pass():
    from run.preflight import validate_emails
    validate_emails(["a@b.com", "c@d.org"])  # no exception


def test_dedup_to_and_cc():
    from run.preflight import merge_recipients
    to_list, cc_list, warnings = merge_recipients(
        config_to=["a@b.com", "c@d.com"],
        cli_to=["c@d.com", "e@f.com"],
        config_cc=["g@h.com"],
        cli_cc=["a@b.com"],   # same as TO → should be removed from CC
    )
    assert "a@b.com" in to_list
    assert "a@b.com" not in cc_list
    assert len(warnings) > 0  # EML-006 warning issued


def test_no_recipients_raises_eml005():
    from run.preflight import merge_recipients, PreflightError
    with pytest.raises(PreflightError, match="ERR-EML-005"):
        merge_recipients([], [], [], [])


def test_notebooklm_configured_no_google_credentials_needed():
    """No Google credentials are needed even when notebooklm.notebook_ids is set.
    The notebooklm-mcp-cli MCP server handles auth via its Chrome browser session."""
    from run.preflight import check_api_keys
    cfg = make_cfg(notebook_ids=["some-notebook-uuid"])
    env = {"ANTHROPIC_API_KEY": "test-key", "COMPOSIO_API_KEY": "composio-test-key"}
    with patch.dict(os.environ, env, clear=True):
        check_api_keys(cfg)  # should not raise


def test_composio_api_key_required():
    """COMPOSIO_API_KEY is always required for Gmail delivery."""
    from run.preflight import check_api_keys, PreflightError
    cfg = make_cfg(notebook_ids=[])
    env = {"ANTHROPIC_API_KEY": "test-key"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError, match="ERR-AUTH-008"):
            check_api_keys(cfg)


def _make_composio_mock(has_gmail: bool = True):
    """Return a mock Composio client with or without an active Gmail connection."""
    mock_account = MagicMock()
    mock_account.toolkit.slug = "gmail"
    mock_account.status = "ACTIVE"

    mock_accounts_list = MagicMock()
    mock_accounts_list.items = [mock_account] if has_gmail else []

    mock_composio = MagicMock()
    mock_composio._client.connected_accounts.list.return_value = mock_accounts_list
    return mock_composio


def test_check_composio_gmail_passes_when_gmail_connected():
    """check_composio_gmail must not raise when an active Gmail account exists."""
    from run.preflight import check_composio_gmail
    cfg = make_cfg()
    with patch.dict(os.environ, {"COMPOSIO_API_KEY": "test-key"}), \
         patch("run.preflight.Composio", return_value=_make_composio_mock(has_gmail=True)):
        check_composio_gmail(cfg)  # should not raise


def test_check_composio_gmail_raises_when_no_gmail_connection():
    """check_composio_gmail must raise ERR-AUTH-008 when no active Gmail connection exists."""
    from run.preflight import check_composio_gmail, PreflightError
    cfg = make_cfg()
    with patch.dict(os.environ, {"COMPOSIO_API_KEY": "test-key"}), \
         patch("run.preflight.Composio", return_value=_make_composio_mock(has_gmail=False)):
        with pytest.raises(PreflightError, match="ERR-AUTH-008") as exc_info:
            check_composio_gmail(cfg)
    assert "app.composio.dev" in str(exc_info.value)


def test_check_composio_gmail_raises_on_invalid_api_key():
    """check_composio_gmail must raise ERR-AUTH-008 when the Composio API key is rejected."""
    from run.preflight import check_composio_gmail, PreflightError
    cfg = make_cfg()
    mock_composio = MagicMock()
    mock_composio._client.connected_accounts.list.side_effect = Exception("Unauthorized")
    with patch.dict(os.environ, {"COMPOSIO_API_KEY": "bad-key"}), \
         patch("run.preflight.Composio", return_value=mock_composio):
        with pytest.raises(PreflightError, match="ERR-AUTH-008"):
            check_composio_gmail(cfg)


def test_check_composio_gmail_skipped_when_no_api_key():
    """check_composio_gmail must be a no-op when COMPOSIO_API_KEY is not set."""
    from run.preflight import check_composio_gmail
    cfg = make_cfg()
    with patch.dict(os.environ, {}, clear=True), \
         patch("run.preflight.Composio") as mock_cls:
        check_composio_gmail(cfg)
    mock_cls.assert_not_called()


def test_run_preflight_calls_check_composio_gmail(tmp_path):
    """run_preflight must invoke check_composio_gmail so the Gmail connection is verified."""
    from run.preflight import run_preflight
    cfg = make_cfg()
    cfg["output_dir"] = str(tmp_path / "reports")
    with patch("run.preflight.check_network"), \
         patch("run.preflight.check_api_keys"), \
         patch("run.preflight.check_output_dirs"), \
         patch("run.preflight.check_composio_gmail") as mock_gmail, \
         patch("run.preflight.check_notebooklm"):
        run_preflight(cfg)
    mock_gmail.assert_called_once_with(cfg)


def test_check_notebooklm_skipped_when_no_notebook_ids():
    """check_notebooklm must be a no-op when notebook_ids is empty."""
    from run.preflight import check_notebooklm
    cfg = make_cfg(notebook_ids=[])
    with patch("tools.notebooklm_reader.verify_notebooklm_auth") as mock_verify:
        check_notebooklm(cfg)
    mock_verify.assert_not_called()


def test_check_notebooklm_passes_when_auth_valid():
    """check_notebooklm must not raise when verify_notebooklm_auth succeeds."""
    from run.preflight import check_notebooklm
    cfg = make_cfg(notebook_ids=["nb-uuid-1"])
    with patch("tools.notebooklm_reader.verify_notebooklm_auth", return_value=None):
        check_notebooklm(cfg)  # should not raise


def test_check_notebooklm_raises_preflight_error_on_auth_expired():
    """Expired auth must surface as PreflightError ERR-AUTH-009 with nlm login hint."""
    from run.preflight import check_notebooklm, PreflightError
    from tools.notebooklm_reader import ToolError
    cfg = make_cfg(notebook_ids=["nb-uuid-1"])
    with patch("tools.notebooklm_reader.verify_notebooklm_auth",
               side_effect=ToolError("[ERR-AUTH-009] NotebookLM authentication expired. Run 'nlm login'...")):
        with pytest.raises(PreflightError, match="ERR-AUTH-009") as exc_info:
            check_notebooklm(cfg)
    assert "nlm login" in str(exc_info.value)


def test_check_notebooklm_raises_preflight_error_on_server_failure():
    """MCP server startup failure must surface as PreflightError ERR-NTB-003."""
    from run.preflight import check_notebooklm, PreflightError
    from tools.notebooklm_reader import ToolError
    cfg = make_cfg(notebook_ids=["nb-uuid-1"])
    with patch("tools.notebooklm_reader.verify_notebooklm_auth",
               side_effect=ToolError("[ERR-NTB-003] NotebookLM MCP server failed to start: FileNotFoundError")):
        with pytest.raises(PreflightError, match="ERR-NTB-003"):
            check_notebooklm(cfg)


def test_run_preflight_calls_check_notebooklm(tmp_path):
    """run_preflight must invoke check_notebooklm so auth is verified before research starts."""
    from run.preflight import run_preflight
    cfg = make_cfg(notebook_ids=["nb-uuid-1"])
    cfg["output_dir"] = str(tmp_path / "reports")
    with patch("run.preflight.check_network"), \
         patch("run.preflight.check_api_keys"), \
         patch("run.preflight.check_output_dirs"), \
         patch("run.preflight.check_notebooklm") as mock_ntb:
        run_preflight(cfg)
    mock_ntb.assert_called_once_with(cfg)
