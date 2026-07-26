#!/usr/bin/env python3
"""craft-memory.py — the craft's memory: lessons harvested from a run's
own evidence, so a skill can learn from what actually failed. Stdlib
only; append-only; provenance-carrying.

    craft-memory.py extract <feature-dir> --skill <name> [--root DIR]
    craft-memory.py list    <skill>                      [--root DIR] [--all]
    craft-memory.py cover   <skill> --skill-dir <dir>    [--root DIR]
    craft-memory.py retire  <skill> <lesson-id> --by <run> [--root DIR]

A LESSON is a grounded record of something that went wrong, tied to the
run that produced it — never invented. Two sources, both already emitted
by the runtime:

  * seal rejections — a human's `rejected` seal with a note ("not our
    brand voice") is the gold lesson: a real correction.
  * gate reds       — a gate that failed with a reason ("research.md
    trivial (<300 chars)") in the run journal.

Design invariants (why this stays safe, see docs/craft-loop.md):
  - Append-only, latest-wins on status (the seal/attest pattern). A
    lesson is EVIDENCE, not a cache — it carries its source run.
  - `retire` is VERIFIER-DRIVEN: a lesson leaves `live` only when
    something proves its failure stopped reproducing (--by <eval-run>).
    The proposer in improve-skill NEVER retires; a separate pruner does,
    reading the eval result. A lesson leaves memory through the front
    door (its case passes), never the back door (the optimizer wants it
    gone).
  - Root defaults to ./craft-memory/<skill>.jsonl.

Exit 0 ok · 1 findings (cover: uncovered lessons; list: none) · 2 usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from subprocess import run as _run

SEAL_REF = "refs/notes/seal"
EXIT_RE = re.compile(r"\bexit ([1-9]\d*): (.+)$")


def sh(*args: str, cwd: Path) -> tuple[int, str]:
    p = _run(list(args), capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout


def lesson_id(skill: str, source: str, symptom: str, run: str) -> str:
    key = f"{skill}|{source}|{symptom.strip().lower()}|{run}"
    return "L-" + hashlib.sha1(key.encode()).hexdigest()[:10]


def store_path(root: Path, skill: str) -> Path:
    return root / f"{skill}.jsonl"


def load(root: Path, skill: str) -> list[dict]:
    p = store_path(root, skill)
    if not p.exists():
        return []
    out = []
    for raw in p.read_text().splitlines():
        raw = raw.strip()
        if raw:
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return out


def append(root: Path, skill: str, rec: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(store_path(root, skill), "a") as f:
        f.write(json.dumps(rec) + "\n")


def live_lessons(root: Path, skill: str) -> dict[str, dict]:
    """Latest-wins fold: a lesson is live unless a later record retired
    it. Returns {id: lesson-record} for live lessons only."""
    lessons: dict[str, dict] = {}
    status: dict[str, str] = {}
    for rec in load(root, skill):
        lid = rec.get("id")
        if not lid:
            continue
        if rec.get("kind") == "lesson":
            lessons.setdefault(lid, rec)
            status.setdefault(lid, "live")
        elif rec.get("kind") == "retire":
            status[lid] = "resolved"
    return {lid: lessons[lid] for lid in lessons if status.get(lid) == "live"}


# ── extract ──────────────────────────────────────────────────────────

def canon(feature: str, cwd: Path) -> str:
    p = Path(feature)
    absolute = p if p.is_absolute() else cwd / p
    try:
        import os
        return os.path.relpath(absolute.resolve(), cwd.resolve())
    except ValueError:
        return str(absolute)


def extract(feature_dir: str, skill: str, root: Path, cwd: Path) -> int:
    want = canon(feature_dir, cwd)
    found: list[dict] = []

    # (1) gate reds from the run journal
    journal = cwd / feature_dir / ".flow-journal.jsonl"
    if journal.exists():
        for raw in journal.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError:
                continue
            m = EXIT_RE.search(str(ev.get("reason", "")))
            if m:
                found.append({"source": "gate", "symptom": m.group(2).strip(),
                              "run": ev.get("run", ""), "ts": ev.get("ts", "")})

    # (2) seal rejections (the gold: a human's recorded correction)
    rc, listing = sh("git", "notes", f"--ref={SEAL_REF}", "list", cwd=cwd)
    if rc == 0:
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) != 2:
                continue
            _, commit = parts
            rc2, body = sh("git", "notes", f"--ref={SEAL_REF}", "show",
                           commit, cwd=cwd)
            if rc2 != 0:
                continue
            for bl in body.splitlines():
                bl = bl.strip()
                if not bl:
                    continue
                try:
                    rec = json.loads(bl)
                except json.JSONDecodeError:
                    continue
                if (rec.get("decision") == "rejected" and rec.get("note")
                        and rec.get("feature") is not None
                        and canon(rec["feature"], cwd) == want):
                    found.append({"source": "seal", "symptom": rec["note"].strip(),
                                  "run": rec.get("run", ""), "ts": rec.get("ts", "")})

    existing = {r.get("id") for r in load(root, skill)}
    added = 0
    for f in found:
        lid = lesson_id(skill, f["source"], f["symptom"], f["run"] or "?")
        if lid in existing:
            continue                       # idempotent: re-extract is a no-op
        append(root, skill, {
            "kind": "lesson", "id": lid, "skill": skill,
            "source": f["source"], "symptom": f["symptom"],
            "run": f["run"], "feature": want,
            "ts": f["ts"] or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        })
        existing.add(lid)
        added += 1
    print(f"craft-memory: extracted {added} new lesson(s) for `{skill}` "
          f"from {feature_dir} ({len(found)} candidate(s))")
    return 0


# ── list / cover / retire ────────────────────────────────────────────

def cmd_list(skill: str, root: Path, show_all: bool) -> int:
    if show_all:
        recs = [r for r in load(root, skill) if r.get("kind") == "lesson"]
    else:
        recs = list(live_lessons(root, skill).values())
    for r in recs:
        print(f"{r['id']}  [{r['source']}]  {r['symptom']}  "
              f"(run {r.get('run', '?')})")
    print(f"craft-memory: {len(recs)} {'total' if show_all else 'live'} "
          f"lesson(s) for `{skill}`")
    return 0 if recs else 1


def cases_of(skill_dir: Path) -> set[str]:
    cases = skill_dir / "eval" / "cases.jsonl"
    ids = set()
    if cases.exists():
        for raw in cases.read_text().splitlines():
            raw = raw.strip()
            if raw:
                try:
                    ids.add(json.loads(raw).get("lesson"))
                except json.JSONDecodeError:
                    continue
    return ids


def cmd_cover(skill: str, skill_dir: Path, root: Path) -> int:
    """Grounding gate: every LIVE lesson must have an eval case that
    cites it (or be tagged human-judged). A lesson with no case is a
    claim the eval can't check — fail closed."""
    covered = cases_of(skill_dir)
    live = live_lessons(root, skill)
    uncovered = [lid for lid, r in live.items()
                 if lid not in covered and not r.get("human_judged")]
    for lid in uncovered:
        print(f"FAIL  [craft-cover]  lesson {lid} has no eval case "
              f"({live[lid]['symptom'][:50]})")
    if uncovered:
        print(f"craft-memory: {len(uncovered)} live lesson(s) uncovered by "
              f"cases in {skill_dir}/eval/cases.jsonl")
        return 1
    print(f"craft-memory: all {len(live)} live lesson(s) covered by cases")
    return 0


