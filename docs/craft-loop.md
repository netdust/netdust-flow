# The craft loop — memory + improve-skill

netdust-flow's gates and seals are the **referee**: deterministic,
frozen, never learning. The **craft** (the `craft:` skills/agents on
each agent node) is the **worker** — and the worker *can* learn. This is
the loop that lets it: harvest what a skill got wrong from the run's own
evidence, and let a grounded eval decide whether a revised skill is
actually better. It is netdust-flow applied to its own craft.

Three small pieces, all stdlib, no LLM in the tools (the model work is
the flow's agent nodes; the tools are deterministic gates):

| Piece | Role |
|---|---|
| `bin/craft-memory.py` | the craft's **memory** — lessons harvested from evidence, append-only, provenance-carrying |
| `bin/skill-eval.py` | the **capability gate** — scores a skill's cases against produced outputs, deterministically |
| `flows/improve-skill.yaml` | the **meta-flow** — propose → cover → eval → review → seal → prune |

## The memory (`craft-memory.py`)

A **lesson** is a grounded record of something that went wrong, tied to
the run that produced it — never invented. Two sources, both already
emitted by the runtime:

- **seal rejections** — a human's `rejected` seal *with a note* ("not our
  brand voice") is the gold lesson: a real human correction.
- **gate reds** — a gate that failed with a reason ("research.md trivial
  (<300 chars)") in the run journal.

`extract` harvests both, deduped and stamped with their run.
`list`/`cover`/`retire`/`prune` read and maintain it. It is append-only,
latest-wins on status — a lesson is *evidence*, not a cache.

Flat files today (`craft-memory/<skill>.jsonl`), on purpose. The
Anthropic knowledge-graph playbook is the *next* step: when lessons span
skills and need dedup/traversal, `extract` grows an entity-resolution
pass and the store becomes a derived graph. Don't build the graph before
the corpus exists to fill it.

## The eval (`skill-eval.py`)

The one new primitive. A skill dir carries `eval/cases.jsonl`; each case
cites the lesson it reproduces and asserts a **deterministic** property
of the skill's output (`min_links`, `has_section`, `not_contains`, …).
`skill-eval` scores produced outputs against them and exits 0 iff every
case passes. It reports which cases passed, so the pruner retires only
confirmed lessons.

Deterministic on purpose: this gate is what stops the loop Goodharting
itself. Lessons whose fix is *judgment* (tone, nuance) can't be a
deterministic assertion — they stay with the fresh-context reviewer and
the human seal. The automated gate owns the mechanizable lessons
(structure, sourcing, required fields); judgment stays human.

## The three invariants (wired into `improve-skill.yaml`, not left to faith)

1. **Grounded.** `gate-cover` fails unless every live lesson has an eval
   case citing it. Cases derive from real failures; the eval can't drift
   from reality because it's *built* from reality.
2. **The gate is the eval.** `gate-eval` is deterministic and the
   proposer never sees its assertions while revising (train/test split).
   Passing it is the only way forward.
3. **The loop improves the worker, never the referee.** This flow touches
   only the skill. It never edits a gate or a flow. A human *seals* the
   adopted skill (`--fresh`), and a **separate, verifier-driven pruner**
   — not the proposer — retires a lesson only when its case truly passes.
   A lesson leaves memory through the front door (its failure stopped
   reproducing), never the back door (the optimizer wants it gone).

## The un-gameable outer check

`improve-skill`'s eval is a **proxy**. The ground truth lives outside
this flow: after a skill is adopted, `flow-eval` must show the live
**domain** cohort actually improving (first-pass-rate climbing,
mean-to-green dropping) on real work. If skill-eval soars but real
reject-rate doesn't budge, that's Goodhart — caught by the outer loop,
not this one. Adopt provisionally on the eval; confirm in production on
the cohort.

## Cadence

Trigger `improve-skill` off a **persistent** cohort hotspot in
`flow-eval` (a skill's reject-rate stuck high across many runs), not a
single rejection. One "not our brand voice" is a data point; twenty are
a lesson.

## The whole picture

```
domain runs ──emit──> evidence (attest / seal / journal)
                          │
                    craft-memory extract   (grounded lessons)
                          │
   improve-skill:  propose → gate-cover → gate-eval → review → seal → prune
                          │                                          │
                   revised skill (human-sealed)            lessons retired
                          │                                 (verifier-driven)
                          └──────────> next domain runs
                                            │
                                    flow-eval confirms (or refutes)
```

Three layers, each safe because the one below it doesn't move: **gates
verify, craft remembers and improves, humans judge** — with the eval
making "better" self-evidencing instead of asserted.
