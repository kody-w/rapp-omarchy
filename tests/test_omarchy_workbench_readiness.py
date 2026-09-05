import importlib.util
import json
import sys
from pathlib import Path


DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("workbench_readiness", DIRECTORY / "workbench.py")
WORKBENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKBENCH)


def test_readiness_never_enables_an_unreviewed_adapter(tmp_path, monkeypatch):
    class Native:
        def inspect(self, project):
            assert project == WORKBENCH.PROJECT
            return {
                "activation": {"ready": True, "findings": []},
                "workspace": {"identity": {"rappid": "fixture-world"}},
                "project": {
                    "stream_id": "fixture-project", "head": {"seq": 3},
                    "completed_cycles": 0, "model_context_approved": False,
                },
            }

        def due_reviews(self, project):
            return [{"project": project}]

    monkeypatch.setattr(WORKBENCH, "components", lambda root, state: (Native(), ()))
    monkeypatch.setattr(WORKBENCH.protocol, "activation_status", lambda: {
        "accepted": True, "reasons": [], "registry": {"registry_seq": 3},
    })
    result = WORKBENCH.status(tmp_path, tmp_path)
    assert result["control_authority_ready"] is True
    assert result["native_project_ready"] is True
    assert result["native_due"] is True
    assert result["review_state"] == "held"
    assert result["automatic_inference"] is False
    assert result["accepted_rapp1_operation"] is False
    assert "no reviewed inference adapter" in result["reasons"][-1]
    assert json.loads((tmp_path / "readiness.json").read_text()) == result


def test_readiness_timer_is_separate_from_the_native_cycle_budget():
    timer = (DIRECTORY / "omarchy-rapp1-readiness.timer").read_text()
    service = (DIRECTORY / "omarchy-rapp1-readiness.service").read_text()
    assert "OnUnitActiveSec=30min" in timer
    assert "PrivateNetwork=yes" in service
    assert "workbench.py tick" in service
    assert "copilot " not in service
    assert "Restart=" not in service
