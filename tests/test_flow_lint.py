"""Static-gate tests: flow-lint enforces the schema and the graph
invariants (I1, I2, I4) that make the flow a well-formed state machine."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINT = ROOT / "bin" / "flow-lint.py"
DELIVER = ROOT / "flows" / "deliver.yaml"
PATCH = ROOT / "flows" / "patch.yaml"

VALID = """\
flow: t
version: 0
state:
  gate: {}
nodes:
  - id: work
    kind: agent
    craft: [agents/implementer]
  - id: check
    kind: gate
    run: "true"
edges:
  - {from: __start__, to: work}
  - {from: work, to: check}
  - {from: check, to: __end__, when: gate.exit == 0}
  - {from: check, to: work, when: gate.exit != 0}
"""


def lint(tmp_path, text, name="t.yaml"):
    f = tmp_path / name
    f.write_text(text)
    p = subprocess.run([sys.executable, str(LINT), str(f)],
                       capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout


def test_real_flows_lint_clean():
    p = subprocess.run([sys.executable, str(LINT), str(DELIVER), str(PATCH)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout
    assert "0 FAIL" in p.stdout


def test_valid_minimal_flow(tmp_path):
    rc, out = lint(tmp_path, VALID)
    assert rc == 0, out


def test_prose_condition_fails_i1(tmp_path):
    rc, out = lint(tmp_path, VALID.replace(
        "when: gate.exit == 0", "when: if it looks fine"))
    assert rc == 1 and "[I1]" in out


def test_agent_finish_fails_i2(tmp_path):
    bad = VALID.replace("  - {from: work, to: check}\n",
                        "  - {from: work, to: check, when: gate.exit == 0}\n"
                        "  - {from: work, to: __end__, when: gate.exit != 0}\n")
    rc, out = lint(tmp_path, bad)
    assert rc == 1 and "[I2]" in out


def test_dead_end_node_fails_i4(tmp_path):
    bad = VALID + """\
  - {from: check, to: stray, when: gate.exit == 2}
"""
    bad = bad.replace("nodes:", """\
nodes:
  - id: stray
    kind: agent
    craft: [agents/implementer]
""")
    rc, out = lint(tmp_path, bad)
    assert rc == 1 and "[I4]" in out and "no outgoing edge" in out


def test_human_pseudo_state_warns_i4(tmp_path):
    warned = VALID.replace("  - {from: check, to: work, when: gate.exit != 0}",
                           "  - {from: check, to: __human__, when: gate.exit != 0}")
    rc, out = lint(tmp_path, warned)
    assert rc == 0                     # WARN never fails the gate
    assert "WARN" in out and "__human__" in out


HUMAN_FLOW = """\
flow: t
version: 0
state:
  gate: {}
nodes:
  - id: work
    kind: agent
    craft: [agents/implementer]
  - id: check
    kind: gate
    run: "true"
  - id: decide
    kind: human
edges:
  - {from: __start__, to: work}
  - {from: work, to: check}
  - {from: check, to: decide, when: gate.exit == 0}
  - {from: check, to: work, when: gate.exit != 0}
  - {from: decide, to: __end__}
"""


def test_human_direct_finish_warns_i4(tmp_path):
    # machine-legal (I2 allows human -> __end__) but protocol-deprecated:
    # a finish should read recorded evidence via a seal gate
    rc, out = lint(tmp_path, HUMAN_FLOW)
    assert rc == 0                     # WARN never fails the gate
    assert "WARN" in out and "finishes directly" in out


def test_human_to_non_gate_warns_i4(tmp_path):
    # keep __end__ reachable (via the gate) while the human routes to
    # an agent — the warned pattern, in an otherwise sound graph
    warned = HUMAN_FLOW.replace(
        "  - {from: check, to: decide, when: gate.exit == 0}",
        "  - {from: check, to: __end__, when: gate.exit == 0}\n"
        "  - {from: check, to: decide, when: gate.exit == 2}").replace(
        "  - {from: decide, to: __end__}",
        "  - {from: decide, to: work}")
    rc, out = lint(tmp_path, warned)
    assert rc == 0, out
    assert "WARN" in out and "re-enter the machine through a gate" in out


def test_human_to_seal_gate_is_clean(tmp_path):
    # the I4 pattern: human -> gate -> __end__ produces no warnings
    clean = HUMAN_FLOW.replace(
        "  - {from: decide, to: __end__}",
        """\
  - {from: decide, to: gate-seal}
  - {from: gate-seal, to: __end__, when: gate.exit == 0}
  - {from: gate-seal, to: decide, when: gate.exit != 0}""").replace(
        "  - id: decide\n    kind: human",
        """\
  - id: decide
    kind: human
  - id: gate-seal
    kind: gate
    run: "true\"""")
    rc, out = lint(tmp_path, clean)
    assert rc == 0 and "0 WARN" in out, out


