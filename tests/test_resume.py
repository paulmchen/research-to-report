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
    from run.resume import display_run_summary
    display_run_summary(make_master_state())
    captured = capsys.readouterr()
    assert "market trends" in captured.out
    assert "regulation" in captured.out


def test_choose_resume_option_1_retry():
    from run.resume import choose_resume_option
    with patch("builtins.input", return_value="1"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "retry_failed"


def test_choose_resume_option_2_skip():
    from run.resume import choose_resume_option
    with patch("builtins.input", return_value="2"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "skip_failed"


def test_choose_resume_option_3_restart():
    from run.resume import choose_resume_option
    with patch("builtins.input", return_value="3"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "restart"


def test_choose_resume_option_4_abort():
    from run.resume import choose_resume_option
    with patch("builtins.input", return_value="4"):
        decision = choose_resume_option(make_master_state())
    assert decision["action"] == "abort"
