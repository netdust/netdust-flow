# netdust-flow

Evidence-driven delivery protocol for AI-assisted software
development: **a YAML file, one Stop hook, and exit codes.**

Agents may create work and propose routing.
Only verified evidence can advance or finish delivery.

```
              Agent
                |
                v
         creates artifact
                |
                v
        deterministic gate
          /            \
       fail            pass
        |                |
        v                v
      Agent         human seal?
                         |
                     approved
                         |
                         v
                    next state
                         |
                         v
                      __end__
```

Agents produce work. Verifiers produce evidence. The flow derives
state. Only verified evidence can finish delivery. Humans make
explicit, recorded decisions; completion is a state transition, not a
statement.
The implementation is small; the claim is not: **workflow authority
belongs to verifiable evidence, not to the system that produced the
artifact.**

## Three words, used precisely

| Term | Meaning | Examples |
| --- | --- | --- |
| **Assertion** | A statement made by an actor. Never workflow state. | "tests pass" · a checked checkbox · "review done" |
| **Evidence** | A recorded fact produced by a verifier, independently of the claimant. | an exit code · an attest note · a human seal |
| **State** | The workflow position, derived from evidence on request. | the marker's node · the ledger's verdict |

The only formula in the system:
`assertion → verification → evidence → state transition`.

## The roads

| Flow | Road |
| --- | --- |
| `flows/deliver.yaml` | brainstorm → spec ⊨gate → plan ⊨gate → **human approval ⊨seal** → build ⟲ ledger → **human shake-out ⊨seal** |
| `flows/patch.yaml` | build ⟲ suite-green → floors clean → done (floor hit → **human re-dispatch ⊨seal**) |

Dispatch floors route work up: whatever a project declares dangerous
takes `deliver` — no agent override downward. The floors themselves
are the project's (`.flow/floors.yaml`), because what is dangerous
about a codebase is not something a runtime can know.

## Invariants

- **I1** — every edge condition is machine-readable: `<state key> <op>
  <literal>`. Prose conditions fail the lint.
- **I2** — `__end__` is reachable only from a gate or a human node.
  Agents may route; only gates and humans finish.
- **I3** — evidence is written only by verifiers. Task completion
  derives from git attest notes recorded by `attest.py` at the moment
  a check passed (`ledger.py` computes state on request); nothing an
  agent asserts — checkboxes included — is a state signal.
- **I4** (v0.2) — the flow is a well-formed state machine and human
  decisions are events with evidence. Formally: `__end__` is the only
  final state (a node without out-edges fails the lint; the absorbing
  `__human__` pseudo-state is deprecated and WARNs), and a human
  node is a yield point only — the decision re-enters the machine as
  a seal record (`seal.py record … approved|rejected`) read by the
  gate that follows it. Resuming a session is never approval;
  rejection travels its own edge. This is I3 applied to humans: a
  decision nobody recorded is not a state signal either.
- **I5** (v0.3, from run 0001) — craft that matters is evidence: a
  review that is not a ledger task did not happen. A node's `craft`
  list is checked to RESOLVE (`--check-craft`, v0.6) and handed to the
  driving agent on the walker's `craft:` line — but nothing mechanical
  notices when it is skipped anyway, which keeps "I used the declared
  craft" exactly the kind of assertion I3 forbids trusting. Gates
  judge outputs, so craft whose absence shows up in a check is covered;
  independent review is not — its absence is invisible to every gate.
  Therefore deliver plans must carry a review cluster: task(s) whose
  check IS an attested independent review run, refused by the plan
  gate when missing. Enforced by the project's gate command and the
  ledger, not the lint (a flow file cannot see plan content).

