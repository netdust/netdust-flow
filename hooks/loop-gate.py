#!/usr/bin/env python3
"""
loop-gate.py — netdust-flow Stop hook: the flow driver.

When a run is ARMED (marker file tasks/.harness-loop.json exists,
written by /flow), this hook consults bin/flow-check.py (the walker)
at every session stop and BLOCKS the stop while the flow is
unfinished. No marker → no-op (zero cost for every normal session).
A marker without flow fields is not ours and is left untouched.

Token cost of the loop itself: ~zero. The gate is deterministic Python;
the only context it ever adds is the 2-line block reason.

Decision table (marker present, stop_hook_active false):
  flow-check exit 0 (FINISHED) → disarm (delete marker), allow stop.
  flow-check exit 2 (BLOCKED)  → allow stop, KEEP marker — the agent has
                                 already surfaced the human question in its
                                 transcript; when the human answers and work
                                 resumes, the loop re-engages at next stop.
  flow-check exit 1 (CONTINUE) → block with the next node, UNLESS a
                                 guardrail disarms first:
    • iteration >= max_iterations           → disarm, allow (budget spent)
    • done-count unchanged 2 stops in a row → disarm, allow (dry loop)

Guardrails that always win: stop_hook_active bypass (one block per stop
cycle), marker deletion by the human, and fail-open — any internal error
allows the stop. Logs to ~/.claude/logs/memory-hook.log.

Marker schema (tasks/.harness-loop.json — runtime state, gitignored by
/flow; run_id is minted here at the first stop of an armed run):
  {"feature_dir": "specs/<feature>", "iteration": 0, "max_iterations": 25,
   "last_done": 0, "dry": 0,
   "flow": "<abs path to flows/*.json twin>", "node": "__start__",
   "flow_check": "<abs path to netdust-flow/bin/flow-check.py>",
   "binds": {"gate_check_cmd": "...",
             "test_suite_cmd": "..."},          # per-flow requirements
   "max_dry": 25, "gate_timeout": 600}          # optional overrides
The walker's `next:` line is persisted back into marker["node"] whenever
the marker survives (CONTINUE and BLOCKED).

Trust boundary (named, v0.2): the marker file IS the persisted machine
state, and it is writable by anything with filesystem access — an agent
could rewrite "node", swap "flow", or neuter "binds" exactly as easily
as forging a git note. hooks/pretooluse-guard.py denies the direct
forge of the twins and journal (and `git notes` writes); the marker
is left editable on purpose, since arming writes it — that residue is
named in the guard. This hook deliberately does not re-verify the
marker's provenance: the gate is deterministic, the guard raises the
cost of the obvious tamper. I8 anchors the GRAPH itself: this hook
passes --require-anchor from the marker so the walker refuses a twin
that was not armed (rewriting the road mid-run is BLOCKED, not silent).
"""

import hashlib
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

LOG_PATH = Path.home() / ".claude" / "logs" / "memory-hook.log"
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


def flow_traces(stdout: str) -> list[dict]:
    """Collect the walker's `trace: {...}` lines (one per gate executed,
    red exits included — the walker is the only component that sees
    them). Malformed lines are dropped; the journal is best-effort."""
    out = []
    for line in stdout.splitlines():
        if not line.startswith("trace: "):
            continue
        try:
            ev = json.loads(line[len("trace: "):])
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def journal(feature_dir: Path, base: dict, events: list[dict]) -> None:
    """Fail-open journal append: one JSONL line per event into
    <feature-dir>/.flow-journal.jsonl (gitignored runtime evidence,
    read back by bin/flow-eval.py). Same rule as trace(): journaling
    must NEVER affect the gate's decision, control flow, or stdout.
    Trust boundary: the journal joins the compiled twins and git notes
    as files hooks/pretooluse-guard.py denies agents from hand-writing."""
    try:
        ts = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with open(feature_dir / ".flow-journal.jsonl", "a") as f:
            for ev in events:
                f.write(json.dumps({"ts": ts, **base, **ev}) + "\n")
    except Exception:
        pass


def read_craft(stdout: str) -> str | None:
    """The walker names the craft the next node declares. Passing it
    into the block reason costs one line of context and removes the
    excuse: before this, the reason said "with its declared craft"
    without ever saying WHICH, so the agent had to open the marker,
    find the twin and read the node — and run 0001 (F4) is what
    happens when it does not."""
    for line in stdout.splitlines():
        if line.startswith("craft: "):
            return line[len("craft: "):].strip() or None
    return None


