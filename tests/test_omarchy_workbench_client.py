import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("workbench_client", ROOT / "client.py")
client = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(client)


@pytest.fixture
def config(tmp_path):
    key = tmp_path / "key"
    hosts = tmp_path / "known-hosts"
    key.write_text("fixture, not a key")
    hosts.write_text("fixture")
    return {
        "host": "100.80.1.2",
        "user": "developer",
        "port": 2222,
        "identity_file": str(key),
        "known_hosts_file": str(hosts),
        "session": "rapp1-workbench",
        "workbench_root": "/home/developer/Workbench with spaces",
    }


def test_private_connection_preserves_host_verification(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    command = client.attach_command(client.target(path))
    assert "StrictHostKeyChecking=yes" in command
    assert "IdentitiesOnly=yes" in command
    assert "ForwardAgent=no" in command
    assert "-A" not in command
    assert command[-1] == "cd '/home/developer/Workbench with spaces' && exec herdr --session rapp1-workbench"


@pytest.mark.parametrize("change", [
    {"host": "203.0.113.10"},
    {"host": "-oProxyCommand=anything"},
    {"user": "root;touch bad"},
    {"session": "../default"},
    {"port": True},
    {"workbench_root": "/home/developer/../another"},
])
def test_invalid_or_public_targets_are_refused(tmp_path, config, change):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**config, **change}))
    with pytest.raises(ValueError):
        client.target(path)
