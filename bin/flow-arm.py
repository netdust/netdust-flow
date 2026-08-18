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
  floors        the flow scans for dispatch floors and the project has
                no `.flow/floors.yaml`. Floors encode what is dangerous
                about THIS codebase; a runtime cannot know that, and
                until v0.5 it shipped a default that pretended to
  armed         a marker is already there; disarm before re-arming, or
                the live run's identity (and journal continuity) is
                silently thrown away

Bind values are collected, in increasing precedence: the defaults
(`netdust_flow`, `base_ref`, `floors_file`), the project CLAUDE.md
(`Gate check:` → `gate_check_cmd`, `Test suite:` → `test_suite_cmd`),
`.flow/pack.yaml`'s `binds.<name>.value` (flow-specific, so it beats
the repo-wide line), then `--bind`. `feature_dir` is never a marker
bind — the walker supplies it.

Authoring-side, like the lint: PyYAML is required here and never in
the Stop-hook path.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flowspec  # noqa: E402

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
PACK_DIR = Path(".flow")
PACK_FLOORS_REL = PACK_DIR / "floors.yaml"

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


def run_lint(src: Path, project: Path, plugin_root: Path,
             binds: dict[str, str], feature_dir: Path) -> tuple[bool, str]:
    """The lint owns the graph verdict, the gate-and-craft resolution
    checks, AND the twin the walker reads. Arming calls it with the
    binds resolved, so `{gate_check_cmd}` is checked for real instead
    of warned about — and arming does not reimplement any of it, which
    is how the two answers stay the same answer.

    `feature_dir` is passed as a bind for checking only: it is the
    walker's to supply at run time, but leaving it standing here would
    make every gate that takes it look unresolvable and skip the check
    — which is nearly all of them."""
    argv = [sys.executable, str(RUNTIME / "bin" / "flow-lint.py"), str(src),
            "--check-gates", "--check-craft",
            "--project", str(project), "--plugin-root", str(plugin_root)]
    if src.suffix != ".json":
        argv.append("--compile")
    for key, value in {**binds, "feature_dir": str(feature_dir)}.items():
        argv += ["--bind", f"{key}={value}"]
    p = subprocess.run(argv, capture_output=True, text=True, cwd=str(project))
    return p.returncode == 0, (p.stdout + p.stderr).strip()


def lint_findings(output: str, status: str) -> list[tuple[str, str]]:
    """The lint's own `FAIL  [check]  detail` lines, parsed back out so
    a gates problem is still reported as one instead of collapsing into
    a generic lint failure."""
    out = []
    prefix = f"{status}  ["
    for line in output.splitlines():
        if line.startswith(prefix):
            check, _, detail = line[len(prefix):].partition("]  ")
            out.append((check.strip() or "lint", detail.strip()))
    return out


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


# ── pack ─────────────────────────────────────────────────────────────

def load_pack(project: Path, r: Refusals) -> dict:
    """`.flow/pack.yaml` is a real artifact with a real schema, not a
    README with colons in it: an invalid pack refuses the arm here
    rather than quietly failing to supply a bind later."""
    path = project / PACK_DIR / "pack.yaml"
    if not path.exists():
        return {}
    try:
        pack = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:
        r.add("pack", f"{path} does not parse ({exc})")
        return {}
    if not isinstance(pack, dict):
        r.add("pack", f"{path}: top level must be a mapping")
        return {}
    try:
        import jsonschema
        schema = json.loads((RUNTIME / "pack.schema.json").read_text())
        for err in sorted(
                jsonschema.Draft202012Validator(schema).iter_errors(pack),
                key=str):
            where = "/".join(str(p) for p in err.absolute_path) or "<root>"
            r.add("pack", f"pack.yaml: {where}: {err.message}")
    except ImportError:  # pragma: no cover — authoring hosts have it
        pass
    return pack


def binds_from_pack(pack: dict) -> dict[str, str]:
    """A pack may supply its own bind values, which is what lets a
    project be self-contained instead of leaning on a CLAUDE.md
    convention it may not follow."""
    declared = pack.get("binds")
    if not isinstance(declared, dict):
        return {}
    return {name: str(spec["value"])
            for name, spec in declared.items()
            if isinstance(spec, dict) and spec.get("value") is not None}


