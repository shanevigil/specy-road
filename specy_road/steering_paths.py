"""Steering files: what an executor can write that trusted code outside it later reads or runs (M21.7).

An unattended executor works in a linked worktree, and some files it can write are read or run later by
something it does not control: the coordinator's harness (its config and hooks), git (hooks and
``core.fsmonitor`` / ``core.hooksPath`` in the common git dir, which every worktree of the repository shares),
the coordinator's shell (startup files, the interpreter ``env_setup.link`` shares), and the toolkit's own gate
(``roadmap/orchestration.yaml`` and the other policy files, other leaves' registry rows, ``work/reviews/``).
This module holds the one list (documented in docs/orchestration-steering-files.md, linked from
docs/orchestration-workers.md) and the per-turn watch; :mod:`specy_road.steering_gate` holds its two other uses:

- :class:`SteeringWatch`: a snapshot per worker turn, in the worktree and in the main checkout, and the diff
  the post-run check (worker_turn_check) records as ``steering_file`` findings. The git half is read from the
  filesystem only, so it is compared before any post-turn git command runs.
- :func:`~specy_road.steering_gate.steering_or_exit`: finish's refusal of a branch that changes an in-tree steering path no touch zone
  names exactly.
- :func:`~specy_road.steering_gate.claude_denies`: per-file ``--disallowedTools`` rules for a Claude Code executor's launch and resume.

Detection only: nothing here restores a changed file. Paths compare project-relative, as ``zone_matches``
does, and one real path is stored once.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from specy_road.git_config_text import read_chain
from specy_road.git_subprocess import run
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.review_files import READY_PREFIX, REVIEWS_REL
from specy_road.runtime_paths import prefix_within
from specy_road.worker_state import status_entries
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


def _value(path: Path) -> str:
    """A path's content as compared: ``link:<target>``, the file's sha256, or ``absent``."""
    try:
        if path.is_symlink():
            return f"link:{os.readlink(path)}"
        return _sha(path.read_bytes()) if path.is_file() else ABSENT
    except OSError:
        return ABSENT


def _real(path: Path) -> Path:
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
        return dotgit.resolve(), dotgit.resolve()
    try:
        line = dotgit.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not line.startswith("gitdir:"):
        return None
    gitdir = (top / line.removeprefix("gitdir:").strip()).resolve()
    try:
        common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        common = gitdir
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
    integration_branch: str
    links: tuple[str, ...]

    @property
    def tops(self) -> list[Path]:
        return [self.w_top] if self.m_top == self.w_top else [self.w_top, self.m_top]

    def display(self, real: Path) -> str:
        """Project-relative in the worker's tree (git-root-relative outside its project), else absolute."""
        for base in (self.w_top / self.prefix, self.w_top):
            if real.is_relative_to(base):
                return real.relative_to(base).as_posix()
        return str(real)


def scope_for(repo_root: Path, worktree: Path, node_id: str) -> Scope:
    m_root = main_project_root(Path(repo_root)).resolve()
    m_top = git_top(m_root)
    ib = resolve_integration_defaults(m_root, explicit_base=None, explicit_remote=None)[0]
    return Scope(node_id, prefix_within(m_top, m_root), git_top(Path(worktree)), m_top, ib,
                 tuple(link_paths(env_setup_config(m_root))))


def _add(snap: Snapshot, scope: Scope, path: Path, cls: str, value: str | None = None, name: str | None = None) -> None:
    real = _real(path)
    snap.setdefault(str(real), Entry(name or scope.display(real), cls, value if value is not None else _value(path)))


def tree_files(root: Path) -> list[Path]:
    """Files and links under ``root``, links not followed."""
    out = []
    for d, dirs, files in os.walk(root, followlinks=False):
        out += [Path(d, f) for f in files]
        out += [Path(d, x) for x in dirs if Path(d, x).is_symlink()]
    return out


def _tree(snap: Snapshot, scope: Scope) -> None:
    """Harness config and hooks, shell startup files and the policy files, at each checkout's git root and
    project root."""
    for top in scope.tops:
        for base, project in ((top, scope.prefix == ""), (top / scope.prefix, True)):
            for name in (*SHELL_FILES, *(POLICY_FILES if project else ())):
                if (base / name).is_file() or (base / name).is_symlink():
                    _add(snap, scope, base / name, in_tree_class(name, project=project) or "")
            for d in HARNESS_DIRS:
                for p in tree_files(base / d) if (base / d).is_dir() else []:
                    if cls := in_tree_class(p.relative_to(base).as_posix(), project=project):
                        _add(snap, scope, p, cls)


