"""Harness adapters: how a worker is launched, resumed, read, and handed to a human.

One adapter per harness the roster may name (``claude-code``, ``codex``, ``cursor``, ``generic``).
Each builds the documented one-shot command of its CLI (verified against the vendors' docs on
2026-10-27, see the v0.3.1 worker-orchestration design note, D2), turns the CLI's JSON output lines
into worker events, and says which of the lifecycle operations it supports. What it does not support
is declared, never emulated: a one-shot CLI has no interrupt short of killing the process, so
``interrupt`` is ``False`` and the command says so, rather than a kill being dressed up as one. The
long-lived protocols (Codex app-server, Cursor ACP) are the later adapters that turn those flags on.
The ``claude-code`` and ``cursor`` adapters live here; ``codex``'s is :mod:`worker_adapter_codex`,
and the shared base :mod:`worker_adapter_base`.

A roster entry's ``channels.cli`` (``{prompt}`` = prompt file path) replaces the built command for
any harness while its output is still parsed as that harness's; that is how an adopter widens or
narrows permissions, pins flags, or points at a wrapper. ``{session_flag}`` is the harness's own
session argument, so one command serves launch and resume (Claude Code: ``--session-id <id>`` on
launch, ``--resume <id>`` on resume); where the harness's resume is its own command (Codex, Cursor),
``channels.cli_resume`` naming ``{session}`` is what message and resume run instead, so they keep
the launch's permissions; ``{effort}`` is its flag for the profile's executor effort (empty on
Cursor), which the default commands carry too; ``{reviews_dir}`` is the main checkout's
``work/reviews/<ID>``, for the harness's writable-root flag, which the default commands pass in a
linked worktree. Claude Code's default asks for the narrowest mode that lets it edit unattended
(``acceptEdits``; ``dontAsk`` is stricter but denies every tool not allow-listed), so a first run
may have shell commands denied (under ``-p`` a denial does not stop the run; it is listed in
``permission_denials``); Cursor's ``agent -p`` has write and shell tools already; its default passes
``--trust --sandbox enabled``, and only ``cursor_force: true`` opts into ``--trust --force``, which
force-allows every command not explicitly denied and is the widest — read the table in
``docs/orchestration-workers.md`` before trusting either on a new repo.

A reviewer gets its own command (:meth:`Adapter.reviewer_launch`), read-only on every harness that
has one: Claude Code bare (``--bare``, API key or ``apiKeyHelper``) or in explicit settings mode
(subscription; see ``docs/orchestration-reviewer-output.md``), either way with ``--disallowedTools``
for ``Write``, ``Edit``, ``NotebookEdit``, commits, pushes and ``gh``; Codex
``sandbox_mode=read-only``; Cursor ``--mode ask --trust`` without ``--force``. Its final message is
the review as JSON: :func:`specy_road.review_answer.final_answer` reads it by the harness's row of
:data:`~specy_road.review_answer.TURNS`, and :mod:`specy_road.review_record_write` files it as the
record. A reviewer's custom command goes through :func:`reviewer_cli`, which gives Antigravity's
``agy`` (a ``generic`` harness) its ``--json-schema`` and read-only flags.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from specy_road.claude_config import claude_projects_dir
from specy_road.orchestration.workers.worker_adapter_base import (  # re-exported
    AGY_REVIEW_FLAGS,
    CODEX_POLICY,
    CODEX_REVIEW_POLICY,
    EFFORT_FLAGS,
    REVIEWER_DISALLOWED,
    REVIEWER_NO_WRITES,
    REVIEWER_TOOLS,
    REVIEWS_DIR,
    STDIN_INSTRUCTION,
    Adapter,
    Capabilities,
    Launch,
    Parsed,
    Unsupported,
    _bare,
    _model_flag,
    _reviews_handoff_dir,
    file_instruction,
    linked_worktree,
    reviewer_cli,
    reviews_dir_into,
)
from specy_road.orchestration.workers.worker_adapter_codex import Codex
from specy_road.orchestration.workers.worker_adapter_parsers import (  # re-exported
    _SESSION,
    _init_detail,
    _json,
    _num,
    _snip,
    _text,
    _tokens,
    limit_detail,
    placeholder_problem,
    substitute_prompt,
    usage_fields,
)
from specy_road.orchestration.workers.worker_sessions import session_id_problem
from specy_road.orchestration.workers.worker_state import HARNESSES
from specy_road.orchestration.workers.worker_usage_delta import SESSION_TOKENS
from specy_road.reviewer_auth import WORKER_FULL_FLAGS, bare_settings_argv, worker_environment


# The ``claude-code`` harness adapter: ``claude -p`` stream-json.

#: The executor's tools, listed rather than left to the mode: since 2.1.302 ``claude -p`` silently
#: denies a tool
#: nothing approved, and ``acceptEdits`` approves no shell command beyond the read-only and
#: filesystem sets.
EXECUTOR_TOOLS = "Read,Edit,Write,Glob,Grep,Bash"
#: An executor's permissions, the same on launch and resume: the mode, the allow-list, and no
#: prompts (anything
#: still unresolved is denied and Claude is told not to retry; the denial shows in the stream, see
#: ``parse_events``).
#: ``--allowedTools`` takes several values, so a single-value flag follows it before the
#: instruction.
EXECUTOR_PERMISSIONS = ("--allowedTools", EXECUTOR_TOOLS, "--permission-prompts", "none",
                        "--permission-mode", "acceptEdits")


def _worker_mode(launch_mode: str) -> list[str]:
    """A worker's mode flags, never ``claude -p``'s default: ``--bare`` (and the user-settings path
    when only an ``apiKeyHelper`` authenticates it), else every setting source named, so the
    subscription login is read."""
    if launch_mode == "bare":
        return ["--bare", *bare_settings_argv(worker_environment())]
    return list(WORKER_FULL_FLAGS)


class ClaudeCode(Adapter):
    harness = "claude-code"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="claude -p stream-json; session id chosen up front; resume = `claude "
                              "-p --resume`; "
                              "no interrupt short of SIGTERM (turn is lost); hand off with `claude "
                              "--resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None,
               launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        sid = str(uuid.uuid4())
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            # left as written; only the check uses the mode
            return replace(custom, launch_mode=launch_mode)
        return Launch([self._program(harness_bin), "-p", *_worker_mode(launch_mode),
                       "--output-format", "stream-json", "--verbose",
                       "--session-id", sid, *_model_flag("--model", model),
                       *self.effort_flag(effort),
                       *self._add_dir(worktree, repo_root, node_id), *EXECUTOR_PERMISSIONS,
                       STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=sid, launch_mode=launch_mode)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str,
               cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None,
               launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id,
                              repo_root=repo_root)
        if custom:
            return replace(custom, launch_mode=launch_mode)
        # A resumed session does not keep the launch's --model: pass it again, as the launch did.
        return Launch([self._program(harness_bin), "-p", *_worker_mode(launch_mode), "--resume",
                       session_id, "--output-format", "stream-json",
                       "--verbose", *_model_flag("--model", model), *self.effort_flag(effort),
                       *self._add_dir(worktree, repo_root, node_id), *EXECUTOR_PERMISSIONS,
                       STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=session_id, launch_mode=launch_mode)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path,
                        effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, mode: str = "bare",
                        harness_bin: str | None = None) -> Launch:
        """A fresh-session reviewer's turn. ``mode="bare"`` (the default) passes ``--bare``.
        ``mode="explicit"`` passes ``--setting-sources user`` and ``--strict-mcp-config`` (help.txt)
        and never ``--bare`` or ``--mcp-config``. Bare mode with only an ``apiKeyHelper`` also
        passes ``--settings`` and that file's path
        (:func:`~specy_road.reviewer_auth.bare_settings_argv`), never the helper command.
        ``harness_bin`` is the roster entry's binary (:meth:`Adapter._program`). Either way the
        branch under review runs none of its hooks and connects none of its MCP servers, and
        ``--add-dir`` names the hand-off directory. The instruction goes right after ``-p``:
        ``--add-dir`` takes several values and would swallow it. ``session`` is ``(id, resume)`` for
        ``review delegate``: the session flag, and stream-json so the id can be read back. Read-only
        (A2): no file-writing tool is allowed or approved (``Write``, ``Edit`` and ``NotebookEdit``
        are denied, and no permission mode approves edits); bare mode fires no hook, so
        ``--disallowedTools`` denies commits, pushes and ``gh`` too (A4). ``--add-dir`` lets it read
        the hand-off directory. ``schema`` (the review output schema file) goes inline as
        ``--json-schema``, less its top-level ``$schema`` (Claude Code 2.1.318 rejects the draft
        2020-12 reference; the file keeps it). ``output`` is unused: the result event carries the
        final answer."""
        tracked = [*self.session_flag(*session), "--output-format", "stream-json",
                   "--verbose"] if session else []
        body = json.loads(schema.read_text(encoding="utf-8")) if schema else {}
        structured = (
            ["--json-schema", json.dumps({k: v for k, v in body.items() if k != "$schema"})]
            if schema
            else []
        )
        # explicit reads the subscription login from user settings and still loads no project
        # settings or MCP.
        # bare with only an apiKeyHelper passes the settings file's path, never the helper command.
        auth = (["--setting-sources", "user", "--strict-mcp-config"] if mode == "explicit"
                else ["--bare", *bare_settings_argv()])
        return Launch([self._program(harness_bin), "-p", STDIN_INSTRUCTION, *auth, *tracked,
                       *_model_flag("--model", model),
                       *self.effort_flag(effort), "--allowedTools", REVIEWER_TOOLS,
                       "--disallowedTools", *REVIEWER_NO_WRITES, *REVIEWER_DISALLOWED, *structured,
                       "--add-dir", str(reviews)],
                      stdin=_text(prompt_path), session_id=session[0] if session else None,
                      launch_mode="explicit" if mode == "explicit" else "bare")

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"claude session {sid} ({d.get('model', '?')})", sid,
                          _init_detail(d))
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(
                p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
            )
            return Parsed("output", _snip(text) or "(tool use)", sid)
        if t == "result":
            text = str(d.get("result") or d.get("api_error") or "")
            ok = not d.get("is_error") and d.get("subtype") == "success"
            cost = d.get("total_cost_usd")
            summary = (
                f"{d.get('subtype')}: {_snip(text)}"
                if ok
                else _snip(text) or f"{d.get('subtype')}: error"
            )
            detail: dict[str, Any] = {}
            if cost is not None:
                detail["cost_usd"] = cost
            if text:
                detail["message"] = text
            # total_cost_usd is the session's, earlier turns included: the wrapper logs the delta.
            usage = usage_fields(d.get("usage"), cost=cost, num_turns=d.get("num_turns"),
                                 estimate=True)
            usage["session_cost_usd"] = usage["cost_usd"]
            return Parsed("turn_completed" if ok else "error", summary, sid, detail or None, usage)
        return None

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        out = [*super().parse_events(line, launch), *self._turn_signals(_json(line))]
        inferred = (
            (out[0].detail or {}).get("inferred_mode") if out and out[0].type == "started" else None
        )
        # explicit is a reviewer mode, not a profile launch_mode the tool list can infer
        if inferred and launch.launch_mode in ("bare", "full") and inferred != launch.launch_mode:
            out.append(Parsed("error",
                              f"claude started in {inferred} mode but the profile's launch_mode is "
                                       f"{launch.launch_mode}", out[0].session_id,
                              {"inferred_mode": inferred, "launch_mode": launch.launch_mode}))
        return out

    @staticmethod
    def _turn_signals(d: dict[str, Any] | None) -> list[Parsed]:
        """What the post-run check reads from a line (worker_turn_check): a ``system/api_retry``,
        each entry of a result's ``permission_denials``, and a usage limit in the result's text
        (code.claude.com/docs/en/headless)."""
        if not d:
            return []
        sid = d.get("session_id")
        if d.get("type") == "system" and d.get("subtype") == "api_retry":
            keys = ("attempt", "max_retries", "retry_delay_ms", "error_status", "error")
            return [Parsed("api_retry",
                           f"api retry {d.get('attempt')}/{d.get('max_retries')}: {d.get('error')} "
                                        f"(next in {d.get('retry_delay_ms')} ms)", sid,
                           {k: d.get(k) for k in keys})]
        if d.get("type") != "result":
            return []
        out = [Parsed("permission_denied",
                      f"denied {p.get('tool_name')}: {_snip(json.dumps(p.get('tool_input')), 160)}",
                      sid, {k: p.get(k) for k in ("tool_name", "tool_input", "tool_use_id")})
               for p in d.get("permission_denials") or [] if isinstance(p, dict)]
        limit = limit_detail(str(d.get("result") or d.get("api_error") or ""),
                             failed=bool(d.get("is_error")) or d.get("subtype") != "success")
        if limit:
            out.append(Parsed("usage_limited",
                              f"usage limit; resets {limit['reset_at'] or 'at an unstated time'}",
                              sid, {**limit, "source": "claude-code result"}))
        return out

    @staticmethod
    def transcript_limit(session_id: str | None, *, home: Path | None = None) -> Parsed | None:
        """A usage limit the session transcript's last assistant message names (Claude writes an API
        error as one), for a turn that exited non-zero with no result line: ``<config
        dir>/projects/<project>/<session-id>.jsonl`` (harness-facts), found by the id alone. The
        prompt is never read: a brief may mention limits."""
        root = claude_projects_dir(home)
        if not session_id or not re.fullmatch(r"[A-Za-z0-9-]+", session_id) or not root.is_dir():
            return None
        text = ""
        for path in sorted(root.glob(f"*/{session_id}.jsonl")):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                d = _json(line) or {}
                message = d.get("message") if d.get("type") == "assistant" else None
                content = message.get("content") if isinstance(message, dict) else None
                parts = (
                    [content]
                    if isinstance(content, str)
                    else [
                        p.get("text", "")
                        for p in content or []
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                )
                text = " ".join(parts).strip() or text
        limit = limit_detail(text, failed=True)
        return Parsed("usage_limited",
                      f"usage limit; resets {limit['reset_at'] or 'at an unstated time'}",
                      session_id,
                      {**limit, "source": "claude-code transcript"}) if limit else None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["claude", "--resume", session_id]

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        # `--session-id` is refused for a session that exists, so a resume needs `--resume`.
        return ["--resume", session_id] if resume else ["--session-id", session_id]


# The ``cursor`` harness adapter: ``agent -p`` stream-json. Composer 2.5 worker logs on this
# toolkit's grind carry usage on the terminal ``result`` line once per turn (``inputTokens``,
# ``outputTokens``, ``cacheReadTokens``, ``cacheWriteTokens``). If a turn ever emits more than one
# usage-bearing line (``usage``, ``assistant``/``message.usage``, or ``result``), token counts are
# summed in :func:`sum_cursor_turn_usage`.


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
    """``agent create-chat`` in the worktree (``program``: the resolved binary): the chat id, known
    before the turn starts, as Claude's is."""
    try:
        r = subprocess.run([program, "create-chat"], cwd=worktree, capture_output=True, text=True,
                           timeout=60, check=False)
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
    """The prompt as ``agent -p`` takes it without an over-long argument: its help documents no
    stdin, so a short instruction naming the prompt file (no ``--add-dir`` for it: an executor's
    extra roots are writable)."""
    return [file_instruction(Path(prompt_path).resolve())]


