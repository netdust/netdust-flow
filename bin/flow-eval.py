#!/usr/bin/env python3
"""flow-eval.py — aggregate run journals into a where-does-it-struggle
report. Nothing is maintained; everything is computed from the journal
on request (the ledger.py philosophy applied to process instead of
state).

    flow-eval.py <feature-dir|journal.jsonl> ... [--json]

Input: `.flow-journal.jsonl` files written by hooks/loop-gate.py in
flow mode — one JSONL event per gate execution (red exits included)
and one per stop decision, each stamped with a run id and the content
hash of the compiled flow twin that drove it.

Output: runs grouped into COHORTS by flow@hash, so editing a flow
compiles to a new hash and the next runs form a new cohort — compare
cohorts, edit the YAML, repeat. That is the whole adaptation loop:
the journal measures, the human adapts, the lint recompiles. No part
of this tool feeds anything back into a flow automatically.

Reading the numbers honestly: a gate's exit code is a ROUTING value,
not universally pass/fail — gate-ledger exiting 1 seventeen times is
the build loop doing its job; the signal is the SIZE of that number
across runs (iterations-to-green), not its existence. first-pass is
meaningful for check gates (gate-spec, gate-plan, seal gates), less so
for loop gates. The report prints distributions and lets you judge.

Exit codes: 0 report printed · 1 no journal entries found · 2 usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def load(paths: list[Path]) -> list[tuple[str, dict]]:
    """(feature label, event) pairs, file order — which is append order,
    which is chronological within one journal."""
    out = []
    for p in paths:
        jp = p if p.suffix == ".jsonl" else p / ".flow-journal.jsonl"
        label = str(p.parent if p.suffix == ".jsonl" else p)
        if not jp.exists():
            continue
        for raw in jp.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(ev, dict) and ev.get("run"):
                out.append((label, ev))
    return out


def group_runs(entries: list[tuple[str, dict]]) -> list[dict]:
    runs: dict[tuple[str, str], dict] = {}
    for label, ev in entries:
        key = (label, str(ev["run"]))
        r = runs.setdefault(key, {
            "run": str(ev["run"]), "feature": label,
            "flow": ev.get("flow", "?"), "fhash": ev.get("fhash", "?"),
            "events": []})
        r["events"].append(ev)
    for r in runs.values():
        stops = [e for e in r["events"] if e.get("event") == "stop"]
        gates = [e for e in r["events"] if e.get("event") == "gate"]
        r["stops"] = len(stops)
        r["iters"] = max((int(e.get("iter", 0)) for e in stops), default=0)
        r["yields"] = sum(1 for e in stops if e.get("decision") == "yield")
        r["gates"] = len(gates)
        r["reds"] = sum(1 for e in gates if e.get("exit") != 0)
        last = stops[-1]["decision"] if stops else "?"
        # a run whose last decision is block/yield has no terminal stop
        # recorded yet — it is either still armed or was disarmed by hand
        r["outcome"] = last if last.startswith("disarm") else f"{last} (open)"
    return sorted(runs.values(), key=lambda r: (r["feature"], r["run"]))


def cohort_stats(runs: list[dict]) -> dict:
    """Per (flow, fhash): gate exit distributions, first-pass, mean
    executions-to-first-green, block-stops and yields per node."""
    cohorts: dict[str, dict] = {}
    for r in runs:
        key = f"{r['flow']}@{r['fhash']}"
        c = cohorts.setdefault(key, {"runs": 0, "gate": {}, "block": Counter(),
                                     "yield": Counter(), "gate_errors": Counter()})
        c["runs"] += 1
        per_node_exits: dict[str, list[int]] = {}
        for e in r["events"]:
            if e.get("event") == "gate":
                per_node_exits.setdefault(str(e["node"]), []).append(
                    int(e.get("exit", -1)))
            elif e.get("event") == "gate-error":
                c["gate_errors"][str(e["node"])] += 1
            elif e.get("event") == "stop":
                node = str(e.get("node", "?"))
                if e.get("decision") == "block":
                    c["block"][node] += 1
                elif e.get("decision") == "yield":
                    c["yield"][node] += 1
        for node, exits in per_node_exits.items():
            g = c["gate"].setdefault(node, {
                "execs": 0, "exits": Counter(), "runs": 0,
                "first_pass": 0, "to_green": []})
            g["execs"] += len(exits)
            g["exits"].update(exits)
            g["runs"] += 1
            if exits[0] == 0:
                g["first_pass"] += 1
            if 0 in exits:
                g["to_green"].append(exits.index(0) + 1)
    return cohorts


def fmt_exits(counter: Counter) -> str:
    return " ".join(f"{code}×{n}" for code, n in sorted(counter.items()))


def report(runs: list[dict], cohorts: dict) -> None:
    features = sorted({r["feature"] for r in runs})
    heads = ", ".join(f"{k} ({v['runs']})" for k, v in sorted(cohorts.items()))
    print(f"FLOW-EVAL — {len(runs)} run(s) · {len(features)} feature "
          f"dir(s) · cohorts: {heads}")
    print()
    print("runs")
    wid = max(len(r["run"]) for r in runs)
    for r in runs:
        print(f"  {r['run']:<{wid}}  {r['feature']}  "
              f"{r['flow']}@{r['fhash']}  stops={r['stops']} "
              f"iters={r['iters']} yields={r['yields']} "
              f"red-gates={r['reds']}/{r['gates']}  {r['outcome']}")
    for key, c in sorted(cohorts.items()):
        print()
        print(f"cohort {key} — {c['runs']} run(s)")
        if c["gate"]:
            print("  gates (exit is a routing value; judge loop gates by "
                  "mean-to-green, check gates by first-pass)")
            for node, g in sorted(c["gate"].items(),
                                  key=lambda kv: -kv[1]["execs"]):
                green = (f"{sum(g['to_green'])/len(g['to_green']):.1f} "
                         f"(n={len(g['to_green'])})"
                         if g["to_green"] else "never")
                print(f"    {node:<18} execs={g['execs']:<4} "
                      f"exits: {fmt_exits(g['exits']):<16} "
                      f"first-pass={g['first_pass']}/{g['runs']}  "
                      f"mean-to-green={green}")
        for title, counter in (("block-stops (iterations landed on an "
                                "agent node, per run)", c["block"]),
                               ("human yields (per run)", c["yield"]),
                               ("gate errors (config, not checks)",
                                c["gate_errors"])):
            if counter:
                print(f"  {title}")
                for node, n in counter.most_common():
                    print(f"    {node:<18} {n / c['runs']:.1f}")
        hot = []
        worst_green = max(
            ((node, sum(g["to_green"]) / len(g["to_green"]))
             for node, g in c["gate"].items() if g["to_green"]),
            key=lambda kv: kv[1], default=None)
        if worst_green and worst_green[1] > 1.5:
            hot.append(f"{worst_green[0]} mean-to-green "
                       f"{worst_green[1]:.1f}")
        if c["block"]:
            node, n = c["block"].most_common(1)[0]
            hot.append(f"{node} {n / c['runs']:.1f} block-stops/run")
        if hot:
            print("  hotspots: " + " · ".join(hot))


def as_json(runs: list[dict], cohorts: dict) -> dict:
    slim = [{k: v for k, v in r.items() if k != "events"} for r in runs]
    coh = {}
    for key, c in cohorts.items():
        coh[key] = {
            "runs": c["runs"],
            "gates": {node: {"execs": g["execs"],
                             "exits": {str(k): v
                                       for k, v in g["exits"].items()},
                             "runs": g["runs"],
                             "first_pass": g["first_pass"],
                             "to_green": g["to_green"]}
                      for node, g in c["gate"].items()},
            "block_stops": dict(c["block"]),
            "yields": dict(c["yield"]),
            "gate_errors": dict(c["gate_errors"]),
        }
    return {"runs": slim, "cohorts": coh}


def main() -> int:
    ap = argparse.ArgumentParser(description="aggregate flow run journals")
    ap.add_argument("paths", nargs="+", type=Path,
                    metavar="feature-dir|journal.jsonl")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    entries = load(args.paths)
    if not entries:
        print("flow-eval: no journal entries found (looked for "
              ".flow-journal.jsonl under the given paths)")
        return 1
    runs = group_runs(entries)
    cohorts = cohort_stats(runs)
    if args.as_json:
        print(json.dumps(as_json(runs, cohorts), indent=2))
    else:
        report(runs, cohorts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
