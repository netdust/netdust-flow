#!/usr/bin/env python3
"""review-check.py — attested review evidence, tree-bound (I5).

The check a review task runs through attest.py. A review is evidence
only if a report exists AND its verdict is CLEAN AND it is bound to
the exact git tree it reviewed — a review of yesterday's dossier
proves nothing about today's.

    review-check.py <record-folder> <review-name>

Requires <record-folder>/reviews/<review-name>.md containing:

    VERDICT: CLEAN
    tree: <git rev-parse HEAD^{tree} of the reviewed worktree>

The reviewer (a fresh-context agent) writes the report; findings
force fixes; a NEW review of the new tree is required after any
change. Reports are gitignored working papers — the durable evidence
is the attest note recording that this check passed against a named
tree. Exit 0 evidence holds · 1 otherwise.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("FAIL  [review-check]  usage: review-check.py <record-folder> <name>")
        return 1
    folder, name = Path(sys.argv[1]), sys.argv[2]
    report = folder / "reviews" / f"{name}.md"
    if not report.exists():
        print(f"FAIL  [review-check]  no report at {report}")
        return 1
    text = report.read_text()
    if "VERDICT: CLEAN" not in text:
        print(f"FAIL  [review-check]  {name}: verdict is not CLEAN")
        return 1
    p = subprocess.run(["git", "rev-parse", "HEAD^{tree}"],
                       capture_output=True, text=True)
    tree = p.stdout.strip()
    if p.returncode != 0 or not tree:
        print("FAIL  [review-check]  cannot resolve HEAD tree")
        return 1
    if f"tree: {tree}" not in text:
        print(f"FAIL  [review-check]  {name}: report not bound to the "
              f"current tree ({tree[:12]}) — re-review after changes")
        return 1
    print(f"ok    [review-check]  {name} CLEAN on tree {tree[:12]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
