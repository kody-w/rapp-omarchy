import copy
import hashlib
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "protocol.py"
SPEC = importlib.util.spec_from_file_location("omarchy_rapp1_protocol", PROTOCOL_PATH)
protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(protocol)

AUTHORITY = Path(os.environ.get("RAPP1_REFERENCE_DIR", ROOT / "vendor" / "rapp-1"))
REGISTRY = Path(os.environ.get(
    "RAPP1_REGISTRY_PATH", AUTHORITY.parent / "rapp-map" / "ecosystem-spec.json",
))
ADAPTER = ROOT / "reviewer.py"


@pytest.fixture(autouse=True)
def pinned_reference_required(request):
    if request.node.name == "test_pins_are_the_researched_immutable_authority":
        return
    if not (AUTHORITY / "rapp.py").is_file() or not REGISTRY.is_file():
        pytest.skip("Set RAPP1_REFERENCE_DIR and RAPP1_REGISTRY_PATH to the documented pinned sources.")


def canonical_document(reference, path):
    R = reference["R"]
    raw = path.read_bytes()
    value = R._strict_json(raw)
    assert raw == R.canonical(value).encode("utf-8")
    return value


def prepared(tmp_path, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    state = tmp_path / "state"
    report = protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)
    return state, report


def synthetic_verified_registry(state):
    reference = protocol._load_reference(AUTHORITY)
    R, REG = reference["R"], reference["REG"]
    proposal = canonical_document(reference, state / "registry-proposal.json")
    document = copy.deepcopy(proposal)
    document["sig"] = "TEST-ONLY-SIGNATURE-BYPASS"
    registry = REG.Registry(document["entries"])
    raw = R.canonical(document).encode("utf-8")
    return {
        "path": REGISTRY,
        "document": document,
        "registry": registry,
        "raw": raw,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "canonical_sha256": hashlib.sha256(raw).hexdigest(),
        "registry_seq": document["registry_seq"],
    }


def install_synthetic_owner_verification(monkeypatch, registry_info):
    def verified(*args, **kwargs):
        persisted = kwargs.get("persisted_seq")
        if persisted is not None and registry_info["registry_seq"] < persisted:
            raise protocol.ProtocolError("synthetic fixture would roll back")
        return registry_info

    monkeypatch.setattr(protocol, "_load_verified_registry", verified)


def test_pins_are_the_researched_immutable_authority():
    assert protocol.PINS["authority"]["accepted_commit"] == (
        "9a129ab59376b55dfe9b2c4ee089f5f4b630617c"
    )
    assert protocol.PINS["authority"]["frame_hash"] == (
        "83ca275f35cca96e43d75c99d338326c1a39b2240eabf57eb7c29ac96cc90818"
    )
    assert protocol.PINS["reference"]["commit"] == (
        "eb50008011447f5e69372ac22a1755f0978d15ed"
    )
    assert protocol.PINS["registry"]["registry_seq"] == 2
    assert protocol.PINS["estate_owner"].startswith(
        "rappid:@kody-w/estate-owner:"
    )


def test_protocol_pin_check_avoids_reference_first_deprecated_entry_gap():
    reference = protocol._load_reference(AUTHORITY)
    info = protocol._load_verified_registry(
        reference["R"],
        reference["REG"],
        REGISTRY,
        persisted_seq=2,
        require_pinned_base=True,
    )
    assert info["registry"].protocols["rapp/1"]["deprecated"] is True
    assert protocol._protocol_pin_reasons(info["document"]) == []