def read_actor(stdout: str) -> str | None:
    """The walker names the actor the next node declares (optional).
    Journaled so the run record answers WHO the work was assigned to —
    a declaration, not proof of who performed it (evidence.md)."""
    for line in stdout.splitlines():
        if line.startswith("actor: "):
            return line[len("actor: "):].strip() or None
    return None


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
    if not (flow and flow_node):
        # not our marker — leave it alone, allow the stop
        log(f"ignore flowless marker cwd={cwd}")
        return

    if hook_input.get("stop_hook_active"):
        log(f"bypass stop_hook_active cwd={cwd}")
        return

    max_iter = int(marker.get("max_iterations", DEFAULT_MAX_ITERATIONS))
    iteration = int(marker.get("iteration", 0))

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
    if marker.get("require_anchor"):
        argv.append("--require-anchor")
    for k, v in (marker.get("binds") or {}).items():
        argv += ["--bind", f"{k}={v}"]
    check = subprocess.run(argv, capture_output=True, text=True,
                           timeout=gate_timeout + 60, cwd=str(cwd))
    reason = (check.stdout.splitlines() or ["FLOW: no output"])[0]
    flow_next = None
    for _line in check.stdout.splitlines():
        if _line.startswith("next: "):
            flow_next = _line.split("next: ", 1)[1].strip()
            break

    # run identity: minted at the first stop of an armed run and
    # persisted in the marker, so every stop of one arming shares it
    if not marker.get("run_id"):
        # A run id scopes evidence (attests, seals). Seconds are not
        # enough resolution: two records armed in the same second get
        # the same id, and then only feature-scoping keeps one run's
        # approval out of the other's gate. The suffix makes run-scoping
        # stand on its own rather than lean on that second guard.
        marker["run_id"] = (time.strftime("r%Y%m%d-%H%M%S")
                            + "-" + secrets.token_hex(2))
    try:
        fhash = hashlib.sha256(flow_path.read_bytes()).hexdigest()[:12]
    except Exception:
        fhash = "unknown"
    jbase = {"run": marker["run_id"], "flow": flow_path.stem, "fhash": fhash}
    gate_events = flow_traces(check.stdout)

    if check.returncode == 0:
        journal(feature_dir, jbase, gate_events + [
            {"event": "stop", "verdict": "FINISHED",
             "decision": "disarm-finished", "node": "__end__",
             "iter": iteration}])
        marker_path.unlink(missing_ok=True)
        log(f"disarm reason=finished iter={iteration} cwd={cwd}")
        return

    if check.returncode == 2:
        journal(feature_dir, jbase, gate_events + [
            {"event": "stop", "verdict": "BLOCKED", "decision": "yield",
             "node": flow_next or str(flow_node), "iter": iteration,
             "reason": reason[:200]}])
        if flow_next:
            marker["node"] = flow_next
            marker_path.write_text(json.dumps(marker))
        log(f"yield reason=blocked iter={iteration} detail={reason!r}")
        return  # human's turn; marker stays armed for when work resumes

    # CONTINUE — apply guardrails, then block the stop.
    iteration += 1
    if iteration > max_iter:
        journal(feature_dir, jbase, gate_events + [
            {"event": "stop", "verdict": "CONTINUE",
             "decision": "disarm-budget",
             "node": flow_next or str(flow_node), "iter": iteration}])
        marker_path.unlink(missing_ok=True)
        log(f"disarm reason=budget-exhausted iter={iteration} max={max_iter}")
        return

    done = read_progress(check.stdout)
    if done is not None:
        if done <= int(marker.get("last_done", -1)):
            marker["dry"] = int(marker.get("dry", 0)) + 1
        else:
            marker["dry"] = 0
        marker["last_done"] = done
        if marker["dry"] >= int(marker.get("max_dry", MAX_DRY)):
            journal(feature_dir, jbase, gate_events + [
                {"event": "stop", "verdict": "CONTINUE",
                 "decision": "disarm-dry",
                 "node": flow_next or str(flow_node),
                 "iter": iteration, "done": done}])
            marker_path.unlink(missing_ok=True)
            log(f"disarm reason=dry-loop iter={iteration} done={done}")
            return

    marker["iteration"] = iteration
    if flow_next:
        marker["node"] = flow_next
    marker_path.write_text(json.dumps(marker))
    actor = read_actor(check.stdout)
    journal(feature_dir, jbase, gate_events + [
        {"event": "stop", "verdict": "CONTINUE", "decision": "block",
         "node": flow_next or str(flow_node), "iter": iteration,
         "done": done, "dry": int(marker.get("dry", 0)),
         **({"actor": actor} if actor else {}),
         "reason": reason[:200]}])

    log(f"block iter={iteration}/{max_iter} done={done} detail={reason!r}")
    craft = read_craft(check.stdout)
    guidance = (
        (f"Craft for this node: {craft}. Work the node with that craft "
         "only; " if craft else
         "Work the named node with its declared craft only; ")
        + "HALT at ── REVIEW GATE ── markers as normal. To stop the loop, "
          "delete "
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