#: The default permission flags, on launch and resume: ``--trust`` accepts the new worktree as a
#: workspace (``agent
#: -p`` otherwise exits asking to trust it) and Cursor's sandbox confines the commands the agent
#: runs.
SANDBOX_FLAGS = ("--trust", "--sandbox", "enabled")
#: A roster entry's ``cursor_force: true``: ``--force`` force-allows every command that is not
#: explicitly denied.
FORCE_FLAGS = ("--trust", "--force")
#: The characters that end a shell word unquoted: ``--force; true`` passes ``--force`` to ``agent``.
_SHELL_OPERATORS = "();<>|&`\n"
#: What the shell reads as quoted: a single-quoted string, a double-quoted string, or one escaped
#: character.
_QUOTED = re.compile(r"""'[^']*'|"(?:\\.|[^"\\])*"|\\.""", re.S)
_ESCAPED = re.compile(r"\\.", re.S)
#: ``agent``'s short switches that take no value: one word may cluster them (``-pf`` is ``-p -f``),
#: and anything after
#: ``-H``, ``-e`` or ``-w`` in a word is that option's value, so ``-Hf`` passes no ``-f``.
_SWITCHES = "-[vpfh]*"
#: A word in a custom command that force-allows commands as ``--force`` does (``-f`` and ``--yolo``
#: are its aliases).
_FORCE = re.compile(rf"--force|--yolo|{_SWITCHES}f.*")
#: A word that is a whole permission flag, value included.
_PERMISSION = re.compile(rf"--trust|--sandbox=.*|{_FORCE.pattern}")
#: A word that asks ``agent`` for its own worktree.
_WORKTREE = re.compile(rf"--worktree(=.*)?|{_SWITCHES}w.*")
#: What a sandboxed shell prints when Cursor refuses the write (checked on agent 2026.11.05-86047df,
#: 2026-11-08).
_DENIAL = re.compile(r"Permission denied|Read-only file system|Operation not permitted")


