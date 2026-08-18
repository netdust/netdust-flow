#!/usr/bin/env python3
"""flowspec.py — the three rules the tools must agree on.

STDLIB ONLY, deliberately: `bin/flow-check.py` imports this and runs in
the Stop-hook path, where a third-party import would break the promise
that the hook works on a bare interpreter (CI enforces it in the
`hooks-run-without-authoring-deps` job). Callers that need YAML pass
their own loader in.

Three rules live here because three tools were each about to implement
them separately, and a rule implemented twice is a rule that drifts:

  resolve_program  where a gate's program is. Project root first, then
                   the plugin root, then PATH — so the answer flow-arm
                   gives at arm time IS the answer flow-check gets at
                   run time. (`flow-lint --check-gates --bind` used to
                   have its own version of this and got it wrong: it
                   substituted a multi-word bind into `run.split()[0]`
                   and then looked for a file named
                   `python3 .flow/bin/gate.py`.)
  resolve_craft    where a node's declared craft is. Same order, same
                   reason: a global skill answering for a project is
                   craft that shapes the wrong work.
  flatten          `extends:` composition, resolved at COMPILE time.
                   The twin holds the complete graph, so the walker
                   never learns that composition exists.
"""
from __future__ import annotations

import shlex
import shutil
from pathlib import Path

SCRIPT_SUFFIXES = (".py", ".sh")
PACK_DIR = Path(".flow")
MAX_EXTENDS_DEPTH = 8


# ── gates ────────────────────────────────────────────────────────────

def substitute(text: str, binds: dict) -> str:
    for key, value in binds.items():
        text = text.replace("{" + key + "}", str(value))
    return text


def resolve_program(token: str, project: Path | None,
                    plugin_root: Path | None) -> Path | None:
    """Project root first — a project's own `.flow/bin/x.py` must beat
    a same-named script installed globally, because a global script
    silently answering for a project is a gate that measures the wrong
    thing. PATH last, which is how a bare `python3` or `make` resolves."""
    candidate = Path(token)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    for root in (project, plugin_root):
        if root is not None and (root / token).exists():
            return root / token
    found = shutil.which(token)
    return Path(found) if found else None


def gate_programs(cmd: str) -> list[str]:
    """Every token of a gate command that has to exist: argv[0], plus
    any argument that looks like a script. `python3 .flow/bin/gate.py`
    resolves argv[0] on PATH, and the thing that actually goes missing
    is the script — checking only argv[0] would pass it every time."""
    try:
        argv = shlex.split(cmd)
    except ValueError:
        return []
    if not argv:
        return []
    return [argv[0]] + [t for t in argv[1:] if t.endswith(SCRIPT_SUFFIXES)]


# ── craft ────────────────────────────────────────────────────────────

def resolve_craft(name: str, project: Path | None,
                  plugin_root: Path | None) -> Path | None:
    """A node's craft, resolved project-first like everything else.
    Accepts both forms in use: a bare name (`agents/planner`, resolved
    with or without a `.md` suffix) and an explicit path
    (`.flow/craft/build.md`)."""
    roots: list[Path] = []
    if project is not None:
        roots += [project / PACK_DIR / "craft", project]
    if plugin_root is not None:
        roots.append(plugin_root)
    names = [name] if name.endswith(".md") else [name, name + ".md"]
    for root in roots:
        for candidate in names:
            path = root / candidate
            if path.exists() and path.is_file():
                return path
    return None


def craft_of(doc: dict) -> list[tuple[str, str]]:
    """(node id, craft entry) for every craft declaration in the flow."""
    out = []
    for node in doc.get("nodes", []) or []:
        if not isinstance(node, dict):
            continue
        for entry in node.get("craft") or []:
            out.append((str(node.get("id")), str(entry)))
    return out


# ── composition ──────────────────────────────────────────────────────

def flow_source(name: str, project: Path | None, runtime: Path,
                base_dir: Path) -> Path | None:
    """Resolve a flow NAME the way `/flow` does — project pack first,
    then the runtime's built-in roads. A path is taken literally,
    relative to the file that named it."""
    if name.endswith((".yaml", ".yml", ".json")) or "/" in name:
        literal = Path(name)
        if not literal.is_absolute():
            literal = base_dir / literal
        return literal if literal.exists() else None
    candidates = []
    if project is not None:
        candidates.append(project / PACK_DIR / "flows" / f"{name}.yaml")
    candidates.append(runtime / "flows" / f"{name}.yaml")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


class ExtendsError(Exception):
    pass


