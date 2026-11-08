"""The ``specy-road upgrade`` write plan: decided once, applied to the checkout or to a preview copy.

The refreshes decide per path: write, refuse a link out of the repository,
skip a file the kit does not own, follow ``CLAUDE.md -> AGENTS.md`` and write
the shared file twice, record ownership in ``.specyrd/manifest.json``. Those
decisions are made exactly once, by the real refresh code, in :func:`make_plan`.
It runs on a :class:`Mirror` of the checkout, which keeps every link, with each
link's resolved target mapped into the sandbox (a target outside the checkout
lands under the sandbox's ``outside/``, which is outside its repository too).
The plan is the difference that run made, expressed as the real paths it lands on.
The mirror holds tracked files, untracked files git does not ignore, and any
extra paths the caller names (what the refreshes read, including a generated
file the preview compares). Gitignored files are not copied. A symlink does
not bring an ignored target in: that path stays out of the mirror. A directory
that cannot be searched is left out too, so the copy does not stop on it. A
target outside the checkout is still copied, so a link that leaves the checkout
resolves as before.

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
from specy_road.bundled_scripts.upgrade_generated import checked, scratch_environ
from specy_road.ignore_report import Match, print_matches, scratch_git_env

State = tuple | None   # ("file", size, mtime_ns, mode) | ("link", text) | ("dir",) | ("other",) | None (absent)

_COPY_LINE = ("copying tracked and untracked files into a temporary directory; "
              "ignored files are not copied")


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
        """Paths read into the mirror whose state differs now, and new non-ignored paths in the checkout."""
        changed = [p for p in self.states if state(Path(p)) != self.states[p]]
        changed.extend(_appeared(self.checkout, self.skip, self.states))
        return sorted(Path(p).relative_to(self.checkout).as_posix() if Path(p).is_relative_to(self.checkout) else p
                      for p in changed)


def _ancestors(rels: set[str]) -> set[str]:
    """Every parent directory of ``rels``, as checkout-relative posix paths."""
    found: set[str] = set()
    for rel in rels:
        parts = Path(rel).parts
        for i in range(1, len(parts)):
            found.add("/".join(parts[:i]))
    return found


def _skipped_dir(path: Path) -> bool:
    """A real directory the copy does not enter: it contains a repository, or it cannot be searched.

    A symlink is not this directory. ``path/.git`` raises ``OSError`` when ``path`` cannot be listed,
    which is the same reason to leave it out: the copy would stop, and a later snapshot cannot list it either.
    """
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        return (path / ".git").exists()
    except OSError:
        return True


def _ignored(checkout: Path, rels: list[str], env: dict[str, str] | None) -> set[str]:
    """The members of ``rels`` that git ignores in ``checkout``. A git failure raises :class:`GitFailed`.

    Plain ``check-ignore`` (not ``-v``) prints only paths whose last matching rule ignores them, so a path
    a later ``!`` rule re-includes is not in the set.
    """
    found: set[str] = set()
    for start in range(0, len(rels), 200):
        chunk = rels[start:start + 200]
        if not chunk:
            continue
        result = git_subprocess.run(
            ["-c", "core.fsmonitor=", "-c", "core.quotepath=false", "check-ignore", "--", *chunk],
            checkout, env=env)
        if result.code not in (0, 1):
            checked(result, "check-ignore", "the checkout")
        found.update(result.out.splitlines())
    return found


def _copy_keeping_mode(src: str, dst: str) -> None:
    """``copy2``, or an empty file of the same mode when ``src`` cannot be read."""
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        Path(dst).touch()
        Path(dst).chmod(Path(src).stat().st_mode & 0o777)


def snapshot_outside(src: Path, dst: Path) -> None:
    """Copy a built mirror's ``outside`` tree, without ``.git``, so a dry run can reuse it."""
    shutil.copytree(src, dst, symlinks=True, copy_function=_copy_keeping_mode,
                    ignore=lambda _dir, names: [n for n in names if n == ".git"])


def _retarget(root: Path, old: Path, new: Path) -> None:
    """Point absolute links that named ``old`` at ``new``; relative links stay."""
    old_s, new_s = str(old), str(new)
    for dirpath, dirs, names in os.walk(root, followlinks=False):
        for name in dirs + names:
            path = Path(dirpath) / name
            if not path.is_symlink():
                continue
            text = os.readlink(path)
            if text == old_s or text.startswith(old_s + os.sep):
                path.unlink()
                os.symlink(new_s + text[len(old_s):], path)


