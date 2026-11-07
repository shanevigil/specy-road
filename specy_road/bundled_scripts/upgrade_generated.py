"""``specy-road upgrade``: the generated files it rewrites, and the environment of its scratch copy.

Split out of ``upgrade.py`` to keep that module under its line cap.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from specy_road import git_subprocess
from specy_road.bundled_scripts.export_roadmap_md import export_markdown
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.digest import DEFAULT_OUTPUT, render_digest
from specy_road.ignore_report import isolate_git, scratch_git_env
from specy_road import safe_write
from specy_road.managed_block import refused_link

COPY = "the temporary copy"


class GitFailed(Exception):
    """A git call upgrade depends on failed; ``run_upgrade`` prints it and returns 2."""


def checked(r: git_subprocess.GitResult, command: str, where: str = COPY, ok: tuple[int, ...] = (0,)) -> None:
    """Raise :class:`GitFailed` unless ``r`` exited with a code in ``ok``: every git call upgrade depends on ends here."""
    if r.code not in ok:
        lines = r.message.splitlines()
        reason = "timed out" if r.failure == "timeout" else lines[-1] if lines else f"exit {r.code}"
        raise GitFailed(f"git {command} failed in {where} ({reason})")


@contextlib.contextmanager
def scratch_environ(tmp: Path | None):
    """One stretch of an upgrade: no ``GIT_`` variable of the caller's reaches git.

    With ``None``, ``os.environ`` is the caller's with every ``GIT_`` variable
    removed and nothing else changed. The checkout still reads the caller's own
    config files, and the ignore-report isolation is left as it was. With a
    path, git also reads no global or system config (``GIT_CONFIG_NOSYSTEM`` and
    an empty ``GIT_CONFIG_GLOBAL``) and :func:`isolate_git` points at that
    scratch directory: the plan's mirror and the dry run's copy.

    Yields the caller's environment with ``GIT_`` variables dropped and nothing
    else changed, for the one git call that reads the caller's own checkout.
    On exit the previous ``os.environ`` is restored and, when this stretch
    isolated, so is the previous ignore-report isolation.
    """
    saved, caller = os.environ.copy(), scratch_git_env()
    env = caller if tmp is None else scratch_git_env(tmp)
    os.environ.clear()
    os.environ.update(env)
    previous = isolate_git(tmp) if tmp is not None else None
    try:
        yield caller
    finally:
        if tmp is not None:
            isolate_git(previous)
        os.environ.clear()
        os.environ.update(saved)


def use_live_history(copy: Path, live: Path, caller_env: dict[str, str]) -> None:
    """Give the scratch repository ``copy`` the history of ``live``, so its digest reads what the real run reads.

    The digest asks git through the directory it renders: commits and trailers from ``HEAD``, and the milestone
    hold from the integration ref a remote's tracking refs name. So ``copy`` takes ``live``'s ``HEAD``, refs and
    remote names; a shallow checkout's boundary too, or its log would fail on the missing parents. Objects are
    read through ``objects/info/alternates``, which git never writes to, and nothing else links to ``live``: the
    copy's own config, index and new objects stay in the copy, and its remotes are never fetched.

    The questions go to the checkout under ``caller_env``, as in :func:`regenerate`.
    """
    def ask(*args: str) -> str:
        r = git_subprocess.run(list(args), live, env=caller_env)
        checked(r, args[0], "the checkout")
        return r.out

    objects, shallow, head = (live / line for line in ask(
        "rev-parse", "--git-path", "objects", "--git-path", "shallow", "--git-path", "HEAD").splitlines())
    refs = ask("for-each-ref", "--format=%(objectname) %(refname)")
    remotes = ask("remote").split()
    git_dir = copy / ".git"
    (git_dir / "objects" / "info" / "alternates").write_text(f"{objects.resolve()}\n", encoding="utf-8")
    shutil.rmtree(git_dir / "refs")
    (git_dir / "refs").mkdir()
    (git_dir / "packed-refs").write_text(refs, encoding="utf-8")
    shutil.copyfile(head, git_dir / "HEAD")
    if shallow.is_file():
        shutil.copyfile(shallow, git_dir / "shallow")
    for name in remotes:
        checked(git_subprocess.run(["remote", "add", name, str(live)], copy), "remote add")


def regenerate(project: Path, tracked_in: Path, verb: str, caller_env: dict[str, str]) -> bool:
    """Write each drifted generated file into ``project``: the digest, and ``roadmap.md`` if ``tracked_in`` tracks it.

    ``tracked_in`` is the checkout's project: a dry run renders and writes into its
    copy, whose index tracks everything. A path the safe-write rule
    refuses (a symlink of any kind) is refused before it is read; the rest are compared as bytes, so a
    file that is not UTF-8 is drifted, not an error. Returns whether a path was refused.

    The question goes to the caller's checkout, under their own config (``caller_env``,
    their environment without ``GIT_`` variables), with only the command-running
    ``core.fsmonitor`` off. Exit 1 is untracked; any other failure raises
    :class:`GitFailed` before a file is written.
    """
    r = git_subprocess.run(["-c", "core.fsmonitor=false", "ls-files", "--error-unmatch", "roadmap.md"], tracked_in,
                           env=caller_env)
    checked(r, "ls-files", "the checkout" if project == tracked_in else COPY, ok=(0, 1))
    tracked = r.ok
    files = [(DEFAULT_OUTPUT, render_digest(project), "specy-road digest")]
    if tracked:
        files.append(("roadmap.md", export_markdown(load_roadmap(project)["nodes"]), "specy-road export"))
    refused = wrote = False
    for rel, body, command in files:
        path = project / rel
        if why := refused_link(project, path):   # checked before any read: a link is never opened
            print(f"refused {rel} ({why})")
            refused = wrote = True
            continue
        if path.is_file() and path.read_bytes() == body.encode("utf-8"):
            continue
        wrote = True
        safe_write.write(project, path, body)
        print(f"{verb} {rel} ({command})")
    if not wrote:
        print("generated files already current")
    return refused
