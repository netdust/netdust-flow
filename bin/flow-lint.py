#!/usr/bin/env python3
"""flow-lint.py — netdust-flow v0

Static gate for flow definitions: findings, FAIL/WARN lines, exit
code — no opinions, no LLM.

Invariants it exists to enforce:
  I1  every edge condition is machine-readable — `<state key> <op>
      <literal>` with ops == != > >= < <= in. Prose is a FAIL.
  I2  __end__ is reachable only from gate or human nodes.
  I4  (v0.2) the machine is well-formed as an FSM: every declared node
      has at least one outgoing edge — __end__ is the only final state.
      A dead-end node is a FAIL; an edge into the absorbing __human__
      pseudo-state is a WARN (prefer a human node with out-edges and a
      seal gate — see bin/seal.py). The seal pattern itself is linted
      as WARNs (v0.3): a human node finishing directly, or routing
      anywhere but a gate, is machine-legal but protocol-deprecated —
      the decision should re-enter through a gate that reads the
      recorded seal.

Structural checks: flow.schema.json enforced (jsonschema, Draft
2020-12 — catches typo'd keys via additionalProperties) · unique
kebab-case node ids · gates carry run, agents carry craft · a gate's
exit must be consumed: its out-edges carry `when` conditions (an
unconditional out-edge from a gate is a FAIL — the gate result would
be theater) · edges reference declared ids (or __start__ / __end__ /
__human__) · every node reachable from __start__ · __end__ reachable ·
deterministic routing: a node with several outgoing edges must have
`when` on all of them.

Usage:  flow-lint.py <flow.yaml> [more.yaml ...] [--json] [--compile]
Exit:   0 if no FAIL findings, 1 otherwise. WARN never fails the gate.

--compile writes a `.json` twin next to every file that lints clean —
the runtime artifact flow-check.py prefers, so the Stop-hook path never
needs PyYAML. A file with FAIL findings never gets a twin.

Dependency note (deliberate): PyYAML + jsonschema at lint time only —
authoring-side, never in the Stop-hook path. The walker reads the
compiled .json twin; missing deps here BLOCK the lint rather than
silently weakening it.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowspec  # noqa: E402

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("flow-lint: PyYAML required (pip install pyyaml) — lint-time only")

try:
    import jsonschema
except ImportError:  # pragma: no cover
    sys.exit("flow-lint: jsonschema required (pip install jsonschema) — "
             "lint-time only; the schema gate must not be skipped silently")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "flow.schema.json"

SPECIAL_FROM = {"__start__"}
SPECIAL_TO = {"__end__", "__human__"}
KINDS = {"agent", "gate", "human"}
ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
COND_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_.]*\s*(==|!=|>=|<=|>|<|in)\s+\S.*$")


class Findings:
    def __init__(self) -> None:
        self.items: list[tuple[str, str, str]] = []

    def fail(self, check: str, detail: str) -> None:
        self.items.append(("FAIL", check, detail))

    def warn(self, check: str, detail: str) -> None:
        self.items.append(("WARN", check, detail))

    @property
    def failed(self) -> bool:
        return any(s == "FAIL" for s, _, _ in self.items)


def load_flat(path: Path, project: Path, f: Findings) -> dict | None:
    """Parse, then resolve `extends:` — every check below, and the twin
    that gets written, sees the COMPLETE graph. A derived flow is
    linted as the road it actually is, not as the diff that produced
    it, so composition can never smuggle a node past I2."""
    try:
        doc = yaml.safe_load(path.read_text())
    except Exception as e:
        f.fail("parse", f"{path.name}: {e}")
        return None
    if not isinstance(doc, dict):
        f.fail("root", f"{path.name}: top level must be a mapping")
        return None
    try:
        return flowspec.flatten(
            doc, lambda p: yaml.safe_load(p.read_text()),
            path.parent, project, SCHEMA_PATH.parent)
    except flowspec.ExtendsError as e:
        f.fail("extends", f"{path.name}: {e}")
        return None
    except Exception as e:
        f.fail("extends", f"{path.name}: cannot resolve `extends` ({e})")
        return None


def lint_file(path: Path, doc: dict, f: Findings) -> None:
    try:
        schema = json.loads(SCHEMA_PATH.read_text())
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(doc), key=str):
            where = "/".join(str(p) for p in err.absolute_path) or "<root>"
            f.fail("schema", f"{path.name}: {where}: {err.message}")
    except FileNotFoundError:
        f.fail("schema", f"flow.schema.json not found at {SCHEMA_PATH}")

    for key in ("flow", "version", "nodes", "edges"):
        if key not in doc:
            f.fail("required", f"{path.name}: missing `{key}`")

    nodes = doc.get("nodes") or []
    edges = doc.get("edges") or []
    state_keys = set((doc.get("state") or {}).keys())

    ids: set[str] = set()
    kind: dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n:
            f.fail("node", f"{path.name}: node without id")
            continue
        nid = str(n["id"])
        if nid in ids:
            f.fail("node", f"{path.name}: duplicate id `{nid}`")
        ids.add(nid)
        if not ID_RE.match(nid):
            f.warn("node", f"{path.name}: id `{nid}` is not kebab-case")
        k = n.get("kind")
        if k not in KINDS:
            f.fail("node", f"{path.name}: `{nid}` kind must be one of {sorted(KINDS)}")
            continue
        kind[nid] = k
        if k == "gate" and "run" not in n:
            f.fail("gate", f"{path.name}: gate `{nid}` missing `run`")
        if k == "agent" and not n.get("craft"):
            f.fail("agent", f"{path.name}: agent `{nid}` missing `craft`")

    out_edges: dict[str, list[dict]] = {}
    end_sources: list[str] = []
    adjacency: dict[str, set[str]] = {}
    for e in edges:
        if not isinstance(e, dict) or "from" not in e or "to" not in e:
            f.fail("edge", f"{path.name}: edge needs `from` and `to`")
            continue
        src, dst = str(e["from"]), str(e["to"])
        if src not in ids and src not in SPECIAL_FROM:
            f.fail("edge", f"{path.name}: unknown source `{src}`")
        if dst not in ids and dst not in SPECIAL_TO:
            f.fail("edge", f"{path.name}: unknown target `{dst}`")
        out_edges.setdefault(src, []).append(e)
        adjacency.setdefault(src, set()).add(dst)
        if dst == "__end__":
            end_sources.append(src)
        if dst == "__human__":
            f.warn("I4", f"{path.name}: edge {src}->__human__ targets an "
                         "absorbing state with no way back — prefer a human "
                         "node with out-edges and a seal gate (bin/seal.py)")

        when = e.get("when")
        if when is not None:
            w = str(when)
            if not COND_RE.match(w):
                f.fail("I1", f"{path.name}: edge {src}->{dst} condition `{w}` "
                             "is not machine-readable")
            else:
                root = w.split()[0].split(".")[0]
                if root not in state_keys:
                    f.warn("I1", f"{path.name}: edge {src}->{dst} tests "
                                 f"undeclared state key `{root}`")

    for src in end_sources:
        if kind.get(src) not in ("gate", "human"):
            f.fail("I2", f"{path.name}: __end__ reached from `{src}` "
                         f"(kind {kind.get(src)}) — only gate/human may finish")
        elif kind.get(src) == "human":
            f.warn("I4", f"{path.name}: human `{src}` finishes directly — "
                         "machine-legal but protocol-deprecated: a finish "
                         "should read recorded evidence (route the human to "
                         "a seal gate, bin/seal.py check, and let the gate "
                         "reach __end__)")

    for src, es in out_edges.items():
        if kind.get(src) != "human":
            continue
        for e in es:
            dst = str(e["to"])
            if kind.get(dst) is not None and kind.get(dst) != "gate":
                f.warn("I4", f"{path.name}: human `{src}` routes to "
                             f"{kind[dst]} `{dst}` — the decision should "
                             "re-enter the machine through a gate that "
                             "reads the recorded seal (bin/seal.py check)")

    for src, es in out_edges.items():
        if len(es) > 1:
            unconditional = [e for e in es if "when" not in e]
            if unconditional:
                f.fail("routing", f"{path.name}: `{src}` has {len(es)} outgoing "
                                  f"edges but {len(unconditional)} lack `when`")
        if kind.get(src) == "gate" and all("when" not in e for e in es):
            f.fail("gate", f"{path.name}: gate `{src}` result unused — its "
                           "out-edges must condition on gate.exit")

    for nid in ids:
        if nid not in out_edges:
            f.fail("I4", f"{path.name}: `{nid}` has no outgoing edge — "
                         "__end__ is the only final state; a dead-end node "
                         "deadlocks the walk")

    if "__start__" not in adjacency:
        f.fail("graph", f"{path.name}: no edge from __start__")
    seen: set[str] = set()
    stack = ["__start__"]
    while stack:
        for nxt in adjacency.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    for nid in ids:
        if nid not in seen:
            f.fail("graph", f"{path.name}: `{nid}` unreachable from __start__")
    if "__end__" not in seen:
        f.fail("graph", f"{path.name}: __end__ unreachable")


PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def check_gates(path: Path, doc: dict, project: Path, plugin_root: Path,
                binds: dict, f: Findings) -> None:
    """Every gate program a flow names must exist NOW, where the walker
    would look for it. A missing gate is otherwise discovered mid-run as
    a BLOCKED walk, which reads like a flow defect and costs a whole
    arming to diagnose.

    Resolution is flowspec's, i.e. the walker's: substitute binds into
    the WHOLE command, split it, resolve argv[0] project-root first and
    check any script it is handed. Doing this by hand here is what made
    the old version reject `--bind gate_check_cmd="python3 x.py"` — it
    substituted a two-word command into `run.split()[0]` and went
    looking for a file with a space in its name.

    A gate whose program still carries a `{placeholder}` cannot be
    checked; that is the arm step's job (it verifies binds resolve), so
    it is a WARN. A project that knows where its own gates live should
    pass --bind and get a real check instead of a warning."""
    for node in doc.get("nodes", []) or []:
        if not isinstance(node, dict) or node.get("kind") != "gate":
            continue
        run = str(node.get("run", "")).strip()
        if not run:
            continue
        cmd = flowspec.substitute(run, binds)
        programs = flowspec.gate_programs(cmd)
        if not programs:
            f.fail("gates", f"{path.name}: gate `{node.get('id')}` command "
                            f"`{cmd}` does not parse as argv")
            continue
        for token in programs:
            # only the PROGRAM tokens matter here: an argument that is
            # still a placeholder (`{feature_dir}`, supplied by the
            # walker) must not stop the program itself being checked
            if PLACEHOLDER_RE.search(token):
                f.warn("gates", f"{path.name}: gate `{node.get('id')}` "
                                f"program comes from a bind ({token}) — "
                                "verified at arm")
                continue
            if flowspec.resolve_program(token, project, plugin_root) is None:
                f.fail("gates", f"{path.name}: gate `{node.get('id')}` needs "
                                f"`{token}`, which is not under {project}, "
                                "the plugin root, or PATH")


def check_craft(path: Path, doc: dict, project: Path, plugin_root: Path,
                f: Findings) -> None:
    """Every craft an agent node declares must resolve — project
    `.flow/craft/` first, then the plugin root.

    Craft is not a gate: nothing mechanical notices when it is skipped
    (that is exactly why I5 forces the craft that matters to become a
    ledger task). But craft that cannot be RESOLVED is craft that
    certainly will not be used, and that much is checkable, so it is
    checked. Run 0001's finding F4 is the cost of not checking it: the
    build node's declared reviewers were never dispatched, and the
    eight escaped defects were the measured price.

    An uninstalled plugin root is a WARN, not a FAIL — the same
    distinction the gate check makes between what this file can know
    and what someone else verifies."""
    plugin_present = plugin_root is not None and plugin_root.exists()
    for nid, entry in flowspec.craft_of(doc):
        if flowspec.resolve_craft(entry, project, plugin_root) is not None:
            continue
        if not plugin_present and "/" in entry and not entry.startswith("."):
            f.warn("craft", f"{path.name}: `{nid}` declares `{entry}`, which "
                            f"is not under {project}/.flow/craft/ and the "
                            f"plugin root ({plugin_root}) is not installed")
            continue
        f.fail("craft", f"{path.name}: `{nid}` declares `{entry}`, which "
                        f"resolves to nothing (looked under "
                        f"{project}/.flow/craft/, {project}, {plugin_root})")


def main() -> int:
    ap = argparse.ArgumentParser(description="Static gate for netdust-flow files")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compile", action="store_true",
                    help="write a .json twin for every file that lints clean")
    ap.add_argument("--check-gates", action="store_true",
                    help="every gate program named by the flow must exist")
    ap.add_argument("--check-craft", action="store_true",
                    help="every craft an agent node declares must resolve")
    ap.add_argument("--project", type=Path, default=Path.cwd(),
                    help="project root relative gate programs resolve against")
    ap.add_argument("--plugin-root", type=Path,
                    default=Path.home() / ".claude" / "plugins"
                    / "netdust-agent",
                    help="fallback root for shared gates and craft")
    ap.add_argument("--bind", action="append", default=[], metavar="NAME=VALUE",
                    help="resolve a {placeholder} so --check-gates can check "
                         "it for real instead of warning")
    args = ap.parse_args()

    binds = {}
    for b in args.bind:
        if "=" not in b:
            print(f"FAIL  [usage]  bad --bind `{b}` (NAME=VALUE)")
            return 1
        k, v = b.split("=", 1)
        binds[k] = v

    f = Findings()
    for path in args.paths:
        if not path.exists():
            f.fail("io", f"{path}: not found")
            continue
        local = Findings()
        project = args.project.resolve()
        plugin_root = args.plugin_root.expanduser()
        doc = load_flat(path, project, local)
        if doc is not None:
            lint_file(path, doc, local)
            if args.check_gates:
                check_gates(path, doc, project, plugin_root, binds, local)
            if args.check_craft:
                check_craft(path, doc, project, plugin_root, local)
        f.items.extend(local.items)
        if (args.compile and doc is not None and not local.failed
                and path.suffix != ".json"):
            # the FLATTENED graph: the walker never sees `extends`
            twin = path.with_suffix(".json")
            twin.write_text(json.dumps(doc, indent=2) + "\n")
            print(f"ok    [compile]  {path.name} -> {twin.name}")

    if args.json:
        print(json.dumps(
            [{"status": s, "check": c, "detail": d} for s, c, d in f.items],
            indent=2))
    else:
        for status, check, detail in f.items:
            print(f"{status}  [{check}]  {detail}")
        n_fail = sum(1 for s, _, _ in f.items if s == "FAIL")
        n_warn = sum(1 for s, _, _ in f.items if s == "WARN")
        print(f"flow-lint: {len(args.paths)} file(s) — "
              f"{n_fail} FAIL, {n_warn} WARN")
    return 1 if f.failed else 0


if __name__ == "__main__":
    sys.exit(main())
