#!/usr/bin/env python3
"""
loop-gate.py — netdust-flow Stop hook: the flow driver.

When a run is ARMED (marker file tasks/.netdust-flow.json exists,
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
    • nothing moved max_dry stops in a row  → disarm, allow (dry loop).
      "Nothing moved" is the done-count AND the worktree AND the gate
      exits, all unchanged. Checkbox-only dryness disarmed the loops
      whose work does not tick checkboxes (run 0004, F04).

Guardrails that always win: stop_hook_active bypass (one block per stop
cycle), marker deletion by the human, and fail-open — any internal error
allows the stop. Logs to ~/.claude/logs/memory-hook.log.

Marker schema (tasks/.netdust-flow.json — runtime state, gitignored by
/flow; run_id is minted here at the first stop of an armed run):
  {"schema": "netdust-flow/1",
   "feature_dir": "specs/<feature>", "iteration": 0, "max_iterations": 25,
   "last_done": 0, "dry": 0,
   "session": "<claimed at the first stop; other sessions no-op>",
   "tree": "<worktree fingerprint>", "gate_sig": "<gate exits>",
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
# Canonically bin/flowspec.py; repeated as a literal because the
# hook path takes no imports that could fail before the fail-open
# wrapper is in scope. test_marker_identity.py asserts they agree.
MARKER_REL = Path("tasks") / ".netdust-flow.json"
MARKER_SCHEMA = "netdust-flow/1"
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


def worktree_fingerprint(cwd: Path, feature_dir: Path) -> str | None:
    """A cheap digest of "did anything actually change".

    `dry` used to mean "no checkbox ticked", which is not the same thing
    at all: a convergence loop produces findings, revises the spec and
    rewrites its report while the task ledger stands still. Run 0004
    needed three such rounds and the default max_dry of 2 would have
    disarmed a healthy run even with no observer in the repo.

    Three sources, none of which touches the repo:
      · HEAD               — a commit landed
      · `git status`       — files appeared, vanished, or became dirty
      · size+mtime of the  — the case status alone cannot see: a file
        dirty paths and      that was ALREADY modified being edited
        the feature dir      again, which is most of a review round

    Fail-open by returning None (no git, not a repo, anything at all),
    which restores the old done-count-only comparison rather than
    trapping or freeing a run on a technicality."""
    try:
        def git(*args: str) -> str | None:
            p = subprocess.run(["git", *args], capture_output=True,
                               text=True, cwd=str(cwd), timeout=30)
            return p.stdout if p.returncode == 0 else None

        head = git("rev-parse", "HEAD")
        status = git("status", "--porcelain")
        if head is None or status is None:
            return None

        parts = [head, status]
        paths = [line[3:].strip() for line in status.splitlines() if line[3:]]
        for name in sorted(set(paths)):
            parts.append(stamp(cwd / name.strip('"')))
        # The feature dir is where review rounds do their work, and its
        # files are often already dirty, so status alone under-reports it.
        for path in sorted((cwd / feature_dir).rglob("*")):
            if path.name.startswith(".flow-journal"):
                continue   # written BY this hook; it is not the run's work
            parts.append(stamp(path))
        return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:16]
    except Exception:
        return None


def stamp(path: Path) -> str:
    try:
        st = path.stat()
        return f"{path}:{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return f"{path}:-"


def gate_signature(events: list[dict]) -> str:
    """Which gates ran in this walk and what they answered. A red gate
    going green is movement, even before a box is ticked."""
    return ";".join(f"{e.get('node')}={e.get('exit')}" for e in events
                    if e.get("event") == "gate")


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

    # A marker that names another harness's schema is not ours, even in
    # our own filename. A marker with NO schema line predates the
    # discriminator and is judged the old way, on its flow fields.
    schema = marker.get("schema")
    if schema is not None and schema != MARKER_SCHEMA:
        log(f"ignore foreign schema={schema!r} cwd={cwd}")
        return

    flow = marker.get("flow")
    flow_node = marker.get("node")
    if not (flow and flow_node):
        # not our marker — leave it alone, allow the stop
        log(f"ignore flowless marker cwd={cwd}")
        return

    if hook_input.get("stop_hook_active"):
        log(f"bypass stop_hook_active cwd={cwd}")
        return

    # RUN OWNERSHIP (F01). The marker is project-scoped, so this hook
    # fires on EVERY session that stops in the repo — including a second
    # session merely watching the run. Run 0004 lost run 1340 to exactly
    # that: two of the observer's stops moved no task counter, counted as
    # dry iterations of the BUILDER's run, and disarmed it.
    #
    # The claim is minted at the first stop, where run_id already is:
    # arming happens in a Bash call that does not know its own session
    # id. A session that finds someone else's claim is as inert as a
    # session with no marker at all. A host that sends no session_id
    # drives unchanged — scoping must never trap a run.
    # Stranded claim (the owning session died): `flow-arm --reclaim`.
    session = hook_input.get("session_id")
    if session:
        owner = marker.get("session")
        if owner and owner != session:
            log(f"ignore foreign session={session} owner={owner} cwd={cwd}")
            return
        marker["session"] = session

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
        # written unconditionally: a first stop that lands on a human
        # node must still persist its session claim, or the run stays
        # unowned and the next foreign stop takes it.
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

    # DRYNESS (F04). A stop is dry only when NOTHING moved: not the
    # done-count, not the worktree, not the gate answers. Counting a
    # stop dry because no checkbox ticked disarms exactly the loops
    # whose work does not tick checkboxes — convergence and review.
    done = read_progress(check.stdout)
    fingerprint = worktree_fingerprint(cwd, Path(marker.get("feature_dir", "")))
    gate_sig = gate_signature(gate_events)
    moved = (
        (done is not None and done > int(marker.get("last_done", -1)))
        or (fingerprint is not None and fingerprint != marker.get("tree"))
        or (gate_sig != marker.get("gate_sig", ""))
    )
    marker["tree"] = fingerprint
    marker["gate_sig"] = gate_sig
    if done is not None:
        marker["last_done"] = done
    marker["dry"] = 0 if moved else int(marker.get("dry", 0)) + 1
    if marker["dry"] >= int(marker.get("max_dry", MAX_DRY)):
        journal(feature_dir, jbase, gate_events + [
            {"event": "stop", "verdict": "CONTINUE",
             "decision": "disarm-dry",
             "node": flow_next or str(flow_node),
             "iter": iteration, "done": done,
             "tree": fingerprint, "gates": gate_sig}])
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
    # The craft is DECLARED here so it actually reaches the agent (run
    # 0001 lost a node's craft because the reason never named it). It is
    # not a deselection of everything else: run 0004's plan and build
    # nodes ran with no threat model, no per-data-flow security pillars
    # and no independent test-author because "with that craft only" read
    # as "and nothing else" — the project's own harness included.
    guidance = (
        (f"Craft for this node: {craft}. Load it and work the node "
         "through it" if craft else
         "Work the named node through its declared craft")
        + " — that names this node's skills and agents, and does not "
          "replace the project's own harness, stack skills or plan-time "
          "gates, which apply as they always do. HALT at "
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
