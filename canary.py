#!/usr/bin/env python3
"""Run one native, read-only Herdr attention canary, not a RAPP/1 activation."""

import argparse
import json
import subprocess
from pathlib import Path

from herdr_bootstrap import SESSION, caller, git, save


def invoke(*arguments, timeout=180):
    result = subprocess.run(
        ["herdr", "--session", SESSION, *arguments],
        capture_output=True, text=True, timeout=timeout, check=False,
    )
    return {
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def inspect_agent(record):
    record["agent"] = invoke("agent", "get", "rapp-canary")
    record["screen"] = invoke("agent", "read", "rapp-canary", "--source", "detection", "--lines", "80")
    if record["agent"]["exit_code"] != 0:
        raise RuntimeError("Herdr could not inspect the owned canary.")
    agent = json.loads(record["agent"]["stdout"])["result"]["agent"]
    if agent["pane_id"] != record["worktree"]["pane_id"] or agent["name"] != "rapp-canary":
        raise RuntimeError("The canary is no longer in its recorded worktree pane.")
    blocked = agent["agent_status"] == "blocked"
    prompted = record.get("prompt", {}).get("exit_code") == 0
    record["attention_state"] = agent["agent_status"]
    record["status"] = (
        "question-blocked" if blocked and prompted else
        "blocked-startup" if blocked and record["start"]["exit_code"] != 0 else
        "attention-not-proved"
    )


def run(root, inspect_only=False):
    context = caller(root)
    layout = json.loads((root / "layout.json").read_text())
    if context != layout["control"]:
        raise RuntimeError("Run the canary from this workbench's owned control pane.")
    lane = layout["lanes"][0]
    if inspect_only:
        record = json.loads((root / "canary.json").read_text())
        if record["worktree"] != lane:
            raise RuntimeError("Recorded canary differs from the current lane.")
        inspect_agent(record)
        record["worktree_unchanged"] = not git(Path(lane["path"]), "status", "--porcelain")
        save(root / "canary-inspection.json", record)
        print(json.dumps(record))
        return 0 if record["status"] == "question-blocked" and record["worktree_unchanged"] else 2
    before = git(Path(lane["path"]), "status", "--porcelain")
    if before:
        raise RuntimeError("The canary worktree is not clean; no agent was started.")
    name = "rapp-canary"
    record = {
        "scope": "native Herdr canary, not accepted RAPP/1 operation",
        "worktree": lane,
        "source_commit": layout["source_commit"],
        "requested_model": "gpt-5.6-sol-fast",
        "changes_allowed": False,
        "permission_approval_allowed": False,
    }
    existing = invoke("agent", "get", name)
    if existing["exit_code"] == 0:
        raise RuntimeError("A canary agent already exists; inspect it rather than starting another.")
    if existing["exit_code"] != 1:
        raise RuntimeError("Herdr could not safely establish whether the canary already exists.")
    error = json.loads(existing["stderr"]).get("error", {})
    if error.get("code") != "agent_not_found":
        raise RuntimeError(f"Canary discovery refused: {error.get('code', 'unrecognized native error')}")
    record["start"] = invoke(
        "agent", "start", name, "--kind", "copilot",
        "--pane", lane["pane_id"], "--timeout", "60000", "--",
        "--model", "gpt-5.6-sol-fast", "--context", "long_context", "--effort", "max",
        "--available-tools=ask_user", "--deny-tool", "shell", "--deny-tool", "write",
        "--deny-tool", "url", "--disable-builtin-mcps",
        "--no-custom-instructions", "--no-auto-update", "--no-remote", "--no-remote-export",
    )
    save(root / "canary.json", record)
    if record["start"]["exit_code"] == 0:
        prompt = (
            "This is a read-only Herdr attention canary, not a request for any system change. "
            "Use ask_user to ask one harmless question titled 'Canary attention check' with choices "
            "'Keep waiting' and 'Cancel canary'. Do not use other tools, edit any file, run commands, "
            "request broader permissions, contact a website, or claim RAPP/1 acceptance."
        )
        record["prompt"] = invoke(
            "agent", "prompt", name, prompt, "--wait", "--until", "blocked", "--timeout", "120000"
        )
    inspect_agent(record)
    record["worktree_unchanged"] = git(Path(lane["path"]), "status", "--porcelain") == before
    save(root / "canary.json", record)
    print(json.dumps(record))
    return 0 if record["status"] == "question-blocked" and record["worktree_unchanged"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    try:
        return run(Path(args.root).expanduser().resolve(), args.inspect)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "error", "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
