"""Steering files: what an executor can write that trusted code outside it later reads or runs (M21.7).

An unattended executor works in a linked worktree, and some files it can write are read or run later by
something it does not control: the coordinator's harness (its config and hooks), git (hooks and
``core.fsmonitor`` / ``core.hooksPath`` in the common git dir, which every worktree of the repository shares),
the coordinator's shell (startup files, the interpreter ``env_setup.link`` shares), and the toolkit's own gate
(``roadmap/orchestration.yaml`` and the other policy files, other leaves' registry rows, ``work/reviews/``).
This module holds the one list (documented in docs/orchestration-steering-files.md, linked from
docs/orchestration-workers.md) and the per-turn watch; :mod:`specy_road.steering_gate` holds its two other uses:

- the snapshots (:func:`git_snapshot`, :func:`file_snapshot`) that the post-run check
  (:class:`~specy_road.worker_turn_check.SteeringWatch`) takes per worker turn, in the worktree and in the main
  checkout, and compares as ``steering_file`` findings. The git half is read from the filesystem only, so it is
  compared before any post-turn git command runs.
- :func:`~specy_road.steering_gate.steering_or_exit`: finish's refusal of a branch that changes an in-tree steering path no touch zone
  names exactly.
- :func:`~specy_road.steering_gate.claude_denies`: per-file ``--disallowedTools`` rules for a Claude Code executor's launch and resume.

Detection only: nothing here restores a changed file. Paths compare project-relative, as ``zone_matches``
does, and one real path is stored once.

**One rule for any input that cannot be read** (:func:`guarded`): every per-file and per-directory step (listing,
reading, decoding, parsing, hashing) runs on its own, and any exception there (invalid UTF-8, a permission error,
a dangling link or a link loop, malformed YAML, a file over :data:`MAX_PARSE_BYTES`, a file gone mid-read) records
that path and its class as unreadable (an ``error:`` value) and the snapshot goes on with every other path. The
comparison reports each such path as a ``check_error`` finding (path and class) and never as unchanged; in the
git half it counts as git steering not verified, so no post-turn git command runs. Only a path that does not
exist is ``absent``.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from specy_road.git_config_text import git_reads, read_chain
from specy_road.git_subprocess import run
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.review_files import READY_PREFIX, REVIEWS_REL
from specy_road.runtime_paths import prefix_within
from specy_road.worktree_env import env_setup_config, git_top, link_paths, main_project_root

#: The sticky worker flag a ``steering_file`` finding sets; only ``worker reconcile`` (without ``--dismiss``) clears it.
FLAG_STEERING = "steering_changed"
#: Every ``class`` a ``steering_file`` finding can carry.
CLASSES = ("harness", "git_hook", "git_config", "policy_tree", "policy_blob", "registry", "review_file",
           "shell_startup", "env_bin", "symlink")
#: The toolkit's policy files, project-relative: checked in the tree and as blobs at the local integration branch tip.
POLICY_FILES = ("roadmap/orchestration.yaml", "roadmap/orchestration.local.yaml", "roadmap/git-workflow.yaml")
#: Shell startup files at a checkout's root (and its project root).
SHELL_FILES = (".bashrc", ".bash_profile", ".profile", ".zshrc", ".zshenv", ".envrc")
#: The harness config directories walked for :func:`in_tree_class`.
HARNESS_DIRS = (".claude", ".codex", ".cursor")
#: Denied to a Claude Code executor whether present at launch or not (unless a touch zone names one exactly).
CLAUDE_ALWAYS_DENIED = (".claude/settings.json", ".claude/settings.local.json")
#: More direct children than this in a hooks directory are recorded as the one marker ``capped``.
HOOKS_CAP = 200
#: git config keys whose values a ``git_config`` finding reports (plus every ``includeIf.<cond>.path``).
GIT_CONFIG_KEYS = ("core.hookspath", "core.fsmonitor", "core.sshcommand", "include.path")
ABSENT = "absent"
#: The prefix of a value that could not be read (:func:`guarded`).
ERROR = "error:"
#: Files this module parses (registry, git config) larger than this are unreadable, not parsed.
MAX_PARSE_BYTES = 8 * 1024 * 1024
#: The classes finish refuses on: in-tree steering paths a branch can land (``roadmap/registry.yaml`` never counts).
FINISH_CLASSES = ("harness", "policy_tree", "shell_startup")


def in_tree_class(rel: str, *, project: bool = True) -> str | None:
    """The class of an in-tree steering path, or ``None``. ``rel`` is relative to a checkout's project root
    (``project``) or to its git root, where only harness config and shell startup files count."""
    parts = rel.split("/")
    if project and rel in POLICY_FILES:
        return "policy_tree"
    if rel in SHELL_FILES:
        return "shell_startup"
    head, n = parts[0], len(parts)
    if head == ".codex" and n > 1:
        return "harness"
    if head == ".claude" and ((n == 2 and fnmatch.fnmatch(parts[1], "settings*.json")) or (n > 2 and parts[1] == "hooks")):
        return "harness"
    if head == ".cursor" and ((n == 2 and parts[1].endswith(".json")) or (n > 2 and parts[1] == "hooks")):
        return "harness"
    return None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(path: Path) -> str:
    """A file's sha256, streamed: size is never a reason to fail."""
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def parse_bytes(path: Path) -> bytes:
    """A file this module parses, refused over :data:`MAX_PARSE_BYTES`."""
    with open(path, "rb") as f:
        data = f.read(MAX_PARSE_BYTES + 1)
    if len(data) > MAX_PARSE_BYTES:
        raise ValueError(f"over the {MAX_PARSE_BYTES} byte parse cap")
    return data