def permission_flags(force: bool) -> list[str]:
    """The default command's permission flags: :data:`FORCE_FLAGS` when the roster opts in, else
    :data:`SANDBOX_FLAGS`."""
    return list(FORCE_FLAGS if force else SANDBOX_FLAGS)


def _joined_lines(command: str) -> str:
    """``command`` without its line continuations: the shell drops a backslash-newline before it
    splits words, in double quotes too, and keeps it in single quotes."""
    def unit(quoted: re.Match[str]) -> str:
        if quoted[0].startswith("'"):
            return quoted[0]
        return _ESCAPED.sub(lambda e: "" if e[0] == "\\\n" else e[0], quoted[0])
    return _QUOTED.sub(unit, command)


def _shell_words(command: str) -> list[str]:
    """``command``'s words and operators, the one reading of a custom command here, and its bounded
    rule: POSIX quoting only. Quotes, backslashes and line continuations are taken as ``sh`` takes
    them, and an unquoted :data:`_SHELL_OPERATORS` character ends a word and stands as its own item.

    Every word of the line counts, in any of its commands, so this errs toward finding a flag: ``rm
    -f x; agent`` and a ``# --force`` comment match. It runs and expands nothing, so a word the
    shell builds at run time is not seen: ``$FLAGS``, ``--fo$(:)rce``, bash's ``$'--force'``, a
    wrapper script, a quoted ``sh -c '...'``. Where the text stops parsing (an open quote, which the
    custom-command check refuses, or a trailing backslash, which ``sh`` passes on as a literal), the
    words before that point still count."""
    lexer = shlex.shlex(_joined_lines(command), posix=True, punctuation_chars=_SHELL_OPERATORS)
    lexer.whitespace_split, lexer.whitespace, lexer.commenters = True, " \t", ""
    words: list[str] = []
    try:
        words.extend(lexer)
    except ValueError:
        pass
    return words


