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

## Tree identity

Evidence that matters answers five questions: **what tree** was
verified, **who/what** verified it, **what** was verified, **when**,
and **with what result**. Where each store stands:

| Evidence | WHAT tree | WHO verified | WHAT was verified | WHEN | RESULT |
| --- | --- | --- | --- | --- | --- |
| attest record | `tree` field (`HEAD^{tree}` at pass time) | `attest.py` running the named `cmd` | the `unit` | `ts` | recorded only on exit 0 |
| seal record | `tree` field; `--fresh` re-checks it against disk | the human, via `seal.py record` | the `node`'s decision | `ts` | `approved` / `rejected` |
| review evidence | `tree:` line in the report, checked against the CURRENT `HEAD^{tree}` by `review-check.py` | the report's required `reviewer:` line (recorded identity) + `attest.py` (the record) | the named review scope | attest `ts` | `VERDICT: CLEAN` only |
| journal event | not tree-bound | the Stop hook, relaying walker traces | gate exits, stop decisions | per-event `ts` | observability — **never authority** |
| marker | not tree-bound | the hook | machine position only | — | never evidence |

The rule the table encodes: everything that can advance or finish
delivery is tree-bound; the two rows that are not tree-bound have no
authority to advance anything. A review of yesterday's tree proves
nothing about today's (`review-check` refuses it); a seal from before
an edit goes stale (`--fresh` re-asks); an attest on a superseded HEAD
still counts for its unit but the SUITE attest must sit on the
finishing HEAD.

## The trust boundary

All four stores are tamper-resistant, not tamper-proof. An agent with
shell access could forge a note, rewrite the marker, or edit the
journal exactly as easily as checking a checkbox. The protocol's
answer is layered: the stores make honesty the path of least
resistance and every record auditable; a pretooluse guard should deny
agent writes to all four outright. Signing records would close the
rest and is deferred as ceremony until a drill shows a leak.

**Performer identity is recorded, not verified.** A node may declare
an `actor:` (WHO the work is assigned to — printed by the walker,
stamped into the journal), and review evidence must carry a
`reviewer:` line (WHO claims to have reviewed). Both are recorded
claims: the builder could write the review itself and sign it
`security-sentinel`, and nothing mechanical would notice. What the
records buy is that the question "who performed this?" has an
auditable answer on the run record instead of no answer — and that a
false answer is a *forged record*, deliberate and on the record,
rather than an omission nobody can point to. Independence is enforced
where enforcement works here: the evidence shape (fresh tree-bound
verdict, attested through `review-check.py`) plus the dispatch
contract in the pack's craft. Transcript-level verification of who
actually ran is named as deferred — until a drill shows a leak, the
same bar as signing.
