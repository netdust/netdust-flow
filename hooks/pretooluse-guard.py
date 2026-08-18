#!/usr/bin/env python3
"""pretooluse-guard.py — netdust-flow PreToolUse hook: keep the trust
boundary the rest of the system only *names*.

The invariants say no assertion is a signal; the signals are git
notes (attest/seal), and — supporting them — the compiled flow twins
and the run journal. Those files are tamper-RESISTANT, not
tamper-proof: an agent with bash can forge any of them a dozen ways,
and this guard does not pretend otherwise. What it does is deny the
DIRECT, obvious path, so that honesty is the path of least
resistance and a forge has to be deliberate rather than incidental.

Denied (agent tool calls only — the legitimate writers are Python
subprocesses inside attest.py/seal.py/flow-lint/loop-gate and never
pass through this hook):

  1. A Bash command that MUTATES git notes (`git … notes …
     add|append|edit|copy|remove|prune`). Reads (list/show/get-ref)
     pass — ledger.py and seal.py read them. There is no legitimate
     reason for an agent to write a note by hand; attest.py and
     seal.py do it inside their own process.
  2. A Write/Edit/NotebookEdit whose target is a compiled flow twin
     (`flows/*.json` — written only by `flow-lint --compile`) or a
     run journal (`*.flow-journal.jsonl` — written only by the Stop
     hook). Hand-editing either is exactly the forge the boundary
     names; the .yaml source and everything else stay editable.

Deliberately NOT denied: the marker (`tasks/.netdust-flow.json`).
Arming a flow legitimately writes it, and telling human-arm from
agent-tamper needs more than a path match — deferred, named here so
the omission is a decision, not a gap.

Contract: reads a PreToolUse event as JSON on stdin; on a match,
prints a `deny` decision and exits 0; otherwise stays silent (no
opinion → normal permission flow). FAIL-OPEN: any internal error
allows the call — a guard that bricks the agent on its own bug would
be worse than the resistance it provides, and the security claim was
never 'proof' to begin with. Wire it in settings.json:

    {"hooks": {"PreToolUse": [{"matcher": "Bash|Write|Edit|NotebookEdit",
      "hooks": [{"type": "command",
        "command": "python3 ~/.claude/netdust-flow/hooks/pretooluse-guard.py"}]}]}}
"""
from __future__ import annotations

import json
import re
import sys

# `git … notes … <write-subcommand>` — flags between `notes` and the
# subcommand are tolerated (--ref=…); reads (list/show/get-ref/merge
# --abort) are not matched, so evidence stays readable.
NOTES_WRITE = re.compile(
    r"\bgit\b[^;&|]*?\bnotes\b(?:\s+--?\S+)*\s+"
    r"(add|append|edit|copy|remove|prune)\b")

# path targets that only a verifier/compiler/hook may write
TWIN = re.compile(r"(^|/)flows/[^/]+\.json$")
JOURNAL = re.compile(r"\.flow-journal\.jsonl$")


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))


def evaluate(tool: str, tool_input: dict) -> str | None:
    """Return a deny reason, or None to stay silent."""
    if tool == "Bash":
        cmd = str(tool_input.get("command", ""))
        if NOTES_WRITE.search(cmd):
            return ("netdust-flow trust boundary: agents do not write "
                    "git notes directly — that is the evidence store. "
                    "Record checks through bin/attest.py and human "
                    "decisions through bin/seal.py; those tools write the "
                    "note themselves.")
        return None
    if tool in ("Write", "Edit", "NotebookEdit"):
        path = str(tool_input.get("file_path")
                   or tool_input.get("notebook_path") or "")
        norm = path.replace("\\", "/")
        if TWIN.search(norm):
            return ("netdust-flow trust boundary: a compiled flow twin "
                    "(flows/*.json) is written only by a green "
                    "`flow-lint --compile`. Edit the .yaml source and "
                    "recompile; never hand-edit the twin.")
        if JOURNAL.search(norm):
            return ("netdust-flow trust boundary: the run journal "
                    "(.flow-journal.jsonl) is written only by the Stop "
                    "hook. It is a record, not a workspace.")
    return None


def main() -> int:
    try:
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        tool = event.get("tool_name", "")
        tool_input = event.get("tool_input") or {}
        reason = evaluate(tool, tool_input)
        if reason:
            deny(reason)
    except Exception:
        pass  # fail-open: a broken guard must never trap the agent
    return 0


if __name__ == "__main__":
    sys.exit(main())
