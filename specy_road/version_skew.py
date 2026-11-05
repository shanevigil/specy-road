"""Warn when the running specy-road is older than the version a project records."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from specy_road import __version__
from specy_road.agent_guide_block import AGENT_GUIDE
from specy_road.agents_md_block import AGENTS_MD
from specy_road.managed_block import HTML_COMMENT, _split
from specy_road.runtime_paths import git_root
from specy_road.toolkit_version import running_toolkit_version

__all__ = [
    "Launcher",
    "launchers_on_path",
    "print_install_report",
    "recorded_toolkit_version",
    "running_toolkit_version",
    "warn_if_blocks_written_by_other_version",
    "warn_if_running_version_older",
]

_VERSION = re.compile(r"^(\d+(?:\.\d+)*)(?:(a|b|rc)(\d+))?$", re.IGNORECASE)
_AGENTS_WRITTEN = re.compile(r"Written by specy-road (\S+)")
#: The block check's version: digits first, no trailing ``;``/``.`` (CLAUDE.md's line ends ``X;``).
_BLOCK_WRITTEN = re.compile(r"Written by specy-road (\d[\w.+-]*\w)")
_MINIMUM_LINE = re.compile(r"\(minimum (\S+)\)")
_PRE = {"a": 0, "b": 1, "rc": 2}


def _version_sort_key(version: str) -> tuple[int, ...]:
    stem = version.strip().split("+", 1)[0]
    m = _VERSION.match(stem)
    if not m:
        return (0,)
    release = tuple(int(p) for p in m.group(1).split("."))
    pre = m.group(2)
    return (*release, 3, 0) if pre is None else (*release, _PRE[pre.lower()], int(m.group(3)))


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except (OSError, UnicodeDecodeError):
        return ""


def recorded_toolkit_version(project: Path) -> tuple[str, str] | None:
    checkout = git_root(project) or project.resolve()
    candidates: list[tuple[str, str]] = []
    try:
        raw = json.loads(_read_text(checkout / ".specyrd" / "manifest.json") or "null")
    except json.JSONDecodeError:
        raw = None
    recorded = str(raw.get("specyrd_version") or "").strip() if isinstance(raw, dict) else ""
    if recorded:
        candidates.append((recorded, ".specyrd/manifest.json"))
    _before, block, _after = _split(_read_text(project / AGENTS_MD), HTML_COMMENT)
    if block:
        for pattern in (_AGENTS_WRITTEN, _MINIMUM_LINE):
            m = pattern.search(block)
            if m:
                candidates.append((m.group(1), AGENTS_MD))
    if not candidates:
        return None
    best = max(candidates, key=lambda item: _version_sort_key(item[0]))
    sources = sorted({where for ver, where in candidates if ver == best[0]})
    where = sources[0] if len(sources) == 1 else " and ".join(sources)
    return best[0], where


def warn_if_blocks_written_by_other_version(project: Path) -> None:
    """Warn for each managed block whose ``Written by specy-road X`` is not the running version.

    The manifest's ``specyrd_version`` can match while a block still carries an
    older version's text, so each block is checked on its own.
    """
    checkout = git_root(project) or project.resolve()
    for path, label in ((project / AGENTS_MD, AGENTS_MD), (checkout / AGENT_GUIDE, AGENT_GUIDE)):
        _before, block, _after = _split(_read_text(path), HTML_COMMENT)
        m = _BLOCK_WRITTEN.search(block or "")
        if m and m.group(1) != __version__:
            print(
                f"specy-road: warning — {label} block written by specy-road {m.group(1)}, "
                f"running {__version__}; run `specy-road upgrade`.",
                file=sys.stderr,
            )


def warn_if_running_version_older(project: Path) -> None:
    warn_if_blocks_written_by_other_version(project)
    found = recorded_toolkit_version(project)
    if found is None:
        return
    recorded, where = found
    if _version_sort_key(__version__) >= _version_sort_key(recorded):
        return
    print(
        f"specy-road: warning — specy-road {__version__} is running but this project records "
        f"{recorded} ({where}); an older install earlier on PATH is the usual cause. "
        "Check `which specy-road` and `specy-road --version`, then reinstall with "
        "`pipx install specy-road` or `uv tool install specy-road`.",
        file=sys.stderr,
    )


@dataclass(frozen=True)
class Launcher:
    """One ``specy-road`` or ``specyrd`` executable on ``PATH``."""

    name: str
    path: Path
    resolved: Path
    running: bool   # belongs to this interpreter's install


def _is_running_install(resolved: Path) -> bool:
    # Fully resolved on both sides: a raw PATH entry can hold ``..``, be relative,
    # or go through a symlinked prefix, and ``is_relative_to`` is only lexical.
    argv0 = Path(sys.argv[0]).resolve() if sys.argv and sys.argv[0] else None
    return resolved == argv0 or resolved.is_relative_to(Path(sys.prefix).resolve())


def launchers_on_path(path_env: str | None = None) -> list[Launcher]:
    """Every ``specy-road`` and ``specyrd`` on ``PATH``, in PATH order (like ``which -a``)."""
    found: list[Launcher] = []
    seen: set[Path] = set()
    raw = os.environ.get("PATH", "") if path_env is None else path_env
    for entry in raw.split(os.pathsep):
        entry = entry or os.getcwd()   # an empty PATH component is the current directory
        for name in ("specy-road", "specyrd"):
            cand = Path(entry) / name
            if cand in seen or not cand.is_file() or not os.access(cand, os.X_OK):
                continue
            seen.add(cand)
            resolved = cand.resolve()
            found.append(Launcher(name, cand, resolved, _is_running_install(resolved)))
    return found


def print_install_report(path_env: str | None = None) -> None:
    """``Install`` section: the launchers on PATH, and a warning when another install shadows this one."""
    launchers = launchers_on_path(path_env)
    print(f"Install: specy-road {__version__} running from {sys.prefix}")
    for ln in launchers:
        target = f" -> {ln.resolved}" if ln.resolved != ln.path else ""
        print(f"- {ln.name:<10} {ln.path}{target}{'  (running)' if ln.running else ''}")
    if not launchers:
        print("- no specy-road or specyrd on PATH")
    first = next((ln for ln in launchers if ln.name == "specy-road"), None)
    if first is not None and not first.running:
        print(
            f"specy-road: warning — the first specy-road on PATH ({first.resolved}) is not the running "
            f"install ({sys.prefix}). Check `which -a specy-road`, then reinstall or reorder PATH.",
            file=sys.stderr,
        )
