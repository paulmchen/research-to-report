import pytest
import os
from unittest.mock import patch

def test_load_config_returns_dict(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
user_email: test@example.com
output_dir: ./reports
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
  log_to_file: true
  log_file: reports/logs/agent.log
  max_file_size_mb: 10
  backup_count: 5
audit:
  enabled: true
  log_file: reports/logs/audit.log
  format: json
""")
    from config import load_config
    cfg = load_config(str(cfg_file))
    assert cfg["user_email"] == "test@example.com"
    assert cfg["agent"]["default_model"] == "claude-sonnet-4-6"


def test_missing_config_raises_cfg001(tmp_path):
    from config import load_config, ConfigError
    with pytest.raises(ConfigError, match="ERR-CFG-001"):
        load_config(str(tmp_path / "nonexistent.yaml"))


def test_log_level_env_overrides_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("user_email: x@x.com\noutput_dir: ./reports\nagent:\n  default_model: claude-sonnet-4-6\n  max_tokens: 8096\nemail:\n  default_recipients: []\n  default_cc: []\nschedule:\n  enabled: false\n  cron: '0 8 * * MON'\n  timezone: America/New_York\n  topics: []\nnotebooklm:\n  notebook_ids: []\ntimeouts:\n  sub_agent_sec: 120\n  synthesis_sec: 180\n  pdf_generation_sec: 60\n  email_delivery_sec: 30\n  total_run_sec: 600\nlogging:\n  level: INFO\n  log_to_file: true\n  log_file: reports/logs/agent.log\n  max_file_size_mb: 10\n  backup_count: 5\naudit:\n  enabled: true\n  log_file: reports/logs/audit.log\n  format: json\n")
    from config import load_config
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
        cfg = load_config(str(cfg_file))
    assert cfg["logging"]["level"] == "DEBUG"


def test_audit_cannot_be_disabled(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("user_email: x@x.com\noutput_dir: ./reports\nagent:\n  default_model: claude-sonnet-4-6\n  max_tokens: 8096\nemail:\n  default_recipients: []\n  default_cc: []\nschedule:\n  enabled: false\n  cron: '0 8 * * MON'\n  timezone: America/New_York\n  topics: []\nnotebooklm:\n  notebook_ids: []\ntimeouts:\n  sub_agent_sec: 120\n  synthesis_sec: 180\n  pdf_generation_sec: 60\n  email_delivery_sec: 30\n  total_run_sec: 600\nlogging:\n  level: INFO\n  log_to_file: true\n  log_file: reports/logs/agent.log\n  max_file_size_mb: 10\n  backup_count: 5\naudit:\n  enabled: false\n  log_file: reports/logs/audit.log\n  format: json\n")
    from config import load_config
    cfg = load_config(str(cfg_file))
    assert cfg["audit"]["enabled"] is True
    captured = capsys.readouterr()
    assert "CFG-006" in captured.out
