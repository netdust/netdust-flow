"""Tests for flow-check.py — the netdust-flow walker.

Style follows the harness hook tests: subprocess the real script, stub
the gate scripts, control their exit codes through files in the feature
dir, assert on exit code + stdout contract.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLOW_CHECK = ROOT / "bin" / "flow-check.py"
DELIVER = ROOT / "flows" / "deliver.yaml"
PATCH = ROOT / "flows" / "patch.yaml"

GATE_STUB = """\
import sys, pathlib
fd = pathlib.Path(sys.argv[1])
ctl = fd / ".stub-{name}"
code = int(ctl.read_text()) if ctl.exists() else 0
print("FAIL  [stub]  simulated finding" if code else "ok")
sys.exit(code)
"""


@pytest.fixture()
def env(tmp_path):
    # plugin-root is only exercised by the relative-run-path test; the
    # real flows bind their gate commands (no plugin-resolved gates)
    plugin = tmp_path / "plugin"
    (plugin / "checks").mkdir(parents=True)
    (plugin / "checks" / "gate.py").write_text(
        GATE_STUB.format(name="gate-check"))
    feature = tmp_path / "feature"
    feature.mkdir()
    flowstub = tmp_path / "flowstub"
    (flowstub / "bin").mkdir(parents=True)
    baked = """\
import sys, pathlib
ctl = pathlib.Path(r'{ctl}')
code = int(ctl.read_text()) if ctl.exists() else 0
print("FAIL  [stub]  simulated finding" if code else "ok")
{extra}
sys.exit(code)
"""
    # deliver's spec/plan gates run the BOUND command {gate_check_cmd};
    # same control file name as before so set_gate() keeps working
    (flowstub / "bin" / "gate-check.py").write_text(baked.format(
        ctl=feature / ".stub-gate-check", extra=""))
    # the ledger stub emits an evidence-derived progress line, like the
    # real ledger.py — the walker must prefer it over checkbox counts
    (flowstub / "bin" / "ledger.py").write_text(baked.format(
        ctl=feature / ".stub-ledger",
        extra='print("progress: done=5 total=7")'))
    (flowstub / "bin" / "floor-check.py").write_text(baked.format(
        ctl=feature / ".stub-floor-check", extra=""))
    # seal stub: argv = [check, <feature-dir>, <node>]; per-node control
    # file; default exit 1 = no seal recorded (the real tool's default)
    (flowstub / "bin" / "seal.py").write_text("""\
