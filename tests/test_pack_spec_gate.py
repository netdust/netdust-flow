"""A task's check has to be able to fail for that task (F06).

Five of run 0004's seventeen tasks carried checks that could not
distinguish their own task's behaviour — three shared one identical
`js-gate.sh test:js 'run test'`, two shared one identical
`wp-render.sh netdust`. `attest.py` records an exit-0 run of the check
as proof the task is done, so a task can attest green against a suite
that contains no test for it at all. The plan stated the standard it
missed — "a task without a check that bites is a task that was not
done" — but nothing enforced it, and the gate only counted that check
lines existed.

Identical commands are the mechanically detectable half of that: two
tasks that run the same command are, to the ledger, the same evidence
recorded twice. A distinct selector (`--filter`, a test name, a route)
is all it takes to make the check answer for its own task.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / ".flow" / "bin" / "spec-gate.py"

SPEC = """\
# spec

## Problem
p

## Requirements
- R01 — a
- R02 — b
- R03 — c

## Acceptance
a
"""

PLAN = """\
# plan

Loop budget: ~25

## Tasks
T01 T02 T03 T90 T91
"""


def feature(tmp_path, tasks):
    fd = tmp_path / "feature"
    fd.mkdir()
    (fd / "spec.md").write_text(SPEC)
    (fd / "plan.md").write_text(PLAN)
    (fd / "tasks.md").write_text(tasks + REVIEW_CLUSTER)
    return fd


REVIEW_CLUSTER = """\
- [ ] T90 — review: security — check: `review-check.py fd security`
- [ ] T91 — review: code — check: `review-check.py fd code`
"""


def run(fd):
    p = subprocess.run([sys.executable, str(GATE), str(fd)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def test_two_tasks_sharing_one_check_is_a_finding(tmp_path):
    fd = feature(tmp_path, """\
- [ ] T01 — scroll engine — check: `sh bin/js-gate.sh test:js 'run test'`
- [ ] T02 — page transitions — check: `sh bin/js-gate.sh test:js 'run test'`
""")
    rc, out = run(fd)

    assert rc == 1
    assert "T01" in out and "T02" in out


def test_the_finding_says_what_to_do_about_it(tmp_path):
    fd = feature(tmp_path, """\
- [ ] T01 — a — check: `sh bin/js-gate.sh test:js 'run test'`
- [ ] T02 — b — check: `sh bin/js-gate.sh test:js 'run test'`
""")
    rc, out = run(fd)

    assert "--filter" in out or "selector" in out


def test_three_tasks_sharing_one_check_report_once(tmp_path):
    """One finding per shared command, not one per pair."""
    fd = feature(tmp_path, """\
- [ ] T01 — a — check: `sh bin/js-gate.sh test:js 'run test'`
- [ ] T02 — b — check: `sh bin/js-gate.sh test:js 'run test'`
- [ ] T03 — c — check: `sh bin/js-gate.sh test:js 'run test'`
""")
    rc, out = run(fd)

    dupes = [l for l in out.splitlines() if "same check" in l]
    assert len(dupes) == 1, out
    assert all(t in dupes[0] for t in ("T01", "T02", "T03"))


def test_the_same_runner_with_distinct_selectors_is_clean(tmp_path):
    """This is the fix the finding asks for, so it must pass."""
    fd = feature(tmp_path, """\
- [ ] T01 — a — check: `ddev composer test:int -- --filter ProjectTest`
- [ ] T02 — b — check: `ddev composer test:int -- --filter AboutTest`
""")
    rc, out = run(fd)

    assert rc == 0, out


def test_the_review_cluster_is_not_a_duplicate(tmp_path):
    """The I5 tasks run the same program with different scopes. Breaking
    them would trade one defect for another."""
    fd = feature(tmp_path, """\
- [ ] T01 — a — check: `ddev composer test:int -- --filter ProjectTest`
""")
    rc, out = run(fd)

    assert rc == 0, out


def test_whitespace_does_not_hide_a_duplicate(tmp_path):
    fd = feature(tmp_path, """\
- [ ] T01 — a — check: `sh bin/js-gate.sh   test:js 'run test'`
- [ ] T02 — b — check: `sh bin/js-gate.sh test:js 'run test'`
""")
    rc, out = run(fd)

    assert rc == 1 and "same check" in out
