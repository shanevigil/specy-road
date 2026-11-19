"""Decide whether a shell command is safe to run in a checkout other agents share.

The guard behind ``specy-road session guard`` and the harness hook adapters
(proposal §3.4, §3.5; agent-guidance and shared-checkouts design note,
decision 6).

A command is **destructive in a shared tree** when it can move or discard
work that is not the caller's: anything that stashes, resets, switches
branches, discards working-tree changes, rewrites history, force-pushes, or
sweeps every change into a commit. Each ``git`` segment of a chained command
is classified on its own, so ``make test && git stash`` is caught.

The verdict is **deny only when another live session is present** (per
``work/.sessions/``), or when the caller asks for ``always``. Alone in a
tree, these commands are the agent's own business; the rules exist to keep
one session from landing on another.

Harness adapters live here too, one per protocol. Each knows how to find the
command in what its harness sends and how to say allow or deny the way that
harness expects. ``generic`` is the contract the others are built on.
"""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.orchestration.guard import tool_call_guard_shapes as shapes
from specy_road.git_subprocess import git_root, git_text
from specy_road.orchestration.guard.session_presence import list_sessions, unreadable_records

ALLOW = "allow"
DENY = "deny"

_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")
#: Wrapper flags that take an argument (``sudo -u bob``, ``env -u VAR``).
_WRAPPER_FLAG_ARG = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-n", "--user", "--group", "--unset",
                     "--chdir", "--adjustment", "--host", "--prompt", "--role", "--type", "--other-user", "--max-args",
                     "--max-procs", "--delimiter", "--arg-file", "--replace", "--signal", "--kill-after"}
_GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
#: Words that merely wrap the real command: ``command git …``, ``env X=1 git …``.
#: Matched by basename, as ``git`` is: ``/usr/bin/sudo`` is ``sudo``.
_WRAPPERS = {"command", "env", "sudo", "nohup", "exec", "time", "nice", "xargs", "timeout", "doas", "ionice"}
#: Wrappers whose first positional is not the command (``timeout 10 git …``).
_WRAPPER_LEADING_ARG = {"timeout"}
#: Shell words that open a command without being one: ``(``, ``{``, ``if``/``then``/``do``…, ``!``.
_OPENERS = {"(", "{", "if", "then", "elif", "else", "while", "until", "do", "!"}
# GNU coreutils 9.4 ``env``: ``getopt_long`` shortopts ``+C:iS:u:v0``.
# A long option matches by an unambiguous prefix (an exact name wins). Its value is attached
# with ``=`` or, when required, taken from the next argument. Short options cluster; one that
# takes a value takes the rest of the cluster or the next argument. The leading ``+`` stops at
# the first non-option. A lone ``-`` is ``-i`` and ends options. After ``-S`` / ``--split-string``,
# coreutils appends the remaining arguments to that command and does not parse them as options.
_ENV_LONG: tuple[tuple[str, str, str], ...] = (
    ("ignore-environment", "no", "i"),
    ("null", "no", "0"),
    ("unset", "required", "u"),
    ("chdir", "required", "C"),
    ("split-string", "required", "S"),
    ("block-signal", "optional", ""),
    ("default-signal", "optional", ""),
    ("ignore-signal", "optional", ""),
    ("list-signal-handling", "no", ""),
    ("debug", "no", "v"),
    ("help", "no", ""),
    ("version", "no", ""),
)
_ENV_BY_SHORT = {short: (name, kind) for name, kind, short in _ENV_LONG if short}
#: Reasons about the working tree only; other worktrees' sessions are not at risk.
_TREE_SCOPED = ("git switch", "git checkout", "git restore", "git clean", "git commit", "git add", "git reset")
#: ``git -C <dir>`` / ``--work-tree`` act on another tree: never scope those to the caller's.
_NAMES_A_TREE = re.compile(r"(^|\s)(-C\S*|--work-tree(=|\s)|--git-dir(=|\s))")
_GIT_WORD = re.compile(r"\bgit\b")
#: Shell expansion in a word: parameter/command substitution, brace expansion, globs.
_EXPANSION = re.compile(r"[$`*?\[]|\{[^}]*(,|\.\.)")
_EXPANSION_SYNTAX = re.compile(r"\$\{[^}]*\}|\$\w+|[$`{}*?\[\],]")
#: ``${NAME:-word}`` / ``${NAME=word}``: the word the author wrote as the fallback.
_DEFAULT = re.compile(r"\$\{\w+:?[-=]([^}]*)\}")
_FUNC_DEF = re.compile(r"(^|[\s;(])\w+\s*\(\s*\)\s*\{")
_INTERPRETERS = {"python", "python3", "perl", "ruby", "node", "php"}
#: ``$(…)``, ``<(…)``, ``>(…)`` and backticks all run their body as a command.
_SUBSTITUTION = re.compile(r"[$<>]\(([^()]*)\)|`([^`]*)`")
_UNBALANCED = re.compile(r"[$<>]\(")
_KNOWN_GIT = {"add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "checkout",
              "cherry-pick", "clean", "clone", "commit", "config", "describe", "diff", "fetch", "format-patch",
              "gc", "grep", "init", "log", "ls-files", "ls-remote", "merge", "merge-base", "mv", "notes", "pull",
              "push", "rebase", "reflog", "remote", "reset", "restore", "rev-list", "rev-parse", "revert", "rm",
              "shortlog", "show", "stash", "status", "submodule", "switch", "tag", "worktree"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}


