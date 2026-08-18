#!/usr/bin/env python3
"""Run the first adversarial protocol eval cohort.

This is intentionally a thin wrapper around the executable trust-boundary
suite. The tests are the oracle; this command makes the cohort explicit and
produces a small machine-readable summary suitable for CI and later baseline
comparisons.

Exit 0 only when every eval passes.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Protocol attacks. Keep the list explicit: adding an eval should be visible
# in review rather than silently broadening a glob.
CASES = [
    ("E01", "fabricated attestation", "tests/test_trust_boundary.py::test_garbage_attest_note_is_ignored_not_fatal"),
    ("E02", "malformed attestation fields", "tests/test_trust_boundary.py::test_forged_attest_missing_fields_does_not_count"),
    ("E03", "fabricated human seal", "tests/test_trust_boundary.py::test_garbage_seal_note_is_not_a_decision"),
    ("E04", "failed verification creates no evidence", "tests/test_trust_boundary.py::test_attest_records_nothing_when_the_check_fails"),
    ("E05", "gate crash cannot finish", "tests/test_trust_boundary.py::test_gate_that_raises_is_red_and_routes_back"),
    ("E06", "missing gate blocks", "tests/test_trust_boundary.py::test_gate_program_missing_blocks_never_traverses"),
    ("E07", "walker crash cannot advance state", "tests/test_trust_boundary.py::test_crashing_walker_never_advances_the_node"),
    ("E08", "missing review evidence", "tests/test_trust_boundary.py::test_review_absent_report_is_not_evidence"),
    ("E09", "stale review cannot advance", "tests/test_trust_boundary.py::test_review_of_yesterdays_tree_proves_nothing_today"),
    ("E10", "builder cannot self-review", "tests/test_trust_boundary.py::test_review_signed_by_the_excluded_builder_is_refused"),
    ("E11", "fantasy review tree", "tests/test_trust_boundary.py::test_review_claiming_a_fantasy_tree_is_rejected"),
    ("E12", "green control can finish", "tests/test_trust_boundary.py::test_green_gate_still_finishes"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    results = []
    for case_id, name, target in CASES:
        p = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q"],
            cwd=ROOT, capture_output=True, text=True,
        )
        results.append({
            "id": case_id,
            "name": name,
            "passed": p.returncode == 0,
            "returncode": p.returncode,
            "output": (p.stdout + p.stderr).strip(),
        })

    attacks = [r for r in results if r["id"] != "E12"]
    controls = [r for r in results if r["id"] == "E12"]
    blocked = sum(r["passed"] for r in attacks)
    escaped = len(attacks) - blocked
    control_pass = sum(r["passed"] for r in controls)
    summary = {
        "cohort": "protocol-v0",
        "cases": len(results),
        "attacks": len(attacks),
        "blocked_attacks": blocked,
        "escaped_attacks": escaped,
        "containment_rate": blocked / len(attacks) if attacks else 1.0,
        "controls": len(controls),
        "control_pass": control_pass,
        "false_positive_rate": (len(controls) - control_pass) / len(controls) if controls else 0.0,
        "passed": all(r["passed"] for r in results),
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("NETDUST PROTOCOL EVAL v0")
        print(f"attacks: {blocked}/{len(attacks)} blocked")
        print(f"containment: {summary['containment_rate']:.0%}")
        print(f"controls: {control_pass}/{len(controls)} passed")
        print(f"false-positive rate: {summary['false_positive_rate']:.0%}")
        for r in results:
            print(f"  {'PASS' if r['passed'] else 'FAIL'} {r['id']} {r['name']}")

    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
