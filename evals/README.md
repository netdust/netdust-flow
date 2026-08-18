# Agent-v0 evaluation

This cohort measures a narrower question than `protocol-v0`:

> Does the flow produce an observable run journal that `flow-eval.py` can compare between a baseline agent run and a netdust-controlled run?

This is deliberately **not** a claim about model quality. The first cohort is a harness/measurement contract. It fails closed if either side does not produce a real `.flow-journal.jsonl`.

## Run

From the repository root:

```sh
python3 evals/agent-v0.py --baseline /path/to/baseline-feature --netdust /path/to/netdust-feature
```

Each argument must contain a real `.flow-journal.jsonl` produced by the flow hooks. The runner invokes `bin/flow-eval.py` separately for both inputs and emits a machine-readable summary.

For a live experiment, create two equivalent feature directories:

- `baseline`: run the same coding task with the agent's normal workflow.
- `netdust`: run the same task with the netdust flow enabled.

Keep the task, starting tree, model, and budget fixed. Do not copy journals between runs.

## Metrics

The first report records the measurements already supported by `flow-eval.py`:

- runs
- iterations
- yields
- red gate executions
- first-pass gate counts
- mean executions to green
- block-stops
- gate errors

It also records whether each side produced a journal and whether `flow-eval.py` successfully parsed it.

**Do not interpret these metrics as proof of better software yet.** The next cohort should add task-level correctness and false-completion labels after the actual agent runs have been collected.
