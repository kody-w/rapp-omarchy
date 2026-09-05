# RAPP Omarchy

A standalone, experimental workbench for persistent, privately reachable work on Omarchy. Herdr owns terminals and attention; Git worktrees isolate changes; RAPP Workspace owns the private world; native RAPP Projects owns project frames, checkpoints, leases and bounded review policy.

This project lives in [`kody-w/rapp-omarchy`](https://github.com/kody-w/rapp-omarchy), independently of AIBAST. It does not modify the AIBAST application, its catalog or its default installer. The creature terrarium is a separate capability, not bundled into this repository.

**The native workbench is usable. Accepted RAPP/1 inference is deliberately held.** The current signed registry lacks the required registrations, the native Projects/SDK pins expose interoperability defects, and the foundation facade has no reviewed inference adapter. A successful candidate review is not an accepted loop cycle.

Read [WORKSPACE_STANDARD.md](WORKSPACE_STANDARD.md) for the transcript-grounded rationale and [RAPP1-GAPS.md](RAPP1-GAPS.md) for reproductions, remedies and upstream patch status.

```bash
git clone https://github.com/kody-w/rapp-omarchy.git
cd rapp-omarchy
```

## Operator entry points

The installed Mac connector is:

```bash
omarchy-workbench
```

It reads the private `~/.config/omarchy-rapp1-workbench/client.json`, uses the existing pinned SSH identity and known-hosts file, and attaches to the named `rapp1-workbench` session. It accepts only Tailnet addresses or full `.ts.net` names. Omarchy's current detach sequence is `Ctrl+Space`, then `d`.

Inside the owned Omarchy control pane:

```bash
cd "$HOME/.local/share/omarchy-rapp1-workbench"
venv/bin/python workbench.py status
```

The profile has sixteen prepared worktree lanes, a control tab, a DHH-inspired review tab and an evidence tab. Preparing lanes starts no coding models. The bounded canary is a separate, explicitly requested model process; if Copilot asks for folder trust, the human must decide. No startup permission is automatically approved.

## Private state and recovery

| Location on Omarchy | Meaning |
| --- | --- |
| `~/.local/share/omarchy-rapp1-workbench/layout.json` | Actual opaque Herdr identifiers and worktree bindings |
| `.../workspace/rappid.json` | Mint-once private Workspace identity and `world_id` |
| `.../workspace/rapp-projects/projects/omarchy-workbench-standardization/frames/` | Authoritative native project frames |
| `.../workspace/rapp-projects/BOARD.md` and `CATCHUP.md` | Rebuildable native projections |
| `.../workspace/rapp-projects/projects/omarchy-workbench-standardization/docs/RESUME.md` | Native checkpoint/resume instructions |
| `.../workspace/mint-inputs/` | Local UUIDv4 producer receipts; not a project ledger or authority |
| `.../workspace/worktree-observations/` | Immutable all-lane branch/HEAD/dirty-path snapshots referenced by native checkpoints |
| `~/.local/state/omarchy-rapp1-workbench/protocol/` | Candidate body/memory genesis, unsigned approval request and registry high-water |
| `~/.local/state/omarchy-rapp1-workbench/facade.sqlite3` | Independent facade sessions and idempotency |
| `~/.local/state/omarchy-rapp1-workbench/readiness.json` | Current readiness projection; never a completed-review receipt |

These roots are private. Do not commit their contents, exported native project eggs, connection configuration or receipt locators. The native Projects pin includes absolute artifact paths in its local metadata even though it excludes artifact bodies.

SSH disconnection does not stop Herdr's hosted processes. Reboot recovery is different: layouts/checkpoints may be restored, but live processes are not claimed to survive an operating-system restart. Do not use the Workspace reference writer on a Projects chain; the two pinned payload profiles are incompatible.

## Services and the held review policy

The user service `omarchy-rapp1-facade.service` verifies the foundation commit, tracked cleanliness and facade source hash before running the unchanged launcher, with its SQLite database outside the existing Brainstem. It listens only at `127.0.0.1:7073`, advertises pre-acceptance, and refuses inference. It neither forwards to nor imports the existing Grail.

The native Projects policy permits at most ten changed-input review cycles, with thirty-minute opportunities and a 240-second per-cycle bound. It permits read/test/draft activity, not source changes, signing, merging, publishing, deployment, purchases or network changes. The reviewer is a **DHH-inspired simulation**, not DHH or an endorsement.

Explicit preparation renews an expired lease only for the same recorded actor; it never takes over a foreign actor. The review wrapper serializes its composite native writes and recovers interrupted cycle/status/verification sequences from the existing native frames. It does not introduce another project ledger or distributed lease. Review inputs must be immutable, versioned receipt files: overwriting old evidence invalidates its historical hashes and is surfaced as a failure.

`omarchy-rapp1-readiness.timer` is a separate, network-isolated readiness observer. It makes no model calls and records no `cell.cycle`; it does not consume the ten-review budget or mean that the critic is running. The facade cannot be activated by setting an environment variable or flipping a label.

```bash
systemctl --user status omarchy-rapp1-facade.service --no-pager
systemctl --user list-timers --all --no-pager omarchy-rapp1-readiness.timer
systemctl --user stop omarchy-rapp1-readiness.timer
```

To remove only this profile's automatic services, disable its two named units. Do not stop the user's default Herdr server or delete the private project history:

```bash
systemctl --user disable --now omarchy-rapp1-readiness.timer
systemctl --user disable --now omarchy-rapp1-facade.service
```

## Reproducing the profile on another approved host

This is an installation profile, not a replacement Brainstem bootstrap. First establish the private host, pinned SSH trust, existing Herdr and an independent Copilot/GitHub CLI account. Never copy a private key into this repository or into another machine to make an example command work.

Use a new dedicated root. Place the public source checkouts below its `dependencies/` directory at these exact pins:

| Directory | Repository | Commit |
| --- | --- | --- |
| `rapp-1` | `kody-w/rapp-1` | `eb50008011447f5e69372ac22a1755f0978d15ed` |
| `rapp-map` | `kody-w/rapp-map` | `95e2f7290886e2de591fc78e4fb6e14b83435381` |
| `RAPP` | `kody-w/RAPP` | `4084c0e4adb05d0977799ac14fd93fe2424d495d` |
| `rapp-projects` | `kody-w/rapp-projects` | `2b375029d051b80b4df8c19749aeb64a96df216a` |
| `rapp-workspace` | `kody-w/rapp-workspace` | `4e194d90cdd34d7ba050b24781fddff971cdb7b5` |
| `rapp-sdk` | `kody-w/rapp-sdk` | `402a7e0210b2c4e71d0a1b44744b842f3c2d6b49` |
| `rapp-herdr` | `kody-w/rapp-herdr` | `e75b9b32d68cd7d37ee595b528136cb6c0ec7902` |

Copy this repository's root Python files and `requirements.txt` into the dedicated runtime root. Create its own `venv`, install `requirements.txt`, and prepare a separate Omarchy source checkout at `sources/omarchy`. Keep the source checkout separate from this private runtime state. From a **genuine terminal inside the named Herdr session**, with that runtime root as the working directory:

```bash
venv/bin/python herdr_bootstrap.py --root "$PWD" --lanes 16
venv/bin/python workbench.py prepare
```

Never spoof `HERDR_ENV`. The bootstrap verifies its real native caller, records Herdr's returned IDs, uses `--no-focus`, and refuses a conflicting existing layout. Repeating preparation preserves existing identities and checkpoints.

The supplied user units assume the default profile root and state path. Inspect them before installing under `~/.config/systemd/user/`; do not overwrite unrelated units. This profile deliberately retains the known upstream pins so incompatibilities remain reproducible. The patch bundle is for review, not an automatically applied fork.

## Portability boundary

`protocol.pack_application()` uses the pinned canonical packer and restricts files to the permitted rapplication layout. A legacy creature export may be retained byte-for-byte as `state/legacy-creature-egg.json`; its floating-point scores are application data, not a RAPP envelope.

The resulting container does not relabel the inner `rapp-creature/egg/3` format, activate its embedded code, assert sentience or invent lineage. The live Brainstem creature and the dormant application artifact have separate identities. The native `rapp-herdr` estate planner is used only for real supplied Twin inventories; ordinary coding lanes are never invented Twins.

## Focused checks

The ordinary unit tests do not require a VM or signer. Install the existing test dependencies with `python -m pip install -r requirements-dev.txt`. For the pinned integration cases, set `RAPP1_REFERENCE_DIR`, `RAPP1_REGISTRY_PATH` and `RAPP_WORKBENCH_NATIVE_SOURCES` to the checkouts in the table. Their local defaults are `vendor/rapp-1`, `vendor/rapp-map/ecosystem-spec.json` and `vendor/`. Missing external reference checkouts skip those cases explicitly; supplying mismatched checkouts fails. CI checks out those exact public pins and runs the integration cases.

```bash
python -m pytest -q tests
```

Positive signature-gate fixtures are explicitly synthetic unit tests. They are not operator signatures or evidence of production activation.

## Provenance

The workbench was extracted from its [original experimental implementation](https://github.com/kody-w/aibast-agents-library/commit/9b657a064444c387f52567fbd9db6474b6b46b3e). The existing MIT notice is preserved in [LICENSE](LICENSE). No AIBAST application code or private installed state is included.
