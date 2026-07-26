"""craft-memory.py: lessons harvested from a run's own evidence
(gate reds in the journal, seal rejections in git notes), append-only,
with verifier-driven retirement. Cover is the grounding gate."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CM = ROOT / "bin" / "craft-memory.py"
SEAL = ROOT / "bin" / "seal.py"


def sh(*args, cwd):
    return subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)


@pytest.fixture()
def repo(tmp_path):
    cwd = tmp_path
    fd = cwd / "records" / "leads" / "acme"
    fd.mkdir(parents=True)
    sh("git", "init", "-b", "main", cwd=cwd)
    sh("git", "config", "user.email", "t@t", cwd=cwd)
    sh("git", "config", "user.name", "t", cwd=cwd)
    (cwd / "a.txt").write_text("v1\n")
    sh("git", "add", "-A", cwd=cwd)
    sh("git", "commit", "-m", "init", cwd=cwd)
    # a run journal with a gate red
    (fd / ".flow-journal.jsonl").write_text(json.dumps({
        "ts": "2026-07-24T16:00:00+0000", "run": "r1", "flow": "leads",
        "event": "stop", "verdict": "CONTINUE", "decision": "block",
        "node": "research",
        "reason": "FLOW: CONTINUE — node: research — gate-research exit 1: "
                  "FAIL [item-check] research.md is trivial (<300 chars)",
    }) + "\n")
    return cwd


def cm(cwd, *args):
    return sh(sys.executable, str(CM), *args, cwd=cwd)


def test_extract_harvests_gate_red_and_seal_rejection(repo):
    # a human rejects with a note — the gold lesson
    sh(sys.executable, str(SEAL), "record", "records/leads/acme", "outreach",
       "rejected", "--note", "tone too aggressive; not our brand voice", cwd=repo)
    p = cm(repo, "extract", "records/leads/acme", "--skill", "outreach")
    assert p.returncode == 0
    # both sources become live lessons
    p = cm(repo, "list", "outreach")
    assert "trivial (<300 chars)" in p.stdout          # from the gate red
    assert "not our brand voice" in p.stdout           # from the seal reject
    assert "[gate]" in p.stdout and "[seal]" in p.stdout


def test_extract_is_idempotent(repo):
    cm(repo, "extract", "records/leads/acme", "--skill", "outreach")
    before = (repo / "craft-memory" / "outreach.jsonl").read_text().count("\n")
    cm(repo, "extract", "records/leads/acme", "--skill", "outreach")  # again
    after = (repo / "craft-memory" / "outreach.jsonl").read_text().count("\n")
    assert before == after                              # re-extract adds nothing


def test_cover_fails_until_every_live_lesson_has_a_case(repo):
    cm(repo, "extract", "records/leads/acme", "--skill", "outreach")
    live_ids = [l.split()[0] for l in cm(repo, "list", "outreach").stdout.splitlines()
                if l.startswith("L-")]
    assert len(live_ids) == 1  # only the gate red (no seal here)
    sd = repo / "skills" / "outreach"
    (sd / "eval").mkdir(parents=True)
    (sd / "eval" / "cases.jsonl").write_text("")       # no cases yet
    p = cm(repo, "cover", "outreach", "--skill-dir", str(sd))
    assert p.returncode == 1 and "uncovered" in p.stdout
    # add a case citing the lesson → cover passes
    (sd / "eval" / "cases.jsonl").write_text(json.dumps(
        {"id": "C1", "lesson": live_ids[0], "assert": [{"kind": "min_chars", "n": 300}]}) + "\n")
    p = cm(repo, "cover", "outreach", "--skill-dir", str(sd))
    assert p.returncode == 0


def test_prune_retires_only_lessons_whose_case_actually_passes(repo):
    # the pruner RE-RUNS the eval; it must not trust a claim. A lesson is
    # retired only if its case genuinely passes on the produced output.
    cm(repo, "extract", "records/leads/acme", "--skill", "outreach")
    lid = next(l.split()[0] for l in cm(repo, "list", "outreach").stdout.splitlines()
               if l.startswith("L-"))
    sd = repo / "skills" / "outreach"
    (sd / "eval").mkdir(parents=True)
    (sd / "eval" / "cases.jsonl").write_text(json.dumps(
        {"id": "C1", "lesson": lid, "assert": [{"kind": "min_chars", "n": 300}]}) + "\n")
    # outputs that FAIL the case → prune retires nothing (lesson stays live)
    (repo / "out.jsonl").write_text(json.dumps({"id": "C1", "output": "too short"}) + "\n")
    cm(repo, "prune", "outreach", "--skill-dir", str(sd), "--outputs", str(repo / "out.jsonl"), "--by", "r-eval")
    assert lid in cm(repo, "list", "outreach").stdout          # NOT retired
    # outputs that PASS the case → prune retires the lesson
    (repo / "out.jsonl").write_text(json.dumps({"id": "C1", "output": "x" * 400}) + "\n")
    cm(repo, "prune", "outreach", "--skill-dir", str(sd), "--outputs", str(repo / "out.jsonl"), "--by", "r-eval")
    assert lid not in cm(repo, "list", "outreach").stdout      # retired, verified


def test_retire_is_verifier_driven_and_removes_from_live(repo):
    cm(repo, "extract", "records/leads/acme", "--skill", "outreach")
    lid = next(l.split()[0] for l in cm(repo, "list", "outreach").stdout.splitlines()
               if l.startswith("L-"))
    # retire needs a --by (the eval run that confirmed the fix)
    assert cm(repo, "retire", "outreach", lid).returncode == 2
    assert cm(repo, "retire", "outreach", lid, "--by", "r-eval-9").returncode == 0
    # it is gone from live, but still in --all (append-only history)
    assert lid not in cm(repo, "list", "outreach").stdout
    assert lid in cm(repo, "list", "outreach", "--all").stdout
