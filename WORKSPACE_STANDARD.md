# RAPP Custom Workspace: Omarchy reference profile

Implementation home: [`kody-w/rapp-omarchy`](https://github.com/kody-w/rapp-omarchy). This is a standalone Omarchy workbench, not an AIBAST application feature or an Omarchy upstream fork.

**Status: candidate implementation profile, subordinate to RAPP/1 and the existing RAPP Workspace and RAPP Projects contracts.** This is not a new wire protocol, a new egg type, or a claim of global ratification.

## Why this is the right default for this workload

The optimization target is **verified useful work per hour of human attention**, subject to privacy, isolation, recoverability and protocol correctness. It is not the number of terminals, models, generated lines or tokens.

DHH's account supports this direction; it does not prove that sixteen agents are universally optimal. He describes roughly sixteen attention threads across four or five machines. His own ability to review and make decisions becomes the limit. The RAPP-specific mapping below is our engineering conclusion, not a statement or endorsement attributed to DHH.

| Public evidence | DHH's stated rationale | Consequence for this profile |
| --- | --- | --- |
| [Official transcript, 01:34:57](https://lexfridman.com/dhh-2-transcript/) | He prefers terminal-native work and terminal user interfaces. | Keep the operator in native Herdr rather than introduce another mandatory coding UI. |
| [01:35:40](https://lexfridman.com/dhh-2-transcript/) | Herdr exposes working agents and alerts him when one is ready for a human decision. | Optimize attention routing: show blocked, working and ready states from actual runtime evidence, never invented completion signals. |
| [01:36:35-01:37:26](https://lexfridman.com/dhh-2-transcript/) | Tailscale makes remote machines accessible like a local network without manually opening firewall holes. Comet KVMs provide a separate hardware-control layer. | Reuse private Tailscale/SSH transport. Do not expose a public shell or claim that SSH is out-of-band hardware KVM. |
| [01:38:09](https://lexfridman.com/dhh-2-transcript/) | More machines enable parallel work, but human processing capacity bounds useful concurrency. | Provision capacity, then tune active concurrency. Sixteen prepared lanes do not justify automatically launching sixteen paid agents. |
| [01:52:27-01:52:58](https://lexfridman.com/dhh-2-transcript/) | He values fast, beautiful systems that are a delight to use. | A repeatable workspace should remove setup and recovery friction, not add ceremony to every ordinary action. |

The resulting argument is causal: persistent sessions avoid needless restarts; attention signals reduce polling; private remote access makes compute location less important; isolated worktrees prevent accidental collisions; durable project records reduce the cost of resuming work in a different runtime. These advantages make this a strong default for the stated workflow. Comparative superiority remains a hypothesis to measure, not an authority claim.

## Reuse the existing RAPP layers

| Responsibility | Existing component | Boundary |
| --- | --- | --- |
| Private world, owner boundary, store and multi-operator rules | [`rapp-workspace`](https://github.com/kody-w/rapp-workspace/tree/4e194d90cdd34d7ba050b24781fddff971cdb7b5) | The workspace is the private world of work. Hive/distributed operation is explicit, not inferred from a shared folder. |
| Goals, actors, leases, checkpoints, receipts, resume prompts and bounded cell policy | [`rapp-projects`](https://github.com/kody-w/rapp-projects/tree/2b375029d051b80b4df8c19749aeb64a96df216a) | Project frames are authoritative; boards, indexes and resume views are derived. Do not build a competing project ledger or scheduler. |
| Native Projects frame and egg primitives | [`rapp-sdk`](https://github.com/kody-w/rapp-sdk/tree/402a7e0210b2c4e71d0a1b44744b842f3c2d6b49) | This is a real transitive dependency, not an assumed copy of the canonical RAPP/1 implementation. Its output is independently checked against the pinned reference. |
| Persistent terminals and attention | [Herdr](https://herdr.dev/docs/how-to-work/) | Herdr owns processes and terminal state. It is not the RAPP kernel or an LLM. |
| Native projection of actual Twin neighborhoods and estate topology | [`rapp-herdr`](https://github.com/kody-w/rapp-herdr/tree/e75b9b32d68cd7d37ee595b528136cb6c0ec7902) | Reuse real identities and membership. A coding pane is not automatically a Twin, and a creature file does not require its own Brainstem process. |
| Private transport | Tailscale and pinned-key SSH | Network membership does not replace workspace authorization, file permissions or artifact verification. |
| Interoperable identity, addresses, frames, wire and packages | [`rapp-1`](https://github.com/kody-w/rapp-1/tree/9a129ab59376b55dfe9b2c4ee089f5f4b630617c) | Import the canonical implementation; verify the accepted checkpoint and registry. Do not infer compliance from a filename or an ordinary HTTP 200. |

There must be **one authoritative project history and one effective writer lease**, not two incompatible tools writing to the same chain. The pinned Workspace reference writer was exercised against a native Projects fixture: it appended a structurally valid but semantically incomplete payload that Projects subsequently refused. This profile therefore uses Workspace's SOLO/private world boundary and Projects as the only project-chain writer and lease authority. Hive takeover is not enabled.

The older hash-locked `rar-kody-w-rapp-projects` skill is a distinct versioned projection. A successful hash preflight proves those bytes, not currency with the current native Projects implementation or current global RAPP/1 authority. The installed skill must not be silently rewritten or treated as proof of a newer protocol.

## The workspace unit

A standardized workspace binds:

1. One explicit private world and owner.
2. Native RAPP Projects cells, their identities, policies and verified histories.
3. A declared set of devices and private connection profiles.
4. A persistent Herdr session with owned, opaque workspace/tab/pane identifiers.
5. A dedicated Git worktree and branch for each concurrently mutating coding task.
6. Capabilities represented as portable userspace files; multiple capabilities may share one Brainstem.
7. An evidence surface showing real status, checkpoints, receipts and unresolved decisions.
8. A clearly labeled simulated DHH-inspired reviewer with no signing or release authority.
9. A verified RAPP/1 control boundary and properly packaged artifacts.
10. An explicit expansion and stop policy.

Machine addresses, SSH keys, credentials, customer content and private receipt locators stay in operator-local configuration or the private store. They do not become public project metadata or generic installation defaults.

## Review loop

The reviewer is a simulation informed by public engineering principles. It is not DHH, does not speak for him, and does not supply endorsement.

Use the native Projects cell policy/cycle mechanism rather than another bespoke job ledger. The prepared policy is review-only, at most ten changed-input reviews, with a thirty-minute opportunity interval and a 240-second per-cycle bound. Unchanged approved input receipts are skipped. Model input is an approved observation bundle, not arbitrary terminal scrollback. Native `human_gates` and `stop_conditions` are declarations, not an execution sandbox; the invoking runtime must enforce them before external effects.

The reviewer may explain strengths, identify evidence-backed concerns and queue a smallest next proposal. It cannot merge, publish, sign, purchase, change network exposure, or modify a running service. Source edits require a separately authorized worker in an isolated worktree. The loop stops or pauses on budget exhaustion, failed receipt/authority verification, missing required evidence, or completed goals.

## What scalability means

Scale by adding independently owned execution cells and private devices, not by adding shared mutable hidden state. A new runtime should resume a project from its verified checkpoint and receipts without reconstructing the task from a chat transcript.

Tune concurrency against measured human attention demand and machine capacity. Compare one, two, four, eight and sixteen active tasks only when there is enough useful work and an approved compute budget. Hold the acceptance standard constant. More output with more review failures is not an improvement.

Git worktrees isolate changes; they are not a security sandbox. Cooperative leases coordinate writers; they are not a substitute for operating-system isolation against hostile actors. A Tailscale connection encrypts transport; it does not authorize every peer to access every workspace.

## Acceptance gates

| Gate | Required evidence |
| --- | --- |
| Private access | A connection receipt for the intended host and pinned SSH key; no new public listener, Funnel or unrelated route changes. |
| Persistence | Disconnect and reconnect to the same owned session/terminal, with the same worktree and no cross-worktree changes. Reboot recovery claims must be demonstrated separately. |
| Attention | One real, bounded canary transitions from working to a recognized human-decision state. Do not manufacture agent status to make the test pass. |
| Project continuity | Native punch-in/checkpoint/resume/verification preserves identity, receipts and the next action after interruption. |
| Concurrency | One effective lease per mutable stream; competing writers, stale takeovers and divergent history fail safely. |
| Review discipline | The actual model has no mutation tools; the native cell policy enforces cadence, action classes, elapsed-time and cycle limits. |
| RAPP/1 wire | Exact success/error shapes, ignored unknown request fields, server-owned sessions and repeatable idempotency pass the reference checks. |
| RAPP/1 authority | The chosen registry signature, kind bindings, error codes and exact stream genesis records verify against an out-of-band owner anchor. |
| Portability | Canonical eggs preserve the permitted file layout, identities and bytes; legacy data is retained as data, not relabeled as a conformant artifact. |
| Kernel boundary | The deployed Grail's recorded bytes remain unchanged. |

The existing Omarchy installation already supplies Herdr. Its private SSH path already traverses the owner's Tailnet. Reusing those working pieces is preferable to installing redundant networking or maintaining a private Herdr fork.

## Standardization status

The native Herdr workbench, sixteen isolated worktree lanes, private Workspace world and native Projects checkpoint/policy are installed. A separate loopback facade is operating in its original fail-closed mode. A thirty-minute, network-isolated readiness observer runs without invoking a model or recording review cycles.

Accepted RAPP/1 review operation remains held. The owner-signed registry additions and reviewed facade inference adapter are unavailable; current native Projects and SDK output also expose owner-binding and egg-encoding defects. Isolated upstream-ready patches address the concrete implementation defects without rewriting deployed history. See [RAPP1-GAPS.md](RAPP1-GAPS.md).

The actual Herdr canary survived disconnection in its recorded worktree pane and reported `blocked` at Copilot's folder-trust dialog. That proves a real startup attention state, not a completed working-to-question cycle. No trust prompt was approved automatically. Reboot process survival and a first accepted model-review cycle have not been demonstrated.

No missing signature, stale projection or unregistered event is repaired by changing a label to “compliant.”