def check_requires(pack: dict, r: Refusals) -> list[tuple[str, str]]:
    """`requires:` is the pack saying which tools its gates shell out
    to. Missing ones fail the gate later; naming them now is free."""
    warnings: list[tuple[str, str]] = []
    for entry in pack.get("requires", []) or []:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        name = str(entry["name"])
        if shutil.which(name):
            continue
        why = entry.get("why", "")
        detail = f"`{name}` is not on PATH" + (f" — {why}" if why else "")
        if entry.get("optional"):
            warnings.append(("requires", detail))
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

    twin = twin_of(src)
    try:
        # Flattened here too: `extends:` is resolved at compile time, and
        # arm has to see the same complete graph the lint will, or it
        # would look for placeholders in half a road.
        doc = flowspec.flatten(
            yaml.safe_load(src.read_text()),
            lambda p: yaml.safe_load(p.read_text()),
            src.parent, project, RUNTIME)
    except flowspec.ExtendsError as exc:
        r.add("extends", f"{src.name}: {exc}")
        r.report()
        return 1

    nodes = {str(n.get("id")) for n in doc.get("nodes", []) or []
             if isinstance(n, dict)}
    if args.node != "__start__" and args.node not in nodes:
        r.add("node", f"`{args.node}` is not a node in {src.name} "
                      f"(declared: {', '.join(sorted(nodes))})")

    pack = load_pack(project, r)
    warnings = check_requires(pack, r)

    binds: dict[str, str] = {"netdust_flow": str(RUNTIME)}
    binds.update(binds_from_claude_md(project))
    binds.update(binds_from_pack(pack))   # pack beats the repo-wide line
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
    if "floors_file" in needed:
        binds.setdefault("floors_file", str(PACK_FLOORS_REL))
        if not (project / binds["floors_file"]).exists():
            r.add("floors", f"`{binds['floors_file']}` does not exist in "
                            f"{project} — a flow that scans for dispatch "
                            "floors needs the project's own floors "
                            "(docs/project-pack.md; "
                            "examples/wordpress-plugin/floors.yaml is a "
                            "worked one). A floor file nobody wrote is a "
                            "floor that never triggers")
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

    if r:
        # Refuse before linting: the lint would compile a twin for a
        # flow that is not going to drive anything, and an unbound
        # placeholder makes its gate check unanswerable anyway.
        r.report()
        return 1

    ok, lint_out = run_lint(src, project, args.plugin_root.expanduser(),
                            binds, feature_dir)
    if not ok:
        found = lint_findings(lint_out, "FAIL")
        for check, detail in (found or [("lint", f"{src.name} does not lint "
                                         "clean — a flow the static gate "
                                         "refused must never drive a run")]):
            r.add(check, detail)
        r.report()
        return 1
    warnings += lint_findings(lint_out, "WARN")

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
    # I8: anchor the compiled twin so the walk can only execute the
    # graph that was armed. Written here inside flow-arm's own process;
    # the guard denies agent-issued `git notes`, so the anchor cannot be
    # forged or removed via the documented path. Re-arming re-anchors.
    anchor_sha = flowspec.write_anchor(
        twin, project, meta=json.dumps({"flow": doc.get("flow")}))
    if anchor_sha:
        marker["require_anchor"] = True

    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(json.dumps(marker, indent=2) + "\n")

    print(f"armed   {doc.get('flow')} ({origin}: {twin}) at `{args.node}`")
    print(f"        feature={feature_dir} budget={budget} max_dry={max_dry} "
          f"binds={', '.join(sorted(binds))}")
    for check, detail in warnings:
        print(f"WARN    [{check}]  {detail}")
    if ignored:
        print(f"        .gitignore += {', '.join(ignored)}")
    print("ends    FINISHED at a gate disarms · a human node yields · "
          "budget or dry-loop disarms · `/flow off` anytime")
    return 0


if __name__ == "__main__":
    sys.exit(main())
