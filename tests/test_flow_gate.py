"""Integration tests: patched hooks/loop-gate.py driving the REAL
bin/flow-check.py over the real flow twins, with stubbed gate scripts.

Mirrors the upstream test_loop_gate.py conventions: subprocess the hook
with a stdin payload, control the world through files, assert on stdout
JSON + marker state. The hook must always exit 0 (fail-open)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "loop-gate.py"
FLOW_CHECK = ROOT / "bin" / "flow-check.py"
DELIVER = ROOT / "flows" / "deliver.json"
PATCH = ROOT / "flows" / "patch.json"

GATE_STUB = """\
import sys, pathlib
fd = pathlib.Path(sys.argv[1])
ctl = fd / ".stub-{name}"
code = int(ctl.read_text()) if ctl.exists() else 0
print("FAIL  [stub]  simulated finding" if code else "ok")
sys.exit(code)
"""


def setup(tmp_path, flow, node, binds=None, extra=None):
    home = tmp_path / "home"
    home.mkdir()
    # deliver's spec/plan gates run the bound {gate_check_cmd}; the stub
    # reads <feature-dir>/.stub-gate-check (absent → exit 0)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gate-check.py").write_text(GATE_STUB.format(name="gate-check"))
    cwd = tmp_path / "proj"
    (cwd / "specs" / "demo").mkdir(parents=True)
    (cwd / "tasks").mkdir()
    # real repo: floor-check (fail-closed on missing base) and seal need one
    for git_args in (["init", "-b", "main"],
                     ["config", "user.email", "t@t"],
                     ["config", "user.name", "t"],
                     ["add", "-A"],
                     ["commit", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", *git_args], capture_output=True, cwd=cwd)
    marker = {"feature_dir": "specs/demo", "iteration": 0,
              "max_iterations": 25, "last_done": 0, "dry": 0,
              "flow": str(flow), "node": node,
              "flow_check": str(FLOW_CHECK),
              "gate_timeout": 30}
    marker["binds"] = {"netdust_flow": str(ROOT), "base_ref": "main",
                       "gate_check_cmd": str(stubs / "gate-check.py")}
    if binds:
        marker["binds"].update(binds)
    if extra:
        marker.update(extra)
    (cwd / "tasks" / ".harness-loop.json").write_text(json.dumps(marker))
    return home, cwd


def run_gate(cwd, home):
    p = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, timeout=120,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    return p.returncode, p.stdout


def marker_of(cwd):
    p = cwd / "tasks" / ".harness-loop.json"
    return json.loads(p.read_text()) if p.exists() else None


def suite(tmp_path, code):
    s = tmp_path / "suite.py"
    s.write_text(f"import sys; sys.exit({code})")
    return f"{sys.executable} {s}"


def test_flow_continue_blocks_and_persists_node(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 1)})
    rc, out = run_gate(cwd, home)
    assert rc == 0
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "gate-suite exit 1" in decision["reason"]
    m = marker_of(cwd)
    assert m["node"] == "build" and m["iteration"] == 1


def test_flow_finished_disarms(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 0)})
    rc, out = run_gate(cwd, home)
    assert rc == 0 and out.strip() == ""
    assert marker_of(cwd) is None


def test_flow_blocked_on_human_keeps_marker_updates_node(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "plan")
    rc, out = run_gate(cwd, home)          # gate-check stub passes → human
    assert rc == 0 and out.strip() == ""   # yield, no block
    m = marker_of(cwd)
    assert m is not None and m["node"] == "approve-plan"


def test_flow_arming_from_start(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "__start__")
    rc, out = run_gate(cwd, home)
    decision = json.loads(out)
    assert decision["decision"] == "block"
    assert "brainstorm" in decision["reason"]
    assert marker_of(cwd)["node"] == "brainstorm"


def test_flow_max_dry_override(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 1)},
                      extra={"max_dry": 1})
    run_gate(cwd, home)                     # done 0→1: dry resets
    rc, out = run_gate(cwd, home)           # done unchanged: dry=1 ≥ 1
    assert rc == 0 and out.strip() == ""
    assert marker_of(cwd) is None           # disarmed as dry loop


def journal_of(cwd):
    p = cwd / "specs" / "demo" / ".flow-journal.jsonl"
    if not p.exists():
        return None
    return [json.loads(l) for l in p.read_text().splitlines()]


def test_journal_records_red_gate_and_block_stop(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 1)})
    run_gate(cwd, home)
    j = journal_of(cwd)
    gates = [e for e in j if e["event"] == "gate"]
    stops = [e for e in j if e["event"] == "stop"]
    assert gates and gates[0]["node"] == "gate-suite" and gates[0]["exit"] == 1
    assert stops[-1]["decision"] == "block" and stops[-1]["node"] == "build"
    assert stops[-1]["verdict"] == "CONTINUE" and stops[-1]["iter"] == 1
    # every entry carries the run identity and the flow version hash
    assert all(e["run"] and e["flow"] == "patch" and len(e["fhash"]) == 12
               for e in j)
    # the minted run id is persisted so later stops share it
    assert marker_of(cwd)["run_id"] == stops[-1]["run"]


def test_journal_run_id_stable_across_stops(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 1)})
    run_gate(cwd, home)
    run_gate(cwd, home)
    stops = [e for e in journal_of(cwd) if e["event"] == "stop"]
    assert len(stops) == 2
    assert stops[0]["run"] == stops[1]["run"]
    assert [s["iter"] for s in stops] == [1, 2]


def test_journal_records_finish_and_survives_disarm(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 0)})
    run_gate(cwd, home)
    assert marker_of(cwd) is None            # disarmed
    j = journal_of(cwd)                      # the journal outlives the run
    assert j[-1]["decision"] == "disarm-finished"
    assert j[-1]["node"] == "__end__"
    # both gates of the green patch walk were journaled on the way out
    assert [e["node"] for e in j if e["event"] == "gate"] == [
        "gate-suite", "gate-floors"]


def test_journal_records_yield_on_human_node(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "plan")
    run_gate(cwd, home)                      # gate-plan passes → human
    j = journal_of(cwd)
    assert j[-1]["decision"] == "yield" and j[-1]["node"] == "approve-plan"
    assert j[-1]["verdict"] == "BLOCKED" and "reason" in j[-1]


def test_journal_records_dry_disarm(tmp_path):
    home, cwd = setup(tmp_path, PATCH, "build",
                      binds={"test_suite_cmd": suite(tmp_path, 1)},
                      extra={"max_dry": 1})
    run_gate(cwd, home)                      # done 0→1: dry resets
    run_gate(cwd, home)                      # done unchanged: disarm
    j = journal_of(cwd)
    assert j[-1]["decision"] == "disarm-dry"


def test_flowless_marker_is_ignored_untouched(tmp_path):
    # the spec-kit-era single-cycle /loop marker is retired: a marker
    # without flow fields is not ours — no block, no journal, and the
    # marker is left in place (never delete what we don't understand)
    home, cwd = setup(tmp_path, PATCH, "build")
    m = marker_of(cwd)
    del m["flow"], m["node"], m["flow_check"]
    (cwd / "tasks" / ".harness-loop.json").write_text(json.dumps(m))
    rc, out = run_gate(cwd, home)
    assert rc == 0 and out.strip() == ""
    assert marker_of(cwd) is not None       # left untouched
    assert journal_of(cwd) is None          # nothing journaled
