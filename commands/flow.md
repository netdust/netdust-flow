---
description: Arm the netdust-flow walker — the Stop-hook then drives execution along the declared flow graph until it FINISHES at a gate, BLOCKS on a human node, or the budget runs out. Usage — /flow <feature-dir> <flow> (arm) · /flow off (disarm) · /flow status · /flow eval [<feature-dir> ...]
allowed_tools: ["Bash", "Read", "Write"]
---

Arm, disarm, or inspect the flow walker for one feature. The Stop hook
(`hooks/loop-gate.py`) consumes `bin/flow-check.py` (the walker) at
every session stop. FINISHED, CONTINUE, and BLOCKED are derived from
the declared graph, gate exit codes, and artifacts — never from your
own assertion.

Resolve `<netdust-flow>` via the stable symlink `~/.claude/netdust-flow`
(same convention as `~/.claude/plugins/netdust-agent`).

## /flow <feature-dir> <flow>  (arm)

`<flow>` is a name under `<netdust-flow>/flows/` — `deliver` or `patch`.

Preconditions — refuse to arm (say why) if any fails:

1. **Lint + twin fresh:** run
   `python3 <netdust-flow>/bin/flow-lint.py <netdust-flow>/flows/<flow>.yaml --compile`
   — exit 0 required (needs PyYAML + jsonschema, authoring-side only).
   The walker reads the `.json` twin; a stale or FAIL-ing flow must
   never drive a run.
2. **deliver only — the graft:** `<feature-dir>/tasks.md` exists with
   `- [ ] Tnn` lines, and the project defines the spec/plan gate
   command (`Gate check:` line in the project CLAUDE.md, or ask the
   human once) — bound as `gate_check_cmd`, it drives `gate-spec` and
   `gate-plan`. Running it against `<feature-dir>` must exit 0 before
   arming: a walker on a gate-failing plan grinds a defective plan.
   No gate command → no spec/plan gates → refuse.
3. **patch only — bindings:** the project defines the suite command
   (`Test suite:` line in the project CLAUDE.md, or ask the human once).
   No suite command → no exit gate → refuse. Floors are no longer
   convention: gate-floors scans the real diff on the way out and
   routes floor-touching work to you for re-dispatch to deliver.
4. **deliver — evidence, not checkboxes:** completion derives from git
   attest notes (bin/attest.py records; bin/ledger.py answers).
   Checkbox state in tasks.md is a display mirror the ledger ignores;
   agents attest units by running their checks through attest.py.

Then:

4. Read `Loop budget: ~N` from `<feature-dir>/plan.md` when present;
   default 25.
5. Write `tasks/.harness-loop.json`:

   ```
   {"feature_dir": "<feature-dir>", "iteration": 0, "max_iterations": N,
    "last_done": 0, "dry": 0,
    "flow": "<netdust-flow>/flows/<flow>.json", "node": "__start__",
    "flow_check": "<netdust-flow>/bin/flow-check.py",
    "binds": {"netdust_flow": "<netdust-flow>",
              "gate_check_cmd": "<cmd>",      # deliver: spec/plan gates
              "test_suite_cmd": "<cmd>",      # patch + deliver SUITE attest
              "base_ref": "main"},            # patch: floor-check diff base
    "max_dry": 25,                            # patch only: budget-governed
    "gate_timeout": 600}
   ```

   (patch has no tasks.md, so its `progress:` line is node-based and
   nearly constant — `max_dry: 25` hands termination to the iteration
   budget instead of the dry-loop counter. deliver keeps the default 2.)
6. Ensure `.gitignore` contains `tasks/.harness-loop.json` AND
   `.flow-journal.jsonl` (the hook appends run-journal events to
   `<feature-dir>/.flow-journal.jsonl`; tracked, it would dirty the
   worktree mid-run and the ledger's clean-tree check could never
   pass).
7. Confirm to the user in two lines: armed, flow, budget, and how it
   ends (FINISHED at a gate → disarms · human node → yields with the
   ask · budget/dry → disarms · `/flow off` anytime).

Then start (or continue) working the CURRENT node normally. Nothing else
changes: review-gate HALTs, tiers, and the subagent-stop backstop all
still apply — the walker drives *through* the gates, never around them.

## Human decisions (I4 — seals)

When the walker BLOCKS on a human node (`approve-plan`, `shakeout`,
`unblock`, `redispatch`), resuming the session does NOT advance the
flow. The decision must be recorded as evidence, BY THE HUMAN's
explicit say-so, and the seal gate after the node reads it back:

    python3 <netdust-flow>/bin/seal.py record <feature-dir> <node> approved
    python3 <netdust-flow>/bin/seal.py record <feature-dir> <node> rejected

Run this only when the human states the decision in so many words —
never infer it, never run it to "unstick" a flow (that is exactly the
signal it exists to carry). Rejection routes along its own edge
(approve-plan → plan; shakeout → build). `unblock` needs no seal: it
re-runs the ledger, so resolving (attesting) the [HUMAN] task is
itself the evidence.

## /flow off  (disarm)

Delete `tasks/.harness-loop.json`. Confirm in one line. (The run's
journal stays; a manually disarmed run has no terminal stop event, so
`/flow eval` reports it as open — that is the honest state.)

## /flow status

Read the marker; run
`python3 <netdust-flow>/bin/flow-check.py <feature-dir> --flow <flow>
--node <node> --cwd .` (plus each bind) and report: armed/disarmed,
flow, current node, iteration/budget, and the walker's verdict line
verbatim.

## /flow eval  [<feature-dir> ...]

Run `python3 <netdust-flow>/bin/flow-eval.py <feature-dir> ...`
(default: every `specs/*` dir that has a `.flow-journal.jsonl`) and
show the report verbatim. It aggregates the run journals the hook
wrote: per-run outcomes, then per-cohort (flow @ twin-hash) gate exit
histograms, first-pass rates, executions-to-green, block-stops per
agent node, and human yields — where the flow works and where the
model struggles.

Read it with the report's own caveat: a gate's exit code is a routing
value, so judge loop gates (gate-ledger, gate-suite) by
mean-to-green and check gates (gate-spec, gate-plan, seal gates) by
first-pass. Adaptation is yours, not the system's: edit the flow YAML,
re-run `flow-lint --compile` (new hash), and the next runs form a new
cohort to compare against. Never let an agent rewrite a flow from an
eval report — the graph is a contract, not a prompt.

## Legacy markers

The spec-kit-era single-cycle /loop marker is retired. The hook only
drives markers that carry `flow` + `node`; a marker without them is
ignored untouched (logged, stop allowed) — it is not ours to delete.