def _hooks_dir(snap: Snapshot, scope: Scope, d: Path) -> None:
    try:
        kids = sorted(d.iterdir())
    except OSError:
        return
    if len(kids) > HOOKS_CAP:
        _add(snap, scope, d, "git_hook", "capped")
        return
    for k in kids:
        if k.is_symlink() or k.is_file():
            _add(snap, scope, k, "git_hook")


def git_snapshot(scope: Scope) -> Snapshot:
    """Git steering, from the filesystem only (:mod:`specy_road.git_config_text`): every config file git reads
    (the common ``config``, ``config.worktree`` and what they include), and the hooks directories: each
    ``core.hooksPath`` value any of them sets (relative to the checkout), else ``<common>/hooks`` and
    ``<worktree-gitdir>/hooks``."""
    snap: Snapshot = {}
    for top in scope.tops:
        dirs = _gitdirs(top)
        if dirs is None:
            continue
        gitdir, common = dirs
        hooks: list[Path] = []
        for start in dict.fromkeys((common / "config", common / "config.worktree", gitdir / "config.worktree")):
            for path, data, pairs in read_chain(start):
                real = _real(path)
                snap.setdefault(str(real), Entry(scope.display(real), "git_config", _sha(data),
                                                 tuple(sorted(watched_values(pairs).items()))))
                hooks += [(top / os.path.expanduser(v)).resolve() for k, v in pairs if k == "core.hookspath" and v]
        for d in dict.fromkeys(hooks or [common / "hooks", gitdir / "hooks"]):
            _hooks_dir(snap, scope, d)
    return snap


def _registry(snap: Snapshot, scope: Scope) -> None:
    """Every ``entries`` item of another leaf, in each checkout's ``roadmap/registry.yaml``."""
    for top in scope.tops:
        path = _real(top / scope.prefix / "roadmap" / "registry.yaml")
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for item in (doc.get("entries") or []) if isinstance(doc, dict) else []:
            if not isinstance(item, dict) or str(item.get("node_id")) == scope.node_id:
                continue
            key = f"{path}#{item.get('node_id')}#{item.get('codename')}"
            snap.setdefault(key, Entry(f"{scope.display(path)}#{item.get('node_id')}", "registry",
                                       _sha(json.dumps(item, sort_keys=True, default=str).encode())))


def _reviews(snap: Snapshot, scope: Scope) -> None:
    """Every file under each checkout's ``work/reviews/`` but the leaf's own READY."""
    for top in scope.tops:
        root = top / scope.prefix / REVIEWS_REL
        for p in tree_files(root) if root.is_dir() else []:
            rel = p.relative_to(root)
            if not (rel.parts[:1] == (scope.node_id,) and len(rel.parts) == 2 and rel.name.startswith(READY_PREFIX)):
                _add(snap, scope, p, "review_file")


def _env_bin(snap: Snapshot, scope: Scope) -> None:
    """Each ``env_setup.link`` path's ``bin/`` entries in each checkout (the worker's link and its main-checkout
    source are one real directory): name, type, link text, resolved regular-file sha256."""
    for top, rel in ((top, rel) for top in scope.tops for rel in scope.links):
        bin_dir = (top / scope.prefix / rel).resolve() / "bin"
        try:
            kids = sorted(bin_dir.iterdir())
        except OSError:
            continue
        for k in kids:
            if k.is_symlink():
                target = k.resolve()
                value = f"link:{os.readlink(k)}" + (f"@{_value(target)}" if target.is_file() else "")
            else:
                value = _value(k) if k.is_file() else "dir" if k.is_dir() else "other"
            _add(snap, scope, k, "env_bin", value, scope.display(top / scope.prefix / rel / "bin" / k.name))


def _blobs(snap: Snapshot, scope: Scope) -> None:
    """The policy files as committed at the local integration branch tip (no fetch)."""
    for rel in POLICY_FILES:
        r = run(["cat-file", "blob", f"refs/heads/{scope.integration_branch}:{scope.prefix}{rel}"], scope.m_top)
        name = f"{scope.integration_branch}:{rel}"
        snap[f"blob:{name}"] = Entry(name, "policy_blob", _sha(r.out.encode()) if r.ok else ABSENT)


def file_snapshot(scope: Scope) -> Snapshot:
    """Everything but git steering that reading the filesystem answers."""
    snap: Snapshot = {}
    _tree(snap, scope)
    _registry(snap, scope)
    _reviews(snap, scope)
    _env_bin(snap, scope)
    return snap


def _git_config_side(value: str, mine: dict[str, str], keys: list[str]) -> str:
    return value + "".join(f";{k}={mine.get(k, 'unset')}" for k in keys)


