# Research-to-Report Agent — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an autonomous agent that accepts a research topic, spawns parallel sub-agents to gather web (and optionally NotebookLM) data, synthesizes findings into a PDF, and delivers it via Gmail — supporting both ad-hoc (with human approval) and scheduled runs.

**Architecture:** An Orchestrator agent decomposes a topic into N subtopics, launches parallel Research sub-agents (one per subtopic), monitors heartbeats, collects results, passes them to a Synthesis agent, generates a PDF via ReportLab, and delivers via Gmail MCP. Each agent owns its own state file — zero file-locking contention in v1. NotebookLM is optional: if `notebooklm.notebook_ids` is empty in config, research agents do web search only.

**Tech Stack:** Python 3.11+, LiteLLM (claude-sonnet-4-6 default), Tavily (web search), notebooklm-mcp-cli MCP server (NotebookLM — optional, browser automation), ReportLab (PDF), Composio Gmail (email delivery), APScheduler (cron), Click (CLI), pypdf (PDF text extraction), mcp Python client (MCP protocol), pytest (tests)

---

## Prerequisites

Install Python 3.11+. All API keys go in `.env` (never committed). Read the design doc at `docs/plans/2026-03-12-research-to-report-design.md` before starting — it has every error code, state schema, and config field you'll need.

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `src/tools/__init__.py`
  _(Note: `src/__init__.py` is NOT created — `src/` is the package root, not a package. See 2026-03-16 refactor note at bottom.)_
- Create: `tests/__init__.py`
- Create: `reports/logs/.gitkeep`
- Create: `reports/state/archive/.gitkeep`
- Create: `.gitignore`

**Step 1: Create `requirements.txt`**

```
litellm>=1.30.0
tavily-python>=0.3.0
mcp>=1.0.0
reportlab>=4.1.0
pypdf>=4.0.0
composio>=1.0.0rc2
apscheduler>=3.10.0
click>=8.1.0
pyyaml>=6.0
python-dotenv>=1.0.0
filelock>=3.13.0
pytest>=8.0.0
pytest-mock>=3.12.0
requests>=2.31.0
```

**Step 2: Install dependencies**

```bash
pip install -r requirements.txt
```

Expected: all packages install with no errors.

**Step 3: Create `.env.example`**

```
ANTHROPIC_API_KEY=...         # required if using Claude models
GOOGLE_API_KEY=...            # required if using Gemini models
OPENAI_API_KEY=...            # required if using GPT models
TAVILY_API_KEY=...            # required (web search)
COMPOSIO_API_KEY=...          # required (Gmail delivery via Composio)
LOG_LEVEL=INFO
# NotebookLM: no API key needed — auth handled by notebooklm-mcp-cli Chrome session
```

**Step 4: Create `config.yaml`**

```yaml
user_email: you@gmail.com
output_dir: ./reports

agent:
  default_model: claude-sonnet-4-6
  max_tokens: 8096
  max_subtopics: 5          # number of parallel research agents to spawn

email:
  default_recipients:
    - you@gmail.com
  default_cc: []

schedule:
  enabled: false
  cron: "0 8 * * MON"
  timezone: "America/New_York"
  topics:
    - "AI industry news"

notebooklm:
  notebook_ids: []   # leave empty to use web search only

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
```

**Step 5: Create `.gitignore`**

```
.env
*.pyc
__pycache__/
reports/logs/*.log
reports/state/*.json
reports/*.pdf
credentials.json
```

**Step 6: Create empty `__init__.py` files**

```bash
touch src/__init__.py src/tools/__init__.py tests/__init__.py
touch reports/logs/.gitkeep reports/state/archive/.gitkeep
```

**Step 7: Commit**

```bash
git init
git add requirements.txt .env.example config.yaml .gitignore src/ tests/ reports/
git commit -m "chore: project scaffold — structure, deps, config template"
```

---

### Task 2: Config Loader

**Files:**
- Create: `src/config.py`
- Create: `tests/test_config.py`

The config loader reads `config.yaml`, merges with environment variables, and validates required fields. It does NOT make any API calls.

**Step 1: Write the failing tests**

```python
# tests/test_config.py
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
    from src.config import load_config
    cfg = load_config(str(cfg_file))
    assert cfg["user_email"] == "test@example.com"
    assert cfg["agent"]["default_model"] == "claude-sonnet-4-6"


def test_missing_config_raises_cfg001(tmp_path):
    from src.config import load_config, ConfigError
    with pytest.raises(ConfigError, match="CFG-001"):
        load_config(str(tmp_path / "nonexistent.yaml"))


def test_log_level_env_overrides_config(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("user_email: x@x.com\noutput_dir: ./reports\nagent:\n  default_model: claude-sonnet-4-6\n  max_tokens: 8096\nemail:\n  default_recipients: []\n  default_cc: []\nschedule:\n  enabled: false\n  cron: '0 8 * * MON'\n  timezone: America/New_York\n  topics: []\nnotebooklm:\n  notebook_ids: []\ntimeouts:\n  sub_agent_sec: 120\n  synthesis_sec: 180\n  pdf_generation_sec: 60\n  email_delivery_sec: 30\n  total_run_sec: 600\nlogging:\n  level: INFO\n  log_to_file: true\n  log_file: reports/logs/agent.log\n  max_file_size_mb: 10\n  backup_count: 5\naudit:\n  enabled: true\n  log_file: reports/logs/audit.log\n  format: json\n")
    from src.config import load_config
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
        cfg = load_config(str(cfg_file))
    assert cfg["logging"]["level"] == "DEBUG"


def test_audit_cannot_be_disabled(tmp_path, capsys):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("user_email: x@x.com\noutput_dir: ./reports\nagent:\n  default_model: claude-sonnet-4-6\n  max_tokens: 8096\nemail:\n  default_recipients: []\n  default_cc: []\nschedule:\n  enabled: false\n  cron: '0 8 * * MON'\n  timezone: America/New_York\n  topics: []\nnotebooklm:\n  notebook_ids: []\ntimeouts:\n  sub_agent_sec: 120\n  synthesis_sec: 180\n  pdf_generation_sec: 60\n  email_delivery_sec: 30\n  total_run_sec: 600\nlogging:\n  level: INFO\n  log_to_file: true\n  log_file: reports/logs/agent.log\n  max_file_size_mb: 10\n  backup_count: 5\naudit:\n  enabled: false\n  log_file: reports/logs/audit.log\n  format: json\n")
    from src.config import load_config
    cfg = load_config(str(cfg_file))
    assert cfg["audit"]["enabled"] is True
    captured = capsys.readouterr()
    assert "CFG-006" in captured.out
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: `ImportError` — `src.config` does not exist yet.

**Step 3: Implement `src/config.py`**

```python
import os
import yaml


class ConfigError(Exception):
    pass


def load_config(path: str = "config.yaml") -> dict:
    if not os.path.exists(path):
        raise ConfigError(f"[ERR-CFG-001] config.yaml not found at: {path}")

    with open(path, "r") as f:
        cfg = yaml.safe_load(f)

    # ENV override: log level
    env_level = os.environ.get("LOG_LEVEL")
    if env_level:
        cfg.setdefault("logging", {})["level"] = env_level

    # Audit cannot be disabled
    if not cfg.get("audit", {}).get("enabled", True):
        print("Warning [WRN-CFG-006]: Audit logging cannot be disabled. Agent actions will always be recorded.")
        cfg["audit"]["enabled"] = True

    return cfg
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: config loader with CFG-001 and CFG-006 enforcement"
```

---

### Task 3: Logging Setup

**Files:**
- Create: `src/logger.py`
- Create: `tests/test_logger.py`

Two loggers: rotating `agent.log` (configurable level) and append-only `audit.log` (structured JSON, always on).

**Step 1: Write the failing tests**

```python
# tests/test_logger.py
import json
import os
import logging
import pytest

def test_get_agent_logger_uses_configured_level(tmp_path):
    from src.logger import setup_loggers
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
    from src.logger import setup_loggers, write_audit
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
    from src.logger import setup_loggers, write_audit
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
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_logger.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/logger.py`**

```python
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


def setup_loggers(cfg: dict) -> tuple[logging.Logger, logging.Logger]:
    log_cfg = cfg.get("logging", {})
    audit_cfg = cfg.get("audit", {})

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
```

**Step 4: Run tests**

```bash
pytest tests/test_logger.py -v
```

Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add src/logger.py tests/test_logger.py
git commit -m "feat: agent + audit logging with rotation and JSON append"
```

---

### Task 4: State Management

**Files:**
- Create: `src/state.py`
- Create: `tests/test_state.py`

State files track run progress and enable resume. Each sub-agent owns its own file. Orchestrator owns the master file. See design doc Section 7 for the full JSON schema.

**Step 1: Write the failing tests**

```python
# tests/test_state.py
import json
import os
import pytest
from datetime import datetime, timezone


def test_create_master_state(tmp_path):
    from src.state import create_master_state, load_state
    run_id = "2026-03-12T08-00-01"
    state_dir = str(tmp_path / "state")
    state = create_master_state(run_id, "AI trends", "ad-hoc", state_dir)
    assert state["run_id"] == run_id
    assert state["status"] == "IN_PROGRESS"
    assert state["topic"] == "AI trends"
    path = os.path.join(state_dir, f"{run_id}-master.json")
    assert os.path.exists(path)


def test_update_master_state(tmp_path):
    from src.state import create_master_state, update_master_state, load_state
    run_id = "2026-03-12T08-00-02"
    state_dir = str(tmp_path / "state")
    create_master_state(run_id, "topic", "ad-hoc", state_dir)
    update_master_state(run_id, state_dir, {"status": "COMPLETED"})
    state = load_state(run_id, state_dir)
    assert state["status"] == "COMPLETED"


def test_create_subtopic_state(tmp_path):
    from src.state import create_subtopic_state, load_subtopic_state
    run_id = "2026-03-12T08-00-03"
    state_dir = str(tmp_path / "state")
    state = create_subtopic_state(run_id, 1, "market trends", state_dir)
    assert state["status"] == "IN_PROGRESS"
    assert state["topic"] == "market trends"
    path = os.path.join(state_dir, f"{run_id}-subtopic-1.json")
    assert os.path.exists(path)


def test_update_heartbeat(tmp_path):
    from src.state import create_subtopic_state, update_heartbeat, load_subtopic_state
    run_id = "2026-03-12T08-00-04"
    state_dir = str(tmp_path / "state")
    create_subtopic_state(run_id, 1, "topic", state_dir)
    update_heartbeat(run_id, 1, state_dir)
    state = load_subtopic_state(run_id, 1, state_dir)
    assert state["last_heartbeat"] is not None


def test_find_incomplete_runs(tmp_path):
    from src.state import create_master_state, find_incomplete_runs
    state_dir = str(tmp_path / "state")
    create_master_state("run-001", "topic A", "ad-hoc", state_dir)
    create_master_state("run-002", "topic B", "scheduled", state_dir)
    runs = find_incomplete_runs(state_dir)
    assert len(runs) == 2
    assert any(r["run_id"] == "run-001" for r in runs)
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_state.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/state.py`**