import sys, pathlib
fd, node = pathlib.Path(sys.argv[2]), sys.argv[3]
ctl = fd / f".stub-seal-{node}"
code = int(ctl.read_text()) if ctl.exists() else 1
print(f"SEAL: stub exit {code} — {node}")
sys.exit(code)
""")
    return plugin, feature, flowstub


def run(flow, node, feature, plugin, *extra, flowstub=None):
    binds = []
    if flowstub is not None:
        binds = ["--bind", f"netdust_flow={flowstub}",
                 "--bind", "base_ref=main",
                 # patch v2: the floors file is the PROJECT's, bound like
                 # any other project value (the stub gate ignores it)
                 "--bind", "floors_file=.flow/floors.yaml",
                 "--bind", f"gate_check_cmd={flowstub}/bin/gate-check.py"]
    p = subprocess.run(
        [sys.executable, str(FLOW_CHECK), str(feature),
         "--flow", str(flow), "--node", node,
         "--plugin-root", str(plugin), *binds, *extra],
        capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def set_gate(feature, name, code):
    (feature / f".stub-{name}").write_text(str(code))


def set_seal(feature, node, code):
    (feature / f".stub-seal-{node}").write_text(str(code))


def next_of(out):
    for line in out.splitlines():
        if line.startswith("next: "):
            return line.split("next: ", 1)[1]
    return None


# ── deliver.yaml traversal ───────────────────────────────────────────

def test_agent_chain_continue(env):
    plugin, feature, flowstub = env
    rc, out = run(DELIVER, "brainstorm", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "spec"
    assert out.startswith("FLOW: CONTINUE")


def test_gate_pass_traverses_to_next_agent(env):
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 0)
    rc, out = run(DELIVER, "spec", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "plan"


def test_gate_fail_loops_back(env):
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 1)
    rc, out = run(DELIVER, "spec", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "spec"
    assert "gate-spec exit 1" in out


def test_plan_pass_blocks_on_human_approval(env):
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 0)
    rc, out = run(DELIVER, "plan", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "approve-plan"


# ── human decisions are evidence (I4): resumption is never approval ──

def test_human_resume_without_seal_reblocks(env):
    plugin, feature, flowstub = env
    rc, out = run(DELIVER, "approve-plan", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "approve-plan"


def test_sealed_approval_advances_to_build(env):
    plugin, feature, flowstub = env
    set_seal(feature, "approve-plan", 0)
    rc, out = run(DELIVER, "approve-plan", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "build"


def test_sealed_rejection_routes_back_to_plan(env):
    plugin, feature, flowstub = env
    set_seal(feature, "approve-plan", 2)
    rc, out = run(DELIVER, "approve-plan", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "plan"


def test_ledger_continue(env):
    plugin, feature, flowstub = env
    set_gate(feature, "ledger", 1)
    rc, out = run(DELIVER, "build", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "build"


def test_ledger_blocked_goes_to_unblock_node(env):
    plugin, feature, flowstub = env
    set_gate(feature, "ledger", 2)
    rc, out = run(DELIVER, "build", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "unblock"       # not __human__


def test_unblock_resume_rederives_the_ledger(env):
    # the fix for the absorbing-state deadlock: after the human resolves
    # the [HUMAN] task, the walk re-runs the ledger and moves on
    plugin, feature, flowstub = env
    set_gate(feature, "ledger", 1)
    rc, out = run(DELIVER, "unblock", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "build"


def test_ledger_finished_blocks_on_shakeout(env):
    plugin, feature, flowstub = env
    set_gate(feature, "ledger", 0)
    rc, out = run(DELIVER, "build", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "shakeout"


def test_shakeout_resume_alone_does_not_finish(env):
    # the old bug: resuming after a FAILED shakeout finished the flow
    plugin, feature, flowstub = env
    rc, out = run(DELIVER, "shakeout", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "shakeout"


def test_shakeout_sealed_approved_finishes(env):
    plugin, feature, flowstub = env
    set_seal(feature, "shakeout", 0)
    rc, out = run(DELIVER, "shakeout", feature, plugin, flowstub=flowstub)
    assert rc == 0 and out.startswith("FLOW: FINISHED")


def test_shakeout_sealed_rejected_reopens_build(env):
    plugin, feature, flowstub = env
    set_seal(feature, "shakeout", 2)
    rc, out = run(DELIVER, "shakeout", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "build"


# ── patch.yaml traversal ─────────────────────────────────────────────

def test_patch_suite_red_loops(env, tmp_path):
    plugin, feature, flowstub = env
    suite = tmp_path / "suite.py"
    suite.write_text("import sys; sys.exit(1)")
    rc, out = run(PATCH, "build", feature, plugin,
                  "--bind", f"test_suite_cmd={sys.executable} {suite}",
                  flowstub=flowstub)
    assert rc == 1 and next_of(out) == "build"


def test_patch_suite_green_finishes(env, tmp_path):
    plugin, feature, flowstub = env
    suite = tmp_path / "suite.py"
    suite.write_text("import sys; sys.exit(0)")
    rc, out = run(PATCH, "build", feature, plugin,
                  "--bind", f"test_suite_cmd={sys.executable} {suite}",
                  flowstub=flowstub)
    assert rc == 0 and out.startswith("FLOW: FINISHED")


def test_patch_floor_triggered_goes_to_redispatch(env, tmp_path):
    plugin, feature, flowstub = env
    suite = tmp_path / "suite.py"
    suite.write_text("import sys; sys.exit(0)")
    set_gate(feature, "floor-check", 2)
    rc, out = run(PATCH, "build", feature, plugin,
                  "--bind", f"test_suite_cmd={sys.executable} {suite}",
                  flowstub=flowstub)
    assert rc == 2 and next_of(out) == "redispatch"    # not __human__


def test_patch_redispatch_sealed_finishes(env):
    plugin, feature, flowstub = env
    set_seal(feature, "redispatch", 0)
    rc, out = run(PATCH, "redispatch", feature, plugin, flowstub=flowstub)
    assert rc == 0 and out.startswith("FLOW: FINISHED")


def test_patch_redispatch_unsealed_reblocks(env):
    plugin, feature, flowstub = env
    rc, out = run(PATCH, "redispatch", feature, plugin, flowstub=flowstub)
    assert rc == 2 and next_of(out) == "redispatch"


def test_unbound_placeholder_blocks(env):
    plugin, feature, flowstub = env
    rc, out = run(PATCH, "build", feature, plugin, flowstub=flowstub)
    assert rc == 2 and "unbound placeholder" in out


# ── contract details ─────────────────────────────────────────────────

def test_progress_uses_tasks_md(env):
    plugin, feature, flowstub = env
    (feature / "tasks.md").write_text(
        "- [x] T01 done thing\n- [ ] T02 open thing\n")
    rc, out = run(DELIVER, "brainstorm", feature, plugin, flowstub=flowstub)
    assert "progress: done=1 total=2" in out


def test_progress_prefers_gate_evidence_over_checkboxes(env):
    # I3 tightened: when a gate printed evidence-derived progress (the
    # ledger's attest counts), checkbox counting must not feed dry-loop
    plugin, feature, flowstub = env
    (feature / "tasks.md").write_text(
        "- [x] T01 done thing\n- [ ] T02 open thing\n")
    set_gate(feature, "ledger", 1)
    rc, out = run(DELIVER, "build", feature, plugin, flowstub=flowstub)
    assert "progress: done=5 total=7" in out
    assert "done=1 total=2" not in out


def test_unknown_node_blocks(env):
    plugin, feature, flowstub = env
    rc, out = run(DELIVER, "nonexistent", feature, plugin, flowstub=flowstub)
    assert rc == 2 and "unknown node" in out


def test_json_twin_loads(env):
    plugin, feature, flowstub = env
    lint = ROOT / "bin" / "flow-lint.py"
    subprocess.run([sys.executable, str(lint), str(DELIVER), "--compile"],
                   capture_output=True, text=True, check=True)
    twin = DELIVER.with_suffix(".json")
    assert twin.exists()
    rc, out = run(twin, "brainstorm", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "spec"


def test_cycle_without_agent_blocks(env, tmp_path):
    plugin, feature, flowstub = env
    bad = tmp_path / "cycle.json"
    bad.write_text(json.dumps({
        "flow": "cycle", "version": 0, "state": {"gate": {}},
        "nodes": [
            {"id": "g1", "kind": "gate",
             "run": "checks/gate.py {feature_dir}"},
        ],
        "edges": [
            {"from": "__start__", "to": "g1"},
            {"from": "g1", "to": "g1"},
        ],
    }))
    rc, out = run(bad, "__start__", feature, plugin)
    assert rc == 2 and "revisited" in out


# ── trace lines (journal food) ───────────────────────────────────────

def traces_of(out):
    return [json.loads(l[len("trace: "):])
            for l in out.splitlines() if l.startswith("trace: ")]


def test_trace_lines_follow_the_contract_lines(env):
    # the stdout contract is a superset: 3 contract lines FIRST (the
    # hook reads line 1 as the reason), trace lines after
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 1)
    rc, out = run(DELIVER, "spec", feature, plugin, flowstub=flowstub)
    lines = out.splitlines()
    assert lines[0].startswith("FLOW: ")
    assert lines[1].startswith("next: ")
    assert lines[2].startswith("progress: ")
    assert all(l.startswith("trace: ") for l in lines[3:])


def test_trace_records_red_gate_exit(env):
    # a failing gate leaves no attest and no ledger mark — the trace
    # line is the only record that the red exit ever happened
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 1)
    rc, out = run(DELIVER, "spec", feature, plugin, flowstub=flowstub)
    assert any(t["event"] == "gate" and t["node"] == "gate-spec"
               and t["exit"] == 1 for t in traces_of(out))


def test_trace_records_green_gate_exit(env):
    plugin, feature, flowstub = env
    set_gate(feature, "gate-check", 0)
    rc, out = run(DELIVER, "spec", feature, plugin, flowstub=flowstub)
    assert any(t["event"] == "gate" and t["node"] == "gate-spec"
               and t["exit"] == 0 for t in traces_of(out))


def test_trace_records_every_gate_in_a_multi_gate_walk(env, tmp_path):
    # patch, suite green, floors clean: gate-suite AND gate-floors both
    # execute in one walk and both must appear
    plugin, feature, flowstub = env
    suite = tmp_path / "suite.py"
    suite.write_text("import sys; sys.exit(0)")
    rc, out = run(PATCH, "build", feature, plugin,
                  "--bind", f"test_suite_cmd={sys.executable} {suite}",
                  flowstub=flowstub)
    nodes = [t["node"] for t in traces_of(out) if t["event"] == "gate"]
    assert nodes == ["gate-suite", "gate-floors"]


def test_trace_gate_error_on_unbound_placeholder(env):
    plugin, feature, flowstub = env
    rc, out = run(PATCH, "build", feature, plugin, flowstub=flowstub)
    assert any(t["event"] == "gate-error" and t["node"] == "gate-suite"
               for t in traces_of(out))


# ── twin staleness (drift is blocked, not documented) ────────────────

MINI_FLOW = {
    "flow": "mini", "version": 1, "state": {"gate": {}},
    "nodes": [{"id": "work", "kind": "agent",
               "craft": ["agents/implementer"]},
              {"id": "check", "kind": "gate", "run": "true"}],
    "edges": [{"from": "__start__", "to": "work"},
              {"from": "work", "to": "check"},
              {"from": "check", "to": "__end__", "when": "gate.exit == 0"},
              {"from": "check", "to": "work", "when": "gate.exit != 0"}],
}


def test_stale_twin_blocks(env, tmp_path):
    # the YAML parses to a DIFFERENT graph than the twin → fail closed
    plugin, feature, flowstub = env
    (tmp_path / "mini.json").write_text(json.dumps(MINI_FLOW))
    changed = dict(MINI_FLOW, version=2)
    import yaml
    (tmp_path / "mini.yaml").write_text(yaml.safe_dump(changed))
    rc, out = run(tmp_path / "mini.json", "work", feature, plugin)
    assert rc == 2 and "STALE" in out


def test_comment_only_yaml_edit_does_not_block(env, tmp_path):
    # comments parse away: same data → no block, cohort hash untouched
    plugin, feature, flowstub = env
    (tmp_path / "mini.json").write_text(json.dumps(MINI_FLOW))
    import yaml
    (tmp_path / "mini.yaml").write_text(
        "# a comment edit, semantically identical\n"
        + yaml.safe_dump(MINI_FLOW))
    rc, out = run(tmp_path / "mini.json", "work", feature, plugin)
    assert rc == 0 and out.startswith("FLOW: FINISHED")   # walked normally
    assert "STALE" not in out


def test_twin_without_source_loads_fine(env, tmp_path):
    plugin, feature, flowstub = env
    (tmp_path / "solo.json").write_text(json.dumps(MINI_FLOW))
    rc, out = run(tmp_path / "solo.json", "work", feature, plugin)
    assert rc == 0 and "STALE" not in out


# ── condition grammar unit tests ─────────────────────────────────────

def _fc():
    import importlib.util
    spec = importlib.util.spec_from_file_location("fc", FLOW_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("expr,state,expected", [
    ("gate.exit == 0", {"gate": {"exit": 0}}, True),
    ("gate.exit != 0", {"gate": {"exit": 1}}, True),
    ("gate.exit >= 2", {"gate": {"exit": 2}}, True),
    ("risk in [A, B]", {"risk": "A"}, True),
    ("risk in [A, B]", {"risk": "C"}, False),
    ("missing.key == 0", {}, False),
])
def test_eval_cond(expr, state, expected):
    assert _fc().eval_cond(expr, state) is expected


def test_prose_condition_raises():
    with pytest.raises(ValueError):
        _fc().eval_cond("if the work looks risky", {})


def test_arming_from_start(env):
    plugin, feature, flowstub = env
    rc, out = run(DELIVER, "__start__", feature, plugin, flowstub=flowstub)
    assert rc == 1 and next_of(out) == "brainstorm"


# ── project-owned flows: the runtime supplies the machine, the project
# supplies the flow AND its gates (netdust-flow stays domain-agnostic)

PROJECT_FLOW = """\
flow: site
version: 1
state:
  gate: {}
