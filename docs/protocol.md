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
  craft: [agents/x]      # agent: required (lint) — referenced, never embedded
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

## Versioning

A flow's identity is the content hash of its compiled `.json` twin.
Editing the YAML and recompiling produces a new hash; runs journal the
hash they were driven by, so cohorts in the eval are attributable to
an exact protocol instance. The YAML file is the only durable asset —
the runtime is replaceable.
