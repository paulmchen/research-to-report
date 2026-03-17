import json
import os
import pytest
from datetime import datetime, timezone


def test_create_master_state(tmp_path):
    from log.state import create_master_state, load_state
    run_id = "2026-03-12T08-00-01"
    state_dir = str(tmp_path / "state")
    state = create_master_state(run_id, "AI trends", "ad-hoc", state_dir)
    assert state["run_id"] == run_id
    assert state["status"] == "IN_PROGRESS"
    assert state["topic"] == "AI trends"
    path = os.path.join(state_dir, f"master-{run_id}.json")
    assert os.path.exists(path)


def test_update_master_state(tmp_path):
    from log.state import create_master_state, update_master_state, load_state
    run_id = "2026-03-12T08-00-02"
    state_dir = str(tmp_path / "state")
    create_master_state(run_id, "topic", "ad-hoc", state_dir)
    update_master_state(run_id, state_dir, {"status": "COMPLETED"})
    state = load_state(run_id, state_dir)
    assert state["status"] == "COMPLETED"


def test_create_subtopic_state(tmp_path):
    from log.state import create_subtopic_state, load_subtopic_state
    run_id = "2026-03-12T08-00-03"
    state_dir = str(tmp_path / "state")
    state = create_subtopic_state(run_id, 1, "market trends", state_dir)
    assert state["status"] == "IN_PROGRESS"
    assert state["topic"] == "market trends"
    path = os.path.join(state_dir, f"subtopic-1-{run_id}.json")
    assert os.path.exists(path)


def test_update_heartbeat(tmp_path):
    from log.state import create_subtopic_state, update_heartbeat, load_subtopic_state
    run_id = "2026-03-12T08-00-04"
    state_dir = str(tmp_path / "state")
    create_subtopic_state(run_id, 1, "topic", state_dir)
    update_heartbeat(run_id, 1, state_dir)
    state = load_subtopic_state(run_id, 1, state_dir)
    assert state["last_heartbeat"] is not None


def test_find_incomplete_runs(tmp_path):
    from log.state import create_master_state, find_incomplete_runs
    state_dir = str(tmp_path / "state")
    create_master_state("run-001", "topic A", "ad-hoc", state_dir)
    create_master_state("run-002", "topic B", "scheduled", state_dir)
    runs = find_incomplete_runs(state_dir)
    assert len(runs) == 2
    assert any(r["run_id"] == "run-001" for r in runs)


def test_find_incomplete_runs_includes_email_failed(tmp_path):
    from log.state import create_master_state, update_master_state, find_incomplete_runs
    state_dir = str(tmp_path / "state")
    create_master_state("run-email-fail", "topic", "ad-hoc", state_dir)
    update_master_state("run-email-fail", state_dir, {"status": "EMAIL_FAILED"})
    runs = find_incomplete_runs(state_dir)
    assert len(runs) == 1
    assert runs[0]["run_id"] == "run-email-fail"


def test_find_incomplete_runs_excludes_completed_and_failed(tmp_path):
    from log.state import create_master_state, update_master_state, find_incomplete_runs
    state_dir = str(tmp_path / "state")
    create_master_state("run-done", "topic", "ad-hoc", state_dir)
    update_master_state("run-done", state_dir, {"status": "COMPLETED"})
    create_master_state("run-fail", "topic", "ad-hoc", state_dir)
    update_master_state("run-fail", state_dir, {"status": "FAILED"})
    runs = find_incomplete_runs(state_dir)
    assert runs == []
