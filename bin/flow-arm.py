#!/usr/bin/env python3
"""flow-arm.py — arm the walker. The marker as evidence, not assertion.

    flow-arm.py <feature-dir> <flow> [--project DIR] [--node ID]
                [--bind NAME=VALUE ...] [--budget N] [--max-dry N]
                [--plugin-root DIR]

The marker (`tasks/.harness-loop.json`) is the ONLY input to the whole
machine: it names the flow, the starting node, the gate commands, and
the budget. Everything downstream refuses to guess — the walker BLOCKS
on an unbound placeholder, an unknown node, an unmatched edge — and
then trusts this one file completely.

Until this script existed the file was written by hand, by an agent
following six prose preconditions in `commands/flow.md`. That is the
one assertion the system never checked: `assertion → verification →
evidence` applied to every state transition except the one that starts
them. This script is that verification. Either every precondition
holds and the marker is written, or nothing is written and the reason
is one line instead of a dead run twenty minutes in — the same trade
the lint makes everywhere else.

What it refuses (each names what is missing, never guesses a value):

  flow          `<flow>` resolves to nothing (project `.flow/flows/`
                first, then the runtime's built-in roads)
  lint          the flow FAILs `flow-lint --compile`; a flow that
                cannot lint must never drive a run, and the walker
                reads the twin this step writes
  node          `--node` names a node the flow does not declare
  binds         a `{placeholder}` in some gate's `run:` has no value.
                This one rule subsumes the old per-flow preconditions:
                deliver's `{gate_check_cmd}` and patch's
                `{test_suite_cmd}` are refusals here for the same
                reason, so a new flow gets the same protection without
                anyone writing it a new paragraph.
  gates         a gate names a program that exists nowhere the walker
                would find it (project root, plugin root, PATH) —
                resolved with the walker's own semantics, so the
                answer here is the answer at run time
  requires      `.flow/pack.yaml` declares a required tool that is not
                on PATH
  base          the flow scans a diff against a base ref that does not
                resolve in this repo
  armed         a marker is already there; disarm before re-arming, or
                the live run's identity (and journal continuity) is
                silently thrown away

Bind values are collected, in increasing precedence: `netdust_flow`
and `base_ref` defaults, the project CLAUDE.md (`Gate check:` →
`gate_check_cmd`, `Test suite:` → `test_suite_cmd`), then `--bind`.
`feature_dir` is never a marker bind — the walker supplies it.

Authoring-side, like the lint: PyYAML is required here and never in
the Stop-hook path.
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("flow-arm: PyYAML required (pip install pyyaml) — "
             "authoring-side, never in the Stop-hook path")

RUNTIME = Path(__file__).resolve().parents[1]
MARKER_REL = Path("tasks") / ".harness-loop.json"
JOURNAL_NAME = ".flow-journal.jsonl"
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
BIND_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BUDGET_RE = re.compile(r"^\s*Loop budget:\s*~?\s*(\d+)", re.M)
SCRIPT_SUFFIXES = (".py", ".sh")

DEFAULT_BUDGET = 25
DEFAULT_MAX_DRY = 2
# A flow with no checkbox progress reports a near-constant `progress:`
# line, so the dry-loop counter would disarm it long before the work is
# done; termination belongs to the iteration budget there instead.
NO_PROGRESS_MAX_DRY = 25
DEFAULT_PLUGIN_ROOT = Path.home() / ".claude" / "plugins" / "netdust-agent"

# The walker binds this itself from its positional argument; a marker
# copy would be a second source of truth for the same value.
WALKER_BINDS = {"feature_dir"}

CLAUDE_MD_BINDS = (("Gate check:", "gate_check_cmd"),
                   ("Test suite:", "test_suite_cmd"))


class Refusals:
    """Same shape as the lint's findings: a check name and a detail,
    so a refusal reads like every other verdict in the system."""

    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    def add(self, check: str, detail: str) -> None:
        self.items.append((check, detail))

    def __bool__(self) -> bool:
        return bool(self.items)

    def report(self) -> None:
        for check, detail in self.items:
            print(f"REFUSED  [{check}]  {detail}")
        print(f"flow-arm: refused to arm — {len(self.items)} problem(s); "
              "nothing was written")


# ── resolution ───────────────────────────────────────────────────────

def resolve_flow(name: str, project: Path) -> tuple[Path | None, str]:
    """Project first, then the built-in roads. A name present in both
    resolves to the project's — a runtime flow silently answering for a
    project is a graph that drives the wrong work."""
    if name.endswith((".yaml", ".yml", ".json")) or "/" in name:
        literal = Path(name)
        if not literal.is_absolute():
            literal = project / literal
        return (literal if literal.exists() else None), "path"
    for candidate, origin in ((project / ".flow" / "flows" / f"{name}.yaml",
                               "project-owned"),
                              (RUNTIME / "flows" / f"{name}.yaml",
                               "built-in")):
        if candidate.exists():
            return candidate, origin
    return None, ""


def twin_of(src: Path) -> Path:
    return src if src.suffix == ".json" else src.with_suffix(".json")


def run_lint(src: Path, project: Path) -> tuple[bool, str]:
    """The lint owns the graph verdict AND writes the twin the walker
    reads. Arming past a red lint would put a flow on the road that the
    static gate already refused."""
    argv = [sys.executable, str(RUNTIME / "bin" / "flow-lint.py"), str(src)]
    if src.suffix != ".json":
        argv.append("--compile")
    p = subprocess.run(argv, capture_output=True, text=True, cwd=str(project))
    return p.returncode == 0, (p.stdout + p.stderr).strip()


# ── bind collection ──────────────────────────────────────────────────

def binds_from_claude_md(project: Path) -> dict[str, str]:
    """The project states its own commands in its own CLAUDE.md — the
    convention this repo already follows for itself. First line wins."""
    path = project / "CLAUDE.md"
    if not path.exists():
        return {}
    found: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        for label, key in CLAUDE_MD_BINDS:
            if stripped.startswith(label):
                value = stripped[len(label):].strip()
                if value:
                    found.setdefault(key, value)
    return found


def required_placeholders(doc: dict) -> set[str]:
    names: set[str] = set()
    for node in doc.get("nodes", []) or []:
        if isinstance(node, dict) and node.get("kind") == "gate":
            names |= set(PLACEHOLDER_RE.findall(str(node.get("run", ""))))
    return names - WALKER_BINDS


# ── gate programs, resolved the way the walker resolves them ─────────

def program_exists(token: str, project: Path, plugin_root: Path) -> bool:
    candidate = Path(token)
    if candidate.is_absolute():
        return candidate.exists()
    if (project / token).exists() or (plugin_root / token).exists():
        return True
    return shutil.which(token) is not None


def check_gates(doc: dict, binds: dict[str, str], feature_dir: Path,
                project: Path, plugin_root: Path, r: Refusals) -> None:
    """A gate whose program is missing surfaces mid-run as a BLOCKED
    walk, which reads like a flow defect and costs a whole arming to
    diagnose. Resolution mirrors flow-check.run_gate: substitute binds
    into the WHOLE command, split it, then resolve argv[0] project-root
    first. Scripts passed to an interpreter (`python3 x/y.py`) are
    checked too — argv[0] is on PATH there, and the thing that actually
    goes missing is the script.

    `feature_dir` is substituted here even though it is never a marker
    bind: the walker supplies it at run time, and leaving it standing
    would make every gate that takes it look unresolvable and skip the
    check — which is nearly all of them."""
    binds = {**binds, "feature_dir": str(feature_dir)}
    for node in doc.get("nodes", []) or []:
        if not isinstance(node, dict) or node.get("kind") != "gate":
            continue
        nid = node.get("id")
        cmd = str(node.get("run", ""))
        for key, value in binds.items():
            cmd = cmd.replace("{" + key + "}", value)
        if PLACEHOLDER_RE.search(cmd):
            continue  # already refused by the binds check; one voice per fault
        try:
            argv = shlex.split(cmd)
        except ValueError as exc:
            r.add("gates", f"gate `{nid}` command does not parse ({exc})")
            continue
        if not argv:
            r.add("gates", f"gate `{nid}` has an empty `run:`")
            continue
        if not program_exists(argv[0], project, plugin_root):
            r.add("gates", f"gate `{nid}` names `{argv[0]}`, which is not "
                           f"under {project}, the plugin root, or PATH")
            continue
        for token in argv[1:]:
            if token.endswith(SCRIPT_SUFFIXES) and not program_exists(
                    token, project, plugin_root):
                r.add("gates", f"gate `{nid}` runs `{token}`, which is not "
                               f"under {project}, the plugin root, or PATH")


# ── pack ─────────────────────────────────────────────────────────────

def load_pack(project: Path) -> dict:
    path = project / ".flow" / "pack.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {"__unparseable__": True}


def check_requires(pack: dict, r: Refusals) -> list[str]:
    """`requires:` is the pack saying which tools its gates shell out
    to. Missing ones fail the gate later; naming them now is free."""
    warnings: list[str] = []
    for entry in pack.get("requires", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        name = str(entry["name"])
        if shutil.which(name):
            continue
        why = entry.get("why", "")
        detail = f"`{name}` is not on PATH" + (f" — {why}" if why else "")
        if entry.get("optional"):
            warnings.append(detail)
        else:
            r.add("requires", detail)
    return warnings


# ── budget, dry, gitignore ───────────────────────────────────────────

def read_budget(feature_dir: Path) -> int:
    plan = feature_dir / "plan.md"
    if plan.exists():
        m = BUDGET_RE.search(plan.read_text())
        if m:
            return int(m.group(1))
    return DEFAULT_BUDGET


def checkbox_progress_available(doc: dict, feature_dir: Path) -> bool:
    """Does this run produce a tasks.md for the walker to count? Either
    it is already there, or some node declares it as an artifact. This
    is the first mechanical consumer of the `out:` declarations, and it
    replaces the prose rule that patch (which has no tasks.md) needs a
    different dry budget than deliver."""
    if (feature_dir / "tasks.md").exists():
        return True
    for node in doc.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        for artifact in node.get("out") or []:
            if "tasks.md" in str(artifact):
                return True
    return False


def ensure_gitignore(project: Path) -> list[str]:
    """The journal MUST be ignored: tracked, it dirties the worktree
    mid-run and the ledger's clean-tree check could never pass."""
    path = project / ".gitignore"
    existing = path.read_text().splitlines() if path.exists() else []
    present = {line.strip() for line in existing}
    added = [line for line in (str(MARKER_REL), JOURNAL_NAME)
             if line not in present]
    if added:
        lines = list(existing)
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["# netdust-flow runtime state", *added]
        path.write_text("\n".join(lines) + "\n")
    return added


