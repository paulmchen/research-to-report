import json
import os
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
    from agents.researcher import run_research_agent
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete") as mock_llm:
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
    from agents.researcher import run_research_agent
    cfg = make_research_cfg(notebook_ids=[])
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)
        mock_nb.assert_not_called()


def test_researcher_calls_notebooklm_when_configured(tmp_path):
    """When notebook_ids is set, NotebookLM reader IS called for each ID."""
    from agents.researcher import run_research_agent
    cfg = make_research_cfg(notebook_ids=["folder-abc", "folder-xyz"])
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_nb.return_value = {"name": "NotebookLM (noteboo...)", "content": "notebook content"}
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)
        assert mock_nb.call_count == 2  # called once per notebook_id


def test_researcher_writes_state_file(tmp_path):
    from agents.researcher import run_research_agent
    from log.state import load_subtopic_state
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete") as mock_llm:
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_llm.return_value = "findings"
        run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=False)

    state = load_subtopic_state("run-001", 1, state_dir)
    assert state["status"] == "COMPLETED"
    assert state["result"] is not None


def test_researcher_dry_run_skips_api_calls(tmp_path):
    from agents.researcher import run_research_agent
    cfg = make_research_cfg()
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete") as mock_llm:
        result = run_research_agent("run-001", 1, "topic", cfg, state_dir, dry_run=True)
        mock_web.assert_not_called()
        mock_nb.assert_not_called()
        mock_llm.assert_not_called()

    assert result  # returns stub findings


def _read_audit_events(audit_log: str) -> list[dict]:
    events = []
    with open(audit_log) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def test_web_search_audit_includes_total_chars(tmp_path):
    """WEB_SEARCH audit event must include total_chars so content volume is visible."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [
            {"title": "T1", "url": "u1", "content": "a" * 300},
            {"title": "T2", "url": "u2", "content": "b" * 200},
        ]
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    web_event = next(e for e in events if e["event"] == "WEB_SEARCH")
    assert web_event["results_count"] == 2
    assert web_event["total_chars"] == 500


def test_web_search_empty_warning_logged_on_zero_results(tmp_path):
    """WEB_SEARCH_EMPTY warning event must be logged when Tavily returns no results."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search", return_value=[]), \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    event_names = [e["event"] for e in events]
    assert "WEB_SEARCH_EMPTY" in event_names

    empty_event = next(e for e in events if e["event"] == "WEB_SEARCH_EMPTY")
    assert "warning" in empty_event


def test_web_search_empty_warning_not_logged_when_results_present(tmp_path):
    """WEB_SEARCH_EMPTY must NOT be logged when results are returned normally."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "content"}]
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    assert not any(e["event"] == "WEB_SEARCH_EMPTY" for e in events)


def test_sources_combined_logged_with_web_only(tmp_path):
    """SOURCES_COMBINED must be logged before the LLM call with correct web-only counts."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [
            {"title": "A", "url": "u1", "content": "content one"},
            {"title": "B", "url": "u2", "content": "content two"},
        ]
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    combined = next(e for e in events if e["event"] == "SOURCES_COMBINED")
    assert combined["web_results_count"] == 2
    assert combined["notebooklm_results_count"] == 0
    assert combined["total_chars"] > 0


def test_sources_combined_logged_with_notebooklm_included(tmp_path):
    """SOURCES_COMBINED must reflect NotebookLM content when the query succeeds."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(notebook_ids=["nb-1"]), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "web content"}]
        mock_nb.return_value = {"name": "NotebookLM (nb-1...)", "content": "notebook content here"}
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    combined = next(e for e in events if e["event"] == "SOURCES_COMBINED")
    assert combined["web_results_count"] == 1
    assert combined["notebooklm_results_count"] == 1
    assert combined["total_chars"] > len("web content")  # includes notebook content too


def test_sources_combined_shows_zero_notebooklm_on_failure(tmp_path):
    """When NotebookLM query fails, SOURCES_COMBINED must show notebooklm_results_count=0."""
    from agents.researcher import run_research_agent
    from tools.web_search import ToolError
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(notebook_ids=["nb-1"]), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook", side_effect=ToolError("[ERR-NTB-003] server error")), \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "web content"}]
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    combined = next(e for e in events if e["event"] == "SOURCES_COMBINED")
    assert combined["notebooklm_results_count"] == 0
    assert combined["web_results_count"] == 1


def test_notebooklm_query_audit_includes_content_chars(tmp_path):
    """NOTEBOOKLM_QUERY audit event must include content_chars so content size is visible."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(notebook_ids=["nb-1"]), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_nb.return_value = {"name": "NotebookLM (nb-1...)", "content": "a" * 500}
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    nb_event = next(e for e in events if e["event"] == "NOTEBOOKLM_QUERY")
    assert nb_event["content_chars"] == 500


def test_research_completed_logged_with_findings_chars(tmp_path):
    """RESEARCH_COMPLETED must be logged after the LLM returns, with findings_chars."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.litellm_complete", return_value="x" * 800):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    events = _read_audit_events(audit_log)
    completed = next(e for e in events if e["event"] == "RESEARCH_COMPLETED")
    assert completed["findings_chars"] == 800


def test_audit_event_order_is_web_then_notebooklm_then_combined_then_completed(tmp_path):
    """Events must appear in the correct pipeline order in the audit log."""
    from agents.researcher import run_research_agent
    audit_log = str(tmp_path / "audit.log")
    cfg = {**make_research_cfg(notebook_ids=["nb-1"]), "audit": {"log_file": audit_log}}
    state_dir = str(tmp_path / "state")

    with patch("agents.researcher.web_search") as mock_web, \
         patch("agents.researcher.query_notebook") as mock_nb, \
         patch("agents.researcher.litellm_complete", return_value="findings"):
        mock_web.return_value = [{"title": "T", "url": "u", "content": "c"}]
        mock_nb.return_value = {"name": "NotebookLM (nb-1...)", "content": "nb content"}
        run_research_agent("run-001", 1, "topic", cfg, state_dir)

    event_names = [e["event"] for e in _read_audit_events(audit_log)]
    assert event_names.index("WEB_SEARCH") < event_names.index("NOTEBOOKLM_QUERY")
    assert event_names.index("NOTEBOOKLM_QUERY") < event_names.index("SOURCES_COMBINED")
    assert event_names.index("SOURCES_COMBINED") < event_names.index("RESEARCH_COMPLETED")
