"""Pinned RAPP/1 preparation, activation, review-journal, and packaging helpers.

This module is target-owned application code.  It imports the exact pinned
``rapp.py`` and ``rapp_registry.py`` supplied by the caller and never retypes
their canonicalization, frame hashing, signature verification, or egg encoder.

Preparation is deliberately not activation.  Only an owner-signed registry
that contains the exact proposed error-code and genesis additions can activate
the local registered control profile.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import importlib.util
import json
import os
import stat
import sys
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


PINS = {
    "authority": {
        "canonical_repository": "https://github.com/kody-w/rapp-1",
        "accepted_commit": "9a129ab59376b55dfe9b2c4ee089f5f4b630617c",
        "source_commit": "58058d08c9f0e340fae07c9865647f599c32634d",
        "frame_hash": "83ca275f35cca96e43d75c99d338326c1a39b2240eabf57eb7c29ac96cc90818",
        "payload_hash": "1ac47416e9caf174c4fdc00265ca187c244fb701ae2a7fb7211ba1385a951310",
        "normative_sha256": "348e7d5baa94aaf2ce4c5354f3cb261f389298a04af65e271a686d3b62f7c384",
        "normative_bytes": 79692,
        "revision": "rev-15",
        "seq": 15,
    },
    "reference": {
        "commit": "eb50008011447f5e69372ac22a1755f0978d15ed",
        "rapp_sha256": "1a04362b02f14c1e37b70c6b4f72d79e92df1cc9c2b5b394e8e1b141fc0b6050",
        "rapp_registry_sha256": "f055a4f933bae8a95e23e6fdf0106ef46860abc997b79f80fef961d494db772c",
        "orient_sha256": "0e0356ef28ff7dae8f28fd363b6234665202110f3328c1ef8962a358527ec954",
        "chain_sha256": "4d9b0e389395bfb2a61ff907e58efd12241c78e167ffd9be0f7f1452cd05b523",
        "index_sha256": "5f19ed2739c48e799ee142152f09da99488c06ee7a9100d6b67de7cf7618ca93",
        "selected_frame_object_sha256": "98d44039266310f8cea42f7ef874243587fbe681317cd9dd7b8f23b73630ebed",
        "bootstrap_index_sha256": "6237f88d91c5932f761159ed052b0c058f58e29a6ef9b166e2f927a5280c1881",
        "bootstrap_profile_sha256": "1666e44acf532f854d4bf74868c9af9f9b362055692189ac858a7c8b52dcd5bb",
        "bootstrap_verifier_sha256": "4a4c19912063d5ce15cec69b1aca0cebf5df122fb1c481f357f1cf21bc0a07ff",
    },
    "foundation": {
        "repository": "https://github.com/kody-w/RAPP",
        "commit": "4084c0e4adb05d0977799ac14fd93fe2424d495d",
        "facade_sha256": "34e08be4c47e9437729160335f9555c5ffb25395b0070c38eeba31e70686d4b0",
    },
    "registry": {
        "repository": "https://github.com/kody-w/rapp-map",
        "commit": "95e2f7290886e2de591fc78e4fb6e14b83435381",
        "sha256": "c19d40d5f287301b51bcfe9f16e60bcc6d7c6e008d2b8396144a02a485b16a33",
        "registry_seq": 2,
        "entries_count": 31,
        "entries_sha256": "35c2d4c460001dfcee50ba16834d864a33b566f42a47ed8b3125380cbc1b98f3",
    },
    "estate_owner": (
        "rappid:@kody-w/estate-owner:"
        "b5814e45e9988df835dfd58d152a6fb05b6510a087a35c24374a1c4ab833c122"
    ),
}

FACADE_ERROR_CODES = (
    "malformed-request",
    "unknown-session",
    "idempotency-in-progress",
    "session-in-progress",
    "inference-refused",
    "facade-storage-refused",
)
PROPOSED_ERROR_CODES = tuple(
    code for code in FACADE_ERROR_CODES if code != "unknown-session"
)

REVIEW_POLICY = {
    "simulation": True,
    "not_dhh": True,
    "no_endorsement": True,
    "review_only": True,
    "max_changed_input_reviews": 10,
    "interval_seconds": 1800,
    "tools_allowed": False,
    "automatic_merges": False,
    "automatic_deployments": False,
    "automatic_network_changes": False,
}

_MAX_REFERENCE_BYTES = 2 * 1024 * 1024
_MAX_ADAPTER_BYTES = 2 * 1024 * 1024
_MAX_AGENT_BYTES = 16 * 1024 * 1024
_MAX_STATE_FILE_BYTES = 64 * 1024 * 1024
_MAX_STATE_TOTAL_BYTES = 256 * 1024 * 1024
_MAX_JOURNAL_BYTES = 16 * 1024 * 1024

_IDENTITY_NAME = "workbench-rappid.json"
_BODY_GENESIS = Path("candidate") / "body-genesis.json"
_CRITIC_GENESIS = Path("candidate") / "critic-genesis.json"
_REGISTRY_PROPOSAL = "registry-proposal.json"
_APPROVAL_REQUEST = "approval-request.json"
_HIGH_WATER = "registry-high-water.json"
_CONTROL_LOCK = ".protocol-control.lock"
_JOURNAL = Path("reviews") / "critic.jsonl"


class ProtocolError(RuntimeError):
    """Preparation, activation, append, or packaging failed closed."""


def _path(value: Path | str, label: str) -> Path:
    try:
        result = Path(value).expanduser()
    except TypeError as exc:
        raise ProtocolError(f"{label} must be a Path or string") from exc
    return Path(os.path.abspath(os.fspath(result)))


def _ensure_directory(path: Path) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_dir():
            raise ProtocolError(f"directory is not a regular directory: {path}")
    else:
        path.mkdir(mode=0o700, parents=True)


def _read_regular(path: Path, *, maximum: int, label: str) -> bytes:
    if path.is_symlink():
        raise ProtocolError(f"{label} must not be a symlink: {path}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProtocolError(f"cannot open {label}: {path}: {exc}") from exc
    try:
        info_before = os.fstat(descriptor)
        if not stat.S_ISREG(info_before.st_mode):
            raise ProtocolError(f"{label} must be a regular file: {path}")
        if info_before.st_size > maximum:
            raise ProtocolError(f"{label} exceeds {maximum} bytes: {path}")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            raise ProtocolError(f"{label} exceeds {maximum} bytes: {path}")
        info_after = os.fstat(descriptor)
        if (
            info_before.st_dev,
            info_before.st_ino,
            info_before.st_size,
            info_before.st_mtime_ns,
        ) != (
            info_after.st_dev,
            info_after.st_ino,
            info_after.st_size,
            info_after.st_mtime_ns,
        ):
            raise ProtocolError(f"{label} changed while being read: {path}")
        return data
    finally:
        os.close(descriptor)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_replace(path: Path, data: bytes) -> None:
    _ensure_directory(path.parent)
    if path.is_symlink():
        raise ProtocolError(f"refusing to replace symlink: {path}")
    temporary = path.parent / (
        f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(temporary, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    path.chmod(0o600)
    _sync_directory(path.parent)


def _write_once_or_equal(path: Path, data: bytes, *, label: str) -> bool:
    if path.exists() or path.is_symlink():
        existing = _read_regular(path, maximum=max(len(data), 1) + 1, label=label)
        if existing != data:
            raise ProtocolError(f"existing {label} differs and will not be overwritten: {path}")
        return False
    _atomic_replace(path, data)
    return True


@contextmanager
def _file_lock(path: Path):
    _ensure_directory(path.parent)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _canonical_bytes(R, value: Any, *, label: str) -> bytes:
    try:
        return R.canonical(value).encode("utf-8")
    except Exception as exc:
        raise ProtocolError(f"{label} is outside the pinned RAPP canonical domain: {exc}") from exc


def _strict_value(R, data: bytes, *, label: str) -> Any:
    try:
        return R._strict_json(data)
    except Exception as exc:
        raise ProtocolError(f"{label} is not strict RAPP JSON: {exc}") from exc


def _canonical_document(R, path: Path, *, label: str) -> dict[str, Any]:
    data = _read_regular(path, maximum=_MAX_REFERENCE_BYTES, label=label)
    value = _strict_value(R, data, label=label)
    if type(value) is not dict:
        raise ProtocolError(f"{label} must be a JSON object")
    if data != _canonical_bytes(R, value, label=label):
        raise ProtocolError(f"{label} is not stored as exact canonical JSON")
    return value


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _utc_datetime(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"invalid fixed-form UTC timestamp: {value!r}") from exc


def _load_module(path: Path, name: str):
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ProtocolError(f"cannot load pinned module: {path}")
    module = importlib.util.module_from_spec(specification)
    prior = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        specification.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = prior
    return module


def _load_reference(reference_dir: Path | str) -> dict[str, Any]:
    root = _path(reference_dir, "reference_dir")
    if root.is_symlink() or not root.is_dir():
        raise ProtocolError(f"reference_dir must be a regular directory: {root}")

    required = {
        "rapp.py": PINS["reference"]["rapp_sha256"],
        "rapp_registry.py": PINS["reference"]["rapp_registry_sha256"],
        "anchor/orient.json": PINS["reference"]["orient_sha256"],
        "anchor/chain.jsonl": PINS["reference"]["chain_sha256"],
        "anchor/index.json": PINS["reference"]["index_sha256"],
        (
            "anchor/frames/"
            f"{PINS['authority']['frame_hash']}.json"
        ): PINS["reference"]["selected_frame_object_sha256"],
        "anchor/bootstrap/index.json": PINS["reference"]["bootstrap_index_sha256"],
        (
            "anchor/bootstrap/sha256-"
            f"{PINS['reference']['bootstrap_profile_sha256']}.json"
        ): PINS["reference"]["bootstrap_profile_sha256"],
        "anchor/bootstrap_verify.py": PINS["reference"]["bootstrap_verifier_sha256"],
    }
    raw: dict[str, bytes] = {}
    for relative, expected in required.items():
        path = root / relative
        data = _read_regular(path, maximum=_MAX_REFERENCE_BYTES, label=relative)
        actual = _sha256(data)
        if actual != expected:
            raise ProtocolError(
                f"pinned reference mismatch for {relative}: expected {expected}, got {actual}"
            )
        raw[relative] = data

    R = _load_module(
        root / "rapp.py",
        f"_omarchy_pinned_rapp_{PINS['reference']['commit'][:12]}",
    )
    previous = sys.modules.get("rapp")
    sys.modules["rapp"] = R
    try:
        REG = _load_module(
            root / "rapp_registry.py",
            f"_omarchy_pinned_registry_{PINS['reference']['commit'][:12]}",
        )
    finally:
        if previous is None:
            sys.modules.pop("rapp", None)
        else:
            sys.modules["rapp"] = previous

    if R.SPEC != "rapp/1" or len(R.FRAME_KEYS) != 11:
        raise ProtocolError("pinned reference has an unexpected protocol or frame key set")
    if set(R.EGG_VARIANTS) != {
        "organism",
        "rapplication",
        "session",
        "invite",
        "neighborhood",
        "estate",
        "sealed",
    }:
        raise ProtocolError("pinned reference does not expose the seven ratified egg variants")

    orient = _strict_value(R, raw["anchor/orient.json"], label="anchor/orient.json")
    if type(orient) is not dict:
        raise ProtocolError("anchor/orient.json must be an object")
    authority = PINS["authority"]
    expected_orient = {
        "seq": authority["seq"],
        "frame_hash": authority["frame_hash"],
        "payload_hash": authority["payload_hash"],
        "normative_sha256": authority["normative_sha256"],
        "normative_bytes": authority["normative_bytes"],
        "revision": authority["revision"],
    }
    actual_orient = {
        "seq": orient.get("head", {}).get("seq"),
        "frame_hash": orient.get("head", {}).get("frame_hash"),
        "payload_hash": orient.get("head", {}).get("payload_hash"),
        "normative_sha256": orient.get("spec", {}).get("normative_sha256"),
        "normative_bytes": orient.get("spec", {}).get("normative_bytes"),
        "revision": orient.get("spec", {}).get("revision"),
    }
    if actual_orient != expected_orient:
        raise ProtocolError(
            f"anchor/orient.json does not identify the pinned authority: {actual_orient!r}"
        )
    if (
        orient.get("bootstrap", {}).get("profile_sha256")
        != PINS["reference"]["bootstrap_profile_sha256"]
        or orient.get("bootstrap", {}).get("verifier_sha256")
        != PINS["reference"]["bootstrap_verifier_sha256"]
    ):
        raise ProtocolError("anchor bootstrap pins do not match PINS")
    bootstrap_index = _strict_value(
        R,
        raw["anchor/bootstrap/index.json"],
        label="anchor/bootstrap/index.json",
    )
    expected_profile_path = (
        "anchor/bootstrap/sha256-"
        f"{PINS['reference']['bootstrap_profile_sha256']}.json"
    )
    if (
        type(bootstrap_index) is not dict
        or bootstrap_index.get("profile_path") != expected_profile_path
        or bootstrap_index.get("profile_sha256")
        != PINS["reference"]["bootstrap_profile_sha256"]
        or bootstrap_index.get("verifier_path") != "anchor/bootstrap_verify.py"
        or bootstrap_index.get("verifier_sha256")
        != PINS["reference"]["bootstrap_verifier_sha256"]
    ):
        raise ProtocolError("anchor bootstrap index does not match PINS")

    spec_octets = _read_regular(
        root / "SPEC.md",
        maximum=_MAX_REFERENCE_BYTES,
        label="SPEC.md",
    )
    if (
        len(spec_octets) != authority["normative_bytes"]
        or _sha256(spec_octets) != authority["normative_sha256"]
    ):
        raise ProtocolError("SPEC.md does not match the selected normative bytes")

    chain_octets = raw["anchor/chain.jsonl"]
    if not chain_octets.endswith(b"\n") or b"\r" in chain_octets:
        raise ProtocolError("anchor chain must be LF-terminated JSONL")
    head = None
    frames: list[dict[str, Any]] = []
    for index, line in enumerate(chain_octets.splitlines(), 1):
        frame = _strict_value(R, line, label=f"anchor frame {index}")
        if type(frame) is not dict:
            raise ProtocolError(f"anchor frame {index} is not an object")
        ok, step, why = R.verify_frame(
            frame,
            head=head,
            stream_id_of_record=orient["stream_id"],
        )
        if not ok:
            raise ProtocolError(
                f"anchor frame {index} failed pinned verification at {step}: {why}"
            )
        frames.append(frame)
        head = frame
    if not frames or {
        "seq": head["seq"],
        "frame_hash": head["frame_hash"],
        "payload_hash": head["payload_hash"],
    } != {
        "seq": authority["seq"],
        "frame_hash": authority["frame_hash"],
        "payload_hash": authority["payload_hash"],
    }:
        raise ProtocolError("anchor chain head does not match PINS")

    frame_object = raw[
        f"anchor/frames/{authority['frame_hash']}.json"
    ]
    selected = _strict_value(R, frame_object, label="selected frame object")
    if selected != head:
        raise ProtocolError("selected frame object differs from the verified chain head")

    return {
        "root": root,
        "R": R,
        "REG": REG,
        "report": {
            "reference_commit": PINS["reference"]["commit"],
            "authority_commit": authority["accepted_commit"],
            "authority_frame_hash": authority["frame_hash"],
            "normative_sha256": authority["normative_sha256"],
            "chain_frames": len(frames),
        },
    }


def _load_registry_document(R, path: Path) -> tuple[dict[str, Any], bytes, str]:
    data = _read_regular(path, maximum=_MAX_REFERENCE_BYTES, label="registry")
    document = _strict_value(R, data, label="registry")
    if type(document) is not dict:
        raise ProtocolError("registry must be a JSON object")
    return document, data, _sha256(data)


def _load_verified_registry(
    R,
    REG,
    registry_path: Path | str,
    *,
    persisted_seq: int | None,
    require_pinned_base: bool = False,
) -> dict[str, Any]:
    path = _path(registry_path, "registry_path")
    document, raw, digest = _load_registry_document(R, path)
    if require_pinned_base and digest != PINS["registry"]["sha256"]:
        raise ProtocolError(
            "prepare requires the immutable pinned base registry "
            f"{PINS['registry']['commit']}"
        )
    status_value, registry, reason = REG.load_document(
        document,
        entries_member="entries",
        trust_anchor=PINS["estate_owner"],
        persisted_seq=persisted_seq,
    )
    if status_value != "verified" or registry is None:
        raise ProtocolError(f"signed registry verification failed: {reason}")
    canonical_digest = _sha256(
        _canonical_bytes(R, document, label="signed registry")
    )
    return {
        "path": path,
        "document": document,
        "registry": registry,
        "raw": raw,
        "sha256": digest,
        "canonical_sha256": canonical_digest,
        "registry_seq": document["registry_seq"],
    }


def _entries_digest(R, entries: Any) -> str:
    return _sha256(_canonical_bytes(R, entries, label="registry entries"))


def _base_prefix_ok(R, entries: Any) -> bool:
    count = PINS["registry"]["entries_count"]
    return (
        type(entries) is list
        and len(entries) >= count
        and _entries_digest(R, entries[:count])
        == PINS["registry"]["entries_sha256"]
    )


def _protocol_pin_reasons(document: dict[str, Any]) -> list[str]:
    expected = {
        "type": "protocol",
        "name": "rapp/1",
        "spec_repo": PINS["authority"]["canonical_repository"],
        "spec_path": "SPEC.md",
        "spec_hash": PINS["authority"]["normative_sha256"],
        "deprecated": False,
    }
    current = [
        entry
        for entry in document.get("entries", [])
        if type(entry) is dict
        and entry.get("type") == "protocol"
        and entry.get("name") == "rapp/1"
        and entry.get("deprecated") is False
    ]
    if current != [expected]:
        return ["signed registry does not contain the one exact current rapp/1 protocol pin"]
    return []


def _identity_path(state: Path) -> Path:
    return state / _IDENTITY_NAME


def _load_identity(R, path: Path, *, owner: str, slug: str) -> str:
    document = _canonical_document(R, path, label="identity")
    if set(document) != {"schema", "rappid"} or document["schema"] != "rapp/1":
        raise ProtocolError(f"identity has an unexpected shape: {path}")
    rappid = document.get("rappid")
    if not R.rappid_valid(rappid):
        raise ProtocolError(f"identity is not a valid RAPPID: {path}")
    parts = R.rappid_parts(rappid)
    if parts["owner"] != owner or parts["slug"] != slug:
        raise ProtocolError(
            f"identity owner/slug mismatch: expected @{owner}/{slug}, got {rappid}"
        )
    return rappid


def _load_or_mint_identity(R, path: Path, *, owner: str, slug: str) -> tuple[str, bool]:
    if path.exists() or path.is_symlink():
        return _load_identity(R, path, owner=owner, slug=slug), False
    rappid = R.mint_rappid(owner, slug)
    document = {"schema": "rapp/1", "rappid": rappid}
    _write_once_or_equal(
        path,
        _canonical_bytes(R, document, label="identity"),
        label="identity",
    )
    return rappid, True


def _assert_distinct_stored_identities(R, state: Path) -> None:
    identities: dict[str, str] = {}
    candidates: list[Path] = []
    runtime_path = _identity_path(state)
    if runtime_path.exists() or runtime_path.is_symlink():
        candidates.append(runtime_path)
    applications = state / "applications"
    if applications.exists() or applications.is_symlink():
        if applications.is_symlink() or not applications.is_dir():
            raise ProtocolError("applications identity directory must be a regular directory")
        candidates.extend(sorted(applications.glob("*/rappid.json")))
    for candidate in candidates:
        if candidate.is_symlink():
            raise ProtocolError(f"identity path must not be a symlink: {candidate}")
        document = _canonical_document(R, candidate, label="stored identity")
        candidate_rappid = document.get("rappid")
        if not R.rappid_valid(candidate_rappid):
            raise ProtocolError(f"stored identity is invalid: {candidate}")
        prior = identities.get(candidate_rappid)
        if prior is not None and prior != str(candidate):
            raise ProtocolError(
                f"distinct runtime/application identities collide: {prior} and {candidate}"
            )
        identities[candidate_rappid] = str(candidate)


def _adapter_report(adapter_path: Path | str) -> dict[str, Any]:
    path = _path(adapter_path, "adapter_path")
    data = _read_regular(path, maximum=_MAX_ADAPTER_BYTES, label="adapter source")
    return {
        "path": path,
        "sha256": _sha256(data),
        "bytes": len(data),
    }


def _body_payload(rappid: str, adapter: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "profile": "omarchy-workbench-registered-control/1",
        "workbench_rappid": rappid,
        "authority": {
            "accepted_commit": PINS["authority"]["accepted_commit"],
            "frame_hash": PINS["authority"]["frame_hash"],
            "reference_commit": PINS["reference"]["commit"],
        },
        "adapter": {
            "sha256": adapter["sha256"],
            "bytes": adapter["bytes"],
        },
        "review_policy": copy.deepcopy(REVIEW_POLICY),
        "activation": "owner-registration-required",
    }


def _critic_payload(rappid: str, body_frame_hash: str) -> dict[str, Any]:
    return {
        "profile": "omarchy-workbench-critic-stream/1",
        "workbench_rappid": rappid,
        "body_genesis_frame_hash": body_frame_hash,
        "simulation": True,
        "not_dhh": True,
        "no_endorsement": True,
        "review_only": True,
        "review_policy": copy.deepcopy(REVIEW_POLICY),
        "activation": "owner-registration-required",
    }


def _validate_genesis(
    R,
    registry,
    frame: dict[str, Any],
    *,
    kind: str,
    stream_id: str,
    payload: dict[str, Any],
) -> None:
    if (
        frame.get("kind") != kind
        or frame.get("stream_id") != stream_id
        or frame.get("seq") != 0
        or frame.get("prev") is not None
        or frame.get("prev_wave") is not None
        or frame.get("sig") is not None
        or frame.get("payload") != payload
    ):
        raise ProtocolError(f"candidate genesis does not match the expected {kind} profile")
    ok, step, why = R.verify_frame(
        frame,
        head=None,
        stream_id_of_record=stream_id,
    )
    if not ok:
        raise ProtocolError(f"candidate genesis failed at {step}: {why}")
    bound, reason = registry.check_frame_binding(frame)
    if not bound:
        raise ProtocolError(f"candidate genesis registry binding failed: {reason}")


def _load_or_create_genesis(
    R,
    registry,
    path: Path,
    *,
    kind: str,
    stream_id: str,
    payload: dict[str, Any],
    utc: str,
) -> tuple[dict[str, Any], bool]:
    if path.exists() or path.is_symlink():
        frame = _canonical_document(R, path, label=f"{kind} candidate genesis")
        _validate_genesis(
            R,
            registry,
            frame,
            kind=kind,
            stream_id=stream_id,
            payload=payload,
        )
        return frame, False
    frame = R.build_frame(
        kind,
        stream_id,
        0,
        utc,
        payload,
        prev=None,
        prev_wave=None,
        sig=None,
    )
    _validate_genesis(
        R,
        registry,
        frame,
        kind=kind,
        stream_id=stream_id,
        payload=payload,
    )
    _write_once_or_equal(
        path,
        _canonical_bytes(R, frame, label=f"{kind} candidate genesis"),
        label=f"{kind} candidate genesis",
    )
    return frame, True


def _expected_additions(
    body: dict[str, Any],
    critic: dict[str, Any],
) -> list[dict[str, Any]]:
    additions = [
        {"type": "error-code", "code": code}
        for code in PROPOSED_ERROR_CODES
    ]
    additions.extend(
        [
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
    )
    return additions


def _proposal_document(
    base: dict[str, Any],
    additions: list[dict[str, Any]],
) -> dict[str, Any]:
    proposal = copy.deepcopy(base)
    proposal["registry_seq"] = PINS["registry"]["registry_seq"] + 1
    proposal["entries"] = copy.deepcopy(base["entries"]) + copy.deepcopy(additions)
    proposal["sig"] = None
    return proposal


def _approval_document(
    *,
    body: dict[str, Any],
    critic: dict[str, Any],
    additions: list[dict[str, Any]],
    proposal_sha256: str,
    adapter: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": "omarchy-workbench-approval-request/1",
        "status": "owner-action-required",
        "prepared_utc": body["utc"],
        "based_on": {
            "registry_repository": PINS["registry"]["repository"],
            "registry_commit": PINS["registry"]["commit"],
            "registry_sha256": PINS["registry"]["sha256"],
            "registry_seq": PINS["registry"]["registry_seq"],
            "authority_commit": PINS["authority"]["accepted_commit"],
            "authority_frame_hash": PINS["authority"]["frame_hash"],
        },
        "proposed_registry_seq": PINS["registry"]["registry_seq"] + 1,
        "proposed_additions": copy.deepcopy(additions),
        "candidate_genesis": {
            "body": body["frame_hash"],
            "critic": critic["frame_hash"],
        },
        "adapter": {
            "sha256": adapter["sha256"],
            "bytes": adapter["bytes"],
        },
        "review_policy": copy.deepcopy(REVIEW_POLICY),
        "registry_proposal_sha256": proposal_sha256,
        "blocked_reasons": [
            "estate-owner signature and publication are unavailable",
            "five facade error codes are not registered by the signed base registry",
            "workbench body genesis is not registered by the signed base registry",
            "critic memory genesis is not registered by the signed base registry",
            "adapter approval is not owner-authenticated",
        ],
        "authority_claim": "preparation-only; not a signature, registration, or activation",
    }


def _high_water_path(state: Path) -> Path:
    return state / _HIGH_WATER


def _load_high_water(R, state: Path) -> dict[str, Any] | None:
    path = _high_water_path(state)
    if not path.exists() and not path.is_symlink():
        return None
    value = _canonical_document(R, path, label="registry high-water record")
    if set(value) != {"schema", "registry_seq", "registry_sha256"}:
        raise ProtocolError("registry high-water record has an unexpected shape")
    if (
        value["schema"] != "omarchy-workbench-registry-high-water/1"
        or type(value["registry_seq"]) is not int
        or isinstance(value["registry_seq"], bool)
        or value["registry_seq"] < PINS["registry"]["registry_seq"]
        or type(value["registry_sha256"]) is not str
        or len(value["registry_sha256"]) != 64
    ):
        raise ProtocolError("registry high-water record is invalid")
    return value


def _record_high_water(
    R,
    state: Path,
    *,
    registry_seq: int,
    registry_sha256: str,
) -> dict[str, Any]:
    current = _load_high_water(R, state)
    if current is not None:
        if registry_seq < current["registry_seq"]:
            raise ProtocolError(
                f"registry rollback: {registry_seq} < persisted {current['registry_seq']}"
            )
        if (
            registry_seq == current["registry_seq"]
            and registry_sha256 != current["registry_sha256"]
        ):
            raise ProtocolError(
                "different signed registry bytes were presented at the persisted sequence"
            )
        if registry_seq == current["registry_seq"]:
            return current
    updated = {
        "schema": "omarchy-workbench-registry-high-water/1",
        "registry_seq": registry_seq,
        "registry_sha256": registry_sha256,
    }
    _atomic_replace(
        _high_water_path(state),
        _canonical_bytes(R, updated, label="registry high-water record"),
    )
    return updated


def _validate_base_registry(R, info: dict[str, Any]) -> None:
    document = info["document"]
    registry = info["registry"]
    if info["registry_seq"] != PINS["registry"]["registry_seq"]:
        raise ProtocolError("pinned base registry has an unexpected sequence")
    if not _base_prefix_ok(R, document.get("entries")):
        raise ProtocolError("pinned base registry entry prefix does not match PINS")
    reasons = _protocol_pin_reasons(document)
    if reasons:
        raise ProtocolError(reasons[0])
    if not set(FACADE_ERROR_CODES).intersection(registry.error_codes) == {
        "unknown-session"
    }:
        raise ProtocolError("pinned base registry error-code set is unexpected")
    for kind in ("body.pulse", "memory.save", "memory.chat-turn"):
        if registry.family(kind) is None:
            raise ProtocolError(f"pinned base registry does not register {kind}")
    if registry.egg_variants.get("rapplication", {}).get("deprecated") is not False:
        raise ProtocolError("pinned base registry does not register rapplication")


def _state_paths(state: Path) -> dict[str, Path]:
    return {
        "identity": _identity_path(state),
        "body_genesis": state / _BODY_GENESIS,
        "critic_genesis": state / _CRITIC_GENESIS,
        "registry_proposal": state / _REGISTRY_PROPOSAL,
        "approval_request": state / _APPROVAL_REQUEST,
        "registry_high_water": state / _HIGH_WATER,
        "review_journal": state / _JOURNAL,
    }


def prepare(
    state_dir: Path | str,
    reference_dir: Path | str,
    registry_path: Path | str,
    adapter_path: Path | str,
) -> dict[str, Any]:
    """Prepare immutable candidate identity, genesis, registry, and approval data.

    The signed base registry is never modified.  Repeated calls reuse the same
    keyless runtime identity and exact candidate genesis frames.
    """

    state = _path(state_dir, "state_dir")
    _ensure_directory(state)
    reference = _load_reference(reference_dir)
    R, REG = reference["R"], reference["REG"]
    adapter = _adapter_report(adapter_path)
    paths = _state_paths(state)

    with _file_lock(state / _CONTROL_LOCK):
        high_water = _load_high_water(R, state)
        persisted = (
            high_water["registry_seq"]
            if high_water is not None
            else PINS["registry"]["registry_seq"]
        )
        base = _load_verified_registry(
            R,
            REG,
            registry_path,
            persisted_seq=persisted,
            require_pinned_base=True,
        )
        _validate_base_registry(R, base)
        _record_high_water(
            R,
            state,
            registry_seq=base["registry_seq"],
            registry_sha256=base["canonical_sha256"],
        )

        rappid, identity_created = _load_or_mint_identity(
            R,
            paths["identity"],
            owner="kody-w",
            slug="omarchy-workbench",
        )
        _assert_distinct_stored_identities(R, state)
        prepared_utc = _utc_now()
        body_payload = _body_payload(rappid, adapter)
        body, body_created = _load_or_create_genesis(
            R,
            base["registry"],
            paths["body_genesis"],
            kind="body.pulse",
            stream_id=rappid,
            payload=body_payload,
            utc=prepared_utc,
        )
        critic_stream = f"{rappid}:critic"
        critic_payload = _critic_payload(rappid, body["frame_hash"])
        critic, critic_created = _load_or_create_genesis(
            R,
            base["registry"],
            paths["critic_genesis"],
            kind="memory.save",
            stream_id=critic_stream,
            payload=critic_payload,
            utc=body["utc"],
        )

        additions = _expected_additions(body, critic)
        proposal = _proposal_document(base["document"], additions)
        draft_status, draft_registry, draft_reason = REG.load_document(
            proposal,
            entries_member="entries",
            trust_anchor=PINS["estate_owner"],
            allow_unsigned=True,
            persisted_seq=base["registry_seq"],
        )
        if draft_status != "draft" or draft_registry is None:
            raise ProtocolError(
                f"unsigned registry proposal did not validate as a draft: {draft_reason}"
            )
        proposal_bytes = _canonical_bytes(
            R,
            proposal,
            label="unsigned registry proposal",
        )
        proposal_created = _write_once_or_equal(
            paths["registry_proposal"],
            proposal_bytes,
            label="unsigned registry proposal",
        )

        approval = _approval_document(
            body=body,
            critic=critic,
            additions=additions,
            proposal_sha256=_sha256(proposal_bytes),
            adapter=adapter,
        )
        approval_created = _write_once_or_equal(
            paths["approval_request"],
            _canonical_bytes(R, approval, label="approval request"),
            label="approval request",
        )

    activation = activation_status(
        state,
        reference_dir,
        registry_path,
        adapter_path,
    )
    return {
        "prepared": True,
        "identity": rappid,
        "critic_stream_id": critic["stream_id"],
        "paths": {name: str(path) for name, path in paths.items()},
        "created": {
            "identity": identity_created,
            "body_genesis": body_created,
            "critic_genesis": critic_created,
            "registry_proposal": proposal_created,
            "approval_request": approval_created,
        },
        "facade_error_codes": list(FACADE_ERROR_CODES),
        "proposed_error_codes": list(PROPOSED_ERROR_CODES),
        "genesis": {
            "body": {
                "stream_id": body["stream_id"],
                "frame_hash": body["frame_hash"],
                "payload_hash": body["payload_hash"],
            },
            "critic": {
                "stream_id": critic["stream_id"],
                "frame_hash": critic["frame_hash"],
                "payload_hash": critic["payload_hash"],
            },
        },
        "registry": {
            "base_seq": base["registry_seq"],
            "base_sha256": base["sha256"],
            "proposal_seq": proposal["registry_seq"],
            "proposal_status": draft_status,
            "proposal_sha256": _sha256(proposal_bytes),
        },
        "adapter": {
            "sha256": adapter["sha256"],
            "bytes": adapter["bytes"],
        },
        "review_policy": copy.deepcopy(REVIEW_POLICY),
        "activation": activation,
        "pins": copy.deepcopy(PINS),
    }


def _unique_reasons(reasons: list[str]) -> list[str]:
    result: list[str] = []
    for reason in reasons:
        if reason not in result:
            result.append(reason)
    return result


def activation_status(
    state_dir: Path | str,
    reference_dir: Path | str,
    registry_path: Path | str,
    adapter_path: Path | str,
) -> dict[str, Any]:
    """Return the locally verified registered-control-profile activation gate."""

    state = _path(state_dir, "state_dir")
    _ensure_directory(state)
    reference = _load_reference(reference_dir)
    R, REG = reference["R"], reference["REG"]
    paths = _state_paths(state)
    reasons: list[str] = []
    adapter: dict[str, Any] | None = None
    registry_info: dict[str, Any] | None = None
    body: dict[str, Any] | None = None
    critic: dict[str, Any] | None = None
    rappid: str | None = None
    high_water: dict[str, Any] | None = None

    try:
        adapter = _adapter_report(adapter_path)
    except ProtocolError as exc:
        reasons.append(str(exc))

    with _file_lock(state / _CONTROL_LOCK):
        try:
            high_water = _load_high_water(R, state)
        except ProtocolError as exc:
            reasons.append(str(exc))
        persisted = max(
            PINS["registry"]["registry_seq"],
            high_water["registry_seq"] if high_water is not None else 0,
        )
        try:
            registry_info = _load_verified_registry(
                R,
                REG,
                registry_path,
                persisted_seq=persisted,
            )
            high_water = _record_high_water(
                R,
                state,
                registry_seq=registry_info["registry_seq"],
                registry_sha256=registry_info["canonical_sha256"],
            )
        except ProtocolError as exc:
            reasons.append(str(exc))
            registry_info = None

        try:
            rappid = _load_identity(
                R,
                paths["identity"],
                owner="kody-w",
                slug="omarchy-workbench",
            )
        except ProtocolError as exc:
            reasons.append(str(exc))

        if registry_info is not None:
            document = registry_info["document"]
            registry = registry_info["registry"]
            entries = document.get("entries")
            if not _base_prefix_ok(R, entries):
                reasons.append("signed registry does not preserve the immutable base entry prefix")
            reasons.extend(_protocol_pin_reasons(document))
            if registry_info["registry_seq"] <= PINS["registry"]["registry_seq"]:
                reasons.append(
                    "signed registry sequence has not advanced beyond the pinned preparation base"
                )
            missing_codes = [
                code for code in FACADE_ERROR_CODES if code not in registry.error_codes
            ]
            if missing_codes:
                reasons.append(
                    "signed registry is missing facade error codes: "
                    + ", ".join(missing_codes)
                )

            if rappid is not None and adapter is not None:
                try:
                    body = _canonical_document(
                        R,
                        paths["body_genesis"],
                        label="body candidate genesis",
                    )
                    _validate_genesis(
                        R,
                        registry,
                        body,
                        kind="body.pulse",
                        stream_id=rappid,
                        payload=_body_payload(rappid, adapter),
                    )
                except ProtocolError as exc:
                    reasons.append(str(exc))
                    body = None
                if body is not None:
                    try:
                        critic = _canonical_document(
                            R,
                            paths["critic_genesis"],
                            label="critic candidate genesis",
                        )
                        _validate_genesis(
                            R,
                            registry,
                            critic,
                            kind="memory.save",
                            stream_id=f"{rappid}:critic",
                            payload=_critic_payload(rappid, body["frame_hash"]),
                        )
                    except ProtocolError as exc:
                        reasons.append(str(exc))
                        critic = None

            if body is not None and critic is not None:
                additions = _expected_additions(body, critic)
                base_count = PINS["registry"]["entries_count"]
                if (
                    type(entries) is not list
                    or entries[base_count : base_count + len(additions)] != additions
                ):
                    reasons.append(
                        "signed registry does not contain the exact prepared additions "
                        "immediately after the immutable base prefix"
                    )
                for label, frame in (("body", body), ("critic", critic)):
                    registered = registry.registered_genesis(frame["stream_id"])
                    if (
                        registered is None
                        or registered.get("frame_hash") != frame["frame_hash"]
                    ):
                        reasons.append(
                            f"signed registry does not register the exact {label} genesis"
                        )

                try:
                    proposal = _canonical_document(
                        R,
                        paths["registry_proposal"],
                        label="unsigned registry proposal",
                    )
                    proposal_status, _, proposal_reason = REG.load_document(
                        proposal,
                        entries_member="entries",
                        trust_anchor=PINS["estate_owner"],
                        allow_unsigned=True,
                        persisted_seq=PINS["registry"]["registry_seq"],
                    )
                    if (
                        proposal_status != "draft"
                        or proposal.get("sig") is not None
                        or proposal.get("registry_seq")
                        != PINS["registry"]["registry_seq"] + 1
                        or proposal.get("entries", [])[base_count:] != additions
                    ):
                        reasons.append(
                            "saved registry proposal is not the exact unsigned prepared draft"
                        )
                    if proposal_status != "draft":
                        reasons.append(
                            f"saved registry proposal validation failed: {proposal_reason}"
                        )
                except ProtocolError as exc:
                    reasons.append(str(exc))

                try:
                    approval = _canonical_document(
                        R,
                        paths["approval_request"],
                        label="approval request",
                    )
                    if (
                        approval.get("status") != "owner-action-required"
                        or approval.get("based_on", {}).get("registry_sha256")
                        != PINS["registry"]["sha256"]
                        or approval.get("proposed_additions") != additions
                        or approval.get("candidate_genesis")
                        != {
                            "body": body["frame_hash"],
                            "critic": critic["frame_hash"],
                        }
                        or approval.get("review_policy") != REVIEW_POLICY
                    ):
                        reasons.append("approval request does not match the prepared control profile")
                except ProtocolError as exc:
                    reasons.append(str(exc))

    reasons = _unique_reasons(reasons)
    accepted = not reasons
    return {
        "accepted": accepted,
        "reasons": reasons,
        "claim": (
            "locally-verified registered control profile"
            if accepted
            else "blocked preparation-only control profile"
        ),
        "identity": rappid,
        "critic_stream_id": f"{rappid}:critic" if rappid else None,
        "registry": {
            "verified": registry_info is not None,
            "registry_seq": (
                registry_info["registry_seq"] if registry_info is not None else None
            ),
            "sha256": registry_info["sha256"] if registry_info is not None else None,
            "canonical_sha256": (
                registry_info["canonical_sha256"]
                if registry_info is not None
                else None
            ),
            "high_water": high_water["registry_seq"] if high_water is not None else None,
        },
        "adapter": (
            {"sha256": adapter["sha256"], "bytes": adapter["bytes"]}
            if adapter is not None
            else None
        ),
        "genesis": {
            "body": body["frame_hash"] if body is not None else None,
            "critic": critic["frame_hash"] if critic is not None else None,
        },
        "review_policy": copy.deepcopy(REVIEW_POLICY),
        "pins": copy.deepcopy(PINS),
    }


def _read_journal(
    R,
    registry,
    data: bytes,
    *,
    critic_genesis: dict[str, Any],
) -> list[dict[str, Any]]:
    if not data:
        return []
    if len(data) > _MAX_JOURNAL_BYTES:
        raise ProtocolError("review journal exceeds its local size bound")
    if not data.endswith(b"\n") or b"\r" in data:
        raise ProtocolError("review journal must be LF-terminated canonical JSONL")
    frames: list[dict[str, Any]] = []
    head = None
    for index, line in enumerate(data.splitlines(), 1):
        if not line:
            raise ProtocolError(f"review journal contains a blank line at {index}")
        frame = _strict_value(R, line, label=f"review journal frame {index}")
        if type(frame) is not dict:
            raise ProtocolError(f"review journal frame {index} is not an object")
        if line != _canonical_bytes(R, frame, label=f"review journal frame {index}"):
            raise ProtocolError(f"review journal frame {index} is not canonical JSON")
        if index == 1 and frame != critic_genesis:
            raise ProtocolError("review journal genesis differs from the registered candidate")
        if index > 1 and frame.get("kind") not in {"memory.save", "memory.chat-turn"}:
            raise ProtocolError("review journal contains an unapproved frame kind")
        if frame.get("sig") is not None or frame.get("prev_wave") is not None:
            raise ProtocolError("review journal memory frames must be unsigned with null prev_wave")
        ok, step, why = R.verify_frame(
            frame,
            head=head,
            stream_id_of_record=critic_genesis["stream_id"],
        )
        if not ok:
            raise ProtocolError(
                f"review journal frame {index} failed at {step}: {why}"
            )
        bound, reason = registry.check_frame_binding(frame)
        if not bound:
            raise ProtocolError(
                f"review journal frame {index} failed registry binding: {reason}"
            )
        if index > 1:
            payload = frame["payload"]
            required = {
                "simulation": True,
                "not_dhh": True,
                "no_endorsement": True,
                "review_only": True,
                "changes_applied": False,
                "review_policy": REVIEW_POLICY,
            }
            if any(payload.get(key) != value for key, value in required.items()):
                raise ProtocolError(
                    f"review journal frame {index} does not carry the fixed simulation policy"
                )
            changed_input_id = payload.get("changed_input_id")
            if (
                type(changed_input_id) is not str
                or not changed_input_id
                or len(changed_input_id) > 256
            ):
                raise ProtocolError(
                    f"review journal frame {index} has an invalid changed_input_id"
                )
        frames.append(frame)
        head = frame
    if len(frames) - 1 > REVIEW_POLICY["max_changed_input_reviews"]:
        raise ProtocolError("review journal exceeds the changed-input review limit")
    return frames


def _review_payload(payload: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise ProtocolError("review payload must be a mapping")
    value = copy.deepcopy(dict(payload))
    kind = value.pop("frame_kind", "memory.save")
    if kind not in {"memory.save", "memory.chat-turn"}:
        raise ProtocolError("frame_kind must be memory.save or memory.chat-turn")
    changed_input_id = value.get("changed_input_id")
    if (
        type(changed_input_id) is not str
        or not changed_input_id
        or len(changed_input_id) > 256
    ):
        raise ProtocolError("review payload requires a nonempty changed_input_id <= 256 characters")
    fixed = {
        "simulation": True,
        "not_dhh": True,
        "no_endorsement": True,
        "review_only": True,
        "changes_applied": False,
        "review_policy": copy.deepcopy(REVIEW_POLICY),
    }
    for key, expected in fixed.items():
        if key in value and value[key] != expected:
            raise ProtocolError(f"review payload conflicts with fixed field {key}")
        value[key] = expected
    return kind, value


def append_review(
    state_dir: Path | str,
    reference_dir: Path | str,
    registry_path: Path | str,
    adapter_path: Path | str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one activated, canonical, review-only memory frame."""

    status_report = activation_status(
        state_dir,
        reference_dir,
        registry_path,
        adapter_path,
    )
    if not status_report["accepted"]:
        raise ProtocolError(
            "activation is blocked: " + "; ".join(status_report["reasons"])
        )

    state = _path(state_dir, "state_dir")
    reference = _load_reference(reference_dir)
    R, REG = reference["R"], reference["REG"]
    adapter = _adapter_report(adapter_path)
    if adapter["sha256"] != status_report["adapter"]["sha256"]:
        raise ProtocolError("adapter changed after activation evaluation")
    registry_info = _load_verified_registry(
        R,
        REG,
        registry_path,
        persisted_seq=status_report["registry"]["high_water"],
    )
    if (
        registry_info["registry_seq"] != status_report["registry"]["registry_seq"]
        or registry_info["sha256"] != status_report["registry"]["sha256"]
    ):
        raise ProtocolError("signed registry changed after activation evaluation")

    paths = _state_paths(state)
    rappid = _load_identity(
        R,
        paths["identity"],
        owner="kody-w",
        slug="omarchy-workbench",
    )
    body = _canonical_document(R, paths["body_genesis"], label="body candidate genesis")
    critic = _canonical_document(
        R,
        paths["critic_genesis"],
        label="critic candidate genesis",
    )
    _validate_genesis(
        R,
        registry_info["registry"],
        body,
        kind="body.pulse",
        stream_id=rappid,
        payload=_body_payload(rappid, adapter),
    )
    _validate_genesis(
        R,
        registry_info["registry"],
        critic,
        kind="memory.save",
        stream_id=f"{rappid}:critic",
        payload=_critic_payload(rappid, body["frame_hash"]),
    )
    registered = registry_info["registry"].registered_genesis(critic["stream_id"])
    if registered is None or registered.get("frame_hash") != critic["frame_hash"]:
        raise ProtocolError("critic genesis is no longer registered")

    kind, review_payload = _review_payload(payload)
    journal_path = paths["review_journal"]
    _ensure_directory(journal_path.parent)
    if journal_path.is_symlink():
        raise ProtocolError("review journal must not be a symlink")
    flags = os.O_RDWR | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(journal_path, flags, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise ProtocolError("review journal must be a regular file")
        if info.st_size > _MAX_JOURNAL_BYTES:
            raise ProtocolError("review journal exceeds its local size bound")
        os.lseek(descriptor, 0, os.SEEK_SET)
        existing = b""
        remaining = _MAX_JOURNAL_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            existing += chunk
            remaining -= len(chunk)
        frames = _read_journal(
            R,
            registry_info["registry"],
            existing,
            critic_genesis=critic,
        )
        reviews = frames[1:] if frames else []
        if len(reviews) >= REVIEW_POLICY["max_changed_input_reviews"]:
            raise ProtocolError("maximum changed-input review count has been reached")
        if any(
            frame["payload"].get("changed_input_id")
            == review_payload["changed_input_id"]
            for frame in reviews
        ):
            raise ProtocolError("changed_input_id has already been reviewed")

        utc = _utc_now()
        if reviews:
            elapsed = (_utc_datetime(utc) - _utc_datetime(reviews[-1]["utc"])).total_seconds()
            if elapsed < REVIEW_POLICY["interval_seconds"]:
                raise ProtocolError(
                    "review interval has not elapsed: "
                    f"{int(elapsed)} < {REVIEW_POLICY['interval_seconds']} seconds"
                )

        head = frames[-1] if frames else critic
        frame = R.build_frame(
            kind,
            critic["stream_id"],
            head["seq"] + 1,
            utc,
            review_payload,
            prev=head["payload_hash"],
            prev_wave=None,
            sig=None,
        )
        ok, step, why = R.verify_frame(
            frame,
            head=head,
            stream_id_of_record=critic["stream_id"],
        )
        if not ok:
            raise ProtocolError(f"review frame failed at {step}: {why}")
        bound, reason = registry_info["registry"].check_frame_binding(frame)
        if not bound:
            raise ProtocolError(f"review frame registry binding failed: {reason}")

        addition = b""
        if not frames:
            addition += _canonical_bytes(R, critic, label="critic genesis") + b"\n"
        addition += _canonical_bytes(R, frame, label="review frame") + b"\n"
        if len(existing) + len(addition) > _MAX_JOURNAL_BYTES:
            raise ProtocolError("review journal would exceed its local size bound")
        view = memoryview(addition)
        while view:
            written = os.write(descriptor, view)
            view = view[written:]
        os.fsync(descriptor)
        _sync_directory(journal_path.parent)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    return {
        "accepted": True,
        "journal_path": str(journal_path),
        "kind": frame["kind"],
        "stream_id": frame["stream_id"],
        "seq": frame["seq"],
        "utc": frame["utc"],
        "payload_hash": frame["payload_hash"],
        "frame_hash": frame["frame_hash"],
        "frame": frame,
        "review_count": len(reviews) + 1,
        "max_changed_input_reviews": REVIEW_POLICY["max_changed_input_reviews"],
        "changes_applied": False,
        "claim": "registered review evidence; not DHH, endorsement, merge, or deployment approval",
    }


def _validate_state_name(R, value: Any) -> str:
    if type(value) is not str or not value:
        raise ProtocolError("state file names must be nonempty strings")
    if unicodedata.normalize("NFC", value) != value:
        raise ProtocolError("state file names must be Unicode NFC")
    if value.startswith("state/"):
        raise ProtocolError("state file names are relative beneath state/; omit the state/ prefix")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or str(path) != value
    ):
        raise ProtocolError(f"unsafe state file path: {value!r}")
    full = f"state/{value}"
    if not R._path_valid(full):
        raise ProtocolError(f"state file path violates the pinned egg grammar: {value!r}")
    return full


