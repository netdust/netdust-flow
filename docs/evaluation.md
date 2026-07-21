# Evaluation — measurement as a first-class feature

The strongest differentiator here is not the workflow engine. It is
that every run leaves a complete, attributable record, and the system
improves based on measured failures, not opinions.

```
flow run
    |
    v
journal        every gate exit (red included) + every stop decision,
    |          stamped with run id + flow version hash
    v
evaluation     flow-eval.py: cohorts by flow@hash
    |
    v
flow improvement   a HUMAN edits the YAML; lint compiles a new hash;
                   the next runs form a new cohort to compare
```

The loop is deliberately human-closed. No part of the eval feeds back
into a flow automatically — self-optimizing pipelines hand authority
back to the actor being measured, which is the failure mode this
system exists to prevent.

## What is tracked

| Metric | Source | What it means |
| --- | --- | --- |
| **Escaped defects** | post-seal reviews, production incidents, recorded in [runs.md](runs.md) | the deciding metric: what the gate set missed. Run 0001's number is 8. |
| **Failed gates** | journal gate events (`exit != 0`) | red exits exist nowhere else — attest records passes, the ledger derives; only the journal sees failure |
| **Executions-to-green / first-pass rate** | journal, per gate node per run | loop gates (ledger, suite): iterations burned. Check gates (spec, plan, seals): whether work passes scrutiny first try |
| **Missing evidence** | ledger CONTINUE reasons; I5 plan-gate refusals | tasks or reviews without attest records |
| **Human interventions** | journal yield events | how often a person had to act, and at which node |

## Reading the numbers honestly

A gate's exit code is a routing value, not universally pass/fail:
`gate-ledger` exiting 1 seventeen times is the build loop doing its
job — the signal is the size of that number across runs, not its
existence. Judge loop gates by mean-to-green, check gates by
first-pass. And watch the inverse signal too: a check gate passing
100% first-try over many runs means the gate command is too lenient,
not that the work is flawless (run 0001, finding F2).

## Cohorts

Runs are grouped by `flow@hash` — the content hash of the compiled
twin that drove them. Editing a flow starts a new cohort, so every
comparison is between exact protocol instances, and an adaptation's
effect on the metrics is attributable. The run ledger
([runs.md](runs.md)) records each delivery, its findings, and the
adaptation each finding forced — append-only; a finding is closed by
naming the commit that closed it, never by deleting it.