def resolved_path(path: Path) -> Path:
    """``path`` resolved without raising: a link loop or a missing part (an executor can make either) stays as named."""
    return Path(os.path.realpath(path))


def _value(path: Path) -> str:
    """A path's content as every class compares it: a file's sha256; ``link:<text>`` plus ``@<sha256>`` of what a
    link resolves to when that is a regular file (a write through an unchanged link changes it; a link to a
    directory is not walked); ``dir``; ``other``; ``absent`` when nothing is there. Raises when the content cannot
    be read (a dangling link or a loop included): :func:`guarded` records that."""
    if not os.path.lexists(path):
        return ABSENT
    if path.is_symlink():
        text, mode = os.readlink(path), os.stat(path).st_mode   # stat follows: a dangling link or a loop raises
        return f"link:{text}" + (f"@{_digest(path)}" if stat.S_ISREG(mode) else "")
    mode = os.stat(path).st_mode
    return _digest(path) if stat.S_ISREG(mode) else "dir" if stat.S_ISDIR(mode) else "other"


def real_path(path: Path) -> Path:
    """``path`` with its parent resolved and its last component kept: a link is recorded, not followed."""
    return Path(os.path.realpath(path.parent)) / path.name


@dataclass(frozen=True)
class Entry:
    path: str                 # as findings name it: project-relative in the worker's tree, else absolute
    cls: str
    value: str
    values: tuple[tuple[str, str], ...] = ()   # git_config only: the watched keys' values


Snapshot = dict[str, Entry]   # keyed by the real path (or a synthetic key for registry rows and blobs)


def _gitdirs(top: Path) -> tuple[Path, Path] | None:
    """``(worktree gitdir, common git dir)`` of the checkout at ``top``, read from ``.git`` without running git."""
    dotgit = top / ".git"
    if dotgit.is_dir():
        return resolved_path(dotgit), resolved_path(dotgit)
    if not dotgit.exists():
        return None
    line = parse_bytes(dotgit).decode("utf-8").strip()
    if not line.startswith("gitdir:"):
        return None
    gitdir = resolved_path(top / line.removeprefix("gitdir:").strip())
    commondir = gitdir / "commondir"
    common = resolved_path(gitdir / parse_bytes(commondir).decode("utf-8").strip()) if commondir.exists() else gitdir
    return gitdir, common


