#!/usr/bin/env python3
"""ledger.py — derive delivery state from git evidence. Nothing is
maintained; everything is computed on request.

    ledger.py <feature-dir>

Requirements set:  task ids parsed from <feature-dir>/tasks.md
                   (`- [ ] T01 ...`; checkbox state is IGNORED — the
                   box is a human-readable mirror, never a signal).
Evidence set:      attest records (refs/notes/attest) on commits
                   reachable from HEAD.
Verdict:
    exit 0  FINISHED — every task has an exit-0 attest, a SUITE
            attest sits on the current HEAD (commit-level drift
            catch), AND the worktree is clean (tree-level drift
            catch: uncommitted edits after a green SUITE must force
            a re-verification, v0.2).
    exit 1  CONTINUE — names the next unattested unit (or SUITE, or
            the dirty worktree).
    exit 2  BLOCKED  — the next unit is marked [HUMAN].

stdout carries the walker-gate contract:
    LEDGER: <verdict> — <reason>
    progress: done=<attested> total=<tasks>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

NOTES_REF = "refs/notes/attest"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowspec  # noqa: E402 — stdlib-only by contract

# One name, one definition (bin/flowspec.py). Run 0004 F02.
MARKER_REL = flowspec.MARKER_REL


def current_run(cwd: Path) -> str | None:
    """Run id of the armed flow, if any — evidence is scoped to it so a
    re-plan (new run id, same feature + task ids) cannot inherit the
    prior run's attests. When no flow is armed (standalone ledger),
    returns None and scoping falls back to feature-only (display)."""
    try:
        return (json.loads((cwd / MARKER_REL).read_text()).get("run_id")
                or None)
    except Exception:
        return None


def canon_feature(feature: str, cwd: Path) -> str:
    """Canonicalize a feature path so scoping compares the SAME thing
    regardless of how it was written. attest.py/seal.py record the
    feature as passed (usually relative, `specs/x`), while the Stop
    hook drives gates with an ABSOLUTE feature_dir — exact-string
    comparison would spuriously mismatch. Normalize both sides to the
    path relative to the repo root (cwd here)."""
    p = Path(feature)
    absolute = p if p.is_absolute() else cwd / p
    try:
        return os.path.relpath(absolute.resolve(), cwd.resolve())
    except ValueError:
        return str(absolute)


TASK_RE = re.compile(r"^- \[( |x|X)\] (T\d+)\b(.*)$")


def sh(*args: str, cwd: Path) -> tuple[int, str]:
    p = subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout


def tasks_of(feature_dir: Path) -> list[tuple[str, bool]]:
    path = feature_dir / "tasks.md"
    if not path.exists():
        return []
    out, fence = [], False
    for line in path.read_text().splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = TASK_RE.match(line)
        if m:
            out.append((m.group(2), "[HUMAN]" in m.group(3)))
    return out


def evidence(cwd: Path, feature: str) -> tuple[set[str], set[str]]:
    """Returns (units attested on any reachable commit,
                units attested on HEAD itself) FOR THIS FEATURE.

    Attests are scoped by their recorded `feature` field: in a repo
    that delivers more than one feature on the same branch, every
    feature reuses the task ids T01, T02, … , so counting units
    globally would let one feature's `T08` satisfy another's. The
    feature field exists exactly to prevent that; honor it. A note
    without a feature field is legacy/unscoped and cannot be trusted
    to belong to this feature, so it does not count."""
    rc, head = sh("git", "rev-parse", "HEAD", cwd=cwd)
    if rc != 0:
        return set(), set()
    head = head.strip()
    want = canon_feature(feature, cwd)
    want_run = current_run(cwd)   # None when standalone → feature-only
    rc, reach = sh("git", "rev-list", "HEAD", cwd=cwd)
    reachable = set(reach.split())
    rc, listing = sh("git", "notes", f"--ref={NOTES_REF}", "list", cwd=cwd)
    anywhere: set[str] = set()
    on_head: set[str] = set()
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        _, target = parts
        if target not in reachable:
            continue
        rc, body = sh("git", "notes", f"--ref={NOTES_REF}", "show",
                      target, cwd=cwd)
        if rc != 0:
            continue
        for raw in body.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (rec.get("exit") == 0 and rec.get("unit")
                    and rec.get("feature") is not None
                    and canon_feature(rec["feature"], cwd) == want
                    and (want_run is None or rec.get("run") == want_run)):
                anywhere.add(rec["unit"])
                if target == head:
                    on_head.add(rec["unit"])
    return anywhere, on_head


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: ledger.py <feature-dir>")
        return 2
    feature_dir = Path(sys.argv[1])
    cwd = Path.cwd()

    tasks = tasks_of(feature_dir)
    attested, on_head = evidence(cwd, str(feature_dir))
    done = [t for t, _ in tasks if t in attested]
    missing = [(t, h) for t, h in tasks if t not in attested]

    def out(verdict: str, reason: str, code: int) -> int:
        print(f"LEDGER: {verdict} — {reason}")
        print(f"progress: done={len(done)} total={len(tasks)}")
        return code

    if not tasks:
        return out("BLOCKED", f"no tasks found in {feature_dir}/tasks.md", 2)
    if missing:
        unit, human = missing[0]
        if human:
            return out("BLOCKED", f"{unit} is [HUMAN] — needs you", 2)
        return out("CONTINUE",
                   f"{unit} unattested — run its check via attest.py "
                   f"({len(missing)} of {len(tasks)} open)", 1)
    if "SUITE" not in on_head:
        return out("CONTINUE",
                   "all tasks attested; SUITE attest missing on current "
                   "HEAD — attest.py <fd> SUITE -- <suite cmd>", 1)
    rc, dirty = sh("git", "status", "--porcelain", cwd=cwd)
    if rc == 0 and dirty.strip():
        return out("CONTINUE",
                   "worktree dirty — uncommitted changes postdate the "
                   "SUITE attest; commit (or clean), then re-attest "
                   "SUITE on the new HEAD", 1)
    return out("FINISHED",
               f"{len(tasks)} tasks attested, SUITE green on HEAD, "
               "worktree clean", 0)


if __name__ == "__main__":
    sys.exit(main())
