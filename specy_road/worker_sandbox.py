"""Run an unattended worker's harness inside a bubblewrap (``bwrap``) sandbox on Linux (M22.44).

:func:`prepare` reads ``worker_sandbox`` from ``roadmap/git-workflow.yaml`` and returns a :class:`Box`, which
:mod:`worker_runner` uses at its one harness launch. Under ``bwrap`` the whole filesystem is read-only except:

* the leaf's linked worktree, and in the common git dir ``objects/``, ``refs/``, ``logs/`` and
  ``worktrees/<name>/``. What points git at a repository or its config is read-only again: the worktree's
  ``.git`` file, ``worktrees/<name>/commondir`` and ``gitdir``, and ``config.worktree`` (an empty file when the
  user has none). Rewriting any of them would steer the coordinator's next git command in that tree;
* a per-worker outbox mounted at the canonical ``work/reviews/<node>/``, seeded with a copy of the regular files
  already there (links are not copied) so a fix round reads its review records: after the turn the runner moves
  only ``READY-*`` files from it into the real directory and discards the rest, edited copies included;
* the harness's state directories, each replaced by the worker's own (transcripts and sessions included), with
  only the user's named auth *files* written through and the user's settings, hooks, plugins, skills, rules and
  instruction files read-only (:data:`HARNESS_STATE`); configuration it must write that can hold launch
  instructions (``~/.claude.json``, Cursor's ``cli-config.json``) is a per-worker copy.

The rule for the home directory: **no directory of the user's is writable from the sandbox, and only the named
auth files are.** Any writable directory is an open namespace (a transcript directory takes a ``memory/``
file the harness reads as instructions just as well), so none is shared. The cost: a worker's transcripts and
sessions stay in ``work/.workers/<id>.state/``, where its own resumes and the runner find them, and a human
``--resume`` from the user's home does not.

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

#: The one rule for harness state. Per harness: its state directories, each ``(env var that relocates it, path
#: under home, auth files written through to the user's, entries read-only from the user's)``, and its seeded
#: files ``(env var, path under home)``. A directory the worker sees is its own; only the named auth files reach
#: the user's (a directory there is never bound writable), and the user's settings, hooks, plugins, skills, rules,
#: MCP and instruction files are read-only. Anything else the harness writes, transcripts and sessions included,
#: stays the worker's. A seeded file is writable configuration that can carry launch instructions: a per-worker
#: copy.
HARNESS_STATE: dict[str, tuple[tuple[tuple[str | None, str, tuple[str, ...], tuple[str, ...]], ...],
                               tuple[tuple[str | None, str], ...]]] = {
    "claude-code": ((("CLAUDE_CONFIG_DIR", ".claude", (".credentials.json",),
                      ("settings.json", "settings.local.json", "hooks", "plugins", "skills", "agents", "commands",
                       "output-styles", "CLAUDE.md")),
                     (None, ".cache", (), ())),
                    ((None, ".claude.json"), ("CLAUDE_CONFIG_DIR", ".claude/.claude.json"))),
    "cursor": (((None, ".cursor", (),
                 ("hooks", "hooks.json", "mcp.json", "plugins", "rules", "skills", "skills-cursor", "extensions")),
                (None, ".config/cursor", ("auth.json",), ()),
                (None, ".cache", (), ())),
               ((None, ".cursor/cli-config.json"),)),
    "codex": ((("CODEX_HOME", ".codex", ("auth.json",),
                ("config.toml", "AGENTS.md", "hooks", "plugins", "rules", "skills")),),
              ()),
}

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
    state: Path | None = None                   # the worker's own home for harness state (transcripts) when sandboxed
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
        _seed_outbox(reviews, outbox)
        (common / "logs").mkdir(exist_ok=True)       # a commit's reflog goes here
        harness = _harness_binds(repo_root, rec, env)
    except OSError as e:
        raise SandboxError(f"cannot set up the sandbox: {e}") from e
    tree = common / "worktrees" / name
    argv = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
            "--die-with-parent", "--bind", str(wt), str(wt),
            *_binds("--bind", [common / "objects", common / "refs", common / "logs", tree]),
            # What points git at a repository or config, read-only; config.worktree empty when absent.
            *_binds("--ro-bind", [wt / ".git", tree / "commondir", tree / "gitdir"]),
            "--ro-bind", str(tree / "config.worktree") if (tree / "config.worktree").is_file() else os.devnull,
            str(tree / "config.worktree"),
            "--bind", str(outbox), str(reviews), *harness]
    for d in HIDDEN_HOME:
        if (Path.home() / d).exists():
            argv += ["--tmpfs", str(Path.home() / d)]
    for k in HIDDEN_ENV:
        env.pop(k, None)
    return Box("bwrap", [*argv, "--chdir", str(wt)], outbox=outbox, reviews=reviews,
               state=state_home(repo_root, rec.worker_id))


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


def _binds(flag: str, paths: list[Path], *, at: list[Path] | None = None) -> list[str]:
    """``flag src dest`` for each source that exists (``dest`` from ``at``, else the source itself): bwrap cannot
    make a mount point on the read-only root."""
    return [a for p, d in zip(paths, at or paths) if p.exists() for a in (flag, str(p), str(d))]


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
    if not line.startswith("gitdir:") or gitdir.parent != common / "worktrees" or not (gitdir / "gitdir").is_file():
        raise SandboxError(need)
    return wt, common, gitdir.name


def _harness_binds(repo_root: Path, rec: WorkerRecord, env: dict[str, str]) -> list[str]:
    """The bwrap arguments for ``rec.harness``'s state, by the rule in :data:`HARNESS_STATE`.

    Each state directory the user has is replaced by the worker's own (``work/.workers/<id>.state/``, kept across
    its turns); into it go the user's auth files (writable) and steering entries (read-only), each only when the
    user has it, and an auth name the user has as a directory is not bound. A seeded file is copied from the user's once and bound writable over its path.
    """
    own = state_home(repo_root, rec.worker_id)
    dirs, seeds = HARNESS_STATE.get(rec.harness, ((), ()))
    argv: list[str] = []
    for var, rel, through, steering in dirs:
        user = _state_path(env, var, rel)
        if user.is_dir():
            mine = own / rel.replace("/", "_")
            mine.mkdir(parents=True, exist_ok=True)
            auth = [n for n in through if (user / n).resolve().is_file()]   # files only: never a directory
            argv += ["--bind", str(mine), str(user),
                     *_binds("--bind", [(user / n).resolve() for n in auth], at=[user / n for n in auth]),
                     *_binds("--ro-bind", [user / n for n in steering])]
    for var, rel in seeds:
        user = _state_path(env, var, rel)
        copy = own / ("seed" + rel.replace("/", "_"))
        if user.is_file():
            if not copy.is_file():
                own.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(user, copy)
                copy.chmod(0o600)
            argv += ["--bind", str(copy), str(user)]
    return argv


def state_home(repo_root: Path, worker_id: str) -> Path:
    """The worker's own home for harness state: ``<state dir path under home>`` with ``/`` as ``_`` beneath it
    (``.claude``, ``.cursor``, ``.config_cursor``), so ``ClaudeCode.transcript_limit(home=...)`` finds its
    transcripts at ``.claude/projects``."""
    return workers_dir(repo_root) / f"{worker_id}.state"


def _state_path(env: dict[str, str], var: str | None, rel: str) -> Path:
    """``rel`` under ``$var`` when the harness environment sets it (its first segment is the directory ``$var``
    replaces), else under the home directory."""
    if var and env.get(var):
        return Path(env[var], *Path(rel).parts[1:])
    return Path.home() / rel


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


def _seed_outbox(reviews: Path, outbox: Path) -> None:
    """Copy the regular files under ``reviews`` into ``outbox``, keeping the layout; a link is not followed or
    copied."""
    for top, dirs, files in os.walk(reviews):
        here = Path(top)
        dest = outbox / here.relative_to(reviews)
        dirs[:] = [d for d in dirs if not (here / d).is_symlink()]
        for d in dirs:
            (dest / d).mkdir(mode=0o700)
        for f in files:
            if (here / f).is_file() and not (here / f).is_symlink():
                shutil.copy2(here / f, dest / f)


def _deliver_ready(outbox: Path, reviews: Path) -> None:
    """Move each regular ``READY-*`` file from the outbox into ``reviews``; nothing else written there is kept."""
    try:
        for p in outbox.iterdir():
            if p.name.upper().startswith(READY_PREFIX.upper()) and p.is_file() and not p.is_symlink():
                shutil.move(str(p), str(reviews / p.name))
    finally:
        shutil.rmtree(outbox, ignore_errors=True)
