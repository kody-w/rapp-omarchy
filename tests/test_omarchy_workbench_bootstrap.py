import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "herdr_bootstrap", ROOT / "herdr_bootstrap.py"
)
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_real_context_is_required_before_control(tmp_path, monkeypatch):
    monkeypatch.delenv("HERDR_ENV", raising=False)
    monkeypatch.setattr(bootstrap, "native", lambda *args: pytest.fail("outside-context control"))
    with pytest.raises(RuntimeError, match="inside"):
        bootstrap.caller(tmp_path)


def test_native_commands_always_name_the_owned_session(monkeypatch):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        return type("Result", (), {"returncode": 0, "stdout": '{"result":{}}', "stderr": ""})()

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    bootstrap.native("workspace", "list")
    assert calls == [["herdr", "--session", "rapp1-workbench", "workspace", "list"]]


def test_layout_uses_returned_ids_preserves_focus_and_is_repeatable(tmp_path, monkeypatch):
    root = tmp_path / "workbench"
    repository = root / "sources/omarchy"
    (repository / ".git").mkdir(parents=True)
    (root / "worktrees").mkdir()
    monkeypatch.chdir(root)
    for key, value in {
        "HERDR_ENV": "1",
        "HERDR_WORKSPACE_ID": "w41",
        "HERDR_TAB_ID": "w41:t97",
        "HERDR_PANE_ID": "w41:p83",
    }.items():
        monkeypatch.setenv(key, value)
    current = {"workspace_id": "w41", "tab_id": "w41:t97", "pane_id": "w41:p83"}
    workspaces = [{"workspace_id": "w41", "label": "initial"}]
    panes = {}
    calls = []

    def git(path, *arguments):
        if arguments == ("remote", "get-url", "origin"):
            return "https://github.com/omacom/omarchy.git"
        if arguments == ("rev-parse", "HEAD"):
            return "a" * 40
        if arguments == ("rev-parse", "--show-toplevel"):
            return str(path)
        if arguments == ("symbolic-ref", "--short", "HEAD"):
            return f"workbench/{path.name}"
        if arguments == ("rev-parse", "--path-format=absolute", "--git-common-dir"):
            return str(repository / ".git")
        raise AssertionError(arguments)

    def native(*arguments, **kwargs):
        calls.append(arguments)
        if arguments[:2] == ("pane", "current"):
            return {"pane": current}
        if arguments[:2] == ("workspace", "list"):
            return {"workspaces": workspaces}
        if arguments[:2] == ("workspace", "rename"):
            workspaces[0]["label"] = arguments[3]
            return {}
        if arguments[:2] == ("worktree", "create"):
            index = len(workspaces)
            wid = f"w{300 + index * 7}"
            destination = Path(arguments[arguments.index("--path") + 1])
            destination.mkdir()
            workspaces.append({"workspace_id": wid, "label": arguments[arguments.index("--label") + 1]})
            panes[wid] = {"workspace_id": wid, "tab_id": f"{wid}:t901", "pane_id": f"{wid}:p711"}
            return {}
        if arguments[:2] == ("pane", "list"):
            return {"panes": [panes[arguments[3]]]}
        if arguments[:2] == ("tab", "create"):
            suffix = len(calls)
            return {"root_pane": {"pane_id": f"w41:p{suffix}", "tab_id": f"w41:t{suffix}"}}
        if arguments[:2] in {("tab", "rename"), ("pane", "report-metadata")}:
            return {}
        raise AssertionError(arguments)

    monkeypatch.setattr(bootstrap, "git", git)
    monkeypatch.setattr(bootstrap, "native", native)
    state = bootstrap.setup(root, 2)
    assert state["control"] == current
    assert state["automatic_coding_agents"] == 0
    assert state["lanes"][0]["pane_id"] == "w307:p711"
    assert state["lanes"][1]["pane_id"] == "w314:p711"
    assert all("--no-focus" in args for args in calls if args[:2] in {("worktree", "create"), ("tab", "create")})
    assert not any(args[:2] in {("pane", "run"), ("agent", "start"), ("workspace", "close")} for args in calls)
    count = sum(args[:2] == ("worktree", "create") for args in calls)
    assert bootstrap.setup(root, 2) == state
    assert sum(args[:2] == ("worktree", "create") for args in calls) == count
    assert json.loads((root / "layout.json").read_text()) == state
    panes["w307"]["tab_id"] = "w307:t-replaced"
    with pytest.raises(RuntimeError, match="pane/tab"):
        bootstrap.setup(root, 2)


@pytest.mark.parametrize("failure", ["missing", "branch", "repository"])
def test_existing_worktrees_are_revalidated(tmp_path, monkeypatch, failure):
    destination = tmp_path / "lane-01"
    if failure != "missing":
        destination.mkdir()
    repository = tmp_path / "source"

    def git(path, *arguments):
        if arguments == ("rev-parse", "--show-toplevel"):
            return str(destination)
        if arguments == ("symbolic-ref", "--short", "HEAD"):
            return "other" if failure == "branch" else "workbench/lane-01"
        if arguments == ("rev-parse", "--path-format=absolute", "--git-common-dir"):
            return str(path / ".git")
        raise AssertionError(arguments)

    monkeypatch.setattr(bootstrap, "git", git)
    with pytest.raises(RuntimeError):
        bootstrap.validate_worktree(repository, destination, "workbench/lane-01")


def test_lane_count_is_bounded(tmp_path):
    with pytest.raises(ValueError, match="between"):
        bootstrap.setup(tmp_path, 17)


def test_void_mutations_do_not_require_a_read_result(monkeypatch):
    result = type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *args, **kwargs: result)
    assert bootstrap.native("workspace", "rename", "w9", "Owned", expect_json=False) is None
    with pytest.raises(RuntimeError, match="required JSON"):
        bootstrap.native("workspace", "list")
