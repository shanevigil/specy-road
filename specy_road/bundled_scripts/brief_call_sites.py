"""The brief's call sites: the modules that import each zoned file, one level.

Executors stopped for files outside their zones on most leaves of a release
line: the zones were written without reading the code, and the callers of a
zoned module were the first thing the change reached. Listing those callers
under the zones puts them in front of the executor, and of whoever wrote the
zones, before work starts.

The import graph is :mod:`specy_road.impact`'s (``ast`` over every ``.py`` blob
at ``HEAD``), read one level instead of walked to the tests. Python only, git
objects only, so the section is the same for the same commit. Paths are
git-root relative, like ``specy-road impact``.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from specy_road.finish_implementation_check import in_zones
from specy_road.impact import imported_names, module_names, python_sources
from specy_road.runtime_paths import project_prefix

FILE_CAP = 30       # zoned files listed; the rest are counted
IMPORTER_CAP = 10   # importers listed per file; the rest are counted


def direct_importers(files: dict[str, bytes], targets: set[str]) -> dict[str, list[str]]:
    """``{target: sorted files in files that import it}``, for targets with any."""
    paths = set(files) | targets
    inits = {p for p in paths if PurePosixPath(p).name == "__init__.py"}
    by_name: dict[str, set[str]] = {}
    for p in targets:
        for name in module_names(p, inits):
            by_name.setdefault(name, set()).add(p)
    out: dict[str, set[str]] = {}
    for p in sorted(files):
        for name in imported_names(files[p], p.split("/")[:-1]) or ():
            for dep in by_name.get(name, ()):
                if dep != p:
                    out.setdefault(dep, set()).add(p)
    return {t: sorted(ps) for t, ps in sorted(out.items())}


def _importer_line(target: str, outside: list[str], inside: int) -> str:
    shown = [f"`{p}`" for p in outside[:IMPORTER_CAP]]
    if len(outside) > IMPORTER_CAP:
        shown.append(f"_… and {len(outside) - IMPORTER_CAP} more_")
    if inside:
        shown.append(f"{inside} inside the zones")
    return f"- `{target}` ← " + ", ".join(shown)


def call_site_lines(root: Path, zones: list[str], ref: str = "HEAD") -> list[str]:
    """``### Call sites`` for section 7 of the brief, without a trailing blank line."""
    lines = [
        "### Call sites (one level)",
        "",
        f"Modules that import each zoned Python file at `{ref}`, named when they lie "
        "outside the zones: each is a likely change outside this leaf's zones, so add "
        "it to the zones before starting or say why it stays unchanged.",
        "",
    ]
    files = python_sources(root, ref)
    if files is None:
        return lines + ["_(cannot compute: git could not read the tree)_"]
    prefix = project_prefix(root)
    zs = [z.strip().strip("/") for z in zones if isinstance(z, str) and z.strip()]
    found = direct_importers(files, {p for p in files if in_zones(zs, p, prefix)})
    if not found:
        return lines + ["_none found (Python imports only)_"]
    rows, inside_only = [], 0
    for target, importers in found.items():
        outside = [p for p in importers if not in_zones(zs, p, prefix)]
        if outside:
            rows.append(_importer_line(target, outside, len(importers) - len(outside)))
        else:
            inside_only += 1
    lines += rows[:FILE_CAP]
    if len(rows) > FILE_CAP:
        lines.append(f"- _… and {len(rows) - FILE_CAP} more zoned files imported from outside the zones_")
    if inside_only:
        lines.append(f"- {inside_only} zoned file(s) imported only from inside the zones")
    return lines
