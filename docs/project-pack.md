# The project pack — flows a project owns

netdust-flow supplies the machine: a walker, an evidence store, a Stop
hook, a lint. It does not supply *checks*. A check is domain knowledge
— what "green" means for a WordPress theme, a Rust crate, a research
dossier, or a contract is not something a runtime can know, and a
runtime that pretended to know it would have to grow a plugin for every
domain anyone ever delivers.

So the split is:

| Lives in netdust-flow | Lives in the project |
| --- | --- |
| the walker, the hook, the lint, the schema | the flow graph for this kind of work |
| attest / ledger / seal (evidence) | the gate scripts the graph names |
| `deliver` and `patch` (domain-independent roads) | the floors that match this codebase |
| the invariants I1–I5 | the craft the agent nodes declare |

A **project pack** is the second column, laid out by convention so the
`/flow` command can find it without configuration.

## Layout

    <project>/
      .flow/
        pack.yaml            # what this pack needs bound, and why
        flows/<name>.yaml    # the flow(s) this project owns
        flows/<name>.json    # compiled twin (flow-lint --compile)
        bin/<gate>.py|.sh    # the gates the flows name
        craft/<name>.md      # craft the agent nodes declare
        floors.yaml          # this codebase's dispatch floors

Nothing here is magic. `.flow/flows/site.yaml` is an ordinary flow file
that passes the ordinary lint against the ordinary schema; `.flow/bin/`
holds ordinary executables. The convention buys one thing: `/flow site`
resolves to the project's flow without anyone typing a path.

## Resolution rules

1. `/flow <feature-dir> <name>` looks for `.flow/flows/<name>.yaml` in
   the project first, then `<netdust-flow>/flows/<name>.yaml`. The
   project wins, and the arm confirmation says which file it bound.
2. The marker records the **resolved absolute path** to the compiled
   twin, never the bare name — so a later `/flow status` cannot drift
   onto a different file.
3. A gate's `run:` program, when relative, resolves against the
   **project root first**, then the plugin root. A project's own
   `.flow/bin/x.py` therefore always beats a same-named script
   installed globally. This matters: a global script silently
   answering for a project is a gate that measures the wrong thing.

## pack.yaml

    pack: <name>
    description: one line — what kind of work this pack delivers
    binds:                    # every {placeholder} the flows use
      test_suite_cmd:
        description: the command that proves the suite is green
        example: "ddev exec vendor/bin/phpunit"
    requires:                 # tools the gates shell out to
      - {name: php, why: "syntax gate"}
      - {name: ddev, why: "render + a11y gates", optional: true}

`pack.yaml` is documentation the arm step can read, not a second
runtime. Its job is to turn "the walk BLOCKED on an unbound
placeholder, twenty minutes in" into "refused to arm, here is the
missing bind" — the same trade the lint makes everywhere else.

## Verifying a pack before it drives anything

    python3 <netdust-flow>/bin/flow-lint.py .flow/flows/<name>.yaml \
        --check-gates --project . --compile

`--check-gates` FAILs when the flow names a gate program that does not
exist under the project. Without it a missing gate surfaces mid-run as
a BLOCKED walk, which reads like a flow defect and costs a whole arming
to diagnose. Gate programs that come from a `{bind}` are reported WARN,
not FAIL — the lint cannot know them, and the arm step verifies binds.

## floors.yaml

`.flow/floors.yaml` is what this codebase considers dangerous enough
to force onto the long road. The `patch` flow binds it as
`{floors_file}` and `bin/floor-check.py` scans the real diff against
it on the way out; a hit routes to a human for re-dispatch. Floors
only ever push work UP.

Three rules, all learned the same way:

1. **The runtime ships none.** Until v0.5 a `floors.yaml` sat in the
   runtime's root describing `wp-login`, `dbDelta` and Stripe, and
   `patch` ran `floor-check` without `--floors` — so every project
   that took the short road was measured against a WordPress
   project's fears. A worked example now lives at
   `examples/wordpress-plugin/floors.yaml`; copy it and tune it, or
   write your own (this repo's is `.flow/floors.yaml`, and it is about
   evidence stores and the hook path, not about WordPress).
2. **Missing means BLOCKED, not clean.** `flow-arm.py` refuses to arm
   a floors-scanning flow when the file is absent, and `floor-check`
   fails closed if it gets that far. A floor file nobody wrote is not
   a floor that always passes; it is a question nobody answered.
3. **Editing your floors trips your floors.** Patterns are matched
   against the diff text, and a diff that adds a pattern contains it.
   That is correct behaviour — changing what counts as dangerous is
   itself deliver-road work — but it surprises everyone once.

## The rule a pack must not break

A project owns its checks. It does not own the invariants. A pack
cannot grant itself a path to `__end__` that skips a gate or a seal —
the lint enforces I2 and I4 against project flows exactly as it does
against the built-in roads, and `--check-gates` is an addition to that
enforcement, never a replacement. A pack that wants a shortcut to done
is asking for the one thing this system exists to refuse.
