import pytest
from unittest.mock import patch, MagicMock


def make_orch_cfg():
    return {
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096, "max_subtopics": 5},
        "notebooklm": {"notebook_ids": []},
        "timeouts": {"sub_agent_sec": 120, "total_run_sec": 600},
        "output_dir": "/tmp/test-reports",
        "email": {"default_recipients": ["test@example.com"], "default_cc": []},
        "logging": {"level": "INFO", "log_to_file": False,
                    "log_file": "/tmp/agent.log", "max_file_size_mb": 1, "backup_count": 1},
        "audit": {"enabled": True, "log_file": "/tmp/audit.log", "format": "json"},
    }


def test_decompose_topic_returns_subtopics():
    from agents.orchestrator import decompose_topic
    with patch("agents.orchestrator.litellm_complete") as mock_llm:
        mock_llm.return_value = "1. Market trends\n2. Key players\n3. Regulation\n4. Future outlook"
        subtopics = decompose_topic("AI trends in healthcare", make_orch_cfg())
    assert len(subtopics) >= 2
    assert any("market" in s.lower() or "trend" in s.lower() for s in subtopics)


def test_decompose_topic_respects_max_subtopics():
    from agents.orchestrator import decompose_topic
    cfg = make_orch_cfg()
    cfg["agent"]["max_subtopics"] = 3
    with patch("agents.orchestrator.litellm_complete") as mock_llm:
        mock_llm.return_value = "1. Alpha\n2. Beta\n3. Gamma"
        decompose_topic("test topic", cfg)
    prompt_used = mock_llm.call_args[0][1][0]["content"]
    assert "3" in prompt_used


def test_decompose_topic_handles_numbered_list():
    from agents.orchestrator import decompose_topic
    with patch("agents.orchestrator.litellm_complete") as mock_llm:
        mock_llm.return_value = "1. Alpha\n2. Beta\n3. Gamma"
        subtopics = decompose_topic("test topic", make_orch_cfg())
    assert subtopics == ["Alpha", "Beta", "Gamma"]


def test_run_parallel_research_collects_results(tmp_path):
    from agents.orchestrator import run_parallel_research
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    with patch("agents.orchestrator.run_research_agent") as mock_agent:
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
    from agents.orchestrator import run_parallel_research
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    def mock_agent(run_id, idx, subtopic, cfg, state_dir, dry_run):
        if subtopic == "regulation":
            raise Exception("timeout")
        return f"findings for {subtopic}"

    with patch("agents.orchestrator.run_research_agent", side_effect=mock_agent):
        results = run_parallel_research(
            run_id="run-001",
            subtopics=["market trends", "regulation", "future outlook"],
            cfg=cfg,
            state_dir=state_dir,
            dry_run=False,
        )

    assert "market trends" in results
    assert "future outlook" in results
    assert results.get("regulation") is None


def test_all_subtopics_fail_raises_res003(tmp_path):
    from agents.orchestrator import run_parallel_research, OrchestratorError
    cfg = make_orch_cfg()
    state_dir = str(tmp_path / "state")

    with patch("agents.orchestrator.run_research_agent", side_effect=Exception("fail")):
        with pytest.raises(OrchestratorError, match="ERR-RES-003"):
            run_parallel_research("run-001", ["a", "b"], cfg, state_dir, dry_run=False)
