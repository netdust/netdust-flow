#!/usr/bin/env python3
"""flow-check.py — the flow walker (netdust-flow v0.1)

Successor of loop-check.py: instead of assuming one hard-coded cycle
(build ⟲ ledger), it walks a declared flow file. Same philosophy — the
answer is derived ONLY from artifacts and exit codes, never from an
agent asserting "done".

    usage: flow-check.py <feature-dir> --flow <flow.yaml|.json> --node <id>
                         [--bind name=value ...] [--plugin-root DIR]
                         [--timeout SECONDS] [--cwd DIR]

The walk starts AT the node the session just worked on (--node, from the
marker) and advances along declared edges:

  * gate nodes are EXECUTED (exit code recorded as state `gate.exit`),
    then their conditional edges are evaluated;
  * landing on an agent node   → exit 1 CONTINUE, naming that node;
  * landing on a human node or __human__ → exit 2 BLOCKED;
  * landing on __end__         → exit 0 FINISHED.

A start node of kind human counts as satisfied (the human acted, the
session resumed and stopped) and the walk advances through its edge.

stdout contract (superset of loop-check's — loop-gate keeps working):

    FLOW: CONTINUE — node: build — gate-ledger exit 1: T03 next
    next: build
    progress: done=2 total=7

  line 1  verdict + reason
  next:   the node the hook must persist into the marker
  progress prefers, in order: the LAST `progress:` line a gate printed
  during this walk (evidence-derived — e.g. ledger.py's attest counts),
  then tasks.md checkbox counts, then node position. Checkboxes feed
  the dry-loop counter only when no gate offered evidence (I3: shrink
  agent-written signals wherever a verifier's signal exists).

Human decisions (v0.2, I4): a human node is a yield point only. The
decision re-enters the machine as a seal record (bin/seal.py) read by
the gate that follows the human node — so resuming a session never
approves anything, and rejection routes along its own edge. __human__
is still honored for backward compatibility but is an absorbing state;
flow-lint WARNs on it.

Safety: conditions are parsed with a closed grammar (key op literal;
ops == != > >= < <= in) — no eval(). Gates run without a shell. Every
config problem (unknown node, unmatched edge, unbound {placeholder},
revisited gate in one walk) is BLOCKED, never a guess. Fail-open
crash behavior stays the hook's job, exactly as today.

Flow loading: a compiled .json twin (written by `flow-lint --compile`)
is preferred so the Stop-hook path needs no PyYAML; the .yaml source is
read only when no twin exists and PyYAML is importable.

Hook migration (the whole v0.1 diff to loop-gate.py):
  1. `/flow <dir> <flow>` arms the marker with two extra fields:
     {"flow": "flows/deliver.json", "node": "brainstorm", ...}
  2. loop-gate calls this script with --flow/--node from the marker.
  3. loop-gate persists the `next:` line back into marker["node"].
  Budget, dry-loop detection, disarm rules, tracing: unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

TASK_RE = re.compile(r"^- \[( |x|X)\] (T\d+)\b(.*)$")
COND_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(==|!=|>=|<=|>|<|in)\s+(.+?)\s*$")
PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")
MAX_HOPS = 50

FINISHED, CONTINUE, BLOCKED = 0, 1, 2


# ── flow loading ─────────────────────────────────────────────────────

def load_flow(path: Path) -> dict:
    if path.suffix == ".json":
        return json.loads(path.read_text())
    twin = path.with_suffix(".json")
    if twin.exists():
        return json.loads(twin.read_text())
    try:
        import yaml  # lint-time dependency; hook path prefers the twin
    except ImportError:
        raise RuntimeError(
            f"{path.name}: no compiled .json twin and PyYAML unavailable — "
            "run `flow-lint --compile` first")
    return yaml.safe_load(path.read_text())


# ── condition grammar (closed; no eval) ──────────────────────────────

def parse_literal(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [parse_literal(x) for x in inner.split(",")] if inner else []
    if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
        return s[1:-1]
    try:
        return int(s)
    except ValueError:
        pass
    if s in ("true", "True"):
        return True
    if s in ("false", "False"):
        return False
    return s


def resolve(state: dict, dotted: str):
    cur = state
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def eval_cond(expr: str, state: dict) -> bool:
    m = COND_RE.match(str(expr))
    if not m:
        raise ValueError(f"condition `{expr}` is not machine-readable")
    lhs = resolve(state, m.group(1))
    op = m.group(2)
    rhs = parse_literal(m.group(3))
    if op == "in":
        return lhs in rhs if isinstance(rhs, list) else False
    if op == "==":
        return lhs == rhs
    if op == "!=":
        return lhs != rhs
    try:
        l, r = int(lhs), int(rhs)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return {"<": l < r, "<=": l <= r, ">": l > r, ">=": l >= r}[op]


# ── gate execution ───────────────────────────────────────────────────

def run_gate(node: dict, binds: dict, plugin_root: Path,
             timeout: int, cwd: Path) -> tuple[int | None, str, str | None]:
    """Returns (exit_code, brief, progress_line) or (None, reason, None)."""
    cmd = str(node["run"])
    for key, val in binds.items():
        cmd = cmd.replace("{" + key + "}", str(val))
    leftover = PLACEHOLDER_RE.search(cmd)
    if leftover:
        return None, (f"gate `{node['id']}` has unbound placeholder "
                      f"{leftover.group(0)} — pass --bind"), None
    argv = shlex.split(cmd)
    prog = Path(argv[0])
    if not prog.is_absolute():
        candidate = plugin_root / argv[0]
        if candidate.exists():
            prog = candidate
    if str(prog).endswith(".py"):
        argv = [sys.executable, str(prog)] + argv[1:]
    else:
        argv = [str(prog)] + argv[1:]
    try:
        p = subprocess.run(argv, capture_output=True, text=True,
                           timeout=timeout, cwd=str(cwd))
    except Exception as e:
        return None, f"gate `{node['id']}` failed to run ({type(e).__name__})", None
    lines = [l.strip() for l in p.stdout.splitlines() if l.strip()]
    fails = [l for l in lines if "FAIL" in l][:3]
    brief = "; ".join(fails) if fails else (lines[0] if lines else "")
    prog = next((l for l in lines if l.startswith("progress: ")), None)
    return p.returncode, brief, prog


# ── progress (unchanged dry-loop food) ───────────────────────────────

def progress(feature_dir: Path, node_pos: int, node_total: int) -> str:
    tasks_path = feature_dir / "tasks.md"
    if tasks_path.exists():
        done = total = 0
        in_fence = False
        for line in tasks_path.read_text().splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = TASK_RE.match(line)
            if m:
                total += 1
                if m.group(1).lower() == "x":
                    done += 1
        return f"progress: done={done} total={total}"
    return f"progress: done={node_pos} total={node_total}"


# ── the walk ─────────────────────────────────────────────────────────

def walk(doc: dict, start: str, feature_dir: Path, binds: dict,
         plugin_root: Path, timeout: int, cwd: Path) -> int:
    nodes = {n["id"]: n for n in doc.get("nodes", [])}
    order = [n["id"] for n in doc.get("nodes", [])]
    out_edges: dict[str, list[dict]] = {}
    for e in doc.get("edges", []):
        out_edges.setdefault(str(e["from"]), []).append(e)

    state: dict = {"gate": {}}
    cur = start
    first = True
    ran_gates: set[str] = set()
    last_gate = ""
    last_progress: str | None = None

    def emit(line1: str, nxt: str, code: int) -> int:
        pos = order.index(nxt) + 1 if nxt in order else len(order)
        print(line1)
        print(f"next: {nxt}")
        # evidence-derived progress from a gate beats checkbox counting
        print(last_progress or progress(feature_dir, pos, len(order)))
        return code

    for _ in range(MAX_HOPS):
        if cur == "__end__":
            return emit(f"FLOW: FINISHED — `{doc.get('flow')}` complete"
                        + (f" ({last_gate})" if last_gate else ""),
                        "__end__", FINISHED)
        if cur == "__human__":
            return emit(f"FLOW: BLOCKED — human needed ({last_gate})",
                        "__human__", BLOCKED)
        node = nodes.get(cur)
        if node is None and cur != "__start__":
            return emit(f"FLOW: BLOCKED — unknown node `{cur}`", cur, BLOCKED)
        kind = node.get("kind") if node else None  # __start__: edges only

        if not first:
            if kind == "agent":
                reason = last_gate or "next in flow"
                return emit(f"FLOW: CONTINUE — node: {cur} — {reason}",
                            cur, CONTINUE)
            if kind == "human":
                what = ", ".join(node.get("out", [])) or "your decision"
                return emit(f"FLOW: BLOCKED — `{cur}` needs a human: {what}",
                            cur, BLOCKED)

        if node is not None and kind == "gate":
            if cur in ran_gates:
                return emit(f"FLOW: BLOCKED — gate `{cur}` revisited in one "
                            "walk (flow cycle without an agent step)",
                            cur, BLOCKED)
            ran_gates.add(cur)
            rc, brief, prog = run_gate(node, binds, plugin_root, timeout, cwd)
            if rc is None:
                return emit(f"FLOW: BLOCKED — {brief}", cur, BLOCKED)
            state["gate"]["exit"] = rc
            if prog:
                last_progress = prog
            last_gate = f"{cur} exit {rc}" + (f": {brief}" if brief else "")

        chosen = None
        for e in out_edges.get(cur, []):
            when = e.get("when")
            if when is None:
                chosen = e
                break
            try:
                if eval_cond(when, state):
                    chosen = e
                    break
            except ValueError as exc:
                return emit(f"FLOW: BLOCKED — {exc}", cur, BLOCKED)
        if chosen is None:
            return emit(f"FLOW: BLOCKED — no matching edge out of `{cur}` "
                        f"(gate.exit={state['gate'].get('exit')})",
                        cur, BLOCKED)
        cur = str(chosen["to"])
        first = False

    return emit(f"FLOW: BLOCKED — walk exceeded {MAX_HOPS} hops (cycle?)",
                cur, BLOCKED)


def main() -> int:
    ap = argparse.ArgumentParser(description="netdust-flow walker")
    ap.add_argument("feature_dir", type=Path)
    ap.add_argument("--flow", required=True, type=Path)
    ap.add_argument("--node", required=True)
    ap.add_argument("--bind", action="append", default=[],
                    metavar="NAME=VALUE")
    ap.add_argument("--plugin-root", type=Path,
                    default=Path.home() / ".claude" / "plugins" / "netdust-agent")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--cwd", type=Path, default=Path.cwd())
    args = ap.parse_args()

    binds = {"feature_dir": str(args.feature_dir)}
    for b in args.bind:
        if "=" not in b:
            print(f"FLOW: BLOCKED — bad --bind `{b}` (NAME=VALUE)")
            return BLOCKED
        k, v = b.split("=", 1)
        binds[k] = v

    try:
        doc = load_flow(args.flow)
    except Exception as e:
        print(f"FLOW: BLOCKED — cannot load flow: {e}")
        return BLOCKED

    return walk(doc, args.node, args.feature_dir, binds,
                args.plugin_root, args.timeout, args.cwd)


if __name__ == "__main__":
    sys.exit(main())
