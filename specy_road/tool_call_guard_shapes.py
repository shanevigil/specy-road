"""Command shapes the shared-checkout guard refuses because it cannot see what runs (split from tool_call_guard).

Three families: git configuration supplied through the environment (review
round 6, B1), a git verb that is not a literal word (B15), and a commit or
add pathspec that names more than explicit files (B17). Each returns the
reason to deny, or ``None``.
"""

from __future__ import annotations

import re

#: Environment variables through which git reads configuration — and so aliases — the guard cannot see.
_ENV_CONFIG = re.compile(r"^GIT_CONFIG(_COUNT|_PARAMETERS|_GLOBAL|_SYSTEM|_KEY_\d+|_VALUE_\d+)?=")
_EXPANSION = re.compile(r"[$`]")
#: ``NAME=value`` anywhere in a command (quoted or bare value).
_ASSIGN = re.compile(r"(?<![\w$])([A-Za-z_]\w*)=(?:'([^']*)'|\"([^\"]*)\"|([^\s;&|()'\"]*))")
#: Pathspec shapes that reach beyond explicit files: tree roots, parents, pathspec magic, globs.
_BROAD_PATHSPEC = re.compile(r"^(\.|\./.*|\.\.|\.\./.*|/.*|:.*|.*[*?\[].*)$")
#: ``git commit`` / ``git add`` flags that take a value, so the value is not mistaken for a pathspec.
_VALUE_FLAGS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date", "--reuse-message",
                "--reedit-message", "--template", "--trailer", "--fixup", "--squash"}


def env_config(tokens: list[str]) -> str | None:
    """A ``GIT_CONFIG*`` assignment ahead of a git command, or ``--config-env`` naming an alias.

    ``GIT_CONFIG_COUNT``/``_KEY_n``/``_VALUE_n``, ``GIT_CONFIG_PARAMETERS`` and
    ``GIT_CONFIG`` / ``_GLOBAL`` / ``_SYSTEM`` can all define ``alias.x = !git
    stash`` after the guard has stripped the assignment; a config file
    pointed to by an env var is not readable at decision time. Fail closed.
    """
    git_at = next((i for i, t in enumerate(tokens) if t.rsplit("/", 1)[-1] == "git"), None)
    if git_at is None:
        return None
    if any(_ENV_CONFIG.match(t) for t in tokens[:git_at]):
        return "GIT_CONFIG* in the environment can define a git alias the guard cannot see; run the git command plainly"
    for i in range(git_at + 1, len(tokens)):
        t = tokens[i]
        if not t.startswith("-"):
            break
        key = t[13:] if t.startswith("--config-env=") else (tokens[i + 1] if t == "--config-env" and i + 1 < len(tokens) else "")
        if key.startswith("alias."):
            return "git --config-env=alias.*: the alias body lives in the environment where the guard cannot see it"
    return None


def inline_git_vars(command: str) -> str:
    """``G=git; ${G} stash`` is ``git stash`` to the guard: a variable assigned a git value is expanded in place.

    Only a value whose first word is ``git`` (or a path to it) is inlined; any
    other variable stays a variable and is judged as before.
    """
    for m in _ASSIGN.finditer(command):
        value = next((v for v in m.groups()[1:] if v is not None), "")
        if re.match(r"(\S*/)?git(\s|$)", value):
            command = re.sub(rf"\$\{{{m.group(1)}\b[^}}]*\}}|\${m.group(1)}\b", lambda _m: value, command)
    return command


def eval_opaque(args: list[str], segment: str) -> str | None:
    """``eval`` of an expansion that mentions git runs text the guard cannot see; a literal ``eval "git …"`` is judged."""
    if any(_EXPANSION.search(a) for a in args) and re.search(r"\bgit\b", segment):
        return "eval of a shell expansion that mentions git; the guard cannot see what runs — run the git command plainly"
    return None


def dynamic_verb(sub: str | None) -> str | None:
    """A git subcommand produced by ``$(…)``, ``${…}``, ``$x`` or backticks is not a word the guard can judge."""
    if sub and _EXPANSION.search(sub):
        return "the git subcommand comes from a shell expansion; the guard cannot see it — write the verb literally"
    return None


def pathspec(args: list[str]) -> list[str]:
    """The paths a ``git commit`` / ``git add`` names, skipping the values of ``-m`` and friends."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return [*out, *args[i + 1:]]
        if a in _VALUE_FLAGS:
            i += 2
            continue
        if not a.startswith("-"):
            out.append(a)
        i += 1
    return out


def broad_pathspec(verb: str, args: list[str]) -> str | None:
    """A pathspec that is a tree root, a parent, pathspec magic, a glob, an absolute path, or read from a file.

    ``git commit --only .`` sweeps every session's change like a bare commit;
    ``:/``, ``:(glob)**`` and ``*`` reach as far, and ``--pathspec-from-file``
    names paths the guard cannot read. A plain directory such as ``src/`` is
    scoped and passes: the caller vouches for that directory.
    """
    hit = next((a for a in args if a.startswith("--pathspec-from-file")), None) \
        or next((p for p in pathspec(args) if _BROAD_PATHSPEC.match(p)), None)
    if hit is None:
        return None
    return (f"git {verb} {hit}: a tree root, parent, pathspec magic, glob, absolute path or pathspec file can sweep other sessions' "
            f"files; name explicit repo-relative files")
