"""What counts as a dry stop (F04).

`dry` used to increment whenever the done-count did not move, and at
`max_dry` (default 2) the walker disarmed. A convergence loop moves no
checkbox at all: it produces findings, the spec is revised, the report
is rewritten, and the task ledger stands still the whole time. Run 0004
needed three rounds to converge — each one closing real defects — so
even with no observer session in the repo, three legitimate rounds
would have exhausted a max_dry of 2 and disarmed a healthy run. The
builder predicted it in the plan's own Risks section and then watched
it happen.

Dry now means "nothing moved", not "no checkbox ticked": a stop counts
as dry only when the done-count, the worktree AND the gate exits are
all unchanged from the previous stop. Artifacts changing is progress
even when no box is ticked.
"""
import json
import subprocess
import sys
from pathlib import Path

from test_flow_gate import setup, marker_of
from test_marker_identity import run_gate_as

ROOT = Path(__file__).resolve().parents[1]
DELIVER = ROOT / "flows" / "deliver.json"


def armed(tmp_path, **extra):
    """A run parked on `spec` with a red spec gate, so every stop is a
    CONTINUE that ticks no checkbox — the convergence-loop shape."""
    home, cwd = setup(tmp_path, DELIVER, "spec", extra=extra)
    (cwd / "specs" / "demo" / ".stub-gate-check").write_text("1")
    (cwd / "specs" / "demo" / "spec.md").write_text("# spec, round 0\n")
    return home, cwd


def test_a_stop_that_changed_nothing_is_dry(tmp_path):
    """The counter still has to work, or the budget is the only brake."""
    home, cwd = armed(tmp_path, max_dry=10)
    run_gate_as(cwd, home, "s1")
    run_gate_as(cwd, home, "s1")

    assert marker_of(cwd)["dry"] >= 1


def test_a_stop_that_revised_an_artifact_is_not_dry(tmp_path):
    """The convergence round: findings land, the spec is revised, no
    checkbox moves. That is work, and the walker must see it."""
    home, cwd = armed(tmp_path, max_dry=10)
    run_gate_as(cwd, home, "s1")

    (cwd / "specs" / "demo" / "spec.md").write_text("# spec, round 1\n")
    run_gate_as(cwd, home, "s1")

    assert marker_of(cwd)["dry"] == 0


def test_three_convergence_rounds_do_not_disarm_a_healthy_run(tmp_path):
    """Run 0004's exact shape, at the default max_dry of 2: three rounds
    of real review work, no checkbox ticked by any of them."""
    home, cwd = armed(tmp_path, max_dry=2)
    reviews = cwd / "specs" / "demo" / "reviews"
    reviews.mkdir()

    for round_no in range(1, 4):
        reviews.joinpath("convergence.md").write_text(
            f"# round {round_no}\nNOT_CONVERGED — {round_no} findings\n")
        (cwd / "specs" / "demo" / "spec.md").write_text(
            f"# spec, revised for round {round_no}\n")
        run_gate_as(cwd, home, "s1")

    assert marker_of(cwd) is not None, (
        "three rounds of real convergence work disarmed the run")


def test_a_new_file_is_progress(tmp_path):
    home, cwd = armed(tmp_path, max_dry=10)
    run_gate_as(cwd, home, "s1")

    (cwd / "specs" / "demo" / "reviews.md").write_text("# findings\n")
    run_gate_as(cwd, home, "s1")

    assert marker_of(cwd)["dry"] == 0


def test_a_commit_is_progress(tmp_path):
    home, cwd = armed(tmp_path, max_dry=10)
    run_gate_as(cwd, home, "s1")

    for args in (["add", "-A"], ["commit", "-m", "round 1"]):
        subprocess.run(["git", *args], capture_output=True, cwd=cwd)
    run_gate_as(cwd, home, "s1")

    assert marker_of(cwd)["dry"] == 0


def test_a_changed_gate_exit_is_progress(tmp_path):
    """Red → green is movement even before a box is ticked."""
    home, cwd = armed(tmp_path, max_dry=10)
    run_gate_as(cwd, home, "s1")
    run_gate_as(cwd, home, "s1")
    assert marker_of(cwd)["dry"] >= 1

    (cwd / "specs" / "demo" / ".stub-gate-check").unlink()   # gate goes green
    run_gate_as(cwd, home, "s1")

    assert marker_of(cwd)["dry"] == 0


def test_a_truly_stuck_run_still_disarms(tmp_path):
    """The guardrail must not be argued away: a session that stops over
    and over changing nothing is what max_dry exists for."""
    home, cwd = armed(tmp_path, max_dry=2)

    for _ in range(6):
        run_gate_as(cwd, home, "s1")

    assert marker_of(cwd) is None, "a genuinely dry loop must still disarm"
