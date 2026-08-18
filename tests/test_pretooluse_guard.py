"""Tests for hooks/pretooluse-guard.py — the trust-boundary guard.

Subprocess the real hook with a PreToolUse JSON payload on stdin;
assert on the deny decision (or silence). The guard must always exit
0 (fail-open); a deny is expressed in stdout JSON, not the exit code.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "hooks" / "pretooluse-guard.py"


def run(tool, tool_input):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input}
    p = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30)
    assert p.returncode == 0, "guard must always exit 0 (fail-open)"
    if not p.stdout.strip():
        return None
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


def denied(tool, tool_input):
    return run(tool, tool_input) == "deny"


def reason_for(tool, tool_input):
    """The deny reason, which is the part an agent actually reads."""
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool,
               "tool_input": tool_input}
    p = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30)
    if not p.stdout.strip():
        return ""
    return json.loads(p.stdout)["hookSpecificOutput"][
        "permissionDecisionReason"]


# ── git notes: writes denied, reads allowed ──────────────────────────

def test_git_notes_append_denied():
    assert denied("Bash", {"command":
        "git notes --ref=refs/notes/attest append -m '{}' HEAD"})


def test_git_notes_add_denied():
    assert denied("Bash", {"command": "git notes add -m x HEAD"})


def test_git_notes_remove_denied():
    assert denied("Bash", {"command": "git notes remove HEAD"})


def test_git_dash_c_notes_append_denied():
    # the -C form must not slip past
    assert denied("Bash", {"command": "git -C /repo notes append -m x HEAD"})


def test_git_notes_list_allowed():
    assert not denied("Bash", {"command": "git notes --ref=attest list"})


def test_git_notes_show_allowed():
    assert not denied("Bash", {"command": "git notes show HEAD"})


def test_ordinary_git_allowed():
    assert not denied("Bash", {"command": "git commit -am wip && git push"})


def test_running_attest_tool_allowed():
    # the legitimate path: an agent runs attest.py, which writes the
    # note in its OWN process — the Bash command names no `git notes`
    assert not denied("Bash", {"command":
        "python3 bin/attest.py specs/x T01 -- pytest"})


# ── protected paths: twins and journal ───────────────────────────────

def test_write_twin_denied():
    assert denied("Write", {"file_path": "/proj/flows/deliver.json",
                            "content": "{}"})


def test_edit_twin_denied():
    assert denied("Edit", {"file_path": "flows/patch.json"})


def test_write_journal_denied():
    assert denied("Write", {"file_path": "specs/x/.flow-journal.jsonl",
                            "content": "{}"})


def test_edit_yaml_source_allowed():
    # the .yaml is authoring surface — never guarded
    assert not denied("Edit", {"file_path": "flows/deliver.yaml"})


def test_write_ordinary_file_allowed():
    assert not denied("Write", {"file_path": "records/x/dossier.md",
                                "content": "hi"})


def test_marker_hand_write_is_denied():
    """Reversed at run 0004 (F09). The marker IS the persisted machine
    state — node, budget, counters, run identity — and it was the one
    thing the guard left open, on the reasoning that arming legitimately
    writes it. But arming writes it from inside flow-arm's own process,
    which never passes through this hook; the only writer this hook can
    see is an agent hand-writing JSON. During run 0004 a session's own
    test mutated the live marker's counters and it repaired them by
    hand-writing the file. Correct outcome, minimal edit — and exactly
    the assertion flow-arm.py's docstring names as the one the system
    never checked."""
    assert denied("Write", {"file_path": "tasks/.netdust-flow.json",
                            "content": "{}"})
    assert denied("Edit", {"file_path": "tasks/.netdust-flow.json"})


def test_the_marker_denial_names_the_legitimate_tools():
    reason = reason_for("Write", {"file_path": "tasks/.netdust-flow.json",
                                  "content": "{}"})
    assert "--reset-counters" in reason or "--reclaim" in reason


def test_disarming_by_deleting_the_marker_is_allowed():
    """`/flow off` deletes the marker, and the block reason printed at
    every stop tells the operator to. Denying that would trap runs."""
    assert not denied("Bash",
                      {"command": "rm tasks/.netdust-flow.json"})


# ── robustness ───────────────────────────────────────────────────────

def test_empty_stdin_is_silent():
    p = subprocess.run([sys.executable, str(GUARD)], input="",
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0 and p.stdout.strip() == ""


def test_unknown_tool_silent():
    assert run("WebFetch", {"url": "http://x"}) is None


def test_deny_reason_is_present_and_actionable():
    payload = {"tool_name": "Bash",
               "tool_input": {"command": "git notes append -m x HEAD"}}
    p = subprocess.run([sys.executable, str(GUARD)],
                       input=json.dumps(payload), capture_output=True,
                       text=True, timeout=30)
    reason = json.loads(p.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "attest.py" in reason  # tells the agent the right path
