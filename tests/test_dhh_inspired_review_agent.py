import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "dhh_reviewer", ROOT / "reviewer.py"
)
reviewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reviewer)


def test_rubric_is_a_labeled_simulation_without_side_effects(tmp_path, monkeypatch):
    location = tmp_path / "absent"
    monkeypatch.setenv("RAPP_REVIEW_HOME", str(location))
    result = json.loads(reviewer.DhhInspiredReviewAgent().perform(action="rubric"))
    assert result["status"] == "ok"
    assert result["simulation"] is True
    assert result["authority"] == "review-only"
    assert "not DHH" in result["rubric"]
    assert not location.exists()


def test_reviewer_exposes_no_tools_and_no_automatic_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("RAPP_REVIEW_HOME", str(tmp_path / "reviewer"))
    monkeypatch.setenv("COPILOT_ALLOW_ALL", "true")
    monkeypatch.setenv("GH_TOKEN", "other-fixture")
    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "fixture-only-not-a-real-token")
    monkeypatch.delenv("COPILOT_PROVIDER_BASE_URL", raising=False)
    calls = []

    class Process:
        returncode = 0

        def communicate(self, timeout):
            assert timeout == reviewer.TIMEOUT_SECONDS
            return "Keep the working private transport; verify the strict protocol boundary.", ""

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        assert "--available-tools=" in command
        assert "--allow-all-tools" not in command
        assert "--allow-all" not in command
        assert command[command.index("--model") + 1] == "gpt-5.6-sol-fast"
        assert command[command.index("--effort") + 1] == "max"
        assert "--disable-builtin-mcps" in command
        assert "--no-custom-instructions" in command
        assert "--no-remote-export" in command
        for kind in ("shell", "write", "url"):
            assert ["--deny-tool", kind] in [command[index:index + 2] for index in range(len(command) - 1)]
        env = kwargs["env"]
        assert env["COPILOT_ALLOW_ALL"] == "false"
        assert env["COPILOT_GITHUB_TOKEN"] == "fixture-only-not-a-real-token"
        assert "GH_TOKEN" not in env and "GITHUB_TOKEN" not in env
        assert str(tmp_path / "reviewer") in env["COPILOT_HOME"]
        return Process()

    monkeypatch.setattr(reviewer.subprocess, "Popen", popen)
    result = reviewer.review({"herdr": {"lanes": 16}, "transport": "private SSH"})
    assert len(calls) == 1
    assert result["simulation"] is True
    assert result["not_dhh_or_endorsement"] is True
    assert result["changes_applied"] is False
    assert "fixture-only" not in json.dumps(result)


@pytest.mark.parametrize("evidence", [{}, [], {"too_much": "x" * 33000}])
def test_missing_or_oversized_evidence_is_not_reviewed(evidence, monkeypatch):
    monkeypatch.setattr(reviewer.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("model must not start"))
    with pytest.raises(ValueError):
        reviewer.review(evidence)


def test_authentication_does_not_borrow_grail_environment(monkeypatch):
    def run(command, **kwargs):
        assert command == ["gh", "auth", "token"]
        assert "GITHUB_TOKEN" not in kwargs["env"]
        assert "GH_TOKEN" not in kwargs["env"]
        return type("Result", (), {"returncode": 0, "stdout": "independent-fixture", "stderr": ""})()

    monkeypatch.setattr(reviewer.subprocess, "run", run)
    assert reviewer._token({"GITHUB_TOKEN": "do-not-borrow", "GH_TOKEN": "do-not-borrow"}) == "independent-fixture"
