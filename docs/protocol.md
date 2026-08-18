# Protocol — the rules, independent of implementation

This is the stable contract. The runtime ([runtime.md](runtime.md))
can be rewritten in any language; a flow file that satisfies this
document must keep working. Each rule names its enforcement layer —
**lint** (static, `flow-lint.py`), **runtime** (the walker/hook), or
**convention** (documented, candidate for future lint) — because a
rule whose enforcement is overstated would itself be an assertion.

## Node kinds

Three kinds, defined by `flow.schema.json` (Draft 2020-12, unknown
keys rejected):

```yaml
- id: kebab-case-id      # unique (lint)
  kind: agent            # agent | gate | human
  craft: [agents/x]      # agent: required (lint) — referenced, never
                         # embedded; must RESOLVE (lint --check-craft):
                         # project `.flow/craft/` first, then the
                         # plugin root, same order as a gate program
  in:  [spec.md]         # optional: declared inputs
  out: [plan.md]         # optional: declared outputs

- id: gate-x
  kind: gate
  run: "{cmd} {feature_dir}"   # required (lint); argv, no shell (runtime)

- id: decide
  kind: human
  out: [seal decide]     # convention: name the seal it yields for
```

## Edge grammar

An edge is `{from, to, when?}`. Conditions use a deliberately closed
grammar — **lint (I1)**:

```
<state key> <op> <literal>       ops: == != > >= < <= in
gate.exit == 0
risk in [A, B]
```

Forbidden, by design: `if this seems safe`, `if the task is complete`,
`if risk is low`. Prose conditions hide judgment; a condition either
evaluates or the walk blocks.

## Transition rules

| Transition | Status | Enforced by |
| --- | --- | --- |
| agent → agent / gate / human | allowed | — |
| agent → `__end__` | **forbidden** — agents never finish | lint (I2, FAIL) |
| gate → any declared node / `__end__` | allowed; every out-edge must consume `gate.exit` | lint (unconditional gate out-edge FAILs) |
| human → gate | the I4 pattern: the decision re-enters as a seal read by the gate | lint (any other human out-edge WARNs) |
| human → `__end__` | machine-legal, protocol-deprecated: a finish should read recorded evidence — route human → seal gate → `__end__` | lint (WARN) |
| any → `__human__` | deprecated absorbing state | lint (WARN) |
| node with no out-edge | **forbidden** — `__end__` is the only final state | lint (I4, FAIL) |
| several out-edges without `when` on all | **forbidden** — routing must be deterministic | lint (FAIL) |

Reachability is mandatory both ways: every node reachable from
`__start__`, and `__end__` reachable — **lint (FAIL)**.

## Completion semantics

The walker's verdict is an exit code, nothing else:

| Exit | Verdict | Meaning | Hook action |
| --- | --- | --- | --- |
| 0 | FINISHED | walk reached `__end__` | disarm (delete marker) |
| 1 | CONTINUE | walk landed on an agent node | block the stop, persist next node |
| 2 | BLOCKED | human node, or any configuration problem | allow the stop, keep the marker |

Fail-closed is a rule, not a style: an unknown node, an unbound
`{placeholder}`, an unmatched edge, a prose condition, or a gate
revisited within one walk all BLOCK — **runtime**. The walk never
guesses. Two dynamic guards bound every run: an iteration budget and a
dry-loop counter (progress unchanged across stops), both of which
disarm — **runtime**.

## Termination authority

I2, elevated to its real altitude: **agents have zero termination
authority.** Only two things may transition a flow into `__end__`:

- a **verified gate** — a command that ran and exited 0, on the
  evidence it was pointed at;
- a **recorded human decision** — a seal, read back by a gate
  (which reduces to the first case: the finish still enters through
  a gate; the human's authority is the record the gate reads).

Everything an agent produces — artifacts, checked boxes, transcripts,
routing proposals — is input to that authority, never the authority
itself. The one-line protocol: *agents produce work; verifiers produce
evidence; the flow derives state; only verified evidence can finish
delivery.* Enforced by the lint (I2 — no agent out-edge to `__end__`)
and exercised end-to-end in `tests/test_trust_boundary.py`.

## Convergence (I7)

Verification asks: is the implementation correct per the CURRENT
specification? Convergence asks: does the specification still
faithfully represent the ORIGINAL ask? Different claims, both required
to finish:

    gates establish that work satisfies a specification;
    convergence establishes that the specification still represents
    what was asked; only when both hold may the system finish.

Mechanically: a `gate-converge` node runs `converge-check.py`, which
verifies the ARTIFACT of a fresh-context convergence judgment — a
review whose verdict is CONVERGED, bound to sha256 of the ask file,
sha256 of the current spec, and the tree, signed by an identity that
is not the spec's author (`--not planner`). NOT_CONVERGED routes red
back to the plan with the missing items; revising the spec stales the
report by construction. Place it after the plan gate (cheapest catch
point) and optionally again before the finish (drift during
implementation). Empirical basis: runs 0002/0003 in `docs/runs.md` —
the same task, model and deliberately intent-lossy paperwork, with the
gate as the only variable; without it the road finished green around a
dropped deliverable, with it the loss was caught before any
implementation spend. **runtime (converge-check) + tests**

## Graph anchoring (I8)

The flow graph is the root of trust: the walker derives every decision
from the compiled twin, so an actor who can rewrite the twin owns
termination — demonstrated by run E13, where a hostile agent rerouted
`__start__ → __end__` and finished with no work done.

The fix draws a line between two phases:

    authoring       — the graph is mutable. An agent may brainstorm and
                      write any flow (a new pack, a site road). No
                      anchor exists; nothing is enforced.
    arming          — the authority transition. `flow-arm` compiles the
                      twin and writes an anchor: a git note keyed by the
                      twin's blob sha, into refs/notes/flow-anchor,
                      inside flow-arm's own process (the guard denies
                      agent-issued `git notes`, so the anchor cannot be
                      forged or removed by the documented path).
    armed execution — the graph is immutable. The walker recomputes the
                      twin's blob sha and BLOCKS any twin without a
                      matching anchor. Enforcement triggers on the
                      marker flag OR the mere presence of the anchor
                      ref, so dropping the flag cannot silently disable
                      it. To change the graph, re-arm — which resets to
                      `__start__`, re-anchors, and discards prior
                      evidence.

