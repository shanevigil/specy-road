"""Harness adapters: how a worker is launched, resumed, read, and handed to a human (slice 7b).

One adapter per harness the roster may name (``claude-code``, ``codex``,
``cursor``, ``generic``). Each builds the documented one-shot command of its
CLI (verified against the vendors' docs on 2026-10-27, see
``docs/design-notes/v0-3-1-worker-orchestration.md`` D2), turns the CLI's
JSON output lines into worker events, and says which of the lifecycle
operations it supports. What it does not support is declared, never
emulated: a one-shot CLI has no interrupt short of killing the process, so
``interrupt`` is ``False`` and the command says so, rather than a kill being
dressed up as one. The long-lived protocols (Codex app-server, Cursor ACP)
are the later adapters that turn those flags on.

A roster entry's ``channels.cli`` (``{prompt}`` = prompt file path) replaces
the built command for any harness while its output is still parsed as that
harness's; that is how an adopter widens or narrows permissions, pins flags,
or points at a wrapper. ``{session_flag}`` is the harness's own session
argument, so one command serves launch and resume (Claude Code:
``--session-id <id>`` on launch, ``--resume <id>`` on resume). Claude Code's
default asks for the narrowest mode that lets it edit unattended
(``acceptEdits``; ``dontAsk`` is stricter but denies every tool not
allow-listed), so a first run may stop at a shell
permission; Cursor's ``agent -p`` has write and shell tools already and
``--force`` force-allows every command not explicitly denied, so that default
is the widest — read the table
in ``docs/orchestration-workers.md`` before trusting either on a new repo.
"""

from __future__ import annotations

import json
import re
import shlex
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specy_road.git_subprocess import git_text
from specy_road.worker_state import HARNESSES


@dataclass(frozen=True)
class Capabilities:
    resume: bool
    interrupt: bool
    steer: bool
    handoff: bool
    events: bool
    notes: str


@dataclass(frozen=True)
class Launch:
    argv: list[str]
    stdin: str | None = None        # prompt text piped in, when the CLI reads it that way
    session_id: str | None = None   # chosen up front, when the harness lets the caller pick


@dataclass(frozen=True)
class Parsed:
    """One output line turned into an event: ``type`` is a worker-event type."""
    type: str
    summary: str
    session_id: str | None = None
    detail: dict[str, Any] | None = None


class Unsupported(Exception):
    """The adapter declares this operation unsupported for its harness."""


def _text(prompt_path: Path) -> str:
    return prompt_path.read_text(encoding="utf-8")


#: What a harness is told when the prompt itself travels on stdin: an argv
#: string is capped at 128 KiB on Linux, and a brief can be longer.
STDIN_INSTRUCTION = "The task is the text on standard input. Follow it exactly; it is the whole prompt."


# `codex exec` has no --ask-for-approval (codex-cli 0.165): set both as config, which exec and resume take.
CODEX_POLICY = ("-c", "sandbox_mode=workspace-write", "-c", "approval_policy=never")


def _model_flag(flag: str, model: str | None) -> list[str]:
    """No model means the harness's own default (a profile whose ``api_id`` is ``unknown``)."""
    return [flag, model] if model else []


#: A placeholder must be a whole shell word, bare or wrapped in exactly one
#: pair of quotes, optionally behind a ``<`` redirection. Inside a larger
#: word (``"prefix <prompt> suffix"``, ``--session-id={session}``) the quoting
#: ``shlex.quote`` adds would land inside still-open quotes, where ``$(…)``
#: runs; and an embedded ``{session}`` would never be substituted at all.
#: Validation and substitution walk the same tokens, so they cannot disagree.
PLACEHOLDERS = ("<prompt>", "{prompt}", "{session}", "{session_flag}")
_SESSION = frozenset({"{session}", "{session_flag}"})
_WORD = re.compile(r'''(?:[^\s"']+|"[^"]*"|'[^']*')+''')   # a shell word: bare runs and whole quoted spans
_ANY_PROMPT = re.compile(r"<prompt>|\{prompt\}")


