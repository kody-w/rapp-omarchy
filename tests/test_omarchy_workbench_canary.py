import importlib.util
import json
import sys
from pathlib import Path

import pytest


DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("workbench_canary", DIRECTORY / "canary.py")
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


@pytest.mark.parametrize(
    ("start", "prompt", "state", "expected"),
    [
        (1, None, "blocked", "blocked-startup"),
        (0, 0, "blocked", "question-blocked"),
        (0, 1, "blocked", "attention-not-proved"),
        (0, 0, "unknown", "attention-not-proved"),
        (0, 0, "done", "attention-not-proved"),
    ],
)
def test_actual_state_is_not_reshaped_into_success(monkeypatch, start, prompt, state, expected):
    calls = []

    def invoke(*args):
        calls.append(args)
        return {
            "exit_code": 0,
            "stdout": json.dumps({"result": {"agent": {
                "pane_id": "wA:p1", "name": "rapp-canary", "agent_status": state,
            }}}),
            "stderr": "",
        }

    monkeypatch.setattr(CANARY, "invoke", invoke)
    record = {"start": {"exit_code": start}, "worktree": {"pane_id": "wA:p1"}}
    if prompt is not None:
        record["prompt"] = {"exit_code": prompt}
    CANARY.inspect_agent(record)
    assert record["status"] == expected
    assert [args[:2] for args in calls] == [("agent", "get"), ("agent", "read")]


def test_refuses_replaced_pane(monkeypatch):
    monkeypatch.setattr(CANARY, "invoke", lambda *args: {
        "exit_code": 0,
        "stdout": json.dumps({"result": {"agent": {
            "pane_id": "wB:p1", "name": "rapp-canary", "agent_status": "blocked",
        }}}),
        "stderr": "",
    })
    with pytest.raises(RuntimeError, match="recorded worktree"):
        CANARY.inspect_agent({"worktree": {"pane_id": "wA:p1"}})


def test_native_commands_are_named_and_read_only(monkeypatch):
    calls = []

    def execute(command, **kwargs):
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": "{}", "stderr": ""})()

    monkeypatch.setattr(CANARY.subprocess, "run", execute)
    CANARY.invoke("agent", "get", "rapp-canary")
    assert calls == [["herdr", "--session", "rapp1-workbench", "agent", "get", "rapp-canary"]]