```python
import json
import os
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _master_path(run_id: str, state_dir: str) -> str:
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"{run_id}-master.json")


def _subtopic_path(run_id: str, idx: int, state_dir: str) -> str:
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"{run_id}-subtopic-{idx}.json")


def _write(path: str, data: dict) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _read(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def create_master_state(run_id: str, topic: str, mode: str, state_dir: str) -> dict:
    state = {
        "run_id": run_id,
        "topic": topic,
        "mode": mode,
        "status": "IN_PROGRESS",
        "started_at": _now(),
        "last_updated": _now(),
        "subtopics": [],
        "synthesis": {"status": "PENDING", "result_file": None},
        "pdf": {"status": "PENDING", "file": None},
        "email": {"status": "PENDING", "sent_at": None},
    }
    _write(_master_path(run_id, state_dir), state)
    return state


def load_state(run_id: str, state_dir: str) -> dict:
    return _read(_master_path(run_id, state_dir))


def update_master_state(run_id: str, state_dir: str, updates: dict) -> None:
    state = load_state(run_id, state_dir)
    state.update(updates)
    state["last_updated"] = _now()
    _write(_master_path(run_id, state_dir), state)


def create_subtopic_state(run_id: str, idx: int, topic: str, state_dir: str) -> dict:
    state = {
        "id": idx,
        "topic": topic,
        "status": "IN_PROGRESS",
        "started_at": _now(),
        "completed_at": None,
        "last_heartbeat": _now(),
        "result": None,
        "error": None,
    }
    _write(_subtopic_path(run_id, idx, state_dir), state)
    return state


def load_subtopic_state(run_id: str, idx: int, state_dir: str) -> dict:
    return _read(_subtopic_path(run_id, idx, state_dir))


def update_subtopic_state(run_id: str, idx: int, state_dir: str, updates: dict) -> None:
    state = load_subtopic_state(run_id, idx, state_dir)
    state.update(updates)
    _write(_subtopic_path(run_id, idx, state_dir), state)


def update_heartbeat(run_id: str, idx: int, state_dir: str) -> None:
    update_subtopic_state(run_id, idx, state_dir, {"last_heartbeat": _now()})


def find_incomplete_runs(state_dir: str) -> list[dict]:
    if not os.path.exists(state_dir):
        return []
    runs = []
    for fname in os.listdir(state_dir):
        if fname.endswith("-master.json"):
            state = _read(os.path.join(state_dir, fname))
            if state.get("status") == "IN_PROGRESS":
                runs.append(state)
    return runs
```

**Step 4: Run tests**

```bash
pytest tests/test_state.py -v
```

Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat: state management — master + subtopic files, heartbeat, resume discovery"
```

---

### Task 5: Pre-flight Checks

**Files:**
- Create: `src/preflight.py`
- Create: `tests/test_preflight.py`

Pre-flight validates network, API keys, config, and output dirs before any API call. See design doc Section 13 for the exact check order and output format. Raises `PreflightError` with the appropriate error code on failure. `COMPOSIO_API_KEY` is always required (Gmail delivery). A `check_composio_gmail(cfg)` function verifies the Gmail OAuth connection in Composio is still active (calls `connected_accounts.list()`; no email sent) and raises `PreflightError([ERR-AUTH-008])` with reconnect instructions if missing or the API key is rejected — the Composio API key itself does not expire, but the Gmail OAuth link can be silently revoked. When `notebooklm.notebook_ids` is non-empty, `check_notebooklm(cfg)` calls `verify_notebooklm_auth(notebook_ids)` from `notebooklm_reader.py` which sends a lightweight ping query to the first notebook. If the Chrome session has expired it raises `PreflightError([ERR-AUTH-009])` with an instruction to run `nlm login`.

**Step 1: Write the failing tests**

```python
# tests/test_preflight.py
import pytest
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
    from src.preflight import run_preflight, PreflightError
    cfg = make_cfg()
    cfg["output_dir"] = str(tmp_path / "reports")
    with patch("src.preflight.check_network", return_value=None), \
         patch("src.preflight.check_api_keys", return_value=None), \
         patch("src.preflight.check_output_dirs", return_value=None):
        run_preflight(cfg)  # should not raise


def test_invalid_email_raises_eml003():
    from src.preflight import validate_emails, PreflightError
    with pytest.raises(PreflightError, match="EML-003"):
        validate_emails(["not-an-email"])


def test_valid_emails_pass():
    from src.preflight import validate_emails
    validate_emails(["a@b.com", "c@d.org"])  # no exception


def test_dedup_to_and_cc():
    from src.preflight import merge_recipients
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
    from src.preflight import merge_recipients, PreflightError
    with pytest.raises(PreflightError, match="EML-005"):
        merge_recipients([], [], [], [])


def test_google_credentials_not_required_without_notebook_ids():
    """Google credentials check is skipped when notebooklm.notebook_ids is empty."""
    from src.preflight import check_api_keys
    import os
    cfg = make_cfg(notebook_ids=[])
    # Even without GOOGLE_CREDENTIALS_PATH set, this should not raise
    env = {k: v for k, v in os.environ.items() if k != "GOOGLE_CREDENTIALS_PATH"}
    env["ANTHROPIC_API_KEY"] = "test-key"
    with patch.dict(os.environ, env, clear=True):
        check_api_keys(cfg)  # should not raise


def test_google_credentials_required_with_notebook_ids():
    """Google credentials ARE required when notebooklm.notebook_ids is non-empty."""
    from src.preflight import check_api_keys, PreflightError
    import os
    cfg = make_cfg(notebook_ids=["some-folder-id"])
    env = {k: v for k, v in os.environ.items()
           if k not in ("GOOGLE_CREDENTIALS_PATH", "GOOGLE_API_KEY")}
    env["ANTHROPIC_API_KEY"] = "test-key"
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(PreflightError, match="AUTH-004"):
            check_api_keys(cfg)


def test_check_composio_gmail_passes_when_gmail_connected():
    """No error raised when an active Gmail connection exists"""
    from src.preflight import check_composio_gmail
    cfg = make_cfg()
    with patch("src.preflight.Composio") as mock_cls:
        mock_cls.return_value = _make_composio_mock(has_gmail=True)
        with patch.dict(os.environ, {"COMPOSIO_API_KEY": "test-key"}):
            check_composio_gmail(cfg)  # should not raise


def test_check_composio_gmail_raises_when_no_gmail_connection():
    """No active Gmail account raises ERR-AUTH-008 with reconnect hint"""
    from src.preflight import check_composio_gmail, PreflightError
    cfg = make_cfg()
    with patch("src.preflight.Composio") as mock_cls:
        mock_cls.return_value = _make_composio_mock(has_gmail=False)
        with patch.dict(os.environ, {"COMPOSIO_API_KEY": "test-key"}):
            with pytest.raises(PreflightError, match="ERR-AUTH-008"):
                check_composio_gmail(cfg)


def test_check_composio_gmail_raises_on_invalid_api_key():
    """Invalid Composio API key raises ERR-AUTH-008"""
    from src.preflight import check_composio_gmail, PreflightError
    cfg = make_cfg()
    with patch("src.preflight.Composio", side_effect=Exception("401 Unauthorized")):
        with patch.dict(os.environ, {"COMPOSIO_API_KEY": "bad-key"}):
            with pytest.raises(PreflightError, match="ERR-AUTH-008"):
                check_composio_gmail(cfg)


def test_check_composio_gmail_skipped_when_no_api_key():
    """No-op when COMPOSIO_API_KEY is not set"""
    from src.preflight import check_composio_gmail
    cfg = make_cfg()
    env = {k: v for k, v in os.environ.items() if k != "COMPOSIO_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        check_composio_gmail(cfg)  # should not raise


def test_run_preflight_calls_check_composio_gmail():
    """`run_preflight()` invokes `check_composio_gmail` before research"""
    from src.preflight import run_preflight
    cfg = make_cfg()
    with patch("src.preflight.check_network"), \
         patch("src.preflight.check_api_keys"), \
         patch("src.preflight.check_output_dirs"), \
         patch("src.preflight.check_composio_gmail") as mock_gmail, \
         patch("src.preflight.check_notebooklm"):
        run_preflight(cfg)
        mock_gmail.assert_called_once_with(cfg)
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_preflight.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/preflight.py`**

```python
import os
import re
import socket

from typing import Optional


class PreflightError(Exception):
    pass


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_emails(emails: list[str]) -> None:
    for email in emails:
        if not _EMAIL_RE.match(email):
            raise PreflightError(f"[ERR-EML-003] Invalid recipient email address: {email}")


def merge_recipients(
    config_to: list[str],
    cli_to: list[str],
    config_cc: list[str],
    cli_cc: list[str],
) -> tuple[list[str], list[str], list[str]]:
    def norm(e): return e.lower().strip()

    seen_to: dict[str, str] = {}
    for e in config_to + cli_to:
        seen_to[norm(e)] = e

    seen_cc: dict[str, str] = {}
    for e in config_cc + cli_cc:
        seen_cc[norm(e)] = e

    warnings = []
    for key in list(seen_cc.keys()):
        if key in seen_to:
            warnings.append(f"[WRN-EML-006] {seen_cc[key]} is in both TO and CC — removed from CC, kept in TO")
            del seen_cc[key]

    to_list = list(seen_to.values())
    cc_list = list(seen_cc.values())

    if not to_list:
        raise PreflightError("[ERR-EML-005] No recipients configured — set default_recipients in config.yaml or pass --email")

    return to_list, cc_list, warnings


def check_network(cfg: dict) -> None:
    try:
        socket.setdefaulttimeout(5)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 53))
    except Exception:
        raise PreflightError("[ERR-NET-001] No internet connection")


