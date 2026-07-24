"""skill-eval.py: deterministic capability gate. Cases score outputs;
all-pass is exit 0, and only passed case-ids are reported (so the
pruner retires only confirmed lessons)."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "bin" / "skill-eval.py"


def sh(*args, cwd):
    return subprocess.run(list(args), capture_output=True, text=True, cwd=cwd)


def skill(tmp_path, cases):
    d = tmp_path / "skills" / "s"
    (d / "eval").mkdir(parents=True)
    (d / "eval" / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n")
    return d


def run(tmp_path, skill_dir, outputs):
    (tmp_path / "out.jsonl").write_text(
        "\n".join(json.dumps(o) for o in outputs) + "\n")
    return sh(sys.executable, str(EVAL), str(skill_dir),
              "--outputs", str(tmp_path / "out.jsonl"), cwd=tmp_path)


def test_all_pass_is_exit_0(tmp_path):
    d = skill(tmp_path, [
        {"id": "C1", "lesson": "L1", "assert": [{"kind": "min_links", "n": 3}]},
        {"id": "C2", "lesson": "L2", "assert": [{"kind": "has_section", "name": "Sources"}]},
    ])
    p = run(tmp_path, d, [
        {"id": "C1", "output": "a http://x/a http://x/b http://x/c"},
        {"id": "C2", "output": "## Sources\n- http://x/a"},
    ])
    assert p.returncode == 0 and "PASS — 2/2" in p.stdout
    assert "passed cases: C1 C2" in p.stdout


def test_one_fails_names_the_case_and_lesson(tmp_path):
    d = skill(tmp_path, [
        {"id": "C1", "lesson": "L1", "assert": [{"kind": "min_links", "n": 3}]},
        {"id": "C2", "lesson": "L2", "assert": [{"kind": "not_contains", "pattern": "guarantee"}]},
    ])
    p = run(tmp_path, d, [
        {"id": "C1", "output": "only http://x/a one link"},   # fails min_links
        {"id": "C2", "output": "no forbidden word here"},
    ])
    assert p.returncode == 1 and "FAIL — 1/2" in p.stdout
    assert "L1" in p.stdout                       # the failing lesson is named
    assert "passed cases: C2" in p.stdout         # only C2 is retirable


def test_missing_output_fails_closed(tmp_path):
    d = skill(tmp_path, [{"id": "C1", "lesson": "L1", "assert": [{"kind": "min_chars", "n": 5}]}])
    p = run(tmp_path, d, [])                       # produced nothing
    assert p.returncode == 1 and "no output" in p.stdout


def test_no_cases_cannot_pass(tmp_path):
    d = tmp_path / "skills" / "empty"
    (d / "eval").mkdir(parents=True)
    (d / "eval" / "cases.jsonl").write_text("")
    p = run(tmp_path, d, [])
    assert p.returncode == 2 and "0 cases" in p.stdout   # unmeasured ≠ passing
