"""Tests at risk: the Python test files that import a leaf's code, at any depth.

Backs ``specy-road impact`` and the **Tests at risk** sections of the executor
prompt and the review packet. An import graph is built with ``ast`` over every
``.py`` file in the git tree at one commit (relative imports resolved), then
walked backwards from the changed modules, or the modules under the touch zones,
to test files. Git objects only, so two runs on the same commits agree byte for
byte. Advisory: it never decides a gate.

Paths are git-root relative, like ``specy-road integrity``; touch zones are
matched against the project-relative form, like the packet's changed paths.
"""

from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from specy_road.finish_implementation_check import zone_matches
from specy_road.git_changed_paths import diff_paths
from specy_road.git_subprocess import git_stdout
from specy_road.runtime_paths import project_prefix, rebase_to_project

ALL = "ALL"
SECTION_CAP = 50   # paths listed in the prompt and packet sections; the rest are counted


@dataclass(frozen=True)
class Impact:
    tests: tuple[str, ...] = ()
    all_tests: bool = False   # a conftest.py changed: every test is at risk
    not_analysed: int = 0     # changed files that are not Python

    def lines(self) -> list[str]:
        """What ``specy-road impact`` prints."""
        if self.all_tests:
            return [ALL]
        tail = [f"not analysed: {self.not_analysed} files"] if self.not_analysed else []
        return [*self.tests, *tail]


def is_test_file(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def impact_for_diff(root: Path, base: str, ref: str) -> Impact | None:
    """Tests importing a module changed between ``base`` and ``ref``; ``None`` when git cannot answer."""
    changed = diff_paths(root, f"{base}...{ref}")
    if changed is None:
        return None
    if any(PurePosixPath(p).name == "conftest.py" for p in changed):
        return Impact(all_tests=True)
    files = python_sources(root, ref)
    if files is None:
        return None
    targets = {p for p in changed if p.endswith(".py")}
    return Impact(tests_importing(files, targets), not_analysed=len(changed) - len(targets))


def impact_for_zones(root: Path, ref: str, zones: list[str]) -> Impact | None:
    """Tests importing a module under ``zones`` at ``ref``; ``None`` when git cannot answer."""
    files = python_sources(root, ref)
    if files is None:
        return None
    prefix = project_prefix(root)
    zs = [z.strip().strip("/") for z in zones if isinstance(z, str) and z.strip()]
    targets = {p for p in files if any(zone_matches(z, rebase_to_project(p, prefix) or p) for z in zs)}
    return Impact(tests_importing(files, targets))


def python_sources(root: Path, ref: str) -> dict[str, str] | None:
    """``{git-root path: source}`` for every ``.py`` blob at ``ref``."""
    out = git_stdout(["ls-tree", "-r", "--full-tree", "-z", ref], root)
    if out is None:
        return None
    blobs: dict[str, str] = {}
    for rec in filter(None, out.split("\0")):
        meta, path = rec.split("\t", 1)
        mode, kind, sha = meta.split()
        if kind == "blob" and mode != "120000" and path.endswith(".py"):
            blobs[path] = sha
    texts = _read_blobs(root, sorted(set(blobs.values())))
    if texts is None:
        return None
    return {p: texts[sha] for p, sha in blobs.items()}


def _read_blobs(root: Path, shas: list[str]) -> dict[str, str] | None:
    """Blob contents by id, through one ``git cat-file --batch``."""
    if not shas:
        return {}
    try:
        r = subprocess.run(["git", "cat-file", "--batch"], cwd=root, input="\n".join(shas).encode() + b"\n",
                           capture_output=True, check=False)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    data, pos, texts = r.stdout, 0, {}
    for sha in shas:
        eol = data.index(b"\n", pos)
        size = int(data[pos:eol].split()[2])
        texts[sha] = data[eol + 1:eol + 1 + size].decode("utf-8", errors="replace")
        pos = eol + 1 + size + 1
    return texts


def tests_importing(files: dict[str, str], targets: set[str]) -> tuple[str, ...]:
    """Sorted test files in ``files`` that import a ``targets`` file, through any chain of imports.

    A target missing from ``files`` (deleted at ``ref``) keeps its module names,
    so a test that still imports it is listed.
    """
    paths = set(files) | targets
    inits = {p for p in paths if PurePosixPath(p).name == "__init__.py"}
    by_name: dict[str, set[str]] = {}
    for p in paths:
        for name in module_names(p, inits):
            by_name.setdefault(name, set()).add(p)
    importers: dict[str, set[str]] = {}
    for p in sorted(files):
        for name in imported_names(files[p], _package(p, inits)):
            for dep in by_name.get(name, ()):
                importers.setdefault(dep, set()).add(p)
    seen: set[str] = set()
    stack = sorted(targets)
    while stack:
        for p in importers.get(stack.pop(), ()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return tuple(sorted(p for p in seen if is_test_file(p)))


def _parts(path: str, inits: set[str]) -> tuple[list[str], int]:
    """``path``'s dotted parts and where its import name starts (the topmost package with ``__init__``)."""
    parts = path[: -len(".py")].split("/")
    start = len(parts) - 1
    while start > 0 and "/".join(parts[:start]) + "/__init__.py" in inits:
        start -= 1
    return parts, start


def module_names(path: str, inits: set[str]) -> set[str]:
    """Names ``path`` can be imported by: from its top package, and from the git root."""
    parts, start = _parts(path, inits)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return {n for n in (".".join(parts[start:]), ".".join(parts)) if n}


def _package(path: str, inits: set[str]) -> list[str]:
    """The package a relative import in ``path`` starts from."""
    parts, start = _parts(path, inits)
    return parts[start:-1]


def imported_names(source: str, package: list[str]) -> set[str]:
    """Every module name ``source`` imports, with each parent package (they run on import too)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return set()
    mods: list[list[str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name.split(".") for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(package):
                    continue
                base = package[: len(package) - node.level + 1]
            else:
                base = []
            mod = base + (node.module.split(".") if node.module else [])
            mods.append(mod)
            mods += [mod + [a.name] for a in node.names if a.name != "*"]
    return {".".join(m[:i]) for m in mods for i in range(1, len(m) + 1)}


def section_lines(impact: Impact | None, *, intro: str, full_cmd: str) -> list[str]:
    """``## Tests at risk`` for the prompt and the packet: at most :data:`SECTION_CAP` paths."""
    lines = ["## Tests at risk", "", intro, ""]
    if impact is None:
        return lines + ["_(cannot compute: git could not read the tree)_", ""]
    if impact.all_tests:
        return lines + [f"- `{ALL}`: a `conftest.py` changed, so every test is at risk", ""]
    shown = impact.tests[:SECTION_CAP]
    lines += [f"- `{p}`" for p in shown] or ["_none found_"]
    if len(impact.tests) > len(shown):
        lines.append(f"- _… and {len(impact.tests) - len(shown)} more (`{full_cmd}` lists them all)_")
    if impact.not_analysed:
        lines.append(f"- not analysed: {impact.not_analysed} files")
    return lines + [""]