def test_unused_gate_result_fails(tmp_path):
    bad = VALID.replace("  - {from: check, to: __end__, when: gate.exit == 0}\n"
                        "  - {from: check, to: work, when: gate.exit != 0}\n",
                        "  - {from: check, to: __end__}\n")
    rc, out = lint(tmp_path, bad)
    assert rc == 1 and "result unused" in out


def test_schema_rejects_unknown_keys(tmp_path):
    # the retired `pass` field and any typo'd key must fail the schema
    bad = VALID.replace('    run: "true"', '    run: "true"\n    pass: exit == 0')
    rc, out = lint(tmp_path, bad)
    assert rc == 1 and "[schema]" in out


def test_compile_refused_on_fail(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(VALID.replace("when: gate.exit == 0", "when: prose here"))
    subprocess.run([sys.executable, str(LINT), str(f), "--compile"],
                   capture_output=True, text=True, timeout=60)
    assert not (tmp_path / "bad.json").exists()


# ── --check-gates: a project-owned flow must name gates that exist

GATED = """\
flow: site
version: 1
state: {gate: {}}
nodes:
  - id: build
    kind: agent
    craft: [.flow/craft/build.md]
    out: [code]
  - id: gate-x
    kind: gate
    run: ".flow/bin/present.py {feature_dir}"
  - id: gate-y
    kind: gate
    run: "{gate_check_cmd} {feature_dir}"
edges:
  - {from: __start__, to: build}
  - {from: build, to: gate-x}
  - {from: gate-x, to: gate-y, when: gate.exit == 0}
  - {from: gate-x, to: build, when: gate.exit != 0}
  - {from: gate-y, to: __end__, when: gate.exit == 0}
  - {from: gate-y, to: build, when: gate.exit != 0}
"""


def _gated_project(tmp_path, with_gate):
    proj = tmp_path / "proj"
    (proj / ".flow" / "bin").mkdir(parents=True)
    (proj / "site.yaml").write_text(GATED)
    if with_gate:
        (proj / ".flow" / "bin" / "present.py").write_text("import sys\n")
    return proj


def _lint(proj, *extra):
    p = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "flow-lint.py"),
         str(proj / "site.yaml"), "--check-gates", "--project", str(proj),
         *extra],
        capture_output=True, text=True)
    return p.returncode, p.stdout


def test_check_gates_passes_when_the_gate_exists(tmp_path):
    rc, out = _lint(_gated_project(tmp_path, True))
    assert rc == 0, out


def test_check_gates_fails_on_a_missing_gate_program(tmp_path):
    rc, out = _lint(_gated_project(tmp_path, False))
    assert rc == 1, out
    assert "gate-x" in out and "does not exist" in out, out


def test_check_gates_warns_not_fails_on_a_bound_gate(tmp_path):
    # {gate_check_cmd} is supplied at arm time; the lint cannot know it
    # and must not invent a failure
    rc, out = _lint(_gated_project(tmp_path, True))
    assert rc == 0, out
    assert "WARN" in out and "gate-y" in out, out


def test_check_gates_is_opt_in(tmp_path):
    # without the flag, a flow naming absent gates still lints clean —
    # the built-in roads name gates that live elsewhere by design
    proj = _gated_project(tmp_path, False)
    p = subprocess.run(
        [sys.executable, str(ROOT / "bin" / "flow-lint.py"),
         str(proj / "site.yaml")], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout
