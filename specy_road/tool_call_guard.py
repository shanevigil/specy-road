"""Decide whether a shell command is safe to run in a checkout other agents share.

The guard behind ``specy-road session guard`` and the harness hook adapters
(proposal §3.4, §3.5; design note
``docs/design-notes/agent-guidance-and-shared-checkouts.md``, decision 6).

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

from specy_road import tool_call_guard_shapes as shapes
from specy_road.git_subprocess import git_text
from specy_road.session_presence import list_sessions

ALLOW = "allow"
DENY = "deny"

_SEPARATORS = ("&&", "||", ";", "|", "&", "\n")
#: Wrapper flags that take an argument (``sudo -u bob``, ``env -u VAR``).
_WRAPPER_FLAG_ARG = {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-n", "--user", "--group", "--unset",
                     "--chdir", "--adjustment", "--host", "--prompt", "--role", "--type", "--other-user", "--max-args",
                     "--max-procs", "--delimiter", "--arg-file", "--replace", "--signal", "--kill-after"}
_GIT_GLOBAL_WITH_ARG = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
#: Words that merely wrap the real command: ``command git …``, ``env X=1 git …``.
_WRAPPERS = {"command", "env", "sudo", "nohup", "exec", "time", "nice", "xargs", "timeout", "doas", "ionice"}
#: Wrappers whose first positional is not the command (``timeout 10 git …``).
_WRAPPER_LEADING_ARG = {"timeout"}
#: ``env -S "git stash"`` splits its argument into a command: opaque to a token parser.
_ENV_SPLIT = {"-S", "--split-string"}
#: Reasons about the working tree only; other worktrees' sessions are not at risk.
_TREE_SCOPED = ("git switch", "git checkout", "git restore", "git clean", "git commit", "git add", "git reset")
#: ``git -C <dir>`` / ``--work-tree`` act on another tree: never scope those to the caller's.
_NAMES_A_TREE = re.compile(r"(^|\s)(-C\S*|--work-tree(=|\s)|--git-dir(=|\s))")
_GIT_WORD = re.compile(r"\bgit\b")
_FUNC_DEF = re.compile(r"(^|[\s;])\w+\s*\(\s*\)\s*\{")
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


def _unwrap(tokens: list[str]) -> list[str]:
    """Strip ``VAR=x``, ``command``/``env``/``sudo``-style wrappers, and subshell parens."""
    i = 0
    wrapped = False
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("(") and len(t) > 1:
            tokens = [t[1:], *tokens[i + 1:]]
            continue
        if ("=" in t and not t.startswith("-")) or t in ("(", "{"):
            i += 1
            continue
        if t in _WRAPPERS:
            wrapped = True
            i += 2 if t in _WRAPPER_LEADING_ARG else 1
            continue
        if wrapped and t.startswith("-"):
            i += 2 if t in _WRAPPER_FLAG_ARG and "=" not in t else 1  # a wrapper's flag, with its argument
            continue
        break
    out = tokens[i:]
    return [t.rstrip(")") if t.endswith(")") and t != ")" else t for t in out if t not in (")", "}")]


def _git_subcommand(tokens: list[str]) -> tuple[str | None, list[str]]:
    """``(subcommand, its args)`` for a ``git …`` token list, else ``(None, [])``.

    ``/usr/bin/git`` counts as ``git``; a ``-c alias.<name>=<cmd>`` whose
    alias is the subcommand is expanded, so ``git -c alias.s=stash s`` is
    ``git stash``; a ``!`` alias comes back as ``("!", [shell command])``.
    """
    tokens = _unwrap(tokens)
    if not tokens or tokens[0].rsplit("/", 1)[-1] != "git":
        return None, []
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


def classify_segment(segment: str) -> str | None:
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
    if sub in ("commit", "add") and shapes.broad_pathspec(sub, args):
        return shapes.broad_pathspec(sub, args)
    if sub == "push" and ("f" in flags or any(a.startswith("--force") for a in args) or any(p.startswith("+") for p in positional)):
        return "git push --force: rewrites the remote branch other sessions pull from"
    return None


def _opaque(segment: str) -> str | None:
    """Shapes a token parser cannot follow: refused when they mention git, rather than waved through.

    A shell function whose body mentions git, a command name that comes from
    a variable, and an interpreter one-liner that mentions git all run git
    where the guard cannot see the arguments.
    """
    if _FUNC_DEF.search(segment) and _GIT_WORD.search(segment):
        return "defines a shell function and mentions git; the guard cannot follow it — run the git command plainly"
    try:
        head = _unwrap(shlex.split(segment, comments=True))
    except ValueError:
        return None
    if head and head[0].startswith("$"):
        return "the command name comes from a variable; the guard cannot see it — run the command plainly"
    try:
        raw = shlex.split(segment, comments=True)
    except ValueError:
        raw = []
    if shapes.env_config(raw):
        return shapes.env_config(raw)
    if raw and raw[0] == "env" and any(a in _ENV_SPLIT or a.startswith("--split-string=") for a in raw[1:]) \
            and _GIT_WORD.search(segment):
        return "env -S splits its argument into a command the guard cannot see; run the git command plainly"
    if raw and "xargs" in raw[:4] and head and head[0].rsplit("/", 1)[-1] == "git" and len(head) == 1:
        return "xargs feeds git its subcommand from stdin; the guard cannot see it — run the git command plainly"
    if head and head[0].rsplit("/", 1)[-1].rstrip("0123456789.") in _INTERPRETERS and _GIT_WORD.search(segment) \
            and any(a in ("-c", "-e") for a in head[1:3]):
        return f"{head[0]} one-liner mentions git; the guard cannot follow it — run the git command plainly"
    return None


def classify(command: str) -> str | None:
    """The first destructive segment's reason, else ``None``."""
    for seg in split_segments(command.strip()):
        reason = classify_segment(seg)
        if reason:
            return reason
    return None


def shared_with_others(repo_root: Path, agent: str | None, *, tree_only: bool = False) -> list[str]:
    """Ids of other live sessions, and of workers running here.

    With ``tree_only`` only sessions in **this** working tree count: a session
    in another linked worktree is not moved by a checkout here. Repo-wide
    operations (stash, rebase, force-push) count every session.
    """
    here = Path(repo_root).resolve()
    others = [s.agent for s in list_sessions(repo_root)
              if s.agent != agent and not (tree_only and s.worktree and Path(s.worktree).resolve() != here)]
    try:
        from specy_road.worker_process import wrapper_alive
        from specy_road.worker_state import list_records

        me = os.environ.get("SPECY_ROAD_WORKER_ID")   # a worker's own hook must not count the worker
        others += [f"worker {r.worker_id}" for r in list_records(repo_root, active_only=True)
                   if r.worker_id != me and wrapper_alive(r, repo_root) and Path(r.worktree).resolve() == here]
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
                         "See the shared-checkout rules in AGENTS.md; `specy-road session list` shows who is here.", command)


from specy_road.tool_call_guard_adapters import ADAPTERS, Adapter  # noqa: E402,F401 — re-exported for session_cli


def read_payload(text: str) -> dict[str, Any]:
    """The hook's stdin as a dict. Malformed or non-object JSON raises: the guard answers that with a deny, not an allow."""
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"hook payload is JSON {type(data).__name__}, not an object; refusing to guess what runs")
    return data