def check_api_keys(cfg: dict) -> None:
    model = cfg.get("agent", {}).get("default_model", "")
    if "claude" in model and not os.environ.get("ANTHROPIC_API_KEY"):
        raise PreflightError("[ERR-AUTH-002] ANTHROPIC_API_KEY is required for Claude models but is not set")
    if "gemini" in model and not os.environ.get("GOOGLE_API_KEY"):
        raise PreflightError("[ERR-AUTH-006] GOOGLE_API_KEY is required for Gemini models but is not set")
    if "gpt" in model and not os.environ.get("OPENAI_API_KEY"):
        raise PreflightError("[ERR-AUTH-006] OPENAI_API_KEY is required for GPT models but is not set")

    # Google credentials only required when NotebookLM is configured
    notebook_ids = cfg.get("notebooklm", {}).get("notebook_ids", [])
    if notebook_ids:
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
        if not os.path.exists(creds_path):
            raise PreflightError(
                f"[ERR-AUTH-004] GOOGLE_CREDENTIALS_PATH not found at '{creds_path}' — "
                f"required because notebooklm.notebook_ids is set"
            )


def check_output_dirs(cfg: dict) -> None:
    base = cfg.get("output_dir", "./reports")
    for subdir in ["", "logs", "state", "state/archive"]:
        path = os.path.join(base, subdir)
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            raise PreflightError(f"[ERR-PDF-002] Output directory not writable: {path} — {e}")


def check_composio_gmail(cfg: dict) -> None:
    """Verify the Composio Gmail OAuth connection is active before research starts."""
    api_key = os.environ.get("COMPOSIO_API_KEY")
    if not api_key:
        return  # check_api_keys already caught the missing key case
    try:
        composio = Composio(api_key=api_key)
        accounts = composio._client.connected_accounts.list()
        gmail_account = next(
            (a for a in accounts.items if a.toolkit.slug == "gmail" and a.status == "ACTIVE"),
            None,
        )
    except Exception as e:
        raise PreflightError(
            f"[ERR-AUTH-008] Composio API key is invalid or unreachable: {e}\n"
            "  Verify your COMPOSIO_API_KEY at app.composio.dev."
        )
    if gmail_account is None:
        raise PreflightError(
            "[ERR-AUTH-008] No active Gmail connection found in Composio.\n"
            "  Connect your Gmail account at app.composio.dev → Apps → Gmail → Connect."
        )


def check_notebooklm(cfg: dict) -> None:
    notebook_ids = cfg.get("notebooklm", {}).get("notebook_ids", [])
    if not notebook_ids:
        return
    from tools.notebooklm_reader import verify_notebooklm_auth, ToolError
    try:
        verify_notebooklm_auth(notebook_ids)
    except ToolError as e:
        msg = str(e)
        if "ERR-AUTH-009" in msg:
            raise PreflightError(
                "[ERR-AUTH-009] NotebookLM authentication has expired.\n"
                "  Run 'nlm login' in your terminal to re-authenticate, then retry."
            )
        raise PreflightError(
            f"[ERR-NTB-003] NotebookLM preflight check failed: {e}\n"
            "  Ensure 'uvx install notebooklm-mcp-cli' has been run and 'nlm login' is up to date."
        )


def run_preflight(cfg: dict) -> None:
    check_network(cfg)
    check_api_keys(cfg)
    check_output_dirs(cfg)
    check_composio_gmail(cfg)
    check_notebooklm(cfg)
```

**Step 4: Run tests**

```bash
pytest tests/test_preflight.py -v
```

Expected: 7 PASSED.

**Step 5: Commit**

```bash
git add src/preflight.py tests/test_preflight.py
git commit -m "feat: pre-flight — network, API keys, email validation, optional NotebookLM credential check"
```

---

### Task 6: Web Search Tool (Tavily)

**Files:**
- Create: `src/tools/web_search.py`
- Create: `tests/test_tools.py`

Wraps the Tavily API. Returns a list of `{"title", "url", "content"}` dicts. On failure raises `ToolError` with the appropriate error code.

**Step 1: Write the failing tests**

```python
# tests/test_tools.py
import pytest
from unittest.mock import patch, MagicMock


def test_web_search_returns_results():
    from src.tools.web_search import web_search
    mock_response = {
        "results": [
            {"title": "Article 1", "url": "https://example.com/1", "content": "Content 1"},
            {"title": "Article 2", "url": "https://example.com/2", "content": "Content 2"},
        ]
    }
    with patch("src.tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.return_value = mock_response
        mock_cls.return_value = mock_client
        results = web_search("AI healthcare trends", api_key="test-key")
    assert len(results) == 2
    assert results[0]["title"] == "Article 1"
    assert results[0]["url"] == "https://example.com/1"


def test_web_search_raises_on_quota_exceeded():
    from src.tools.web_search import web_search, ToolError
    with patch("src.tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("quota exceeded")
        mock_cls.return_value = mock_client
        with pytest.raises(ToolError, match="AUTH-005"):
            web_search("topic", api_key="test-key")


def test_web_search_raises_on_invalid_key():
    from src.tools.web_search import web_search, ToolError
    with patch("src.tools.web_search.TavilyClient") as mock_cls:
        mock_client = MagicMock()
        mock_client.search.side_effect = Exception("invalid api key")
        mock_cls.return_value = mock_client
        with pytest.raises(ToolError, match="AUTH-003"):
            web_search("topic", api_key="bad-key")
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_tools.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/tools/web_search.py`**

```python
import os
from tavily import TavilyClient


class ToolError(Exception):
    pass


def web_search(query: str, api_key: str = None, max_results: int = 5) -> list[dict]:
    key = api_key or os.environ.get("TAVILY_API_KEY")
    if not key:
        raise ToolError("[ERR-AUTH-003] TAVILY_API_KEY not set")

    try:
        client = TavilyClient(api_key=key)
        response = client.search(query, max_results=max_results)
    except Exception as e:
        msg = str(e).lower()
        if "quota" in msg or "limit" in msg:
            raise ToolError(f"[ERR-AUTH-005] Tavily quota exceeded: {e}")
        if "invalid" in msg or "unauthorized" in msg or "api key" in msg:
            raise ToolError(f"[ERR-AUTH-003] Invalid or expired Tavily API key: {e}")
        raise ToolError(f"[ERR-NET-003] Tavily API unreachable: {e}")

    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "content": r.get("content", "")}
        for r in response.get("results", [])
    ]
```

**Step 4: Run tests**

```bash
pytest tests/test_tools.py -v
```

Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add src/tools/web_search.py tests/test_tools.py
git commit -m "feat: Tavily web search tool with AUTH-003/AUTH-005/NET-003 error handling"
```

---

### Task 7: NotebookLM Reader Tool

**Files:**
- Create: `src/tools/notebooklm_reader.py`
- Modify: `tests/test_tools.py` (add tests)

Queries a NotebookLM notebook via the `notebooklm-mcp-cli` MCP server (browser automation). The package exposes the server as `notebooklm-mcp`; the launch command is `uvx --from notebooklm-mcp-cli notebooklm-mcp`. For each subtopic query, calls `query_notebook(notebook_id, query)` which returns a `{"name", "content"}` dict with the AI-synthesized answer. Auth errors (expired Chrome session) raise `ToolError([ERR-AUTH-009])` — distinct from generic MCP errors `ERR-NTB-003`. Python 3.11+ asyncio `ExceptionGroup` from `TaskGroup` is unwrapped by `_unwrap_exception_group()` before error classification. This module is only called by the researcher when `notebook_ids` is non-empty. `verify_notebooklm_auth(notebook_ids)` is a lightweight preflight probe used by `preflight.py`.

**How it works:** The `notebooklm-mcp-cli` MCP server runs as a separate process (stdio transport), controlling a Chrome browser session logged into NotebookLM. The Python `mcp` client library spawns the server as a subprocess, calls `notebook_query` via JSON-RPC, and gets back a synthesized answer from NotebookLM's AI. No Google service account or API key required — auth is via the saved Chrome browser session.

**Notebook UUID:** Found in the NotebookLM URL: `notebooklm.google.com/notebooklm?notebook=<UUID>`

**Step 1: Add failing tests to `tests/test_tools.py`**

```python
# Add to tests/test_tools.py

def test_notebooklm_reader_returns_sources():
    from src.tools.notebooklm_reader import read_notebook_sources
    mock_drive = MagicMock()
    mock_drive.files().list().execute.return_value = {
        "files": [{"id": "file1", "name": "Source 1", "mimeType": "application/vnd.google-apps.document"}]
    }
    mock_drive.files().export().execute.return_value = b"Source content here"
    with patch("src.tools.notebooklm_reader.build_drive_service", return_value=mock_drive):
        results = read_notebook_sources("folder-id-123")
    assert len(results) == 1
    assert results[0]["name"] == "Source 1"
    assert "Source content" in results[0]["content"]


def test_notebooklm_reader_raises_on_not_found():
    from src.tools.notebooklm_reader import read_notebook_sources, ToolError
    mock_drive = MagicMock()
    mock_drive.files().list().execute.side_effect = Exception("File not found")
    with patch("src.tools.notebooklm_reader.build_drive_service", return_value=mock_drive):
        with pytest.raises(ToolError, match="NTB-001"):
            read_notebook_sources("bad-folder-id")


def test_notebooklm_reader_raises_on_permission_denied():
    from src.tools.notebooklm_reader import read_notebook_sources, ToolError
    mock_drive = MagicMock()
    mock_drive.files().list().execute.side_effect = Exception("permission denied")
    with patch("src.tools.notebooklm_reader.build_drive_service", return_value=mock_drive):
        with pytest.raises(ToolError, match="NTB-003"):
            read_notebook_sources("folder-id")
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_tools.py::test_notebooklm_reader_returns_sources -v
```

Expected: `ImportError`.

**Step 3: Implement `src/tools/notebooklm_reader.py`**

```python
import os

from googleapiclient.discovery import build
from google.oauth2 import service_account

from src.tools.web_search import ToolError

_MCP_COMMAND = "uvx"
_MCP_ARGS = ["--from", "notebooklm-mcp-cli", "notebooklm-mcp"]


def build_drive_service(credentials_path: str = None):
    path = credentials_path or os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    return build("drive", "v3", credentials=creds)


def read_notebook_sources(folder_id: str, credentials_path: str = None) -> list[dict]:
    try:
        service = build_drive_service(credentials_path)
    except Exception as e:
        raise ToolError(f"[ERR-AUTH-004] Invalid or expired Google credentials: {e}")

    try:
        results = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
        ).execute()
    except Exception as e:
        msg = str(e).lower()
        if "permission" in msg or "forbidden" in msg:
            raise ToolError(f"[ERR-NTB-003] Google Drive permission denied for folder {folder_id}: {e}")
        raise ToolError(f"[ERR-NTB-001] NotebookLM notebook not found: {folder_id} — {e}")

    files = results.get("files", [])
    if not files:
        raise ToolError(f"[ERR-NTB-002] No readable sources in notebook: {folder_id}")

    sources = []
    for file in files:
        try:
            request = service.files().export(fileId=file["id"], mimeType="text/plain")
            content = request.execute()
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
        except Exception:
            content = ""
        sources.append({"name": file["name"], "content": content})

    return sources
```

