#!/usr/bin/env python3
"""review-check.py — attested review evidence, tree-bound (I5).

The check a review task runs through attest.py. A review is evidence
only if a report exists AND its verdict is CLEAN AND it is bound to
the exact git tree it reviewed — a review of yesterday's dossier
proves nothing about today's.

    review-check.py <record-folder> <review-name> [--not <identity> ...]

`--not` names identities that may NOT sign this review — pass the
building node's actor so "the reviewer is not the builder" is a
machine check on the record, not a hope. Still a claim (a builder
could sign a false name), but a false distinct identity is a forged
record — deliberate, auditable — where a same-identity review was
previously just sloppy.

Requires <record-folder>/reviews/<review-name>.md containing:

    VERDICT: CLEAN
    tree: <git rev-parse HEAD^{tree} of the reviewed worktree>
    reviewer: <who performed the review — persona or agent identity>

The reviewer line is a recorded claim, auditable rather than proven
(identity assertions stay testimony — evidence.md); what it buys is
that the run record answers "who reviewed this?" instead of only
"a review existed".

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
    argv = sys.argv[1:]
    excluded: list[str] = []
    while "--not" in argv:
        i = argv.index("--not")
        if i + 1 >= len(argv):
            print("FAIL  [review-check]  --not requires an identity")
            return 1
        excluded.append(argv[i + 1].strip().lower())
        del argv[i:i + 2]
    if len(argv) != 2:
        print("FAIL  [review-check]  usage: review-check.py "
              "<record-folder> <name> [--not <identity> ...]")
        return 1
    folder, name = Path(argv[0]), argv[1]
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
    reviewer = next((l[len("reviewer:"):].strip()
                     for l in text.splitlines()
                     if l.startswith("reviewer:")), "")
    if not reviewer:
        print(f"FAIL  [review-check]  {name}: no `reviewer:` line — the "
              "record must answer WHO reviewed, not just that a review "
              "exists (a recorded claim, auditable; independence is the "
              "dispatch contract's job)")
        return 1
    if reviewer.strip().lower() in excluded:
        print(f"FAIL  [review-check]  {name}: reviewer `{reviewer}` is the "
              "excluded identity — the builder may not sign the review of "
              "its own work. Dispatch a fresh-context reviewer. (Signing a "
              "different name without dispatching one is a forged record, "
              "deliberate and on the record.)")
        return 1
    print(f"ok    [review-check]  {name} CLEAN on tree {tree[:12]} "
          f"by {reviewer}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
