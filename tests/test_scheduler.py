import pytest
from unittest.mock import patch, MagicMock


def make_sched_cfg():
    return {
        "schedule": {
            "enabled": True,
            "cron": "0 8 * * MON",
            "timezone": "America/New_York",
            "topics": ["AI industry news", "Cybersecurity threats"],
        },
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096},
        "email": {"default_recipients": ["test@example.com"], "default_cc": []},
        "output_dir": "/tmp/reports",
        "notebooklm": {"notebook_ids": []},
        "timeouts": {"sub_agent_sec": 120, "synthesis_sec": 180,
                     "pdf_generation_sec": 60, "email_delivery_sec": 30, "total_run_sec": 600},
        "logging": {"level": "INFO", "log_to_file": False,
                    "log_file": "/tmp/agent.log", "max_file_size_mb": 1, "backup_count": 1},
        "audit": {"enabled": True, "log_file": "/tmp/audit.log", "format": "json"},
    }


def test_validate_cron_valid():
    from run.scheduler import validate_cron
    validate_cron("0 8 * * MON")  # should not raise


def test_validate_cron_invalid_raises_cfg002():
    from run.scheduler import validate_cron
    from config import ConfigError
    with pytest.raises(ConfigError, match="ERR-CFG-002"):
        validate_cron("not a cron expression")


def test_validate_cron_invalid_field_raises_cfg003():
    from run.scheduler import validate_cron
    from config import ConfigError
    with pytest.raises(ConfigError, match="ERR-CFG-003"):
        validate_cron("99 8 * * MON")  # minute 99 is invalid


def test_start_scheduler_disabled_exits_early():
    from run.scheduler import start_scheduler
    cfg = make_sched_cfg()
    cfg["schedule"]["enabled"] = False
    with patch("run.scheduler.BlockingScheduler") as mock_sched:
        start_scheduler(cfg)
        mock_sched.assert_not_called()