nodes:
  - id: build
    kind: agent
    craft: [.flow/craft/build.md]
    out: [code]
  - id: gate-project
    kind: gate
    run: ".flow/bin/project-gate.py {feature_dir}"
edges:
  - {from: __start__, to: build}
  - {from: build, to: gate-project}
  - {from: gate-project, to: __end__, when: gate.exit == 0}
  - {from: gate-project, to: build, when: gate.exit != 0}
"""


def _project(tmp_path, gate_exit):
    """A project that owns both its flow and the gate the flow names."""
    proj = tmp_path / "site-repo"
    (proj / ".flow" / "bin").mkdir(parents=True)
    (proj / ".flow" / "flows").mkdir(parents=True)
    (proj / ".flow" / "flows" / "site.yaml").write_text(PROJECT_FLOW)
    (proj / ".flow" / "bin" / "project-gate.py").write_text(
        f"import sys\nprint('ok' if not {gate_exit} else 'FAIL  [wp]  red')\n"
        f"sys.exit({gate_exit})\n")
    (proj / "feature").mkdir()
    return proj


def test_project_owned_flow_and_gate_walks(tmp_path, ):
    proj = _project(tmp_path, 0)
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    rc, out = run(proj / ".flow" / "flows" / "site.yaml", "build",
                  proj / "feature", plugin, "--cwd", str(proj))
    assert rc == 0, out          # FINISHED through a gate the repo owns
    assert "FINISHED" in out


def test_project_gate_red_routes_back(tmp_path):
    proj = _project(tmp_path, 1)
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    rc, out = run(proj / ".flow" / "flows" / "site.yaml", "build",
                  proj / "feature", plugin, "--cwd", str(proj))
    assert rc == 1 and next_of(out) == "build", out


def test_project_gate_wins_over_plugin_root(tmp_path):
    # same relative name in both places: the project's must run, or a
    # globally installed script could silently answer for a project
    proj = _project(tmp_path, 0)
    plugin = tmp_path / "plugin"
    (plugin / ".flow" / "bin").mkdir(parents=True)
    (plugin / ".flow" / "bin" / "project-gate.py").write_text(
        "import sys\nprint('FAIL  [plugin]  wrong gate ran')\nsys.exit(1)\n")
    rc, out = run(proj / ".flow" / "flows" / "site.yaml", "build",
                  proj / "feature", plugin, "--cwd", str(proj))
    assert rc == 0, out
    assert "wrong gate ran" not in out
