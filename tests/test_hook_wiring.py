"""Arming refuses wiring that cannot survive the run (F05).

A pack scaffolded `"command": "python3 .flow/hooks/pretooluse-guard.py"`
— a RELATIVE path. One `cd` into the runtime (which a session did while
reading flow's own source) moved the shell cwd, and the hook could no
longer find itself. Because the PreToolUse matcher is
`Bash|Write|Edit|NotebookEdit`, every tool that could have repaired the
config was blocked BY the broken config. Run 0004's session 2 was
unrecoverable and had to be abandoned.

The shims themselves were fine — they fall back to the absolute
`~/.claude/netdust-flow` symlink. They simply could not be FOUND.

flow-arm already refuses a flow that will not lint, a gate program that
does not exist and a placeholder with no value, on the same principle:
a named refusal now beats a dead run twenty minutes in. Hook wiring
that dies on the first `cd` belongs in that list — and unlike the
others, it takes the session's ability to repair itself down with it.
"""
import json
from pathlib import Path

from test_flow_arm import project, arm, MARKER_REL

RELATIVE = {"hooks": {
    "Stop": [{"hooks": [
        {"type": "command", "command": "python3 .flow/hooks/loop-gate.py"}]}],
    "PreToolUse": [{"matcher": "Bash|Write|Edit|NotebookEdit", "hooks": [
        {"type": "command",
         "command": "python3 .flow/hooks/pretooluse-guard.py"}]}]}}

ANCHORED = {"hooks": {
    "Stop": [{"hooks": [
        {"type": "command",
         "command": "python3 $CLAUDE_PROJECT_DIR/.flow/hooks/loop-gate.py"}]}]}}

ABSOLUTE = {"hooks": {
    "Stop": [{"hooks": [
        {"type": "command",
         "command": "python3 /home/x/.claude/netdust-flow/hooks/loop-gate.py"}
    ]}]}}

UNRELATED = {"hooks": {
    "Stop": [{"hooks": [
        {"type": "command", "command": "python3 $CLAUDE_PROJECT_DIR/"
                                       ".flow/hooks/loop-gate.py"}]}],
    "PostToolUse": [{"hooks": [
        {"type": "command", "command": "sh bin/format.sh"}]}]}}


def wire(proj, settings, name="settings.json"):
    (proj / ".claude").mkdir(exist_ok=True)
    (proj / ".claude" / name).write_text(json.dumps(settings, indent=2))
    return proj


def test_a_relative_hook_path_refuses_the_arm(tmp_path):
    proj = wire(project(tmp_path), RELATIVE)
    rc, out = arm(proj)

    assert rc == 1
    assert "REFUSED  [hooks]" in out
    assert "loop-gate.py" in out
    assert "$CLAUDE_PROJECT_DIR" in out, "the refusal must name the fix"
    assert not (proj / MARKER_REL).exists(), "a refusal never arms"


def test_the_refusal_says_why_it_is_not_survivable(tmp_path):
    """A refusal nobody understands gets worked around."""
    proj = wire(project(tmp_path), RELATIVE)
    rc, out = arm(proj)

    assert "cd" in out.lower()


def test_an_anchored_hook_path_arms(tmp_path):
    proj = wire(project(tmp_path), ANCHORED)
    rc, out = arm(proj)

    assert rc == 0, out


def test_an_absolute_hook_path_arms(tmp_path):
    proj = wire(project(tmp_path), ABSOLUTE)
    rc, out = arm(proj)

    assert rc == 0, out


def test_hooks_that_are_not_ours_are_not_policed(tmp_path):
    """`sh bin/format.sh` is relative and none of our business — the
    check stays in its lane or it becomes a nuisance nobody keeps on."""
    proj = wire(project(tmp_path), UNRELATED)
    rc, out = arm(proj)

    assert rc == 0, out
    assert "format.sh" not in out


def test_settings_local_json_is_checked_too(tmp_path):
    proj = wire(project(tmp_path), RELATIVE, name="settings.local.json")
    rc, out = arm(proj)

    assert rc == 1 and "REFUSED  [hooks]" in out


def test_no_stop_hook_anywhere_is_a_warning_not_a_refusal(tmp_path):
    """A project may wire the hook at user level, where arming cannot
    see it. Refusing would be wrong; saying nothing would arm a run that
    nothing will ever drive."""
    proj = project(tmp_path)
    rc, out = arm(proj)

    assert rc == 0, out
    assert "WARN    [hooks]" in out
    assert "Stop hook" in out


def test_unparseable_settings_do_not_block_arming(tmp_path):
    """Fail open on a file we only read to be helpful about."""
    proj = project(tmp_path)
    (proj / ".claude").mkdir(exist_ok=True)
    (proj / ".claude" / "settings.json").write_text("{not json")

    rc, out = arm(proj)

    assert rc == 0, out
