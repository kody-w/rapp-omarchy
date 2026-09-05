# RAPP/1 workbench interoperability findings

**Status: reproducible implementation/authority findings and proposed patches, not global ratification.** No normative specification, signed registry or frozen Grail was changed. The upstream patch bundle is prepared for review; it is not automatically applied to the running reference profile.

The workbench itself is operating. Its RAPP/1 inference/review activation is held rather than relabeled as compliant. This document separates operational prerequisites, implementation defects and specification ambiguities.

## Immutable reference points

| Component | Pin |
| --- | --- |
| Accepted RAPP/1 checkpoint | `kody-w/rapp-1@9a129ab59376b55dfe9b2c4ee089f5f4b630617c` |
| Selected authority frame | `83ca275f35cca96e43d75c99d338326c1a39b2240eabf57eb7c29ac96cc90818` |
| Normative text | SHA-256 `348e7d5baa94aaf2ce4c5354f3cb261f389298a04af65e271a686d3b62f7c384`, 79,692 bytes |
| Reference tools | `kody-w/rapp-1@eb50008011447f5e69372ac22a1755f0978d15ed` |
| Signed registry, sequence 2 | `kody-w/rapp-map@95e2f7290886e2de591fc78e4fb6e14b83435381` |
| Foundation facade/core | `kody-w/RAPP@4084c0e4adb05d0977799ac14fd93fe2424d495d` |
| Native Projects | `kody-w/rapp-projects@2b375029d051b80b4df8c19749aeb64a96df216a` |
| Native Projects SDK | `kody-w/rapp-sdk@402a7e0210b2c4e71d0a1b44744b842f3c2d6b49` |
| Native Workspace | `kody-w/rapp-workspace@4e194d90cdd34d7ba050b24781fddff971cdb7b5` |

The out-of-band estate-owner public anchor is pinned in `protocol.py`. A branch name, revision banner, unsigned proposal, ordinary HTTP success or hash-locked skill is not a substitute for that authority.

## Findings and disposition

| ID | Category | Observed gap | Local disposition |
| --- | --- | --- | --- |
| G01 | Authority prerequisite | Sequence 2 lacks five facade error codes and the new body, critic and project genesis registrations. | Emit an unsigned, exact proposal; preserve registry high-water; refuse activation. Real owner signing/publication remains required. |
| G02 | Runtime/adapter acceptance | The existing Brainstem wire differs from section 8; the independent facade has no reviewed inference adapter. A tool-free CLI rehearsal does not satisfy that missing approval. | Preserve the Grail. Run the unchanged loopback facade in refusal mode. No accepted model-review loop is running. |
| G03 | Reference implementation | `verify_egg()` accepts rapplication files outside the closed layout. | Enforce layout in the workbench wrapper; upstream reference patch and regression vectors prepared. |
| G04 | Reference implementation | `Registry.protocols` selects the first, deprecated protocol entry. | Inspect the exact active raw entry locally; upstream active-entry selection and ambiguity-refusal patch prepared. |
| G05 | Specification/implementation ambiguity | Reference and foundation ZIP encoders disagree on unspecified central-directory metadata for an identical manifest. | Use the pinned reference encoder for new workbench artifacts; do not claim cross-encoder byte parity. Request a normative byte-profile decision. |
| G06 | Native SDK implementation | `ZipInfo.flag_bits |= 0x800` is cleared by Python for ASCII names when writing native project eggs. | Keep native eggs private and reject canonical acceptance. SDK UTF-8 filename-encoding patch prepared. |
| G07 | Native Projects implementation | New identities use the synthetic owner `rapp-projects` and a default 32-byte random seed instead of the declared owner and UUIDv4 input. | Supply and record UUIDv4 input locally; still reject owner mismatch. Native owner-bound UUIDv4 patch prepared without rewriting existing histories. |
| G08 | Framework composition | Workspace's generic writer can append a frame that native Projects cannot fold. The two writer/lease profiles are not interchangeable. | Projects is the sole project writer/lease authority; Workspace remains SOLO/private. Hive/shared-chain writing is disabled. |
| G09 | Execution-policy boundary | Native `human_gates` and `stop_conditions` are stored declarations; they are not themselves execution controls. | Enforce the no-effect boundary in the invoking runtime. The installed readiness observer is network-isolated and makes no model calls. |
| G10 | Private artifact portability | Native project eggs exclude artifact bodies but can retain absolute receipt paths. | Do not publish these eggs or private project state. An opaque-locator export/import profile needs upstream design. |
| G11 | Stale implementation/projection | Foundation core has six variants and omits `sealed`; visible authority/version labels and the older installed Projects skill differ from the current pins. | Pin actual sources and selected authority bytes. Do not rewrite the installed generated skill, claim unsupported variants, or use a stale banner as authority. |
| G12 | Migration implementation | Legacy repacking derives identities from names/content, can emit a placeholder invite signature, and moves extra code into illegal `src/`. | Do not use it for live history. Upstream fail-closed migration patch prepared; preserve creature data in an opaque `state/` file instead. |
| G13 | Reference implementation scope | The compact reference canonicalizer rejects floating-point JSON values even though the full section 4 profile permits representable binary64 values. | Control frames use the supported subset; facade parsing uses its full-JCS core. Legacy floating-point scores remain unchanged application bytes, not frame payloads. No general canonicalizer-conformance claim is made. |

