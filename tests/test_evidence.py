"""Evidence machinery against a real git repo: attest writes only on
green, ledger derives state on request, drift un-finishes, floors scan
real diffs."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ATTEST = ROOT / "bin" / "attest.py"
LEDGER = ROOT / "bin" / "ledger.py"
FLOORS = ROOT / "bin" / "floor-check.py"
SEAL = ROOT / "bin" / "seal.py"


def sh(*args, cwd):
    return subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)


@pytest.fixture()
def repo(tmp_path):
    cwd = tmp_path / "repo"
    (cwd / "specs" / "demo").mkdir(parents=True)
    sh("git", "init", "-b", "main", cwd=cwd)
    sh("git", "config", "user.email", "t@t", cwd=cwd)
    sh("git", "config", "user.name", "t", cwd=cwd)
    (cwd / "specs" / "demo" / "tasks.md").write_text(
        "- [ ] T01 [Tier B] first\n- [ ] T02 [Tier C] second\n")
    (cwd / "a.txt").write_text("v1\n")
    sh("git", "add", "-A", cwd=cwd)
    sh("git", "commit", "-m", "init", cwd=cwd)
    return cwd


def attest(cwd, unit, code):
    return sh(sys.executable, str(ATTEST), "specs/demo", unit, "--",
              sys.executable, "-c", f"import sys; sys.exit({code})", cwd=cwd)


def ledger(cwd):
    p = sh(sys.executable, str(LEDGER), "specs/demo", cwd=cwd)
    return p.returncode, p.stdout


def seal(cwd, *args):
    p = sh(sys.executable, str(SEAL), *args, cwd=cwd)
    return p.returncode, p.stdout


def test_attests_are_scoped_by_feature(repo):
    # a multi-feature repo: another feature attests the SAME unit ids
    # on the same branch — they must NOT satisfy this feature's tasks
    (repo / "specs" / "other").mkdir(parents=True)
    (repo / "specs" / "other" / "tasks.md").write_text("- [ ] T01 x\n")
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-m", "other feature", cwd=repo)
    sh(sys.executable, str(ATTEST), "specs/other", "T01", "--",
       sys.executable, "-c", "import sys; sys.exit(0)", cwd=repo)
    sh(sys.executable, str(ATTEST), "specs/other", "T02", "--",
       sys.executable, "-c", "import sys; sys.exit(0)", cwd=repo)
    # specs/demo has attested NOTHING — its ledger must still show 0 done
    rc, out = ledger(repo)
    assert rc == 1 and "done=0 total=2" in out, out
    # and once demo attests its own T01, only that counts
    attest(repo, "T01", 0)
    rc, out = ledger(repo)
    assert "done=1 total=2" in out, out


def test_failed_check_records_nothing(repo):
    p = attest(repo, "T01", 1)
    assert p.returncode == 1 and "nothing recorded" in p.stdout
    rc, out = ledger(repo)
    assert rc == 1 and "T01" in out and "done=0 total=2" in out


def test_green_check_records_and_ledger_advances(repo):
    assert attest(repo, "T01", 0).returncode == 0
    rc, out = ledger(repo)
    assert rc == 1 and "T02" in out and "done=1 total=2" in out


def test_all_tasks_but_no_suite_is_not_finished(repo):
    attest(repo, "T01", 0)
    attest(repo, "T02", 0)
    rc, out = ledger(repo)
    assert rc == 1 and "SUITE" in out


def test_suite_on_head_finishes(repo):
    attest(repo, "T01", 0)
    attest(repo, "T02", 0)
    attest(repo, "SUITE", 0)
    rc, out = ledger(repo)
    assert rc == 0 and "FINISHED" in out


def test_drift_unfinishes(repo):
    attest(repo, "T01", 0)
    attest(repo, "T02", 0)
    attest(repo, "SUITE", 0)
    (repo / "a.txt").write_text("v2\n")
    sh("git", "commit", "-am", "later change", cwd=repo)
    rc, out = ledger(repo)
    assert rc == 1 and "SUITE" in out          # suite no longer on HEAD


def test_checkboxes_are_ignored(repo):
    (repo / "specs" / "demo" / "tasks.md").write_text(
        "- [x] T01 [Tier B] first\n- [x] T02 [Tier C] second\n")
    rc, out = ledger(repo)
    assert rc == 1 and "done=0 total=2" in out  # boxes buy nothing


def test_human_task_blocks(repo):
    (repo / "specs" / "demo" / "tasks.md").write_text(
        "- [ ] T01 [HUMAN] decide copy\n- [ ] T02 second\n")
    rc, out = ledger(repo)
    assert rc == 2 and "T01" in out


def test_dirty_worktree_unfinishes(repo):
    # tree-level drift catch: uncommitted edits after a green SUITE must
    # force re-verification — commit-level (note on HEAD) is not enough
    attest(repo, "T01", 0)
    attest(repo, "T02", 0)
    attest(repo, "SUITE", 0)
    (repo / "a.txt").write_text("v2, uncommitted\n")
    rc, out = ledger(repo)
    assert rc == 1 and "dirty" in out


# ── seal.py: human decisions as evidence (I4) ────────────────────────

def test_seal_absent(repo):
    rc, out = seal(repo, "check", "specs/demo", "approve-plan")
    assert rc == 1 and "absent" in out


def test_seal_record_and_check(repo):
    rc, out = seal(repo, "record", "specs/demo", "approve-plan", "approved")
    assert rc == 0 and "RECORDED" in out
    rc, out = seal(repo, "check", "specs/demo", "approve-plan")
    assert rc == 0 and "approved" in out


def test_seal_rejection_and_latest_wins(repo):
    seal(repo, "record", "specs/demo", "shakeout", "rejected")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 2
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 0                                  # latest decision wins


def test_seal_nodes_are_independent(repo):
    seal(repo, "record", "specs/demo", "approve-plan", "approved")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 1


def test_seals_are_scoped_by_feature(repo):
    # a multi-feature repo: another feature's human node reuses the same
    # name (shakeout) — its `approved` must NOT satisfy this feature's
    # seal check, or one person's decision finishes a flow they never
    # looked at (I4 broken at its core)
    seal(repo, "record", "specs/other", "shakeout", "approved")
    rc, out = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 1 and "absent" in out, out           # NOT approved
    # this feature's own seal is honored
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 0


def test_feature_scope_normalizes_relative_vs_absolute(repo):
    # the Stop hook drives gates with an ABSOLUTE feature_dir while a
    # human records with a relative one — scoping must see them as the
    # same feature, or a real seal/attest is invisible to its own gate
    abs_fd = str(repo / "specs" / "demo")
    seal(repo, "record", "specs/demo", "approve-plan", "approved")
    rc, _ = seal(repo, "check", abs_fd, "approve-plan")   # absolute check
    assert rc == 0, "absolute-path check must match a relative-path seal"
    attest(repo, "T01", 0)                                 # relative attest
    p = sh(sys.executable, str(LEDGER), abs_fd, cwd=repo)  # absolute ledger
    assert "done=1" in p.stdout, p.stdout


def test_seal_invalid_decision_records_nothing(repo):
    rc, out = seal(repo, "record", "specs/demo", "approve-plan", "maybe")
    assert rc == 2
    rc, _ = seal(repo, "check", "specs/demo", "approve-plan")
    assert rc == 1


def test_floor_clean_and_triggered(repo):
    p = sh(sys.executable, str(FLOORS), "--base", "main", cwd=repo)
    assert p.returncode == 0
    mig = repo / "database" / "migrations"
    mig.mkdir(parents=True)
    (mig / "001.sql").write_text("CREATE TABLE x (id int);\n")
    sh("git", "add", "-A", cwd=repo)
    p = sh(sys.executable, str(FLOORS), "--base", "main", cwd=repo)
    assert p.returncode == 2 and "schema" in p.stdout


def test_floor_missing_base_fails_closed(repo):
    # an unresolvable base ref must BLOCK (exit 2), never silently
    # shrink the diff to worktree-only and let committed changes escape
    p = sh(sys.executable, str(FLOORS), "--base", "no-such-ref", cwd=repo)
    assert p.returncode == 2 and "cannot resolve base" in p.stdout
