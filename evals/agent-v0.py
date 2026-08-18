#!/usr/bin/env python3
"""Compare two real flow journals using the repository's flow-eval.py.

This is intentionally a measurement harness, not an agent simulator. It
refuses to manufacture observations: both inputs must contain a real
.flow-journal.jsonl and flow-eval.py must successfully parse each one.

Usage:
    python3 evals/agent-v0.py --baseline DIR --netdust DIR
    python3 evals/agent-v0.py --baseline DIR --netdust DIR --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW_EVAL = ROOT / "bin" / "flow-eval.py"


def run_eval(path: Path) -> tuple[int, dict | None, str]:
    journal = path / ".flow-journal.jsonl"
    if not journal.is_file():
        return 1, None, f"missing journal: {journal}"
    proc = subprocess.run(
        [sys.executable, str(FLOW_EVAL), str(journal), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return proc.returncode, None, proc.stdout + proc.stderr
    try:
        return 0, json.loads(proc.stdout), ""
    except json.JSONDecodeError as exc:
        return 1, None, f"flow-eval produced invalid JSON: {exc}"


def summarize(data: dict) -> dict:
    runs = data.get("runs", [])
    cohorts = data.get("cohorts", {})
    return {
        "runs": len(runs),
        "iterations": [r.get("iters", 0) for r in runs],
        "yields": [r.get("yields", 0) for r in runs],
        "red_gates": [r.get("reds", 0) for r in runs],
        "outcomes": [r.get("outcome", "?") for r in runs],
        "cohorts": cohorts,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--netdust", type=Path, required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = {}
    errors = []
    for name, path in (("baseline", args.baseline), ("netdust", args.netdust)):
        code, data, error = run_eval(path)
        if code or data is None:
            errors.append(f"{name}: {error}")
        else:
            results[name] = summarize(data)

    if errors:
        report = {"status": "invalid", "errors": errors, "results": results}
        print(json.dumps(report, indent=2) if args.json else "\n".join(errors))
        return 2

    report = {"status": "ok", "baseline": results["baseline"], "netdust": results["netdust"]}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name in ("baseline", "netdust"):
            r = report[name]
            print(f"{name}: runs={r['runs']} iterations={r['iterations']} "
                  f"yields={r['yields']} red-gates={r['red_gates']} "
                  f"outcomes={r['outcomes']}")
        print("\nNo correctness or false-completion conclusion is made by agent-v0.")
        print("Use the same task and starting tree for the two real runs, then label outcomes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