**Step 4: Run tests**

```bash
pytest tests/test_tools.py -v
```

Expected: 6 PASSED.

**Step 5: Commit**

```bash
git add src/tools/notebooklm_reader.py tests/test_tools.py
git commit -m "feat: NotebookLM reader tool via Google Drive API with NTB error codes"
```

---

### Task 8: Research Sub-Agent

**Files:**
- Create: `src/researcher.py`
- Create: `tests/test_researcher.py`

Each Research sub-agent receives one subtopic, runs web search (always) + NotebookLM queries (only if `notebook_ids` is non-empty), updates its heartbeat every 10 seconds, writes results to its state file, and returns a markdown findings string. Every external action (web search, NotebookLM query, NotebookLM failure) is written to the audit log via a local `_audit()` helper that appends `run_id` and `subtopic_idx` to each event.

**Step 1: Write the failing tests**

```python
# tests/test_researcher.py
import pytest
from unittest.mock import patch, MagicMock
import threading


def make_research_cfg(notebook_ids=None):
    return {
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096},
        "notebooklm": {"notebook_ids": notebook_ids or []},
        "timeouts": {"sub_agent_sec": 120},
    }


def test_researcher_returns_markdown(tmp_path):
    from src.researcher import run_research_agent
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("src.researcher.web_search") as mock_web, \
         patch("src.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [
            {"title": "Article", "url": "https://x.com", "content": "Some findings about the topic."}
        ]
        mock_llm.return_value = "## Market Trends\n\nKey finding: AI is growing rapidly."
        result = run_research_agent(
            run_id="run-001", subtopic_idx=1, subtopic="market trends",
            cfg=cfg, state_dir=state_dir, dry_run=False
        )

    assert "Market Trends" in result or "market trends" in result.lower()


def test_researcher_skips_notebooklm_when_not_configured(tmp_path):
    """When notebook_ids is empty, NotebookLM reader must not be called."""
    from src.researcher import run_research_agent
    cfg = make_research_cfg(notebook_ids=[])
    state_dir = str(tmp_path / "state")

    with patch("src.researcher.web_search") as mock_web, \
         patch("src.researcher.read_notebook_sources") as mock_nb, \
         patch("src.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)
        mock_nb.assert_not_called()


def test_researcher_calls_notebooklm_when_configured(tmp_path):
    """When notebook_ids is set, NotebookLM reader IS called for each ID."""
    from src.researcher import run_research_agent
    cfg = make_research_cfg(notebook_ids=["folder-abc", "folder-xyz"])
    state_dir = str(tmp_path / "state")

    with patch("src.researcher.web_search") as mock_web, \
         patch("src.researcher.read_notebook_sources") as mock_nb, \
         patch("src.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_nb.return_value = [{"name": "Source", "content": "notebook content"}]
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)
        assert mock_nb.call_count == 2  # called once per notebook_id


def test_researcher_writes_state_file(tmp_path):
    from src.researcher import run_research_agent
    from src.state import load_subtopic_state
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("src.researcher.web_search") as mock_web, \
         patch("src.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)

    state = load_subtopic_state("run-001", 1, state_dir)
    assert state["status"] == "COMPLETED"
    assert state["result"] is not None


def test_researcher_dry_run_skips_api_calls(tmp_path):
    from src.researcher import run_research_agent
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("src.researcher.web_search") as mock_web, \
         patch("src.researcher.read_notebook_sources") as mock_nb, \
         patch("src.researcher.litellm_complete") as mock_llm:
        result = run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=True)
        mock_web.assert_not_called()
        mock_nb.assert_not_called()
        mock_llm.assert_not_called()

    assert result  # returns stub findings
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_researcher.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/researcher.py`**

```python
import os
import threading
import time

from src.logger import write_audit
from src.state import create_subtopic_state, update_subtopic_state, update_heartbeat
from src.tools.web_search import web_search
from src.tools.notebooklm_reader import query_notebook

import litellm


_DRY_RUN_STUB = "## [DRY RUN] Stub Findings\n\nThis is a dry-run result. No API calls were made."

# Retry settings for rate limit errors
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF = [15, 30, 60]  # seconds to wait before each retry


def litellm_complete(model: str, messages: list[dict], max_tokens: int) -> str:
    for attempt, wait in enumerate([0] + _RATE_LIMIT_BACKOFF):
        if wait:
            time.sleep(wait)
        try:
            response = litellm.completion(model=model, messages=messages, max_tokens=max_tokens)
            return response.choices[0].message.content
        except litellm.exceptions.AuthenticationError:
            raise LLMError("[ERR-AUTH-002] Invalid or missing API key. Check your .env file.")
        except litellm.exceptions.BadRequestError as e:
            msg = str(e).lower()
            if "credit" in msg or "billing" in msg or "balance" in msg:
                raise LLMError("[ERR-AUTH-002] Anthropic API credit balance too low.")
            raise LLMError(f"[ERR-AUTH-007] Model '{model}' returned a bad request error: {e}")
        except litellm.exceptions.RateLimitError:
            if attempt < _RATE_LIMIT_RETRIES:
                continue  # wait and retry
            raise LLMError("[ERR-AUTH-005] API rate limit exceeded. Wait a moment and try again.")
        except litellm.exceptions.APIConnectionError:
            raise LLMError("[ERR-NET-002] Could not reach the Anthropic API.")
        except Exception as e:
            raise LLMError(f"[LLM] Unexpected error from model '{model}': {e}")


def _heartbeat_loop(run_id: str, idx: int, state_dir: str, stop_event: threading.Event):
    while not stop_event.wait(10):
        try:
            update_heartbeat(run_id, idx, state_dir)
        except Exception:
            pass


def run_research_agent(
    run_id: str,
    subtopic_idx: int,
    subtopic: str,
    cfg: dict,
    state_dir: str,
    dry_run: bool = False,
) -> str:
    create_subtopic_state(run_id, subtopic_idx, subtopic, state_dir)

    if dry_run:
        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "COMPLETED", "result": _DRY_RUN_STUB,
            "completed_at": None,
        })
        return _DRY_RUN_STUB

    stop_event = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat_loop,
        args=(run_id, subtopic_idx, state_dir, stop_event),
        daemon=True,
    )
    heartbeat_thread.start()

    audit_path = cfg.get("audit", {}).get("log_file")

    def _audit(data: dict) -> None:
        if audit_path:
            write_audit(audit_path, {"run_id": run_id, "subtopic_idx": subtopic_idx, **data})

    try:
        model = cfg["agent"]["default_model"]
        max_tokens = cfg["agent"].get("max_tokens", 8096)
        notebook_ids = cfg.get("notebooklm", {}).get("notebook_ids", [])
        api_key = os.environ.get("TAVILY_API_KEY")

        # Web search — always
        query = f"{subtopic} latest research 2026"
        web_results = web_search(query, api_key=api_key)
        _audit({"event": "WEB_SEARCH", "subtopic": subtopic,
                "query": query, "results_count": len(web_results)})
        sources_text = "\n\n".join(
            f"**{r['title']}** ({r['url']})\n{r['content']}" for r in web_results
        )

        # NotebookLM — only if configured
        if notebook_ids:
            notebook_sections = []
            for notebook_id in notebook_ids:
                try:
                    result = query_notebook(notebook_id, subtopic)
                    notebook_sections.append(f"**{result['name']}** (NotebookLM)\n{result['content']}")
                    _audit({"event": "NOTEBOOKLM_QUERY", "notebook_id": notebook_id,
                            "subtopic": subtopic})
                except Exception as e:
                    _audit({"event": "NOTEBOOKLM_QUERY_FAILED", "notebook_id": notebook_id,
                            "subtopic": subtopic, "error": str(e)})
            if notebook_sections:
                sources_text += "\n\n" + "\n\n".join(notebook_sections)

        # Synthesize findings with LLM
        prompt = (
            f"You are a research analyst. Based on the following sources, write a thorough "
            f"markdown research brief on: **{subtopic}**\n\n"
            f"Sources:\n{sources_text}\n\n"
            f"Write in professional tone. Include key findings, statistics, and insights."
        )
        findings = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens)

        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "COMPLETED",
            "result": findings,
            "completed_at": None,
        })
        return findings

    except Exception as e:
        update_subtopic_state(run_id, subtopic_idx, state_dir, {
            "status": "FAILED",
            "error": str(e),
        })
        raise
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=1)
```

**Step 4: Run tests**

```bash
pytest tests/test_researcher.py -v
```

Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add src/researcher.py tests/test_researcher.py
git commit -m "feat: research sub-agent — web search always, NotebookLM only when notebook_ids configured"
```

---

### Task 9: Orchestrator

**Files:**
- Create: `src/orchestrator.py`
- Create: `tests/test_orchestrator.py`

The orchestrator: decomposes a topic into N subtopics via LLM, launches parallel research sub-agents (one thread each), monitors heartbeats, collects results, and returns the combined findings dict. Uses `concurrent.futures.ThreadPoolExecutor`.

**Step 1: Write the failing tests**

```python
# tests/test_orchestrator.py
import pytest
from unittest.mock import patch, MagicMock


def make_orch_cfg():
    return {
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096},
        "notebooklm": {"notebook_ids": []},
        "timeouts": {"sub_agent_sec": 120, "total_run_sec": 600},
        "output_dir": "/tmp/test-reports",
        "email": {"default_recipients": ["test@example.com"], "default_cc": []},
        "logging": {"level": "INFO", "log_to_file": False,
                    "log_file": "/tmp/agent.log", "max_file_size_mb": 1, "backup_count": 1},
        "audit": {"enabled": True, "log_file": "/tmp/audit.log", "format": "json"},
    }


def test_decompose_topic_returns_subtopics():
    from src.orchestrator import decompose_topic
    with patch("src.orchestrator.litellm_complete") as mock_llm:
        mock_llm.return_value = "1. Market trends\n2. Key players\n3. Regulation\n4. Future outlook"
        subtopics = decompose_topic("AI trends in healthcare", make_orch_cfg())
    assert len(subtopics) >= 2
    assert any("market" in s.lower() or "trend" in s.lower() for s in subtopics)


def test_decompose_topic_handles_numbered_list():
    from src.orchestrator import decompose_topic
    with patch("src.orchestrator.litellm_complete") as mock_llm:
        mock_llm.return_value = "1. Alpha\n2. Beta\n3. Gamma"
        subtopics = decompose_topic("test topic", make_orch_cfg())
    assert subtopics == ["Alpha", "Beta", "Gamma"]