def flatten(doc: dict, load, base_dir: Path, project: Path | None,
            runtime: Path, _seen: tuple[str, ...] = ()) -> dict:
    """Resolve `extends:` into one complete graph.

    Composition happens at compile time and nowhere else: the twin the
    walker reads is fully flattened, so the runtime keeps exactly one
    notion of what a flow is. The merge rules are deliberately few, and
    the derived graph still faces the whole lint — reachability, dead
    ends, determinism, I1/I2/I4 — so a composition that breaks the
    wiring fails statically instead of mid-run.

      nodes    merged by id: a child node with a parent's id REPLACES
               it, a new id is appended.
      remove   drops those nodes and every edge that touches them.
      edges    routing is overridden per source node: if the child
               declares any edge from X, the child's edges from X
               replace the parent's edges from X entirely. Anything
               else would leave two routing tables for one decision.
      state    parent's, updated with the child's.

    `flow` and `version` always come from the child — a derived road is
    its own road, with its own eval cohort.
    """
    parent_name = doc.get("extends")
    if not parent_name:
        return {k: v for k, v in doc.items() if k != "remove"}
    if len(_seen) >= MAX_EXTENDS_DEPTH:
        raise ExtendsError(f"`extends` nested deeper than "
                           f"{MAX_EXTENDS_DEPTH} (cycle?)")
    if str(parent_name) in _seen:
        raise ExtendsError(f"`extends` cycle: {' -> '.join(_seen)} -> "
                           f"{parent_name}")

    parent_path = flow_source(str(parent_name), project, runtime, base_dir)
    if parent_path is None:
        raise ExtendsError(f"`extends: {parent_name}` resolves to nothing")
    parent = flatten(load(parent_path), load, parent_path.parent, project,
                     runtime, _seen + (str(parent_name),))

    removed = {str(x) for x in (doc.get("remove") or [])}
    child_nodes = {str(n["id"]): n for n in (doc.get("nodes") or [])
                   if isinstance(n, dict) and "id" in n}

    nodes: list[dict] = []
    for node in parent.get("nodes") or []:
        nid = str(node.get("id"))
        nodes.append(child_nodes.pop(nid, node) if nid in child_nodes else node)
    nodes += list(child_nodes.values())
    nodes = [n for n in nodes if str(n.get("id")) not in removed]

    child_edges = [e for e in (doc.get("edges") or []) if isinstance(e, dict)]
    overridden = {str(e.get("from")) for e in child_edges}
    edges = [e for e in (parent.get("edges") or [])
             if str(e.get("from")) not in overridden] + child_edges
    edges = [e for e in edges
             if str(e.get("from")) not in removed
             and str(e.get("to")) not in removed]

    merged = dict(parent)
    merged.update({k: v for k, v in doc.items()
                   if k not in ("extends", "remove", "nodes", "edges",
                                "state")})
    merged["state"] = {**(parent.get("state") or {}),
                       **(doc.get("state") or {})}
    merged["nodes"] = nodes
    merged["edges"] = edges
    merged.pop("extends", None)
    merged.pop("remove", None)
    return merged


# ── I8: graph anchoring ──────────────────────────────────────────────
# An armed flow may only execute the exact graph present when it was
# armed. flow-arm writes a note keyed by the twin's git blob sha into
# ANCHOR_REF (inside its own process, so the pretooluse guard's
# git-notes deny covers forgery/removal); the walker recomputes the
# blob sha and refuses a twin that carries no matching anchor. Editing
# the graph changes the blob → no anchor → BLOCK, until a deliberate
# re-arm writes a new anchor. Stdlib only (subprocess); the hook path
# takes no authoring deps and git is already the evidence substrate.

ANCHOR_REF = "refs/notes/flow-anchor"


def _git(cwd, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


def twin_blob_sha(twin, cwd, write=False):
    """The git blob sha of the twin's exact bytes. `write` stores the
    blob so a note can attach to it. None if git is unavailable."""
    args = ["hash-object"] + (["-w"] if write else []) + [str(twin)]
    p = _git(cwd, *args)
    sha = p.stdout.strip()
    return sha if (p.returncode == 0 and sha) else None


def anchor_ref_exists(cwd):
    return _git(cwd, "rev-parse", "--verify", "--quiet",
                ANCHOR_REF).returncode == 0


def anchor_valid_for(twin, cwd):
    """True iff the CURRENT twin's blob carries an anchor note — i.e.
    this is the exact graph that was armed."""
    sha = twin_blob_sha(twin, cwd)
    if not sha:
        return False
    return _git(cwd, "notes", "--ref=" + ANCHOR_REF, "show",
                sha).returncode == 0


def write_anchor(twin, cwd, meta=""):
    """Arm-time: store the twin blob and attach the anchor note. Returns
    the blob sha, or None if git is unavailable."""
    sha = twin_blob_sha(twin, cwd, write=True)
    if not sha:
        return None
    _git(cwd, "notes", "--ref=" + ANCHOR_REF, "add", "-f", "-m",
         meta or "armed", sha)
    return sha