def _appeared(checkout: Path, skip: Path, states: dict[str, State]) -> list[str]:
    """Checkout paths absent from ``states`` that are not ignored, under ``skip``, or inside a nested repository."""
    recorded = {Path(p).relative_to(checkout).as_posix() for p in states if Path(p).is_relative_to(checkout)}
    ancestors = _ancestors(recorded)
    found: list[str] = []
    for dirpath, dirs, names in os.walk(checkout):
        here = Path(dirpath)
        children = [here / name for name in dirs + names if name != ".git" and here / name != skip]
        rel_of = {path: path.relative_to(checkout).as_posix() for path in children}
        ignored = _ignored(checkout, list(rel_of.values()), None)
        descend: list[str] = []
        for path in children:
            rel = rel_of[path]
            if _skipped_dir(path):
                continue
            pruned = (path.is_dir() and not path.is_symlink() and rel not in ancestors
                      and rel not in recorded and rel in ignored)
            if pruned:
                continue
            if path.is_dir() and not path.is_symlink():
                descend.append(path.name)
            if str(path) not in states and rel not in ignored:
                found.append(str(path))
        dirs[:] = descend
    return found


class Mirror:
    """The filesystem as the checkout sees it, under ``dest/outside``: the checkout at ``outside/<its absolute path>``.

    The checkout is copied without ``.git`` or ``skip``: tracked files, untracked
    files git does not ignore, and extra paths the caller names. A nested
    repository is not copied. Every link keeps its own text, one hop: a relative
    text verbatim, an absolute one with ``outside`` put in front. So a chain, a
    target under a linked directory, or a ``..`` that climbs out and back resolves
    in the mirror exactly as in the checkout. A target outside the checkout, or
    under ``skip`` and not itself gitignored, is copied to its real path's
    place, and a link whose text names that place another way reaches it
    through one more link, which only a path already outside the checkout can
    cross. A gitignored checkout path, a nested repository, and a directory that
    cannot be searched are not copied for a link that points at them. A text whose ``..`` climbs past
    ``/`` (where the checkout stops) would climb out of the mirror here, so
    :meth:`build` gives that one link its target's place, absolutely; nothing
    is ever made outside ``dest``.

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
        self._git_env: dict[str, str] | None = None

    def to_sandbox(self, real: Path) -> Path:
        return self.outside / real.relative_to(real.anchor)

    def to_real(self, path: Path) -> Path:
        return Path("/") / path.relative_to(self.outside)

    def real_text(self, text: str) -> str:
        """``text`` with the mirror's paths given as the real ones (``outside/x`` is ``/x``)."""
        return text.replace(str(self.outside), "")

    def build(self, *, git_env: dict[str, str] | None = None, extra: set[str] | None = None) -> Mirror:
        """Copy the checkout and ``git init`` the copy; :class:`GitFailed` if git could not, for every mirror alike."""
        self._hardlinks.clear()
        self._git_env = git_env
        self.outside.mkdir(parents=True)
        print(_COPY_LINE, flush=True)
        self._copy_selected(extra or set())
        self._resolve_links()
        self._init_git()
        return self

    def reuse(self, staging: Path, source: Mirror) -> Mirror:
        """A second mirror from ``staging`` (a snapshot of ``source``), not from another checkout walk."""
        self._hardlinks.clear()
        self._git_env = source._git_env
        self.outside.mkdir(parents=True)
        shutil.copytree(staging, self.outside, symlinks=True, dirs_exist_ok=True, copy_function=_copy_keeping_mode)
        _retarget(self.outside, source.outside, self.outside)
        self.unreadable = [self.outside / path.relative_to(source.outside) for path in source.unreadable]
        self._init_git()
        return self

    def _init_git(self) -> None:
        template = self.dest / "no-template"
        template.mkdir()
        self.hooks.mkdir()
        checked(git_subprocess.run(["-c", f"core.hooksPath={self.hooks}", "init", "-q", f"--template={template}"],
                                   self.repo, env=scratch_git_env(self.dest)), "init")

    def _resolve_links(self) -> None:
        made: list[tuple[Path, Path]] = []
        while True:
            while self._links:   # every link of a round first, so content never lands where a link belongs
                batch, self._links = self._links, []
                for src, dst in batch:
                    text = os.readlink(src)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(self.to_sandbox(Path(text)) if os.path.isabs(text) else text, dst)   # its own text, one hop
                for src, _dst in batch:
                    self._ensure(Path(os.path.realpath(src)), self.to_sandbox(src.parent / os.readlink(src)))
                made += batch
            escaping = [(src, dst) for src, dst in made if not self._inside(dst)]
            if not escaping:
                break
            for src, dst in escaping:
                self._contain(src, dst)

    def _copy_selected(self, extra: set[str]) -> None:
        """Copy tracked files, untracked files git does not ignore, and ``extra`` paths that are present."""
        listed = {rel.rstrip("/") for rel in self._listed()}
        present = {rel for rel in extra if (self.checkout / rel).exists() or (self.checkout / rel).is_symlink()}
        selected = self._without_skipped(listed | present | self._link_parents(listed | present))
        self.repo.mkdir(parents=True, exist_ok=True)
        self.states[str(self.checkout)] = ("dir",)
        with contextlib.suppress(OSError):
            shutil.copymode(self.checkout, self.repo)
        self._walk(self.checkout, self.repo, selected, _ancestors(selected))

    def _listed(self) -> set[str]:
        result = git_subprocess.run(
            ["-c", "core.fsmonitor=", "-c", "core.quotepath=false", "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"],
            self.checkout, env=self._git_env)
        checked(result, "ls-files", "the checkout")
        return {rel for rel in result.out.split("\0") if rel}

    def _without_skipped(self, rels: set[str]) -> set[str]:
        skip = self._skip_rel()
        kept: set[str] = set()
        for rel in rels:
            path = self.checkout / rel
            if skip and (rel == skip or rel.startswith(skip + "/")):
                continue
            # A symlink to a nested repository is the link, not the repository: keep the link, leave the target out.
            if self._under_nested(path) or _skipped_dir(path):
                continue
            kept.add(rel)
        return kept

    def _skip_rel(self) -> str:
        try:
            rel = self.skip.relative_to(self.checkout).as_posix()
        except ValueError:
            return ""
        return "" if rel == "." else rel

    def _under_nested(self, path: Path) -> bool:
        for parent in path.parents:
            if parent == self.checkout:
                return False
            if _skipped_dir(parent):
                return True
        return False

    def _link_parents(self, rels: set[str]) -> set[str]:
        found: set[str] = set()
        for rel in rels:
            parts = Path(rel).parts
            for i in range(1, len(parts)):
                parent = "/".join(parts[:i])
                if (self.checkout / parent).is_symlink():
                    found.add(parent)
        return found

    def _walk(self, src: Path, dst: Path, selected: set[str], ancestors: set[str]) -> None:
        try:
            entries = list(os.scandir(src))
        except OSError:
            return
        rel_of = {e: Path(e.path).relative_to(self.checkout).as_posix() for e in entries if e.name != ".git"}
        ignored = _ignored(self.checkout, list(rel_of.values()), self._git_env)
        for entry in entries:
            source, dest = Path(entry.path), dst / entry.name
            if entry.name == ".git" or source == self.skip or (source == self.checkout and dst != self.repo):
                continue
            rel = rel_of[entry]
            if entry.is_symlink():
                if rel in selected:
                    self.states[str(source)] = state(source)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    self._links.append((source, dest))
                continue
            if entry.is_dir(follow_symlinks=False):
                if _skipped_dir(source):
                    continue
                if rel not in selected and rel not in ancestors and rel in ignored:
                    continue
                dest.mkdir(parents=True, exist_ok=True)
                self.states[str(source)] = ("dir",)
                with contextlib.suppress(OSError):
                    shutil.copymode(source, dest)
                self._walk(source, dest, selected, ancestors)
                continue
            if entry.is_file(follow_symlinks=False) and rel in selected:
                self._copy_file(source, dest)

    def _copy_dir(self, src: Path, dst: Path) -> None:
        dst.mkdir(parents=True, exist_ok=True)
        self.states[str(src)] = ("dir",)
        try:
            entries = list(os.scandir(src))
        except OSError:
            entries = []
        for e in entries:
            s, d = Path(e.path), dst / e.name
            if e.name == ".git" or s == self.skip or (s == self.checkout and dst != self.repo) or self._left_out(s):
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
        where = Path(os.path.realpath(mapped))   # where the text lands in the mirror; out of it, build contains the link
        if not where.is_relative_to(self.outside):
            return
        home = self._place(real)
        if os.path.lexists(home) and not os.path.lexists(where):   # the text names the place another way
            where.parent.mkdir(parents=True, exist_ok=True)
            os.symlink(home, where)

    def _inside(self, path: Path) -> bool:
        return Path(os.path.realpath(path)).is_relative_to(self.outside)

    def _contain(self, src: Path, dst: Path) -> None:
        """Point ``dst``, whose text climbs out of the mirror, at its real target's place in it.

        A ``..`` past ``/`` stays at ``/`` in the checkout but climbs above
        ``outside`` here, so such a text is given as that place, absolutely.
        """
        real = Path(os.path.realpath(src))
        home = self.to_sandbox(real)
        if os.readlink(dst) == str(home):   # contained once and still out: refuse rather than reach outside
            raise safe_write.SafeWriteError(f"{src} resolves out of the upgrade's copy; nothing was written")
        dst.unlink()
        os.symlink(home, dst)
        if os.path.exists(src) and ".git" not in real.parts:
            self._place(real)

    def _place(self, real: Path) -> Path:
        """``real``'s place in the mirror. A checkout path the copy omits is not created."""
        home = self.to_sandbox(real)
        if not os.path.lexists(home) and not self._left_out(real):
            (self._copy_dir if real.is_dir() else self._copy_file)(real, home)
        return home

    def _left_out(self, real: Path) -> bool:
        """An in-checkout path the selective copy omits: gitignored, a nested repository, or unsearchable.

        A link that points at one does not bring it in. A path outside the checkout is not omitted here.
        """
        if not real.is_relative_to(self.checkout) or real == self.checkout:
            return False
        rel = real.relative_to(self.checkout)
        if ".git" in rel.parts or _skipped_dir(real) or self._under_nested(real):
            return True
        text = rel.as_posix()
        return text in _ignored(self.checkout, [text], self._git_env)

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