def test_run_parallel_research_collects_results(tmp_path):
    from src.orchestrator import run_parallel_research
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    with patch("src.orchestrator.run_research_agent") as mock_agent:
        mock_agent.side_effect = lambda run_id, idx, subtopic, cfg, state_dir, dry_run: f"findings for {subtopic}"
        results = run_parallel_research(
            run_id="run-001",
            subtopics=["market trends", "regulation"],
            cfg=cfg,
            state_dir=state_dir,
            dry_run=False,
        )

    assert len(results) == 2
    assert results["market trends"] == "findings for market trends"
    assert results["regulation"] == "findings for regulation"


def test_run_parallel_research_continues_on_single_failure(tmp_path):
    from src.orchestrator import run_parallel_research
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    def mock_agent(run_id, idx, subtopic, cfg, state_dir, dry_run):
        if subtopic == "regulation":
            raise Exception("timeout")
        return f"findings for {subtopic}"

    with patch("src.orchestrator.run_research_agent", side_effect=mock_agent):
        results = run_parallel_research(
            run_id="run-001",
            subtopics=["market trends", "regulation", "future outlook"],
            cfg=cfg,
            state_dir=state_dir,
            dry_run=False,
        )

    assert "market trends" in results
    assert "future outlook" in results
    assert results.get("regulation") is None  # failed subtopic not in results


def test_all_subtopics_fail_raises_res003(tmp_path):
    from src.orchestrator import run_parallel_research, OrchestratorError
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    with patch("src.orchestrator.run_research_agent", side_effect=Exception("fail")):
        with pytest.raises(OrchestratorError, match="RES-003"):
            run_parallel_research("run-001", ["a", "b"], cfg, state_dir, dry_run=False)
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/orchestrator.py`**

```python
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.researcher import run_research_agent, litellm_complete


class OrchestratorError(Exception):
    pass


def decompose_topic(topic: str, cfg: dict) -> list[str]:
    model = cfg["agent"]["default_model"]
    n = cfg["agent"].get("max_subtopics", 5)
    prompt = (
        f"Break the following research topic into exactly {n} focused subtopics suitable for independent research.\n"
        f"Topic: {topic}\n\n"
        f"Return ONLY a numbered list of exactly {n} items, one subtopic per line. No explanations."
    )
    raw = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens=512)
    subtopics = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r"^[\d]+[\.\)]\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        if line:
            subtopics.append(line)
    return subtopics


def run_parallel_research(
    run_id: str,
    subtopics: list[str],
    cfg: dict,
    state_dir: str,
    dry_run: bool = False,
) -> dict[str, str]:
    results: dict[str, str] = {}
    errors: dict[str, Exception] = {}

    with ThreadPoolExecutor(max_workers=len(subtopics)) as executor:
        futures = {
            executor.submit(
                run_research_agent,
                run_id, idx + 1, subtopic, cfg, state_dir, dry_run
            ): subtopic
            for idx, subtopic in enumerate(subtopics)
        }
        for future in as_completed(futures):
            subtopic = futures[future]
            try:
                results[subtopic] = future.result()
            except Exception as e:
                errors[subtopic] = e

    if errors and not results:
        raise OrchestratorError(
            f"[ERR-RES-003] All subtopics failed: {', '.join(errors.keys())}"
        )

    return results
```

**Step 4: Run tests**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator — topic decomposition + parallel research with RES-003"
```

---

### Task 10: Synthesis Agent

**Files:**
- Create: `src/synthesizer.py`
- Create: `tests/test_synthesizer.py`

The synthesis agent receives all subtopic findings and produces: an executive summary (1–2 pages) and a full report body (5–10 pages), both in markdown. Calls the LLM once with a structured prompt.

**Step 1: Write the failing tests**

```python
# tests/test_synthesizer.py
import pytest
from unittest.mock import patch


def make_syn_cfg():
    return {
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096},
    }


def test_synthesize_returns_executive_summary_and_body():
    from src.synthesizer import synthesize
    findings = {
        "market trends": "AI healthcare market growing 30% YoY.",
        "regulation": "FDA increasing oversight of AI medical devices.",
    }
    with patch("src.synthesizer.litellm_complete") as mock_llm:
        mock_llm.return_value = (
            "# Executive Summary\n\nAI healthcare is transforming medicine.\n\n"
            "---\n\n"
            "# Full Report\n\n## Market Trends\n\nGrowing fast."
        )
        result = synthesize("AI trends in healthcare", findings, make_syn_cfg())

    assert "executive_summary" in result
    assert "full_report" in result
    assert result["executive_summary"]
    assert result["full_report"]


def test_synthesize_dry_run_returns_stub():
    from src.synthesizer import synthesize
    findings = {"topic": "some findings"}
    with patch("src.synthesizer.litellm_complete") as mock_llm:
        result = synthesize("topic", findings, make_syn_cfg(), dry_run=True)
        mock_llm.assert_not_called()

    assert result["executive_summary"]
    assert result["full_report"]


def test_synthesize_empty_result_raises_syn001():
    from src.synthesizer import synthesize, SynthesisError
    findings = {"topic": "findings"}
    with patch("src.synthesizer.litellm_complete", return_value=""):
        with pytest.raises(SynthesisError, match="SYN-001"):
            synthesize("topic", findings, make_syn_cfg())
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_synthesizer.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/synthesizer.py`**

```python
from src.researcher import litellm_complete

_DRY_RUN_EXEC = "## [DRY RUN] Executive Summary\n\nThis is a dry-run stub executive summary."
_DRY_RUN_BODY = "## [DRY RUN] Full Report\n\nThis is a dry-run stub full report body."
_SEPARATOR = "---"


class SynthesisError(Exception):
    pass


def synthesize(
    topic: str,
    findings: dict[str, str],
    cfg: dict,
    dry_run: bool = False,
) -> dict[str, str]:
    if dry_run:
        return {"executive_summary": _DRY_RUN_EXEC, "full_report": _DRY_RUN_BODY}

    model = cfg["agent"]["default_model"]
    max_tokens = cfg["agent"].get("max_tokens", 8096)

    findings_text = "\n\n".join(
        f"### {subtopic}\n{content}" for subtopic, content in findings.items()
    )

    prompt = (
        f"You are a senior research analyst. Using the subtopic research below, "
        f"write a professional report on: **{topic}**\n\n"
        f"Structure your response EXACTLY as follows — with '---' as the separator:\n\n"
        f"# Executive Summary\n"
        f"[1-2 page executive summary with key findings and recommendations]\n\n"
        f"{_SEPARATOR}\n\n"
        f"# Full Report\n"
        f"[5-10 page detailed report: background, findings per subtopic, analysis, recommendations]\n\n"
        f"---\n\nSubtopic Research:\n\n{findings_text}"
    )

    raw = litellm_complete(model, [{"role": "user", "content": prompt}], max_tokens)

    if not raw or not raw.strip():
        raise SynthesisError("[ERR-SYN-001] Synthesis agent produced empty report")

    parts = raw.split(f"\n{_SEPARATOR}\n", 1)
    if len(parts) == 2:
        executive_summary, full_report = parts[0].strip(), parts[1].strip()
    else:
        executive_summary = raw[:500].strip()
        full_report = raw.strip()

    return {"executive_summary": executive_summary, "full_report": full_report}
```

**Step 4: Run tests**

```bash
pytest tests/test_synthesizer.py -v
```

Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add src/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: synthesis agent — executive summary + full report body with SYN-001"
```

---

### Task 11: PDF Formatter

**Files:**
- Create: `src/pdf_formatter.py`
- Create: `tests/test_pdf_formatter.py`

Generates a professional PDF using ReportLab (platypus + graphics). Includes: cover page, executive summary, full report body (markdown → paragraphs, charts, and images), page numbers, footer with run timestamp. Renders ` ```chart` JSON blocks as native ReportLab bar/hbar/line/pie/stacked_bar charts and `![caption](src)` image references from web URLs, local file paths, or `notebooklm://` URIs. Any chart or image that cannot be rendered is replaced with a visible grey placeholder box — PDF generation never aborts. Saves to `reports/{run_id}-{slug}.pdf`.

**Step 1: Write the failing tests**

```python
# tests/test_pdf_formatter.py
import os
import pytest


def make_report_data():
    return {
        "topic": "AI trends in healthcare",
        "run_id": "2026-03-12T08-00-01",
        "executive_summary": "## Executive Summary\n\nAI is transforming healthcare rapidly.",
        "full_report": "## Full Report\n\n### Market Trends\n\nGrowing 30% YoY.",
        "generated_at": "2026-03-12T08:01:00Z",
    }


def test_generate_pdf_creates_file(tmp_path):
    from src.pdf_formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert os.path.exists(output_path)
    assert output_path.endswith(".pdf")


def test_generate_pdf_file_is_nonempty(tmp_path):
    from src.pdf_formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert os.path.getsize(output_path) > 1024  # at least 1KB


def test_generate_pdf_filename_contains_run_id(tmp_path):
    from src.pdf_formatter import generate_pdf
    output_path = generate_pdf(make_report_data(), output_dir=str(tmp_path))
    assert "2026-03-12" in os.path.basename(output_path)


def test_generate_pdf_raises_on_unwritable_dir():
    from src.pdf_formatter import generate_pdf, PDFError
    with pytest.raises(PDFError, match="PDF-002"):
        generate_pdf(make_report_data(), output_dir="/nonexistent/path/that/cannot/be/created")
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_pdf_formatter.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/pdf_formatter.py`**

```python
import os
import re
from datetime import datetime, timezone

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, HRFlowable
)
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors


class PDFError(Exception):
    pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:40].strip("-")


def _markdown_to_paragraphs(text: str, styles) -> list:
    elements = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 0.1 * inch))
            continue
        if line.startswith("### "):
            elements.append(Paragraph(line[4:], styles["Heading3"]))
        elif line.startswith("## "):
            elements.append(Paragraph(line[3:], styles["Heading2"]))
        elif line.startswith("# "):
            elements.append(Paragraph(line[2:], styles["Heading1"]))
        else:
            line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            elements.append(Paragraph(line, styles["Normal"]))
    return elements


def generate_pdf(data: dict, output_dir: str) -> str:
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        raise PDFError(f"[ERR-PDF-002] Output directory not writable: {output_dir} — {e}")

    run_id = data["run_id"]
    topic = data["topic"]
    filename = f"{run_id[:10]}-{_slug(topic)}.pdf"
    output_path = os.path.join(output_dir, filename)

    try:
        doc = SimpleDocTemplate(
            output_path, pagesize=letter,
            rightMargin=inch, leftMargin=inch, topMargin=inch, bottomMargin=inch,
        )
        styles = getSampleStyleSheet()
        timestamp = data.get("generated_at", datetime.now(timezone.utc).isoformat())
        story = []

        # Cover page
        story.append(Spacer(1, 2 * inch))
        story.append(Paragraph(topic, ParagraphStyle("Title", fontSize=24, alignment=TA_CENTER, spaceAfter=12)))
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph("Research Report", ParagraphStyle("Subtitle", fontSize=16, alignment=TA_CENTER)))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(f"Generated: {timestamp}", ParagraphStyle("Date", fontSize=10, alignment=TA_CENTER, textColor=colors.grey)))
        story.append(PageBreak())

        # Executive summary
        story.append(Paragraph("Executive Summary", styles["Heading1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.2 * inch))
        story.extend(_markdown_to_paragraphs(data.get("executive_summary", ""), styles))
        story.append(PageBreak())

        # Full report
        story.append(Paragraph("Full Report", styles["Heading1"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
        story.append(Spacer(1, 0.2 * inch))
        story.extend(_markdown_to_paragraphs(data.get("full_report", ""), styles))

        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.grey)
            canvas.drawString(inch, 0.5 * inch, f"Generated: {timestamp} | Page {doc.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
    except OSError as e:
        raise PDFError(f"[ERR-PDF-002] Output directory not writable: {output_dir} — {e}")
    except Exception as e:
        raise PDFError(f"[ERR-PDF-001] PDF generation failed: {e}")

    return output_path
```

