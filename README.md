# netdust-flow

Declared workflows for AI-assisted delivery: **a YAML file, one Stop
hook, and exit codes.**

Every feature takes one of two declared roads. Agents do the work,
deterministic gates decide progress, humans seal both ends. The graph
is data — versioned, schema-checked, linted — so the process is
identical run after run, and readable by anyone in one sitting. Built
for a solo studio shipping WordPress sites and smaller apps with
Claude Code; craft (agents, skills) lives in
[netdust-plugins](https://github.com/netdust/netdust-plugins) and is
referenced by nodes, never embedded.

## The two flows

| Flow | Road |
| --- | --- |
| `flows/deliver.yaml` | brainstorm → spec ⊨gate → plan ⊨gate → **human approval ⊨seal** → build ⟲ ledger → **human shake-out ⊨seal** |
| `flows/patch.yaml` | build ⟲ suite-green → floors clean → done (floor hit → **human re-dispatch ⊨seal**) |

Dispatch floors route work: anything touching auth, user input,
schema/migrations, or payments takes `deliver` — no agent override
downward.

## Invariants (enforced by `bin/flow-lint.py`)

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

## Parts

- `flows/` — YAML sources plus committed `.json` twins, written only
  by a green `flow-lint --compile`, so the hook path needs no PyYAML.
- `flow.schema.json` — Draft 2020-12 schema for flow files, enforced
  by the lint (typo'd keys fail via `additionalProperties: false`).
- `bin/flow-lint.py` — static gate: schema, graph, determinism,
  I1/I2/I4, gate results actually consumed by their out-edges.
- `bin/flow-check.py` — the walker: stateless, closed condition
  grammar, gates run as argv (no shell, no eval), every config problem
  BLOCKS instead of guessing. Progress prefers a gate's
  evidence-derived `progress:` line over checkbox counts.
- `hooks/loop-gate.py` — the Stop hook, patched for flow mode; legacy
  `/loop` markers keep working unchanged during migration.
- `bin/attest.py` / `bin/ledger.py` — evidence recorded by the
  verifier into git notes; delivery state derived on request. Drift is
  caught at both levels: SUITE attest must sit on HEAD (commit-level)
  and the worktree must be clean (tree-level).
- `bin/seal.py` — human decisions as evidence (I4): `record` writes a
  decision into git notes, `check` reads the latest back as an exit
  code for the seal gate after each human node.
- `bin/floor-check.py` + `floors.yaml` — the dispatch floors as a
  mechanical diff scan on the patch road; an unresolvable base ref
  fails closed (exit 2), never shrinks the diff silently.
- `commands/flow.md` — `/flow` arm · off · status · seal.
- `tests/` — 63 tests here (walker + hook integration + evidence +
  lint); the upstream loop-gate suite (21) passes against the patched
  hook.

Trust boundary, named: git notes, the marker
(`tasks/.harness-loop.json`), and the compiled `.json` twins are
tamper-resistant, not tamper-proof. The pretooluse guard should deny
agent writes to all three (`git notes` outside `attest.py`/`seal.py`
included); see the docstrings in `attest.py` and `hooks/loop-gate.py`.

## Runtime

Claude Code plus the Stop hook — nothing else. Symlink this checkout:

    ln -s "$(pwd)" ~/.claude/netdust-flow

## Deliberately not here

Parallel fan-out (solo operation), an external runner (the file format
keeps that door open), agent-designed graphs (the thesis is the
opposite), an include mechanism (two files don't duplicate enough to
matter). Revisit each only when a real trigger fires.