def _words(argv: list[str]) -> list[str]:
    """``argv``'s words, with a custom launch's ``sh -c <command>`` read by :func:`_shell_words`."""
    return _shell_words(argv[2]) if len(argv) == 3 and argv[:2] == ["sh", "-c"] else argv


def launch_permissions(argv: list[str]) -> list[str]:
    """The permission flags a Cursor launch passes, in argv order and as written, for its
    ``launched`` event; a custom command is read by the bounded rule of :func:`_shell_words`."""
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
    """One warning per ``cursor`` roster entry, assigned or not, that force-allows commands:
    ``cursor_force: true`` on the default command, or a ``channels.cli`` / ``cli_resume`` passing
    ``--force``, ``-f`` or ``--yolo`` (by the bounded rule of :func:`_shell_words`)."""
    out: list[str] = []
    for entry in roster:
        if entry.get("harness") != "cursor":
            continue
        channels = entry.get("channels") if isinstance(entry.get("channels"), dict) else {}
        how = ["cursor_force: true"] if entry.get("cursor_force") is True else []
        how += [
            f"channels.{k} passes --force/-f/--yolo"
            for k in ("cli", "cli_resume")
            if _forces(channels.get(k))
        ]
        if how:
            out.append(f"! cursor --force: {entry.get('id')} ({'; '.join(how)}) runs every command "
                       "not explicitly "
                       "denied, without Cursor's sandbox; see docs/orchestration-workers.md "
                       "(Permissions)")
    return out


