#!/usr/bin/env python3
"""Attach to an owned Omarchy Herdr workbench over pinned-key Tailnet SSH."""

import argparse
import ipaddress
import json
import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath


def target(path):
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"host", "user", "port", "identity_file", "known_hosts_file", "session", "workbench_root"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Connection configuration has an unexpected shape.")
    host = value["host"]
    if not isinstance(host, str) or not host or any(char.isspace() for char in host):
        raise ValueError("Invalid private host.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*\.ts\.net\.?", host):
            raise ValueError("Use a Tailnet address or full MagicDNS .ts.net name.") from None
    else:
        network = ipaddress.ip_network("100.64.0.0/10") if address.version == 4 else ipaddress.ip_network("fd7a:115c:a1e0::/48")
        if address not in network:
            raise ValueError("The configured address is not a private Tailnet address.")
    if not isinstance(value["user"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", value["user"]):
        raise ValueError("Invalid SSH user.")
    if type(value["port"]) is not int or not 1 <= value["port"] <= 65535:
        raise ValueError("Invalid SSH port.")
    if not isinstance(value["session"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", value["session"]):
        raise ValueError("Invalid owned Herdr session name.")
    root = value["workbench_root"]
    if not isinstance(root, str) or not PurePosixPath(root).is_absolute() or ".." in PurePosixPath(root).parts or "\n" in root:
        raise ValueError("Workbench directory must be an absolute remote path.")
    for field in ("identity_file", "known_hosts_file"):
        if not isinstance(value[field], str):
            raise ValueError(f"{field} must name an existing local file.")
        resolved = Path(value[field]).expanduser()
        if not resolved.is_file():
            raise ValueError(f"{field} is unavailable; no trust setting was bypassed.")
        value[field] = str(resolved)
    return value


def attach_command(config):
    remote = (
        f"cd {shlex.quote(config['workbench_root'])} && "
        f"exec herdr --session {shlex.quote(config['session'])}"
    )
    return [
        "ssh", "-tt",
        "-o", "IdentitiesOnly=yes",
        "-o", "ForwardAgent=no",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config['known_hosts_file']}",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-i", config["identity_file"],
        "-p", str(config["port"]),
        f"{config['user']}@{config['host']}",
        remote,
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/omarchy-rapp1-workbench/client.json")
    parser.add_argument("--show-command", action="store_true", help="Print the pinned connection command without connecting.")
    arguments = parser.parse_args()
    try:
        config = target(arguments.config)
        command = attach_command(config)
        if arguments.show_command:
            print(shlex.join(command))
            return 0
        if not sys.stdin.isatty():
            raise ValueError("Attach from a real terminal. Use --show-command for a noninteractive inspection.")
        print("Opening the private Omarchy workbench. Omarchy's current detach keys: Ctrl+Space, then d.", flush=True)
        os.execvp(command[0], command)
    except (OSError, ValueError) as error:
        print(f"Omarchy workbench: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
