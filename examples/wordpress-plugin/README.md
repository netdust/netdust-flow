# wordpress-plugin

A trimmed deliver road for plugin-sized work: spec gated, build driven
by the evidence ledger, finish sealed by an attended shake-out.
(Plugin work touching user input still belongs on the full
`flows/deliver.yaml` road — the floors say so.)

**Expected path:** `__start__ → spec → gate-spec → build ⟲
gate-ledger → shakeout (yield) → gate-acceptance → __end__`.
Rejected shake-out routes back to build; no seal yet re-asks.

**Gates used:** `gate-spec` (project-bound `gate_check_cmd`),
`gate-ledger` (attest-derived completion), `gate-acceptance`
(seal read).

**Evidence generated:** attest notes per task + SUITE on HEAD
(`refs/notes/attest`); the shake-out seal (`refs/notes/seal`); every
gate exit in the run journal. Per I5, tasks.md must include a review
task whose check is an attested independent review run — the plan
gate should refuse a tasks.md without one.