def make_plan(checkout: Path, project: Path, refresh: Callable[[Path, Path], dict[str, str]],
              *, defer_ignore: bool = False, mirror: Mirror | None = None,
              git_env: dict[str, str] | None = None, extra: set[str] | None = None) -> Plan:
    """Run ``refresh(project, checkout)`` once, on a mirror; the plan is what it wrote and what it declined.

    ``refresh`` returns ``{checkout-relative path: refuse | error | skip | fail}``.
    Its output is printed with the mirror's paths given as the checkout's.
    Only the refresh runs in the mirror's scratch environment (no ``GIT_``
    variable, no global or system config). When it returns, that isolation is
    the caller's again, before the plan is applied in the checkout.

    The mirror's git index is empty, so its ignore note does not describe the
    checkout. With ``defer_ignore`` that note is not printed (the caller reports
    from the checkout around the write). Otherwise it is labelled an estimate.
    ``mirror`` is a copy already built; otherwise one is built here. ``extra``
    paths are copied even when git ignores them.
    """
    if mirror is None:
        checkout = checkout.resolve()
        with tempfile.TemporaryDirectory(prefix="specy-road-upgrade-plan-") as tmp:
            built = Mirror(checkout, Path(tmp), project / "work").build(git_env=git_env, extra=extra)
            return _refresh_on(built, project, refresh, defer_ignore=defer_ignore)
    return _refresh_on(mirror, project, refresh, defer_ignore=defer_ignore)


