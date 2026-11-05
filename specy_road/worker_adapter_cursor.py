"""The ``cursor`` harness adapter: ``agent -p`` stream-json (slice 7b).

Split from :mod:`specy_road.worker_adapters` for the file limit; callers reach it through that module.

Composer 2.5 worker logs on this toolkit's grind carry usage on the terminal ``result`` line
once per turn (``inputTokens``, ``outputTokens``, ``cacheReadTokens``, ``cacheWriteTokens``).
If a turn ever emits more than one usage-bearing line (``usage``, ``assistant``/``message.usage``,
or ``result``), token counts are summed in :func:`sum_cursor_turn_usage`.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from specy_road.worker_adapter_base import (Adapter, Capabilities, Launch, Parsed, Unsupported, _model_flag,
                                         file_instruction)
from specy_road.worker_adapter_parsers import _json, _num, _snip, usage_fields
from specy_road.worker_sessions import session_id_problem
from specy_road.worker_usage_delta import SESSION_TOKENS


def _raw_usage(d: dict[str, Any]) -> Any:
    if d.get("usage") is not None:
        return d.get("usage")
    msg = d.get("message")
    if isinstance(msg, dict) and msg.get("usage") is not None:
        return msg.get("usage")
    return None


def sum_cursor_turn_usage(parts: list[dict[str, Any]]) -> dict[str, Any]:
    """One turn's usage: a single line unchanged, several lines summed per token key."""
    if not parts:
        return usage_fields(None)
    if len(parts) == 1:
        return dict(parts[0])
    out = usage_fields(None)
    for k in SESSION_TOKENS:
        vals = [p[k] for p in parts if p.get(k) is not None]
        out[k] = sum(vals) if vals else None
    for k in ("cost_usd", "cost_is_estimate", "num_turns", "harness_version"):
        out[k] = next((p[k] for p in reversed(parts) if p.get(k) is not None), None)
    return out