def changes(before: Snapshot, after: Snapshot) -> list[dict[str, Any]]:
    """One ``steering_file`` finding per entry whose value differs (a missing entry is ``absent``)."""
    out = []
    for key in sorted(before.keys() | after.keys()):
        b, a = before.get(key), after.get(key)
        bv, av = (b.value if b else ABSENT), (a.value if a else ABSENT)
        if bv == av:
            continue
        e = a or b
        if e.cls == "git_config":
            bd, ad = dict(b.values if b else ()), dict(a.values if a else ())
            keys = sorted(k for k in bd.keys() | ad.keys() if bd.get(k) != ad.get(k))
            bv, av = _git_config_side(bv, bd, keys), _git_config_side(av, ad, keys)
        out.append(finding(e.path, e.cls, bv, av))
    return out


def finding(path: str, cls: str, before: str, after: str) -> dict[str, Any]:
    return {"kind": "steering_file", "path": path, "class": cls, "before": before, "after": after,
            "summary": f"steering file {path} ({cls}) changed: {before[:24]} -> {after[:24]}"}


def _links(top: Path, dirty: dict[str, str] | None) -> dict[str, str]:
    """``{path: link text}`` for the symlinks among a checkout's porcelain entries."""
    if dirty is None:
        entries = status_entries(top)
        dirty = {p: _value(top / p) for _xy, p in entries or ()}
    return {p: v.removeprefix("link:") for p, v in dirty.items() if v.startswith("link:")}


class SteeringWatch:
    """One turn's steering snapshot, taken at the turn's start; :meth:`git_changes` before any post-turn git
    command, :meth:`rest_changes` after the git probes (or with ``git_ok=False`` when they were skipped)."""

    def __init__(self, repo_root: Path, worktree: Path, node_id: str, worktree_dirty: dict[str, str] | None) -> None:
        self.scope = scope_for(repo_root, worktree, node_id)
        self.git = git_snapshot(self.scope)
        self.files = file_snapshot(self.scope)
        _blobs(self.files, self.scope)
        self.links = self._porcelain_links(worktree_dirty)

    def _porcelain_links(self, worktree_dirty: dict[str, str] | None) -> dict[str, str]:
        out = {str(self.scope.w_top / p): t for p, t in _links(self.scope.w_top, worktree_dirty).items()}
        if self.scope.m_top != self.scope.w_top:
            out.update({str(self.scope.m_top / p): t for p, t in _links(self.scope.m_top, None).items()})
        return out

    def git_changes(self) -> list[dict[str, Any]]:
        return changes(self.git, git_snapshot(self.scope))

    def rest_changes(self, worktree_dirty: dict[str, str] | None, *, git_ok: bool) -> list[dict[str, Any]]:
        """The non-git classes; with ``git_ok`` also the policy blobs and new or retargeted symlinks leaving the
        worker's git root (both need git). ``worktree_dirty`` is the worktree's porcelain after the turn."""
        after = file_snapshot(self.scope)
        before = {k: v for k, v in self.files.items() if git_ok or v.cls != "policy_blob"}
        if git_ok:
            _blobs(after, self.scope)
        out = changes(before, after)
        if git_ok:
            for path, target in sorted(self._porcelain_links(worktree_dirty).items()):
                old = self.links.get(path)
                if old != target and not Path(path).resolve().is_relative_to(self.scope.w_top):
                    out.append(finding(self.scope.display(_real(Path(path))), "symlink",
                                       f"link:{old}" if old is not None else ABSENT, f"link:{target}"))
        return out

    def merged(self, found: list[dict[str, Any]], steer: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """``found`` plus ``steer`` with one finding per path: of several ``steering_file`` findings for one path
        (two detectors reach it, e.g. a harness file that is also a new escaping symlink) the first class in
        :data:`CLASSES` order is kept, and every steering path is dropped from the ``porcelain`` and
        ``committed_outside_zones`` findings."""
        one: dict[str, dict[str, Any]] = {}
        for f in sorted(steer, key=lambda f: CLASSES.index(f["class"])):
            one.setdefault(f["path"], f)
        out = []
        for f in found:
            if f["kind"] not in ("porcelain", "committed_outside_zones") or "paths" not in f:
                out.append(f)
                continue
            keep = [p for p in f["paths"] if self.scope.display(_real(self.scope.w_top / p)) not in one]
            if keep:
                out.append({**f, "paths": keep, "summary": f["summary"].split(": ", 1)[0] + ": " + ", ".join(keep[:10])})
        return out + sorted(one.values(), key=lambda f: f["path"])
