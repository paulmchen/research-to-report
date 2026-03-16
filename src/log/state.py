import json
import os
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _master_path(run_id: str, state_dir: str) -> str:
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"master-{run_id}.json")


def _subtopic_path(run_id: str, idx: int, state_dir: str) -> str:
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"subtopic-{idx}-{run_id}.json")


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
        if fname.startswith("master-") and fname.endswith(".json"):
            state = _read(os.path.join(state_dir, fname))
            if state.get("status") == "IN_PROGRESS":
                runs.append(state)
    return runs
