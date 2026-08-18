"""A node does not leave until it delivered what it declared (F03).

Run 0004's `gate-plan` could not fail on a missing plan: the project's
spec-gate put every plan-stage check behind `if plan.exists()`, so a
missing plan.md returned "exit 0 — structure clean". It was observed
twice with no plan on disk. The plan was then caught one node later by
gate-converge, which failed for an unrelated reason — so the operator
was told "no convergence review" when the real state was "there is no
plan".

The gate was fixable, but the rule belongs in the walker, once, for
every gate a project will ever write: a flow already DECLARES what each
node produces (`out:`), and nothing read it. Now the walk refuses to
advance out of an agent node whose declared file artifacts are not
there — the node keeps the work instead of handing a gate something to
be wrong about.

Prose outcomes stay prose: `out: [code, checked tasks]` and
`out: [seal approve-plan]` name results no filesystem check can settle,
and treating them as filenames would block every run at `build`.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLOW_CHECK = ROOT / "bin" / "flow-check.py"

FLOW = """\
flow: artifacts
version: 1
state:
  gate: {}
nodes:
  - id: plan
    kind: agent
    out: [plan.md, tasks.md]
  - id: gate-plan
    kind: gate
    run: "{gate} {feature_dir}"
  - id: build
    kind: agent
    in: [tasks.md]
    out: [code, checked tasks]
  - id: gate-done
    kind: gate
    run: "{gate} {feature_dir}"
edges:
  - {from: __start__, to: plan}
  - {from: plan, to: gate-plan}
  - {from: gate-plan, to: build, when: gate.exit == 0}
  - {from: gate-plan, to: plan, when: gate.exit != 0}
  - {from: build, to: gate-done}
  - {from: gate-done, to: __end__, when: gate.exit == 0}
  - {from: gate-done, to: build, when: gate.exit != 0}
"""

# Records that it ran, so "the gate never executed" is provable rather
# than inferred from the verdict line.
GATE_STUB = """\
import sys, pathlib
pathlib.Path(sys.argv[1], ".gate-ran").write_text("yes")
print("ok")
sys.exit(0)
"""


@pytest.fixture()
def env(tmp_path):
    feature = tmp_path / "feature"
    feature.mkdir()
    gate = tmp_path / "gate.py"
    gate.write_text(GATE_STUB)
    flow = tmp_path / "artifacts.yaml"
    flow.write_text(FLOW.replace("{gate}", str(gate)))
    return flow, feature


def run(flow, node, feature):
    p = subprocess.run(
        [sys.executable, str(FLOW_CHECK), str(feature),
         "--flow", str(flow), "--node", node],
        capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def next_of(out):
    for line in out.splitlines():
        if line.startswith("next: "):
            return line.split("next: ", 1)[1]
    return None


def test_a_node_that_delivered_nothing_keeps_the_work(env):
    flow, feature = env
    rc, out = run(flow, "plan", feature)

    assert rc == 1, "CONTINUE — the work is not done, nothing is blocked"
    assert next_of(out) == "plan", "the node keeps it; the walk does not leave"
    assert not (feature / ".gate-ran").exists(), (
        "the gate must not run at all — a gate handed nothing to measure "
        "is the whole defect")


def test_the_verdict_names_what_is_missing(env):
    """The damage in run 0004 was diagnostic: the operator was told the
    wrong thing about the wrong node. The reason has to be specific."""
    flow, feature = env
    (feature / "plan.md").write_text("# plan\n")

    rc, out = run(flow, "plan", feature)

    first = out.splitlines()[0]
    assert "tasks.md" in first
    assert "plan.md" not in first, "delivered artifacts are not the complaint"


def test_a_node_that_delivered_advances(env):
    flow, feature = env
    (feature / "plan.md").write_text("# plan\n")
    (feature / "tasks.md").write_text("- [ ] T01 — do it\n")

    rc, out = run(flow, "plan", feature)

    assert rc == 1 and next_of(out) == "build"
    assert (feature / ".gate-ran").exists(), "the gate runs once fed"


def test_prose_outcomes_are_never_filesystem_checks(env):
    """`out: [code, checked tasks]` names results no stat() can settle.
    Reading them as filenames would park every run at `build` forever."""
    flow, feature = env
    (feature / "tasks.md").write_text("- [ ] T01 — do it\n")

    rc, out = run(flow, "build", feature)

    assert next_of(out) == "__end__"
    assert (feature / ".gate-ran").exists()


def test_the_rule_holds_on_the_built_in_road(env):
    """deliver.yaml declares `out: [plan.md, tasks.md]` on `plan` — the
    exact declaration run 0004 had and nothing read."""
    _, feature = env
    deliver = ROOT / "flows" / "deliver.yaml"

    rc, out = run(deliver, "plan", feature)

    assert rc == 1 and next_of(out) == "plan"
    assert "plan.md" in out.splitlines()[0]
