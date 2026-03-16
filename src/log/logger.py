import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


def setup_loggers(cfg: dict) -> tuple[logging.Logger, logging.Logger]:
    log_cfg = cfg.get("logging", {})

    level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)

    agent_logger = logging.getLogger("agent")
    agent_logger.setLevel(level)
    agent_logger.handlers.clear()

    if log_cfg.get("log_to_file", True):
        log_file = log_cfg.get("log_file", "reports/logs/agent.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handler = RotatingFileHandler(
            log_file,
            maxBytes=log_cfg.get("max_file_size_mb", 10) * 1024 * 1024,
            backupCount=log_cfg.get("backup_count", 5),
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        agent_logger.addHandler(handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    agent_logger.addHandler(console)

    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)

    return agent_logger, audit_logger


def write_audit(audit_path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(audit_path) if os.path.dirname(audit_path) else ".", exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **data}
    with open(audit_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
