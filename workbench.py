"""Prepare and inspect the native workspace; never convert readiness into authority."""

import argparse
import json
from pathlib import Path

import frameworks
import protocol
from herdr_bootstrap import save


PROJECT = "omarchy-workbench-standardization"
SESSION = "rapp1-workbench"


def components(root, state):
    dependencies = root / "dependencies"
    sources = frameworks.NativeSources(
        projects=dependencies / "rapp-projects",
        workspace=dependencies / "rapp-workspace",
        sdk=dependencies / "rapp-sdk",
        herdr=dependencies / "rapp-herdr",
        rapp1=dependencies / "rapp-1",
        registry=dependencies / "rapp-map" / "ecosystem-spec.json",
    )
    native = frameworks.WorkbenchFrameworks(root / "workspace", sources)
    protocol_args = (
        state / "protocol", sources.rapp1, sources.registry, root / "reviewer.py",
    )
    return native, protocol_args


def prepare(root, state):
    native, protocol_args = components(root, state)
    prepared = protocol.prepare(*protocol_args)
    world = native.initialize_solo_world(
        slug="omarchy-workbench", name="Omarchy Brainstem Workbench",
        owner="kody-w", world_id="omarchy:workbench",
    )
    project = native.ensure_project(
        PROJECT, title="Omarchy Workbench Standardization",
        goal="Standardize a private, persistent, evidence-backed RAPP custom workspace.",
        owner="kody-w", origin="public DHH workflow and private Omarchy workbench",
    )
    actor = native.review_actor(
        session_id=SESSION, runtime="copilot-cli", model="gpt-5.6-sol-fast",
    )
    layout = native.bind_worktree_layout(
        PROJECT, actor, layout_path=root / "layout.json",
        repository="https://github.com/omacom/omarchy.git", lease_seconds=21600,
    )
    policy = native.arm_review_policy(
        PROJECT, actor, lease_seconds=21600, max_seconds_per_cycle=240,
    )
    result = {
        "prepared": True,
        "world_created": world["created"],
        "project_created": project["created"],
        "bound_worktree_lanes": len(layout["layout"]["lanes"]),
        "policy": policy["policy"],
        "protocol_prepared": prepared["prepared"],
        "activation": status(root, state),
    }
    save(state / "native-preparation.json", result)
    return result


def status(root, state):
    native, protocol_args = components(root, state)
    control = protocol.activation_status(*protocol_args)
    project = native.inspect(PROJECT)
    reasons = list(control["reasons"]) + [
        item["detail"] for item in project["activation"]["findings"]
        if item["severity"] == "blocker" and not item["ok"]
    ]
    reasons.append(
        "The pinned facade has no reviewed inference adapter. The tool-free CLI "
        "reviewer is a separate candidate, not an accepted facade adapter."
    )
    result = {
        "profile": "omarchy-workbench-candidate/1",
        "review_state": "held",
        "automatic_inference": False,
        "accepted_rapp1_operation": False,
        "control_authority_ready": control["accepted"],
        "native_project_ready": project["activation"]["ready"],
        "reasons": reasons,
        "native_due": bool(native.due_reviews(PROJECT)),
        "completed_native_review_cycles": project["project"]["completed_cycles"],
        "registry_sequence": control["registry"]["registry_seq"],
        "world_rappid": project["workspace"]["identity"]["rappid"],
        "project_rappid": project["project"]["stream_id"],
        "project_head": project["project"]["head"],
        "workspace_writer_enabled": False,
        "model_context_approved": project["project"]["model_context_approved"],
    }
    save(state / "readiness.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "status", "tick"))
    parser.add_argument("--root", type=Path, default=Path.home() / ".local/share/omarchy-rapp1-workbench")
    parser.add_argument("--state", type=Path, default=Path.home() / ".local/state/omarchy-rapp1-workbench")
    args = parser.parse_args()
    root, state = args.root.expanduser().resolve(), args.state.expanduser().resolve()
    try:
        if not root.is_dir() or root == Path.home():
            raise ValueError("Use the existing dedicated workbench root.")
        state.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = prepare(root, state) if args.operation == "prepare" else status(root, state)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "refused", "error": str(error)}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
