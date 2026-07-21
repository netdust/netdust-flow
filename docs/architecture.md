# Architecture — the system model

netdust-flow is a finite-state delivery protocol where state changes
require evidence. Agents generate work; evidence advances state. This
document describes the model; [protocol.md](protocol.md) defines the
rules; [runtime.md](runtime.md) describes the implementation.

## The authority model

Every actor in the system has exactly one kind of authority, and no
actor holds two:

| Actor | May write | May never write |
| --- | --- | --- |
| Agent | artifacts (code, specs, plans) | evidence, state |
| Gate (verifier) | evidence (exit codes, attest notes) | artifacts it judges |
| Human | decisions, as recorded seals | state directly — a seal is read back by a gate |
| Walker | nothing — it derives | anything; it is stateless |

The separation is the whole design. An agent's statement about its own
work — "tests pass", "review done", a checked checkbox — is an
**assertion**, and assertions are never workflow state. State moves
only when a verifier records **evidence**: an exit code, an attest
note, a seal. See [evidence.md](evidence.md) for the three terms used
precisely.

```
Agent
  |
  v
Artifact
  |
  v
Verifier
  |
  v
Evidence
  |
  v
Workflow state
```

## Node types

- **agent** — does work. References craft (skills, subagents) by name;
  produces declared artifacts (`out:`). Landing here CONTINUES the
  loop: the driving session works the node, then stops, and the walker
  re-derives.
- **gate** — verifies work. Runs one command as argv; its exit code is
  written into walk state (`gate.exit`) and consumed by its out-edges.
  Gates are transient: resolved within a single walk.
- **human** — yields. Landing here BLOCKS the loop until a person
  records a decision (`seal.py record`); the gate after the node reads
  the seal back as an exit code. Resuming a session is never approval.

Two pseudo-states: `__start__` (entry, edges only) and `__end__` (the
only final state — reachable exclusively from gates and humans).

## Flow lifecycle

```
/flow arm            writes the marker (flow, node=__start__, binds)
   |
session stop  ──▶  Stop hook ──▶ walker walks from marker["node"]
   |                                |
   |          CONTINUE (agent) ─ block the stop, persist next node
   |          BLOCKED  (human) ─ allow the stop, keep the marker
   |          FINISHED (__end__) ─ delete the marker (disarm)
   |
every stop appends journal events (gate exits, stop decision)
   |
/flow eval           aggregates journals into cohorts by flow version
```

Termination is guaranteed twice over: statically (the lint enforces
reachability, deterministic routing, and finish-only-through-gate/human
— workflow-net soundness, van der Aalst 1997) and dynamically (the
hook's iteration budget and dry-loop counter disarm a loop that stops
progressing).

## State transitions

State lives in exactly two places, both derived, neither authored:

1. **Within one walk** — `gate.exit`, written by the walker after each
   gate execution, consumed by edge conditions in a closed grammar
   (`gate.exit == 0`; prose fails the lint).
2. **Across stops** — the marker's `node`, persisted by the hook from
   the walker's `next:` line; and delivery state, computed on request
   by `ledger.py` from attest notes reachable from HEAD.

Nothing is bookkept. If the evidence changes (a new commit, a revoked
attest, a rejection seal), the derived state changes with it.

## What is deliberately absent

Self-modifying workflows, agent-created graphs, autonomous policy
changes, and hidden completion heuristics — each would hand authority
back to the actor the design exists to check. The human measurement
loop ([evaluation.md](evaluation.md)) is not a limitation; it is part
of the architecture.
