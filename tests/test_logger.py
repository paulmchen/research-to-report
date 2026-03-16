import json
import os
import logging
import pytest

def test_get_agent_logger_uses_configured_level(tmp_path):
    from log.logger import setup_loggers
    cfg = {
        "logging": {
            "level": "DEBUG",
            "log_to_file": True,
            "log_file": str(tmp_path / "agent.log"),
            "max_file_size_mb": 1,
            "backup_count": 1,
        },
        "audit": {
            "enabled": True,
            "log_file": str(tmp_path / "audit.log"),
            "format": "json",
        }
    }
    agent_log, audit_log = setup_loggers(cfg)
    assert agent_log.level == logging.DEBUG


def test_audit_log_writes_json_line(tmp_path):
    from log.logger import setup_loggers, write_audit
    cfg = {
        "logging": {
            "level": "INFO",
            "log_to_file": True,
            "log_file": str(tmp_path / "agent.log"),
            "max_file_size_mb": 1,
            "backup_count": 1,
        },
        "audit": {
            "enabled": True,
            "log_file": str(tmp_path / "audit.log"),
            "format": "json",
        }
    }
    agent_log, audit_log = setup_loggers(cfg)
    audit_path = str(tmp_path / "audit.log")
    write_audit(audit_path, {"event": "TEST_EVENT", "topic": "test"})
    with open(audit_path) as f:
        line = json.loads(f.readline())
    assert line["event"] == "TEST_EVENT"
    assert "timestamp" in line


def test_audit_log_appends_not_overwrites(tmp_path):
    from log.logger import setup_loggers, write_audit
    cfg = {
        "logging": {"level": "INFO", "log_to_file": True,
                    "log_file": str(tmp_path / "agent.log"),
                    "max_file_size_mb": 1, "backup_count": 1},
        "audit": {"enabled": True, "log_file": str(tmp_path / "audit.log"), "format": "json"}
    }
    setup_loggers(cfg)
    audit_path = str(tmp_path / "audit.log")
    write_audit(audit_path, {"event": "FIRST"})
    write_audit(audit_path, {"event": "SECOND"})
    with open(audit_path) as f:
        lines = f.readlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "FIRST"
    assert json.loads(lines[1])["event"] == "SECOND"
