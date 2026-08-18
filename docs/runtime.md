# Runtime — the implementation

The runtime does not understand software development. It understands
nodes, transitions, and evidence — nothing else. Everything
domain-specific (what a spec is, what green means, what a review
covers) lives in the commands gates run and the craft agents
reference, outside this layer.

```
      flow-arm.py      (arming: writes the marker, or refuses)
          |
          v
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

## Arming (`bin/flow-arm.py`)

The marker (`tasks/.netdust-flow.json`) is the only input to the whole
machine — it names the flow, the start node, the gate commands and the
budget — and everything downstream refuses to guess about it. Arming
is where that file is proven before it is written: the flow resolves
(project `.flow/flows/` first, then the built-in roads), lints clean
and compiles its twin, every gate program exists where the walker
would look for it (project root · plugin root · PATH), every
`{placeholder}` a gate uses has a value, every craft an agent node
declares resolves, `.flow/pack.yaml` validates against
`pack.schema.json` and its required tools are present, and any
`{base_ref}` or `{floors_file}` resolves. Any one of those failing is
a refusal naming what is missing — not a marker.

The generic placeholder rule replaces what used to be per-flow prose:
deliver's `{gate_check_cmd}` and patch's `{test_suite_cmd}` are the
same refusal, so a new flow inherits the protection without anyone
writing it a new precondition.

Two side effects belong here rather than mid-run: the feature dir is
created (the hook journals into it fail-open — a missing dir loses the
run journal silently) and the `.gitignore` entries for the marker and
the journal are ensured. `max_dry` is derived from whether the run
will have a `tasks.md` to count, which is the first mechanical
consumer of a node's `out:` declarations.

Authoring-side, like the lint: PyYAML, never in the hook path.

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

stdout contract: verdict line, `next:` line, `progress:` line, an
optional `craft:` line naming what the next node declares, then one
`trace:` JSON line per executed gate (the hook folds these into the
journal; standalone runs like `/flow status` just print them — a
status check must not write history). The hook puts the craft into the
block reason, so the declaration reaches the agent that has to use it
instead of waiting in a file for someone to look it up.

## Flow loading

The walker prefers the compiled `.json` twin, written only by a green
`flow-lint --compile` — so the hook path needs no PyYAML and a flow
that fails the lint can never drive a run. The YAML source is
authoring-side.

`extends:` composition is resolved by the lint before the twin is
written, so the twin is always the COMPLETE graph and the runtime
keeps exactly one notion of what a flow is. (The staleness check
flattens the source the same way before comparing — otherwise every
armed run of a derived road would block on a twin that is correct.)

## Shared rules (`bin/flowspec.py`)

Where a gate program is, where a node's craft is, and how `extends:`
composes: three rules the walker, the lint and the arm step all need
and none may answer differently. Stdlib only, because the walker
imports it and the hook path takes no authoring dependencies — the
`hooks-run-without-authoring-deps` CI job is what keeps that true.

## Evidence writers

- `attest.py <fd> <unit> -- <cmd>` runs the check itself; on exit 0 it
  appends a structured record to `refs/notes/attest` on HEAD. On
  failure, nothing is recorded and the red exit propagates.
- `ledger.py <fd>` derives delivery state on request: every task
  attested somewhere reachable, SUITE attested on the current HEAD,
  worktree clean. Exit 0/1/2 — it is itself just a gate.
- `seal.py record|check` writes and reads human decisions on
  `refs/notes/seal`; the check is a gate like any other.
- `floor-check.py` scans the real diff against the project's floors
  (`.flow/floors.yaml`, bound as `{floors_file}`). Both config faults
  fail closed: an unresolvable base ref, and a missing floors file —
  "nothing was scanned" must never read as "clean" on a gate whose job
  is pushing work up.

## Trust boundary

The marker, the compiled twins, git notes, and the journal are
tamper-resistant, not tamper-proof — an agent with shell access could
forge any of them. The runtime deliberately does not re-verify their
provenance; the enforcement layer is a pretooluse guard that denies
agent writes to all four (`git notes` outside `attest.py`/`seal.py`
included). The gate is deterministic; the guard is the wall.