def _shell_bodies(d: dict[str, Any]) -> list[dict[str, Any]]:
    """The ``success`` and ``failure`` objects of a completed shell ``tool_call``, either of which
    can carry a denial."""
    if d.get("type") != "tool_call" or d.get("subtype") != "completed":
        return []
    call = d.get("tool_call")
    shell = call.get("shellToolCall") if isinstance(call, dict) else None
    result = shell.get("result") if isinstance(shell, dict) else None
    if not isinstance(result, dict):
        return []
    return [body for key in ("failure", "success") if isinstance(body := result.get(key), dict)]


#: Cursor's question tool: the ``tool_call`` key in ``tests/fixtures/cursor_question_tool.jsonl``,
#: one real
#: ``agent -p --output-format stream-json`` capture. Assistant text and every other tool key are not
#: this.
QUESTION_TOOL = "askQuestionToolCall"


def _interactive_tool(d: dict[str, Any] | None) -> Parsed | None:
    """One ``interactive_tool`` when a ``tool_call`` line's tool key is :data:`QUESTION_TOOL`.

    A call is at least two lines (``started`` and ``completed``). Each line is its own event; the
    post-run check collapses them to one finding per turn.
    """
    if not d or d.get("type") != "tool_call":
        return None
    call = d.get("tool_call")
    if not isinstance(call, dict) or QUESTION_TOOL not in call:
        return None
    return Parsed("interactive_tool", f"question tool {QUESTION_TOOL}: no person saw it",
                  d.get("session_id"),
                  {"tool_name": QUESTION_TOOL})


