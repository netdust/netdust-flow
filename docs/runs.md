# Run ledger — flow-driven deliveries

theory.md ends on "the final word belongs to the delivery ledger, not
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
PHP-version floor). Escaped-defect count is the metric theory.md says
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

---

## Run 0002 — r20260721-140229 · deliver@c5d0ea23260d

**Delivered:** Netdust Forms v2 — the same form builder, rebuilt from
the same approved spec under the post-run-0001 process. Same cohort
hash as run 0001: the flow was unchanged; the process around it was
not.
**Method note:** same manual-stop drive as run 0001, but this time
the craft was DISPATCHED, not just declared: the plan was produced by
the `planner` craft as a fresh subagent; the T08/T09 reviews ran as
independent fresh-context subagents using the real `security-sentinel`
and `reviewer` definitions, their verdicts recorded as tree-bound
evidence (`review-check.py`: report must say VERDICT: CLEAN and name
the exact tree it reviewed — a review of last week's code proves
nothing about today's).

**Eval (vs run 0001, same cohort):**

    run 0001: 10 stops · 7 iters · red-gates 3/8 · ledger mean-to-green 4.0
    run 0002:  8 stops · 5 iters · red-gates 1/6 · ledger mean-to-green 2.0
    both: 2 human yields · disarm-finished · zero overrides

**I5, executed for the first time:** the plan gate (v2 project gate
command) mechanically required a review cluster — it would have
REFUSED run 0001's plan. T02 made test realism a task of its own:
shims that mirror real platform semantics (slashed POST bodies,
strict `sanitize_email`, slashing-aware meta/post writers, insert
failure), self-tested so shim drift is itself a red check.

**The headline event — an attested review caught a live defect:**
the wp-semantics reviewer returned VERDICT: FINDINGS on a defect the
author did not know about (submission `post_title` passed to
`wp_insert_post` unslashed — the same slashing class as run 0001's
escape #1, at a call site the suite didn't model). The red verdict
BLOCKED T09's attest; the fix landed with a shim improvement and a
regression check; both reviewers re-verified the diff and re-staked
CLEAN on the new tree; only then did the attest pass. In run 0001
this would have been escape #9. In run 0002 it is a caught-in-flow
finding with a complete audit trail. That is invariant I5's designed
behavior, observed once in production.

**Escaped defects: 0 known at seal time — stated carefully.** The
in-flow reviews are part of the process, so they don't count as the
post-seal audit that produced run 0001's number. The honest
comparison requires a later, independent post-seal review (ideally
after real deployment). Contamination caveat, recorded up front: the
author carried run 0001's answer key, so non-recurrence of the known
eight classes is NOT process-attributable. The T09 catch IS — the
defect was unknown to the author and was found by the attested
review, which is the only clean signal this run could produce, and it
produced it.

**Findings:**

- **F5 (tool defect, fixed this entry):** `flow-eval` crashed with
  BrokenPipeError when its report was piped into `head`. Fixed
  (SIGPIPE default).
- **F6 (boundary, open):** review reports are gitignored working
  papers; the durable evidence is the attest note recording that
  `review-check` passed against a named tree. Acceptable — same
  status as the journal — but the report content itself dies with the
  workspace. If report retention ever matters, they need a store.
- **F7 (observation):** in-flow review verdicts arriving AFTER a code
  fix require re-review of the new tree; the tree-binding forced the
  correct behavior automatically. The freshness mechanism deferred
  for seals ("stricter freshness is deferred until a drill shows a
  leak") has now been drilled for reviews, and it held.
