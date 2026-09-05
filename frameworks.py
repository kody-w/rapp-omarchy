"""Thin, fail-closed adapters for the pinned RAPP workbench frameworks.

RAPP Workspace owns the private world and store boundary. RAPP Projects owns
project cells, leases, checkpoints, policies, cycles, receipts, and derived
views. The Workspace reference writer is deliberately never loaded against a
Projects chain because the pinned profiles are not semantically compatible.

Public flow: construct ``NativeSources`` and ``WorkbenchFrameworks``; call
``initialize_solo_world``, ``ensure_project``, ``bind_worktree_layout``, and
``arm_review_policy``; use ``due_reviews`` and ``record_review_cycle``; consume
``inspect`` / ``activation_status``. ``herdr_estate_plan`` is optional and
plan-only. ``require_activation`` is the refusing parent-protocol handoff.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


PROJECTS_COMMIT = "2b375029d051b80b4df8c19749aeb64a96df216a"
WORKSPACE_COMMIT = "4e194d90cdd34d7ba050b24781fddff971cdb7b5"
HERDR_COMMIT = "e75b9b32d68cd7d37ee595b528136cb6c0ec7902"
RAPP_SDK_COMMIT = "402a7e0210b2c4e71d0a1b44744b842f3c2d6b49"
RAPP1_TOOLS_COMMIT = "eb50008011447f5e69372ac22a1755f0978d15ed"
RAPP1_ACCEPTED_COMMIT = "9a129ab59376b55dfe9b2c4ee089f5f4b630617c"
RAPP1_HEAD = "83ca275f35cca96e43d75c99d338326c1a39b2240eabf57eb7c29ac96cc90818"
RAPP1_NORMATIVE_SHA256 = "348e7d5baa94aaf2ce4c5354f3cb261f389298a04af65e271a686d3b62f7c384"
REGISTRY_COMMIT = "95e2f7290886e2de591fc78e4fb6e14b83435381"
REGISTRY_SEQ = 2
ESTATE_OWNER = (
    "rappid:@kody-w/estate-owner:"
    "b5814e45e9988df835dfd58d152a6fb05b6510a087a35c24374a1c4ab833c122"
)

REVIEW_MAY = ("draft", "read", "test")
REVIEW_NEVER = (
    "delete_external",
    "deploy",
    "merge",
    "network_change",
    "pay",
    "publish_remote",
    "purchase",
    "send",
    "sign",
    "write_local",
    "write_source",
)
REVIEW_STOP_CONDITIONS = (
    "goal complete",
    "approved input unchanged",
    "receipt verification fails",
    "authority verification fails",
    "human decision required",
)
REVIEW_HUMAN_GATES = ("external side effect", "budget increase")
_LABEL = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_LAYOUT_FORMAT = "omarchy-workbench-layout-v1"

SOURCE_CITATIONS = {
    "projects_store": (
        "https://github.com/kody-w/rapp-projects/blob/"
        f"{PROJECTS_COMMIT}/src/rapp_projects/core.py#L325-L1130"
    ),
    "projects_policy": (
        "https://github.com/kody-w/rapp-projects/blob/"
        f"{PROJECTS_COMMIT}/src/rapp_projects/core.py#L992-L1128"
    ),
    "projects_visibility": (
        "https://github.com/kody-w/rapp-projects/blob/"
        f"{PROJECTS_COMMIT}/src/rapp_projects/core.py#L1455-L1518"
    ),
    "projects_sdk_profile": (
        "https://github.com/kody-w/rapp-sdk/blob/"
        f"{RAPP_SDK_COMMIT}/src/rapp_sdk/projects.py#L30-L570"
    ),
    "projects_sdk_egg": (
        "https://github.com/kody-w/rapp-sdk/blob/"
        f"{RAPP_SDK_COMMIT}/src/rapp_sdk/projects.py#L1189-L1207"
    ),
    "workspace_boundary": (
        "https://github.com/kody-w/rapp-workspace/blob/"
        f"{WORKSPACE_COMMIT}/SPEC.md#L29-L132"
    ),
    "workspace_writer": (
        "https://github.com/kody-w/rapp-workspace/blob/"
        f"{WORKSPACE_COMMIT}/tools/append_frame.py#L148-L235"
    ),
    "herdr_estate": (
        "https://github.com/kody-w/rapp-herdr/blob/"
        f"{HERDR_COMMIT}/src/rapp_herdr/estate.py#L194-L437"
    ),
    "herdr_plan": (
        "https://github.com/kody-w/rapp-herdr/blob/"
        f"{HERDR_COMMIT}/src/rapp_herdr/estate.py#L808-L850"
    ),
    "rapp_reference": (
        "https://github.com/kody-w/rapp-1/blob/"
        f"{RAPP1_ACCEPTED_COMMIT}/rapp.py#L91-L305"
    ),
    "rapp_reference_egg": (
        "https://github.com/kody-w/rapp-1/blob/"
        f"{RAPP1_ACCEPTED_COMMIT}/rapp.py#L330-L365"
    ),
    "registry_checks": (
        "https://github.com/kody-w/rapp-1/blob/"
        f"{RAPP1_TOOLS_COMMIT}/rapp_registry.py#L296-L405"
    ),
    "signed_registry": (
        "https://github.com/kody-w/rapp-map/blob/"
        f"{REGISTRY_COMMIT}/ecosystem-spec.json"
    ),
}


class FrameworkError(RuntimeError):
    """A thin integration boundary refused an unsafe or ambiguous operation."""


class ActivationRefused(FrameworkError):
    """The local native state exists, but the authority gate is not satisfied."""


@dataclass(frozen=True)
class NativeSources:
    """Explicit local checkouts used by this adapter."""

    projects: Path
    workspace: Path
    sdk: Path
    rapp1: Path
    registry: Path
    herdr: Path | None = None

    def normalized(self) -> "NativeSources":
        return NativeSources(
            projects=Path(self.projects).expanduser().resolve(),
            workspace=Path(self.workspace).expanduser().resolve(),
            sdk=Path(self.sdk).expanduser().resolve(),
            rapp1=Path(self.rapp1).expanduser().resolve(),
            registry=Path(self.registry).expanduser().resolve(),
            herdr=(
                Path(self.herdr).expanduser().resolve()
                if self.herdr is not None
                else None
            ),
        )


def _run(arguments: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(arguments),
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise FrameworkError(f"{' '.join(arguments[:3])} failed: {detail[:1000]}")
    return result.stdout.rstrip("\r\n")


def _verify_git_checkout(path: Path, expected: str, label: str) -> dict[str, str]:
    if not path.is_dir() or path.is_symlink():
        raise FrameworkError(f"{label} checkout must be a regular directory: {path}")
    head = _run(("git", "-C", str(path), "rev-parse", "HEAD"))
    if head != expected:
        raise FrameworkError(f"{label} checkout is {head}, expected {expected}")
    result = subprocess.run(
        ["git", "-C", str(path), "diff", "--quiet", "HEAD", "--"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise FrameworkError(f"{label} checkout has tracked modifications")
    return {"path": str(path), "commit": head}


@contextlib.contextmanager
def _path_prefix(*paths: Path):
    prior = list(sys.path)
    sys.path[:0] = [str(path) for path in paths]
    try:
        yield
    finally:
        sys.path[:] = prior


def _module_is_from(module, root: Path) -> bool:
    origin = getattr(module, "__file__", None)
    return bool(origin and Path(origin).resolve().is_relative_to(root.resolve()))


def _import_package(name: str, source_root: Path):
    existing = sys.modules.get(name)
    if existing is not None:
        if not _module_is_from(existing, source_root):
            raise FrameworkError(
                f"{name} is already loaded from an unpinned location: "
                f"{getattr(existing, '__file__', '<unknown>')}"
            )
        return existing
    with _path_prefix(source_root):
        module = importlib.import_module(name)
    if not _module_is_from(module, source_root):
        raise FrameworkError(f"{name} did not load from {source_root}")
    return module


def _load_file_module(label: str, path: Path):
    name = (
        "_omarchy_workbench_"
        + label
        + "_"
        + hashlib.sha256(str(path).encode()).hexdigest()[:12]
    )
    existing = sys.modules.get(name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FrameworkError(f"cannot load native module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def _load_reference_modules(root: Path):
    reference = _load_file_module("rapp_reference", root / "rapp.py")
    registry_path = root / "rapp_registry.py"
    name = (
        "_omarchy_workbench_rapp_registry_"
        + hashlib.sha256(str(registry_path).encode()).hexdigest()[:12]
    )
    existing = sys.modules.get(name)
    if existing is not None:
        return reference, existing
    prior = sys.modules.get("rapp")
    sys.modules["rapp"] = reference
    try:
        registry = _load_file_module("rapp_registry", registry_path)
    finally:
        if prior is None:
            sys.modules.pop("rapp", None)
        else:
            sys.modules["rapp"] = prior
    return reference, registry


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, value: object) -> None:
    _atomic_bytes(
        path,
        (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise FrameworkError(f"required JSON file is missing or unsafe: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FrameworkError(f"invalid JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise FrameworkError(f"JSON file must contain an object: {path}")
    return value


@contextlib.contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _label(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not _LABEL.fullmatch(value)
        or len(value.encode("utf-8")) > 100
    ):
        raise FrameworkError(f"{field} must be a lowercase RAPP label")
    return value


def _text(value: str, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(character in value for character in ("\0", "\n", "\r"))
    ):
        raise FrameworkError(f"{field} must be non-empty single-line text")
    return value.strip()


class WorkbenchFrameworks:
    """Use the pinned native frameworks inside one explicit private root."""

    def __init__(
        self,
        workspace_root: str | Path,
        sources: NativeSources,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        raw_root = Path(workspace_root).expanduser()
        if not raw_root.is_absolute():
            raise FrameworkError("workspace_root must be an explicit absolute path")
        if raw_root.exists() and raw_root.is_symlink():
            raise FrameworkError("workspace_root cannot be a symbolic link")
        self.root = raw_root.resolve()
        self.sources = sources.normalized()
        self.clock = clock
        self.source_pins = self._verify_sources()
        with _path_prefix(
            self.sources.projects / "src",
            self.sources.sdk / "src",
        ):
            self.sdk = _import_package("rapp_sdk", self.sources.sdk / "src")
            self.projects = _import_package(
                "rapp_projects",
                self.sources.projects / "src",
            )
            self.projects_core = importlib.import_module("rapp_projects.core")
        self.reference, self.registry_reference = _load_reference_modules(
            self.sources.rapp1
        )
        self._store_instance = None

    @property
    def projects_root(self) -> Path:
        return self.root / "rapp-projects"

    def _verify_sources(self) -> dict[str, object]:
        pins: dict[str, object] = {
            "projects": _verify_git_checkout(
                self.sources.projects,
                PROJECTS_COMMIT,
                "rapp-projects",
            ),
            "workspace": _verify_git_checkout(
                self.sources.workspace,
                WORKSPACE_COMMIT,
                "rapp-workspace",
            ),
            "sdk": _verify_git_checkout(
                self.sources.sdk,
                RAPP_SDK_COMMIT,
                "rapp-sdk",
            ),
            "rapp1_tools": _verify_git_checkout(
                self.sources.rapp1,
                RAPP1_TOOLS_COMMIT,
                "rapp-1 reference tools",
            ),
        }
        if self.sources.herdr is not None:
            pins["herdr"] = _verify_git_checkout(
                self.sources.herdr,
                HERDR_COMMIT,
                "rapp-herdr",
            )
        if not self.sources.registry.is_file():
            raise FrameworkError(f"signed registry is missing: {self.sources.registry}")
        if not (self.sources.workspace / "SPEC.md").is_file():
            raise FrameworkError("rapp-workspace SPEC.md is missing")
        spec = (self.sources.workspace / "SPEC.md").read_text(encoding="utf-8")
        if "`spec_id: rapp-workspace/1.1`" not in spec:
            raise FrameworkError("rapp-workspace checkout is not profile 1.1")
        pins["registry"] = {
            "path": str(self.sources.registry),
            "commit": REGISTRY_COMMIT,
            "registry_seq": REGISTRY_SEQ,
        }
        return pins

    def _documents(
        self,
        *,
        name: str,
        owner: str,
        world_id: str,
    ) -> dict[str, str]:
        return {
            "README.md": (
                "# PRIVATE RAPP Workspace — NEVER PUBLISH\n\n"
                f"This is the private `{world_id}` world for {name}. It is local-only by "
                "default. Public projections must be separate and PII-free.\n"
            ),
            "CLAUDE.md": (
                f"# {name} operating boundary\n\n"
                f"Owner: `{owner}`. World: `{world_id}`. Slosh within this world; never "
                "read or write across another world_id. Propose external effects and "
                "budget changes for human approval. Never publish this vault.\n"
            ),
            "HOME.md": (
                f"# {name}\n\n"
                "Project authority lives under `rapp-projects/`. Use its BOARD.md and "
                "CATCHUP.md projections; never hand-edit project history.\n"
            ),
            "OWNER.md": (
                f"# Owner\n\nRAPP owner label: `{owner}`.\n\n"
                "The owner remains sovereign over visibility, external effects, budgets, "
                "publication, signing, and irreversible actions.\n"
            ),
            "where-everything-lives.md": (
                "# Where everything lives\n\n"
                "- `rappid.json` — mint-once private workspace identity and world boundary.\n"
                "- `rapp-projects/projects/` — native Projects cells and frame authority.\n"
                "- `rapp-projects/BOARD.md` — rebuildable native board projection.\n"
                "- External worktree layouts — receipts only; source and artifact bodies stay put.\n"
            ),
        }

    def initialize_solo_world(
        self,
        *,
        slug: str,
        name: str,
        owner: str,
        world_id: str,
    ) -> dict[str, object]:
        slug = _label(slug, "workspace slug")
        owner = _label(owner, "workspace owner")
        name = _text(name, "workspace name")
        world_id = _text(world_id, "world_id")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        identity_path = self.root / "rappid.json"
        with _file_lock(self.root / ".frameworks.lock"):
            created = not identity_path.exists()
            if not created:
                identity = _read_json(identity_path)
            else:
                occupants = [
                    entry.name
                    for entry in self.root.iterdir()
                    if entry.name != ".frameworks.lock"
                ]
                if occupants:
                    raise FrameworkError(
                        "refusing to mint a workspace identity into a non-empty "
                        f"unowned root: {sorted(occupants)}"
                    )
                identity = {
                    "schema": "rapp/1",
                    "rappid": self.reference.mint_rappid(owner, slug),
                    "name": name,
                    "mode": "solo",
                    "world_id": world_id,
                }
                _atomic_json(identity_path, identity)
            self._validate_world_identity(
                identity,
                slug=slug,
                name=name,
                owner=owner,
                world_id=world_id,
            )
            for filename, content in self._documents(
                name=name,
                owner=owner,
                world_id=world_id,
            ).items():
                path = self.root / filename
                if path.exists():
                    if not path.is_file() or path.is_symlink():
                        raise FrameworkError(f"unsafe workspace document: {path}")
                else:
                    _atomic_bytes(path, content.encode("utf-8"))
            self.projects_root.mkdir(exist_ok=True, mode=0o700)
            os.chmod(self.projects_root, 0o700)
        return {
            "created": created,
            "root": str(self.root),
            "identity": identity,
            "mode": "solo",
            "world_id": world_id,
            "projects_root": str(self.projects_root),
            "workspace_writer_enabled": False,
            "ownership": {
                "world_and_store": "rapp-workspace/1.1",
                "project_cell_and_lease": "rapp-projects/1",
            },
        }

    def _validate_world_identity(
        self,
        identity: Mapping[str, object],
        *,
        slug: str | None = None,
        name: str | None = None,
        owner: str | None = None,
        world_id: str | None = None,
    ) -> dict[str, object]:
        if identity.get("schema") != "rapp/1":
            raise FrameworkError("workspace identity schema must be rapp/1")
        if identity.get("mode") != "solo" or identity.get("members"):
            raise FrameworkError("this adapter activates SOLO workspaces only")
        if not isinstance(identity.get("world_id"), str) or not identity["world_id"]:
            raise FrameworkError("workspace identity must declare world_id")
        rappid = identity.get("rappid")
        if not self.reference.rappid_valid(rappid):
            raise FrameworkError("workspace identity contains an invalid RAPPID")
        parts = self.reference.rappid_parts(rappid)
        if slug is not None and parts["slug"] != slug:
            raise FrameworkError("existing workspace RAPPID belongs to another slug")
        if owner is not None and parts["owner"] != owner:
            raise FrameworkError("existing workspace RAPPID belongs to another owner")
        if name is not None and identity.get("name") != name:
            raise FrameworkError("existing workspace uses another name")
        if world_id is not None and identity.get("world_id") != world_id:
            raise FrameworkError("existing workspace belongs to another world_id")
        return dict(identity)

    def world_identity(self) -> dict[str, object]:
        return self._validate_world_identity(_read_json(self.root / "rappid.json"))

    def project_store(self):
        self.world_identity()
        if self._store_instance is None:
            self._store_instance = self.projects.ProjectStore(
                self.projects_root,
                clock=self.clock,
            )
        return self._store_instance

    def _state(self, project: str) -> dict[str, object]:
        project = _label(project, "project")
        rows = self.project_store().rebuild()
        matches = [row for row in rows if row.get("project") == project]
        if len(matches) != 1:
            raise FrameworkError(f"native project is not available: {project}")
        if matches[0].get("state") == "corrupt":
            raise FrameworkError(f"native project failed verification: {project}")
        return matches[0]

    def ensure_project(
        self,
        project: str,
        *,
        title: str,
        goal: str,
        owner: str,
        origin: str,
    ) -> dict[str, object]:
        project = _label(project, "project")
        store = self.project_store()
        path = store.project_path(project)
        created = not (path / "rappid.json").is_file()
        if created:
            entropy = self._mint_input(project, create=True)
            store.open(
                project,
                title=title,
                goal=goal,
                owner=owner,
                origin=origin,
                visibility="local",
                entropy=entropy,
            )
        frames = store.frames(project)
        genesis = frames[0]["payload"]
        expected = {
            "project": project,
            "title": title,
            "goal": goal,
            "owner": owner,
            "origin": origin,
            "visibility": "local",
        }
        if any(genesis.get(key) != value for key, value in expected.items()):
            raise FrameworkError("existing native project genesis conflicts with request")
        return {
            "created": created,
            "project": project,
            "identity": _read_json(path / "rappid.json"),
            "stream_id": frames[0]["stream_id"],
            "genesis": {
                "seq": frames[0]["seq"],
                "frame_hash": frames[0]["frame_hash"],
                "payload_hash": frames[0]["payload_hash"],
            },
            "head": {
                "seq": frames[-1]["seq"],
                "frame_hash": frames[-1]["frame_hash"],
                "payload_hash": frames[-1]["payload_hash"],
            },
            "visibility": "local",
            "model_context_approved": False,
        }

    def _mint_input(self, project: str, *, create: bool = False) -> bytes:
        path = self.root / "mint-inputs" / f"{_label(project, 'project')}.json"
        with _file_lock(self.root / ".mint-inputs.lock"):
            if create and not path.exists():
                _atomic_json(path, {
                    "schema": "omarchy-workbench-mint-input/1",
                    "uuid4": str(uuid.uuid4()),
                    "claim": "local producer receipt; not registration or signing authority",
                })
            value = _read_json(path)
        if value.get("schema") != "omarchy-workbench-mint-input/1":
            raise FrameworkError("native project mint-input receipt has an invalid schema")
        try:
            entropy = uuid.UUID(value["uuid4"])
        except (KeyError, ValueError, TypeError, AttributeError) as error:
            raise FrameworkError("native project mint input is not a UUID") from error
        if entropy.version != 4 or entropy.variant != uuid.RFC_4122 or str(entropy) != value["uuid4"]:
            raise FrameworkError("native project mint input must be a canonical UUIDv4")
        return entropy.bytes

    def review_actor(
        self,
        *,
        session_id: str,
        actor_id: str = "simulated-dhh-inspired-reviewer",
        runtime: str = "rapp-brainstem",
        model: str | None = None,
        host: str | None = None,
    ):
        return self.projects.Actor(
            id=actor_id,
            runtime=runtime,
            session_id=session_id,
            capabilities=REVIEW_MAY,
            model=model,
            host=host,
        )

    @staticmethod
    def _actor_key(value: Mapping[str, object] | object) -> tuple[object, ...]:
        payload = value.as_payload() if hasattr(value, "as_payload") else value
        if not isinstance(payload, Mapping):
            return ()
        return (
            payload.get("id"),
            payload.get("runtime"),
            payload.get("session_id"),
        )

    def _ensure_actor_lease(self, project, actor, *, location, lease_seconds):
        state = self._state(project)
        current = state.get("actor")
        if current is not None and self._actor_key(current) != self._actor_key(actor):
            raise FrameworkError("another actor owns the native project lease")
        expires = state.get("lease_expires_utc")
        if current is None or not isinstance(expires, str) or self.projects_core._parse_utc(expires) <= self.clock():
            self.project_store().punchin(
                project, actor, location=str(location),
                intent="Review changed, approved Omarchy workbench inputs only",
                role="simulated-dhh-inspired-reviewer", lease_seconds=lease_seconds,
            )
            state = self._state(project)
        return state

    def _layout(self, path: str | Path, expected_session: str) -> dict[str, object]:
        layout_path = Path(path).expanduser().resolve()
        value = _read_json(layout_path)
        if value.get("format") != _LAYOUT_FORMAT:
            raise FrameworkError(f"layout format must be {_LAYOUT_FORMAT}")
        if value.get("session") != expected_session:
            raise FrameworkError("layout belongs to another Herdr session")
        raw_lanes = value.get("lanes")
        if not isinstance(raw_lanes, list) or not 1 <= len(raw_lanes) <= 16:
            raise FrameworkError("layout must declare between one and sixteen lanes")
        lanes = []
        seen_numbers: set[int] = set()
        seen_paths: set[Path] = set()
        for raw in raw_lanes:
            if not isinstance(raw, Mapping):
                raise FrameworkError("layout lane must be an object")
            number = raw.get("number")
            if (
                not isinstance(number, int)
                or isinstance(number, bool)
                or not 1 <= number <= 16
                or number in seen_numbers
            ):
                raise FrameworkError("layout lane number is invalid or duplicated")
            lane_path = Path(str(raw.get("path") or "")).expanduser()
            if not lane_path.is_absolute():
                raise FrameworkError("layout lane paths must be absolute")
            if lane_path.is_symlink() or not lane_path.is_dir():
                raise FrameworkError(f"layout lane path is unavailable: {lane_path}")
            lane_path = lane_path.resolve()
            if lane_path in seen_paths:
                raise FrameworkError("layout lane path is duplicated")
            top = Path(_run(("git", "-C", str(lane_path), "rev-parse", "--show-toplevel")))
            if top.resolve() != lane_path:
                raise FrameworkError(f"lane is not a Git worktree root: {lane_path}")
            branch = _run(("git", "-C", str(lane_path), "symbolic-ref", "--short", "HEAD"))
            if branch != raw.get("branch"):
                raise FrameworkError(f"lane branch does not match layout: {lane_path}")
            head = _run(("git", "-C", str(lane_path), "rev-parse", "HEAD"))
            dirty = _run(
                ("git", "-C", str(lane_path), "status", "--porcelain=v1")
            ).splitlines()
            lanes.append(
                {
                    "number": number,
                    "path": str(lane_path),
                    "branch": branch,
                    "head": head,
                    "dirty_paths": [line[3:] for line in dirty if len(line) >= 4],
                    "workspace_id": raw.get("workspace_id"),
                    "tab_id": raw.get("tab_id"),
                    "pane_id": raw.get("pane_id"),
                }
            )
            seen_numbers.add(number)
            seen_paths.add(lane_path)
        lanes.sort(key=lambda lane: lane["number"])
        return {
            "path": str(layout_path),
            "sha256": hashlib.sha256(layout_path.read_bytes()).hexdigest(),
            "lanes": lanes,
        }

    def bind_worktree_layout(
        self,
        project: str,
        actor,
        *,
        layout_path: str | Path,
        repository: str,
        primary_lane: int = 1,
        session: str = "rapp1-workbench",
        lease_seconds: int = 7200,
    ) -> dict[str, object]:
        layout = self._layout(layout_path, session)
        lanes = layout["lanes"]
        primary = next(
            (lane for lane in lanes if lane["number"] == primary_lane),
            None,
        )
        if primary is None:
            raise FrameworkError("primary_lane is absent from the native layout")
        store = self.project_store()
        state = self._ensure_actor_lease(
            project, actor, location=primary["path"], lease_seconds=lease_seconds,
        )
        observation = {
            "schema": "omarchy-worktree-observation/1", "session": session,
            "repository": repository, "primary_lane": primary_lane,
            "layout_path": layout["path"], "layout_sha256": layout["sha256"],
            "lanes": layout["lanes"],
        }
        observation_bytes = self.reference.canonical(observation).encode("utf-8")
        observation_hash = hashlib.sha256(observation_bytes).hexdigest()
        observation_path = self.root / "worktree-observations" / f"{observation_hash}.json"
        if observation_path.exists():
            if observation_path.is_symlink() or observation_path.read_bytes() != observation_bytes:
                raise FrameworkError("existing worktree observation differs from its content address")
        else:
            _atomic_bytes(observation_path, observation_bytes)
        layout["observation_path"] = str(observation_path)
        layout["observation_sha256"] = observation_hash
        checkpoint = state.get("checkpoint")
        if isinstance(checkpoint, Mapping):
            artifacts = checkpoint.get("artifacts")
            workspace = checkpoint.get("workspace")
            if (
                isinstance(artifacts, list)
                and any(
                    isinstance(item, Mapping)
                    and item.get("path") == str(observation_path)
                    and item.get("sha256") == observation_hash
                    for item in artifacts
                )
                and isinstance(workspace, Mapping)
                and workspace.get("cwd") == primary["path"]
                and workspace.get("branch") == primary["branch"]
                and workspace.get("head") == primary["head"]
                and workspace.get("dirty_paths") == primary["dirty_paths"]
                and workspace.get("repository") == repository
            ):
                return {
                    "created": False,
                    "layout": layout,
                    "checkpoint": checkpoint,
                }
        frame = store.checkpoint(
            project,
            actor,
            summary=(
                f"Bound {len(lanes)} existing isolated Omarchy worktree lanes "
                "through the existing Herdr layout receipt."
            ),
            completed=[
                "initialized the private Workspace world",
                "opened the native Projects cell",
            ],
            in_progress="review-only workbench standardization",
            next_action="wait for changed approved input and the native due time",
            resume_prompt=(
                "Verify PROJECT.egg, read docs/RESUME.md, inspect the existing "
                "Herdr layout receipt, then continue review-only."
            ),
            cwd=primary["path"],
            repository=repository,
            branch=primary["branch"],
            head=primary["head"],
            dirty_paths=primary["dirty_paths"],
            commands=[],
            artifacts=[observation_path],
        )
        return {
            "created": True,
            "layout": layout,
            "checkpoint_frame_hash": frame["frame_hash"],
            "receipt_copied": False,
        }

    def arm_review_policy(
        self,
        project: str,
        actor,
        *,
        location: str | Path | None = None,
        lease_seconds: int = 7200,
        cadence_seconds: int = 1800,
        max_cycles: int = 10,
        max_seconds_per_cycle: int = 900,
        human_approved_policy_change: bool = False,
    ) -> dict[str, object]:
        if cadence_seconds != 1800 or max_cycles != 10:
            if not human_approved_policy_change:
                raise FrameworkError(
                    "changing the default cadence or cycle budget requires "
                    "explicit human_approved_policy_change"
                )
        if not 0 < max_seconds_per_cycle <= cadence_seconds:
            raise FrameworkError("max_seconds_per_cycle must fit within cadence")
        store = self.project_store()
        state = self._ensure_actor_lease(
            project, actor, location=Path(location or self.root).expanduser().resolve(),
            lease_seconds=lease_seconds,
        )
        desired = {
            "cadence_seconds": cadence_seconds,
            "may": list(REVIEW_MAY),
            "never": list(REVIEW_NEVER),
            "budgets": {
                "max_cycles": max_cycles,
                "max_seconds_per_cycle": max_seconds_per_cycle,
            },
            "stop_conditions": list(REVIEW_STOP_CONDITIONS),
            "human_gates": list(REVIEW_HUMAN_GATES),
        }
        existing = state.get("cell_policy")
        if isinstance(existing, Mapping):
            comparable = {key: existing.get(key) for key in desired}
            if comparable == desired:
                return {"created": False, "policy": dict(existing)}
            if not human_approved_policy_change:
                raise FrameworkError(
                    "native policy changes require explicit human approval"
                )
        frame = store.set_cell_policy(
            project,
            actor,
            cadence_seconds=cadence_seconds,
            may=REVIEW_MAY,
            never=REVIEW_NEVER,
            max_cycles=max_cycles,
            max_seconds_per_cycle=max_seconds_per_cycle,
            stop_conditions=REVIEW_STOP_CONDITIONS,
            human_gates=REVIEW_HUMAN_GATES,
        )
        return {
            "created": True,
            "frame_hash": frame["frame_hash"],
            "policy": frame["payload"],
            "reviewer": "SIMULATED DHH-inspired reviewer; no endorsement or authority",
        }

    def approve_model_context(
        self,
        project: str,
        *,
        owner_approved: bool = False,
    ) -> str:
        if owner_approved is not True:
            raise FrameworkError("model context requires explicit local owner approval")
        return str(self.project_store().approve_model_context(project, "local"))

    def due_reviews(self, project: str | None = None) -> list[dict[str, object]]:
        due = self.project_store().due_cells()
        if project is not None:
            project = _label(project, "project")
            due = [row for row in due if row.get("project") == project]
        return due

    @staticmethod
    def _native_cycle_receipt_fingerprint(
        frames: Iterable[Mapping[str, object]],
    ) -> tuple[tuple[str, int], ...] | None:
        for frame in reversed(list(frames)):
            payload = frame.get("payload")
            if (
                not isinstance(payload, Mapping)
                or payload.get("event") != "cell.cycle"
            ):
                continue
            receipts = payload.get("receipts")
            if not isinstance(receipts, list):
                return None
            values = []
            for receipt in receipts:
                if (
                    not isinstance(receipt, Mapping)
                    or not isinstance(receipt.get("sha256"), str)
                    or not isinstance(receipt.get("bytes"), int)
                ):
                    return None
                values.append((receipt["sha256"], receipt["bytes"]))
            return tuple(sorted(values))
        return None

    @staticmethod
    def _receipt_inputs(
        receipts: Iterable[str | Path],
    ) -> tuple[list[Path], tuple[tuple[str, int], ...]]:
        paths = []
        fingerprint = []
        for value in receipts:
            path = Path(value).expanduser()
            if not path.is_absolute():
                raise FrameworkError("review receipts must use explicit absolute paths")
            if path.is_symlink() or not path.is_file():
                raise FrameworkError(f"review receipt is not a regular file: {path}")
            path = path.resolve()
            content = path.read_bytes()
            paths.append(path)
            fingerprint.append((hashlib.sha256(content).hexdigest(), len(content)))
        if not paths:
            raise FrameworkError("a review cycle requires at least one receipt")
        return paths, tuple(sorted(fingerprint))

    def record_review_cycle(
        self,
        project: str,
        actor,
        *,
        outcome: str,
        observations: Iterable[str],
        proposed: Iterable[str],
        applied: Iterable[str],
        blockers: Iterable[str],
        action_classes: Iterable[str],
        elapsed_seconds: int,
        receipts: Iterable[str | Path],
    ) -> dict[str, object]:
        if outcome not in {"completed", "blocked"}:
            raise FrameworkError("review outcome must be completed or blocked")
        blocker_values = [str(value) for value in blockers]
        if outcome == "blocked" and not blocker_values:
            raise FrameworkError("a blocked review must identify at least one blocker")
        if outcome == "completed" and blocker_values:
            raise FrameworkError("a completed review cannot declare blockers")
        project = _label(project, "project")
        store = self.project_store()
        # Serialize the composite wrapper, not a second writer lease or project ledger.
        with _file_lock(self.root / ".review-locks" / f"{project}.lock"):
            receipt_paths, fingerprint = self._receipt_inputs(receipts)
            frames = store.frames(project)
            cycles = [frame for frame in frames if frame["payload"].get("event") == "cell.cycle"]
            if cycles:
                previous = cycles[-1]
                prior = self._native_cycle_receipt_fingerprint(frames)
                if prior == fingerprint:
                    result = self._finish_review_cycle(project, actor, previous)
                    if result["appended"]:
                        result["recovered"] = True
                    else:
                        result.update(status="skipped", reason="approved input receipts are unchanged")
                    return result
                status_frame, verification = self._review_followups(frames, previous)
                if status_frame is None or verification is None:
                    raise FrameworkError("previous review cycle is incomplete; retry its original immutable receipts first")
            if not self.due_reviews(project):
                raise FrameworkError("native RAPP Projects does not report this cell due")
            cycle = store.record_cell_cycle(
                project, actor,
                observations=[str(value) for value in observations],
                proposed=[str(value) for value in proposed],
                applied=[str(value) for value in applied] if outcome == "completed" else [],
                rejected=blocker_values,
                action_classes=[str(value) for value in action_classes],
                elapsed_seconds=elapsed_seconds, receipts=receipt_paths,
            )
            result = self._finish_review_cycle(project, actor, cycle)
            result["appended"] = True
            return result

    def _review_followups(self, frames, cycle):
        payload = cycle["payload"]
        outcome = "blocked" if payload["rejected"] else "completed"
        expected_next = (
            payload["proposed"][0] if payload["proposed"] else
            "await human decision" if outcome == "blocked" else
            "wait for changed input and the next native due time"
        )
        suffix = frames[int(cycle["seq"]) + 1:]
        status_frame = next((
            frame for frame in suffix
            if frame["payload"].get("event") == "work.status"
            and self._actor_key(frame["payload"].get("actor")) == self._actor_key(payload["actor"])
            and frame["payload"].get("status") == f"review {outcome}"
            and frame["payload"].get("blockers") == payload["rejected"]
            and frame["payload"].get("next_action") == expected_next
        ), None)
        verification = next((
            frame for frame in suffix
            if status_frame is not None
            and frame["payload"].get("event") == "project.verify"
            and frame["payload"].get("verdict") == "pass"
            and frame["payload"].get("verified_frames", 0) > int(status_frame["seq"])
        ), None)
        return status_frame, verification

    def _finish_review_cycle(self, project, actor, cycle):
        store = self.project_store()
        frames = store.frames(project)
        status_frame, verification = self._review_followups(frames, cycle)
        payload = cycle["payload"]
        outcome = "blocked" if payload["rejected"] else "completed"
        appended = False
        if status_frame is None:
            if self._actor_key(actor) != self._actor_key(payload["actor"]):
                raise FrameworkError("an incomplete review belongs to another actor")
            for frame in frames[int(cycle["seq"]) + 1:]:
                item = frame["payload"]
                if item.get("event") == "project.verify":
                    continue
                if item.get("event") in {"work.punchin", "work.heartbeat"} and self._actor_key(item.get("actor")) == self._actor_key(actor):
                    continue
                raise FrameworkError("review completion is ambiguous after intervening work; inspect native history")
            state = self._state(project)
            status_frame = store.status(
                project, actor, location=str(state.get("location") or self.root),
                status=f"review {outcome}", artifacts=[], blockers=payload["rejected"],
                next_action=(
                    payload["proposed"][0] if payload["proposed"] else
                    "await human decision" if outcome == "blocked" else
                    "wait for changed input and the next native due time"
                ),
                pct=int(state.get("pct") or 0),
            )
            appended = True
        if verification is None:
            verified = store.verify(project)
            if verified["verdict"] != "pass":
                raise FrameworkError("review cycle committed, but native receipt verification failed")
            verification = verified["frame"]
            appended = True
        return {
            "status": "ok",
            "project": project,
            "outcome": outcome,
            "appended": appended,
            "cycle_frame_hash": cycle["frame_hash"],
            "cycle": payload["cycle"],
            "status_frame_hash": status_frame["frame_hash"],
            "receipt_verdict": verification["payload"]["verdict"],
            "verification_frame_hash": verification["frame_hash"],
            "receipts": payload["receipts"],
        }

    def activation_status(self, project: str) -> dict[str, object]:
        findings: list[dict[str, object]] = []

        def finding(
            code: str,
            ok: bool,
            detail: str,
            *,
            severity: str = "info",
            source: str | None = None,
        ) -> None:
            findings.append(
                {
                    "code": code,
                    "ok": ok,
                    "severity": severity,
                    "detail": detail,
                    "source": source,
                }
            )

        registry_document = _read_json(self.sources.registry)
        registry_status, registry, registry_reason = (
            self.registry_reference.load_document(
                registry_document,
                entries_member="entries",
                trust_anchor=ESTATE_OWNER,
                persisted_seq=REGISTRY_SEQ,
            )
        )
        finding(
            "signed-registry",
            registry_status == "verified",
            f"{registry_status}: {registry_reason}",
            severity="blocker" if registry_status != "verified" else "info",
            source=SOURCE_CITATIONS["signed_registry"],
        )
        live_protocols = [
            entry
            for entry in registry_document.get("entries", [])
            if isinstance(entry, Mapping)
            and entry.get("type") == "protocol"
            and entry.get("name") == "rapp/1"
            and entry.get("deprecated") is False
        ]
        protocol_ok = (
            len(live_protocols) == 1
            and live_protocols[0].get("spec_hash") == RAPP1_NORMATIVE_SHA256
            and registry_document.get("anchor", {}).get("head_frame_hash")
            == RAPP1_HEAD
        )
        finding(
            "accepted-rapp1-checkpoint",
            protocol_ok,
            (
                f"accepted_commit={RAPP1_ACCEPTED_COMMIT}, "
                f"head={RAPP1_HEAD}, normative_sha256={RAPP1_NORMATIVE_SHA256}"
            ),
            severity="blocker" if not protocol_ok else "info",
            source=SOURCE_CITATIONS["registry_checks"],
        )
        store = self.project_store()
        frames = store.frames(project)
        head = None
        frame_ok = True
        frame_reason = "all native frames pass the current canonical verifier"
        for frame in frames:
            ok, step, reason = self.reference.verify_frame(
                frame,
                head=head,
                stream_id_of_record=frames[0]["stream_id"],
            )
            if not ok:
                frame_ok = False
                frame_reason = f"seq {frame.get('seq')} step {step}: {reason}"
                break
            head = frame
        finding(
            "canonical-frame-verification",
            frame_ok,
            frame_reason,
            severity="blocker" if not frame_ok else "info",
            source=SOURCE_CITATIONS["rapp_reference"],
        )
        binding_ok = registry is not None
        binding_reason = "body.pulse is live and bound to a body stream"
        if registry is not None:
            for frame in frames:
                ok, reason = registry.check_frame_binding(frame)
                if not ok:
                    binding_ok = False
                    binding_reason = reason
                    break
        else:
            binding_reason = "signed registry was unavailable"
        finding(
            "signed-kind-binding",
            binding_ok,
            binding_reason,
            severity="blocker" if not binding_ok else "info",
            source=SOURCE_CITATIONS["registry_checks"],
        )
        stream_id = str(frames[0]["stream_id"])
        registered_genesis = (
            registry.registered_genesis(stream_id) if registry is not None else None
        )
        genesis_ok = bool(
            registered_genesis
            and registered_genesis.get("frame_hash") == frames[0]["frame_hash"]
        )
        finding(
            "registered-project-genesis",
            genesis_ok,
            (
                "the signed registry has no binding for the newly minted native "
                f"project stream {stream_id}"
                if not genesis_ok
                else "project genesis matches the signed registry"
            ),
            severity="blocker" if not genesis_ok else "info",
            source=SOURCE_CITATIONS["registry_checks"],
        )
        project_owner = self.reference.rappid_parts(stream_id)["owner"]
        workspace_owner = self.reference.rappid_parts(
            self.world_identity()["rappid"]
        )["owner"]
        owner_ok = project_owner == workspace_owner
        finding(
            "workspace-project-owner-binding",
            owner_ok,
            (
                f"native Projects minted owner {project_owner!r}; private Workspace "
                f"owner is {workspace_owner!r}"
            ),
            severity="blocker" if not owner_ok else "info",
            source=SOURCE_CITATIONS["projects_store"],
        )
        try:
            entropy = self._mint_input(project)
            canonical_mint = stream_id.rsplit(":", 1)[1] == self.reference.Hb(
                "rapp/1:rappid", entropy,
            )
            mint_detail = (
                "The recorded UUIDv4 input reproduces the native project's exact identity tail."
                if canonical_mint else
                "The recorded UUIDv4 input does not reproduce the project identity tail."
            )
        except (OSError, FrameworkError) as error:
            canonical_mint = False
            mint_detail = str(error)
        finding(
            "canonical-keyless-mint-profile",
            canonical_mint,
            mint_detail,
            severity="blocker" if not canonical_mint else "info",
            source=SOURCE_CITATIONS["projects_sdk_profile"],
        )
        egg_path = store.project_path(project) / "PROJECT.egg"
        egg_ok, egg_step, egg_reason = self.reference.verify_egg(
            egg_path.read_bytes()
        )
        finding(
            "canonical-project-egg",
            egg_ok,
            (
                "native PROJECT.egg passes the canonical verifier"
                if egg_ok
                else f"{egg_step}: {egg_reason}"
            ),
            severity="blocker" if not egg_ok else "info",
            source=SOURCE_CITATIONS["projects_sdk_egg"],
        )
        variant_ok = bool(
            registry is not None
            and registry.egg_variants.get("organism")
            and not registry.egg_variants["organism"]["deprecated"]
        )
        finding(
            "registered-organism-variant",
            variant_ok,
            "organism is a live signed-registry egg variant",
            severity="blocker" if not variant_ok else "info",
            source=SOURCE_CITATIONS["signed_registry"],
        )
        finding(
            "workspace-project-writer-compatibility",
            False,
            (
                "contained: Workspace append_frame.py can append structurally valid "
                "minimal actor/event payloads that current Projects rejects; this "
                "adapter never enables that writer and Projects is the sole chain writer"
            ),
            severity="gap",
            source=SOURCE_CITATIONS["workspace_writer"],
        )
        finding(
            "native-human-gate-enforcement",
            False,
            (
                "contained: Projects stores human_gates and stop_conditions but cycle "
                "validation enforces only lease, count, time, may, and never; this "
                "adapter requires explicit approval for policy changes"
            ),
            severity="gap",
            source=SOURCE_CITATIONS["projects_policy"],
        )
        absolute_receipts = []
        for frame in frames:
            payload = frame.get("payload")
            if not isinstance(payload, Mapping):
                continue
            for field in ("artifacts", "receipts"):
                values = payload.get(field)
                if not isinstance(values, list):
                    continue
                absolute_receipts.extend(
                    item.get("path")
                    for item in values
                    if isinstance(item, Mapping)
                    and isinstance(item.get("path"), str)
                    and Path(item["path"]).is_absolute()
                )
        finding(
            "private-receipt-locators",
            not absolute_receipts,
            (
                "native project frames retain absolute local receipt paths inside the "
                "local PROJECT.egg; keep the cell local until an opaque-locator profile exists"
                if absolute_receipts
                else "no absolute receipt locators were observed"
            ),
            severity="gap" if absolute_receipts else "info",
            source=SOURCE_CITATIONS["projects_store"],
        )
        blockers = [
            item["code"]
            for item in findings
            if item["severity"] == "blocker" and not item["ok"]
        ]
        return {
            "ready": not blockers,
            "blocked_by": blockers,
            "findings": findings,
            "authority": {
                "accepted_commit": RAPP1_ACCEPTED_COMMIT,
                "reference_tools_commit": RAPP1_TOOLS_COMMIT,
                "head_frame_hash": RAPP1_HEAD,
                "normative_sha256": RAPP1_NORMATIVE_SHA256,
                "registry_seq": REGISTRY_SEQ,
                "estate_owner": ESTATE_OWNER,
            },
        }

    def require_activation(self, project: str) -> dict[str, object]:
        status = self.activation_status(project)
        if not status["ready"]:
            raise ActivationRefused(
                "activation refused: " + ", ".join(status["blocked_by"])
            )
        return status

    def inspect(self, project: str) -> dict[str, object]:
        store = self.project_store()
        state = self._state(project)
        frames = store.frames(project)
        project_path = store.project_path(project)
        resume = store.resume(project) if state.get("checkpoint") else None
        approvals_path = self.projects_root / "model-context-approvals.json"
        approvals = _read_json(approvals_path) if approvals_path.exists() else {}
        return {
            "workspace": {
                "root": str(self.root),
                "identity": self.world_identity(),
                "projects_root": str(self.projects_root),
            },
            "ownership": {
                "world_and_store": "rapp-workspace/1.1",
                "project_cell_lease_policy_cycle": "rapp-projects/1",
                "workspace_reference_writer_enabled": False,
            },
            "project": {
                "slug": project,
                "identity": _read_json(project_path / "rappid.json"),
                "stream_id": frames[0]["stream_id"],
                "genesis": {
                    "frame_hash": frames[0]["frame_hash"],
                    "payload_hash": frames[0]["payload_hash"],
                },
                "head": {
                    "seq": frames[-1]["seq"],
                    "frame_hash": frames[-1]["frame_hash"],
                    "payload_hash": frames[-1]["payload_hash"],
                },
                "state": state,
                "policy": state.get("cell_policy"),
                "completed_cycles": len(state.get("cell_cycles") or []),
                "egg": str(project_path / "PROJECT.egg"),
                "resume": resume,
                "board": str(self.projects_root / "BOARD.md"),
                "catchup": str(self.projects_root / "CATCHUP.md"),
                "model_context_approved": approvals.get(project) == "local",
            },
            "activation": self.activation_status(project),
            "source_pins": self.source_pins,
            "source_citations": SOURCE_CITATIONS,
        }

    def herdr_estate_plan(
        self,
        *,
        inventory_roots: Iterable[str | Path],
        session: str = "rapp1-workbench",
        herdr_bin: str = "herdr",
        rapp_herdr_bin: str = "rapp-herdr",
        manifest_path: str | Path | None = None,
    ) -> dict[str, object]:
        roots = []
        for value in inventory_roots:
            path = Path(value).expanduser()
            if not path.is_absolute():
                raise FrameworkError("Herdr inventory roots must be explicit paths")
            if path.is_symlink() or not path.is_dir():
                raise FrameworkError(f"Herdr inventory root is unavailable: {path}")
            roots.append(str(path.resolve()))
        if not roots:
            return {
                "created": False,
                "reason": (
                    "omitted: no actual Twin inventory root was supplied; worktree "
                    "panes and creature files are not Twin brainstems"
                ),
            }
        if self.sources.herdr is None:
            raise FrameworkError("an explicit pinned rapp-herdr checkout is required")
        estate_source = self.sources.herdr / "src"
        _import_package("rapp_herdr", estate_source)
        with _path_prefix(estate_source):
            estate_module = importlib.import_module("rapp_herdr.estate")
        destination = (
            Path(manifest_path).expanduser().resolve()
            if manifest_path is not None
            else self.root / "operator" / "rapp-herdr-estate.json"
        )
        if not destination.is_relative_to(self.root):
            raise FrameworkError("Herdr operator config must stay inside the private world")
        value = {
            "schema": "rapp-herdr-estate/1.0",
            "name": f"{self.world_identity()['name']} operator view",
            "devices": [
                {
                    "id": "local",
                    "enabled": False,
                    "transport": "local",
                    "os": "posix",
                    "session": _text(session, "Herdr session"),
                    "herdr_bin": _text(herdr_bin, "Herdr binary"),
                    "rapp_herdr_bin": _text(
                        rapp_herdr_bin,
                        "rapp-herdr binary",
                    ),
                    "inventory_roots": roots,
                    "catalog_roots": [],
                    "audit_roots": [],
                    "neighborhoods": [],
                    "note": (
                        "Plan-only inventory. Omarchy worktree panes and multiple "
                        "creature agents on one Brainstem are not Twin memberships."
                    ),
                }
            ],
        }
        created = not destination.exists()
        if not created:
            if _read_json(destination) != value:
                raise FrameworkError("existing Herdr operator config differs; not overwritten")
        else:
            _atomic_json(destination, value)
        estate = estate_module.load_estate(destination)
        plan = estate_module.EstateManager(estate).plan()
        return {
            "created": created,
            "manifest": str(destination),
            "plan": plan,
            "launched": False,
            "altered_existing_session": False,
            "worktree_panes_are_twins": False,
        }


__all__ = [
    "ActivationRefused",
    "FrameworkError",
    "NativeSources",
    "SOURCE_CITATIONS",
    "WorkbenchFrameworks",
]