- **I7** (v1, from runs 0002/0003) — **convergence is a gate, not a
  suggestion.** Gates establish that work satisfies a specification;
  convergence establishes that the specification still represents what
  was asked. Only when both hold may delivery finish. The judgment is
  an agent's, but it becomes state only as evidence:
  `bin/converge-check.py` verifies a fresh-context convergence review
  bound to sha256(ask) + sha256(spec) + tree, signed by someone other
  than the spec's author; NOT_CONVERGED is a red exit and a revised
  spec stales the report by construction. The controlled pair that
  forced this: without the gate the road delivered a consumer-less
  endpoint with every gate green ("verification integrity without
  intent preservation"); with it, the dropped deliverable was caught
  at plan time.

- **I8** (v1, from run E13) — **an armed flow may only execute the
  graph it was armed on.** The flow graph is the root of trust:
  everything derives from the compiled twin, so whoever can rewrite the
  twin owns termination. E13 (a hostile agent told to reach `__end__`
  by any means) proved it — it rerouted `__start__ → __end__` and
  finished with no work done. Fix: `flow-arm` anchors the twin (a git
  note keyed by the twin's blob sha, written inside its own process so
  the guard's git-notes deny covers it); the walker refuses any twin
  that carries no matching anchor. Authoring stays free (no anchor
  before arm); changing an armed graph requires a deliberate re-arm —
  which resets to `__start__`, re-anchors on the record, and discards
  prior evidence. Honest residual: an agent with shell can still
  disarm + rewrite + re-arm (loud, not silent) or delete the anchor ref
  via git plumbing AND edit the marker; making *arming itself*
  human-gated is the next deferred layer. Pinned by
  `tests/test_anchor_i8.py` (the E13 attack matrix, permanent).

- **I6** (v1, from external review) — **fail-open for interaction,
  fail-closed for state.** A broken harness must never trap a session,
  and a crash must never produce evidence or advance the flow: a hook
  crash allows the stop but leaves the marker's node unchanged; a gate
  that crashes exits red; a gate that cannot run BLOCKS rather than
  emitting an exit code an edge could consume (a deleted seal program
  must not read as a human rejection). The two safeties are different
  properties and are tested separately.

All eight are the same rule at different altitudes: **no assertion is a
signal.** I1, I2, and I4's shape are enforced by `bin/flow-lint.py`;
I3 by the attest/ledger design; I5 by the plan gate + ledger; I6 and I7
by `tests/test_trust_boundary.py`; I8 by `tests/test_anchor_i8.py` (the
E13 attack matrix). The trust boundary end to end lives across both.

## Documentation

| Doc | What it covers |
| --- | --- |
| [`docs/architecture.md`](docs/architecture.md) | The system model: node types, lifecycle, authority. |
| [`docs/protocol.md`](docs/protocol.md) | The rules, independent of implementation — the stable contract. |
| [`docs/runtime.md`](docs/runtime.md) | The implementation: hook, walker, gates, journal. |
| [`docs/evidence.md`](docs/evidence.md) | Assertion vs evidence vs state; the evidence stores; the trust boundary. |
| [`docs/runs.md`](docs/runs.md) | The run ledger — every flow-driven delivery, measured. |
| [`docs/project-pack.md`](docs/project-pack.md) | How a project owns its own flow and gates — the runtime supplies the machine, never the checks. |
| [`docs/examples.md`](docs/examples.md) | Index of the example flows under `examples/`. |
| [`docs/essays/`](docs/essays/) | The intellectual record, three-document spine: [`article.md`](docs/essays/article.md) — why completion authority is the missing abstraction; [`theory.md`](docs/essays/theory.md) — the foundation, with the v1 empirical addendum (what the evals demonstrated, what stays open); [`evaluation.md`](docs/essays/evaluation.md) — the evidence record (E1–E13, failures visible). Supporting: `comparison.md`, `craft-loop.md`. |

## Install

Two ways to get the runtime, both pinned, both deliberate:

- **Composer, per project** (how `wp-starter` sites consume it):
  `composer require netdust/flow` via a VCS repository entry — the
  kernel lands in `vendor/netdust/flow`, the executables in
  `vendor/bin`, and `composer.lock` pins the exact revision. A runtime
  update is a lockfile diff, never a silent change to what "finished"
  means. The project commits its own hooks and `.flow/`; arming
  refuses if the runtime is not resolvable, so a clone that skipped
  `composer install` degrades to an ordinary unharnessed session —
  never to a fake-harnessed one.
- **Clone, per machine**: `git clone` to `~/.claude/netdust-flow` for
  driving flows outside composer-managed projects.

## Parts

- `flows/` — YAML sources plus committed `.json` twins, written only
  by a green `flow-lint --compile`, so the hook path needs no PyYAML.
- `flow.schema.json` / `pack.schema.json` — Draft 2020-12 schemas for
  flow files and project packs, enforced by the lint and the arm step
  (typo'd keys fail via `additionalProperties: false`).
- `bin/flowspec.py` — the three rules the tools must agree on:
  where a gate program is, where a node's craft is, and how `extends:`
  composes. Stdlib only, because the walker imports it and the hook
  path takes no authoring dependencies. A rule implemented twice is a
  rule that drifts.
- `bin/flow-lint.py` — static gate: schema, graph, determinism,
  I1/I2/I4, gate results actually consumed by their out-edges. Opt-in
  `--check-gates` / `--check-craft` prove that every program and every
  craft a flow names actually resolves; `extends:` is flattened here,
  so the twin is always a complete graph.
- `bin/flow-arm.py` — arming as verification: resolves the flow
  project-first, lints and compiles it, proves every gate program
  exists and every `{placeholder}` has a value, then writes the
  marker. The marker is the only input to the machine, and it used to
  be written by hand from prose preconditions — the one assertion the
  system never checked. Refuses with a named reason instead of arming
  a run that would BLOCK twenty minutes in.
- `bin/flow-check.py` — the walker: stateless, closed condition
  grammar, gates run as argv (no shell, no eval), every config problem
  BLOCKS instead of guessing. Its stdout names the next node's craft,
  so the declaration reaches the agent that has to use it.
- `hooks/loop-gate.py` — the Stop hook: drives flow markers only; a
  marker without `flow` + `node` is not ours and is ignored untouched.
  Each stop it appends run-journal events (every gate exit — red ones
  included, which exist nowhere else — plus one stop decision) to
  `<feature-dir>/.flow-journal.jsonl`, fail-open. The block reason
  carries the next node's craft by name.
- `bin/attest.py` / `bin/ledger.py` — evidence recorded by the
  verifier into git notes; delivery state derived on request.
- `bin/converge-check.py` — the I7 gate: verifies an attested
  fresh-context convergence review (does the spec still represent the
  original ask?) bound to sha256(ask)+sha256(spec)+tree, reviewer not
  the spec's author. NOT_CONVERGED and stale bindings are red.
- `bin/review-check.py` — the check an I5 review task runs through
  attest.py: a report exists, its verdict is CLEAN, and it is bound to
  the exact tree it reviewed. Run 0002's caught defect came through
  here — a review of yesterday's code proves nothing about today's.
- `bin/seal.py` — human decisions as evidence (I4): `record` writes a
  decision into git notes, `check` reads the latest back as an exit
  code for the seal gate after each human node. `check --fresh` also
  requires the decision to still describe what is on disk (same tree,
  clean under the feature dir) and exits 1 — re-ask — when it does not,
  so a judgment-bearing finish cannot ride a stale approval.
- `bin/flow-eval.py` — aggregates run journals into cohorts by flow
  version (content hash of the twin): exit histograms, first-pass
  rates, executions-to-green, human yields. The journal measures, the
  human adapts, the lint recompiles — nothing feeds back into a flow
  automatically.
- `bin/floor-check.py` — the dispatch floors as a mechanical diff scan
  on the patch road; fails closed on an unresolvable base AND on a
  missing floors file. The floors are the project's
  (`.flow/floors.yaml`, bound into the flow as `{floors_file}`); this
  runtime ships none, having learned the hard way that a default
  floors file means every project inherits the author's domain.
- `commands/flow.md` — `/flow` arm · off · status · seal · eval.
- `examples/` — four small lint-clean flows with expected paths and
  the evidence each generates; the WordPress one is DERIVED from
  `deliver` with `extends:` rather than copied from it.
- `.flow/` — this repo's own project pack: `pack.yaml`, its spec/plan
  gate, and floors about evidence stores and the hook path rather than
  about anyone's domain. The convention has a consumer here so it
  cannot rot untested.
- `tests/` — 171 tests (walker + hook integration + evidence + lint +
  arm + eval + project packs), run by CI on Python 3.10–3.12. One CI job
  installs no authoring dependencies at all, which is how the promise
  that the hook path needs no PyYAML stays true.

Trust boundary, enforced (as far as resistance goes): git notes, the
compiled `.json` twins, and the run journal (`.flow-journal.jsonl`)
are tamper-resistant, not tamper-proof. `hooks/pretooluse-guard.py`
(a PreToolUse hook) denies the direct forge — `git notes` writes via
Bash, and Write/Edit to twins or journal — so a forge must be
deliberate, not incidental; it makes no airtight claim. The marker
(`tasks/.harness-loop.json`) is deliberately left editable because
arming writes it; that residue is named in the guard. Wire the guard
in `settings.json` alongside the Stop hook. The journal must also be
GITIGNORED in the project (as `/flow` arm ensures): tracked, it would
dirty the worktree mid-run and the ledger's clean-tree check could
never pass.

- `hooks/pretooluse-guard.py` — the trust-boundary guard: denies
  agent-issued `git notes` writes and hand-edits of twins/journal,
  fail-open. The enforcement the invariants above depend on.

## Runtime

Claude Code plus the Stop hook — nothing else. Symlink this checkout:

    ln -s "$(pwd)" ~/.claude/netdust-flow

## Deliberately not here

Parallel fan-out (solo operation), an external runner (the file format
keeps that door open), agent-designed graphs, self-modifying
workflows, autonomous policy changes, hidden completion heuristics.
The human measurement loop is not a limitation; it is part of the
architecture. Revisit each only when a real trigger fires.

---

netdust-flow is not trying to make agents appear autonomous. It is
trying to make autonomous work trustworthy, by ensuring that progress
and completion require evidence.