def _watched(key: str) -> bool:
    return key in GIT_CONFIG_KEYS or (key.startswith("includeif.") and key.endswith(".path"))


def watched_values(pairs: list[tuple[str, str]]) -> dict[str, str]:
    """The watched keys among a config file's ``(key, value)`` pairs, as a finding shows them: ``{key: v1,v2}``."""
    out: dict[str, list[str]] = {}
    for k, v in pairs:
        if _watched(k):
            out.setdefault(k, []).append(v)
    return {k: ",".join(v) for k, v in out.items()}


@dataclass(frozen=True)
class Scope:
    """Where one worker's steering files live: its worktree and the main checkout, the same project prefix."""
    node_id: str
    prefix: str
    w_top: Path
    m_top: Path
    integration_branch: str | None
    links: tuple[str, ...]
    #: per checkout top, what git itself said it reads at the turn's start (:func:`git_reads`)
    git_known: dict[Path, tuple[list[Path], list[Path]]] = field(default_factory=dict, compare=False)
    #: ``(path, class, error)`` per input the scope itself could not read (``roadmap/git-workflow.yaml``)
    problems: tuple[tuple[Path, str, str], ...] = ()

    @property
    def tops(self) -> list[Path]:
        return [self.w_top] if self.m_top == self.w_top else [self.w_top, self.m_top]

    def display(self, real: Path) -> str:
        """Project-relative in the worker's tree (git-root-relative outside its project), else absolute."""
        for base in (self.w_top / self.prefix, self.w_top):
            if real.is_relative_to(base):
                return real.relative_to(base).as_posix()
        return str(real)


def _error(e: BaseException) -> str:
    return f"{ERROR}{type(e).__name__}: {e}"


def scope_for(repo_root: Path, worktree: Path, node_id: str) -> Scope:
    """The worker's scope, taken at the turn's start: the only time git is asked what it reads. The workflow
    file it reads (integration branch, ``env_setup.link``) is guarded too: unreadable, it is a problem of the
    scope, which every snapshot reports, and the classes that need it go without."""
    m_root = resolved_path(main_project_root(Path(repo_root)))
    m_top, w_top = git_top(m_root), git_top(Path(worktree))
    try:
        ib, links, problems = (resolve_integration_defaults(m_root, explicit_base=None, explicit_remote=None)[0],
                               tuple(link_paths(env_setup_config(m_root))), ())
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        ib, links, problems = None, (), ((m_root / "roadmap" / "git-workflow.yaml", "policy_tree", _error(e)),)
    return Scope(node_id, prefix_within(m_top, m_root), w_top, m_top, ib, links,
                 {top: git_reads(top) for top in dict.fromkeys((w_top, m_top))}, problems)


def guarded(snap: Snapshot, scope: Scope, path: Path, cls: str, step: Callable[[], None]) -> None:
    """Run one per-file or per-directory ``step``; any exception records ``path`` as unreadable for ``cls``
    (the module's one rule) and the snapshot goes on."""
    try:
        step()
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        unreadable(snap, scope, path, cls, e)


def unreadable(snap: Snapshot, scope: Scope, path: Path, cls: str, e: BaseException) -> None:
    """Record ``path`` as unreadable for ``cls``, replacing whatever was recorded for it."""
    real = real_path(path)
    snap[str(real)] = Entry(scope.display(real), cls, _error(e))


def _add(snap: Snapshot, scope: Scope, path: Path, cls: str, value: str | None = None, name: str | None = None) -> None:
    """Record one path once (by its real path), its value read under the one rule: unreadable is an ``error:``."""
    real = real_path(path)
    if str(real) in snap:
        return
    try:
        value = value if value is not None else _value(path)
    except Exception as e:  # noqa: BLE001 — one rule: an unreadable input is reported, never fatal
        value = _error(e)
    snap[str(real)] = Entry(name or scope.display(real), cls, value)


