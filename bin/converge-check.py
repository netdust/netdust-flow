#!/usr/bin/env python3
"""converge-check.py — attested convergence evidence (I7).

Verification asks: is the implementation correct per the CURRENT spec?
Convergence asks: does the spec still faithfully represent the ORIGINAL
ask? This gate verifies the artifact of that judgment — a fresh-context
convergence review — bound to the exact task, spec and tree it judged.
Proven by the agent-evals-v0 pair (runs 0002/0003): without it the road
delivered a consumer-less endpoint with every gate green; with it, a
neutrally-prompted fresh reviewer caught the exact dropped deliverable
at plan time, citing the ask's own wording.

    converge-check.py <feature-dir> --task <file> [--not <identity> ...]

Requires <feature-dir>/reviews/convergence.md:

    VERDICT: CONVERGED            (anything else exits 1)
    task: <sha256 of the --task file>
    spec: <sha256 of <feature-dir>/spec.md>
    tree: <git rev-parse HEAD^{tree}>
    reviewer: <who judged — not an excluded identity>

Exit 0 only when the verdict is CONVERGED and every binding matches the
CURRENT state. A revised spec or task stales the report by construction.
"""
import hashlib
import subprocess
import sys
from pathlib import Path


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    argv = sys.argv[1:]
    excluded = []
    task = None
    while "--not" in argv:
        i = argv.index("--not"); excluded.append(argv[i+1].strip().lower()); del argv[i:i+2]
    if "--task" in argv:
        i = argv.index("--task"); task = Path(argv[i+1]); del argv[i:i+2]
    if len(argv) != 1 or task is None:
        print("FAIL  [converge-check]  usage: converge-check.py <fd> --task FILE [--not id ...]")
        return 1
    fd = Path(argv[0])
    report = fd / "reviews" / "convergence.md"
    if not report.exists():
        print(f"FAIL  [converge-check]  no convergence review at {report}")
        return 1
    text = report.read_text()
    def line(prefix):
        return next((l[len(prefix):].strip() for l in text.splitlines()
                     if l.startswith(prefix)), "")
    if not text.startswith("VERDICT: CONVERGED"):
        print(f"FAIL  [converge-check]  verdict is not CONVERGED — the spec "
              "does not faithfully represent the original ask; revise the "
              "plan (missing items listed in the report)")
        return 1
    if line("task:") != sha(task):
        print("FAIL  [converge-check]  report not bound to the current task file")
        return 1
    if line("spec:") != sha(fd / "spec.md"):
        print("FAIL  [converge-check]  report not bound to the CURRENT spec — "
              "spec changed since the judgment; re-converge")
        return 1
    p = subprocess.run(["git", "rev-parse", "HEAD^{tree}"],
                       capture_output=True, text=True)
    if f"tree: {p.stdout.strip()}" not in text:
        print("FAIL  [converge-check]  report not bound to the current tree")
        return 1
    reviewer = line("reviewer:")
    if not reviewer or reviewer.lower() in excluded:
        print(f"FAIL  [converge-check]  reviewer `{reviewer or '(none)'}` "
              "missing or excluded — the spec's author may not certify its "
              "own convergence")
        return 1
    print(f"ok    [converge-check]  CONVERGED — task+spec+tree bound, by {reviewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
