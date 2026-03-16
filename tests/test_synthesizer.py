import pytest
from unittest.mock import patch


def make_syn_cfg():
    return {
        "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 8096},
    }


def test_synthesize_returns_executive_summary_and_body():
    from agents.synthesizer import synthesize
    findings = {
        "market trends": "AI healthcare market growing 30% YoY.",
        "regulation": "FDA increasing oversight of AI medical devices.",
    }
    with patch("agents.synthesizer.litellm_complete") as mock_llm:
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
    from agents.synthesizer import synthesize
    findings = {"topic": "some findings"}
    with patch("agents.synthesizer.litellm_complete") as mock_llm:
        result = synthesize("topic", findings, make_syn_cfg(), dry_run=True)
        mock_llm.assert_not_called()

    assert result["executive_summary"]
    assert result["full_report"]


def test_synthesize_empty_result_raises_syn001():
    from agents.synthesizer import synthesize, SynthesisError
    findings = {"topic": "findings"}
    with patch("agents.synthesizer.litellm_complete", return_value=""):
        with pytest.raises(SynthesisError, match="ERR-SYN-001"):
            synthesize("topic", findings, make_syn_cfg())


def test_synthesize_prompt_includes_chart_instruction():
    from agents.synthesizer import synthesize
    from unittest.mock import patch
    captured = []
    def fake_llm(model, messages, max_tokens):
        captured.append(messages[0]["content"])
        return "# Executive Summary\nSummary.\n\n---\n\n# Full Report\nBody."
    with patch("agents.synthesizer.litellm_complete", side_effect=fake_llm):
        synthesize("AI trends", {"subtopic 1": "findings"}, {
            "agent": {"default_model": "claude-sonnet-4-6", "max_tokens": 4096}
        })
    assert "```chart" in captured[0]
    assert "![" in captured[0]
