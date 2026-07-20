#!/usr/bin/env python3
"""
loop-gate.py — netdust-agent harness

Stop hook: the loop driver. When a feature loop is ARMED (marker file
tasks/.harness-loop.json exists, written by /loop), this hook runs
spec-kit/loop-check.py at every session stop and BLOCKS the stop while
Stage 2 is unfinished — the exact mechanism subagent-stop.py uses on
subagents, one level up. No marker → no-op (zero cost for every normal
session).

Token cost of the loop itself: ~zero. The gate is deterministic Python;
the only context it ever adds is the 2-line block reason.

Decision table (marker present, stop_hook_active false):
  loop-check exit 0 (FINISHED) → disarm (delete marker), allow stop.
  loop-check exit 2 (BLOCKED)  → allow stop, KEEP marker — the agent has
                                 already surfaced the human question in its
                                 transcript; when the human answers and work
                                 resumes, the loop re-engages at next stop.
  loop-check exit 1 (CONTINUE) → block with the next unit, UNLESS a
                                 guardrail disarms first:
    • iteration >= max_iterations           → disarm, allow (budget spent)
    • done-count unchanged 2 stops in a row → disarm, allow (dry loop)

Guardrails that always win: stop_hook_active bypass (one block per stop
cycle), marker deletion by the human, and fail-open — any internal error
allows the stop. Logs to ~/.claude/logs/memory-hook.log.

Marker schema (tasks/.harness-loop.json — runtime state, gitignored by /loop):
  {"feature_dir": "specs/<feature>", "iteration": 0, "max_iterations": 25,
   "last_done": 0, "dry": 0}

Flow mode (netdust-flow v0.1) — armed by /flow instead of /loop. The same
marker carries four extra fields and the gate consults flow-check.py (the
walker) instead of loop-check.py:
  {"flow": "<abs path to flows/*.json twin>", "node": "__start__",
   "flow_check": "<abs path to netdust-flow/bin/flow-check.py>",
   "binds": {"test_suite_cmd": "..."},          # optional
   "max_dry": 25, "gate_timeout": 600}          # optional overrides
The walker's `next:` line is persisted back into marker["node"] whenever
the marker survives (CONTINUE and BLOCKED). Markers without "flow" take
the legacy loop-check path unchanged — /loop keeps working as before.

Trust boundary (named, v0.2): the marker file IS the persisted machine
state, and it is writable by anything with filesystem access — an agent
could rewrite "node", swap "flow", or neuter "binds" exactly as easily
as forging a git note. The same pretooluse guard that protects
`git notes` (see attest.py) should deny agent writes to
tasks/.harness-loop.json and to the compiled flows/*.json twins. This
hook deliberately does not re-verify the marker's provenance: the gate
is deterministic, the guard is the enforcement layer.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

LOG_PATH = Path.home() / ".claude" / "logs" / "memory-hook.log"
LOOP_CHECK = Path(__file__).resolve().parent.parent / "spec-kit" / "loop-check.py"
RUN_TRACE = Path(__file__).resolve().parent.parent / "spec-kit" / "run-trace.py"
MARKER_REL = Path("tasks") / ".harness-loop.json"
DEFAULT_MAX_ITERATIONS = 25
MAX_DRY = 2


def log(msg: str) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a") as f:
            f.write(f"[{ts}] loop-gate: {msg}\n")
    except Exception:
        pass


def trace(feature_dir: Path, event: str, cwd: Path, **kv) -> None:
    """Fail-open trace emission: append one run-trace event. Any failure —
    nonzero exit, subprocess exception, timeout, whatever — is swallowed
    here. Tracing must NEVER affect the gate's decision, control flow, or
    printed stdout."""
    try:
        args = [sys.executable, str(RUN_TRACE), "append", str(feature_dir), event]
        args += [f"{k}={v}" for k, v in kv.items()]
        subprocess.run(args, capture_output=True, timeout=10, cwd=str(cwd))
    except Exception:
        pass  # fail-open: tracing must never affect the gate's decision


def read_progress(stdout: str) -> int | None:
    for line in stdout.splitlines():
        if line.startswith("progress: done="):
            try:
                return int(line.split("done=")[1].split()[0])
            except (IndexError, ValueError):
                return None
    return None


def main() -> None:
    raw = sys.stdin.read()
    hook_input = json.loads(raw) if raw.strip() else {}

    cwd = Path(hook_input.get("cwd") or Path.cwd())
    marker_path = cwd / MARKER_REL
    if not marker_path.exists():
        return  # not armed — the common case, exit silently

    marker = json.loads(marker_path.read_text())
    feature_dir = cwd / marker.get("feature_dir", "")

    flow = marker.get("flow")
    flow_node = marker.get("node")
    flow_mode = bool(flow and flow_node)

    if hook_input.get("stop_hook_active"):
        log(f"bypass stop_hook_active cwd={cwd}")
        trace(feature_dir, "loop-bypass", cwd=cwd)
        return

    max_iter = int(marker.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    iteration = int(marker.get("iteration", 0))

    if flow_mode:
        flow_check = Path(marker.get("flow_check")
                          or Path.home() / ".claude" / "netdust-flow"
                          / "bin" / "flow-check.py").expanduser()
        flow_path = Path(flow).expanduser()
        if not flow_path.is_absolute():
            flow_path = cwd / flow_path
        gate_timeout = int(marker.get("gate_timeout", 600))
        argv = [sys.executable, str(flow_check), str(feature_dir),
                "--flow", str(flow_path), "--node", str(flow_node),
                "--cwd", str(cwd), "--timeout", str(gate_timeout)]
        for k, v in (marker.get("binds") or {}).items():
            argv += ["--bind", f"{k}={v}"]
        check = subprocess.run(argv, capture_output=True, text=True,
                               timeout=gate_timeout + 60, cwd=str(cwd))
    else:
        check = subprocess.run(
            [sys.executable, str(LOOP_CHECK), str(feature_dir)],
            capture_output=True, text=True, timeout=120, cwd=str(cwd),
        )
    reason = (check.stdout.splitlines() or ["LOOP: no output"])[0]
    flow_next = None
    if flow_mode:
        for _line in check.stdout.splitlines():
            if _line.startswith("next: "):
                flow_next = _line.split("next: ", 1)[1].strip()
                break

    if check.returncode == 0:
        marker_path.unlink(missing_ok=True)
        log(f"disarm reason=finished iter={iteration} cwd={cwd}")
        trace(feature_dir, "loop-disarm-finished", cwd=cwd, iteration=iteration)
        return

    if check.returncode == 2:
        if flow_mode and flow_next:
            marker["node"] = flow_next
            marker_path.write_text(json.dumps(marker))
        log(f"yield reason=blocked iter={iteration} detail={reason!r}")
        trace(feature_dir, "loop-yield-blocked", cwd=cwd, iteration=iteration, reason=reason)
        return  # human's turn; marker stays armed for when work resumes

    # CONTINUE — apply guardrails, then block the stop.
    iteration += 1
    if iteration > max_iter:
        marker_path.unlink(missing_ok=True)
        log(f"disarm reason=budget-exhausted iter={iteration} max={max_iter}")
        trace(feature_dir, "loop-disarm-budget", cwd=cwd, iteration=iteration, max_iterations=max_iter)
        return

    done = read_progress(check.stdout)
    if done is not None:
        if done <= int(marker.get("last_done", -1)):
            marker["dry"] = int(marker.get("dry", 0)) + 1
        else:
            marker["dry"] = 0
        marker["last_done"] = done
        if marker["dry"] >= int(marker.get("max_dry", MAX_DRY)):
            marker_path.unlink(missing_ok=True)
            log(f"disarm reason=dry-loop iter={iteration} done={done}")
            # No ternary needed here (unlike the `block` trace call below):
            # this whole branch is inside `if done is not None:` above, so
            # `done` is already guaranteed non-None.
            trace(feature_dir, "loop-disarm-dry", cwd=cwd,
                  iteration=iteration, done=done)
            return

    marker["iteration"] = iteration
    if flow_mode and flow_next:
        marker["node"] = flow_next
    marker_path.write_text(json.dumps(marker))

    log(f"block iter={iteration}/{max_iter} done={done} detail={reason!r}")
    trace(feature_dir, "loop-block", cwd=cwd,
          iteration=iteration, done=(done if done is not None else "unknown"),
          total=max_iter, reason=reason)
    if flow_mode:
        guidance = (
            "Work the named node with its declared craft only; HALT at "
            "── REVIEW GATE ── markers as normal. To stop the loop, delete "
        )
    else:
        guidance = (
            "Rebuild state "
            "from tasks.md + the plan (never from scrollback), dispatch the "
            "next unit per building Stage 2, and HALT at "
            "── REVIEW GATE ── markers as normal. To stop the loop, delete "
        )
    print(json.dumps({
        "decision": "block",
        "reason": (
            f"{reason} [harness loop {iteration}/{max_iter}] {guidance}"
            f"{MARKER_REL}."
        ),
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail OPEN: a broken gate must never trap a session.
        log(f"unhandled-exception err={type(e).__name__}:{e} (failing open)")
    sys.exit(0)
