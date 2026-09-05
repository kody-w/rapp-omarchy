"""Verify the isolated foundation snapshot before starting its refusing facade."""

import hashlib
import os
import sys
from pathlib import Path

from frameworks import FrameworkError, _verify_git_checkout
from protocol import PINS


def validate_foundation(root):
    foundation = root / "dependencies" / "RAPP"
    pin = PINS["foundation"]
    _verify_git_checkout(foundation, pin["commit"], "foundation facade")
    facade = foundation / "rapp_brainstem" / "rapp1_facade.py"
    if facade.is_symlink() or not facade.is_file():
        raise FrameworkError("Pinned facade must be a regular source file.")
    if hashlib.sha256(facade.read_bytes()).hexdigest() != pin["facade_sha256"]:
        raise FrameworkError("Pinned facade source hash differs; inference remains disabled.")
    launcher = foundation / "rapp_brainstem" / "run_rapp1_facade.py"
    if launcher.is_symlink() or not launcher.is_file():
        raise FrameworkError("Pinned facade launcher is unavailable.")
    return launcher


def main():
    try:
        launcher = validate_foundation(Path(__file__).resolve().parent)
        os.execv(sys.executable, [sys.executable, str(launcher)])
    except (OSError, RuntimeError) as error:
        print(f"Workbench facade refused startup: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
