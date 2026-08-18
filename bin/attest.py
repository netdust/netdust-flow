#!/usr/bin/env python3
"""attest.py — run a check; on success, record evidence in git.

    attest.py <feature-dir> <unit-id> -- <check command ...>

The check runs as argv (no shell). On exit 0 a structured record is
appended as a git note (ref refs/notes/attest) on the CURRENT HEAD:

    {"unit": "T03", "cmd": "...", "exit": 0, "ts": "...", "tree": "..."}

On non-zero exit nothing is recorded and the same exit code is
returned, so the caller sees red. The claimant never writes evidence:
this tool executed the check itself, which is the whole point (I3 —
ledger state transitions may only be written by verifiers).

Freshness model: per-unit attests prove each unit was verified when
built; a final `SUITE` attest must sit on the finishing HEAD, so any
later change forces re-verification of the whole. Drift is caught by
re-checking, not by bookkeeping.

Boundary, stated honestly: git notes are tamper-resistant, not
tamper-proof — an agent with bash could forge one. hooks/
pretooluse-guard.py denies the DIRECT path (`git notes` writes via
Bash, and Write/Edit to the compiled twins and journal), so a forge
must be deliberate rather than incidental; it does not claim to be
airtight, and the marker (tasks/.netdust-flow.json) is deliberately
left editable because arming legitimately writes it. Signing records
would close the rest and is deferred as ceremony until a drill shows
a leak.
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

NOTES_REF = "refs/notes/attest"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowspec  # noqa: E402 — stdlib-only by contract

# One name, one definition (bin/flowspec.py). Run 0004 F02.
MARKER_REL = flowspec.MARKER_REL


def current_run(cwd: Path) -> str | None:
    """The run id of the armed flow, if any (minted by the Stop hook,
    persisted in the marker). Evidence records it so a re-plan — which
    re-arms with a NEW run id but the SAME feature and task ids —
    cannot inherit the prior run's attests. Same run-scoping the
    journal already uses."""
    try:
        return (json.loads((cwd / MARKER_REL).read_text()).get("run_id")
                or None)
    except Exception:
        return None


def git(*args: str, cwd: Path) -> str:
    p = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def main() -> int:
    argv = sys.argv[1:]
    if "--" not in argv or len(argv) < 3:
        print("usage: attest.py <feature-dir> <unit-id> -- <check command ...>")
        return 2
    split = argv.index("--")
    feature_dir, unit = Path(argv[0]), argv[1]
    cmd = argv[split + 1:]
    if not cmd:
        print("attest: empty check command")
        return 2
    cwd = Path.cwd()

    check = subprocess.run(cmd, cwd=cwd)
    if check.returncode != 0:
        print(f"ATTEST: FAILED — {unit} exit {check.returncode} "
              f"({shlex.join(cmd)}) — nothing recorded")
        return check.returncode

    record = {
        "unit": unit,
        "feature": str(feature_dir),
        "cmd": shlex.join(cmd),
        "exit": 0,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tree": git("rev-parse", "HEAD^{tree}", cwd=cwd),
    }
    run = current_run(cwd)
    if run:
        record["run"] = run
    git("notes", f"--ref={NOTES_REF}", "append", "-m",
        json.dumps(record), "HEAD", cwd=cwd)
    head = git("rev-parse", "--short", "HEAD", cwd=cwd)
    print(f"ATTEST: RECORDED — {unit} on {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
