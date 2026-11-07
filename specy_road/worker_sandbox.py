"""Run an unattended worker's harness inside a bubblewrap (``bwrap``) sandbox on Linux (M22.44).

:func:`prepare` reads ``worker_sandbox`` from ``roadmap/git-workflow.yaml`` and returns a :class:`Box`, which
:mod:`worker_runner` uses at its one harness launch. Under ``bwrap`` the whole filesystem is read-only except:

* the leaf's linked worktree, and in the common git dir ``objects/``, ``refs/``, ``logs/`` and
  ``worktrees/<name>/`` (its ``commondir`` and ``gitdir`` read-only again: rewriting them would steer the
  coordinator's next git command in that tree);
* a per-worker outbox mounted at the canonical ``work/reviews/<node>/``: after the turn the runner moves only
  ``READY-*`` files from it into the real directory and discards the rest;
* the transcript, auth and runtime state of the worker's harness, with its shared settings, hooks, plugins and
  skills read-only on top; configuration it must write that can hold launch instructions (``~/.claude.json``,
  Cursor's ``cli-config.json``) is a per-worker copy kept beside the worker's record.

``~/.ssh`` and ``~/.config/gh`` are hidden behind an empty tmpfs, and ``SSH_AUTH_SOCK``, ``GH_TOKEN`` and
``GITHUB_TOKEN`` are dropped from the harness environment. ``/tmp`` is a private tmpfs; the network stays open.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from specy_road.git_workflow_config import worker_sandbox_mode
from specy_road.review_files import READY_PREFIX, reviews_dir
from specy_road.worker_state import WorkerRecord, workers_dir

#: Environment entries the sandboxed harness does not get.
HIDDEN_ENV = ("SSH_AUTH_SOCK", "GH_TOKEN", "GITHUB_TOKEN")
#: Home directories hidden behind an empty tmpfs.
HIDDEN_HOME = (".ssh", ".config/gh")

NO_SANDBOX_WARNING = ("no worker sandbox on this host ({why}): the harness runs unsandboxed and can write the main "
                      "checkout, its git config and hooks, your home and other leaves' hand-offs "
                      "(docs/orchestration-workers.md, Worker sandbox)")


class SandboxError(Exception):
    """The sandbox was selected but cannot be set up: the turn does not start."""


@dataclass
class Box:
    """How one turn's harness is started: ``prefix`` is empty when it runs unsandboxed."""

    mode: str                                   # bwrap, or off (explicit or the warned fallback)
    prefix: list[str] = field(default_factory=list)
    warning: str | None = None
    outbox: Path | None = None
    reviews: Path | None = None
    pass_fds: tuple[int, ...] = ()              # bwrap's status pipe, write end, for ``Popen``
    _status: int | None = None

    def command(self, argv: list[str]) -> list[str]:
        """``argv``, under bwrap when sandboxed: bwrap reports on a pipe (``pass_fds``) once the harness starts."""
        if not self.prefix:
            return argv
        self._status, w = os.pipe()
        self.pass_fds = (w,)
        return [*self.prefix, "--json-status-fd", str(w), "--", *argv]

    def finish(self) -> str | None:
        """After the harness exits (or failed to start): deliver READY from the outbox; the reason the sandbox
        never started the harness, else ``None``."""
        for w in self.pass_fds:
            os.close(w)
        self.pass_fds = ()
        started = True
        if self._status is not None:
            started = b'"child-pid"' in _read_available(self._status)
            self._status = None
        if self.outbox is not None and self.reviews is not None:
            _deliver_ready(self.outbox, self.reviews)
        return None if started else "bwrap stopped before the harness started (its message is in the worker log)"


def prepare(repo_root: Path, rec: WorkerRecord, env: dict[str, str]) -> Box:
    """The turn's :class:`Box`, per ``worker_sandbox``; drops the hidden entries from ``env`` when sandboxed.

    Raises :class:`SandboxError` when the sandbox is selected (``bwrap``, or ``auto`` where bwrap is installed)
    but this turn cannot run in it.
    """
    bwrap = _select(worker_sandbox_mode(repo_root))
    if isinstance(bwrap, Box):
        return bwrap
    wt, common, name = linked_worktree(Path(rec.worktree))
    reviews = reviews_dir(repo_root, rec.node_id)
    outbox = workers_dir(repo_root) / f"{rec.worker_id}.outbox"
    try:
        reviews.mkdir(parents=True, exist_ok=True)   # a mount point must exist: the root is read-only
        shutil.rmtree(outbox, ignore_errors=True)
        outbox.mkdir(mode=0o700, parents=True)
        (common / "logs").mkdir(exist_ok=True)       # a commit's reflog goes here
        harness = _harness_binds(*_harness_state(repo_root, rec, env))
    except OSError as e:
        raise SandboxError(f"cannot set up the sandbox: {e}") from e
    tree = common / "worktrees" / name
    argv = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--die-with-parent", "--bind", str(wt), str(wt),
            *_binds("--bind", [common / "objects", common / "refs", common / "logs", tree]),
            *_binds("--ro-bind", [tree / "commondir", tree / "gitdir"]),
            "--bind", str(outbox), str(reviews), *harness]
    for d in HIDDEN_HOME:
        if (Path.home() / d).exists():
            argv += ["--tmpfs", str(Path.home() / d)]
    for k in HIDDEN_ENV:
        env.pop(k, None)
    return Box("bwrap", [*argv, "--chdir", str(wt)], outbox=outbox, reviews=reviews)