## G01: registration is an owner operation

The authenticated [sequence-2 registry](https://github.com/kody-w/rapp-map/blob/95e2f7290886e2de591fc78e4fb6e14b83435381/ecosystem-spec.json) includes `unknown-session` and `kernel-drift`, but not:

```text
malformed-request
idempotency-in-progress
session-in-progress
inference-refused
facade-storage-refused
```

`protocol.prepare()` verifies the current signature and selected checkpoint, mints a keyless workbench identity once, creates exact body/critic candidate genesis frames, and saves a seven-entry registry-addition proposal with `sig:null`. Native project registration is a separate explicit addition after its identity/encoding defects are resolved. These drafts are private operator artifacts, not this public report.

`activation_status()` remains false against the actual sequence-2 registry. Positive unit fixtures are clearly labeled synthetic signature bypasses and are never deployed. The existing global signer requires an explicit owner-held key path; no signer path was configured, no private shares were searched or reconstructed, and no substitute estate-owner key was minted.

## G02: a conformant response shape is not an accepted runtime

The observed legacy Brainstem returns extra top-level fields and string-valued `agent_logs`; an existing asynchronous workbench capability also returned a coroutine through its synchronous caller. Those observations belong to that installed runtime, not a claim that all current RAPP implementations behave that way.

The [foundation facade contract](https://github.com/kody-w/RAPP/blob/4084c0e4adb05d0977799ac14fd93fe2424d495d/rapp_brainstem/RAPP1_FACADE.md) explicitly forbids using Grail agents, credentials or telemetry as an inference shortcut and requires a separately reviewed, side-effect-free adapter. It advertises pre-acceptance. The workbench deploys those bytes unchanged, with separate SQLite persistence:

```json
{"status":"pre-acceptance","authenticated":false,"fully_conformant":false}
```

A real request received HTTP 422 and exactly:

```json
{"error":{"code":"inference-refused","step":null}}
```

The DHH-inspired tool-free CLI candidate uses independent GitHub CLI authentication and was rehearsed once. It is not installed as the facade adapter. Its success was not retroactively inserted into accepted review history.

## G03-G04: reference verifier and authority-selection defects

[Rapplication viability](https://github.com/kody-w/rapp-1/blob/eb50008011447f5e69372ac22a1755f0978d15ed/rapp.py#L540-L548) only counts root Python files. Starting with valid `agent.py` and matching `rappid.json`, adding `outside.txt` or `src/helper.py` still returns `(True, None, "ok")`. Section 9.2 permits only those two roots, optional `ui.html`, and files below `state/`.

[Registry construction](https://github.com/kody-w/rapp-1/blob/eb50008011447f5e69372ac22a1755f0978d15ed/rapp_registry.py#L237-L280) uses `setdefault` for protocol entries. The actual signed sequence-2 registry therefore exposes the deprecated pin through `registry.protocols["rapp/1"]`, while its raw entries also contain the current active pin.

`upstream/rapp-1-interop.patch` adds closed-layout rejection and selects only an unambiguous non-deprecated protocol entry. Deprecated history remains available through `entries`. Existing reference conformance and operational runners cover the fixes; no anchor or normative file is changed.

## G05-G06: ZIP bytes, not merely ZIP contents

Using the same RAPPID, timestamp, payload and rapplication files with the two pinned packers produced:

| Property | `rapp.py` | Foundation `rapp1_core.egg` |
| --- | --- | --- |
| Manifest and egg address | Identical | Identical |
| Archive length in the reproduction | 872 bytes | 872 bytes |
| `create_system` | `3` | `0` |
| `create_version` / `extract_version` | `20` / `20` | `20` / `20` |
| `external_attr` | `25165824` | `0` |
| UTF-8 flag | `2048` | `2048` |
| Accepts the other's output | Yes | No: `invalid-zip-metadata` |

Section 9.1 fixes order, compression, timestamps, extra fields and UTF-8, but does not fully select these central-directory fields while also promising byte-identical output. Do not arbitrarily rewrite existing eggs to choose a winner. A normative resolution should fix every header field and add an exact-byte cross-implementation fixture.

The native SDK has a different, unambiguous defect: its [project packer](https://github.com/kody-w/rapp-sdk/blob/402a7e0210b2c4e71d0a1b44744b842f3c2d6b49/src/rapp_sdk/projects.py#L1189-L1207) sets a flag that `zipfile` subsequently clears for ASCII names. The real native project egg fails the canonical reader with `ZIP local and central UTF-8 flags must match exactly`.

`upstream/rapp-sdk-utf8.patch` uses the same filename-encoding override as the pinned canonical reference and asserts bit 11 in both local and central headers. It does not pretend to settle G05.

## G07-G10: use native frameworks without conflating their contracts

[Native Projects creation](https://github.com/kody-w/rapp-projects/blob/2b375029d051b80b4df8c19749aeb64a96df216a/src/rapp_projects/core.py#L468-L517) passes the literal owner `rapp-projects` and `entropy or os.urandom(32)` to the SDK. `owner="kody-w"` therefore changes the payload's display owner but not its identity namespace.

`upstream/rapp-projects-identity.patch` uses the declared lowercase owner and UUIDv4 input for new projects, validates explicit entropy before creating a project, and leaves existing identities untouched. The workbench wrapper's local UUIDv4 receipt reproduces its native identity tail, avoiding the separate mistake of inferring mint provenance from an opaque hash. The running baseline still refuses its synthetic-owner mismatch.

After that native patch is reviewed, use an explicit new cell/transfer preserving the old candidate's history; do not edit its `rappid.json` or rewrite old frames in place.

The controlled writer-composition reproduction is `test_workspace_reference_writer_and_current_projects_profile_conflict_safely`: Workspace [append_frame.py](https://github.com/kody-w/rapp-workspace/blob/4e194d90cdd34d7ba050b24781fddff971cdb7b5/tools/append_frame.py#L148-L235) appends a minimal `work.status` payload; native Projects then refuses missing required fields. Each component's individual integrity check is insufficient to establish semantic compatibility.

The native [policy/cycle implementation](https://github.com/kody-w/rapp-projects/blob/2b375029d051b80b4df8c19749aeb64a96df216a/src/rapp_projects/core.py#L992-L1128) enforces lease, declared action classes, elapsed-time and count budgets. Arbitrary human-gate/stop-condition strings are not machine-enforced authorization rules. The profile contains this gap by not granting execution authority to the observer.

Native receipt data can contain absolute paths. `test_native_layout_policy_due_cycle_and_receipts_are_thin` demonstrates that artifact bodies are not copied while path metadata remains. Keep the world and eggs private; fixing that requires a shared opaque-locator and re-binding contract, not a cosmetic path replacement after hashing.

## G11-G13: preserve boundaries instead of changing labels

The foundation [egg variant set](https://github.com/kody-w/RAPP/blob/4084c0e4adb05d0977799ac14fd93fe2424d495d/rapp1_core/egg.py#L26-L31) omits `sealed`. Its old authority descriptor and the installed hash-locked Projects skill are distinct versions from the current native repositories. A successful checksum preflight is not proof of currency or registry acceptance.

At the pinned baseline, two legacy session inputs with the same slug and different transcripts get the same derived RAPPID from [egg_repack.py](https://github.com/kody-w/rapp-1/blob/eb50008011447f5e69372ac22a1755f0978d15ed/egg_repack.py). A legacy neighborhood pointer emits `MIGRATED-UNSIGNED-legacy-pointer` as its signature. Extra Python files are moved to `src/`, outside the rapplication layout.

The migration portion of `upstream/rapp-1-interop.patch` instead requires an explicit mint-once identity when none can be preserved, rejects replacement of an existing canonical identity, refuses unsigned invite reissuance, refuses ambiguous agent selection/invalid output, and verifies before creating a new output file. It never emits a fake signature. Some legacy inputs need a provenance-preserving wrapper rather than automatic conversion.

The compact [reference canonicalizer](https://github.com/kody-w/rapp-1/blob/eb50008011447f5e69372ac22a1755f0978d15ed/rapp.py#L32-L64) raises `floats require full-JCS number serialization; use ints/strings` for `canonical({"energy": 1.25})`. A migration wrapper initially applied that parser to opaque legacy state and was corrected locally. The actual Moss export, including floating-point scores, was preserved byte-for-byte inside a canonical rapplication container:

```text
legacy bytes SHA-256: 7be07207ffa223384cc2a026e4eba5524426aae0af84688197b624ea2d6538f1
archive paths: agent.py, rappid.json, state/legacy-creature-egg.json
inner format: rapp-creature/egg/3, unchanged
claim: container conformance only; embedded code not activated or approved
```

## Reproducing the proposed patches

Apply each patch only to an isolated checkout at its matching baseline, never to the live pinned dependencies:

```bash
git apply --check /path/to/upstream/rapp-1-interop.patch
git apply /path/to/upstream/rapp-1-interop.patch
python3 conformance.py
python3 parity_check.py
python3 operations_conformance.py
```

The corresponding native runners are:

```bash
# In the isolated SDK checkout after applying rapp-sdk-utf8.patch:
PYTHONPATH=src python3 -m unittest discover -s tests -p test_projects.py

# In the isolated Projects checkout after applying rapp-projects-identity.patch:
PYTHONPATH="src:/path/to/pinned-rapp-sdk/src" python -m pytest -q tests/test_store.py tests/test_egg.py tests/test_cli_and_agent.py
```

The profile's own tests and required source environment variables are documented in [README.md](README.md). Controlled fixtures cover the current real-signature negative gate separately from synthetic positive gate behavior.

## Remaining operator decisions

Complete the real folder-trust decision in the owned Herdr canary. Supply an existing approved signer interface for the exact registry additions, or explicitly design and approve a separate private estate; neither is inferred from access to SSH. Review the native patches and select updated pins with a history-preserving project transfer. Review an inference adapter against the facade's actual no-Grail/no-tools contract.

Only after those gates pass should the runtime perform a first accepted review and arm native due/cycle execution. The currently installed thirty-minute readiness observer is not that execution loop. Global submission of these findings and any normative revision remains a separate owner-reviewed step.
