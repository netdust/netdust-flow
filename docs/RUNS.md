# Run ledger — flow-driven deliveries

THEORY.md ends on "the final word belongs to the delivery ledger, not
the literature." This is that ledger: one entry per flow-driven run —
what happened, what the eval measured, what escaped, and what the
system changed because of it. Entries are append-only; a finding is
closed by naming the commit that closed it, never by deleting it.

---

## Run 0001 — r20260721-082049 · deliver@c5d0ea23260d

**Delivered:** Netdust Forms v1 — a schema-driven WordPress form
builder (separate project repo; ~600 lines PHP + 69-check suite).
**Method note:** driven in a remote session without the Stop hook
installed; the hook was invoked manually with a stop payload after
each work burst — real walker, real gates, real seals, real journal.
Craft subagents were NOT dispatched (see F4).

**Eval:**

    10 stops · 7 iterations · 2 human yields · red-gates 3/8 · disarm-finished
    gate-ledger  execs=4  exits 0×1 1×3  mean-to-green 4.0   (the build loop)
    gate-spec / gate-plan / gate-approval / gate-acceptance: first-pass 1/1

**Machinery verdict:** everything held. Routing, revisit guard, both
seal yields (resumption advanced nothing; `seal.py record` did),
ledger-derived completion (checkboxes ignored), journal complete,
budget untouched (7/25). Zero manual overrides of any gate.

**Quality verdict:** the run proved the machinery, not quality. No
check gate ever refused anything, and the strongest verifier in the
run (the test suite) was written by the same agent as the code. A
post-seal independent review (two adversarial reviewers, verified
against WordPress core source) found **8 escaped defects, 3
high-severity** — all three highs in the seam the shim-based suite
could not see (WP slashing semantics, `sanitize_email` strictness,
PHP-version floor). Escaped-defect count is the metric THEORY.md says
settles the bull/bear bet; run 0001's number is 8.

**Findings:**

- **F1 (doc defect, fixed run 0001):** `/flow` arm preconditions
  demanded `tasks.md` before every deliver arm, but a from-`__start__`
  run creates tasks.md at the `plan` node. Fixed: the tasks.md
  precondition now applies only when grafting mid-flow.
- **F2 (blindspot, open):** both check gates passed first-try. Over
  more runs, a persistent 100% first-pass rate on gate-spec/gate-plan
  means the gate command is too lenient, not that specs are good.
  Watch the cohort table.
- **F3 (measured gap, addressed by I5):** the suite's shims diverged
  from real WordPress semantics exactly where all three high-severity
  defects lived. A same-party suite bounds the run's Π pᵥ; gates
  verified the checks ran, not that the checks were strong.
- **F4 (system gap → invariant I5, fixed run 0001):** the build
  node's declared craft (reviewer, security-sentinel, …) was never
  dispatched and nothing mechanical noticed — craft was prose, and
  "I used the declared craft" is an agent assertion, exactly what I3
  forbids trusting. Fixed as I5: deliver plans must carry a review
  cluster whose checks are attested independent review runs; the plan
  gate refuses a plan without one. The 8 escaped defects are the
  measured cost of running the graph without the craft.

**Adaptations shipped with this entry:** I5 (README), arm
preconditions rewritten (F1, I5 requirement) in `commands/flow.md`.
**Open for next runs:** F2 watch; test-realism guidance (suite shims
must mirror real-platform semantics where security-bearing — or run
against the real platform).
