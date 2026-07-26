"""Tests for flow-arm.py — arming as verification, not assertion.

Style follows test_flow_check.py: subprocess the real script against a
throwaway project, assert on the exit code, the refusal lines, and the
marker it did (or did not) write.

The load-bearing assertion in every refusal test is the SAME one:
`tasks/.harness-loop.json` must not exist. A refusal that still armed
is worse than no check at all — it would put a known-broken config on
the road with a warning nobody reads.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLOW_ARM = ROOT / "bin" / "flow-arm.py"
MARKER_REL = Path("tasks") / ".harness-loop.json"

# No placeholders but {feature_dir} (the walker's own) — the base case:
# a project that owns its flow and the gate the flow names.
SELF_CONTAINED = """\
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

# The gate command is data the project supplies (CLAUDE.md / --bind).
BOUND_GATE = SELF_CONTAINED.replace(
    'run: ".flow/bin/project-gate.py {feature_dir}"',
    'run: "{gate_check_cmd} {feature_dir}"')

# Declares tasks.md, so checkbox progress will exist for the dry counter.
PRODUCES_TASKS = SELF_CONTAINED.replace("out: [code]", "out: [code, tasks.md]")

# A diff-scanning gate: the base ref has to resolve before arming.
NEEDS_BASE = SELF_CONTAINED.replace(
    'run: ".flow/bin/project-gate.py {feature_dir}"',
    'run: ".flow/bin/project-gate.py --base {base_ref}"')

# I2: an agent node may not finish. The lint refuses this; so must arm.
RED_LINT = """\
flow: site
version: 1
state:
  gate: {}
nodes:
  - id: build
    kind: agent
    craft: [.flow/craft/build.md]
edges:
  - {from: __start__, to: build}
  - {from: build, to: __end__}
"""


def project(tmp_path, flow_text=SELF_CONTAINED, name="site", *,
            gate=True, claude_md=None, pack=None, plan=None, tasks=None):
    proj = tmp_path / "site-repo"
    (proj / ".flow" / "flows").mkdir(parents=True, exist_ok=True)
    (proj / ".flow" / "bin").mkdir(parents=True, exist_ok=True)
    (proj / ".flow" / "flows" / f"{name}.yaml").write_text(flow_text)
    if gate:
        (proj / ".flow" / "bin" / "project-gate.py").write_text(
            "import sys\nprint('ok')\nsys.exit(0)\n")
    if claude_md is not None:
        (proj / "CLAUDE.md").write_text(claude_md)
    if pack is not None:
        (proj / ".flow" / "pack.yaml").write_text(pack)
    if plan is not None or tasks is not None:
        (proj / "feature").mkdir(exist_ok=True)
    if plan is not None:
        (proj / "feature" / "plan.md").write_text(plan)
    if tasks is not None:
        (proj / "feature" / "tasks.md").write_text(tasks)
    return proj


def arm(proj, *extra, feature="feature", flow="site"):
    p = subprocess.run(
        [sys.executable, str(FLOW_ARM), feature, flow,
         "--project", str(proj), *extra],
        capture_output=True, text=True, timeout=60, cwd=str(proj))
    return p.returncode, p.stdout + p.stderr


def marker(proj):
    return json.loads((proj / MARKER_REL).read_text())


# ── the happy path ───────────────────────────────────────────────────

def test_arms_and_records_the_resolved_twin(tmp_path):
    proj = project(tmp_path)
    rc, out = arm(proj)
    assert rc == 0, out
    m = marker(proj)
    # the ABSOLUTE twin path, never the bare name — a later status check
    # must not be able to drift onto a different file
    assert m["flow"] == str((proj / ".flow" / "flows" / "site.json").resolve())
    assert Path(m["flow"]).exists()          # --compile ran
    assert m["node"] == "__start__"
    assert m["binds"]["netdust_flow"] == str(ROOT)
    assert "feature_dir" not in m["binds"]   # the walker supplies it
    assert m["flow_check"] == str(ROOT / "bin" / "flow-check.py")
    assert "project-owned" in out


def test_project_flow_wins_over_the_builtin_road(tmp_path):
    # `deliver` exists in the runtime; the project's must win, and the
    # confirmation must say which file it bound
    proj = project(tmp_path, name="deliver")
    rc, out = arm(proj, flow="deliver")
    assert rc == 0, out
    assert "project-owned" in out
    assert str(proj) in marker(proj)["flow"]


def test_feature_dir_and_gitignore_are_prepared(tmp_path):
    # the hook journals into <feature-dir>/.flow-journal.jsonl fail-open:
    # a missing dir loses the whole run journal silently
    proj = project(tmp_path)
    rc, out = arm(proj)
    assert rc == 0, out
    assert (proj / "feature").is_dir()
    ignored = (proj / ".gitignore").read_text()
    assert str(MARKER_REL) in ignored
    assert ".flow-journal.jsonl" in ignored


def test_budget_comes_from_the_plan(tmp_path):
    proj = project(tmp_path, plan="# Plan\n\nLoop budget: ~7\n")
    rc, out = arm(proj)
    assert rc == 0, out
    assert marker(proj)["max_iterations"] == 7


