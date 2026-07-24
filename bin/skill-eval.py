#!/usr/bin/env python3
"""skill-eval.py — the grounded capability gate for a skill. Runs a
skill's eval cases against produced outputs and scores them
DETERMINISTICALLY, so "did the skill get better" is a gate exit code,
not an opinion. Stdlib only.

    skill-eval.py <skill-dir> --outputs <outputs.jsonl>

  <skill-dir>/eval/cases.jsonl   one JSON object per case:
    {"id": "C-1", "lesson": "L-abc", "input": "...",
     "assert": [{"kind": "min_links", "n": 3},
                {"kind": "not_contains", "pattern": "guarantee"}]}
  <outputs.jsonl>                 the skill's output for each case:
    {"id": "C-1", "output": "...text the candidate skill produced..."}

Assertion kinds (deterministic — a gate must be):
    min_links n · min_chars n · has_section NAME ·
    contains PATTERN · not_contains PATTERN · regex PATTERN
Lessons that CANNOT be reduced to a deterministic assertion (tone,
nuance) are not encoded here — they stay with the fresh-context
reviewer and the human seal. The automated gate owns the mechanizable
lessons (structure, sourcing, required fields); judgment stays human.

Why deterministic: this gate is what keeps the improve-skill loop from
Goodharting itself. Cases are GROUNDED (each cites a real lesson), the
proposer never sees this file's assertions while revising, and a
passing case is the ONLY thing that retires its lesson. The eval is a
proxy; the un-gameable truth is the live cohort in flow-eval.

stdout contract (read by a gate):
    SKILLEVAL: <PASS|FAIL> — <passed>/<total>
    progress: passed=<n> total=<n>
    passed cases: C-1 C-3         (so the pruner retires only these)
Exit 0 iff every case passes · 1 some failed · 2 usage/no cases.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"https?://\S+")
SECTION = lambda name: re.compile(r"^##+\s*" + re.escape(name), re.M | re.I)


def load_jsonl(p: Path) -> list[dict]:
    out = []
    for raw in p.read_text().splitlines():
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return out


def check(a: dict, output: str) -> tuple[bool, str]:
    kind = a.get("kind")
    if kind == "min_links":
        n = len(LINK_RE.findall(output))
        return n >= a.get("n", 1), f"links {n} < {a.get('n', 1)}"
    if kind == "min_chars":
        return len(output) >= a.get("n", 1), f"chars {len(output)} < {a.get('n', 1)}"
    if kind == "has_section":
        return bool(SECTION(a["name"]).search(output)), f"missing section ## {a.get('name')}"
    if kind == "contains":
        return a["pattern"] in output, f"missing {a.get('pattern')!r}"
    if kind == "not_contains":
        return a["pattern"] not in output, f"contains forbidden {a.get('pattern')!r}"
    if kind == "regex":
        return bool(re.search(a["pattern"], output, re.I | re.M)), f"no match {a.get('pattern')!r}"
    return False, f"unknown assertion kind {kind!r}"


def main() -> int:
    ap = argparse.ArgumentParser(description="grounded skill capability gate")
    ap.add_argument("skill_dir", type=Path)
    ap.add_argument("--outputs", required=True, type=Path)
    args = ap.parse_args()

    cases_path = args.skill_dir / "eval" / "cases.jsonl"
    if not cases_path.exists():
        print(f"SKILLEVAL: FAIL — no cases at {cases_path}")
        return 2
    cases = load_jsonl(cases_path)
    if not cases:
        print("SKILLEVAL: FAIL — 0 cases (an unmeasured skill cannot pass)")
        return 2
    if not args.outputs.exists():
        print(f"SKILLEVAL: FAIL — no outputs at {args.outputs}")
        return 2
    outputs = {o.get("id"): o.get("output", "") for o in load_jsonl(args.outputs)}

    passed = []
    for c in cases:
        cid = c.get("id")
        out = outputs.get(cid)
        if out is None:
            print(f"  FAIL  {cid}  — no output produced for this case")
            continue
        fails = [msg for a in c.get("assert", []) for ok, msg in [check(a, out)] if not ok]
        if fails:
            print(f"  FAIL  {cid}  (lesson {c.get('lesson')}) — {'; '.join(fails)}")
        else:
            print(f"  ok    {cid}  (lesson {c.get('lesson')})")
            passed.append(cid)

    total = len(cases)
    ok = len(passed) == total
    print(f"SKILLEVAL: {'PASS' if ok else 'FAIL'} — {len(passed)}/{total}")
    print(f"progress: passed={len(passed)} total={total}")
    print("passed cases: " + " ".join(passed))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
