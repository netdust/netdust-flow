#!/usr/bin/env python3
"""floor-check.py — mechanical dispatch floors (principle 8's gate).

    floor-check.py [--floors floors.yaml] [--base REF]

Scans the change (git diff BASE...HEAD plus the working tree) for
floor patterns. Exit 0: clean — small-road work. Exit 2: a floor
triggered — this change belongs on the deliver flow; the patch flow
routes exit != 0 to __human__ so YOU re-dispatch. Floors only ever
push work UP; there is deliberately no override down.
"""
from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


def sh(*args: str) -> tuple[int, str]:
    p = subprocess.run(list(args), capture_output=True, text=True)
    return p.returncode, p.stdout


def load_floors(path: Path) -> dict:
    if yaml is not None:
        return (yaml.safe_load(path.read_text()) or {}).get("floors", {})
    # dependency-free fallback: crude but sufficient structure parse
    floors: dict = {}
    cat = None
    for line in path.read_text().splitlines():
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s == "floors:":
            continue
        if s.endswith(":") and not line.startswith("    "):
            cat = s[:-1]
            floors[cat] = {"paths": [], "content": []}
        elif cat and s.startswith(("paths:", "content:")):
            key = s.split(":")[0]
            items = re.findall(r"['\"](.+?)['\"]", s)
            floors[cat][key] = items
    return floors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--floors", type=Path,
                    default=Path(__file__).resolve().parents[1] / "floors.yaml")
    ap.add_argument("--base", default="main")
    args = ap.parse_args()

    floors = load_floors(args.floors)
    rc, merge_base = sh("git", "merge-base", "HEAD", args.base)
    if rc != 0:
        # Fail CLOSED: an unresolvable base means committed changes would
        # escape the scan entirely. Floors only ever push up (exit 2).
        print(f"FLOOR: BLOCKED — cannot resolve base ref `{args.base}` "
              "(git merge-base failed); refusing to scan a partial diff — "
              "pass --base <ref> that exists in this repo")
        return 2
    base = merge_base.strip()
    _, names = sh("git", "diff", "--name-only", base)
    _, wt_names = sh("git", "diff", "--name-only")
    files = sorted(set(names.split()) | set(wt_names.split()))
    _, body = sh("git", "diff", base)
    _, wt_body = sh("git", "diff")
    text = body + wt_body

    hits: list[str] = []
    for cat, rules in floors.items():
        for pattern in rules.get("paths", []):
            for f in files:
                if fnmatch.fnmatch(f, pattern):
                    hits.append(f"{cat}: path {f}")
        for rx in rules.get("content", []):
            if re.search(rx, text):
                hits.append(f"{cat}: content /{rx}/")

    if hits:
        print("FLOOR: TRIGGERED — this change belongs on deliver")
        for h in sorted(set(hits))[:6]:
            print(f"  - {h}")
        return 2
    print(f"FLOOR: clean ({len(files)} files against {args.base})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
