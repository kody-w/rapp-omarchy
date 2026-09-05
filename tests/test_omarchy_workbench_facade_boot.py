import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


DIRECTORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIRECTORY))
SPEC = importlib.util.spec_from_file_location("workbench_facade_boot", DIRECTORY / "facade_boot.py")
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)


def test_preflight_binds_checkout_and_source_bytes(tmp_path, monkeypatch):
    source = tmp_path / "dependencies/RAPP/rapp_brainstem"
    source.mkdir(parents=True)
    (source / "rapp1_facade.py").write_bytes(b"fixture facade\n")
    (source / "run_rapp1_facade.py").write_bytes(b"fixture launcher\n")
    calls = []
    monkeypatch.setattr(BOOT, "_verify_git_checkout", lambda *args: calls.append(args))
    monkeypatch.setitem(BOOT.PINS, "foundation", {
        "commit": "a" * 40,
        "facade_sha256": hashlib.sha256(b"fixture facade\n").hexdigest(),
    })
    assert BOOT.validate_foundation(tmp_path) == source / "run_rapp1_facade.py"
    assert calls == [(source.parent, "a" * 40, "foundation facade")]
    (source / "rapp1_facade.py").write_bytes(b"changed\n")
    with pytest.raises(BOOT.FrameworkError, match="source hash"):
        BOOT.validate_foundation(tmp_path)


def test_preflight_never_launches_a_drifted_checkout(tmp_path, monkeypatch):
    def refuse(*args):
        raise BOOT.FrameworkError("checkout differs")

    monkeypatch.setattr(BOOT, "_verify_git_checkout", refuse)
    with pytest.raises(BOOT.FrameworkError, match="checkout differs"):
        BOOT.validate_foundation(tmp_path)


def test_service_starts_through_the_preflight():
    unit = (DIRECTORY / "omarchy-rapp1-facade.service").read_text()
    assert "/facade_boot.py" in unit
    assert "python rapp_brainstem/run_rapp1_facade.py" not in unit