**Step 4: Run tests**

```bash
pytest tests/test_pdf_formatter.py -v
```

Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add src/pdf_formatter.py tests/test_pdf_formatter.py
git commit -m "feat: ReportLab PDF formatter with cover page, sections, footer"
```

---

### Task 12: Email Sender

**Files:**
- Create: `src/email_sender.py`
- Create: `tests/test_email_sender.py`

Sends the PDF via Gmail using Composio's `GMAIL_SEND_EMAIL` tool. Checks the audit log first to prevent duplicate sends (EML-004). Accepts `pdf_paths: list[str]` but attaches only `pdf_paths[0]` (the English PDF) — the Composio Gmail API supports one attachment per send call. Translated PDFs are saved locally and listed in the approval prompt but not emailed.

**Step 1: Write the failing tests**

```python
# tests/test_email_sender.py
import json
import os
import pytest
from unittest.mock import patch, MagicMock


def test_send_email_calls_gmail_api(tmp_path):
    from src.email_sender import send_report_email
    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4 fake content")

    with patch("src.email_sender._send_via_gmail") as mock_send:
        mock_send.return_value = {"id": "msg123", "threadId": "thread456"}
        result = send_report_email(
            pdf_path=pdf_path, topic="AI trends",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-001",
        )
    mock_send.assert_called_once()
    assert result["id"] == "msg123"


def test_send_email_prevents_duplicate(tmp_path):
    from src.email_sender import send_report_email, EmailError
    audit_log = str(tmp_path / "audit.log")
    with open(audit_log, "w") as f:
        f.write(json.dumps({"event": "EMAIL_SENT", "run_id": "run-001"}) + "\n")

    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with pytest.raises(EmailError, match="EML-004"):
        send_report_email(
            pdf_path=pdf_path, topic="AI trends",
            to_list=["a@b.com"], cc_list=[],
            audit_log_path=audit_log, run_id="run-001",
        )


def test_send_email_raises_on_missing_recipients(tmp_path):
    from src.email_sender import send_report_email, EmailError
    audit_log = str(tmp_path / "audit.log")
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF fake")

    with pytest.raises(EmailError, match="EML-005"):
        send_report_email(
            pdf_path=pdf_path, topic="AI trends",
            to_list=[], cc_list=[],
            audit_log_path=audit_log, run_id="run-002",
        )
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_email_sender.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/email_sender.py`**

```python
import base64
import json
import os
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.oauth2 import service_account
from googleapiclient.discovery import build


class EmailError(Exception):
    pass


