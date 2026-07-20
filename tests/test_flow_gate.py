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
    stub_kit = home / ".claude" / "plugins" / "netdust-agent" / "spec-kit"
    stub_kit.mkdir(parents=True)
    for name in ("gate-check", "loop-check"):
        (stub_kit / f"{name}.py").write_text(GATE_STUB.format(name=name))
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
    marker["binds"] = {"netdust_flow": str(ROOT), "base_ref": "main"}
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


def test_legacy_marker_ignores_flow_path(tmp_path):
    # legacy path resolves spec-kit relative to the gate file itself, so
    # give the gate a private home with a stub loop-check sibling.
    site = tmp_path / "site"
    (site / "hooks").mkdir(parents=True)
    (site / "spec-kit").mkdir()
    (site / "hooks" / "loop-gate.py").write_text(GATE.read_text())
    (site / "spec-kit" / "loop-check.py").write_text(
        GATE_STUB.format(name="loop-check"))
    home, cwd = setup(tmp_path, PATCH, "build")
    m = marker_of(cwd)
    del m["flow"], m["node"], m["flow_check"]
    (cwd / "tasks" / ".harness-loop.json").write_text(json.dumps(m))
    p = subprocess.run(
        [sys.executable, str(site / "hooks" / "loop-gate.py")],
        input=json.dumps({"cwd": str(cwd)}),
        capture_output=True, text=True, timeout=60,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    assert p.returncode == 0 and p.stdout.strip() == ""
    assert marker_of(cwd) is None           # FINISHED disarm, legacy path