def _sandbox_denial(d: dict[str, Any] | None) -> Parsed | None:
    """One ``permission_denied`` when a shell result's stderr is a sandbox refusal, else ``None``.

    A denied ``touch`` is ``result.failure`` and exit 1; a script that keeps going puts the same
    text on ``result.success``. The turn's own ``result`` line stays ``success`` either way, so this
    is what the post-run check sees.
    """
    if not d:
        return None
    for body in _shell_bodies(d):
        text = str(body.get("stderr") or body.get("interleavedOutput") or "")
        if _DENIAL.search(text):
            return Parsed("permission_denied", f"denied shell: {_snip(text.strip(), 160)}",
                          d.get("session_id"),
                          {"tool_name": "shell",
                           "tool_input": {"command": _snip(str(body.get("command") or ""), 160)},
                           "exit_code": body.get("exitCode")})
    return None


def _no_worktree_flag(cli: str | None) -> None:
    """A custom command must not pass ``-w``/``--worktree`` (by the bounded rule of
    :func:`_shell_words`): ``agent`` would make its own worktree under ``~/.cursor/worktrees`` and
    work there, not in the one specy-road created (harness-facts)."""
    if any(_WORKTREE.fullmatch(w) for w in _shell_words(cli or "")):
        raise Unsupported(f"channels.cli: cursor workers never pass -w/--worktree; specy-road "
                          f"creates the worktree: {cli}")


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent create-chat, then agent -p --resume <chat> --trust --sandbox "
                              "enabled stream-json, "
                              "the prompt a file the agent is told to read (--trust skips a new "
                              "worktree's trust prompt; "
                              "the sandbox confines shell commands; roster cursor_force: true "
                              "passes --trust --force "
                              "instead, which force-allows every command not denied; never -w); "
                              "resume = `agent -p "
                              "--resume` with a new prompt (same session id, the new prompt "
                              "answered; agent 2026.11.05-86047df, 2026-11-08)")

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
               *, node_id: str | None = None, repo_root: Path | None = None,
               launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None,
               force: bool = False) -> Launch:
        """``force``: the roster entry's ``cursor_force`` (:func:`permission_flags`); a custom
        command keeps its own."""
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, effort=effort, node_id=node_id, repo_root=repo_root)
        if custom:
            return custom
        program = self._program(harness_bin)
        # the chat first: a turn that dies before its first event still has its id
        chat = create_chat(worktree, program)
        return Launch([program, "-p", "--resume", chat, "--output-format", "stream-json",
                       *permission_flags(force),
                       *_model_flag("--model", model), "--workspace", str(worktree),
                       *self._add_dir(worktree, repo_root, node_id),
                       *_prompt_args(prompt_path)], session_id=chat)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str,
               cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None,
               launch_mode: str = "full",
               effort: str | None = None, harness_bin: str | None = None,
               force: bool = False) -> Launch:
        _no_worktree_flag(cli)
        custom = self._custom(cli, prompt_path, session_id, effort, node_id=node_id,
                              repo_root=repo_root)
        if custom:
            return custom
        return Launch([self._program(harness_bin), "-p", "--resume", session_id, "--output-format",
                       "stream-json",
                       *permission_flags(force),
                       *_model_flag("--model", model), "--workspace", str(worktree),
                       *self._add_dir(worktree, repo_root, node_id),
                       *_prompt_args(prompt_path)],
                      session_id=session_id)

    def reviewer_launch(self, prompt_path: Path, model: str | None, reviews: Path,
                        effort: str | None = None,
                        session: tuple[str, bool] | None = None, *, schema: Path | None = None,
                        output: Path | None = None, harness_bin: str | None = None) -> Launch:
        """A reviewer's turn in ``--mode ask`` (read-only Q&A) with ``--trust`` and without
        ``--force``, which would force-allow every command not denied. ``agent -p`` has no
        structured-output flag, so ``schema`` and ``output`` are unused and the result event's text
        is parsed as the final JSON; ``session`` is ``(id, resume)``, and only a resume can name the
        id. The prompt is a file the agent is told to read."""
        resume = ["--resume", session[0]] if session and session[1] else []
        return Launch([self._program(harness_bin), "-p", *resume, "--output-format", "stream-json",
                       "--mode", "ask",
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
            summary = (
                f"{d.get('subtype')}: {_snip(text)}"
                if ok
                else _snip(text) or f"{d.get('subtype')}: error"
            )
            detail = {"message": text} if text else None
            usage = (
                sum_cursor_turn_usage(self._usage_parts)
                if self._usage_parts
                else usage_fields(d.get("usage"))
            )
            nt = _num(d.get("num_turns"), whole=True)
            if nt is not None:
                usage["num_turns"] = nt
            self._usage_parts = []
            return Parsed("turn_completed" if ok else "error", summary, sid, detail, usage)
        return None

    def parse_events(self, line: str, launch: Launch) -> list[Parsed]:
        raw = _json(line)
        extra = [event for event in (_sandbox_denial(raw), _interactive_tool(raw)) if event]
        return [*super().parse_events(line, launch), *extra]

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]


ADAPTERS: dict[str, Adapter] = {a.harness: a for a in (Adapter(), ClaudeCode(), Codex(), Cursor())}
assert set(ADAPTERS) == set(HARNESSES)


def adapter_for(harness: str) -> Adapter:
    try:
        return ADAPTERS[harness]
    except KeyError:
        raise Unsupported(
            f"unknown harness {harness!r}; expected one of {', '.join(HARNESSES)}"
        ) from None
