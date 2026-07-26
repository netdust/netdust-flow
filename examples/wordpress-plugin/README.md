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

**`floors.yaml`** — what a WordPress project's dispatch floors look
like: auth, user input, schema/migrations, payments, expressed as the
path globs and diff patterns that actually appear in that stack
(`wp-login`, `current_user_can`, `dbDelta`, `woocommerce_order`).
Copy it to `.flow/floors.yaml` in a plugin repo and tune it; a project
taking the `patch` road must have one, and `bin/flow-arm.py` refuses
to arm without it. This file lived at the runtime's repo root until
v0.5, which meant every project inherited WordPress floors whether it
was a WordPress project or not — a runtime knowing a domain, exactly
what `docs/project-pack.md` exists to prevent.
