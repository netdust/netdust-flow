"""Marker identity: WHOSE run is this, and WHOSE marker is this file?

Run 0004 lost an armed run to the two questions this file answers (the
post-mortem's F01 and F02, the same root problem seen from two sides:
the marker was a shared global with no owner).

F01 — the marker is project-scoped, so loop-gate.py fired on EVERY
session that stopped in the repo. A review session that produced no
task progress registered as a dry iteration of the builder's run, and
two of those disarmed it. The marker now records the session that
claimed it and the hook no-ops for every other session, exactly as it
already no-ops when there is no marker at all.

F02 — netdust-flow and netdust-agent both claimed
`tasks/.harness-loop.json` for completely different schemas, so arming
one silently armed the other. The marker is namespaced now, and carries
a schema discriminator so any reader can refuse a file it does not own.

Conventions follow test_flow_gate.py: subprocess the hook, control the
world through files, assert on stdout JSON + marker state.
"""
import json
import subprocess
import sys
from pathlib import Path

from test_flow_arm import arm, marker as arm_marker
from test_flow_arm import project as arm_project
from test_flow_gate import setup, marker_of, MARKER_REL

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "loop-gate.py"
ARM = ROOT / "bin" / "flow-arm.py"
DELIVER = ROOT / "flows" / "deliver.json"
LEGACY_MARKER_REL = Path("tasks") / ".harness-loop.json"


