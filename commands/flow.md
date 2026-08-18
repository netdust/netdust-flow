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

    python3 <netdust-flow>/bin/flow-arm.py <feature-dir> <flow>

That is the whole step: run it, show its output verbatim, and stop if
it refused. Do not write `tasks/.netdust-flow.json` by hand.

Arming used to be six preconditions written out here and executed by
goodwill — the one assertion the system never checked, in a system
whose whole thesis is that assertions are not signals. It is code now,
and it refuses rather than guesses:

| It refuses when | Was |
| --- | --- |
| `<flow>` resolves to nothing | precondition 1 |
| the flow FAILs `flow-lint --compile` | precondition 1 |
| a gate names a program that exists nowhere the walker looks | precondition 1b |
| a node declares craft that resolves to nothing | new — craft was unchecked |
| `.flow/pack.yaml` does not match `pack.schema.json` | new — the pack was prose |
| a `{placeholder}` used by a gate has no value | preconditions 1c, 2, 5 |
| `.flow/pack.yaml` requires a tool that is not on PATH | precondition 1c |
| the flow scans floors and there is no `.flow/floors.yaml` | new — the runtime used to supply one |
| a `{base_ref}` diff base does not resolve in the repo | new — used to fail mid-run |
| `--node` names a node the flow does not declare | new |
| a marker is already there | new — re-arming discarded the live run's id |

Note the placeholder row: the old per-flow rules ("deliver needs a gate
command", "patch needs a suite command") are consequences of one
generic rule now, so a NEW flow gets the same protection without
anyone writing it a new paragraph here.

`<flow>` is a NAME, resolved project-first — `.flow/flows/<flow>.yaml`
in the project (a flow the project owns, naming gates the project
owns; see `docs/project-pack.md`), then `<netdust-flow>/flows/<flow>.yaml`
(the built-in roads, domain-independent by construction). A name in
both resolves to the project's and the confirmation says so. A path
argument is taken literally. The marker always records the resolved
ABSOLUTE path to the compiled twin, never the bare name, so a later
`/flow status` cannot silently bind a different file.

Bind values, in increasing precedence: `netdust_flow`, `base_ref`
(default `main`, verified to resolve) and `floors_file` (default
`.flow/floors.yaml`, verified to exist); the project CLAUDE.md
(`Gate check:` → `gate_check_cmd`, `Test suite:` → `test_suite_cmd`);
`.flow/pack.yaml`'s `binds.<name>.value` (flow-specific, so it beats
the repo-wide line); then `--bind NAME=VALUE`. `feature_dir` is never
a marker bind — the walker supplies it. Pass `--node <id>` to graft onto an existing run,
`--budget`/`--max-dry` to override what it derives.

It also prepares what the run needs and cannot recover afterwards: the
feature dir (the hook journals into it fail-open, so a missing dir
loses the whole run journal silently) and the two `.gitignore` lines.
Budget comes from `Loop budget:` in plan.md, default 25. `max_dry` is
derived — 2 when the run has or will produce a `tasks.md` for the
walker to count, 25 when it will not, because a near-constant
`progress:` line would otherwise disarm a healthy run.

Two things it deliberately does NOT check, because neither is
mechanical at arm time:

- **I5, the review cluster.** The plan must carry at least one task
  whose check IS an attested independent review (run 0001 finding F4).
  The project's gate command enforces that against the real plan —
  `.flow/bin/spec-gate.py` does it here — and `gate-plan` runs it on
  the way through. Arming would only duplicate a check the flow
  already makes.
- **Grafting mid-flow.** `--node <id>` past the plan node is legal and
  arm verifies only that the node is declared. A walker on a
  gate-failing plan grinds a defective plan, so run the gate command
  yourself first; arm at `__start__` unless you mean to skip the
  stages before it.

And one thing worth repeating because it is what the whole road is
for: completion derives from git attest notes (`bin/attest.py`
records, `bin/ledger.py` answers). Checkbox state in tasks.md is a
display mirror the ledger ignores — agents attest units by running
their checks through attest.py.

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

Delete `tasks/.netdust-flow.json`. Confirm in one line. (The run's
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

## Whose run is it  (session ownership)

The marker is project-scoped, but a RUN belongs to ONE session. The
first stop after arming writes that session's id into the marker; every
other session that stops in the repo is then as inert as if there were
no marker at all — no gates run, no counters move, nothing is written.

This exists because run 0004 lost a run without it: a second session
was merely WATCHING, and two of its stops — which of course moved no
task counter — were counted as dry iterations of the builder's run and
disarmed it. Watching a run is not free until the claim is in place.

    python3 <netdust-flow>/bin/flow-arm.py --reclaim

Hands a live run to whichever session stops next. Use it when the
owning session died (a wedged session cannot release its own claim).
Run id, node and journal continuity are preserved — this is not a
re-arm, which would mint a new run id and split the journal.

    python3 <netdust-flow>/bin/flow-arm.py --reset-counters

Zeroes `iteration` and `dry` on a live run, for the case where a defect
rather than the work spent the budget. Same preservation rules. Both
modes exist so the legitimate reasons to touch the marker never require
hand-writing it.

## Foreign markers

The hook only drives markers that carry `flow` + `node`; a marker
without them is ignored untouched (logged, stop allowed) — it is not
ours to delete.

`tasks/.netdust-flow.json` is namespaced, and every marker this runtime
writes declares `"schema": "netdust-flow/1"`. A marker whose schema
names something else is refused even in our own filename. Until run
0004 this file was `tasks/.harness-loop.json`, which netdust-agent also
claims for a completely different schema: arming one harness armed the
other, which then read our marker, ran its own gate against a plan
written to our contract, and reported the mismatch as a regression —
pointing sessions straight through a human seal. One filename, two
owners, no discriminator.