def test_prepare_is_idempotent_and_current_signed_registry_stays_blocked(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    state = tmp_path / "state"
    registry_before = REGISTRY.read_bytes()

    first = protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)
    second = protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)

    assert first["identity"] == second["identity"]
    assert first["genesis"] == second["genesis"]
    assert first["registry"]["proposal_status"] == "draft"
    assert first["registry"]["proposal_seq"] == 3
    assert first["proposed_error_codes"] == [
        "malformed-request",
        "idempotency-in-progress",
        "session-in-progress",
        "inference-refused",
        "facade-storage-refused",
    ]
    assert first["activation"]["accepted"] is False
    assert any(
        "sequence has not advanced" in reason
        for reason in first["activation"]["reasons"]
    )
    assert any(
        "missing facade error codes" in reason
        for reason in first["activation"]["reasons"]
    )
    assert REGISTRY.read_bytes() == registry_before
    assert second["created"] == {
        "identity": False,
        "body_genesis": False,
        "critic_genesis": False,
        "registry_proposal": False,
        "approval_request": False,
    }

    reference = protocol._load_reference(AUTHORITY)
    R = reference["R"]
    body = canonical_document(reference, Path(first["paths"]["body_genesis"]))
    critic = canonical_document(reference, Path(first["paths"]["critic_genesis"]))
    assert set(body) == R.FRAME_KEYS
    assert set(critic) == R.FRAME_KEYS
    assert body["payload"]["adapter"]["sha256"] == hashlib.sha256(
        ADAPTER.read_bytes()
    ).hexdigest()
    assert body["payload"]["review_policy"] == protocol.REVIEW_POLICY
    assert critic["stream_id"] == first["critic_stream_id"]

    proposal = canonical_document(
        reference, Path(first["paths"]["registry_proposal"])
    )
    assert proposal["sig"] is None
    assert proposal["registry_seq"] == 3
    assert proposal["entries"][-7:] == [
        {"type": "error-code", "code": code}
        for code in protocol.PROPOSED_ERROR_CODES
    ] + [
        {
            "type": "genesis",
            "stream_id": body["stream_id"],
            "frame_hash": body["frame_hash"],
            "deprecated": False,
        },
        {
            "type": "genesis",
            "stream_id": critic["stream_id"],
            "frame_hash": critic["frame_hash"],
            "deprecated": False,
        },
    ]


def test_prepare_refuses_to_rebind_existing_genesis_to_changed_adapter(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    adapter = tmp_path / "reviewer.py"
    adapter.write_bytes(ADAPTER.read_bytes())
    state = tmp_path / "state"
    protocol.prepare(state, AUTHORITY, REGISTRY, adapter)
    adapter.write_bytes(adapter.read_bytes() + b"\n# changed\n")

    with pytest.raises(protocol.ProtocolError, match="candidate genesis"):
        protocol.prepare(state, AUTHORITY, REGISTRY, adapter)


def test_registry_high_water_refuses_current_registry_after_higher_observation(
    tmp_path, monkeypatch
):
    state, report = prepared(tmp_path, monkeypatch)
    reference = protocol._load_reference(AUTHORITY)
    R = reference["R"]
    high_water = {
        "schema": "omarchy-workbench-registry-high-water/1",
        "registry_seq": 3,
        "registry_sha256": "a" * 64,
    }
    Path(report["paths"]["registry_high_water"]).write_bytes(
        R.canonical(high_water).encode("utf-8")
    )
    status = protocol.activation_status(state, AUTHORITY, REGISTRY, ADAPTER)
    assert status["accepted"] is False
    assert any("rollback" in reason for reason in status["reasons"])


def test_synthetic_owner_gate_exercises_positive_activation_without_signing(
    tmp_path, monkeypatch
):
    state, _ = prepared(tmp_path, monkeypatch)
    registry_info = synthetic_verified_registry(state)
    install_synthetic_owner_verification(monkeypatch, registry_info)

    status = protocol.activation_status(state, AUTHORITY, REGISTRY, ADAPTER)

    assert status["accepted"] is True
    assert status["reasons"] == []
    assert status["claim"] == "locally-verified registered control profile"
    assert status["registry"]["registry_seq"] == 3
    assert status["genesis"]["body"]
    assert status["genesis"]["critic"]


def test_append_review_bootstraps_registered_genesis_and_enforces_policy(
    tmp_path, monkeypatch
):
    clock = {"value": "2026-09-05T14:00:00.000Z"}
    monkeypatch.setattr(protocol, "_utc_now", lambda: clock["value"])
    state = tmp_path / "state"
    prepared_report = protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)
    registry_info = synthetic_verified_registry(state)
    install_synthetic_owner_verification(monkeypatch, registry_info)

    first = protocol.append_review(
        state,
        AUTHORITY,
        REGISTRY,
        ADAPTER,
        {
            "changed_input_id": "change-001",
            "summary": "Queue one proposal; apply nothing.",
        },
    )
    assert first["accepted"] is True
    assert first["seq"] == 1
    assert first["kind"] == "memory.save"
    assert first["changes_applied"] is False
    assert first["frame"]["payload"]["simulation"] is True
    assert first["frame"]["payload"]["not_dhh"] is True
    assert first["frame"]["payload"]["no_endorsement"] is True
    assert first["frame"]["payload"]["review_only"] is True
    assert first["frame"]["payload"]["review_policy"] == protocol.REVIEW_POLICY

    reference = protocol._load_reference(AUTHORITY)
    R = reference["R"]
    journal = Path(first["journal_path"]).read_bytes()
    lines = journal.splitlines()
    assert len(lines) == 2
    genesis = R._strict_json(lines[0])
    review = R._strict_json(lines[1])
    assert lines[0] == R.canonical(genesis).encode("utf-8")
    assert lines[1] == R.canonical(review).encode("utf-8")
    assert review["prev"] == genesis["payload_hash"]
    assert review["prev_wave"] is None
    assert set(review) == R.FRAME_KEYS
    assert genesis["frame_hash"] == prepared_report["genesis"]["critic"]["frame_hash"]

    with pytest.raises(protocol.ProtocolError, match="already been reviewed"):
        protocol.append_review(
            state,
            AUTHORITY,
            REGISTRY,
            ADAPTER,
            {"changed_input_id": "change-001"},
        )

    clock["value"] = "2026-09-05T14:15:00.000Z"
    with pytest.raises(protocol.ProtocolError, match="interval has not elapsed"):
        protocol.append_review(
            state,
            AUTHORITY,
            REGISTRY,
            ADAPTER,
            {"changed_input_id": "change-002"},
        )

    clock["value"] = "2026-09-05T14:30:00.000Z"
    second = protocol.append_review(
        state,
        AUTHORITY,
        REGISTRY,
        ADAPTER,
        {
            "frame_kind": "memory.chat-turn",
            "changed_input_id": "change-002",
            "response": "Second read-only review.",
        },
    )
    assert second["seq"] == 2
    assert second["kind"] == "memory.chat-turn"
    assert second["frame"]["prev"] == first["payload_hash"]