def tree_files(root: Path, errors: list[OSError] | None = None) -> list[Path]:
    """Files and links under ``root``, links not followed; a directory that cannot be listed goes to ``errors``."""
    out = []
    for d, dirs, files in os.walk(root, followlinks=False, onerror=errors.append if errors is not None else None):
        out += [Path(d, f) for f in files]
        out += [Path(d, x) for x in dirs if Path(d, x).is_symlink()]
    return out


def _walk(snap: Snapshot, scope: Scope, root: Path, cls: str) -> list[Path]:
    """:func:`tree_files` with each directory it could not list recorded as unreadable for ``cls``."""
    errors: list[OSError] = []
    files = tree_files(root, errors)
    for e in errors:
        unreadable(snap, scope, Path(e.filename or root), cls, e)
    return files


def _tree(snap: Snapshot, scope: Scope) -> None:
    """Harness config and hooks, shell startup files and the policy files, at each checkout's git root and
    project root."""
    for top in scope.tops:
        for base, project in ((top, scope.prefix == ""), (top / scope.prefix, True)):
            for name in (*SHELL_FILES, *(POLICY_FILES if project else ())):
                if os.path.lexists(base / name):
                    _add(snap, scope, base / name, in_tree_class(name, project=project) or "")
            for d in HARNESS_DIRS:
                for p in _walk(snap, scope, base / d, "harness") if (base / d).is_dir() or (base / d).is_symlink() else []:
                    if cls := in_tree_class(p.relative_to(base).as_posix(), project=project):
                        _add(snap, scope, p, cls)


def _list(snap: Snapshot, scope: Scope, d: Path, cls: str, each: Callable[[list[Path]], None]) -> None:
    """``each`` on the sorted entries of directory ``d`` (none when it does not exist), guarded."""
    if os.path.lexists(d):
        guarded(snap, scope, d, cls, lambda: each(sorted(d.iterdir())))


def _hooks_dir(snap: Snapshot, scope: Scope, d: Path) -> None:
    def each(kids: list[Path]) -> None:
        if len(kids) > HOOKS_CAP:
            _add(snap, scope, d, "git_hook", "capped")
            return
        for k in kids:
            if not k.is_dir() or k.is_symlink():   # direct entries; a real subdirectory is not a hook
                _add(snap, scope, k, "git_hook")
    _list(snap, scope, d, "git_hook", each)


def _config_file(snap: Snapshot, scope: Scope, top: Path, start: Path, hooks: list[Path]) -> None:
    """One config file git reads and those it includes, each guarded; their ``core.hooksPath`` values go to ``hooks``."""
    for path, data, pairs in read_chain(start, parse_bytes):
        if isinstance(data, Exception):
            unreadable(snap, scope, path, "git_config", data)
            continue
        real = real_path(path)
        snap.setdefault(str(real), Entry(scope.display(real), "git_config", _sha(data),
                                         tuple(sorted(watched_values(pairs).items()))))
        hooks += [top / os.path.expanduser(v) for k, v in pairs if k == "core.hookspath" and v]


def git_snapshot(scope: Scope) -> Snapshot:
    """Git steering, from the filesystem only: the config files and hooks directories git named at the turn's
    start (``scope.git_known``), plus, as candidates from :mod:`specy_road.git_config_text`, the common
    ``config``, ``config.worktree`` and every file they include (conditions not evaluated), ``<common>/hooks``,
    ``<worktree-gitdir>/hooks`` and each ``core.hooksPath`` value read (relative to the checkout)."""
    snap: Snapshot = {}
    for top in scope.tops:
        guarded(snap, scope, top / ".git", "git_config", lambda top=top: _git_top(snap, scope, top))
    return snap


