# Runtime — the implementation

The runtime does not understand software development. It understands
nodes, transitions, and evidence — nothing else. Everything
domain-specific (what a spec is, what green means, what a review
covers) lives in the commands gates run and the craft agents
reference, outside this layer.

```
Claude Code Stop hook  (hooks/loop-gate.py)
          |
          v
      flow-check.py    (the walker)
          |
          v
      YAML graph       (compiled .json twin)
     /     |     \
 Agent   Gate   Human
```

## The Stop hook (`hooks/loop-gate.py`)

Fires at every session stop. No marker → no-op. A marker without
`flow` + `node` is not ours and is left untouched. Otherwise it runs
the walker and acts on the exit code (see protocol.md, completion
semantics): FINISHED disarms, BLOCKED yields keeping the marker,
CONTINUE blocks the stop with the next node — unless the iteration
budget or the dry-loop counter disarms first. Fail-open by contract: a
crashing hook must never trap a session.

Each invocation appends journal events to
`<feature-dir>/.flow-journal.jsonl` — one per gate execution (red
exits included) plus one stop decision, stamped with a per-arming run
id and the content hash of the flow twin. Journaling is fail-open and
can never affect the gate's decision.

## The walker (`bin/flow-check.py`)

Stateless. Starts at the marker's node, advances along declared edges:
gates are executed (exit code → `gate.exit`, consumed by out-edges),
agent nodes stop the walk with CONTINUE, human nodes with BLOCKED,
`__end__` with FINISHED. Guards: a hop ceiling, a revisited-gate check
(a cycle without an agent step blocks), and fail-closed handling of
every configuration problem. Conditions are parsed with the closed
grammar — no `eval`. Gates run as argv — no shell. Placeholders
(`{feature_dir}`, `{netdust_flow}`, project binds) are substituted
from the marker; an unbound placeholder blocks.

stdout contract: verdict line, `next:` line, `progress:` line, then
one `trace:` JSON line per executed gate (the hook folds these into
the journal; standalone runs like `/flow status` just print them —
a status check must not write history).

## Flow loading

The walker prefers the compiled `.json` twin, written only by a green
`flow-lint --compile` — so the hook path needs no PyYAML and a flow
that fails the lint can never drive a run. The YAML source is
authoring-side.

## Evidence writers

- `attest.py <fd> <unit> -- <cmd>` runs the check itself; on exit 0 it
  appends a structured record to `refs/notes/attest` on HEAD. On
  failure, nothing is recorded and the red exit propagates.
- `ledger.py <fd>` derives delivery state on request: every task
  attested somewhere reachable, SUITE attested on the current HEAD,
  worktree clean. Exit 0/1/2 — it is itself just a gate.
- `seal.py record|check` writes and reads human decisions on
  `refs/notes/seal`; the check is a gate like any other.
- `floor-check.py` scans the real diff against the declared floors;
  an unresolvable base ref fails closed.

## Trust boundary

The marker, the compiled twins, git notes, and the journal are
tamper-resistant, not tamper-proof — an agent with shell access could
forge any of them. The runtime deliberately does not re-verify their
provenance; the enforcement layer is a pretooluse guard that denies
agent writes to all four (`git notes` outside `attest.py`/`seal.py`
included). The gate is deterministic; the guard is the wall.