def create_chat(worktree: Path, program: str = "agent") -> str:
    """``agent create-chat`` in the worktree (``program``: the resolved binary): the chat id, known before the turn
    starts, as Claude's is."""
    try:
        r = subprocess.run([program, "create-chat"], cwd=worktree, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unsupported(f"cursor: `agent create-chat` did not run: {e}") from None
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    chat = lines[-1] if lines else ""
    why = session_id_problem("cursor", chat)
    if r.returncode != 0 or why:
        raise Unsupported(f"cursor: `agent create-chat` exited {r.returncode} without a chat id "
                          f"({why or 'ok'}): {_snip(r.stderr or r.stdout)}")
    return chat


def _prompt_args(prompt_path: Path) -> list[str]:
    """The prompt as ``agent -p`` takes it without an over-long argument: its help documents no stdin, so a short
    instruction naming the prompt file (no ``--add-dir`` for it: an executor's extra roots are writable)."""
    return [file_instruction(Path(prompt_path).resolve())]


#: The default permission flags, on launch and resume: ``--trust`` accepts the new worktree as a workspace (``agent
#: -p`` otherwise exits asking to trust it) and Cursor's sandbox confines the commands the agent runs.
SANDBOX_FLAGS = ("--trust", "--sandbox", "enabled")
#: A roster entry's ``cursor_force: true``: ``--force`` force-allows every command that is not explicitly denied.
FORCE_FLAGS = ("--trust", "--force")
#: The characters that end a shell word unquoted: ``--force; true`` passes ``--force`` to ``agent``.
_SHELL_OPERATORS = "();<>|&`"
#: ``agent``'s short switches that take no value: one word may cluster them (``-pf`` is ``-p -f``), and anything after
#: ``-H``, ``-e`` or ``-w`` in a word is that option's value, so ``-Hf`` passes no ``-f``.
_SWITCHES = "-[vpfh]*"
#: A word in a custom command that force-allows commands as ``--force`` does (``-f`` and ``--yolo`` are its aliases).
_FORCE = re.compile(rf"--force|--yolo|{_SWITCHES}f.*")
#: A word that is a whole permission flag, value included.
_PERMISSION = re.compile(rf"--trust|--sandbox=.*|{_FORCE.pattern}")
#: A word that asks ``agent`` for its own worktree.
_WORKTREE = re.compile(rf"--worktree(=.*)?|{_SWITCHES}w.*")


def permission_flags(force: bool) -> list[str]:
    """The default command's permission flags: :data:`FORCE_FLAGS` when the roster opts in, else
    :data:`SANDBOX_FLAGS`."""
    return list(FORCE_FLAGS if force else SANDBOX_FLAGS)


def _shell_words(command: str) -> list[str]:
    """``command``'s words and operators, the one reading of a custom command here: quotes and backslashes as the shell
    takes them, an unquoted :data:`_SHELL_OPERATORS` character ending a word and standing as its own item.

    Every word of the line counts, in any of its commands, so this errs toward finding a flag: ``rm -f x; agent`` and a
    ``# --force`` comment match. It reads text and expands nothing: a flag in ``$FLAGS``, in a wrapper script or inside
    a quoted ``sh -c '...'`` is not seen. Unbalanced quotes give no words; the custom-command check refuses those."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_SHELL_OPERATORS)
    lexer.whitespace_split, lexer.commenters = True, ""
    try:
        return list(lexer)
    except ValueError:
        return []


def _words(argv: list[str]) -> list[str]:
    """``argv``'s words, with a custom launch's ``sh -c <command>`` read by :func:`_shell_words`."""
    return _shell_words(argv[2]) if len(argv) == 3 and argv[:2] == ["sh", "-c"] else argv


def launch_permissions(argv: list[str]) -> list[str]:
    """The permission flags a Cursor launch passes, in argv order and as written, for its ``launched`` event; a custom
    command is read by the bounded rule of :func:`_shell_words`."""
    words, out = _words(argv), []
    for i, w in enumerate(words):
        if _PERMISSION.fullmatch(w):
            out.append(w)
        elif w == "--sandbox":
            out += [w, *(v for v in words[i + 1:i + 2] if v.strip(_SHELL_OPERATORS))]
    return out


def _forces(cli: Any) -> bool:
    return isinstance(cli, str) and any(_FORCE.fullmatch(w) for w in _shell_words(cli))


def force_warnings(roster: list[dict[str, Any]]) -> list[str]:
    """One warning per ``cursor`` roster entry, assigned or not, that force-allows commands: ``cursor_force: true``
    on the default command, or a ``channels.cli`` / ``cli_resume`` passing ``--force``, ``-f`` or ``--yolo`` (by the
    bounded rule of :func:`_shell_words`)."""
    out: list[str] = []
    for entry in roster:
        if entry.get("harness") != "cursor":
            continue
        channels = entry.get("channels") if isinstance(entry.get("channels"), dict) else {}
        how = ["cursor_force: true"] if entry.get("cursor_force") is True else []
        how += [f"channels.{k} passes --force/-f/--yolo" for k in ("cli", "cli_resume") if _forces(channels.get(k))]
        if how:
            out.append(f"! cursor --force: {entry.get('id')} ({'; '.join(how)}) runs every command not explicitly "
                       "denied, without Cursor's sandbox; see docs/orchestration-workers.md (Permissions)")
    return out


def _no_worktree_flag(cli: str | None) -> None:
    """A custom command must not pass ``-w``/``--worktree`` (by the bounded rule of :func:`_shell_words`): ``agent``
    would make its own worktree under ``~/.cursor/worktrees`` and work there, not in the one specy-road created
    (harness-facts)."""
    if any(_WORKTREE.fullmatch(w) for w in _shell_words(cli or "")):
        raise Unsupported(f"channels.cli: cursor workers never pass -w/--worktree; specy-road creates the worktree: {cli}")


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent create-chat, then agent -p --resume <chat> --trust --sandbox enabled stream-json, "
                              "the prompt a file the agent is told to read (--trust skips a new worktree's trust prompt; "
                              "the sandbox confines shell commands; roster cursor_force: true passes --trust --force "
                              "instead, which force-allows every command not denied; never -w); resume = `agent -p "
                              "--resume` (undocumented with a new prompt: verify)")

    def __init__(self) -> None:
        self._usage_parts: list[dict[str, Any]] = []

    def _track_usage(self, d: dict[str, Any]) -> None:
        if d.get("type") == "system" and d.get("subtype") == "init":
            self._usage_parts = []
            return
        raw = _raw_usage(d)
        if raw is not None:
            self._usage_parts.append(usage_fields(raw))

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None, force: bool = False) -> Launch:
        """``force``: the roster entry's ``cursor_force`` (:func:`permission_flags`); a custom command keeps its own."""
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        program = self._program(harness_bin)
        chat = create_chat(worktree, program)   # the chat first: a turn that dies before its first event still has its id
        return Launch([program, "-p", "--resume", chat, "--output-format", "stream-json", *permission_flags(force),
                       *_model_flag("--model", model), "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id),
                       *_prompt_args(prompt_path)], session_id=chat)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None, launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None, force: bool = False) -> Launch:
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        return Launch([self._program(harness_bin), "-p", "--resume", session_id, "--output-format", "stream-json",
                       *permission_flags(force),
                       *_model_flag("--model", model), "--workspace", str(worktree), *self._add_dir(worktree, repo_root, node_id),
                       *_prompt_args(prompt_path)],
                      session_id=session_id)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path, effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, harness_bin: str | None = None) -> Launch:
        """A reviewer's turn in ``--mode ask`` (read-only Q&A) with ``--trust`` and without ``--force``, which
        would force-allow every command not denied. ``agent -p`` has no structured-output flag, so ``schema`` and
        ``output`` are unused and the result event's text is parsed as the final JSON; ``session`` is
        ``(id, resume)``, and only a resume can name the id. The prompt is a file the agent is told to read."""
        resume = ["--resume", session[0]] if session and session[1] else []
        return Launch([self._program(harness_bin), "-p", *resume, "--output-format", "stream-json", "--mode", "ask",
                       "--trust", *_model_flag("--model", model), *_prompt_args(prompt_path)],
                      session_id=session[0] if resume else None)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        self._track_usage(d)
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"cursor session {sid} ({d.get('model', '?')})", sid)
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict))
            return Parsed("output", _snip(text) or "(assistant)", sid)
        if t == "tool_call":
            return Parsed("output", f"tool call {d.get('subtype', '')}".strip(), sid)
        if t == "usage":
            return Parsed("output", "usage", sid)
        if t == "result":
            text = str(d.get("result") or "")
            ok = not d.get("is_error")
            summary = f"{d.get('subtype')}: {_snip(text)}" if ok else _snip(text) or f"{d.get('subtype')}: error"
            detail = {"message": text} if text else None
            usage = sum_cursor_turn_usage(self._usage_parts) if self._usage_parts else usage_fields(d.get("usage"))
            nt = _num(d.get("num_turns"), whole=True)
            if nt is not None:
                usage["num_turns"] = nt
            self._usage_parts = []
            return Parsed("turn_completed" if ok else "error", summary, sid, detail, usage)
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]
