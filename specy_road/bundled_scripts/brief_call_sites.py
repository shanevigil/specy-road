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
IMPORTER_CAP = 20   # importers listed per file; the rest are counted


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


def _importer_line(target: str, importers: list[str], outside: set[str]) -> str:
    ordered = sorted(importers, key=lambda p: (p not in outside, p))
    shown = [
        f"`{p}`" + (" _(outside zones)_" if p in outside else "")
        for p in ordered[:IMPORTER_CAP]
    ]
    if len(ordered) > IMPORTER_CAP:
        shown.append(f"_… and {len(ordered) - IMPORTER_CAP} more_")
    return f"- `{target}` ← " + ", ".join(shown)


def call_site_lines(root: Path, zones: list[str], ref: str = "HEAD") -> list[str]:
    """``### Call sites`` for section 7 of the brief, without a trailing blank line.

    Every zoned file with an importer gets a line naming its importers, those
    outside the zones first and marked, so the caps never hide them behind
    importers the leaf may already change. Files with an outside importer are
    listed first for the same reason.
    """
    lines = [
        "### Call sites (one level)",
        "",
        f"Modules that import each zoned Python file at `{ref}`: likely call sites to "
        "read before starting. One marked _(outside zones)_ is a likely change outside "
        "this leaf's zones, so add it to the zones first or say why it stays unchanged.",
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
    outside = {p for ps in found.values() for p in ps if not in_zones(zs, p, prefix)}
    targets = sorted(found, key=lambda t: (not outside.intersection(found[t]), t))
    lines += [_importer_line(t, found[t], outside) for t in targets[:FILE_CAP]]
    if len(targets) > FILE_CAP:
        lines.append(f"- _… and {len(targets) - FILE_CAP} more zoned files with importers_")
    return lines