def _already_sent(audit_log_path: str, run_id: str) -> bool:
    if not os.path.exists(audit_log_path):
        return False
    with open(audit_log_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("event") == "EMAIL_SENT" and entry.get("run_id") == run_id:
                    return True
            except json.JSONDecodeError:
                continue
    return False


def _build_message(to_list: list, cc_list: list, subject: str, body: str, pdf_path: str) -> dict:
    msg = MIMEMultipart()
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header("Content-Disposition", "attachment", filename=os.path.basename(pdf_path))
        msg.attach(attachment)
    return {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}


def _send_via_gmail(message: dict, credentials_path: str = None) -> dict:
    path = credentials_path or os.environ.get("GOOGLE_CREDENTIALS_PATH", "./credentials.json")
    scopes = ["https://www.googleapis.com/auth/gmail.send"]
    creds = service_account.Credentials.from_service_account_file(path, scopes=scopes)
    service = build("gmail", "v1", credentials=creds)
    return service.users().messages().send(userId="me", body=message).execute()


def send_report_email(
    pdf_path: str,
    topic: str,
    to_list: list[str],
    cc_list: list[str],
    audit_log_path: str,
    run_id: str,
    credentials_path: str = None,
) -> dict:
    if not to_list:
        raise EmailError("[ERR-EML-005] No recipients configured — set default_recipients in config.yaml or pass --email")

    if _already_sent(audit_log_path, run_id):
        raise EmailError(f"[ERR-EML-004] Email already sent for run {run_id} — duplicate prevented")

    message = _build_message(to_list, cc_list, f"Research Report: {topic}",
                             f"Please find attached the research report on: {topic}", pdf_path)
    try:
        return _send_via_gmail(message, credentials_path)
    except Exception as e:
        raise EmailError(f"[ERR-EML-002] Email delivery failed: {e}")
```

**Step 4: Run tests**

```bash
pytest tests/test_email_sender.py -v
```

Expected: 3 PASSED.

**Step 5: Commit**

```bash
git add src/email_sender.py tests/test_email_sender.py
git commit -m "feat: Gmail email sender with EML-004 duplicate guard and EML-005"
```

---

### Task 13: Human-in-the-Loop Approval Gate

**Files:**
- Create: `src/approval.py`
- Create: `tests/test_approval.py`

Interactive terminal prompt shown in ad-hoc mode only. Supports `y` / `n` / `edit`. In `edit` mode, opens the PDF in the system default viewer, then re-prompts. Scheduled mode skips this entirely.

**Step 1: Write the failing tests**

```python
# tests/test_approval.py
import pytest
from unittest.mock import patch


def test_approval_y_returns_approved():
    from src.approval import request_approval
    with patch("builtins.input", return_value="y"):
        decision = request_approval("AI trends", ["a@b.com"], [], "/tmp/report.pdf")
    assert decision == "approved"


def test_approval_n_returns_declined():
    from src.approval import request_approval
    with patch("builtins.input", return_value="n"):
        decision = request_approval("AI trends", ["a@b.com"], [], "/tmp/report.pdf")
    assert decision == "declined"


def test_approval_invalid_then_y():
    from src.approval import request_approval
    with patch("builtins.input", side_effect=["x", "y"]):
        decision = request_approval("AI trends", ["a@b.com"], [], "/tmp/report.pdf")
    assert decision == "approved"


def test_approval_edit_then_y(tmp_path):
    from src.approval import request_approval
    pdf_path = str(tmp_path / "report.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"fake pdf")
    with patch("builtins.input", side_effect=["edit", "y"]), \
         patch("src.approval.open_pdf_viewer"):
        decision = request_approval("AI trends", ["a@b.com"], [], pdf_path)
    assert decision == "approved"
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_approval.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/approval.py`**

```python
import os
import platform
import subprocess


def open_pdf_viewer(pdf_path: str) -> None:
    system = platform.system()
    if system == "Windows":
        os.startfile(pdf_path)
    elif system == "Darwin":
        subprocess.run(["open", pdf_path], check=False)
    else:
        subprocess.run(["xdg-open", pdf_path], check=False)


def request_approval(topic: str, to_list: list[str], cc_list: list[str], pdf_path: str) -> str:
    print(f'\nReport ready: "{topic}"')
    print(f"\nTo:  {', '.join(to_list)}")
    print(f"CC:  {', '.join(cc_list) if cc_list else '(none)'}")
    print(f"PDF: {pdf_path}\n")

    while True:
        choice = input("Send this report? [y/n/edit]: ").strip().lower()
        if choice == "y":
            return "approved"
        elif choice == "n":
            return "declined"
        elif choice == "edit":
            open_pdf_viewer(pdf_path)
            print("Review the PDF, then confirm.")
        else:
            print("Please enter y, n, or edit.")
```

**Step 4: Run tests**

```bash
pytest tests/test_approval.py -v
```

Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add src/approval.py tests/test_approval.py
git commit -m "feat: human-in-the-loop approval gate with y/n/edit flow"
```

---

### Task 14: Resume Flow

**Files:**
- Create: `src/resume.py`
- Create: `tests/test_resume.py`

Finds incomplete runs, displays their status, and presents the 4-option menu (retry failed / skip failed / restart / abort).

**Step 1: Write the failing tests**

```python
# tests/test_resume.py
import pytest
from unittest.mock import patch


def make_master_state():
    return {
        "run_id": "2026-03-12T08-00-01",
        "topic": "AI trends",
        "mode": "ad-hoc",
        "status": "IN_PROGRESS",
        "subtopics": [
            {"id": 1, "topic": "market trends", "status": "COMPLETED"},
            {"id": 2, "topic": "regulation", "status": "TIMED_OUT", "error": "RES-001"},
            {"id": 3, "topic": "future outlook", "status": "COMPLETED"},
        ],
        "synthesis": {"status": "PENDING"},
        "pdf": {"status": "PENDING"},
        "email": {"status": "PENDING"},
    }


def test_display_run_summary_shows_all_stages(capsys):
    from src.resume import display_run_summary
    display_run_summary(make_master_state())
    captured = capsys.readouterr()
    assert "market trends" in captured.out
    assert "regulation" in captured.out


def test_choose_resume_option_1_retry():
    from src.resume import choose_resume_option
    with patch("builtins.input", return_value="1"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "retry_failed"


def test_choose_resume_option_2_skip():
    from src.resume import choose_resume_option
    with patch("builtins.input", return_value="2"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "skip_failed"


def test_choose_resume_option_3_restart():
    from src.resume import choose_resume_option
    with patch("builtins.input", return_value="3"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "restart"


def test_choose_resume_option_4_abort():
    from src.resume import choose_resume_option
    with patch("builtins.input", return_value="4"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "abort"
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_resume.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/resume.py`**

```python
_STATUS_ICON = {
    "COMPLETED": "✓", "TIMED_OUT": "✗", "FAILED": "✗",
    "IN_PROGRESS": "~", "PENDING": "○", "SKIPPED": "-",
}


def display_run_summary(state: dict) -> None:
    print(f'\nRun summary for: "{state["topic"]}" ({state["run_id"]})')
    for sub in state.get("subtopics", []):
        icon = _STATUS_ICON.get(sub["status"], "?")
        error = f' [{sub.get("error", "")}]' if sub.get("error") else ""
        print(f"  {icon} Subtopic {sub['id']}: {sub['topic']:30s} — {sub['status']}{error}")
    for stage in ["synthesis", "pdf", "email"]:
        st = state.get(stage, {})
        icon = _STATUS_ICON.get(st.get("status", "PENDING"), "?")
        print(f"  {icon} {stage.capitalize():35s} — {st.get('status', 'PENDING')}")


def choose_resume_option(state: dict) -> dict:
    failed = [s for s in state.get("subtopics", []) if s["status"] in ("TIMED_OUT", "FAILED")]
    print("\nResume options:")
    if failed:
        print(f"  [1] Retry {len(failed)} failed subtopic(s), then continue")
        print(f"  [2] Skip failed subtopic(s), continue with completed results")
    else:
        print("  [1] Continue from last completed stage")
        print("  [2] Continue from last completed stage (same as 1)")
    print("  [3] Restart entire run from scratch")
    print("  [4] Abort and discard\n")

    while True:
        choice = input("Choice: ").strip()
        if choice == "1":
            return {"action": "retry_failed", "failed_subtopics": failed}
        elif choice == "2":
            return {"action": "skip_failed", "failed_subtopics": failed}
        elif choice == "3":
            return {"action": "restart"}
        elif choice == "4":
            return {"action": "abort"}
        else:
            print("Please enter 1, 2, 3, or 4.")
```

**Step 4: Run tests**

```bash
pytest tests/test_resume.py -v
```

Expected: 5 PASSED.

**Step 5: Commit**

```bash
git add src/resume.py tests/test_resume.py
git commit -m "feat: resume flow — incomplete run discovery, status display, 4-option menu"
```

---

### Task 15: CLI Entry Point

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

The CLI ties everything together. Uses Click for command parsing. Three commands: `research`, `scheduler`, `resume`. Log-level priority: `--log-level` flag → `LOG_LEVEL` env → `config.yaml` → `INFO`.

**Step 1: Write the failing tests**

```python
# tests/test_main.py
import pytest
from click.testing import CliRunner
from unittest.mock import patch


def test_research_command_exists():
    from src.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["research", "--help"])
    assert result.exit_code == 0
    assert "TOPIC" in result.output or "topic" in result.output.lower()


def test_scheduler_command_exists():
    from src.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["scheduler", "--help"])
    assert result.exit_code == 0


def test_resume_command_exists():
    from src.main import cli
    runner = CliRunner()
    result = runner.invoke(cli, ["resume", "--help"])
    assert result.exit_code == 0


def test_dry_run_flag_runs_without_api_calls(tmp_path):
    from src.main import cli
    runner = CliRunner()
    cfg_content = f"""
user_email: test@example.com
output_dir: {str(tmp_path / "reports")}
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
  log_file: {str(tmp_path / "agent.log")}
  max_file_size_mb: 1
  backup_count: 1
audit:
  enabled: true
  log_file: {str(tmp_path / "audit.log")}
  format: json
"""
    cfg_path = str(tmp_path / "config.yaml")
    with open(cfg_path, "w") as f:
        f.write(cfg_content)

    with patch("src.main.run_preflight"), \
         patch("src.main.decompose_topic", return_value=["subtopic A", "subtopic B"]), \
         patch("src.main.run_parallel_research", return_value={"subtopic A": "findings A"}), \
         patch("src.main.synthesize", return_value={"executive_summary": "exec", "full_report": "full"}), \
         patch("src.main.generate_pdf", return_value=str(tmp_path / "report.pdf")):
        result = runner.invoke(cli, ["research", "AI trends", "--dry-run", "--config", cfg_path])

    assert result.exit_code == 0, result.output
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_main.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/main.py`**

```python
import os
import sys
from datetime import datetime, timezone

import click
from dotenv import load_dotenv

from src.config import load_config, ConfigError
from src.logger import setup_loggers, write_audit
from src.preflight import run_preflight, PreflightError, merge_recipients, validate_emails
from src.orchestrator import decompose_topic, run_parallel_research, OrchestratorError
from src.synthesizer import synthesize, SynthesisError
from src.pdf_formatter import generate_pdf, PDFError
from src.email_sender import send_report_email, EmailError
from src.approval import request_approval
from src.state import create_master_state, update_master_state, find_incomplete_runs
from src.resume import display_run_summary, choose_resume_option

load_dotenv()


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


@click.group()
def cli():
    """Research-to-Report: autonomous research agent."""
    pass


@cli.command()
@click.argument("topic")
@click.option("--email", "cli_to", default="", help="Comma-separated TO recipients")
@click.option("--email-cc", "cli_cc", default="", help="Comma-separated CC recipients")
@click.option("--dry-run", is_flag=True, default=False, help="Run without making API calls")
@click.option("--log-level", default=None, help="Override log level (DEBUG/INFO/WARNING/ERROR)")
@click.option("--config", "config_path", default="config.yaml", help="Path to config.yaml")
def research(topic, cli_to, cli_cc, dry_run, log_level, config_path):
    """Run research pipeline for TOPIC."""
    if log_level:
        os.environ["LOG_LEVEL"] = log_level

    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    setup_loggers(cfg)
    audit_path = cfg["audit"]["log_file"]
    state_dir = os.path.join(cfg["output_dir"], "state")
    run_id = _run_id()

    config_to = cfg["email"].get("default_recipients", [])
    config_cc = cfg["email"].get("default_cc", [])
    parsed_cli_to = [e.strip() for e in cli_to.split(",") if e.strip()]
    parsed_cli_cc = [e.strip() for e in cli_cc.split(",") if e.strip()]

    try:
        to_list, cc_list, warnings = merge_recipients(config_to, parsed_cli_to, config_cc, parsed_cli_cc)
        for w in warnings:
            click.echo(f"Warning: {w}")
        validate_emails(to_list + cc_list)
    except PreflightError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    if not dry_run:
        try:
            run_preflight(cfg)
        except PreflightError as e:
            click.echo(str(e), err=True)
            sys.exit(1)

    write_audit(audit_path, {"event": "RUN_STARTED", "run_id": run_id,
                              "mode": "ad-hoc", "topic": topic, "triggered_by": "cli"})
    create_master_state(run_id, topic, "ad-hoc", state_dir)

    try:
        click.echo(f"Decomposing topic: {topic}")
        subtopics = decompose_topic(topic, cfg) if not dry_run else ["Subtopic A (dry run)", "Subtopic B (dry run)"]

        click.echo(f"Launching {len(subtopics)} research agents...")
        findings = run_parallel_research(run_id, subtopics, cfg, state_dir, dry_run=dry_run)

        click.echo("Synthesizing findings...")
        report = synthesize(topic, findings, cfg, dry_run=dry_run)

        click.echo("Generating PDF...")
        pdf_path = generate_pdf(
            data={"topic": topic, "run_id": run_id,
                  "executive_summary": report["executive_summary"],
                  "full_report": report["full_report"],
                  "generated_at": datetime.now(timezone.utc).isoformat()},
            output_dir=cfg["output_dir"],
        )
        write_audit(audit_path, {"event": "REPORT_GENERATED", "run_id": run_id, "file": pdf_path})
        click.echo(f"PDF saved: {pdf_path}")

    except (OrchestratorError, SynthesisError, PDFError) as e:
        click.echo(str(e), err=True)
        update_master_state(run_id, state_dir, {"status": "FAILED"})
        sys.exit(1)

    if dry_run:
        click.echo("[DRY RUN] Skipping email delivery.")
        update_master_state(run_id, state_dir, {"status": "COMPLETED"})
        return

    decision = request_approval(topic, to_list, cc_list, pdf_path)
    write_audit(audit_path, {"event": "APPROVAL_DECISION", "run_id": run_id, "decision": decision})

    if decision == "approved":
        try:
            send_report_email(pdf_path, topic, to_list, cc_list, audit_path, run_id)
            write_audit(audit_path, {"event": "EMAIL_SENT", "run_id": run_id,
                                      "to": to_list, "cc": cc_list})
            click.echo("Email sent successfully.")
        except EmailError as e:
            click.echo(str(e), err=True)
    else:
        click.echo("Email skipped. PDF saved locally.")

    update_master_state(run_id, state_dir, {"status": "COMPLETED"})
    write_audit(audit_path, {"event": "RUN_COMPLETED", "run_id": run_id, "status": "success"})


@cli.command()
@click.argument("action", type=click.Choice(["start", "stop"]))
@click.option("--config", "config_path", default="config.yaml")
def scheduler(action, config_path):
    """Start or stop the APScheduler cron scheduler."""
    if action == "start":
        try:
            cfg = load_config(config_path)
        except ConfigError as e:
            click.echo(str(e), err=True)
            sys.exit(1)
        from src.scheduler import start_scheduler
        start_scheduler(cfg)
    else:
        click.echo("Scheduler stopped.")


@cli.command("resume")
@click.option("--config", "config_path", default="config.yaml")
def resume_cmd(config_path):
    """Resume an incomplete research run."""
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    state_dir = os.path.join(cfg["output_dir"], "state")
    runs = find_incomplete_runs(state_dir)

    if not runs:
        click.echo("[ERR-STA-003] No incomplete runs found to resume.")
        return

    click.echo("\nFinding incomplete runs...")
    for run in runs:
        click.echo(f"  Found: {run['run_id']} — \"{run['topic']}\" ({run['status']})")
        display_run_summary(run)
        decision = choose_resume_option(run)
        click.echo(f"Action: {decision['action']}")


if __name__ == "__main__":
    cli()
```

**Step 4: Run tests**

```bash
pytest tests/test_main.py -v
```

Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: CLI entry point — research/scheduler/resume commands with full pipeline"
```

---

### Task 16: Scheduler

**Files:**
- Create: `src/scheduler.py`
- Create: `tests/test_scheduler.py`

Wraps APScheduler. Validates the cron expression before starting (CFG-002, CFG-003). Runs the full pipeline per topic — no human approval gate (scheduled mode).

**Step 1: Write the failing tests**

```python
# tests/test_scheduler.py
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
    from src.scheduler import validate_cron
    validate_cron("0 8 * * MON")  # should not raise


def test_validate_cron_invalid_raises_cfg002():
    from src.scheduler import validate_cron
    from src.config import ConfigError
    with pytest.raises(ConfigError, match="CFG-002"):
        validate_cron("not a cron expression")


def test_validate_cron_invalid_field_raises_cfg003():
    from src.scheduler import validate_cron
    from src.config import ConfigError
    with pytest.raises(ConfigError, match="CFG-003"):
        validate_cron("99 8 * * MON")  # minute 99 is invalid


def test_start_scheduler_disabled_exits_early():
    from src.scheduler import start_scheduler
    cfg = make_sched_cfg()
    cfg["schedule"]["enabled"] = False
    with patch("src.scheduler.BlockingScheduler") as mock_sched:
        start_scheduler(cfg)
        mock_sched.assert_not_called()
```

**Step 2: Run to verify failure**

```bash
pytest tests/test_scheduler.py -v
```

Expected: `ImportError`.

**Step 3: Implement `src/scheduler.py`**

```python
import logging
import re

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import ConfigError

logger = logging.getLogger("agent")

_CRON_RE = re.compile(r"^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)$")


def validate_cron(expr: str) -> None:
    if not _CRON_RE.match(expr.strip()):
        raise ConfigError(f"[ERR-CFG-002] Invalid cron expression format: '{expr}'")
    try:
        CronTrigger.from_crontab(expr)
    except ValueError as e:
        raise ConfigError(f"[ERR-CFG-003] Invalid cron field value in '{expr}': {e}")


def start_scheduler(cfg: dict) -> None:
    sched_cfg = cfg.get("schedule", {})
    if not sched_cfg.get("enabled", False):
        logger.info("Scheduler is disabled in config.")
        return

    cron = sched_cfg.get("cron", "0 8 * * MON")
    timezone = sched_cfg.get("timezone", "UTC")
    topics = sched_cfg.get("topics", [])
    validate_cron(cron)

    def run_scheduled_topic(topic: str) -> None:
        from src.orchestrator import decompose_topic, run_parallel_research, OrchestratorError
        from src.synthesizer import synthesize, SynthesisError
        from src.pdf_formatter import generate_pdf, PDFError
        from src.email_sender import send_report_email, EmailError
        from src.state import create_master_state, update_master_state
        from src.logger import write_audit
        from datetime import datetime, timezone as tz
        import os

        run_id = datetime.now(tz.utc).strftime("%Y-%m-%dT%H-%M-%S")
        state_dir = os.path.join(cfg["output_dir"], "state")
        audit_path = cfg["audit"]["log_file"]
        write_audit(audit_path, {"event": "RUN_STARTED", "run_id": run_id,
                                  "mode": "scheduled", "topic": topic, "triggered_by": "scheduler"})
        create_master_state(run_id, topic, "scheduled", state_dir)
        try:
            subtopics = decompose_topic(topic, cfg)
            findings = run_parallel_research(run_id, subtopics, cfg, state_dir, dry_run=False)
            report = synthesize(topic, findings, cfg)
            pdf_path = generate_pdf(
                data={"topic": topic, "run_id": run_id,
                      "executive_summary": report["executive_summary"],
                      "full_report": report["full_report"],
                      "generated_at": datetime.now(tz.utc).isoformat()},
                output_dir=cfg["output_dir"],
            )
            to_list = cfg["email"].get("default_recipients", [])
            cc_list = cfg["email"].get("default_cc", [])
            send_report_email(pdf_path, topic, to_list, cc_list, audit_path, run_id)
            write_audit(audit_path, {"event": "EMAIL_SENT", "run_id": run_id, "to": to_list})
            write_audit(audit_path, {"event": "RUN_COMPLETED", "run_id": run_id, "status": "success"})
            update_master_state(run_id, state_dir, {"status": "COMPLETED"})
        except Exception as e:
            logger.error(f"[ERR-SCH-002] Scheduled run failed for '{topic}': {e}")
            write_audit(audit_path, {"event": "RUN_FAILED", "run_id": run_id, "error": str(e)})
            update_master_state(run_id, state_dir, {"status": "FAILED"})

    scheduler = BlockingScheduler(timezone=timezone)
    trigger = CronTrigger.from_crontab(cron, timezone=timezone)
    for topic in topics:
        scheduler.add_job(run_scheduled_topic, trigger, args=[topic], id=f"research-{topic[:20]}")

    logger.info(f"Scheduler started. Cron: '{cron}' | Topics: {topics}")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
    except Exception as e:
        raise ConfigError(f"[ERR-SCH-001] Scheduler failed to start: {e}")
```

**Step 4: Run tests**

```bash
pytest tests/test_scheduler.py -v
```

Expected: 4 PASSED.

**Step 5: Commit**

```bash
git add src/scheduler.py tests/test_scheduler.py
git commit -m "feat: APScheduler cron scheduler with CFG-002/003 cron validation"
```

---

### Task 17: Full Test Suite + Smoke Test

**Step 1: Run all unit tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests PASSED. Fix any failures before proceeding.

**Step 2: Run with coverage**

```bash
pip install pytest-cov
pytest tests/ --cov=src --cov-report=term-missing
```

Aim for >80% coverage.

**Step 3: Dry-run smoke test**

```bash
cp .env.example .env
# Add ANTHROPIC_API_KEY to .env
research-report research "AI trends in healthcare" --dry-run
```

Expected output:
```
Decomposing topic: AI trends in healthcare
Launching 2 research agents...
Synthesizing findings...
Generating PDF...
PDF saved: reports/2026-03-12-ai-trends-in-healthcare.pdf
[DRY RUN] Skipping email delivery.
```

**Step 4: Verify PDF and audit log**

```bash
ls -lh reports/*.pdf
cat reports/logs/audit.log
```

Expected: PDF file exists; audit log has `RUN_STARTED`, `REPORT_GENERATED`, `RUN_COMPLETED` entries.

**Step 5: Commit**

```bash
git add .
git commit -m "test: full suite passing, dry-run smoke test verified"
```

---

### Task 18: README

**Files:**
- Create: `README.md`

**Step 1: Create `README.md`**

```markdown
# Research-to-Report Agent

Autonomous agent: topic → parallel web research → PDF report → Gmail delivery.

**NotebookLM is optional.** Leave `notebooklm.notebook_ids: []` in `config.yaml` to use web search only.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in API keys in .env (ANTHROPIC_API_KEY and TAVILY_API_KEY are required)
# GOOGLE_CREDENTIALS_PATH is only needed if notebooklm.notebook_ids is set
```

## Usage

```bash
# After `pip install -e .`, the CLI binary is available as:
research-report research "AI trends in healthcare"

# Or run directly (src/ must be on PYTHONPATH, handled by pyproject.toml pythonpath setting):
python -m main research "AI trends in healthcare"

# With recipients
research-report research "AI trends" --email boss@company.com --email-cc reviewer@company.com

# Dry run (no API calls — for testing)
research-report research "AI trends" --dry-run

# Start scheduler (automated cron runs)
research-report scheduler start

# Resume an incomplete run
research-report resume
```

## Configuration

Edit `config.yaml`. Key settings:
- `notebooklm.notebook_ids: []` — leave empty for web-only research
- `schedule.enabled: true` — enable cron scheduler
- `email.default_recipients` — who receives reports

See `docs/plans/2026-03-12-research-to-report-design.md` for full config reference.

## Testing

```bash
pytest tests/ -v
```
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, usage, NotebookLM optional note"
```

---

## Summary of Files Created

> **Note (2026-03-16 refactor):** `src/` was restructured into logical subpackages. File paths below reflect the new locations. `src/__init__.py` was deleted — `src/` is now the package root (not itself a package). `pyproject.toml` was added with `[tool.pytest.ini_options] pythonpath = ["src"]` so all imports work without a `src.` prefix. The CLI binary `research-report` is exposed via `[project.scripts] research-report = "main:cli"`.

### New folder structure

```
src/
  main.py                     # CLI entry point (stays at root)
  agents/
    __init__.py
    orchestrator.py           # was src/orchestrator.py
    researcher.py             # was src/researcher.py
    synthesizer.py            # was src/synthesizer.py
  pdf/
    __init__.py
    formatter.py              # was src/pdf_formatter.py
    translator.py             # was src/translate_pdf.py
  delivery/
    __init__.py
    email_sender.py           # was src/email_sender.py
    approval.py               # was src/approval.py
  config/
    __init__.py               # re-exports load_config, ConfigError
    config.py                 # was src/config.py
  log/
    __init__.py
    logger.py                 # was src/logger.py
    state.py                  # was src/state.py
  run/
    __init__.py
    scheduler.py              # was src/scheduler.py
    resume.py                 # was src/resume.py
    preflight.py              # was src/preflight.py
  tools/
    __init__.py
    web_search.py             # unchanged
    notebooklm_reader.py      # unchanged
```

### Import path changes

All imports use the new paths without any `src.` prefix, e.g.:
- `from config import load_config, ConfigError`
- `from log.logger import setup_loggers, write_audit`
- `from agents.orchestrator import decompose_topic`
- `from pdf.formatter import generate_pdf`
- `from delivery.email_sender import send_report_email`
- `from run.preflight import run_preflight`

### File reference (new paths)

| File | Purpose |
|---|---|
| `src/config/config.py` | Config loader + CFG-001/006 enforcement |
| `src/config/__init__.py` | Re-exports `load_config`, `ConfigError` |
| `src/log/logger.py` | Agent + audit logging |
| `src/log/state.py` | Run state management + heartbeat |
| `src/run/preflight.py` | Pre-flight checks — COMPOSIO_API_KEY always required; notebooklm-mcp-cli checked when notebook_ids set |
| `src/tools/web_search.py` | Tavily web search (always used) |
| `src/tools/notebooklm_reader.py` | NotebookLM reader via MCP client (optional — only called when notebook_ids configured); exposes `query_notebook()` for text queries and `fetch_notebook_image()` for resolving `notebooklm://notebook-id/filename` image URIs used by the PDF formatter |
| `src/agents/researcher.py` | Research sub-agent — web always, NotebookLM conditionally |
| `src/agents/orchestrator.py` | Topic decomposition + parallel sub-agent launch |
| `src/agents/synthesizer.py` | Synthesis agent — exec summary + full report |
| `src/pdf/formatter.py` | ReportLab PDF generation with charts (bar/hbar/line/pie/stacked_bar via ReportLab graphics), image embedding (web URL, local file, notebooklm:// URI), and grey placeholder fallback for any unrenderable element |
| `src/pdf/translator.py` | PDF translation for non-English languages |
| `src/delivery/email_sender.py` | Gmail delivery with EML-004 duplicate guard |
| `src/delivery/approval.py` | Human-in-the-loop approval gate (ad-hoc only) |
| `src/run/resume.py` | Incomplete run detection + 4-option resume menu |
| `src/run/scheduler.py` | APScheduler cron integration |
| `src/main.py` | CLI entry point (Click) |
