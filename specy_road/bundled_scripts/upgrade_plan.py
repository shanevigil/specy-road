"""The ``specy-road upgrade`` write plan: decided once, applied to the checkout or to a preview copy.

The refreshes decide per path: write, refuse a link out of the repository,
skip a file the kit does not own, follow ``CLAUDE.md -> AGENTS.md`` and write
the shared file twice, record ownership in ``.specyrd/manifest.json``. Those
decisions are made exactly once, by the real refresh code, in :func:`make_plan`.
It runs on a :class:`Mirror` of the checkout, which keeps every link, with each
link's resolved target mapped into the sandbox (a target outside the checkout
lands under the sandbox's ``outside/``, which is outside its repository too).
The plan is the difference that run made, expressed as the real paths it lands on.

:func:`apply_plan` writes the plan into the checkout (``upgrade``) or into a
second mirror (``upgrade --dry-run``, which then validates that copy). Neither
caller decides anything.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from specy_road import git_subprocess
from specy_road.ignore_report import scratch_git_env

State = tuple | None   # ("file", size, mtime_ns, mode) | ("link", text) | ("dir",) | ("other",) | None (absent)


def state(path: Path) -> State:
    """``path``'s own state, links not followed."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError:
        return ("other",)
    if stat.S_ISLNK(st.st_mode):
        return ("link", os.readlink(path))
    if stat.S_ISDIR(st.st_mode):
        return ("dir",)
    if stat.S_ISREG(st.st_mode):
        return ("file", st.st_size, st.st_mtime_ns, stat.S_IMODE(st.st_mode))
    return ("other",)


@dataclass(frozen=True)
class Entry:
    """One path of the plan.

    ``path`` is how the refresh names it (checkout-relative, or absolute outside
    the checkout); ``target`` is the real path it lands on, links followed;
    ``action`` is ``write`` / ``link`` / ``mkdir`` / ``remove``, or ``refuse`` /
    ``skip`` / ``fail`` for a path the refresh leaves as it is; ``data`` is the
    final bytes of a ``write``, ``link`` the final text of a ``link``; ``before``
    is the target's state when the plan was made.
    """

    path: str
    target: Path
    action: str
    data: bytes | None = None
    link: str | None = None
    mode: int | None = None
    before: State = None


@dataclass
class Plan:
    checkout: Path
    skip: Path
    entries: list[Entry]
    states: dict[str, State] = field(default_factory=dict)   # every path read into the mirror, as it was

    def changes(self) -> list[Entry]:
        return [e for e in self.entries if e.action in ("write", "link", "mkdir", "remove")]

    def changed_since(self) -> list[str]:
        """Paths read into the mirror whose state differs now, and paths new in the checkout."""
        now = {p: state(Path(p)) for p in self.states}
        for dirpath, dirs, names in os.walk(self.checkout):
            dirs[:] = [d for d in dirs if d != ".git" and Path(dirpath, d) != self.skip]
            for name in (n for n in dirs + names if n != ".git"):
                now.setdefault(str(Path(dirpath) / name), state(Path(dirpath) / name))
        changed = [p for p, st in now.items() if st != self.states.get(p)]
        return sorted(Path(p).relative_to(self.checkout).as_posix() if Path(p).is_relative_to(self.checkout) else p
                      for p in changed)


