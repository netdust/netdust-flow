# netdust-flow — project instructions

The evidence-driven delivery runtime. Read `README.md` for the claim,
`docs/protocol.md` for the rules, `docs/architecture.md` for the model.

## Flow bindings

These two lines are read by `/flow` at arm time. Without them the
walker refuses to arm on this repo — which is the correct behaviour,
and was the state of this repo until they were added.

    Gate check: python3 .flow/bin/spec-gate.py
    Test suite: make test

`Gate check` drives `gate-spec` and `gate-plan` (bound as
`gate_check_cmd`, called with the feature dir). `Test suite` is what
`patch` attests as SUITE and what `deliver` runs on the way out.

## What this repo is, and what it is not

netdust-flow supplies the **machine**: walker, hook, lint, schema,
evidence stores (attest / ledger / seal), eval. It does **not** supply
domain checks. Anything that knows what "green" means for a particular
kind of work belongs in that project's own pack — see
`docs/project-pack.md`. This repo's own checks live in `.flow/`, by the
same rule, and that is deliberate: the convention has one consumer here
so it cannot rot untested.

When a change would make this repo know something about WordPress, or
research, or any other domain, that is the signal it belongs in a pack
instead.

## Working here

- **`bin/` and `hooks/` are the trust boundary.** A change that makes
  it easier for an agent's assertion to become state is a defect, no
  matter how convenient. Read `docs/evidence.md` before touching
  attest / ledger / seal.
- **The hook path takes no authoring dependencies.** `flow-check.py`
  and `loop-gate.py` run on a bare interpreter and read compiled
  `.json` twins; PyYAML and jsonschema are lint-time only. CI enforces
  this in the `hooks-run-without-authoring-deps` job — if you add an
  import there, that job is where you will hear about it.
- **Twins are compiled, never hand-edited.** After changing any
  `flows/*.yaml`, run `make compile` and commit both files. CI fails on
  a stale twin.
- **A new invariant needs a lint rule or a test**, or it is prose. I1,
  I2 and I4's shape are lint-enforced; I3 and I5 are enforced by the
  evidence design and the plan gate. An invariant nothing checks is
  exactly the assertion this project refuses to trust.

## Commands

    make check     # lint + test — run before every commit
    make test      # the suite
    make lint      # every flow, including examples/
    make compile   # regenerate .json twins