Honest scope: this closes SILENT mid-run mutation (the E13 attack). A
determined agent with shell can still disarm + rewrite + re-arm — but
that is loud, non-incremental, resets progress, and is equivalent to
"the operator armed a different flow", which is the authoring/arming
boundary working, not a bypass. Making *arming* itself require a human
credential is the next layer, deferred. **runtime (flow-arm anchor +
walker check) + tests (test_anchor_i8.py, the E13 matrix).**

## Failure semantics (I6)

Two different safeties, explicitly separated:

    FAIL-OPEN FOR INTERACTION — a broken harness must never trap a
    session. Any internal hook error allows the stop.

    FAIL-CLOSED FOR STATE — a crash can never produce evidence or
    advance the flow.

Concretely, every failure mode lands on the safe side of the line:

| Failure | Interaction | State |
| --- | --- | --- |
| hook crashes (bad marker, internal bug) | session continues | marker untouched, no evidence written |
| walker crashes or is missing | session continues | marker's node unchanged |
| gate program crashes at runtime | — | non-zero exit → the red edge |
| gate program missing / can't launch / times out | — | BLOCKED — never an exit code an edge could consume (a deleted seal program must not read as a human rejection) |
| journal write fails | session continues | journal is observability, never authority |

A hook failure may cost a loop iteration; it can never mint a green.
Enforced by `tests/test_trust_boundary.py` (crash cases) plus the
walker's BLOCK-on-config rule above.

## Evidence requirements

- A gate's evidence is its exit code, produced by executing its
  command — never by parsing an agent's transcript. **runtime**
- Task completion derives from attest records (`refs/notes/attest`)
  written by the tool that ran the check (I3). A SUITE attest must sit
  on the finishing HEAD with a clean worktree. **runtime (ledger)**
- Human decisions are seal records (`refs/notes/seal`) written on the
  human's explicit say-so and read back by a gate (I4). Resumption
  carries no information. **runtime (seal) + convention (say-so)**
- Deliver plans must carry a review cluster whose checks are attested
  independent review runs (I5). **convention + project plan gate**
- Every run appends a journal of gate exits and stop decisions;
  red exits exist nowhere else. **runtime (hook, fail-open)**

## Composition

A flow may derive from another — **lint**, resolved at compile time:

```yaml
flow: wp-plugin
version: 2
extends: deliver         # NAME (project pack first, then the roads)
remove: [brainstorm]     # nodes, and every edge that touches them
nodes: [...]             # merged by id: same id replaces, new appends
edges: [...]             # replaces the parent's edges FROM each source
                         # node the child mentions — one routing
                         # decision, one routing table
```

Two rules keep this from becoming a second protocol:

1. **The twin is flat.** `extends` is resolved by the lint before the
   twin is written, so the runtime has exactly one notion of what a
   flow is and the walker never learns composition exists. A derived
   flow costs the hook path nothing.
2. **The derived graph faces the whole lint** — reachability, dead
   ends, deterministic routing, I1/I2/I4. Composition cannot smuggle a
   node past an invariant; a `remove` that breaks the wiring fails
   statically, which is the only reason this is safe to offer at all.

`flow` and `version` always come from the child: a derived road is its
own road, with its own eval cohort.

## Versioning

A flow's identity is the content hash of its compiled `.json` twin.
Editing the YAML and recompiling produces a new hash; runs journal the
hash they were driven by, so cohorts in the eval are attributable to
an exact protocol instance. Because the twin is flattened, editing a
PARENT flow changes every derived flow's hash on the next compile —
correctly: the road really did change. The YAML file is the only
durable asset — the runtime is replaceable.