def marker_run(cwd: Path) -> str:
    try:
        return (json.loads((cwd / "tasks" / ".harness-loop.json").read_text())
                .get("run_id") or "manual")
    except Exception:
        return "manual"


def cmd_prune(skill: str, skill_dir: Path, outputs: Path, by: str,
              root: Path, cwd: Path) -> int:
    """The verifier-driven pruner: RE-RUN skill-eval (never trust the
    proposer's word), then retire only the lessons whose cases actually
    pass. A lesson leaves memory through the front door only. Separated
    from `propose` on purpose — the thing that wants a lesson gone is not
    the thing allowed to remove it."""
    ev = _run([sys.executable, str(Path(__file__).parent / "skill-eval.py"),
               str(skill_dir), "--outputs", str(outputs)],
              capture_output=True, text=True, cwd=cwd)
    passed = set()
    for line in ev.stdout.splitlines():
        if line.startswith("passed cases: "):
            passed = set(line[len("passed cases: "):].split())
    # map passed case-ids → their cited lessons
    lesson_by_case: dict[str, str] = {}
    cases = skill_dir / "eval" / "cases.jsonl"
    if cases.exists():
        for raw in cases.read_text().splitlines():
            raw = raw.strip()
            if raw:
                try:
                    c = json.loads(raw)
                    lesson_by_case[c.get("id")] = c.get("lesson")
                except json.JSONDecodeError:
                    continue
    by = by or marker_run(cwd)
    live = live_lessons(root, skill)
    retired = 0
    for cid in passed:
        lid = lesson_by_case.get(cid)
        if lid and lid in live:
            append(root, skill, {"kind": "retire", "id": lid, "by": by,
                                 "case": cid,
                                 "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
            print(f"craft-memory: retired {lid} — case {cid} passes on the "
                  f"adopted skill (confirmed by {by})")
            retired += 1
    remaining = len(live_lessons(root, skill))
    print(f"craft-memory: pruned {retired}; {remaining} live lesson(s) remain")
    return 0


def cmd_retire(skill: str, lesson: str, by: str, root: Path) -> int:
    live = live_lessons(root, skill)
    if lesson not in live:
        print(f"craft-memory: {lesson} is not a live lesson for `{skill}` "
              f"— nothing retired")
        return 1
    if not by:
        print("craft-memory: retire needs --by <eval-run> (retirement is "
              "verifier-driven, never a bare claim)")
        return 2
    append(root, skill, {"kind": "retire", "id": lesson, "by": by,
                         "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    print(f"craft-memory: retired {lesson} (confirmed by {by})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="the craft's memory")
    ap.add_argument("--root", type=Path, default=Path("craft-memory"))
    sub = ap.add_subparsers(dest="mode", required=True)
    ex = sub.add_parser("extract"); ex.add_argument("feature_dir"); ex.add_argument("--skill", required=True)
    ls = sub.add_parser("list"); ls.add_argument("skill"); ls.add_argument("--all", action="store_true")
    cv = sub.add_parser("cover"); cv.add_argument("skill"); cv.add_argument("--skill-dir", required=True, type=Path)
    rt = sub.add_parser("retire"); rt.add_argument("skill"); rt.add_argument("lesson"); rt.add_argument("--by", default="")
    pr = sub.add_parser("prune"); pr.add_argument("skill"); pr.add_argument("--skill-dir", required=True, type=Path)
    pr.add_argument("--outputs", required=True, type=Path); pr.add_argument("--by", default="")
    args = ap.parse_args()
    cwd = Path.cwd()
    root = args.root
    if args.mode == "extract":
        return extract(args.feature_dir, args.skill, root, cwd)
    if args.mode == "list":
        return cmd_list(args.skill, root, args.all)
    if args.mode == "cover":
        return cmd_cover(args.skill, args.skill_dir, root)
    if args.mode == "retire":
        return cmd_retire(args.skill, args.lesson, args.by, root)
    if args.mode == "prune":
        return cmd_prune(args.skill, args.skill_dir, args.outputs, args.by, root, cwd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
