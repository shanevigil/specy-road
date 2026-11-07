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

from specy_road import git_subprocess, safe_write
from specy_road.bundled_scripts.upgrade_generated import checked
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
    ``action`` is ``write`` / ``link`` / ``mkdir`` / ``remove``, or ``refuse`` / ``error`` /
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
    """The filesystem as the checkout sees it, under ``dest/outside``: the checkout at ``outside/<its absolute path>``.

    The checkout is copied without ``.git`` or ``skip``, and every link keeps
    its own text, one hop: a relative text verbatim, an absolute one with
    ``outside`` put in front. So a chain, a target under a linked directory, or
    a ``..`` that climbs out and back resolves in the mirror exactly as in the
    checkout. Content the copy lacks (a target out of the checkout, or under
    ``skip``) is copied to its real path's place, and a link whose text names
    that place another way reaches it through one more link, which only a path
    already outside the checkout can cross.

    Invariant: ``safe_write`` and the skills-link rule see the same link shapes
    here as in the checkout, so ``upgrade``, ``upgrade --dry-run`` and
    ``refresh-stubs`` give the same verdict for the same checkout.
    """

    def __init__(self, checkout: Path, dest: Path, skip: Path) -> None:
        self.checkout, self.skip = checkout.resolve(), skip.resolve()
        self.dest = dest.resolve()
        self.outside, self.hooks = self.dest / "outside", self.dest / "no-hooks"
        self.repo = self.to_sandbox(self.checkout)
        self.unreadable: list[Path] = []   # files copied empty: git add could not read them
        self.states: dict[str, State] = {}
        self._links: list[tuple[Path, Path]] = []
        self._hardlinks: dict[tuple[int, int], Path] = {}   # (dev, ino) -> first sandbox path for this inode

    def to_sandbox(self, real: Path) -> Path:
        return self.outside / real.relative_to(real.anchor)

    def to_real(self, path: Path) -> Path:
        return Path("/") / path.relative_to(self.outside)

    def real_text(self, text: str) -> str:
        """``text`` with the mirror's paths given as the real ones (``outside/x`` is ``/x``)."""
        return text.replace(str(self.outside), "")

    def build(self) -> Mirror:
        """Copy the checkout and ``git init`` the copy; :class:`GitFailed` if git could not, for every mirror alike."""
        self._hardlinks.clear()
        self.outside.mkdir(parents=True)
        self._copy_dir(self.checkout, self.repo)
        while self._links:   # every link of a round first, so content never lands where a link belongs
            batch, self._links = self._links, []
            for src, dst in batch:
                text = os.readlink(src)
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.symlink(self.to_sandbox(Path(text)) if os.path.isabs(text) else text, dst)   # its own text, one hop
            for src, _dst in batch:
                self._ensure(Path(os.path.realpath(src)), self.to_sandbox(src.parent / os.readlink(src)))
        template = self.dest / "no-template"
        template.mkdir()
        self.hooks.mkdir()
        checked(git_subprocess.run(["-c", f"core.hooksPath={self.hooks}", "init", "-q", f"--template={template}"],
                                   self.repo, env=scratch_git_env(self.dest)), "init")
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
            self.unreadable.append(dst)

    def _ensure(self, real: Path, mapped: Path) -> None:
        """Give a link's target (``mapped``, as its text names it) content when the mirror lacks it.

        The content goes to the real path's place; ``mapped`` naming it another
        way gets a link there.
        """
        if os.path.lexists(mapped) or ".git" in real.parts or not real.exists():
            return
        home = self._place(real)
        if not os.path.lexists(mapped):   # the text names the place another way (a ``..``, an alias)
            mapped.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(home, mapped)

    def _place(self, real: Path) -> Path:
        """``real``'s place in the mirror, with its content copied there when missing."""
        home = self.to_sandbox(real)
        if not os.path.lexists(home):
            (self._copy_dir if real.is_dir() else self._copy_file)(real, home)
        return home

    def snapshot(self) -> dict[Path, State]:
        out: dict[Path, State] = {}
        for dirpath, dirs, names in os.walk(self.outside):
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


def _named_in_checkout(e: OSError, real: Callable[[str], str]) -> OSError:
    """``e`` naming the checkout's paths, not the mirror's: a ``SafeWriteError``'s are in its message, another's in its filename."""
    if isinstance(e, safe_write.SafeWriteError):
        return safe_write.SafeWriteError(real(str(e)))
    e.filename = e.filename and real(str(e.filename))
    return e


def make_plan(checkout: Path, project: Path, refresh: Callable[[Path, Path], dict[str, str]]) -> Plan:
    """Run ``refresh(project, checkout)`` once, on a mirror; the plan is what it wrote and what it declined.

    ``refresh`` returns ``{checkout-relative path: refuse | error | skip | fail}``.
    Its output is printed with the mirror's paths given as the checkout's.
    """
    checkout = checkout.resolve()
    with tempfile.TemporaryDirectory(prefix="specy-road-upgrade-plan-") as tmp:
        mirror = Mirror(checkout, Path(tmp), project / "work").build()
        before = mirror.snapshot()
        out, err = io.StringIO(), io.StringIO()
        real = mirror.real_text
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                declined = refresh(mirror.to_sandbox(project.resolve()), mirror.repo)
        except (OSError, RuntimeError) as e:   # a symlink loop in the mirror is the checkout's: refused, named there
            refusal = safe_write.loop_refusal(e)
            if refusal is None and not isinstance(e, OSError):
                raise
            raise _named_in_checkout(refusal or e, real) from e
        finally:
            for buf, stream in ((out, sys.stdout), (err, sys.stderr)):
                stream.write(real(buf.getvalue()))
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


def check_changes(plan: Plan) -> None:
    """Raise ``SafeWriteError`` naming each change whose real target is not under the checkout by real directories.

    A refresh that wrote through a link out of the checkout made its change at
    the link's target, which this names; so a refresher that bypasses the rule
    still never reaches outside. Declined entries are not changes: their
    refresher already refused and reported them.
    """
    found = [why for e in plan.changes() if (why := safe_write.refused(plan.checkout, e.target, None))]
    if found:
        raise safe_write.SafeWriteError(f"{'; '.join(found)}; nothing was written")


def apply_plan(plan: Plan, locate: Callable[[Path], Path] = lambda p: p) -> None:
    """Make every change in ``plan`` at ``locate(real path)``: removals deepest first, then directories, then the rest.

    Every change's real target is checked by the safe-write rule first; any
    refusal raises ``SafeWriteError`` naming each path, and nothing is applied
    (neither to the checkout nor to ``locate``'s copy).
    """
    check_changes(plan)
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
