"""Tests for flow-eval.py — the journal aggregator.

Journals are synthesized (the writer side is covered by the hook
integration tests); these assert the derived numbers: cohort grouping
by flow@hash, first-pass rates, executions-to-green, block-stop and
yield rates, open-vs-finished outcomes.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLOW_EVAL = ROOT / "bin" / "flow-eval.py"

HASH_A = "aaaabbbbcccc"
HASH_B = "ddddeeeeffff"


def ev(run, event, fhash=HASH_A, **kv):
    return {"ts": "2026-07-21T10:00:00+0000", "run": run, "flow": "deliver",
            "fhash": fhash, "event": event, **kv}


def gate(run, node, exit, **kv):
    return ev(run, "gate", node=node, exit=exit, **kv)


def stop(run, decision, node, iter, **kv):
    verdict = {"block": "CONTINUE", "yield": "BLOCKED",
               "disarm-finished": "FINISHED"}.get(decision, "CONTINUE")
    return ev(run, "stop", decision=decision, node=node, iter=iter,
              verdict=verdict, **kv)


@pytest.fixture()
def feature(tmp_path):
    fd = tmp_path / "specs" / "demo"
    fd.mkdir(parents=True)
    entries = [
        # r1: spec gate red once then green; ledger loops twice; finishes
        gate("r1", "gate-spec", 1), stop("r1", "block", "spec", 1),
        gate("r1", "gate-spec", 0), stop("r1", "block", "plan", 2),
        gate("r1", "gate-plan", 0), stop("r1", "yield", "approve-plan", 2),
        gate("r1", "gate-approval", 0), gate("r1", "gate-ledger", 1),
        stop("r1", "block", "build", 3),
        gate("r1", "gate-ledger", 1), stop("r1", "block", "build", 4),
        gate("r1", "gate-ledger", 0), stop("r1", "yield", "shakeout", 4),
        gate("r1", "gate-acceptance", 0),
        stop("r1", "disarm-finished", "__end__", 4),
        # r2: first-pass spec gate, then parked at the human — still open
        gate("r2", "gate-spec", 0), stop("r2", "block", "plan", 1),
        gate("r2", "gate-plan", 0), stop("r2", "yield", "approve-plan", 1),
        # r3: same flow, DIFFERENT version hash — its own cohort
        gate("r3", "gate-spec", 0, fhash=HASH_B),
        stop("r3", "block", "plan", 1, fhash=HASH_B),
    ]
    (fd / ".flow-journal.jsonl").write_text(
        "".join(json.dumps(e) + "\n" for e in entries))
    return fd


def run_eval(*args):
    p = subprocess.run([sys.executable, str(FLOW_EVAL), *map(str, args)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def test_report_counts_runs_and_cohorts(feature):
    rc, out = run_eval(feature)
    assert rc == 0
    assert "3 run(s)" in out
    assert f"deliver@{HASH_A} (2)" in out and f"deliver@{HASH_B} (1)" in out


def test_outcomes_distinguish_finished_from_open(feature):
    rc, out = run_eval(feature)
    lines = {l.split()[0].lstrip(): l for l in out.splitlines()
             if l.strip().startswith("r")}
    assert "disarm-finished" in lines["r1"]
    assert "yield (open)" in lines["r2"]     # parked at approve-plan
    assert "block (open)" in lines["r3"]     # mid-loop when journal ends


def test_first_pass_and_mean_to_green(feature):
    rc, out = run_eval(feature)
    spec_line = next(l for l in out.splitlines()
                     if l.strip().startswith("gate-spec")
                     and f"@{HASH_A}" not in l)
    # cohort A: r1 first exec red (1 then 0 → to-green 2), r2 green (1)
    assert "first-pass=1/2" in spec_line
    assert "mean-to-green=1.5" in spec_line


def test_loop_gate_reads_as_iterations_not_failures(feature):
    rc, out = run_eval(feature)
    ledger_line = next(l for l in out.splitlines()
                       if l.strip().startswith("gate-ledger"))
    assert "execs=3" in ledger_line
    assert "0×1 1×2" in ledger_line
    assert "mean-to-green=3.0" in ledger_line


def test_yields_and_block_stops_per_run(feature):
    rc, out = run_eval(feature)
    # cohort A, 2 runs: approve-plan yielded in both → 1.0/run;
    # build blocked twice in r1 only → 1.0/run
    section = out.split(f"cohort deliver@{HASH_A}")[1]
    section = section.split("cohort ")[0]
    assert "approve-plan" in section and "shakeout" in section
    build_line = next(l for l in section.splitlines()
                      if l.strip().startswith("build"))
    assert "1.0" in build_line


def test_json_mode(feature):
    rc, out = run_eval(feature, "--json")
    assert rc == 0
    data = json.loads(out)
    assert len(data["runs"]) == 3
    coh = data["cohorts"][f"deliver@{HASH_A}"]
    assert coh["runs"] == 2
    assert coh["gates"]["gate-spec"]["first_pass"] == 1
    assert coh["gates"]["gate-ledger"]["to_green"] == [3]
    assert coh["yields"] == {"approve-plan": 2, "shakeout": 1}
    assert coh["block_stops"]["build"] == 2


def test_direct_jsonl_path_accepted(feature):
    rc, out = run_eval(feature / ".flow-journal.jsonl")
    assert rc == 0 and "3 run(s)" in out


def test_no_journal_exits_1(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    rc, out = run_eval(empty)
    assert rc == 1 and "no journal entries" in out


def test_malformed_lines_are_skipped(feature):
    jp = feature / ".flow-journal.jsonl"
    jp.write_text("not json\n" + jp.read_text() + "{\"half\": \n")
    rc, out = run_eval(feature)
    assert rc == 0 and "3 run(s)" in out
