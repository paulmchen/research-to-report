import pytest
from click.testing import CliRunner
from unittest.mock import patch


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

    with patch("main.run_preflight"), \
         patch("main.decompose_topic", return_value=["subtopic A", "subtopic B"]), \
         patch("main.run_parallel_research", return_value={"subtopic A": "findings A"}), \
         patch("main.synthesize", return_value={"executive_summary": "exec", "full_report": "full"}), \
         patch("main.generate_pdf", return_value=str(tmp_path / "report.pdf")):
        result = runner.invoke(cli, ["research", "AI trends", "--dry-run", "--config", cfg_path])

    assert result.exit_code == 0, result.output