# ── main ─────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Arm the netdust-flow walker for one feature")
    ap.add_argument("feature_dir", type=Path)
    ap.add_argument("flow", help="flow NAME (project-first) or a path")
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--node", default="__start__",
                    help="start node; past __start__ grafts onto existing work")
    ap.add_argument("--bind", action="append", default=[], metavar="NAME=VALUE")
    ap.add_argument("--budget", type=int, default=None)
    ap.add_argument("--max-dry", type=int, default=None)
    ap.add_argument("--gate-timeout", type=int, default=600)
    ap.add_argument("--plugin-root", type=Path, default=DEFAULT_PLUGIN_ROOT)
    args = ap.parse_args()

    project = args.project.resolve()
    feature_dir = args.feature_dir
    if feature_dir.is_absolute():
        try:
            feature_dir = feature_dir.relative_to(project)
        except ValueError:
            print(f"REFUSED  [feature]  {feature_dir} is outside {project}")
            return 1
    r = Refusals()

    marker_path = project / MARKER_REL
    if marker_path.exists():
        try:
            armed_at = json.loads(marker_path.read_text()).get("node", "?")
        except Exception:
            armed_at = "?"
        r.add("armed", f"{MARKER_REL} already exists (node `{armed_at}`) — "
                       "`/flow off` first; re-arming would discard the live "
                       "run's id and split its journal")
        r.report()
        return 1

    src, origin = resolve_flow(args.flow, project)
    if src is None:
        r.add("flow", f"`{args.flow}` resolves to nothing — looked in "
                      f"{project}/.flow/flows/ then {RUNTIME}/flows/")
        r.report()
        return 1

    ok, lint_out = run_lint(src, project)
    if not ok:
        r.add("lint", f"{src} does not lint clean — a flow the static gate "
                      "refused must never drive a run")
        r.report()
        print(lint_out)
        return 1

    twin = twin_of(src)
    doc = yaml.safe_load(src.read_text())

    nodes = {str(n.get("id")) for n in doc.get("nodes", []) or []
             if isinstance(n, dict)}
    if args.node != "__start__" and args.node not in nodes:
        r.add("node", f"`{args.node}` is not a node in {src.name} "
                      f"(declared: {', '.join(sorted(nodes))})")

    pack = load_pack(project)
    if pack.get("__unparseable__"):
        r.add("pack", f"{project}/.flow/pack.yaml does not parse")
        pack = {}
    warnings = check_requires(pack, r)

    binds: dict[str, str] = {"netdust_flow": str(RUNTIME)}
    binds.update(binds_from_claude_md(project))
    for raw in args.bind:
        if "=" not in raw:
            r.add("binds", f"bad --bind `{raw}` (NAME=VALUE)")
            continue
        key, value = raw.split("=", 1)
        if not BIND_NAME_RE.match(key):
            # a name no `{placeholder}` can ever spell binds nothing —
            # silently accepting it is how a typo becomes a dead run
            r.add("binds", f"bad --bind name `{key}` (must match "
                           f"{BIND_NAME_RE.pattern})")
            continue
        binds[key] = value

    needed = required_placeholders(doc)
    if "base_ref" in needed:
        binds.setdefault("base_ref", "main")
        probe = subprocess.run(["git", "rev-parse", "--verify",
                                binds["base_ref"]],
                               capture_output=True, text=True, cwd=str(project))
        if probe.returncode != 0:
            r.add("base", f"base ref `{binds['base_ref']}` does not resolve "
                          f"in {project} — pass --bind base_ref=<ref>; a diff "
                          "scan against a missing base fails closed mid-run")

    declared = pack.get("binds") or {}
    for name in sorted(needed - set(binds)):
        hint = ""
        if isinstance(declared, dict) and isinstance(declared.get(name), dict):
            hint = str(declared[name].get("description") or "")
        for label, key in CLAUDE_MD_BINDS:
            if key == name:
                hint = hint or f"add a `{label} <cmd>` line to CLAUDE.md"
        r.add("binds", f"`{{{name}}}` is used by a gate but has no value"
                       + (f" — {hint}" if hint else "") + " (or --bind it)")

    check_gates(doc, binds, feature_dir, project,
                args.plugin_root.expanduser(), r)

    if r:
        r.report()
        return 1

    # Nothing below here can refuse; the marker is written now.
    (project / feature_dir).mkdir(parents=True, exist_ok=True)
    budget = args.budget if args.budget is not None else read_budget(
        project / feature_dir)
    max_dry = args.max_dry if args.max_dry is not None else (
        DEFAULT_MAX_DRY if checkbox_progress_available(doc, project / feature_dir)
        else NO_PROGRESS_MAX_DRY)
    ignored = ensure_gitignore(project)

    marker = {
        "feature_dir": str(feature_dir),
        "iteration": 0,
        "max_iterations": budget,
        "last_done": 0,
        "dry": 0,
        "flow": str(twin.resolve()),
        "node": args.node,
        "flow_check": str(RUNTIME / "bin" / "flow-check.py"),
        "binds": binds,
        "max_dry": max_dry,
        "gate_timeout": args.gate_timeout,
    }
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2) + "\n")

    print(f"armed   {doc.get('flow')} ({origin}: {twin}) at `{args.node}`")
    print(f"        feature={feature_dir} budget={budget} max_dry={max_dry} "
          f"binds={', '.join(sorted(binds))}")
    for detail in warnings:
        print(f"WARN    [requires]  {detail}")
    if ignored:
        print(f"        .gitignore += {', '.join(ignored)}")
    print("ends    FINISHED at a gate disarms · a human node yields · "
          "budget or dry-loop disarms · `/flow off` anytime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