def _refresh_on(mirror: Mirror, project: Path, refresh: Callable[[Path, Path], dict[str, str]],
                *, defer_ignore: bool) -> Plan:
    """The plan from running ``refresh`` on ``mirror``."""
    checkout = mirror.checkout
    before = mirror.snapshot()
    out, err = io.StringIO(), io.StringIO()
    real = mirror.real_text
    import specy_road.agent_ignores as agent_ignores

    def notice(matches: list[Match] | str, *, estimated: bool) -> None:
        """Label the mirror's note as an estimate. Its index is empty, whatever ``estimated`` the mirror passed."""
        if not defer_ignore:
            print_matches(matches, estimated=True)

    saved_notice = agent_ignores.print_matches
    agent_ignores.print_matches = notice
    try:
        with (
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
            scratch_environ(mirror.dest),
        ):
            declined = refresh(mirror.to_sandbox(project.resolve()), mirror.repo)
    except (OSError, RuntimeError) as e:   # a symlink loop in the mirror is the checkout's: refused, named there
        refusal = safe_write.loop_refusal(e)
        if refusal is None and not isinstance(e, OSError):
            raise
        raise _named_in_checkout(refusal or e, real) from e
    finally:
        agent_ignores.print_matches = saved_notice
        for buf, stream in ((out, sys.stdout), (err, sys.stderr)):
            stream.write(real(buf.getvalue()))
            stream.flush()
    entries = _diff(mirror, before, mirror.snapshot(), mirror.states)
    for rel, action in sorted(declined.items()):
        landed = Path(os.path.realpath(checkout / rel))
        entries.append(Entry(path=rel, target=landed, action=action, before=mirror.states.get(str(landed))))
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
