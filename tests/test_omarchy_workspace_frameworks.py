from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest


WORKBENCH = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "omarchy_workbench_frameworks",
    WORKBENCH / "frameworks.py",
)
frameworks = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = frameworks
SPEC.loader.exec_module(frameworks)


def sources() -> frameworks.NativeSources:
    native = Path(os.environ.get("RAPP_WORKBENCH_NATIVE_SOURCES", WORKBENCH / "vendor"))
    authority = Path(os.environ.get("RAPP1_REFERENCE_DIR", WORKBENCH / "vendor/rapp-1"))
    return frameworks.NativeSources(
        projects=native / "rapp-projects",
        workspace=native / "rapp-workspace",
        sdk=native / "rapp-sdk",
        herdr=native / "rapp-herdr",
        rapp1=authority,
        registry=Path(os.environ.get("RAPP1_REGISTRY_PATH", WORKBENCH / "vendor/rapp-map/ecosystem-spec.json")),
    )


@pytest.fixture(autouse=True)
def native_sources_required():
    selected = sources()
    if not all(path.is_dir() for path in (
        selected.projects, selected.workspace, selected.sdk, selected.rapp1, selected.herdr,
    )) or not selected.registry.is_file():
        pytest.skip("Set RAPP_WORKBENCH_NATIVE_SOURCES, RAPP1_REFERENCE_DIR, and RAPP1_REGISTRY_PATH to pinned checkouts.")