def _placeholder_of(token: str) -> tuple[str | None, str]:
    """``(placeholder, prefix)``: the placeholder a token *is* (bare, ``"ph"`` or ``'ph'``, optionally
    behind a ``<`` redirection that is the prefix), or ``(None, "")``."""
    forms = {f: p for p in PLACEHOLDERS for f in (p, f'"{p}"', f"'{p}'")}
    if token in forms:
        return forms[token], ""
    if token.startswith("<") and token[1:] in forms:
        return forms[token[1:]], "<"
    return None, ""


def _tokens(cli: str) -> list[tuple[int, int, str | None, str]]:
    """``(start, end, placeholder-or-None, prefix)`` per shell word; ``ValueError`` on an unbalanced quote."""
    if _WORD.sub("", cli).strip():
        raise ValueError("unbalanced quote")
    return [(m.start(), m.end(), *_placeholder_of(m.group(0))) for m in _WORD.finditer(cli)]


def substitute_prompt(cli: str, prompt_path: Path, session: str | None = None,
                      session_flag: list[str] | None = None) -> str:
    """``{prompt}`` → the quoted file path; ``<prompt>`` (the profiles' form) → the quoted text;
    ``{session_flag}`` → ``session_flag`` as quoted words (nothing when ``None``).

    Per token, whole words only: substituted text is never rescanned, and a
    placeholder embedded in a larger word is refused by
    :func:`placeholder_problem` before this runs.
    """
    values = {"{session}": lambda: shlex.quote(session or ""), "{prompt}": lambda: shlex.quote(str(prompt_path)),
              "<prompt>": lambda: shlex.quote(_text(prompt_path)),
              "{session_flag}": lambda: shlex.join(session_flag or [])}
    out, pos = [], 0
    for start, end, ph, prefix in _tokens(cli):
        if ph is None:
            continue
        out.append(cli[pos:start] + prefix + values[ph]())
        pos = end
    return "".join(out) + cli[pos:]


def placeholder_problem(cli: str | None) -> str | None:
    """Why ``cli`` cannot be run: no prompt placeholder, or one that is not a whole word."""
    if not cli or not _ANY_PROMPT.search(cli):
        return "no {prompt} (the prompt file path) or <prompt> (the prompt text) placeholder"
    try:
        toks = _tokens(cli)
    except ValueError as e:
        return str(e)
    for start, end, ph, _prefix in toks:
        tok = cli[start:end]
        if ph is None and any(p in tok for p in PLACEHOLDERS):
            return (f"placeholder in {tok!r} must be a whole argument — bare or in one pair of quotes "
                    '("<prompt>", {prompt}, "{session}", {session_flag}), not part of a larger word')
        if ph == "{session_flag}" and _prefix:
            return f"{tok!r}: {{session_flag}} is arguments, not a file to redirect from"
    if not any(ph in ("<prompt>", "{prompt}") for _s, _e, ph, _p in toks):
        return 'the prompt placeholder must be a whole argument ("<prompt>" or {prompt}), not part of a larger word'
    return None


def has_prompt_placeholder(cli: str | None) -> bool:
    return placeholder_problem(cli) is None


def _snip(s: str, n: int = 200) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def linked_worktree(worktree: Path) -> bool:
    """True when ``worktree`` is a linked checkout, not the repository's main worktree."""
    common = git_text(["rev-parse", "--path-format=absolute", "--git-common-dir"], worktree)
    gitdir = git_text(["rev-parse", "--path-format=absolute", "--git-dir"], worktree)
    return bool(common and gitdir and Path(common).name == ".git" and Path(gitdir) != Path(common))


def _reviews_handoff_dir(repo_root: Path, node_id: str) -> Path:
    from specy_road.review_files import reviews_dir  # noqa: PLC0415 — keeps adapter import graph small

    return reviews_dir(repo_root, node_id)