def _enforce_rapplication_layout(R, files: Mapping[str, bytes]) -> None:
    paths = list(files)
    if "agent.py" not in files or "rappid.json" not in files:
        raise ProtocolError("rapplication requires root agent.py and rappid.json")
    if sum(1 for path in paths if "/" not in path and path.endswith(".py")) != 1:
        raise ProtocolError("rapplication must contain exactly one root Python file: agent.py")
    if any(
        path not in {"agent.py", "rappid.json", "ui.html"}
        and not path.startswith("state/")
        for path in paths
    ):
        raise ProtocolError("rapplication contains a path outside its ratified layout")
    if len(paths) != len(set(paths)):
        raise ProtocolError("rapplication contains duplicate paths")
    if not R._path_set_valid(["manifest.json", *paths]):
        raise ProtocolError("rapplication paths collide on a common filesystem")


def _artifact_identity(
    R,
    state: Path,
    *,
    slug: str,
) -> tuple[str, str, dict[str, Path]]:
    if (
        type(slug) is not str
        or not 1 <= len(slug) <= 100
        or R._LCLABEL.fullmatch(slug) is None
    ):
        raise ProtocolError("slug must satisfy the pinned RAPP lclabel grammar")
    directory = state / "applications" / slug
    _ensure_directory(directory)
    identity_path = directory / "rappid.json"
    metadata_path = directory / "artifact-profile.json"
    rappid, _ = _load_or_mint_identity(
        R,
        identity_path,
        owner="kody-w",
        slug=slug,
    )
    if metadata_path.exists() or metadata_path.is_symlink():
        metadata = _canonical_document(R, metadata_path, label="artifact profile")
        if (
            set(metadata) != {"schema", "rappid", "slug", "created_utc"}
            or metadata.get("schema") != "omarchy-workbench-artifact-profile/1"
            or metadata.get("rappid") != rappid
            or metadata.get("slug") != slug
            or not R.utc_valid(metadata.get("created_utc"))
        ):
            raise ProtocolError("artifact profile is invalid or does not match its identity")
    else:
        metadata = {
            "schema": "omarchy-workbench-artifact-profile/1",
            "rappid": rappid,
            "slug": slug,
            "created_utc": _utc_now(),
        }
        _write_once_or_equal(
            metadata_path,
            _canonical_bytes(R, metadata, label="artifact profile"),
            label="artifact profile",
        )

    _assert_distinct_stored_identities(R, state)
    return rappid, metadata["created_utc"], {
        "identity": identity_path,
        "metadata": metadata_path,
    }