def git(path: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return result.stdout.strip()


def make_layout(root: Path, count: int = 2) -> Path:
    lanes = []
    for number in range(1, count + 1):
        lane = root / f"lane-{number:02d}"
        lane.mkdir(parents=True)
        branch = f"workbench/lane-{number:02d}"
        subprocess.run(
            ["git", "init", "--quiet", "--initial-branch", branch, str(lane)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        (lane / "README.md").write_text(
            f"lane {number}\n",
            encoding="utf-8",
        )
        git(lane, "add", "README.md")
        subprocess.run(
            [
                "git",
                "-C",
                str(lane),
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "--quiet",
                "-m",
                "fixture",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        lanes.append(
            {
                "number": number,
                "path": str(lane),
                "branch": branch,
                "workspace_id": f"w{number}",
                "tab_id": f"w{number}:t1",
                "pane_id": f"w{number}:p1",
            }
        )
    path = root / "layout.json"
    path.write_text(
        json.dumps(
            {
                "format": "omarchy-workbench-layout-v1",
                "session": "rapp1-workbench",
                "source_commit": git(Path(lanes[0]["path"]), "rev-parse", "HEAD"),
                "lanes": lanes,
                "automatic_coding_agents": 0,
                "review_authority": "review-only",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def initialized(
    tmp_path: Path,
    now: list[float],
    *,
    name: str = "world",
) -> frameworks.WorkbenchFrameworks:
    adapter = frameworks.WorkbenchFrameworks(
        tmp_path / name,
        sources(),
        clock=lambda: now[0],
    )
    adapter.initialize_solo_world(
        slug=f"omarchy-{name}",
        name=f"Omarchy {name.title()}",
        owner="kody-w",
        world_id=f"omarchy:{name}",
    )
    return adapter


def prepared(
    tmp_path: Path,
    now: list[float],
    *,
    max_seconds_per_cycle: int = 900,
) -> tuple[frameworks.WorkbenchFrameworks, object, Path]:
    adapter = initialized(tmp_path, now)
    adapter.ensure_project(
        "omarchy-workbench-standardization",
        title="Omarchy Workbench Standardization",
        goal="Standardize a private, review-only RAPP custom workbench.",
        owner="kody-w",
        origin="local Omarchy workbench",
    )
    actor = adapter.review_actor(session_id="rapp1-workbench")
    layout = make_layout(tmp_path / "existing-worktrees")
    adapter.bind_worktree_layout(
        "omarchy-workbench-standardization",
        actor,
        layout_path=layout,
        repository="https://github.com/omacom/omarchy.git",
        lease_seconds=40_000,
    )
    adapter.arm_review_policy(
        "omarchy-workbench-standardization",
        actor,
        lease_seconds=40_000,
        max_seconds_per_cycle=max_seconds_per_cycle,
    )
    return adapter, actor, layout


def test_repeat_initialization_preserves_identity_and_private_worlds_do_not_share(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    first = initialized(tmp_path, now, name="one")
    first_identity = first.world_identity()
    repeated = first.initialize_solo_world(
        slug="omarchy-one",
        name="Omarchy One",
        owner="kody-w",
        world_id="omarchy:one",
    )
    second = initialized(tmp_path, now, name="two")

    assert repeated["identity"] == first_identity
    assert second.world_identity()["rappid"] != first_identity["rappid"]
    opened = first.ensure_project(
        "only-first",
        title="Only First",
        goal="Prove roots are isolated.",
        owner="kody-w",
        origin="fixture",
    )
    reopened = first.ensure_project(
        "only-first",
        title="Only First",
        goal="Prove roots are isolated.",
        owner="kody-w",
        origin="fixture",
    )
    assert opened["identity"] == reopened["identity"]
    assert reopened["created"] is False
    assert [row["project"] for row in first.project_store().rebuild()] == [
        "only-first"
    ]
    assert second.project_store().rebuild() == []
    assert (first.root / "README.md").read_text().startswith(
        "# PRIVATE RAPP Workspace — NEVER PUBLISH"
    )


def test_native_layout_policy_due_cycle_and_receipts_are_thin(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    adapter, actor, layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    store = adapter.project_store()
    state = adapter._state(project)
    policy = state["cell_policy"]

    assert policy["cadence_seconds"] == 1800
    assert policy["budgets"] == {
        "max_cycles": 10,
        "max_seconds_per_cycle": 900,
    }
    assert set(policy["may"]) == {"read", "test", "draft"}
    assert {
        "send",
        "sign",
        "pay",
        "purchase",
        "delete_external",
        "publish_remote",
        "merge",
        "deploy",
        "network_change",
    } <= set(policy["never"])
    assert policy["human_gates"] == [
        "external side effect",
        "budget increase",
    ]
    assert "Omarchy Workbench Standardization" not in store.model_context(
        ("local",)
    )
    with pytest.raises(frameworks.FrameworkError, match="owner approval"):
        adapter.approve_model_context(project)

    now[0] += 1801
    assert [row["project"] for row in adapter.due_reviews(project)] == [project]
    receipt = tmp_path / "approved-observation.json"
    body = b'{"changed":true,"scope":"review-only"}\n'
    receipt.write_bytes(body)
    result = adapter.record_review_cycle(
        project,
        actor,
        outcome="completed",
        observations=["The approved input changed."],
        proposed=["Keep the smallest review-only next step."],
        applied=["Recorded the review result only."],
        blockers=[],
        action_classes=["read", "test", "draft"],
        elapsed_seconds=120,
        receipts=[receipt.resolve()],
    )

    assert result["status"] == "ok"
    assert result["cycle"] == 1
    assert result["receipt_verdict"] == "pass"
    assert result["receipts"][0]["path"] == str(receipt.resolve())
    project_path = store.project_path(project)
    assert not (project_path / receipt.name).exists()
    with zipfile.ZipFile(project_path / "PROJECT.egg") as archive:
        assert receipt.name not in archive.namelist()
        assert body not in [archive.read(name) for name in archive.namelist()]

    inspected = adapter.inspect(project)
    assert inspected["project"]["board"] == str(
        adapter.projects_root / "BOARD.md"
    )
    assert inspected["project"]["resume"]["checkpoint"]["workspace"]["cwd"] == str(
        tmp_path / "existing-worktrees/lane-01"
    )
    observation_path = Path(inspected["project"]["state"]["checkpoint"]["artifacts"][0]["path"])
    assert observation_path.parent == adapter.root / "worktree-observations"
    assert json.loads(observation_path.read_text())["layout_path"] == str(layout.resolve())

    now[0] += 1801
    before = len(store.frames(project))
    skipped = adapter.record_review_cycle(
        project,
        actor,
        outcome="completed",
        observations=["Text changed, but the approved receipt did not."],
        proposed=["Do not spend another review cycle."],
        applied=[],
        blockers=[],
        action_classes=["read"],
        elapsed_seconds=1,
        receipts=[receipt.resolve()],
    )
    assert skipped["status"] == "skipped"
    assert len(store.frames(project)) == before


def test_native_policy_enforces_time_actions_and_ten_changed_input_cycles(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    adapter, actor, _layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    store = adapter.project_store()
    receipt = tmp_path / "cycle-input.txt"
    now[0] += 1801

    receipt.write_text("too slow\n", encoding="utf-8")
    before = len(store.frames(project))
    with pytest.raises(adapter.projects.ProjectError, match="time budget"):
        adapter.record_review_cycle(
            project,
            actor,
            outcome="completed",
            observations=["review"],
            proposed=["stop"],
            applied=[],
            blockers=[],
            action_classes=["read"],
            elapsed_seconds=901,
            receipts=[receipt.resolve()],
        )
    assert len(store.frames(project)) == before

    with pytest.raises(adapter.projects.ProjectError, match="outside policy"):
        adapter.record_review_cycle(
            project,
            actor,
            outcome="completed",
            observations=["review"],
            proposed=["stop"],
            applied=[],
            blockers=[],
            action_classes=["write_local"],
            elapsed_seconds=1,
            receipts=[receipt.resolve()],
        )
    assert len(store.frames(project)) == before

    for cycle in range(10):
        receipt = tmp_path / f"cycle-input-{cycle}.txt"
        receipt.write_text(f"changed input {cycle}\n", encoding="utf-8")
        result = adapter.record_review_cycle(
            project,
            actor,
            outcome="completed",
            observations=[f"review {cycle}"],
            proposed=["wait"],
            applied=["recorded review"],
            blockers=[],
            action_classes=["read", "draft"],
            elapsed_seconds=10,
            receipts=[receipt.resolve()],
        )
        assert result["cycle"] == cycle + 1
        now[0] += 1801

    assert adapter.due_reviews(project) == []
    assert adapter._state(project)["cell_cycles"][-1]["cycle"] == 10


def test_blocked_review_cycle_is_recorded_by_native_cycle_and_status(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    adapter, actor, _layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    receipt = tmp_path / "missing-authority-evidence.txt"
    receipt.write_text("registry binding still missing\n", encoding="utf-8")
    now[0] += 1801

    result = adapter.record_review_cycle(
        project,
        actor,
        outcome="blocked",
        observations=["The project stream has no signed genesis binding."],
        proposed=["Obtain owner-authorized registration."],
        applied=[],
        blockers=["Never invent substitute authority."],
        action_classes=["read", "draft"],
        elapsed_seconds=30,
        receipts=[receipt.resolve()],
    )

    assert result["outcome"] == "blocked"
    assert result["receipt_verdict"] == "pass"
    state = adapter._state(project)
    assert state["status"] == "review blocked"
    assert state["blockers"] == ["Never invent substitute authority."]
    assert state["cell_cycles"][-1]["rejected"] == [
        "Never invent substitute authority."
    ]


def test_active_native_lease_blocks_a_second_writer(tmp_path: Path) -> None:
    now = [1_788_192_000.0]
    adapter, _actor, _layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    foreign = adapter.review_actor(
        session_id="foreign-session",
        actor_id="foreign-reviewer",
    )
    store = adapter.project_store()

    with pytest.raises(adapter.projects.ProjectError, match="another actor"):
        store.punchin(
            project,
            foreign,
            location=str(tmp_path),
            intent="compete",
            role="reviewer",
        )
    with pytest.raises(adapter.projects.ProjectError, match="another actor"):
        store.status(
            project,
            foreign,
            location=str(tmp_path),
            status="competing",
            artifacts=[],
            blockers=[],
            next_action="stop",
            pct=0,
        )


def test_workspace_reference_writer_and_current_projects_profile_conflict_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1_788_192_000.0]
    adapter = initialized(tmp_path, now)
    project = "writer-compatibility"
    adapter.ensure_project(
        project,
        title="Writer Compatibility",
        goal="Measure the two pinned writer profiles.",
        owner="kody-w",
        origin="fixture",
    )
    actor = adapter.review_actor(session_id="compat")
    store = adapter.project_store()
    store.punchin(
        project,
        actor,
        location=str(tmp_path),
        intent="measure",
        role="reviewer",
    )
    monkeypatch.setenv("RAPP_PROJECTS_ROOT", str(adapter.projects_root))
    monkeypatch.setenv("RAPP1_PATH", str(sources().rapp1))
    previous = sys.modules.pop("rapp", None)
    reference_path = str(sources().rapp1)
    prior_sys_path = list(sys.path)
    try:
        native_spec = importlib.util.spec_from_file_location(
            "workspace_append_frame_fixture",
            sources().workspace / "tools/append_frame.py",
        )
        workspace_writer = importlib.util.module_from_spec(native_spec)
        native_spec.loader.exec_module(workspace_writer)
        assert len(workspace_writer.verify_chain(project)) == 2
        workspace_writer.append(
            project,
            "work.status",
            {"status": "minimal workspace profile"},
            actor.id,
        )
    finally:
        sys.path[:] = prior_sys_path
        sys.modules.pop("rapp", None)
        if previous is not None:
            sys.modules["rapp"] = previous

    with pytest.raises(adapter.projects.ProjectError, match="missing required fields"):
        store.frames(project)


def test_activation_uses_signed_bindings_and_reports_measured_upstream_gaps(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    adapter = initialized(tmp_path, now)
    project = "authority-gap"
    adapter.ensure_project(
        project,
        title="Authority Gap",
        goal="Expose, never paper over, native compatibility gaps.",
        owner="kody-w",
        origin="fixture",
    )
    status = adapter.activation_status(project)
    by_code = {finding["code"]: finding for finding in status["findings"]}

    assert status["ready"] is False
    assert by_code["signed-registry"]["ok"] is True
    assert by_code["accepted-rapp1-checkpoint"]["ok"] is True
    assert by_code["canonical-frame-verification"]["ok"] is True
    assert by_code["signed-kind-binding"]["ok"] is True
    assert by_code["registered-organism-variant"]["ok"] is True
    assert by_code["registered-project-genesis"]["ok"] is False
    assert by_code["workspace-project-owner-binding"]["ok"] is False
    assert by_code["canonical-keyless-mint-profile"]["ok"] is True
    assert by_code["canonical-project-egg"]["ok"] is False
    assert "UTF-8 flags" in by_code["canonical-project-egg"]["detail"]
    assert {
        "registered-project-genesis",
        "workspace-project-owner-binding",
        "canonical-project-egg",
    } <= set(status["blocked_by"])
    with pytest.raises(frameworks.ActivationRefused):
        adapter.require_activation(project)
    receipt_path = adapter.root / "mint-inputs" / f"{project}.json"
    receipt_path.unlink()
    missing = adapter.activation_status(project)
    assert "canonical-keyless-mint-profile" in missing["blocked_by"]


def test_optional_herdr_estate_is_plan_only_and_never_fakes_twins(
    tmp_path: Path,
) -> None:
    now = [1_788_192_000.0]
    adapter = initialized(tmp_path, now)
    inventory = tmp_path / "real-twin-inventory"
    inventory.mkdir()

    plan = adapter.herdr_estate_plan(inventory_roots=[inventory.resolve()])

    assert plan["launched"] is False
    assert plan["altered_existing_session"] is False
    assert plan["worktree_panes_are_twins"] is False
    device = plan["plan"]["devices"][0]
    assert device["enabled"] is False
    assert device["session"] == "rapp1-workbench"
    assert device["inventory_roots"] == [str(inventory.resolve())]
    assert device["neighborhoods"] == []
    document = json.loads(Path(plan["manifest"]).read_text(encoding="utf-8"))
    assert "buddy_owner" not in document
    assert document["devices"][0]["neighborhoods"] == []
    assert adapter.herdr_estate_plan(inventory_roots=[])["created"] is False


@pytest.mark.parametrize("operation", ["layout", "policy"])
def test_same_actor_preparation_renews_an_expired_native_lease(tmp_path, operation):
    now = [1_788_192_000.0]
    adapter, actor, layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    before = len(adapter.project_store().frames(project))
    now[0] += 40_001
    if operation == "layout":
        result = adapter.bind_worktree_layout(
            project, actor, layout_path=layout,
            repository="https://github.com/omacom/omarchy.git", lease_seconds=7200,
        )
    else:
        result = adapter.arm_review_policy(project, actor, lease_seconds=7200)
    assert result["created"] is False
    state = adapter._state(project)
    assert adapter.projects_core._parse_utc(state["lease_expires_utc"]) > now[0]
    assert len(adapter.project_store().frames(project)) == before + 1


@pytest.mark.parametrize("change", ["primary-dirty", "secondary-dirty", "secondary-head", "repository"])
def test_checkpoint_binds_live_resume_state_for_all_lanes(tmp_path, change):
    now = [1_788_192_000.0]
    adapter, actor, layout = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    before = adapter._state(project)["checkpoint"]
    repository = "https://github.com/omacom/omarchy.git"
    lane = tmp_path / "existing-worktrees" / ("lane-01" if change == "primary-dirty" else "lane-02")
    if change == "repository":
        repository = "https://github.com/example/alternate"
    else:
        (lane / "README.md").write_text("changed resume state\n")
        if change == "secondary-head":
            git(lane, "add", "README.md")
            git(lane, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                "commit", "--quiet", "-m", "second head")
    result = adapter.bind_worktree_layout(
        project, actor, layout_path=layout, repository=repository,
    )
    assert result["created"] is True
    after = adapter._state(project)["checkpoint"]
    assert before["artifacts"][0]["sha256"] != after["artifacts"][0]["sha256"]
    assert Path(before["artifacts"][0]["path"]).is_file()
    if change == "primary-dirty":
        assert after["workspace"]["dirty_paths"] == ["README.md"]
    snapshot = json.loads(Path(after["artifacts"][0]["path"]).read_text())
    assert snapshot["repository"] == repository
    assert len(snapshot["lanes"]) == 2
    assert adapter.bind_worktree_layout(
        project, actor, layout_path=layout, repository=repository,
    )["created"] is False


def cycle_arguments(receipt, *, blocked=False):
    return {
        "outcome": "blocked" if blocked else "completed",
        "observations": ["Only the frozen approved input was reviewed."],
        "proposed": (value for value in ["Wait for operator decision."]),
        "applied": [],
        "blockers": (value for value in (["authority missing"] if blocked else [])),
        "action_classes": ["read", "draft"],
        "elapsed_seconds": 2,
        "receipts": [receipt],
    }


def test_same_actor_concurrent_reviews_append_exactly_one_cycle(tmp_path, monkeypatch):
    now = [1_788_192_000.0]
    adapter, actor, _ = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    now[0] += 1801
    receipt = tmp_path / "frozen-input.json"
    receipt.write_text('{"approved":true}\n')
    store = adapter.project_store()
    original = store.record_cell_cycle

    def slow_append(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "record_cell_cycle", slow_append)
    barrier = Barrier(2)

    def record(_):
        barrier.wait(timeout=10)
        return adapter.record_review_cycle(project, actor, **cycle_arguments(receipt))

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(record, range(2)))
    assert sorted(result["status"] for result in results) == ["ok", "skipped"]
    events = [frame["payload"]["event"] for frame in store.frames(project)]
    assert events.count("cell.cycle") == 1
    assert events.count("work.status") == 1
    assert events.count("project.verify") == 1


@pytest.mark.parametrize("stage", ["before-status", "after-status", "before-verify", "after-verify"])
def test_partial_review_recovers_from_native_history_without_consuming_another_cycle(tmp_path, monkeypatch, stage):
    now = [1_788_192_000.0]
    adapter, actor, _ = prepared(tmp_path, now)
    project = "omarchy-workbench-standardization"
    now[0] += 1801
    receipt = tmp_path / "frozen-blocked-input.json"
    receipt.write_text('{"authority":"missing"}\n')
    store = adapter.project_store()
    timing, method = stage.split("-")
    original = getattr(store, method)
    interrupted = False

    def fail_once(*args, **kwargs):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            if timing == "after":
                original(*args, **kwargs)
            raise OSError("simulated process interruption")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, method, fail_once)
    with pytest.raises(OSError, match="process interruption"):
        adapter.record_review_cycle(project, actor, **cycle_arguments(receipt, blocked=True))
    assert adapter.due_reviews(project) == []
    result = adapter.record_review_cycle(project, actor, **cycle_arguments(receipt, blocked=True))
    assert result["cycle"] == 1
    assert result["outcome"] == "blocked"
    assert result["receipt_verdict"] == "pass"
    assert adapter._state(project)["blockers"] == ["authority missing"]
    events = [frame["payload"]["event"] for frame in store.frames(project)]
    assert events.count("cell.cycle") == 1
    assert events.count("work.status") == 1
    assert events.count("project.verify") == 1
