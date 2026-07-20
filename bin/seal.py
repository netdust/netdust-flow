#!/usr/bin/env python3
"""seal.py — record and read HUMAN decisions as evidence (I4).

    seal.py record <feature-dir> <node-id> <approved|rejected> [--note TEXT]
    seal.py check  <feature-dir> <node-id>

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

Flows wire it as a gate after each human node:

    - id: gate-approval
      kind: gate
      run: "{netdust_flow}/bin/seal.py check {feature_dir} approve-plan"
    edges:
      - {from: gate-approval, to: build,        when: gate.exit == 0}
      - {from: gate-approval, to: plan,         when: gate.exit == 2}
      - {from: gate-approval, to: approve-plan, when: gate.exit == 1}

Freshness model, stated honestly: latest-wins means an approval can go
stale if the sealed artifact changes afterwards without a re-seal. The
record carries the tree hash for audit; requiring seal-on-current-tree
is deferred as ceremony until a drill shows a leak. Tamper boundary is
attest.py's: git notes are tamper-resistant, not tamper-proof — the
pretooluse guard should deny `git notes` outside attest.py/seal.py.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from subprocess import run as _run

NOTES_REF = "refs/notes/seal"
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
    rc, _ = sh("git", "notes", f"--ref={NOTES_REF}", "append", "-m",
               json.dumps(body), "HEAD", cwd=cwd)
    if rc != 0:
        print("seal: git notes append failed — nothing recorded")
        return 2
    _, head = sh("git", "rev-parse", "--short", "HEAD", cwd=cwd)
    print(f"SEAL: RECORDED — {node} {decision} on {head.strip()}")
    return 0


def check(node: str, cwd: Path) -> int:
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
            if rec.get("unit") == "seal" and rec.get("node") == node:
                latest = rec
        if latest is not None:
            decision = latest.get("decision")
            code = DECISIONS.get(decision, NO_SEAL)
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
    args = ap.parse_args()
    cwd = Path.cwd()
    if args.mode == "record":
        return record(args.feature_dir, args.node, args.decision,
                      args.note, cwd)
    return check(args.node, cwd)


if __name__ == "__main__":
    sys.exit(main())
