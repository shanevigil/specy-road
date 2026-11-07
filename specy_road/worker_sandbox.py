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
import subprocess
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
    _status: int | None = None

    def popen(self, argv: list[str], **kw) -> subprocess.Popen:
        """``subprocess.Popen`` of ``argv``, under bwrap when sandboxed; bwrap reports on a pipe once the harness starts."""
        if not self.prefix:
            return subprocess.Popen(argv, **kw)  # noqa: S603 — the adapter's documented command
        r, w = os.pipe()
        try:
            proc = subprocess.Popen([*self.prefix, "--json-status-fd", str(w), "--", *argv],  # noqa: S603
                                    pass_fds=(w,), **kw)
        except OSError:
            os.close(r)
            raise
        finally:
            os.close(w)
        self._status = r
        return proc

    def finish(self) -> str | None:
        """After the harness exits: deliver READY from the outbox; the reason the sandbox never started, else ``None``."""
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
    mode = worker_sandbox_mode(repo_root)
    if mode == "off":
        return Box("off")
    bwrap = shutil.which("bwrap") if sys.platform.startswith("linux") else None
    if bwrap is None:
        why = "bwrap is not installed" if sys.platform.startswith("linux") else f"{sys.platform} has no backend"
        if mode == "bwrap":
            raise SandboxError(f"worker_sandbox: bwrap, but {why}; install bubblewrap or set worker_sandbox: off")
        return Box("off", warning=NO_SANDBOX_WARNING.format(why=why))
    wt, common, name = linked_worktree(Path(rec.worktree))
    reviews = reviews_dir(repo_root, rec.node_id)
    outbox = workers_dir(repo_root) / f"{rec.worker_id}.outbox"
    try:
        reviews.mkdir(parents=True, exist_ok=True)   # a mount point must exist: the root is read-only
        shutil.rmtree(outbox, ignore_errors=True)
        outbox.mkdir(mode=0o700, parents=True)
        (common / "logs").mkdir(exist_ok=True)       # a commit's reflog goes here
        harness = _harness_binds(repo_root, rec, env)
    except OSError as e:
        raise SandboxError(f"cannot set up the sandbox: {e}") from e
    argv = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--die-with-parent", "--bind", str(wt), str(wt)]
    for d in ("objects", "refs", "logs", f"worktrees/{name}"):
        argv += ["--bind", str(common / d), str(common / d)]
    for f in ("commondir", "gitdir"):
        p = common / "worktrees" / name / f
        if p.exists():
            argv += ["--ro-bind", str(p), str(p)]
    argv += ["--bind", str(outbox), str(reviews), *harness]
    home = Path.home()
    for d in HIDDEN_HOME:
        if (home / d).exists():
            argv += ["--tmpfs", str(home / d)]
    for k in HIDDEN_ENV:
        env.pop(k, None)
    return Box("bwrap", [*argv, "--chdir", str(wt)], outbox=outbox, reviews=reviews)


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


def _harness_binds(repo_root: Path, rec: WorkerRecord, env: dict[str, str]) -> list[str]:
    """Writable state for ``rec.harness``, its shared steering files read-only on top; per-worker config copies."""
    home = Path.home()
    rw: list[Path] = []
    ro: list[Path] = []
    copies: list[tuple[Path, Path]] = []
    own = workers_dir(repo_root)   # the per-worker copies sit beside the record
    if rec.harness == "claude-code":
        conf = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"
        rw += [conf, home / ".cache" / "claude-cli-nodejs"]
        ro += [conf / n for n in ("settings.json", "settings.local.json", "hooks", "plugins", "skills", "agents",
                                  "commands", "output-styles", "CLAUDE.md")]
        state = conf / ".claude.json" if env.get("CLAUDE_CONFIG_DIR") else home / ".claude.json"
        copies.append((state, own / f"{rec.worker_id}.claude.json"))
    elif rec.harness == "cursor":
        rw += [home / ".cursor", home / ".config" / "cursor", home / ".cache" / "cursor-compile-cache"]
        ro += [home / ".cursor" / n for n in ("hooks", "hooks.json", "mcp.json", "plugins", "rules", "skills",
                                              "skills-cursor", "extensions", "sandbox-policies")]
        copies.append((home / ".cursor" / "cli-config.json", own / f"{rec.worker_id}.cursor-cli-config.json"))
    elif rec.harness == "codex":
        conf = Path(env.get("CODEX_HOME") or home / ".codex")
        rw += [conf, (conf / "auth.json").resolve()]   # the profile's auth.json links to the user's login
        ro += [conf / n for n in ("config.toml", "AGENTS.md", "hooks", "plugins", "rules", "skills")]
    argv: list[str] = []
    for p in rw:
        if p.exists():
            argv += ["--bind", str(p), str(p)]
    for p in ro:
        if p.exists():
            argv += ["--ro-bind", str(p), str(p)]
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
