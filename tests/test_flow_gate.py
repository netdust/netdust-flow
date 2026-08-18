"""Integration tests: hooks/loop-gate.py driving the REAL
bin/flow-check.py over the real flow twins, with stubbed gate scripts.

Conventions: subprocess the hook with a stdin payload, control the
world through files, assert on stdout JSON + marker state. The hook
must always exit 0 (fail-open)."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "loop-gate.py"
FLOW_CHECK = ROOT / "bin" / "flow-check.py"
DELIVER = ROOT / "flows" / "deliver.json"
MARKER_REL = Path("tasks") / ".netdust-flow.json"
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
    marker = {"schema": "netdust-flow/1",
              "feature_dir": "specs/demo", "iteration": 0,
              "max_iterations": 25, "last_done": 0, "dry": 0,
              "flow": str(flow), "node": node,
              "flow_check": str(FLOW_CHECK),
              "gate_timeout": 30}
    # patch v2 runs the REAL floor-check, which fails closed without a
    # project floors file — the project owns its floors (docs/project-pack.md)
    (cwd / ".flow").mkdir(parents=True, exist_ok=True)
    (cwd / ".flow" / "floors.yaml").write_text(
        "floors:\n  schema:\n    paths: [\"**/migrations/**\"]\n")
    marker["binds"] = {"netdust_flow": str(ROOT), "base_ref": "main",
                       "floors_file": ".flow/floors.yaml",
                       "gate_check_cmd": str(stubs / "gate-check.py")}
    if binds:
        marker["binds"].update(binds)
    if extra:
        marker.update(extra)
    (cwd / MARKER_REL).write_text(json.dumps(marker))
    return home, cwd


def run_gate(cwd, home):
    p = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, timeout=120,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    return p.returncode, p.stdout


def marker_of(cwd):
    p = cwd / MARKER_REL
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
    # a marker without flow fields is not ours — no block, no journal,
    # and the marker is left in place (never delete what we don't
    # understand)
    home, cwd = setup(tmp_path, PATCH, "build")
    m = marker_of(cwd)
    del m["flow"], m["node"], m["flow_check"]
    (cwd / MARKER_REL).write_text(json.dumps(m))
    rc, out = run_gate(cwd, home)
    assert rc == 0 and out.strip() == ""
    assert marker_of(cwd) is not None       # left untouched
    assert journal_of(cwd) is None          # nothing journaled


def test_run_id_unique_across_concurrent_runs(tmp_path):
    # F1: two records armed in the same second used to receive the SAME
    # run id, which left feature-scoping as the only thing keeping one
    # run's evidence out of the other's gate. Run-scoping must stand on
    # its own.
    ids = set()
    for i in range(8):
        base = tmp_path / f"r{i}"
        base.mkdir()
        home, cwd = setup(base, PATCH, "build",
                          binds={"test_suite_cmd": suite(base, 1)})
        run_gate(cwd, home)
        ids.add(marker_of(cwd)["run_id"])
    assert len(ids) == 8, f"run ids collided: {sorted(ids)}"
    assert all(re.fullmatch(r"r\d{8}-\d{6}-[0-9a-f]{4}", rid)
               for rid in ids), sorted(ids)


# ── the hook path's dependency contract, asserted directly
#
# The `hooks-run-without-authoring-deps` CI job proves this by running
# on a bare interpreter, but that job fails LATE and reads like an
# unrelated breakage. flow-check.py imports flowspec, so flowspec is
# now part of the hook path; this test says so in one line.

STDLIB_OK = {
    "__future__", "argparse", "hashlib", "json", "os", "pathlib", "re",
    "secrets", "shlex", "shutil", "subprocess", "sys", "time", "datetime",
    "fnmatch", "typing",
}


def _toplevel_imports(path):
    """MODULE-LEVEL imports only: an import inside a guarded function
    (flow-check's `import yaml` for the staleness check) is optional by
    construction and never runs on a bare host."""
    import ast
    names = set()
    for node in ast.parse(Path(path).read_text()).body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_flowspec_imports_nothing_third_party():
    extra = _toplevel_imports(ROOT / "bin" / "flowspec.py") - STDLIB_OK
    assert not extra, f"flowspec is in the hook path; it may not import {extra}"


def test_hook_path_scripts_import_nothing_third_party():
    # PyYAML appears inside flow-check only behind a guarded try, for
    # the staleness check — never at module level
    for name in ("bin/flow-check.py", "hooks/loop-gate.py"):
        extra = _toplevel_imports(ROOT / name) - STDLIB_OK - {"flowspec"}
        assert not extra, f"{name} is in the hook path; it may not import {extra}"


def test_no_test_name_is_shadowed():
    """Two functions with one name means Python keeps the last and the
    earlier one never runs — coverage silently deleted, suite still
    green. This merge produced exactly that twice (a branch's F1/F2
    tests landing beside main's), so it is a check now rather than a
    thing someone has to notice."""
    import ast
    import collections
    shadowed = {}
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        names = [n.name for n in ast.parse(path.read_text()).body
                 if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        dupes = [n for n, c in collections.Counter(names).items() if c > 1]
        if dupes:
            shadowed[path.name] = dupes
    assert not shadowed, f"shadowed test functions: {shadowed}"