def _select(mode: str) -> str | Box:
    """bwrap's path when the sandbox is selected and available; else the unsandboxed :class:`Box`, or a refusal."""
    if mode == "off":
        return Box("off")
    linux = sys.platform.startswith("linux")
    bwrap = shutil.which("bwrap") if linux else None
    if bwrap is not None:
        return bwrap
    why = "bwrap is not installed" if linux else f"{sys.platform} has no backend"
    if mode == "bwrap":
        raise SandboxError(f"worker_sandbox: bwrap, but {why}; install bubblewrap or set worker_sandbox: off")
    return Box("off", warning=NO_SANDBOX_WARNING.format(why=why))


def _binds(flag: str, paths: list[Path]) -> list[str]:
    """``flag p p`` for each path that exists: bwrap cannot make a mount point on the read-only root."""
    return [a for p in paths if p.exists() for a in (flag, str(p), str(p))]


def linked_worktree(worktree: Path) -> tuple[Path, Path, str]:
    """``(worktree, common git dir, worktree name)`` of a linked worktree, read from ``.git`` and ``commondir``.

    Raises :class:`SandboxError` for the main checkout or anything else: its common dir would be writable.
    """
    wt = worktree.resolve()
    need = (f"a sandboxed turn needs a linked worktree distinct from the main checkout, and {wt} is not one; "
            "delegate with a separate --worktree (or set worker_sandbox: off to run unsandboxed)")
    dotgit = wt / ".git"
    if not dotgit.is_file():
        raise SandboxError(need)
    try:
        line = dotgit.read_text(encoding="utf-8").strip()
        gitdir = (wt / line.removeprefix("gitdir:").strip()).resolve()
        common = (gitdir / (gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError as e:
        raise SandboxError(f"{need}: {e}") from e
    if not line.startswith("gitdir:") or gitdir.parent != common / "worktrees":
        raise SandboxError(need)
    return wt, common, gitdir.name


def _harness_state(repo_root: Path, rec: WorkerRecord,
                   env: dict[str, str]) -> tuple[list[Path], list[Path], list[tuple[Path, Path]]]:
    """``(writable, read-only on top, (config, per-worker copy))`` for ``rec.harness``: its transcript, auth and
    runtime state stay writable; its shared settings, hooks, plugins and skills do not."""
    home = Path.home()
    own = workers_dir(repo_root)   # the per-worker copies sit beside the record
    if rec.harness == "claude-code":
        conf = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        state = conf / ".claude.json" if env.get("CLAUDE_CONFIG_DIR") else home / ".claude.json"
        return ([conf, home / ".cache" / "claude-cli-nodejs"],
                [conf / n for n in ("settings.json", "settings.local.json", "hooks", "plugins", "skills", "agents",
                                    "commands", "output-styles", "CLAUDE.md")],
                [(state, own / f"{rec.worker_id}.claude.json")])
    if rec.harness == "cursor":
        return ([home / ".cursor", home / ".config" / "cursor", home / ".cache" / "cursor-compile-cache"],
                [home / ".cursor" / n for n in ("hooks", "hooks.json", "mcp.json", "plugins", "rules", "skills",
                                                "skills-cursor", "extensions", "sandbox-policies")],
                [(home / ".cursor" / "cli-config.json", own / f"{rec.worker_id}.cursor-cli-config.json")])
    if rec.harness == "codex":
        conf = Path(env.get("CODEX_HOME") or home / ".codex")
        return ([conf, (conf / "auth.json").resolve()],   # the profile's auth.json links to the user's login
                [conf / n for n in ("config.toml", "AGENTS.md", "hooks", "plugins", "rules", "skills")], [])
    return [], [], []


def _harness_binds(rw: list[Path], ro: list[Path], copies: list[tuple[Path, Path]]) -> list[str]:
    """The bwrap arguments for :func:`_harness_state`; a copy is made once, from the user's file, and kept."""
    argv = [*_binds("--bind", rw), *_binds("--ro-bind", ro)]
    for src, copy in copies:
        if src.is_file():
            if not copy.is_file():
                shutil.copyfile(src, copy)
                copy.chmod(0o600)
            argv += ["--bind", str(copy), str(src)]
    return argv


def _read_available(fd: int) -> bytes:
    """What the closed-or-idle pipe ``fd`` holds now, then close it: never blocks on a harness that kept it open."""
    os.set_blocking(fd, False)
    out = b""
    try:
        while chunk := os.read(fd, 65536):
            out += chunk
    except BlockingIOError:
        pass
    finally:
        os.close(fd)
    return out


def _deliver_ready(outbox: Path, reviews: Path) -> None:
    """Move each regular ``READY-*`` file from the outbox into ``reviews``; nothing else written there is kept."""
    try:
        for p in outbox.iterdir():
            if p.name.upper().startswith(READY_PREFIX.upper()) and p.is_file() and not p.is_symlink():
                shutil.move(str(p), str(reviews / p.name))
    finally:
        shutil.rmtree(outbox, ignore_errors=True)
