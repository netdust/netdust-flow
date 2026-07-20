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