@dataclass
class Verdict:
    decision: str
    reason: str
    command: str

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW


def split_segments(command: str) -> list[str]:
    """Split on ``&&``, ``||``, ``;``, ``|``, ``&`` and newlines — outside quotes."""
    out, buf, quote, i = [], [], None, 0
    while i < len(command):
        ch = command[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            elif ch == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 1
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        sep = next((x for x in _SEPARATORS if command.startswith(x, i)), None)
        if sep:
            out.append("".join(buf))
            buf = []
            i += len(sep)
            continue
        buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


@dataclass(frozen=True)
class _EnvRun:
    ok: bool
    split: bool
    command: tuple[str, ...]
    shell: str
    determined: bool = True
    source: str = ""
    ate_option: bool = False


def _env_long_name(name: str) -> tuple[str, str] | None:
    """``(kind, canonical)`` when ``name`` is an unambiguous long option, else ``None``."""
    matches = [row for row in _ENV_LONG if row[0].startswith(name)]
    exact = [row for row in matches if row[0] == name]
    chosen = exact[0] if exact else (matches[0] if len(matches) == 1 else None)
    if chosen is None:
        return None
    return chosen[1], chosen[0]


def _env_long_at(tokens: list[str], i: int) -> tuple[int, str, str | None] | None:
    """One long option at ``tokens[i]``: ``(next index, canonical name, value)``, or ``None``."""
    name, sep, attached = tokens[i][2:].partition("=")
    matched = _env_long_name(name)
    if matched is None:
        return None
    kind, canonical = matched
    if kind == "no":
        return None if sep else (i + 1, canonical, None)
    if kind == "optional":
        return i + 1, canonical, (attached if sep else None)
    if sep:
        return i + 1, canonical, attached
    if i + 1 >= len(tokens):
        return None
    return i + 2, canonical, tokens[i + 1]


def _env_short_at(tokens: list[str], i: int) -> tuple[int, list[tuple[str, str | None]]] | None:
    """One short cluster: ``(next index, [(canonical name, value), ...])``, or ``None``."""
    arg, j, taken = tokens[i], 1, []
    while j < len(arg):
        spec = _ENV_BY_SHORT.get(arg[j])
        if spec is None:
            return None
        name, kind = spec
        if kind != "required":
            taken.append((name, None))
            j += 1
            continue
        rest = arg[j + 1:]
        if rest:
            taken.append((name, rest))
            return i + 1, taken
        if i + 1 >= len(tokens):
            return None
        taken.append((name, tokens[i + 1]))
        return i + 2, taken
    return i + 1, taken


# GNU coreutils 9.4 ``env -S``: unquoted whitespace separates words. These escapes insert a
# character (they are not themselves separators — a following scan does not re-split them).
_ENV_WS = frozenset(" \t\n\v\f\r")
_ENV_ESC = {"\\": "\\", "'": "'", '"': '"', "t": "\t", "n": "\n", "r": "\r", "v": "\v", "f": "\f", "#": "#", "$": "$"}
_ENV_SPLIT_OPAQUE = "env -S splits its argument into a command the guard cannot see; run the git command plainly"


def _env_flush(cur: list[str], argv: list[str]) -> None:
    if cur:
        argv.append("".join(cur))
        cur.clear()


def _env_split_escape(value: str, i: int, dq: bool, cur: list[str], argv: list[str]) -> int | None:
    """The index after one backslash escape, or ``None`` when env would reject it."""
    if i + 1 >= len(value):
        return None
    nxt = value[i + 1]
    if nxt == "c":
        if dq:
            return None
        _env_flush(cur, argv)
        return len(value)
    if nxt == "_" and not dq:
        _env_flush(cur, argv)
        return i + 2
    if nxt == "_":
        cur.append(" ")
        return i + 2
    mapped = _ENV_ESC.get(nxt)
    if mapped is None:
        return None
    cur.append(mapped)
    return i + 2


def _env_split_plain(value: str, i: int, dq: bool, cur: list[str], argv: list[str]) -> tuple[int, bool] | None:
    """One unquoted or double-quoted character. ``None`` means ``$`` / ``${VAR}``."""
    ch = value[i]
    if ch == '"':
        return i + 1, not dq
    if not dq and ch in _ENV_WS:
        _env_flush(cur, argv)
        return i + 1, dq
    if ch == "$":
        return None
    if not dq and ch == "#" and not cur:
        _env_flush(cur, argv)
        return len(value), dq
    cur.append(ch)
    return i + 1, dq


def _env_split_argv(value: str) -> tuple[str, ...] | None:
    """GNU coreutils 9.4 ``-S`` words, or ``None`` when an escape cannot be known.

    ``None`` is an unknown escape, a trailing backslash, ``\\c`` inside double quotes,
    or ``$`` / ``${VAR}`` outside single quotes: the command needs runtime state.
    Single quotes keep every character except ``\\\\`` and ``\\'``.
    """
    argv, cur = [], []
    i, sq, dq = 0, False, False
    while i < len(value):
        ch = value[i]
        nxt = value[i + 1] if i + 1 < len(value) else ""
        if sq:
            if ch == "\\" and nxt in "\\'":
                cur.append(nxt)
                i += 2
                continue
            if ch == "'":
                sq = False
            else:
                cur.append(ch)
            i += 1
            continue
        if ch == "\\":
            i = _env_split_escape(value, i, dq, cur, argv)
            if i is None:
                return None
            continue
        if ch == "'" and not dq:
            sq = True
            i += 1
            continue
        step = _env_split_plain(value, i, dq, cur, argv)
        if step is None:
            return None
        i, dq = step
    _env_flush(cur, argv)
    return tuple(argv)


def _env_from_split(value: str, trailing: list[str]) -> _EnvRun:
    """Words ``-S`` builds, then parsed again as env options before the command.

    ``--unset`` and ``--chdir`` inside the split string consume the next word, so
    that word is not the command. ``ate_option`` is set when this rescan changes
    the words. A nested split that cannot be known (a ``$`` / ``${VAR}`` or an
    unknown escape) stays unknowable.
    """
    words = _env_split_argv(value)
    extra = " ".join(shlex.quote(part) for part in trailing)
    source = f"{value} {extra}" if extra else value
    if words is None:
        return _EnvRun(True, True, (), source, False, source)
    parsed = _env_invocation(["env", *words, *trailing])
    if not parsed.ok:
        return _EnvRun(False, False, (), source)
    if not parsed.determined:
        return parsed
    command = parsed.command
    whole = (*words, *trailing)
    removed = whole[:len(whole) - len(command)]
    ate = any(word.startswith("-") for word in removed)
    return _EnvRun(True, True, command, shlex.join(command), True, source, ate)


def _env_invocation(tokens: list[str]) -> _EnvRun:
    """What GNU coreutils 9.4 ``env`` runs for ``tokens`` that start with ``env``.

    ``ok`` is false when env rejects the options. A split-string is decoded and its
    words are parsed as options again. The command starts at the first non-option
    and keeps every ``NAME=VALUE`` word, so a ``GIT_CONFIG*`` assignment is still
    classified wherever it sits among env's arguments.
    """
    i, bad = 1, _EnvRun(False, False, (), "")
    while i < len(tokens):
        arg = tokens[i]
        if arg in ("--", "-"):
            i += 1
            break
        if arg.startswith("--"):
            step = _env_long_at(tokens, i)
            if step is None:
                return bad
            i, canonical, value = step
            if canonical == "split-string":
                return _env_from_split(value or "", tokens[i:])
            continue
        if arg.startswith("-"):
            short = _env_short_at(tokens, i)
            if short is None:
                return bad
            i, taken = short
            split = next((val for name, val in taken if name == "split-string"), None)
            if split is not None:
                return _env_from_split(split, tokens[i:])
            continue
        break
    return _EnvRun(True, False, tuple(tokens[i:]), "")


def _is_opaque_subject(tokens: list[str], i: int) -> bool:
    """``env``'s split-string, or a ``GIT_CONFIG*`` assignment: the opaque checks judge it.

    ``env`` is the basename, so ``/usr/bin/env`` is the same subject as ``env``.
    """
    token = tokens[i]
    if token.rsplit("/", 1)[-1] == "env":
        parsed = _env_invocation(tokens[i:])
        return bool(parsed.ok and (parsed.split or shapes.env_config(tokens[i:])))
    return bool(shapes.env_config([token, "git"]))


def _skip_wrapper(tokens: list[str], i: int, wrapped: bool) -> tuple[list[str], int, bool] | None:
    """Advance past one wrapper word. ``env`` is replaced by the command it would run.

    The word's basename is the wrapper, as ``git`` already is: ``/usr/bin/env`` is ``env``.
    """
    t = tokens[i]
    name = t.rsplit("/", 1)[-1]
    if name == "env":
        parsed = _env_invocation(tokens[i:])
        if parsed.ok:
            return [*tokens[:i], *parsed.command], i, False
    if name in _WRAPPERS:
        return tokens, i + (2 if name in _WRAPPER_LEADING_ARG else 1), True
    if wrapped and t.startswith("-"):
        step = 2 if t in _WRAPPER_FLAG_ARG and "=" not in t else 1
        return tokens, i + step, wrapped
    return None


def _unwrap(tokens: list[str], *, keep_signals: bool = False) -> list[str]:
    """Strip ``VAR=x``, ``command``/``env``/``sudo``-style wrappers, control-flow openers, and subshell parens.

    A ``(`` glued to the next word is peeled and that word is read, including when an opener
    precedes it (``! (git stash)``). ``env``'s options are read with getopt, so ``--unset`` and
    ``--chdir`` consume their values. With ``keep_signals``, unwrapping stops at ``env``'s
    split-string or a ``GIT_CONFIG*`` assignment so the opaque checks still see them.
    """
    i = 0
    wrapped = False
    while i < len(tokens):
        t = tokens[i]
        if keep_signals and _is_opaque_subject(tokens, i):
            break
        if t.startswith("(") and len(t) > 1:
            tokens = [*tokens[:i], t[1:], *tokens[i + 1:]]  # re-read the word the parenthesis hid
            continue
        if ("=" in t and not t.startswith("-")) or t in _OPENERS:
            i += 1
            continue
        step = _skip_wrapper(tokens, i, wrapped)
        if step is None:
            break
        tokens, i, wrapped = step
    out = tokens[i:]
    return [t.rstrip(")") if t.endswith(")") and t != ")" else t for t in out if t not in (")", "}")]


def _git_subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    """``(subcommand, its args)`` for a ``git …`` token list, else ``(None, [])``.

    ``/usr/bin/git`` counts as ``git``; a ``-c alias.<name>=<cmd>`` whose
    alias is the subcommand is expanded, so ``git -c alias.s=stash s`` is
    ``git stash``; a ``!`` alias comes back as ``("!", [shell command])``.
    A ``git`` word after the head (``case … in a) git …``, ``find -exec git …``)
    is read from there: it may run, so it is judged.
    """
    tokens = _unwrap(tokens)
    at = next((j for j, t in enumerate(tokens) if t.rsplit("/", 1)[-1] == "git"), None)
    if at is None:
        return None, []
    tokens = tokens[at:]
    i = 1
    aliases: dict[str, str] = {}
    while i < len(tokens) and tokens[i].startswith("-"):
        if tokens[i].startswith("-C") and len(tokens[i]) > 2:   # attached: git -C/other/tree
            i += 1
            continue
        if tokens[i] in _GIT_GLOBAL_WITH_ARG:
            if tokens[i] == "-c" and i + 1 < len(tokens) and tokens[i + 1].startswith("alias."):
                name, _eq, value = tokens[i + 1][6:].partition("=")
                aliases[name] = value
            i += 2
        elif tokens[i].startswith("-c") and len(tokens[i]) > 2 and tokens[i][2:].startswith("alias."):
            name, _eq, value = tokens[i][8:].partition("=")
            aliases[name] = value
            i += 1
        else:
            i += 1
    if i >= len(tokens):
        return None, []
    sub, rest = tokens[i], tokens[i + 1:]
    if sub in aliases:
        if aliases[sub].startswith("!"):
            return "!", [aliases[sub][1:], *rest]   # a bang alias is a shell command; classified as one
        expanded = shlex.split(aliases[sub]) if aliases[sub] else []
        if expanded:
            return expanded[0], [*expanded[1:], *rest]
    return sub, rest


def _short_flags(args: list[str]) -> str:
    """Letters from every clustered short flag (``-am`` → ``am``)."""
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--") and len(a) > 1)


def classify_segment(segment: str) -> str | None:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    """The reason a single command is destructive in a shared tree, else ``None``.

    A segment that will not parse but mentions ``git`` is treated as
    destructive: an unbalanced quote around a git command is exactly the
    shape a guard must not wave through. ``sh -c '…'`` is classified by what
    it runs.
    """
    rest = segment
    for _ in range(8):                               # `$(git …)` and `\`git …\`` run too, nested as well
        hit = False
        for m in _SUBSTITUTION.finditer(rest):
            hit = True
            inner = classify(m.group(1) or m.group(2) or "")
            if inner:
                return inner
        if not hit:
            break
        rest = _SUBSTITUTION.sub(" x ", rest)
    if _UNBALANCED.search(rest) and _GIT_WORD.search(segment):
        return "unbalanced command substitution mentioning git; rewrite it plainly"
    opaque = _opaque(segment)
    if opaque:
        return opaque
    try:
        tokens = shlex.split(segment, comments=True)
    except ValueError:
        return ("could not parse this shell command and it mentions git; rewrite it plainly"
                if re.search(r"\bgit\b", segment) else None)
    inner = _unwrap(tokens)
    if inner and inner[0] == "eval":                 # eval joins its arguments and re-parses: `eval "git stash"`
        return shapes.eval_opaque(inner[1:], segment) or classify(" ".join(inner[1:]))
    if inner and inner[0].rsplit("/", 1)[-1] in _SHELLS:
        for j, t in enumerate(inner[1:], 1):
            if t in ("-c", "-lc", "-ic", "-ec", "-xc") or (t.startswith("-") and "c" in t[1:] and len(t) <= 4):
                return classify(inner[j + 1]) if j + 1 < len(inner) else None
    sub, args = _git_subcommand(tokens)
    if sub is None:
        return None
    if sub == "!":
        return classify(" ".join(args))
    if shapes.dynamic_verb(sub):
        return shapes.dynamic_verb(sub)
    flags = _short_flags(args)
    positional = [a for a in args if not a.startswith("-")]
    if sub == "stash":
        return "git stash: the stash stack is shared by every session in this checkout"
    if sub == "reset" and any(a in ("--hard", "--merge", "--keep") for a in args):
        return f"git reset {next(a for a in args if a.startswith('--'))}: discards other sessions' uncommitted work"
    if sub == "switch" or (sub == "checkout" and ("--" not in args) and (positional or "b" in flags or "B" in flags or "--orphan" in args)):
        return f"git {sub}: switching branches moves every other session's working tree too; use `git worktree add`"
    if sub == "checkout" and ("--" in args or "f" in flags or "--force" in args):
        return "git checkout -- <paths> / -f: discards working-tree changes that may be another session's"
    staged_only = ("S" in flags or "--staged" in args) and "W" not in flags and "--worktree" not in args
    if sub == "restore" and positional and (not staged_only or "." in positional or ":/" in positional):
        return "git restore <paths>: discards other sessions' uncommitted changes to those files"
    if sub == "clean" and ("f" in flags or "--force" in args):
        return "git clean -f: deletes untracked files other sessions are still writing"
    if sub == "rm" and ("f" in flags or "--force" in args):
        return "git rm -f: deletes files along with uncommitted changes that may be another session's"
    if sub == "rebase":
        return "git rebase: rewrites history under other sessions' feet"
    if sub == "commit" and "--amend" in args:
        return "git commit --amend: rewrites a commit another session may already build on"
    if sub == "commit" and ("a" in flags or "--all" in args):
        return "git commit -a: sweeps every session's tracked changes into your commit; stage by explicit path"
    if sub == "commit" and not shapes.pathspec(args) and "--only" not in args:
        return "git commit without paths: commits whatever another session staged in the shared index; `git commit --only <paths>`"
    if sub == "add" and ("A" in flags or "u" in flags or "--all" in args or "--update" in args
                         or any(p in (".", ":/", "-A") for p in positional)):
        return "git add -A/-u/.: stages other sessions' files; `git add <paths>` only"
    if sub in ("commit", "add", "rm") and shapes.broad_pathspec(sub, args):
        return shapes.broad_pathspec(sub, args)
    if sub == "push" and ("f" in flags or any(a.startswith("--force") for a in args) or any(p.startswith("+") for p in positional)):
        return "git push --force: rewrites the remote branch other sessions pull from"
    return None


def _embedded_space_reason(command: tuple[str, ...]) -> str | None:
    """A word env built with an embedded tab or newline, read with those as spaces."""
    for word in command:
        if not any(ch in word for ch in "\t\n\v\f\r"):
            continue
        flat = "".join(" " if ch in "\t\n\v\f\r" else ch for ch in word)
        reason = classify(flat)
        if reason:
            return reason
    return None


def _split_command_reason(seen: list[str]) -> str | None:
    """The reason for the command an ``env`` split-string runs, else ``None``.

    The first word is ``env`` by basename, so ``/usr/bin/env`` is the same subject.

    Options in the split string are parsed first. When one consumes a word, only
    the remaining command is classified (``--unset git`` is not ``git``). A
    ``NAME=VALUE`` word in that command is kept, so ``GIT_CONFIG*`` after an
    option is still the env-config refusal. Otherwise
    the split text is classified as the shell command it was written as. ``$`` and
    ``${VAR}`` are not expanded. An unknown escape has no knowable argv: the shell
    reason stands, or the opaque reason, and that case is never allowed.
    """
    if not seen or seen[0].rsplit("/", 1)[-1] != "env":
        return None
    parsed = _env_invocation(seen)
    if not (parsed.ok and parsed.split):
        return None
    if not parsed.determined:
        return classify(parsed.source) or _ENV_SPLIT_OPAQUE
    command_reason = classify(parsed.shell) or _embedded_space_reason(parsed.command)
    if parsed.ate_option:
        return command_reason
    return classify(parsed.source) or command_reason


def _opaque(segment: str) -> str | None:
    """Shapes a token parser cannot follow: refused when they mention git, rather than waved through.

    A shell function whose body mentions git, a command name built by shell
    expansion that could be git (``$X``, ``git${IFS}stash``, ``{git,stash}``, ``gi?``), a later
    word that expansion could turn into ``git``, and an interpreter one-liner
    that mentions git all run git where the guard cannot see the arguments.
    ``env -S`` and ``GIT_CONFIG*`` are judged after openers, subshell parentheses, wrappers
    and ordinary assignments are removed.
    """
    if _FUNC_DEF.search(segment) and _GIT_WORD.search(segment):
        return "defines a shell function and mentions git; the guard cannot follow it — run the git command plainly"
    try:
        raw = shlex.split(segment, comments=True)
    except ValueError:
        return None
    # The split string is the command, so the reason is that command's own reason.
    seen = _unwrap(raw, keep_signals=True)
    if shapes.env_config(seen):
        return shapes.env_config(seen)
    split_reason = _split_command_reason(seen)
    if split_reason:
        return split_reason
    head = _unwrap(raw)
    if head and _EXPANSION.search(head[0]) and head[0] not in ("[", "[[") and _may_name_git(head[0]):
        return "the command name comes from a shell expansion; the guard cannot see it — run the command plainly"
    if any(_EXPANSION.search(t) and " " not in t and _EXPANSION_SYNTAX.sub("", t).startswith("git") for t in raw):
        return "a shell expansion could build `git` here; the guard cannot see it — run the git command plainly"
    xargs = any(word.rsplit("/", 1)[-1] == "xargs" for word in raw[:4])
    if xargs and head and head[0].rsplit("/", 1)[-1] == "git" and len(head) == 1:
        return "xargs feeds git its subcommand from stdin; the guard cannot see it — run the git command plainly"
    if head and head[0].rsplit("/", 1)[-1].rstrip("0123456789.") in _INTERPRETERS and _GIT_WORD.search(segment) \
            and any(a in ("-c", "-e") for a in head[1:3]):
        return f"{head[0]} one-liner mentions git; the guard cannot follow it — run the git command plainly"
    return None


def _may_name_git(word: str) -> bool:
    """Whether a command word built by expansion could be ``git``.

    With the expansion removed (a ``${X:-default}`` kept as its default), a name
    that starts with ``git`` or whose letters appear in ``git`` in order (empty
    included) could be git (``${G}``, ``git${IFS}stash``, ``g{i,}t``, ``gi?``,
    ``g${X}t``); ``$HOME/bin/pytest`` and ``${PYTHON:-python}`` cannot. A command
    substitution's output is unknowable.
    """
    name = _EXPANSION_SYNTAX.sub("", _DEFAULT.sub(r"\1", word)).rsplit("/", 1)[-1]
    rest = iter("git")
    in_order = all(c in rest for c in name)   # a subsequence of "git": the expansion may fill the gaps
    return bool(_UNBALANCED.search(word)) or "`" in word or name.startswith("git") or in_order


def classify(command: str) -> str | None:
    """The first destructive segment's reason, else ``None``."""
    for seg in split_segments(shapes.inline_git_vars(command).strip()):
        reason = classify_segment(seg)
        if reason:
            return reason
    return None


def shared_with_others(repo_root: Path, agent: str | None, *, tree_only: bool = False) -> list[str]:
    """Ids of other live sessions, and of workers running here.

    With ``tree_only`` only sessions in **this** working tree count: a session
    in another linked worktree is not moved by a checkout here. Repo-wide
    operations (stash, rebase, force-push) count every session. A record that
    will not load counts too: the guard cannot tell it is not a live peer.
    """
    here = Path(repo_root).resolve()
    # A worker records the git root of its tree; in the nested layout the guard runs at the project root below it.
    trees = {here, git_root(here) or here}
    others = [s.agent for s in list_sessions(repo_root)
              if s.agent != agent and not (tree_only and s.worktree and Path(s.worktree).resolve() != here)]
    others += [f"{p} (unreadable; fix or delete it)" for p in unreadable_records(repo_root)]
    try:
        from specy_road.orchestration.workers.worker_process import wrapper_alive
        from specy_road.orchestration.workers.worker_state import list_records

        me = os.environ.get("SPECY_ROAD_WORKER_ID")   # a worker's own hook must not count the worker
        others += [f"worker {r.worker_id}" for r in list_records(repo_root, active_only=True)
                   if r.worker_id != me and wrapper_alive(r, repo_root) and Path(r.worktree).resolve() in trees]
    except Exception:  # noqa: BLE001 — presence is advisory; a broken record must not break the guard
        pass
    return others


def _expand_config_aliases(repo_root: Path, command: str) -> str:
    """``git s`` with ``alias.s = stash`` in the repo's git config is ``git stash`` to the guard."""
    out = []
    for seg in split_segments(command.strip()):
        try:
            sub, rest = _git_subcommand(shlex.split(seg, comments=True))
        except ValueError:
            out.append(seg)
            continue
        if sub and sub not in _KNOWN_GIT and sub != "!" and re.match(r"^[A-Za-z0-9_-]+$", sub):
            value = git_text(["config", "--get", f"alias.{sub}"], repo_root)
            if value:
                if value.startswith("!"):
                    seg = value[1:] + " " + " ".join(shlex.quote(a) for a in rest)
                else:
                    seg = "git " + value + " " + " ".join(shlex.quote(a) for a in rest)
        out.append(seg)
    return "; ".join(out)


def decide(repo_root: Path, command: str, *, agent: str | None, always: bool = False) -> Verdict:
    expanded = _expand_config_aliases(repo_root, command)
    reason = classify(expanded)
    if not reason:
        return Verdict(ALLOW, "", command)
    tree_only = reason.startswith(_TREE_SCOPED) and not _NAMES_A_TREE.search(expanded)
    others = shared_with_others(repo_root, agent, tree_only=tree_only)
    if not others and not always:
        return Verdict(ALLOW, f"(would deny with another live session: {reason})", command)
    who = f"live sessions: {', '.join(others)}" if others else "guard runs with --always"
    return Verdict(DENY, f"refused in a shared checkout ({who}) — {reason}. "
                         "See the shared-checkout rules in AGENTS.md; `specy-road session list` shows who is here. "
                         "Do not end, edit or delete another session's record to get past this; ask its owner "
                         "or a human.", command)


from specy_road.orchestration.guard.tool_call_guard_adapters import ADAPTERS, Adapter  # noqa: E402,F401 — re-exported for session_cli


def read_payload(text: str) -> dict[str, Any]:
    """The hook's stdin as a dict. Malformed or non-object JSON raises: the guard answers that with a deny, not an allow."""
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"hook payload is JSON {type(data).__name__}, not an object; refusing to guess what runs")
    return data