def _json(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        d = json.loads(line)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None


class Adapter:
    harness = "generic"
    caps = Capabilities(resume=False, interrupt=False, steer=False, handoff=False, events=False,
                        notes="runs the roster/profile cli; output lines become events, nothing else is known")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        why = placeholder_problem(cli)
        if why:
            raise Unsupported(f"generic harness needs a roster channels.cli or profile access.cli: {why}")
        self._session_flag_check(cli, {ph for _s, _e, ph, _p in _tokens(cli)})
        return Launch(["sh", "-c", substitute_prompt(cli, prompt_path)])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        raise Unsupported(f"{self.harness}: resume is not supported")

    def parse(self, line: str) -> Parsed | None:
        raw = line.strip()
        if not raw:
            return None
        return Parsed("output", _snip(raw), detail={"message": raw})

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        raise Unsupported(f"{self.harness}: no native session to hand off")

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        """The arguments ``{session_flag}`` expands to; ``None`` where the harness has no such flag."""
        return None

    def _session_flag_check(self, cli: str, named: set[str | None]) -> None:
        if "{session_flag}" in named and self.session_flag("", False) is None:
            raise Unsupported(f"channels.cli: {{session_flag}} is defined only for claude-code, not {self.harness}; "
                              f"use {{session}} with the harness's own flag: {cli}")

    def _custom(self, cli: str | None, prompt_path: Path, session_id: str | None = None) -> Launch | None:
        """The roster's own command, when it has the placeholders this call needs.

        ``{prompt}`` is the prompt file path; ``{session}`` (optional) is the
        native session id and ``{session_flag}`` the harness's argument for it
        (:meth:`session_flag`). A resume uses the custom command only when it
        names one of them, since otherwise the default command is the only
        one that knows the harness's resume flag.
        """
        if not cli:
            return None
        why = placeholder_problem(cli)
        if why:
            # Never fall back to the vendor default: that would silently
            # widen (or change) the permissions the adopter wrote down.
            raise Unsupported(f"channels.cli / access.cli: {why}: {cli}")
        named = {ph for _s, _e, ph, _p in _tokens(cli)}
        self._session_flag_check(cli, named)
        if session_id is not None and not named & _SESSION:
            return None
        # On launch a command that names {session} gets a fresh id, and the
        # record keeps it, so the same command serves `message` / `resume`.
        sid = session_id if session_id is not None else (str(uuid.uuid4()) if named & _SESSION else None)
        flag = self.session_flag(sid, session_id is not None) if "{session_flag}" in named else None
        return Launch(["sh", "-c", substitute_prompt(cli, prompt_path, sid, flag)], session_id=sid)


class ClaudeCode(Adapter):
    harness = "claude-code"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="claude -p stream-json; session id chosen up front; resume = `claude -p --resume`; "
                              "no interrupt short of SIGTERM (turn is lost); hand off with `claude --resume`")

    def _add_dir(self, worktree: Path, repo_root: Path | None, node_id: str | None) -> list[str]:
        if not repo_root or not node_id or not linked_worktree(worktree):
            return []
        return ["--add-dir", str(_reviews_handoff_dir(repo_root, node_id))]

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        sid = str(uuid.uuid4())
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["claude", "-p", "--output-format", "stream-json", "--verbose", "--session-id", sid,
                       *_model_flag("--model", model), "--permission-mode", "acceptEdits",
                       *self._add_dir(worktree, repo_root, node_id), STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=sid)

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        return Launch(["claude", "-p", "--resume", session_id, "--output-format", "stream-json", "--verbose",
                       "--permission-mode", "acceptEdits", *self._add_dir(worktree, repo_root, node_id),
                       STDIN_INSTRUCTION],
                      stdin=_text(prompt_path), session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        sid = d.get("session_id")
        t = d.get("type")
        if t == "system" and d.get("subtype") == "init":
            return Parsed("started", f"claude session {sid} ({d.get('model', '?')})", sid)
        if t == "assistant":
            parts = (d.get("message") or {}).get("content") or []
            text = " ".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")
            return Parsed("output", _snip(text) or "(tool use)", sid)
        if t == "result":
            text = str(d.get("result") or d.get("api_error") or "")
            ok = not d.get("is_error") and d.get("subtype") == "success"
            cost = d.get("total_cost_usd")
            summary = (f"{d.get('subtype')}: {_snip(text)}" if ok else _snip(text) or f"{d.get('subtype')}: error")
            detail: dict[str, Any] = {}
            if cost is not None:
                detail["cost_usd"] = cost
            if text:
                detail["message"] = text
            return Parsed("turn_completed" if ok else "error", summary, sid, detail or None)
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["claude", "--resume", session_id]

    def session_flag(self, session_id: str, resume: bool) -> list[str] | None:
        # `--session-id` is refused for a session that exists, so a resume needs `--resume`.
        return ["--resume", session_id] if resume else ["--session-id", session_id]


class Codex(Adapter):
    harness = "codex"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="codex exec --json (prompt on stdin); thread id from thread.started; "
                              "resume = `codex exec resume <id> -` (prompt on stdin); hand off with `codex resume`")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["codex", "exec", "--json", *_model_flag("-m", model), *CODEX_POLICY,
                       "-C", str(worktree), "-"], stdin=_text(prompt_path))

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        # Same sandbox and approval policy as the launch, and the prompt on
        # stdin again: an argv string is capped at 128 KiB on Linux. `exec
        # resume` takes neither --sandbox nor -C (the wrapper runs it in the
        # worktree), so the policy goes in as config overrides.
        return Launch(["codex", "exec", "resume", "--json", *CODEX_POLICY, session_id, "-"],
                      stdin=_text(prompt_path), session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
        t = d.get("type")
        if t == "thread.started":
            return Parsed("started", f"codex thread {d.get('thread_id')}", d.get("thread_id"))
        if t == "item.completed":
            item = d.get("item") or {}
            if item.get("type") == "agent_message":
                text = str(item.get("text") or "")
                return Parsed("output", _snip(text) or "(empty message)",
                              detail={"message": text} if text else None)
            return Parsed("output", f"{item.get('type', 'item')} done")
        if t == "turn.completed":
            return Parsed("turn_completed", "turn completed", detail={"usage": d.get("usage")})
        if t in ("turn.failed", "error"):
            raw = json.dumps(d.get("error") or d.get("message") or d)
            return Parsed("error", _snip(raw), detail={"message": raw})
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["codex", "resume", session_id]


class Cursor(Adapter):
    harness = "cursor"
    caps = Capabilities(resume=True, interrupt=False, steer=False, handoff=True, events=True,
                        notes="agent -p --force --trust stream-json (--force force-allows every command not denied; --trust "
                              "skips a new worktree's trust prompt; print mode can write and run shell); session id "
                              "from the first event; resume = `agent -p --resume` (undocumented with a new prompt: verify)")

    def launch(self, prompt_path: Path, worktree: Path, model: str | None, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        custom = self._custom(cli, prompt_path)
        if custom:
            return custom
        return Launch(["agent", "-p", "--output-format", "stream-json", "--force", "--trust",   # new worktree: untrusted
                       *_model_flag("--model", model), "--workspace", str(worktree), _text(prompt_path)])

    def resume(self, session_id: str, prompt_path: Path, worktree: Path, model: str, cli: str | None,
               *, node_id: str | None = None, repo_root: Path | None = None) -> Launch:
        custom = self._custom(cli, prompt_path, session_id)
        if custom:
            return custom
        return Launch(["agent", "-p", "--resume", session_id, "--output-format", "stream-json", "--force", "--trust",
                       "--workspace", str(worktree), _text(prompt_path)], session_id=session_id)

    def parse(self, line: str) -> Parsed | None:
        d = _json(line)
        if not d:
            return None
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
        if t == "result":
            text = str(d.get("result") or "")
            ok = not d.get("is_error")
            summary = f"{d.get('subtype')}: {_snip(text)}" if ok else _snip(text) or f"{d.get('subtype')}: error"
            detail = {"message": text} if text else None
            return Parsed("turn_completed" if ok else "error", summary, sid, detail)
        return None

    def human_resume(self, session_id: str, worktree: Path) -> list[str]:
        return ["agent", "--resume", session_id]


ADAPTERS: dict[str, Adapter] = {a.harness: a for a in (Adapter(), ClaudeCode(), Codex(), Cursor())}
assert set(ADAPTERS) == set(HARNESSES)


def adapter_for(harness: str) -> Adapter:
    try:
        return ADAPTERS[harness]
    except KeyError:
        raise Unsupported(f"unknown harness {harness!r}; expected one of {', '.join(HARNESSES)}") from None
