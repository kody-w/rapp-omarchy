#!/usr/bin/env python3
"""Prepare owned worktree lanes from a genuine Herdr-managed terminal.

This is an installation utility for Herdr's native API, not a RAPP wire or
kernel. It does not start coding models, read terminal scrollback, change
networking, or operate the user's default Herdr session.
"""

import argparse
import fcntl
import json
import os
import subprocess
import tempfile
from pathlib import Path


SESSION = "rapp1-workbench"
MAX_LANES = 16


def native(*arguments, expect_json=True):
    result = subprocess.run(
        ["herdr", "--session", SESSION, *arguments],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Herdr {' '.join(arguments[:2])} failed: {result.stderr.strip()[:4000]}")
    if not expect_json:
        return None
    try:
        document = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Herdr {' '.join(arguments[:2])} did not return the required JSON.") from error
    if not isinstance(document, dict) or not isinstance(document.get("result"), dict):
        raise RuntimeError("Herdr returned an unexpected native response.")
    return document["result"]


def git(path, *arguments):
    return subprocess.run(
        ["git", "-C", str(path), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    ).stdout.strip()


def save(path, value):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            os.chmod(temporary, 0o600)
            json.dump(value, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def caller(root):
    if os.environ.get("HERDR_ENV") != "1":
        raise RuntimeError("Run this utility inside the owned Herdr pane; do not manufacture HERDR_ENV.")
    values = {name: os.environ.get(name, "") for name in (
        "HERDR_WORKSPACE_ID", "HERDR_TAB_ID", "HERDR_PANE_ID"
    )}
    if not all(values.values()):
        raise RuntimeError("Herdr did not provide complete caller context.")
    if Path.cwd().resolve() != root:
        raise RuntimeError("Start the bootstrap in the dedicated workbench directory.")
    current = native("pane", "current", "--current").get("pane")
    if not isinstance(current, dict):
        raise RuntimeError("Herdr did not identify the calling pane.")
    if current.get("pane_id") != values["HERDR_PANE_ID"] or current.get("workspace_id") != values["HERDR_WORKSPACE_ID"]:
        raise RuntimeError("Herdr caller identity differs from the inherited context.")
    return {
        "workspace_id": current["workspace_id"],
        "tab_id": current["tab_id"],
        "pane_id": current["pane_id"],
    }


def workspaces():
    result = native("workspace", "list").get("workspaces")
    if not isinstance(result, list):
        raise RuntimeError("Herdr did not return a workspace list.")
    return result


def workspace_by_label(label):
    matches = [item for item in workspaces() if item.get("label") == label]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple workspaces use reserved label {label!r}; nothing was taken over.")
    return matches[0] if matches else None


def root_pane(workspace_id):
    panes = native("pane", "list", "--workspace", workspace_id).get("panes")
    if not isinstance(panes, list) or len(panes) != 1:
        raise RuntimeError("A newly opened worktree must have exactly one root pane.")
    pane = panes[0]
    if not isinstance(pane.get("pane_id"), str) or not isinstance(pane.get("tab_id"), str):
        raise RuntimeError("Herdr did not provide the new pane identifiers.")
    return pane


def validate_worktree(repository, destination, branch):
    if destination.is_symlink() or not destination.is_dir():
        raise RuntimeError(f"The recorded worktree is unavailable: {destination}.")
    if Path(git(destination, "rev-parse", "--show-toplevel")).resolve() != destination.resolve():
        raise RuntimeError("The lane is no longer a Git worktree root.")
    if git(destination, "symbolic-ref", "--short", "HEAD") != branch:
        raise RuntimeError("The recorded lane branch changed; no lane was taken over.")
    common = ("rev-parse", "--path-format=absolute", "--git-common-dir")
    if git(destination, *common) != git(repository, *common):
        raise RuntimeError("The lane belongs to another Git repository.")
    if git(destination, "remote", "get-url", "origin") != "https://github.com/omacom/omarchy.git":
        raise RuntimeError("The lane no longer uses the approved public repository.")


def validate_existing_lane(repository, destination, branch, entry, live):
    if not live or live["workspace_id"] != entry["workspace_id"]:
        raise RuntimeError("A recorded lane workspace was closed or changed.")
    if entry["path"] != str(destination) or entry["branch"] != branch:
        raise RuntimeError("The saved lane binding differs from its reserved location.")
    validate_worktree(repository, destination, branch)
    panes = native("pane", "list", "--workspace", entry["workspace_id"]).get("panes")
    if not isinstance(panes, list) or not any(
        pane.get("pane_id") == entry["pane_id"] and pane.get("tab_id") == entry["tab_id"]
        for pane in panes
    ):
        raise RuntimeError("The recorded lane pane/tab no longer exists; reopen it explicitly.")


def setup(root, lanes):
    if not 1 <= lanes <= MAX_LANES:
        raise ValueError(f"lanes must be between 1 and {MAX_LANES}")
    if not root.is_dir() or root.is_symlink() or root == Path.home().resolve():
        raise ValueError("Use an existing dedicated, non-symlink workbench directory.")
    context = caller(root)
    repository = root / "sources" / "omarchy"
    if not (repository / ".git").exists():
        raise RuntimeError("Prepare the separate Omarchy source checkout before opening worktrees.")
    if git(repository, "remote", "get-url", "origin") != "https://github.com/omacom/omarchy.git":
        raise RuntimeError("The source checkout is not the approved public Omarchy repository.")
    source_commit = git(repository, "rev-parse", "HEAD")
    state_path = root / "layout.json"
    lock_descriptor = os.open(root / ".bootstrap.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_descriptor, "a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state.get("session") != SESSION or state.get("control") != context:
                raise RuntimeError("Existing layout belongs to a different caller; refusing to change it.")
        else:
            state = {
                "format": "omarchy-workbench-layout-v1",
                "session": SESSION,
                "control": context,
                "source_commit": source_commit,
                "lanes": [],
                "tabs": {},
                "automatic_coding_agents": 0,
                "review_authority": "review-only",
            }
            save(state_path, state)
        native("workspace", "rename", context["workspace_id"], "Brainstem Workbench", expect_json=False)
        native("tab", "rename", context["tab_id"], "Control", expect_json=False)
        existing = {item["number"]: item for item in state["lanes"]}
        for number in range(1, lanes + 1):
            destination = root / "worktrees" / f"lane-{number:02d}"
            branch = f"workbench/lane-{number:02d}"
            label = f"{number:02d} - Omarchy"
            if number in existing:
                entry = existing[number]
                live = workspace_by_label(label)
                validate_existing_lane(repository, destination, branch, entry, live)
                continue
            if destination.exists():
                validate_worktree(repository, destination, branch)
                if workspace_by_label(label) is None:
                    native("worktree", "open", "--cwd", str(repository), "--path", str(destination), "--label", label, "--no-focus")
            else:
                native(
                    "worktree", "create", "--cwd", str(repository),
                    "--branch", branch, "--base", state["source_commit"],
                    "--path", str(destination), "--label", label, "--no-focus",
                )
            validate_worktree(repository, destination, branch)
            workspace = workspace_by_label(label)
            if workspace is None:
                raise RuntimeError("Herdr did not report the worktree it just opened.")
            pane = root_pane(workspace["workspace_id"])
            native(
                "pane", "report-metadata", pane["pane_id"],
                "--source", "omarchy-workbench", "--title", f"Lane {number:02d} - model not started",
                "--token", f"branch={branch}",
                expect_json=False,
            )
            state["lanes"].append({
                "number": number,
                "path": str(destination),
                "branch": branch,
                "workspace_id": workspace["workspace_id"],
                "tab_id": pane["tab_id"],
                "pane_id": pane["pane_id"],
            })
            save(state_path, state)
            print(f"Prepared isolated lane {number:02d}: {pane['pane_id']}", flush=True)
        for key, label in (("critic", "DHH-inspired reviews"), ("evidence", "Protocol evidence")):
            if key in state["tabs"]:
                continue
            result = native("tab", "create", "--workspace", context["workspace_id"], "--cwd", str(root), "--label", label, "--no-focus")
            pane = result.get("root_pane")
            if not isinstance(pane, dict) or not isinstance(pane.get("pane_id"), str):
                raise RuntimeError("Herdr did not return the created tab's root pane.")
            state["tabs"][key] = {"tab_id": pane["tab_id"], "pane_id": pane["pane_id"]}
            save(state_path, state)
        state["status"] = "ready"
        save(state_path, state)
        print(json.dumps({"status": "ready", "session": SESSION, "lanes": len(state["lanes"]), "automatic_coding_agents": 0}))
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--lanes", type=int, default=16)
    arguments = parser.parse_args()
    root = Path(arguments.root).expanduser().resolve()
    try:
        setup(root, arguments.lanes)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "error", "error": str(error)}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
