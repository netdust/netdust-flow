#!/usr/bin/env python3
"""flow-lint.py — netdust-flow v0

Static gate for flow definitions. Sibling of gate-check.py: findings,
FAIL/WARN lines, exit code — no opinions, no LLM.

Invariants it exists to enforce:
  I1  every edge condition is machine-readable — `<state key> <op>
      <literal>` with ops == != > >= < <= in. Prose is a FAIL.
  I2  __end__ is reachable only from gate or human nodes.
  I4  (v0.2) the machine is well-formed as an FSM: every declared node
      has at least one outgoing edge — __end__ is the only final state.
      A dead-end node is a FAIL; an edge into the absorbing __human__
      pseudo-state is a WARN (prefer a human node with out-edges and a
      seal gate — see bin/seal.py).

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


def lint_file(path: Path, f: Findings) -> None:
    try:
        doc = yaml.safe_load(path.read_text())
    except Exception as e:
        f.fail("parse", f"{path.name}: {e}")
        return
    if not isinstance(doc, dict):
        f.fail("root", f"{path.name}: top level must be a mapping")
        return

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Static gate for netdust-flow files")
    ap.add_argument("paths", nargs="+", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--compile", action="store_true",
                    help="write a .json twin for every file that lints clean")
    args = ap.parse_args()

    f = Findings()
    for path in args.paths:
        if not path.exists():
            f.fail("io", f"{path}: not found")
            continue
        local = Findings()
        lint_file(path, local)
        f.items.extend(local.items)
        if args.compile and not local.failed and path.suffix != ".json":
            twin = path.with_suffix(".json")
            twin.write_text(json.dumps(yaml.safe_load(path.read_text()),
                                       indent=2) + "\n")
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