def pack_application(
    state_dir: Path | str,
    reference_dir: Path | str,
    slug: str,
    agent_path: Path | str,
    state_files: Mapping[str, bytes],
    output_path: Path | str,
) -> dict[str, Any]:
    """Pack one unsigned, non-activated rapplication with exact state-file bytes."""

    state = _path(state_dir, "state_dir")
    _ensure_directory(state)
    reference = _load_reference(reference_dir)
    R = reference["R"]
    agent_source_path = _path(agent_path, "agent_path")
    output = _path(output_path, "output_path")
    if output == agent_source_path:
        raise ProtocolError("output_path must not replace agent_path")
    agent_source = _read_regular(
        agent_source_path,
        maximum=_MAX_AGENT_BYTES,
        label="agent source",
    )
    if not isinstance(state_files, Mapping):
        raise ProtocolError("state_files must be a mapping of relative names to raw bytes")

    normalized: dict[str, bytes] = {}
    total = 0
    for relative, raw in state_files.items():
        full = _validate_state_name(R, relative)
        if not isinstance(raw, (bytes, bytearray, memoryview)):
            raise ProtocolError(f"state file {relative!r} must contain raw bytes")
        data = bytes(raw)
        if len(data) > _MAX_STATE_FILE_BYTES:
            raise ProtocolError(
                f"state file {relative!r} exceeds {_MAX_STATE_FILE_BYTES} bytes"
            )
        total += len(data)
        if total > _MAX_STATE_TOTAL_BYTES:
            raise ProtocolError(
                f"state files exceed {_MAX_STATE_TOTAL_BYTES} aggregate bytes"
            )
        if full in normalized:
            raise ProtocolError(f"duplicate state file path: {relative!r}")
        if relative == "legacy-creature-egg.json":
            # Application bytes are not a RAPP frame; valid legacy floats stay unchanged.
            try:
                legacy = json.loads(data)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise ProtocolError(f"legacy creature egg is not JSON: {exc}") from exc
            if type(legacy) is not dict:
                raise ProtocolError("legacy creature egg must be a JSON object")
        normalized[full] = data

    with _file_lock(state / _CONTROL_LOCK):
        rappid, created_utc, identity_paths = _artifact_identity(
            R,
            state,
            slug=slug,
        )
        identity_octets = _canonical_bytes(
            R,
            {"schema": "rapp/1", "rappid": rappid},
            label="packed artifact identity",
        )
        files = {
            "agent.py": agent_source,
            "rappid.json": identity_octets,
            **normalized,
        }
        _enforce_rapplication_layout(R, files)
        egg = R.pack_egg(
            "rapplication",
            rappid,
            created_utc,
            files=files,
            payload={},
            sig=None,
        )
        ok, step, why = R.verify_egg(egg)
        if not ok:
            raise ProtocolError(f"pinned reference refused packed egg at {step}: {why}")
        manifest, unpacked = R.read_egg(egg)
        _enforce_rapplication_layout(R, unpacked)
        if (
            manifest.get("schema") != "rapp/1-egg"
            or manifest.get("variant") != "rapplication"
            or manifest.get("rappid") != rappid
            or manifest.get("sig") is not None
            or set(unpacked) != set(files)
            or any(unpacked[path] != data for path, data in files.items())
        ):
            raise ProtocolError("packed egg failed exact manifest or content readback")
        _write_once_or_equal(output, egg, label="rapplication egg")

    return {
        "container_conformant": True,
        "variant": "rapplication",
        "rappid": rappid,
        "created_utc": created_utc,
        "egg_address": R.egg_address(manifest),
        "egg_sha256": _sha256(egg),
        "bytes": len(egg),
        "output_path": str(output),
        "identity_path": str(identity_paths["identity"]),
        "artifact_profile_path": str(identity_paths["metadata"]),
        "files": sorted(unpacked),
        "unsigned": True,
        "signature": None,
        "embedded_code_activated": False,
        "legacy_creature_preserved": (
            "state/legacy-creature-egg.json" in unpacked
        ),
        "claim": (
            "RAPP/1 rapplication container conformance only; "
            "embedded legacy runtime is neither activated nor approved"
        ),
        "pins": copy.deepcopy(PINS),
    }