def test_append_review_refuses_existing_journal_divergence(tmp_path, monkeypatch):
    clock = {"value": "2026-09-05T14:00:00.000Z"}
    monkeypatch.setattr(protocol, "_utc_now", lambda: clock["value"])
    state = tmp_path / "state"
    protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)
    registry_info = synthetic_verified_registry(state)
    install_synthetic_owner_verification(monkeypatch, registry_info)
    result = protocol.append_review(
        state,
        AUTHORITY,
        REGISTRY,
        ADAPTER,
        {"changed_input_id": "change-001"},
    )
    journal = Path(result["journal_path"])
    journal.write_bytes(journal.read_bytes()[:-1])
    clock["value"] = "2026-09-05T14:30:00.000Z"

    with pytest.raises(protocol.ProtocolError, match="LF-terminated"):
        protocol.append_review(
            state,
            AUTHORITY,
            REGISTRY,
            ADAPTER,
            {"changed_input_id": "change-002"},
        )


def test_append_review_stops_after_ten_changed_inputs(tmp_path, monkeypatch):
    current = {
        "value": datetime(2026, 9, 5, 14, 0, 0, tzinfo=timezone.utc)
    }

    def utc_now():
        return (
            current["value"]
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    monkeypatch.setattr(protocol, "_utc_now", utc_now)
    state = tmp_path / "state"
    protocol.prepare(state, AUTHORITY, REGISTRY, ADAPTER)
    registry_info = synthetic_verified_registry(state)
    install_synthetic_owner_verification(monkeypatch, registry_info)

    for index in range(10):
        result = protocol.append_review(
            state,
            AUTHORITY,
            REGISTRY,
            ADAPTER,
            {"changed_input_id": f"change-{index:03d}"},
        )
        assert result["review_count"] == index + 1
        current["value"] += timedelta(seconds=1800)

    with pytest.raises(protocol.ProtocolError, match="maximum changed-input"):
        protocol.append_review(
            state,
            AUTHORITY,
            REGISTRY,
            ADAPTER,
            {"changed_input_id": "change-010"},
        )


def test_pack_application_preserves_identity_and_legacy_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    state, prepared_report = prepared(tmp_path, monkeypatch)
    agent = tmp_path / "creature_agent.py"
    agent.write_bytes(b"class CreatureAgent:\n    pass\n")
    legacy = (
        b'{\n  "schema": "rapp-creature/egg/3",\n'
        b'  "payload": {"preserved": true, "energy": 1.25}\n}\n'
    )
    snapshot = b'{"schema":"rapp-creature/state/3","state":{}}'
    output = tmp_path / "creature.rapplication.egg"

    first = protocol.pack_application(
        state,
        AUTHORITY,
        "astra-creature",
        agent,
        {
            "legacy-creature-egg.json": legacy,
            "application-snapshot.json": snapshot,
        },
        output,
    )
    second = protocol.pack_application(
        state,
        AUTHORITY,
        "astra-creature",
        agent,
        {
            "legacy-creature-egg.json": legacy,
            "application-snapshot.json": snapshot,
        },
        output,
    )

    assert first["rappid"] == second["rappid"]
    assert first["rappid"] != prepared_report["identity"]
    assert first["egg_address"] == second["egg_address"]
    assert first["container_conformant"] is True
    assert first["unsigned"] is True
    assert first["embedded_code_activated"] is False
    assert first["legacy_creature_preserved"] is True
    assert first["files"] == [
        "agent.py",
        "rappid.json",
        "state/application-snapshot.json",
        "state/legacy-creature-egg.json",
    ]

    reference = protocol._load_reference(AUTHORITY)
    R = reference["R"]
    ok, step, why = R.verify_egg(output.read_bytes())
    assert ok, (step, why)
    manifest, files = R.read_egg(output.read_bytes())
    assert manifest["variant"] == "rapplication"
    assert manifest["sig"] is None
    assert files["state/legacy-creature-egg.json"] == legacy
    assert set(files) == {
        "agent.py",
        "rappid.json",
        "state/application-snapshot.json",
        "state/legacy-creature-egg.json",
    }


def test_pack_application_preserves_existing_output_directory_permissions(tmp_path):
    import stat

    output_directory = tmp_path / "shared-output"
    output_directory.mkdir(mode=0o755)
    before = stat.S_IMODE(output_directory.stat().st_mode)
    agent = tmp_path / "agent.py"
    agent.write_bytes(b"GENOME = ()\n")
    protocol.pack_application(
        tmp_path / "private-state", AUTHORITY, "permission-probe", agent, {},
        output_directory / "creature.egg",
    )
    assert stat.S_IMODE(output_directory.stat().st_mode) == before


@pytest.mark.parametrize(
    "bad_path",
    [
        "../escape.json",
        "/absolute.json",
        "state/already-prefixed.json",
        "a/../../escape.json",
        "a\\windows.json",
    ],
)
def test_pack_application_rejects_paths_outside_state(
    tmp_path, monkeypatch, bad_path
):
    monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    agent = tmp_path / "agent.py"
    agent.write_bytes(b"pass\n")
    with pytest.raises(protocol.ProtocolError):
        protocol.pack_application(
            tmp_path / "state",
            AUTHORITY,
            "path-test",
            agent,
            {bad_path: b"{}"},
            tmp_path / "bad.egg",
        )


def test_pack_application_will_not_overwrite_different_existing_output(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(protocol, "_utc_now", lambda: "2026-09-05T14:00:00.000Z")
    agent = tmp_path / "agent.py"
    agent.write_bytes(b"pass\n")
    output = tmp_path / "application.egg"
    protocol.pack_application(
        tmp_path / "state",
        AUTHORITY,
        "output-test",
        agent,
        {"one.json": b"{}"},
        output,
    )
    with pytest.raises(protocol.ProtocolError, match="will not be overwritten"):
        protocol.pack_application(
            tmp_path / "state",
            AUTHORITY,
            "output-test",
            agent,
            {"one.json": b'{"changed":true}'},
            output,
        )