class Mirror:
    """The checkout under ``dest/repo``, without ``.git`` or ``skip``; link targets outside it under ``dest/outside``."""

    def __init__(self, checkout: Path, dest: Path, skip: Path) -> None:
        self.checkout, self.skip = checkout.resolve(), skip.resolve()
        self.dest = dest.resolve()
        self.repo, self.outside, self.hooks = self.dest / "repo", self.dest / "outside", self.dest / "no-hooks"
        self.init: git_subprocess.GitResult | None = None   # the scratch ``git init``, set by build()
        self.unreadable: list[str] = []   # repo-relative files copied empty: git add could not read them
        self.states: dict[str, State] = {}
        self._links: list[tuple[Path, Path]] = []
        self._hardlinks: dict[tuple[int, int], Path] = {}   # (dev, ino) -> first sandbox path for this inode

    def to_sandbox(self, real: Path) -> Path:
        if real.is_relative_to(self.checkout):
            return self.repo / real.relative_to(self.checkout)
        return self.outside / real.relative_to(real.anchor)

    def to_real(self, path: Path) -> Path:
        if path.is_relative_to(self.repo):
            return self.checkout / path.relative_to(self.repo)
        return Path("/") / path.relative_to(self.outside)

    def build(self) -> Mirror:
        self._hardlinks.clear()
        self.outside.mkdir(parents=True)
        self._copy_dir(self.checkout, self.repo)
        made: list[tuple[Path, Path, Path]] = []
        while self._links:
            src, dst = self._links.pop()
            text, real = os.readlink(src), Path(os.path.realpath(src))
            mapped = self.to_sandbox(real)
            dst.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(mapped if os.path.isabs(text) else text, dst)
            made.append((src, dst, mapped))
            self._ensure(real, mapped)
        for _src, dst, mapped in made:   # a relative text that resolves elsewhere here gets the mapped target
            if os.path.realpath(dst) != str(mapped):
                dst.unlink()
                os.symlink(mapped, dst)
        template = self.dest / "no-template"
        template.mkdir()
        self.hooks.mkdir()
        self.init = git_subprocess.run(["-c", f"core.hooksPath={self.hooks}", "init", "-q", f"--template={template}"],
                                       self.repo, env=scratch_git_env(self.dest))
        return self

    def _copy_dir(self, src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        self.states[str(src)] = ("dir",)
        try:
            entries = list(os.scandir(src))
        except OSError:
            entries = []
        for e in entries:
            s, d = Path(e.path), dst / e.name
            if e.name == ".git" or s == self.skip or (s == self.checkout and dst != self.repo):
                continue
            if e.is_symlink():
                self.states[str(s)] = state(s)
                self._links.append((s, d))
            elif e.is_dir(follow_symlinks=False):
                self._copy_dir(s, d)
            elif e.is_file(follow_symlinks=False):
                self._copy_file(s, d)
        with contextlib.suppress(OSError):
            shutil.copymode(src, dst)   # an unreadable or read-only directory stays so

    def _copy_file(self, src: Path, dst: Path) -> None:
        self.states[str(src)] = state(src)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            st = os.lstat(src)
            if stat.S_ISREG(st.st_mode):
                key = (st.st_dev, st.st_ino)
                if key in self._hardlinks:
                    os.link(self._hardlinks[key], dst)
                else:
                    shutil.copy2(src, dst)
                    self._hardlinks[key] = dst
            else:
                shutil.copy2(src, dst)
        except PermissionError:   # unreadable: unreadable in the sandbox too, so every reader fails alike
            dst.touch()
            dst.chmod(src.stat().st_mode & 0o777)
            if dst.is_relative_to(self.repo):
                self.unreadable.append(dst.relative_to(self.repo).as_posix())

    def _ensure(self, real: Path, mapped: Path) -> None:
        """Give a link target the mirror lacks (outside the checkout, or under ``skip``) its content."""
        if os.path.lexists(mapped) or ".git" in real.parts or not real.exists():
            return
        if real.is_dir():
            self._copy_dir(real, mapped)
        else:
            self._copy_file(real, mapped)

    def snapshot(self) -> dict[Path, State]:
        out: dict[Path, State] = {}
        for top in (self.repo, self.outside):
            for dirpath, dirs, names in os.walk(top):
                if Path(dirpath) == self.repo:
                    dirs[:] = [d for d in dirs if d != ".git"]
                for name in dirs + names:
                    path = Path(dirpath) / name
                    out[path] = state(path)
        return out


def _diff(mirror: Mirror, before: dict[Path, State], after: dict[Path, State], states: dict[str, State]) -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted(before.keys() | after.keys()):
        b, a = before.get(path), after.get(path)
        if b == a:
            continue
        real = mirror.to_real(path)
        shown = real.relative_to(mirror.checkout).as_posix() if real.is_relative_to(mirror.checkout) else str(real)
        common = {"path": shown, "target": real, "before": states.get(str(real))}
        if a is None:
            entries.append(Entry(action="remove", **common))
        elif a[0] == "dir":
            if b is None or b[0] != "dir":
                entries.append(Entry(action="mkdir", **common))
        elif a[0] == "link":
            text = a[1]
            if os.path.isabs(text):
                text = str(mirror.to_real(Path(text)))
            entries.append(Entry(action="link", link=text, **common))
        elif a[0] == "file":
            entries.append(Entry(action="write", data=path.read_bytes(), mode=a[3], **common))
    return entries


def make_plan(checkout: Path, project: Path, refresh: Callable[[Path, Path], dict[str, str]]) -> Plan:
    """Run ``refresh(project, checkout)`` once, on a mirror; the plan is what it wrote and what it declined.

    ``refresh`` returns ``{checkout-relative path: refuse | skip | fail}``.
    Its output is printed with the mirror's paths given as the checkout's.
    """
    checkout = checkout.resolve()
    with tempfile.TemporaryDirectory(prefix="specy-road-upgrade-plan-") as tmp:
        mirror = Mirror(checkout, Path(tmp), project / "work").build()
        before = mirror.snapshot()
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                declined = refresh(mirror.to_sandbox(project.resolve()), mirror.repo)
        except OSError as e:   # name the checkout's path, not the mirror's
            e.filename = e.filename and str(e.filename).replace(str(mirror.repo), str(checkout))
            raise
        finally:
            for buf, stream in ((out, sys.stdout), (err, sys.stderr)):
                stream.write(buf.getvalue().replace(str(mirror.repo), str(checkout)))
                stream.flush()
        entries = _diff(mirror, before, mirror.snapshot(), mirror.states)
        for rel, action in sorted(declined.items()):
            real = Path(os.path.realpath(checkout / rel))
            entries.append(Entry(path=rel, target=real, action=action, before=mirror.states.get(str(real))))
        return Plan(checkout, mirror.skip, entries, mirror.states)


def conflicts(plan: Plan) -> list[str]:
    """Paths whose state changed since the plan was made: applying over them would lose that change."""
    return [e.path for e in plan.changes() if state(e.target) != e.before]


def _replaces(e: Entry) -> bool:
    """Whether what is at the target now must go before ``e`` is made."""
    kind = e.before[0] if e.before else None
    return kind is not None and (e.action in ("remove", "link")
                                 or (e.action == "write" and kind != "file")
                                 or (e.action == "mkdir" and kind != "dir"))


def apply_plan(plan: Plan, locate: Callable[[Path], Path] = lambda p: p) -> None:
    """Make every change in ``plan`` at ``locate(real path)``: removals deepest first, then directories, then the rest."""
    changes = plan.changes()
    for e in sorted((e for e in changes if _replaces(e)), key=lambda e: -len(e.target.parts)):
        where = locate(e.target)
        if e.before and e.before[0] == "dir":
            where.rmdir()
        else:
            where.unlink()
    for e in sorted((e for e in changes if e.action == "mkdir"), key=lambda e: len(e.target.parts)):
        locate(e.target).mkdir(exist_ok=True)
    for e in changes:
        where = locate(e.target)
        if e.action == "link" and e.link is not None:
            os.symlink(str(locate(Path(e.link))) if os.path.isabs(e.link) else e.link, where)
        elif e.action == "write":
            where.write_bytes(e.data or b"")
            if e.mode is not None and (e.before is None or e.before[0] != "file" or e.before[3] != e.mode):
                where.chmod(e.mode)