def test_max_dry_derives_from_checkbox_progress(tmp_path):
    # a flow that produces tasks.md gets real progress → the dry-loop
    # counter is meaningful; one that never does would be disarmed by it
    with_tasks = project(tmp_path / "a", PRODUCES_TASKS)
    without = project(tmp_path / "b", SELF_CONTAINED)
    assert arm(with_tasks)[0] == 0
    assert arm(without)[0] == 0
    assert marker(with_tasks)["max_dry"] == 2
    assert marker(without)["max_dry"] == 25


def test_claude_md_supplies_the_gate_command(tmp_path):
    proj = project(tmp_path, BOUND_GATE,
                   claude_md="    Gate check: python3 .flow/bin/project-gate.py\n")
    rc, out = arm(proj)
    assert rc == 0, out
    assert marker(proj)["binds"]["gate_check_cmd"] == \
        "python3 .flow/bin/project-gate.py"


# ── refusals: nothing is written ─────────────────────────────────────

def test_unknown_flow_refuses(tmp_path):
    proj = project(tmp_path)
    rc, out = arm(proj, flow="nowhere")
    assert rc == 1
    assert "REFUSED  [flow]" in out
    assert not (proj / MARKER_REL).exists()


def test_red_lint_refuses(tmp_path):
    proj = project(tmp_path, RED_LINT)
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [lint]" in out
    assert "I2" in out                       # the lint's own verdict is shown
    assert not (proj / MARKER_REL).exists()


def test_missing_gate_program_refuses(tmp_path):
    proj = project(tmp_path, gate=False)
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [gates]" in out
    assert "project-gate.py" in out
    assert not (proj / MARKER_REL).exists()


def test_unbound_placeholder_refuses_and_names_it(tmp_path):
    # deliver's old precondition 2 ("no gate command → refuse"), now a
    # consequence of the generic rule rather than a per-flow paragraph
    proj = project(tmp_path, BOUND_GATE)
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [binds]" in out
    assert "gate_check_cmd" in out
    assert "CLAUDE.md" in out                # says how to supply it
    assert not (proj / MARKER_REL).exists()


def test_bind_flag_satisfies_the_placeholder(tmp_path):
    proj = project(tmp_path, BOUND_GATE)
    rc, out = arm(proj, "--bind",
                  "gate_check_cmd=python3 .flow/bin/project-gate.py")
    assert rc == 0, out
    assert marker(proj)["binds"]["gate_check_cmd"].endswith("project-gate.py")


def test_unknown_start_node_refuses(tmp_path):
    proj = project(tmp_path)
    rc, out = arm(proj, "--node", "nonesuch")
    assert rc == 1
    assert "REFUSED  [node]" in out
    assert not (proj / MARKER_REL).exists()


def test_grafting_onto_a_declared_node_arms(tmp_path):
    proj = project(tmp_path)
    rc, out = arm(proj, "--node", "build")
    assert rc == 0, out
    assert marker(proj)["node"] == "build"


def test_already_armed_refuses(tmp_path):
    proj = project(tmp_path)
    assert arm(proj)[0] == 0
    before = (proj / MARKER_REL).read_text()
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [armed]" in out
    # the live run's marker — and with it its run id — survives untouched
    assert (proj / MARKER_REL).read_text() == before


def test_missing_required_tool_refuses(tmp_path):
    proj = project(tmp_path, pack=(
        "pack: site\ndescription: test pack\n"
        "requires:\n  - {name: definitely-not-a-real-binary, why: \"the gate\"}\n"))
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [requires]" in out
    assert not (proj / MARKER_REL).exists()


def test_optional_tool_only_warns(tmp_path):
    proj = project(tmp_path, pack=(
        "pack: site\ndescription: test pack\n"
        "requires:\n  - {name: definitely-not-a-real-binary, why: \"nice to have\","
        " optional: true}\n"))
    rc, out = arm(proj)
    assert rc == 0, out
    assert "WARN    [requires]" in out


def test_unresolvable_base_ref_refuses(tmp_path):
    # floor-check fails closed on a bad base mid-run; arming is where
    # that is one line instead of a dead run
    proj = project(tmp_path, NEEDS_BASE)
    rc, out = arm(proj)
    assert rc == 1
    assert "REFUSED  [base]" in out
    assert not (proj / MARKER_REL).exists()


def test_resolvable_base_ref_arms(tmp_path):
    proj = project(tmp_path, NEEDS_BASE)
    for args in (["git", "init", "-b", "main"],
                 ["git", "config", "user.email", "t@t.invalid"],
                 ["git", "config", "user.name", "t"],
                 ["git", "add", "-A"],
                 ["git", "commit", "-m", "base", "--no-gpg-sign"]):
        subprocess.run(args, cwd=str(proj), capture_output=True, check=True)
    rc, out = arm(proj)
    assert rc == 0, out
    assert marker(proj)["binds"]["base_ref"] == "main"


@pytest.mark.parametrize("bad", ["novalue", "=empty"])
def test_malformed_bind_refuses(tmp_path, bad):
    proj = project(tmp_path)
    rc, out = arm(proj, "--bind", bad)
    assert rc == 1
    assert "REFUSED  [binds]" in out
    assert not (proj / MARKER_REL).exists()
