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
