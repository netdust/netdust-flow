"""Keeping the record must not break the gate (F08).

`converge-check.py` read exactly `reviews/convergence.md`. Preserving a
round's report by renaming it to `convergence-round1.md` — a reasonable
instinct, and the record is genuinely worth keeping — left the gate
reading a filename that no longer existed, and the failure looked
identical to "no review was ever done".

The gate now reads the NEWEST matching report. A stale one is still
caught, but by the binding checks that exist for it, with an accurate
reason — not by a missing-file error that says the wrong thing.
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONVERGE = ROOT / "bin" / "converge-check.py"


def report(verdict="CONVERGED"):
    return f"VERDICT: {verdict}\nReviewer: someone-else\n"


def run(fd, task):
    p = subprocess.run(
        [sys.executable, str(CONVERGE), str(fd), "--task", str(task)],
        capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


def feature(tmp_path):
    fd = tmp_path / "feature"
    (fd / "reviews").mkdir(parents=True)
    (fd / "ask.md").write_text("# ask\n")
    (fd / "spec.md").write_text("# spec\n")
    task = tmp_path / "task.md"
    task.write_text("- [ ] T01\n")
    return fd, task


def test_an_archived_round_still_satisfies_the_lookup(tmp_path):
    """The only shape that matters: the operator renamed the file to
    keep the record, and the gate must still FIND a report."""
    fd, task = feature(tmp_path)
    (fd / "reviews" / "convergence-round1.md").write_text(report())

    rc, out = run(fd, task)

    assert "no convergence review" not in out, (
        "an archived report read as 'no review was ever done'")


def test_the_newest_report_is_the_one_read(tmp_path):
    fd, task = feature(tmp_path)
    (fd / "reviews" / "convergence-round1.md").write_text(
        report("NOT_CONVERGED"))
    time.sleep(0.01)
    (fd / "reviews" / "convergence.md").write_text(report("CONVERGED"))

    rc, out = run(fd, task)

    assert "verdict is not CONVERGED" not in out, (
        "the superseded round was read instead of the current one")


def test_a_superseded_round_does_not_answer_for_a_newer_one(tmp_path):
    fd, task = feature(tmp_path)
    (fd / "reviews" / "convergence.md").write_text(report("CONVERGED"))
    time.sleep(0.01)
    (fd / "reviews" / "convergence-round2.md").write_text(
        report("NOT_CONVERGED"))

    rc, out = run(fd, task)

    assert rc != 0
    assert "verdict is not CONVERGED" in out


def test_no_report_at_all_still_fails_and_says_so(tmp_path):
    fd, task = feature(tmp_path)

    rc, out = run(fd, task)

    assert rc != 0
    assert "no convergence review" in out


def test_unrelated_reviews_are_not_mistaken_for_one(tmp_path):
    """`reviews/` also holds security.md and code.md (I5 review tasks).
    Neither is a convergence report."""
    fd, task = feature(tmp_path)
    (fd / "reviews" / "security.md").write_text(report())
    (fd / "reviews" / "code.md").write_text(report())

    rc, out = run(fd, task)

    assert rc != 0
    assert "no convergence review" in out
