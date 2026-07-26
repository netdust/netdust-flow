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

Every entry is load-bearing, and each is checked before a run starts:
`pack.yaml` against `pack.schema.json`, `flows/` by the lint, `bin/`
and `craft/` by resolution, `floors.yaml` by existence. A pack that
declares something it does not have refuses the arm.

## Resolution rules

1. `/flow <feature-dir> <name>` looks for `.flow/flows/<name>.yaml` in
   the project first, then `<netdust-flow>/flows/<name>.yaml`. The
   project wins, and the arm confirmation says which file it bound.
2. The marker records the **resolved absolute path** to the compiled
   twin, never the bare name — so a later `/flow status` cannot drift
   onto a different file.
3. A gate's `run:` program, when relative, resolves against the
   **project root first**, then the plugin root, then PATH. A
   project's own `.flow/bin/x.py` therefore always beats a same-named
   script installed globally. This matters: a global script silently
   answering for a project is a gate that measures the wrong thing.
4. A node's **craft** resolves the same way and in the same order:
   `.flow/craft/<name>[.md]` in the project, then the project root
   (so an explicit `.flow/craft/build.md` works), then the plugin
   root. One rule, `bin/flowspec.py`, used by the walker, the lint and
   the arm step — so the answer given at arm time is the answer the
   run gets.

## Craft is per project, and that is the point

`agents/reviewer` does not mean the same thing in a WordPress plugin,
a Rust crate and a research dossier. A pack answers that question for
itself by putting `.flow/craft/agents/reviewer.md` next to its flows;
resolution finds the project's copy first, and only falls back to the
shared plugin for craft that genuinely is shared.

Two honest limits, both worth stating plainly:

- **Craft is not evidence and cannot be made into evidence by
  declaring it.** Nothing mechanical notices when an agent ignores the
  craft a node names. That is exactly why invariant I5 exists: the one
  kind of craft whose absence no gate can see — independent review —
  must become a ledger task, whose check is an attested review run.
  Everything else is guidance.
- **What IS checkable is that it resolves.** Craft naming a file that
  does not exist will certainly not be used, so
  `flow-lint --check-craft` FAILs on it and arming runs that check.
  An uninstalled plugin root is a WARN rather than a FAIL — the same
  line the gate check draws between what the lint can know and what
  someone else verifies. Run 0001's finding F4 is the cost of neither
  check existing: the build node's declared reviewers were never
  dispatched, nothing noticed, and eight defects escaped.

The walker also prints the next node's craft on its `craft:` line, and
the Stop hook puts it in the block reason — so the driving agent is
HANDED the declaration instead of having to open the marker, find the
twin and read the node. That does not make it evidence. It removes the
excuse.

## pack.yaml

    pack: <name>
    description: one line — what kind of work this pack delivers
    binds:                    # every {placeholder} the flows use
      test_suite_cmd:
        description: the command that proves the suite is green
        example: "ddev exec vendor/bin/phpunit"
        value: "ddev exec vendor/bin/phpunit"   # optional
    requires:                 # tools the gates shell out to
      - {name: php, why: "syntax gate"}
      - {name: ddev, why: "render + a11y gates", optional: true}

Validated against `pack.schema.json` (Draft 2020-12, unknown keys
rejected) by the arm step, so a pack that does not parse or does not
conform refuses the arm instead of quietly failing to supply a bind
later. This repo's own pack is `.flow/pack.yaml`, and the suite
validates it on every commit — a pack format with no consumer is a
pack format that rots.

Its job is to turn "the walk BLOCKED on an unbound placeholder, twenty
minutes in" into "refused to arm, here is the missing bind" — the same
trade the lint makes everywhere else. Two ways it earns that:

- `description` becomes the hint printed when a bind is missing.
- `value` **supplies** the bind. A pack with values is self-contained:
  it needs no `Gate check:` / `Test suite:` convention in the project
  CLAUDE.md, and it wins over those lines when both exist, being the
  more specific declaration. Precedence, lowest first: built-in
  defaults · CLAUDE.md · pack `value` · `--bind`.

## Verifying a pack before it drives anything

    python3 <netdust-flow>/bin/flow-lint.py .flow/flows/<name>.yaml \
        --check-gates --check-craft --project . --compile

`--check-gates` FAILs when the flow names a gate program that exists
nowhere the walker would look (project root · plugin root · PATH);
`--check-craft` FAILs when a node's craft resolves to nothing. Without
them both surface mid-run — the gate as a BLOCKED walk that reads like
a flow defect, the craft as nothing at all — and each costs a whole
arming to diagnose. Programs that still carry a `{bind}` are reported
WARN, not FAIL; pass `--bind name=value` and they are checked for
real. Arming does exactly that, which is why it can promise the answer
it gives is the answer the run gets.

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

## Deriving from a road instead of copying it

A pack rarely wants a graph from scratch — it wants `deliver` with two
stages dropped, or `patch` with an extra gate. Copy it and you own a
divergent duplicate that ages on its own, which is how four
near-identical roads came to exist here.

    flow: wp-plugin
    version: 2
    extends: deliver          # project pack first, then the roads
    remove: [brainstorm, plan, gate-plan]
    nodes: [...]              # same id replaces, new id appends
    edges: [...]              # replaces the parent's edges FROM each
                              # source node the child mentions

`examples/wordpress-plugin/flow.yaml` is the worked case: six nodes,
five of them inherited, and it flattens to exactly the graph it used
to spell out by hand. Composition is resolved at compile time — the
twin holds the complete graph — and the derived road faces the entire
lint, so a `remove` that breaks the wiring fails before it can drive
anything. See [protocol.md](protocol.md#composition) for the rules.

## The rule a pack must not break

A project owns its checks. It does not own the invariants. A pack
cannot grant itself a path to `__end__` that skips a gate or a seal —
the lint enforces I2 and I4 against project flows exactly as it does
against the built-in roads, and `--check-gates` is an addition to that
enforcement, never a replacement. A pack that wants a shortcut to done
is asking for the one thing this system exists to refuse.
