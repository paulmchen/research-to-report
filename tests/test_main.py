import json
import os
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock


def _write_config(tmp_path) -> str:
    cfg_content = f"""
user_email: test@example.com
output_dir: {str(tmp_path / "reports").replace(chr(92), "/")}
agent:
  default_model: claude-sonnet-4-6
  max_tokens: 8096
email:
  default_recipients:
    - test@example.com
  default_cc: []
schedule:
  enabled: false
  cron: "0 8 * * MON"
  timezone: "America/New_York"
  topics: []
notebooklm:
  notebook_ids: []
timeouts:
  sub_agent_sec: 120
  synthesis_sec: 180
  pdf_generation_sec: 60
  email_delivery_sec: 30
  total_run_sec: 600
logging:
  level: INFO
  log_to_file: false
  log_file: {str(tmp_path / "agent.log").replace(chr(92), "/")}
  max_file_size_mb: 1
  backup_count: 1
audit:
  enabled: true
  log_file: {str(tmp_path / "audit.log").replace(chr(92), "/")}
  format: json
"""
    cfg_path = str(tmp_path / "config.yaml")
    with open(cfg_path, "w") as f:
        f.write(cfg_content)
    return cfg_path


def test_research_command_exists():
    from main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["research", "--help"])
    assert result.exit_code == 0
    assert "TOPIC" in result.output or "topic" in result.output.lower()


def test_scheduler_command_exists():
    from main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["scheduler", "--help"])
    assert result.exit_code == 0


def test_resume_command_exists():
    from main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["resume", "--help"])
    assert result.exit_code == 0


def test_dry_run_flag_runs_without_api_calls(tmp_path):
    from main import cli
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)

    with patch("main.run_preflight"), \
         patch("main.decompose_topic", return_value=["subtopic A", "subtopic B"]), \
         patch("main.run_parallel_research", return_value={"subtopic A": "findings A"}), \
         patch("main.synthesize", return_value={"executive_summary": "exec", "full_report": "full"}), \
         patch("main.generate_pdf", return_value=str(tmp_path / "report.pdf")):
        result = runner.invoke(cli, ["research", "AI trends", "--dry-run", "--config", cfg_path])

    assert result.exit_code == 0, result.output


def test_email_failure_sets_email_failed_state(tmp_path):
    """When email delivery fails, run state must be EMAIL_FAILED (not COMPLETED)."""
    from main import cli
    from delivery.email_sender import EmailError
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)
    pdf_path = str(tmp_path / "report.pdf")

    with patch("main.run_preflight"), \
         patch("main.decompose_topic", return_value=["sub A"]), \
         patch("main.run_parallel_research", return_value={"sub A": "findings"}), \
         patch("main.synthesize", return_value={"executive_summary": "exec", "full_report": "full"}), \
         patch("main.generate_pdf", return_value=pdf_path), \
         patch("main.request_approval", return_value="approved"), \
         patch("main.send_report_email", side_effect=EmailError("[ERR-EML-002] delivery failed")):
        result = runner.invoke(cli, ["research", "AI trends", "--config", cfg_path])

    state_dir = str(tmp_path / "reports" / "state")
    state_files = [f for f in os.listdir(state_dir) if f.startswith("master-")]
    assert state_files, "No state file written"
    with open(os.path.join(state_dir, state_files[0])) as f:
        state = json.load(f)

    assert state["status"] == "EMAIL_FAILED"
    assert state["email"]["status"] == "FAILED"
    assert state["pdf"]["files"] == [pdf_path]


def test_email_success_sets_completed_state(tmp_path):
    """When email delivery succeeds, run state must be COMPLETED."""
    from main import cli
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)
    pdf_path = str(tmp_path / "report.pdf")

    with patch("main.run_preflight"), \
         patch("main.decompose_topic", return_value=["sub A"]), \
         patch("main.run_parallel_research", return_value={"sub A": "findings"}), \
         patch("main.synthesize", return_value={"executive_summary": "exec", "full_report": "full"}), \
         patch("main.generate_pdf", return_value=pdf_path), \
         patch("main.request_approval", return_value="approved"), \
         patch("main.send_report_email", return_value={"id": "msg-1"}):
        result = runner.invoke(cli, ["research", "AI trends", "--config", cfg_path])

    state_dir = str(tmp_path / "reports" / "state")
    state_files = [f for f in os.listdir(state_dir) if f.startswith("master-")]
    with open(os.path.join(state_dir, state_files[0])) as f:
        state = json.load(f)

    assert state["status"] == "COMPLETED"
    assert state["email"]["status"] == "COMPLETED"


def test_resume_retries_email_for_email_failed_run(tmp_path):
    """resume goes directly to the email step — no research/synthesis/PDF re-run."""
    from main import cli
    from log.state import create_master_state, update_master_state, load_state
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)

    state_dir = str(tmp_path / "reports" / "state")
    pdf_path = str(tmp_path / "report.pdf")
    run_id = "2026-03-17T10-00-00"

    # Seed an EMAIL_FAILED run with saved PDF paths
    create_master_state(run_id, "AI trends", "ad-hoc", state_dir)
    update_master_state(run_id, state_dir, {
        "status": "EMAIL_FAILED",
        "email": {"status": "FAILED", "error": "previous error"},
        "pdf": {"status": "COMPLETED", "files": [pdf_path]},
    })

    with patch("main.request_approval", return_value="approved"), \
         patch("main.send_report_email", return_value={"id": "msg-1"}) as mock_send, \
         patch("main.decompose_topic") as mock_decompose, \
         patch("main.run_parallel_research") as mock_research, \
         patch("main.synthesize") as mock_synthesize, \
         patch("main.generate_pdf") as mock_pdf:
        result = runner.invoke(cli, ["resume", "--config", cfg_path])

    assert result.exit_code == 0, result.output

    # Email sent with the PDF paths that were saved in state — not a new PDF
    mock_send.assert_called_once()
    call_args = mock_send.call_args
    assert call_args.kwargs.get("pdf_paths") == [pdf_path] or call_args.args[0] == [pdf_path]

    # Research/synthesis/PDF generation must NOT have been triggered
    mock_decompose.assert_not_called()
    mock_research.assert_not_called()
    mock_synthesize.assert_not_called()
    mock_pdf.assert_not_called()

    # State must be COMPLETED after successful retry
    state = load_state(run_id, state_dir)
    assert state["status"] == "COMPLETED"
    assert state["email"]["status"] == "COMPLETED"


def test_resume_no_retry_when_user_declines(tmp_path):
    """resume must not send email when user declines at the approval prompt."""
    from main import cli
    from log.state import create_master_state, update_master_state, load_state
    runner = CliRunner()
    cfg_path = _write_config(tmp_path)

    state_dir = str(tmp_path / "reports" / "state")
    pdf_path = str(tmp_path / "report.pdf")
    run_id = "2026-03-17T10-00-01"

    create_master_state(run_id, "AI trends", "ad-hoc", state_dir)
    update_master_state(run_id, state_dir, {
        "status": "EMAIL_FAILED",
        "pdf": {"status": "COMPLETED", "files": [pdf_path]},
    })

    with patch("main.request_approval", return_value="declined"), \
         patch("main.send_report_email") as mock_send:
        result = runner.invoke(cli, ["resume", "--config", cfg_path])

    mock_send.assert_not_called()
    state = load_state(run_id, state_dir)
    assert state["status"] == "EMAIL_FAILED"  # unchanged
