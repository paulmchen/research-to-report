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
