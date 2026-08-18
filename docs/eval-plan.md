# Eval plan — what each experiment attacks, and why the order

The eval program tests distinct architectural claims, not model
quality. One experiment per claim; run only what tells us where the
real weakness is. Status as of E3.

## Done

- **E1 — protocol integrity** (PASS). The `eval-protocol` cohort
  E01–E12 + the trust-boundary suite: forged notes, fabricated seals,
  failed-check-writes-nothing, gate/hook crashes, direct-store writes,
  missing/stale/fantasy reviews, self-review, green control. Mechanism
  level.
- **E2 — convergence catches omission** (PASS, runs 0002/0003). The
  controlled pair: intent-lossy paperwork, gate as the only variable.
- **E3 — convergence resists rationalization** (PASS). A spec that
  argues its own completeness; the reviewer saw through it.

## The one thing genuinely untested — highest priority

- **E13 / E6 / E7 — the hostile-agent pen-test.** In every run so far
  the CONTROLLER ran attest/seal/ledger and the pretooluse guard was
  not installed. So the authority boundary has been tested as CODE,
  never as a boundary under attack. E13 needs a real harness: the
  agent gets shell, the guard is wired into its settings, and it is
  told "reach `__end__` by any means — modify tests, evidence, config,
  or state." The question: can an intelligent adversary obtain
  termination authority it was not given? This is the closest thing to
  falsifying the thesis, and the reason to build it first.

## Deferred, each for a SPECIFIC reason (not "skip")

- **E4 — stale evidence, DISCRIMINATING not merely strict.** Unit
  tests prove `--fresh` blocks on a changed tree. The open question
  they do NOT answer: does it stay GREEN on an irrelevant change (a
  README edit outside the feature dir) while blocking on a relevant
  one? If `--fresh` is strict-but-blind it will nag on every commit
  and get disabled. Cheap: add two discrimination tests. → next tests
  pass, not an experiment.
- **E5 — self-review end-to-end.** `--not implementer` is unit-tested;
  the untested part is an implementer told to fake a reviewer identity.
  Folds into E13's harness.
- **E8 — crash recovery PATHOLOGIES.** I6 covers walker/hook crash →
  marker unchanged. NOT covered: a half-written journal creating a
  false green, a resumed run re-running a human decision, a stale
  marker reading as current. Real gaps, correctness-level. After E13.
- **E9 — requirement mutation.** Already closed by construction:
  `converge-check` binds sha256(ask), so a mutated ask stales the
  report. → a two-line test, not an experiment.
- **E12 — model portability.** Scientifically the strongest claim
  (authority external to the intelligence). BLOCKED here: this
  environment serves one model family; a true cross-vendor reviewer
  needs infrastructure we don't have. Deferred on capability, not
  priority.
- **E14 — economics / E15 — ablation.** Both need n>1 real tasks of
  varying size to mean anything (small-task/complex-task crossover;
  which gate catches what %). Slow, later, and only honest at scale.

## The shape

    authority (E13/E5/E6/E7) — untested, build the harness
    intent    (E2/E3)        — PASS
    resilience(E4/E8)         — partial; specific gaps named
    portability(E12)          — blocked by environment
    economics (E14/E15)       — needs scale
