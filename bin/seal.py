#!/usr/bin/env python3
"""seal.py — record and read HUMAN decisions as evidence (I4).

    seal.py record <feature-dir> <node-id> <approved|rejected> [--note TEXT]
    seal.py check  <feature-dir> <node-id> [--fresh]

The missing half of attest.py: attest records what a CHECK proved,
seal records what a HUMAN decided. Both write structured records into
git notes; both are read back mechanically. A human node in a flow is
therefore a yield point only — the decision enters the machine as a
recorded event checked by a seal GATE, never as "the session resumed"
(resumption carries no information; a human who resumed to say `no`
must not advance the flow).

    record  appends {"unit": "seal", "node": "approve-plan",
            "decision": "approved", "ts": "...", "tree": "..."} to
            refs/notes/seal on the CURRENT HEAD. Exit 0.
    check   scans commits reachable from HEAD, newest first; the most
            recent record for <node-id> wins.
            Exit 0 approved · 2 rejected · 1 no seal recorded.
            --fresh additionally requires the decision to still describe
            what is on disk (see below); a stale one exits 1, not 0.

Flows wire it as a gate after each human node:

    - id: gate-approval
      kind: gate
      run: "{netdust_flow}/bin/seal.py check {feature_dir} approve-plan"
    edges:
      - {from: gate-approval, to: build,        when: gate.exit == 0}
      - {from: gate-approval, to: plan,         when: gate.exit == 2}
      - {from: gate-approval, to: approve-plan, when: gate.exit == 1}

Freshness model. The DEFAULT is latest-wins: an approval can go stale
if the sealed artifact changes afterwards without a re-seal. The record
carries the tree hash, so `--fresh` turns that audit trail into a gate
— use it on any finishing gate whose decision is judgment-bearing
(send, publish, sign, ship). A seal is FRESH only when both hold:

  * the recorded `tree` equals the current `HEAD^{tree}` — nothing has
    been committed since the human looked; and
  * the worktree is clean UNDER <feature-dir> — nothing has been edited
    since either. Without this second half the whole check is bypassed
    by simply not committing, which is the easiest drift there is.

A stale seal exits NO_SEAL (1), never `rejected` (2): drift is not a
human saying no, it is a human who has not been asked yet. Flows route
1 back to the human node, so the effect is to re-ask — and because a
rejection goes stale by the same rule, the fix that answers a rejection
also re-asks rather than looping on the old `no`. Tamper boundary is
attest.py's: git notes are tamper-resistant, not tamper-proof —
hooks/pretooluse-guard.py denies agent-issued `git notes` writes, so
attest.py/seal.py (which write inside their own process) stay the
only path.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from subprocess import run as _run

NOTES_REF = "refs/notes/seal"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowspec  # noqa: E402 — stdlib-only by contract

# One name, one definition (bin/flowspec.py). Run 0004 F02.
MARKER_REL = flowspec.MARKER_REL


def current_run(cwd: Path) -> str | None:
    """Run id of the armed flow, if any — seals are scoped to it so a
    re-plan (new run id, same feature + human node names) cannot be
    advanced by the prior run's decision. Standalone → None → the
    check falls back to feature-only."""
    try:
        return (json.loads((cwd / MARKER_REL).read_text()).get("run_id")
                or None)
    except Exception:
        return None


def canon_feature(feature: str, cwd: Path) -> str:
    """Canonicalize a feature path so scoping compares the same thing
    whether the decision was recorded with a relative path (`specs/x`,
    as a human types it) or checked with the absolute feature_dir the
    Stop hook drives gates with. Normalize both to repo-root-relative."""
    p = Path(feature)
    absolute = p if p.is_absolute() else cwd / p
    try:
        return os.path.relpath(absolute.resolve(), cwd.resolve())
    except ValueError:
        return str(absolute)
DECISIONS = {"approved": 0, "rejected": 2}
NO_SEAL = 1


def sh(*args: str, cwd: Path) -> tuple[int, str]:
    p = _run(list(args), capture_output=True, text=True, cwd=cwd)
    return p.returncode, p.stdout


def record(feature_dir: str, node: str, decision: str, note: str,
           cwd: Path) -> int:
    if decision not in DECISIONS:
        print(f"seal: decision must be one of {sorted(DECISIONS)}")
        return 2
    rc, tree = sh("git", "rev-parse", "HEAD^{tree}", cwd=cwd)
    if rc != 0:
        print("seal: not a git repository (or no HEAD) — nothing recorded")
        return 2
    body = {
        "unit": "seal",
        "node": node,
        "decision": decision,
        "feature": feature_dir,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tree": tree.strip(),
    }
    if note:
        body["note"] = note
    run = current_run(cwd)
    if run:
        body["run"] = run
    rc, _ = sh("git", "notes", f"--ref={NOTES_REF}", "append", "-m",
               json.dumps(body), "HEAD", cwd=cwd)
    if rc != 0:
        print("seal: git notes append failed — nothing recorded")
        return 2
    _, head = sh("git", "rev-parse", "--short", "HEAD", cwd=cwd)
    print(f"SEAL: RECORDED — {node} {decision} on {head.strip()}")
    return 0


def head_tree(cwd: Path) -> str:
    rc, out = sh("git", "rev-parse", "HEAD^{tree}", cwd=cwd)
    return out.strip() if rc == 0 else ""


def dirty_under(feature: str, cwd: Path) -> list[str]:
    """Paths with uncommitted changes under <feature-dir>. A seal is a
    decision about a state; if that state has been edited since, the
    decision no longer describes it — and HEAD^{tree} alone cannot see
    this, because an uncommitted edit does not move the tree."""
    rc, out = sh("git", "status", "--porcelain", "--", feature, cwd=cwd)
    if rc != 0:
        return []
    return [l[3:].strip() for l in out.splitlines() if l.strip()]


def stale_reason(rec: dict, feature: str, cwd: Path) -> str | None:
    """Why this seal no longer describes what is on disk, or None."""
    sealed = str(rec.get("tree") or "")
    if not sealed:
        return "the record carries no tree hash (pre-freshness seal)"
    current = head_tree(cwd)
    if not current:
        return "cannot resolve the current HEAD tree"
    if sealed != current:
        return (f"sealed on tree {sealed[:12]} but HEAD is "
                f"{current[:12]} — the artifact changed after the decision")
    edited = dirty_under(feature, cwd)
    if edited:
        shown = ", ".join(edited[:3]) + (", …" if len(edited) > 3 else "")
        return (f"uncommitted changes under {feature} since the seal "
                f"({shown})")
    return None


def check(node: str, feature: str, cwd: Path, fresh: bool = False) -> int:
    want = canon_feature(feature, cwd)
    want_run = current_run(cwd)   # None when standalone → feature-only
    rc, reach = sh("git", "rev-list", "HEAD", cwd=cwd)
    if rc != 0:
        print(f"SEAL: absent — {node} (not a git repository)")
        return NO_SEAL
    rc, listing = sh("git", "notes", f"--ref={NOTES_REF}", "list", cwd=cwd)
    noted = set()
    for line in listing.splitlines():
        parts = line.split()
        if len(parts) == 2:
            noted.add(parts[1])
    # rev-list is newest-first; the first noted commit holds the freshest
    # records, and within one note body the last matching line wins.
    #
    # Seals are scoped by FEATURE: in a repo that delivers more than one
    # feature on the same branch, human nodes reuse the same names
    # (shakeout, approve-plan, …), so a decision recorded for one
    # feature must never satisfy another's — that would be one person's
    # `approved` finishing a flow they never looked at (I4 violated at
    # its core). A record whose feature differs is skipped; a legacy
    # record with no feature field is unscoped and cannot be trusted to
    # belong here, so it does not count.
    for commit in reach.split():
        if commit not in noted:
            continue
        rc, body = sh("git", "notes", f"--ref={NOTES_REF}", "show", commit,
                      cwd=cwd)
        if rc != 0:
            continue
        latest = None
        for raw in body.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (rec.get("unit") == "seal" and rec.get("node") == node
                    and rec.get("feature") is not None
                    and canon_feature(rec["feature"], cwd) == want
                    and (want_run is None or rec.get("run") == want_run)):
                latest = rec
        if latest is not None:
            decision = latest.get("decision")
            code = DECISIONS.get(decision, NO_SEAL)
            if fresh and code != NO_SEAL:
                why = stale_reason(latest, want, cwd)
                if why:
                    print(f"SEAL: STALE — {node} {decision} is no longer "
                          f"current: {why}. Re-ask the human.")
                    return NO_SEAL
            print(f"SEAL: {decision} — {node} (recorded {latest.get('ts')})")
            return code
    print(f"SEAL: absent — {node} needs a human decision "
          f"(seal.py record <fd> {node} approved|rejected)")
    return NO_SEAL


def main() -> int:
    ap = argparse.ArgumentParser(description="human decisions as evidence")
    sub = ap.add_subparsers(dest="mode", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("feature_dir")
    rec.add_argument("node")
    rec.add_argument("decision")
    rec.add_argument("--note", default="")
    chk = sub.add_parser("check")
    chk.add_argument("feature_dir")
    chk.add_argument("node")
    chk.add_argument("--fresh", action="store_true",
                     help="a decision that no longer describes what is on "
                          "disk exits 1 (re-ask) instead of 0")
    args = ap.parse_args()
    cwd = Path.cwd()
    if args.mode == "record":
        return record(args.feature_dir, args.node, args.decision,
                      args.note, cwd)
    return check(args.node, args.feature_dir, cwd, fresh=args.fresh)


if __name__ == "__main__":
    sys.exit(main())
