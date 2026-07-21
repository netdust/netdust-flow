# Evidence — three terms, used precisely

The system's vocabulary is small and strict. Misusing it is how
workflow authority leaks back to the actor being checked.

## Assertion

A statement made by an actor.

- "Tests passed."
- "Security review completed."
- "The feature is done."
- A checked checkbox in tasks.md.

**Assertions are never workflow state.** Not the agent's (I3), not the
process's own inference — "the session resumed, so the human must have
approved" (I4), not the claim that declared craft was used (I5).

## Evidence

A recorded fact produced independently of the claimant.

- an exit code from an executed command
- an attest note written by the tool that ran the check
- a human seal recorded on the human's explicit say-so
- a journal event written by the hook

**Evidence changes state.** Nothing else does.

## State

The current workflow position, derived from evidence on request —
never maintained, never authored. The marker's node (persisted from
the walker's verdict), the ledger's answer (computed from attest
notes), a cohort's metrics (computed from journals).

The formula:

```
Assertion
    |
    v
Verification        (a gate runs the check itself)
    |
    v
Evidence            (recorded by the verifier)
    |
    v
State transition    (derived by the walker/ledger)
```

## The evidence stores

| Store | Written by | Read by | Contains |
| --- | --- | --- | --- |
| `refs/notes/attest` | `attest.py` (ran the check) | `ledger.py` | `{unit, cmd, exit, ts, tree}` per passed check |
| `refs/notes/seal` | `seal.py record` (human say-so) | `seal.py check` (a gate) | `{node, decision, ts, tree}` per human decision |
| `<fd>/.flow-journal.jsonl` | the Stop hook (fail-open) | `flow-eval.py` | every gate exit (red included) + stop decisions |
| `tasks/.harness-loop.json` | the hook | the hook | persisted machine position (marker) |

Freshness rules, stated honestly: per-unit attests prove a unit was
verified when built; a SUITE attest must sit on the finishing HEAD
with a clean worktree, so any later change forces re-verification.
Seals are latest-wins — an approval can go stale if the sealed
artifact changes without a re-seal (records carry the tree hash for
audit; stricter freshness is deferred until a drill shows a leak).

## The trust boundary

All four stores are tamper-resistant, not tamper-proof. An agent with
shell access could forge a note, rewrite the marker, or edit the
journal exactly as easily as checking a checkbox. The protocol's
answer is layered: the stores make honesty the path of least
resistance and every record auditable; a pretooluse guard should deny
agent writes to all four outright. Signing records would close the
rest and is deferred as ceremony until a drill shows a leak.