def _git_top(snap: Snapshot, scope: Scope, top: Path) -> None:
    known_hooks, known_files = scope.git_known.get(top, ([], []))
    hooks, starts = list(known_hooks), list(known_files)
    if dirs := _gitdirs(top):
        gitdir, common = dirs
        hooks += [common / "hooks", gitdir / "hooks"]
        starts += [common / "config", common / "config.worktree", gitdir / "config.worktree"]
    for start in dict.fromkeys(starts):
        _config_file(snap, scope, top, start, hooks)
    for d in dict.fromkeys(resolved_path(h) for h in hooks):
        _hooks_dir(snap, scope, d)


def _registry(snap: Snapshot, scope: Scope) -> None:
    """Every ``entries`` item of another leaf, in each checkout's ``roadmap/registry.yaml``."""
    for top in scope.tops:
        path = real_path(top / scope.prefix / "roadmap" / "registry.yaml")
        if os.path.lexists(path):
            guarded(snap, scope, path, "registry", lambda path=path: _registry_rows(snap, scope, path))


def _registry_rows(snap: Snapshot, scope: Scope, path: Path) -> None:
    doc = yaml.safe_load(parse_bytes(path).decode("utf-8")) or {}
    entries = doc.get("entries") if isinstance(doc, dict) else None
    for item in entries if isinstance(entries, list) else []:   # any other shape: no rows to watch
        if not isinstance(item, dict) or str(item.get("node_id")) == scope.node_id:
            continue
        key = f"{path}#{item.get('node_id')}#{item.get('codename')}"
        snap.setdefault(key, Entry(f"{scope.display(path)}#{item.get('node_id')}", "registry",
                                   _sha(json.dumps(item, sort_keys=True, default=str).encode())))


def _reviews(snap: Snapshot, scope: Scope) -> None:
    """Every file under each checkout's ``work/reviews/`` but the leaf's own READY."""
    for top in scope.tops:
        root = top / scope.prefix / REVIEWS_REL
        for p in _walk(snap, scope, root, "review_file") if root.is_dir() else []:
            rel = p.relative_to(root)
            if not (rel.parts[:1] == (scope.node_id,) and len(rel.parts) == 2 and rel.name.startswith(READY_PREFIX)):
                _add(snap, scope, p, "review_file")


def _env_bin(snap: Snapshot, scope: Scope) -> None:
    """Each ``env_setup.link`` path's ``bin/`` entries in each checkout (the worker's link and its main-checkout
    source are one real directory): name, type, link text, resolved regular-file sha256."""
    for top, rel in ((top, rel) for top in scope.tops for rel in scope.links):
        named = top / scope.prefix / rel / "bin"
        _list(snap, scope, resolved_path(top / scope.prefix / rel) / "bin", "env_bin", lambda kids, named=named: [
            _add(snap, scope, k, "env_bin", name=scope.display(named / k.name)) for k in kids])


def blobs(snap: Snapshot, scope: Scope) -> None:
    """The policy files as committed at the local integration branch tip (no fetch)."""
    for rel in POLICY_FILES if scope.integration_branch else ():
        r = run(["cat-file", "blob", f"refs/heads/{scope.integration_branch}:{scope.prefix}{rel}"], scope.m_top)
        name = f"{scope.integration_branch}:{rel}"
        snap[f"blob:{name}"] = Entry(name, "policy_blob", _sha(r.out.encode()) if r.ok else ABSENT)


def file_snapshot(scope: Scope) -> Snapshot:
    """Everything but git steering that reading the filesystem answers, plus the scope's own problems."""
    snap: Snapshot = {str(p): Entry(scope.display(real_path(p)), cls, err) for p, cls, err in scope.problems}
    _tree(snap, scope)
    _registry(snap, scope)
    _reviews(snap, scope)
    _env_bin(snap, scope)
    return snap
