#!/usr/bin/env python3
"""spec-gate.py — netdust-flow's OWN spec/plan structure gate.

This repo is a project like any other, so its checks live in its own
project pack (`.flow/`, see docs/project-pack.md) rather than in `bin/`
alongside the runtime. The runtime stays domain-independent; this file
is netdust-flow-the-project's opinion about its own specs, and it is
here so the system can drive its own development (CLAUDE.md binds it
as `Gate check:`).

Bound into the deliver flow as {gate_check_cmd}; drives gate-spec and
gate-plan. Stage-aware, and — per invariant I5 — it REFUSES a plan
whose tasks carry no review cluster: a review that is not a ledger
task did not happen (run 0001, finding F4).

    spec-gate.py <feature-dir>

  spec stage  spec.md exists with ## Problem, ## Requirements, and
              ## Acceptance sections, and at least 3 requirement lines.
  plan stage  (only once plan.md exists) plan.md carries ## Tasks and
              a `Loop budget:` line; tasks.md exists with `- [ ] Tnn`
              lines, each Tnn also named in plan.md; AND at least one
              task line contains the word "review" (I5 — the review
              cluster, attested like any other task).

Exit 0 clean · 1 findings (FAIL lines on stdout).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TASK_RE = re.compile(r"^- \[( |x|X)\] (T\d+)\b(.*)$", re.M)


def main() -> int:
    if len(sys.argv) != 2:
        print("FAIL  [usage]  spec-gate.py <feature-dir>")
        return 1
    fd = Path(sys.argv[1])
    fails: list[str] = []

    spec = fd / "spec.md"
    if not spec.exists():
        fails.append("spec.md missing")
    else:
        text = spec.read_text()
        for section in ("## Problem", "## Requirements", "## Acceptance"):
            if section not in text:
                fails.append(f"spec.md missing `{section}` section")
        reqs = [l for l in text.splitlines() if l.startswith("- R")]
        if len(reqs) < 3:
            fails.append(f"spec.md has {len(reqs)} requirement lines (need 3+)")

    plan = fd / "plan.md"
    if plan.exists():
        ptext = plan.read_text()
        if "## Tasks" not in ptext:
            fails.append("plan.md missing `## Tasks` section")
        if "Loop budget:" not in ptext:
            fails.append("plan.md missing `Loop budget:` line")
        tasks = fd / "tasks.md"
        if not tasks.exists():
            fails.append("plan.md exists but tasks.md missing")
        else:
            matches = TASK_RE.findall(tasks.read_text())
            if not matches:
                fails.append("tasks.md has no `- [ ] Tnn` lines")
            for _, tid, _ in matches:
                if tid not in ptext:
                    fails.append(f"{tid} in tasks.md but not named in plan.md")
            if not any("review" in rest.lower() for _, _, rest in matches):
                fails.append("no review cluster in tasks.md (I5: a review "
                             "that is not a ledger task did not happen)")

    for f in fails:
        print(f"FAIL  [spec-gate]  {f}")
    if not fails:
        print("ok    [spec-gate]  structure clean")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
