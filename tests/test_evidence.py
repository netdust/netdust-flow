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
    # the floors are the PROJECT's (docs/project-pack.md) — the runtime
    # ships none, so a repo under test writes its own
    (cwd / ".flow").mkdir(parents=True)
    (cwd / ".flow" / "floors.yaml").write_text(
        "floors:\n"
        "  schema:\n"
        "    paths: [\"**/migrations/**\"]\n"
        "    content: ['CREATE TABLE', 'ALTER TABLE']\n")
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


def _arm(cwd, run_id):
    """Write a minimal marker so attest/seal/ledger see an armed run."""
    (cwd / "tasks").mkdir(exist_ok=True)
    (cwd / "tasks" / ".netdust-flow.json").write_text(
        json.dumps({"feature_dir": "specs/demo", "run_id": run_id}))


def test_replan_does_not_inherit_prior_run_evidence(repo):
    # run 1: attest T01 and seal approve-plan under run r1
    _arm(repo, "r1")
    attest(repo, "T01", 0)
    seal(repo, "record", "specs/demo", "approve-plan", "approved")
    rc, out = ledger(repo)
    assert "done=1 total=2" in out
    # re-plan: same feature, same task ids, NEW run id r2. The prior
    # run's T01 attest and approve-plan seal must NOT carry over.
    _arm(repo, "r2")
    rc, out = ledger(repo)
    assert "done=0 total=2" in out, out          # r1's T01 does not count
    rc, _ = seal(repo, "check", "specs/demo", "approve-plan")
    assert rc == 1                                # r1's seal does not advance r2
    # r2 records its own evidence, which does count
    attest(repo, "T01", 0)
    seal(repo, "record", "specs/demo", "approve-plan", "approved")
    rc, out = ledger(repo)
    assert "done=1 total=2" in out
    rc, _ = seal(repo, "check", "specs/demo", "approve-plan")
    assert rc == 0


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


def test_floor_missing_floors_file_fails_closed(repo):
    # "nothing was scanned" must never read as "clean" on a gate whose
    # whole job is pushing work up. The runtime ships no floors, so a
    # project without its own gets BLOCKED, not a free pass.
    (repo / ".flow" / "floors.yaml").unlink()
    p = sh(sys.executable, str(FLOORS), "--base", "main", cwd=repo)
    assert p.returncode == 2 and "no floors file" in p.stdout


def test_floor_uses_the_project_file_not_a_runtime_default(repo):
    # the floors that decide are the ones in THIS project: a pattern
    # only this repo declares must trigger, and the WordPress patterns
    # that used to ship with the runtime must not
    (repo / ".flow" / "floors.yaml").write_text(
        "floors:\n  house-style:\n    content: ['MAGIC_TOKEN']\n")
    # commit the floors file first: a pattern declared in the diff would
    # match itself, which is a real trap for anyone editing their floors
    sh("git", "add", "-A", cwd=repo)
    sh("git", "commit", "-m", "floors", cwd=repo)
    (repo / "b.txt").write_text("current_user_can();\n")   # old runtime floor
    sh("git", "add", "-A", cwd=repo)
    p = sh(sys.executable, str(FLOORS), "--base", "main", cwd=repo)
    assert p.returncode == 0, p.stdout
    (repo / "c.txt").write_text("MAGIC_TOKEN\n")
    sh("git", "add", "-A", cwd=repo)
    p = sh(sys.executable, str(FLOORS), "--base", "main", cwd=repo)
    assert p.returncode == 2 and "house-style" in p.stdout


# ── seal freshness (--fresh): a decision must still describe what is
# on disk. Default stays latest-wins; the finishing gates opt in.

def _commit(cwd, msg="change"):
    sh("git", "add", "-A", cwd=cwd)
    sh("git", "commit", "-m", msg, cwd=cwd)


def test_seal_fresh_accepts_an_undisturbed_approval(repo):
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 0, out          # nothing moved — the seal still holds


def test_seal_fresh_flags_drift(repo):
    # the F2 drill: approve, then commit an edit to the sealed artifact.
    # Default check still passes (latest-wins); --fresh must re-ask.
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    (repo / "specs" / "demo" / "dossier.md").write_text("edited after seal\n")
    _commit(repo, "post-seal edit")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout")
    assert rc == 0, "default must stay latest-wins"
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 1, out
    assert "STALE" in out and "HEAD is" in out, out


def test_seal_fresh_catches_uncommitted_drift(repo):
    # the hole a tree-only check leaves: never commit, and HEAD^{tree}
    # never moves, so the seal rides forever. Dirty UNDER the feature
    # is drift too.
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    (repo / "specs" / "demo" / "dossier.md").write_text("uncommitted edit\n")
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 1, out
    assert "STALE" in out and "uncommitted" in out, out


def test_seal_fresh_ignores_edits_outside_the_feature(repo):
    # another feature's work in flight must not invalidate this seal,
    # or nothing in a busy repo could ever finish
    seal(repo, "record", "specs/demo", "shakeout", "approved")
    (repo / "unrelated.txt").write_text("someone else's work\n")
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 0, out


def test_seal_fresh_rejection_goes_stale_after_the_fix(repo):
    # a rejection is a decision about a state too: once the fix lands,
    # the `no` no longer describes the artifact, so the gate must
    # re-ask (1) rather than loop on the old rejection (2)
    seal(repo, "record", "specs/demo", "shakeout", "rejected")
    rc, _ = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 2, "a fresh rejection still routes as a rejection"
    (repo / "specs" / "demo" / "dossier.md").write_text("the fix\n")
    _commit(repo, "address the rejection")
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 1, out


def test_seal_fresh_absent_is_still_absent(repo):
    rc, out = seal(repo, "check", "specs/demo", "shakeout", "--fresh")
    assert rc == 1 and "absent" in out