def run_gate_as(cwd, home, session=None):
    """The Stop hook, driven as a named session. `session=None` is a
    host that sends no session_id — it must still drive (fail-open)."""
    payload = {"cwd": str(cwd)}
    if session is not None:
        payload["session_id"] = session
    p = subprocess.run(
        [sys.executable, str(GATE)],
        input=json.dumps(payload),
        capture_output=True, text=True, timeout=120,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    return p.returncode, p.stdout


# ── F01: the run belongs to the session that claimed it ──────────────

def test_first_stop_claims_the_run_for_its_session(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "spec")
    rc, out = run_gate_as(cwd, home, "sess-builder")

    assert rc == 0
    assert json.loads(out)["decision"] == "block"
    assert marker_of(cwd)["session"] == "sess-builder"


def test_a_foreign_session_does_not_drive_the_walker(tmp_path):
    """The whole of F01: an observer session stopping in the same repo
    must be as inert as a session with no marker at all."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    run_gate_as(cwd, home, "sess-builder")
    claimed = marker_of(cwd)

    rc, out = run_gate_as(cwd, home, "sess-observer")

    assert rc == 0
    assert out.strip() == "", "a foreign session must not block its own stop"
    assert marker_of(cwd) == claimed, "and must not touch the run's state"


def test_a_foreign_session_cannot_spend_the_dry_counter(tmp_path):
    """The exact way run 1340 died: the observer's stops produced no
    task progress, so they counted as dry iterations of someone else's
    run and disarmed it. max_dry=1 makes one foreign stop fatal if the
    counter is still reachable from outside."""
    home, cwd = setup(tmp_path, DELIVER, "spec", extra={"max_dry": 1})
    # a red spec gate keeps the walk on `spec`, so the observer's stops
    # are CONTINUEs that move no counter — the shape that killed 1340.
    # (Without this the observer lands on a human node and yields before
    # the dry logic is even reached, and the test proves nothing.)
    (cwd / "specs" / "demo" / ".stub-gate-check").write_text("1")
    run_gate_as(cwd, home, "sess-builder")

    for _ in range(3):
        run_gate_as(cwd, home, "sess-observer")

    marker = marker_of(cwd)
    assert marker is not None, "a foreign session must never disarm the run"
    assert marker["dry"] == 0
    assert marker["iteration"] == 1


def test_the_claiming_session_keeps_driving(tmp_path):
    """The owner is not slowed down by the sessions it now excludes."""
    home, cwd = setup(tmp_path, DELIVER, "spec", extra={"max_dry": 10})
    # a red spec gate routes `spec` back to itself, so every stop is a
    # CONTINUE and two of them are comparable
    (cwd / "specs" / "demo" / ".stub-gate-check").write_text("1")

    assert json.loads(run_gate_as(cwd, home, "sess-builder")[1])["decision"] \
        == "block"
    run_gate_as(cwd, home, "sess-observer")
    rc, out = run_gate_as(cwd, home, "sess-builder")

    assert json.loads(out)["decision"] == "block"
    assert marker_of(cwd)["iteration"] == 2, "the observer spent no budget"


def test_a_host_that_sends_no_session_id_still_drives(tmp_path):
    """Fail-open: session scoping must never trap a run on a host whose
    Stop payload carries no session_id."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    rc, out = run_gate_as(cwd, home, session=None)

    assert json.loads(out)["decision"] == "block"
    assert "session" not in marker_of(cwd)


def test_an_unclaimed_marker_is_claimable_by_whoever_stops_first(tmp_path):
    """Arming does not know its own session id, so the claim is minted
    at the first stop — the same place run_id is minted. A run armed by
    a session that then died is reclaimed with `flow-arm --reclaim`."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    marker = marker_of(cwd)
    assert "session" not in marker

    run_gate_as(cwd, home, "sess-late")
    assert marker_of(cwd)["session"] == "sess-late"


def test_reclaim_hands_a_stranded_run_to_the_current_session(tmp_path):
    """Session 2 of run 0004 wedged itself dead. Without a takeover the
    claim would strand the run on a session that will never stop again;
    --reclaim clears the claim while preserving run identity."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    run_gate_as(cwd, home, "sess-dead")
    before = marker_of(cwd)

    p = subprocess.run(
        [sys.executable, str(ARM), "--reclaim", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 0, p.stdout + p.stderr
    after = marker_of(cwd)
    assert "session" not in after, "cleared, so the next stop claims it"
    assert after["run_id"] == before["run_id"], "run identity is preserved"
    assert after["iteration"] == before["iteration"]

    run_gate_as(cwd, home, "sess-successor")
    assert marker_of(cwd)["session"] == "sess-successor"


def test_reset_counters_clears_dryness_without_disarming(tmp_path):
    """F09's legitimate case: a run whose counters were spent by a
    defect should not have to be re-armed (which discards run identity
    and splits the journal) to keep going."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    run_gate_as(cwd, home, "sess-builder")
    before = marker_of(cwd)

    p = subprocess.run(
        [sys.executable, str(ARM), "--reset-counters", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 0, p.stdout + p.stderr
    after = marker_of(cwd)
    assert after["iteration"] == 0 and after["dry"] == 0
    assert after["run_id"] == before["run_id"]
    assert after["node"] == before["node"]


# ── F02: the marker is netdust-flow's, and says so ───────────────────

def test_the_marker_is_namespaced(tmp_path):
    assert MARKER_REL == Path("tasks") / ".netdust-flow.json", (
        "netdust-agent owns tasks/.harness-loop.json for a different "
        "schema; sharing the filename armed both harnesses at once")


def test_arming_writes_the_schema_discriminator(tmp_path):
    """Written by flow-arm, so a reader can refuse a marker it does not
    own before interpreting a single other key."""
    proj = arm_project(tmp_path)
    rc, out = arm(proj)

    assert rc == 0, out
    assert arm_marker(proj)["schema"] == "netdust-flow/1"


def test_every_copy_of_the_marker_name_agrees(tmp_path):
    """The hook path repeats the literal instead of importing it (an
    import that fails at module scope would crash before the fail-open
    wrapper). That trade is only safe while the copies agree, so the
    agreement is machine-checked rather than trusted."""
    import importlib.util

    def constants(path):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)   # both files only act under __main__
        return mod

    flowspec = constants(ROOT / "bin" / "flowspec.py")
    hook = constants(ROOT / "hooks" / "loop-gate.py")

    assert hook.MARKER_REL == flowspec.MARKER_REL
    assert hook.MARKER_SCHEMA == flowspec.MARKER_SCHEMA

    # The guard names the marker as a path regex, not a constant, so it
    # is checked by what it matches rather than by what it equals.
    guard = constants(ROOT / "hooks" / "pretooluse-guard.py")
    assert guard.MARKER.search(str(flowspec.MARKER_REL))
    assert not guard.MARKER.search("tasks/.harness-loop.json"), (
        "the guard must not police netdust-agent's marker")


def test_the_hook_ignores_the_netdust_agent_marker(tmp_path):
    """A netdust-agent marker in the same repo must be invisible here —
    the reciprocal of the guard netdust-agent needs against ours."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    (cwd / MARKER_REL).unlink()
    (cwd / LEGACY_MARKER_REL).write_text(json.dumps(
        {"spec_dir": "specs/demo", "iteration": 3, "max_iterations": 40}))

    rc, out = run_gate_as(cwd, home, "sess-builder")

    assert rc == 0 and out.strip() == ""
    assert json.loads((cwd / LEGACY_MARKER_REL).read_text())["iteration"] == 3


def test_a_foreign_schema_in_our_own_filename_is_refused(tmp_path):
    """The discriminator earns its keep only if a reader checks it."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    (cwd / MARKER_REL).write_text(json.dumps(
        {"schema": "some-other-harness/9", "flow": "x", "node": "y"}))

    rc, out = run_gate_as(cwd, home, "sess-builder")

    assert rc == 0 and out.strip() == ""


def test_the_stop_instruction_names_the_namespaced_marker(tmp_path):
    """The escape hatch the block reason prints must delete OUR marker."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    rc, out = run_gate_as(cwd, home, "sess-builder")

    reason = json.loads(out)["reason"]
    assert ".netdust-flow.json" in reason
    assert ".harness-loop.json" not in reason


# ── F02 follow-through: the rename must not strand live runs ─────────

def test_migrate_moves_a_legacy_marker_and_keeps_run_identity(tmp_path):
    """The rename orphans every run that was armed under the old name:
    the hook reads the new path, finds nothing, and the run simply stops
    being driven. Re-arming is not the answer — it mints a NEW run id,
    and attests are run-scoped, so every task already proven would read
    as open again."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    legacy = json.loads((cwd / MARKER_REL).read_text())
    legacy.pop("schema", None)
    (cwd / MARKER_REL).unlink()
    (cwd / LEGACY_MARKER_REL).write_text(json.dumps(legacy))

    p = subprocess.run(
        [sys.executable, str(ARM), "--migrate", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 0, p.stdout + p.stderr
    assert not (cwd / LEGACY_MARKER_REL).exists()
    moved = marker_of(cwd)
    assert moved["schema"] == "netdust-flow/1"
    assert moved["node"] == legacy["node"]
    assert moved["feature_dir"] == legacy["feature_dir"]
    assert moved["iteration"] == legacy["iteration"]


def test_migrate_preserves_the_run_id(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "spec")
    legacy = json.loads((cwd / MARKER_REL).read_text())
    legacy["run_id"] = "r20260818-174545-48f9"
    legacy.pop("schema", None)
    (cwd / MARKER_REL).unlink()
    (cwd / LEGACY_MARKER_REL).write_text(json.dumps(legacy))

    subprocess.run([sys.executable, str(ARM), "--migrate",
                    "--project", str(cwd)], capture_output=True, text=True)

    assert marker_of(cwd)["run_id"] == "r20260818-174545-48f9", (
        "attests are scoped to the run id; losing it voids every one")


def test_migrate_refuses_a_marker_that_is_not_ours(tmp_path):
    """netdust-agent's marker lives at the legacy path too, and it is
    not ours to move."""
    home, cwd = setup(tmp_path, DELIVER, "spec")
    (cwd / MARKER_REL).unlink()
    (cwd / LEGACY_MARKER_REL).write_text(json.dumps(
        {"spec_dir": "specs/demo", "iteration": 3}))

    p = subprocess.run(
        [sys.executable, str(ARM), "--migrate", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 1
    assert "REFUSED" in p.stdout
    assert (cwd / LEGACY_MARKER_REL).exists(), "left untouched"
    assert not (cwd / MARKER_REL).exists()


def test_migrate_refuses_to_overwrite_a_live_marker(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "spec")
    (cwd / LEGACY_MARKER_REL).write_text(json.dumps(
        {"flow": "x", "node": "y", "feature_dir": "specs/demo"}))

    p = subprocess.run(
        [sys.executable, str(ARM), "--migrate", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 1
    assert marker_of(cwd)["node"] == "spec", "the live run is untouched"


def test_migrate_with_nothing_to_migrate_says_so(tmp_path):
    home, cwd = setup(tmp_path, DELIVER, "spec")
    (cwd / MARKER_REL).unlink()

    p = subprocess.run(
        [sys.executable, str(ARM), "--migrate", "--project", str(cwd)],
        capture_output=True, text=True)

    assert p.returncode == 1 and "REFUSED" in p.stdout
